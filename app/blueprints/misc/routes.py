from flask import (
    render_template, request, redirect, url_for, session, 
    jsonify, flash, send_file, make_response, current_app, send_from_directory, abort, Blueprint, Response
)
import os
import logging
import traceback
from datetime import datetime, timedelta
import json
import glob
from werkzeug.utils import secure_filename
from app.blueprints.misc import bp
from app.utils.common import CommonUtils as Utils
from app.utils.common import standardize_template_data
import time
import sqlite3
import base64
import qrcode
from app.utils.image_processing import process_plate_image
from app.utils.common import get_estado_guia
import pytz
from app.utils.pdf_generator import Pdf_generatorUtils

# Database path (assuming it's at the workspace root)
DB_PATH = 'tiquetes.db'

# Configurar logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG) # <-- Forzar nivel DEBUG para este logger

# URLs de los Webhooks en Make.com
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"
REGISTER_WEBHOOK_URL = "https://hook.us2.make.com/f63o7rmsuixytjfqxq3gjljnscqhiedl"
REVALIDATION_WEBHOOK_URL = "https://hook.us2.make.com/bok045bvtwpj89ig58nhrmx1x09yh56u"
ADMIN_NOTIFICATION_WEBHOOK_URL = "https://hook.us2.make.com/wpeskbay7k21c3jnthu86lyo081r76fe"
PESAJE_WEBHOOK_URL = "https://hook.us2.make.com/srw5ti54ulwuxtvocrj2lypa5pmq3im4"
AUTORIZACION_WEBHOOK_URL = "https://hook.us2.make.com/py29fwgfrehp9il45832acotytu8xr5s"
REGISTRO_PESO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"
CLASIFICACION_WEBHOOK_URL = "https://hook.us2.make.com/clasificacion_webhook_url"
REGISTRO_CLASIFICACION_WEBHOOK_URL = "https://hook.us2.make.com/ydtogfd3mln2ixbcuam0xrd2m9odfgna"
PLACA_WEBHOOK_URL = "https://hook.us2.make.com/a2yotw5cls6qxom2iacvyaoh2b9uk9ip"
REGISTRO_PESO_NETO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"  # Using the same URL as REGISTRO_PESO_WEBHOOK_URL for now

codigos_autorizacion = {}


# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@bp.route('/guias/<filename>')
def serve_guia(filename):
    """
    Sirve los archivos HTML de las guías de proceso
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    try:
        logger.info(f"Intentando servir guía: {filename}")
        
        # Extraer el código de guía del nombre del archivo eliminando todos los prefijos comunes
        codigo_guia = filename.replace('.html', '')
        # Remover prefijos comunes (guia_, pesaje_, etc.)
        prefijos_a_remover = ['guia_', 'pesaje_', 'clasificacion_', 'salida_', 'entrada_']
        for prefijo in prefijos_a_remover:
            codigo_guia = codigo_guia.replace(prefijo, '')
        
        logger.info(f"Código de guía extraído después de quitar prefijos: {codigo_guia}")
        
        # Ruta del archivo de guía solicitado
        guia_path = os.path.join(current_app.config['GUIAS_FOLDER'], filename)
        
        # Si el archivo no existe, verificar si tenemos que buscar por código base
        if not os.path.exists(guia_path):
            logger.info(f"Archivo de guía no encontrado directamente: {guia_path}")
            # Extraer el código base si el código contiene guión bajo
            if '_' in codigo_guia:
                codigo_base = codigo_guia.split('_')[0]
                guias_folder = current_app.config['GUIAS_FOLDER']
                # Buscar las guías con ese código base
                guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}*.html'))
                
                if guias_files:
                    # Ordenar por fecha de modificación, más reciente primero
                    guias_files.sort(key=os.path.getmtime, reverse=True)
                    latest_guia = os.path.basename(guias_files[0])
                    logger.info(f"Redirigiendo a la guía más reciente: {latest_guia}")
                    # Redirigir a la versión más reciente
                    return redirect(url_for('misc.serve_guia', filename=latest_guia))
            
            logger.error(f"No se encontró ninguna guía para: {codigo_guia}")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Obtener datos actualizados de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia}")
            return render_template('error.html', message="Datos de guía no encontrados"), 404
            
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        # Servir el archivo actualizado
        return send_from_directory(current_app.config['GUIAS_FOLDER'], filename)
        
    except Exception as e:
        logger.error(f"Error sirviendo guía: {str(e)}")
        return render_template('error.html', message="Error al servir la guía"), 500


@bp.route('/', methods=['GET', 'POST'])
def upload_file():
    """
    Handles file upload and processing
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    if request.method == 'POST':
        try:
            session.clear()
            
            if 'file' not in request.files:
                return render_template('error.html', message="No se ha seleccionado ningún archivo.")
                
            file = request.files['file']
            plate_file = request.files.get('plate_file')
            
            if file.filename == '':
                return render_template('error.html', message="No se ha seleccionado ningún archivo.")
                
            if file and allowed_file(file.filename):
                try:
                    # Guardar imagen del tiquete
                    filename = secure_filename(file.filename)
                    # Asegurarse de que el directorio de uploads exista
                    uploads_dir = current_app.config.get('UPLOAD_FOLDER', os.path.join(os.getcwd(), 'static', 'uploads'))
                    if not os.path.exists(uploads_dir):
                        os.makedirs(uploads_dir)
                        
                    image_path = os.path.join(uploads_dir, filename)
                    file.save(image_path)
                    session['image_filename'] = filename
                    logger.info(f"Imagen guardada en: {image_path}")

                    # Procesar imagen de placa si existe
                    if plate_file and plate_file.filename != '' and allowed_file(plate_file.filename):
                        plate_filename = secure_filename(plate_file.filename)
                        plate_path = os.path.join(uploads_dir, plate_filename)
                        plate_file.save(plate_path)
                        session['plate_image_filename'] = plate_filename
                        logger.info(f"Imagen de placa guardada en: {plate_path}")
                    
                    # Guardar sesión antes de redirigir
                    session.modified = True
                    logger.info(f"Redirigiendo a: {url_for('entrada.processing')}")
                    return redirect(url_for('entrada.processing'))
                except Exception as e:
                    logger.error(f"Error guardando archivo: {str(e)}")
                    logger.error(traceback.format_exc())
                    return render_template('error.html', message=f"Error procesando el archivo: {str(e)}")
            else:
                return render_template('error.html', message="Tipo de archivo no permitido.")
        except Exception as e:
            logger.error(f"Error general en upload_file: {str(e)}")
            logger.error(traceback.format_exc())
            return render_template('error.html', message=f"Error general en la aplicación: {str(e)}")
    
    # Si es GET, redirigir a la pantalla principal
    return redirect(url_for('entrada.home'))


@bp.route('/reprocess_plate', methods=['POST'])
def reprocess_plate():
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    try:
        plate_image_filename = session.get('plate_image_filename')
        if not plate_image_filename:
            return jsonify({
                'success': False,
                'message': 'No hay imagen de placa para procesar'
            })
        
        plate_path = os.path.join(current_app.config['UPLOAD_FOLDER'], plate_image_filename)
        if not os.path.exists(plate_path):
            return jsonify({
                'success': False,
                'message': 'No se encontró la imagen de la placa'
            })
        
        # Procesar la imagen de la placa
        result = process_plate_image(plate_path, plate_image_filename)
        
        if result.get("result") == "ok":
            session['plate_text'] = result.get("plate_text")
            session.pop('plate_error', None)
            return jsonify({
                'success': True,
                'message': 'Placa procesada correctamente'
            })
        else:
            session['plate_error'] = result.get("message")
            session.pop('plate_text', None)
            return jsonify({
                'success': False,
                'message': result.get("message")
            })
            
    except Exception as e:
        logger.error(f"Error reprocesando placa: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })


@bp.route('/revalidation_results')
def revalidation_results():
    """
    Renderiza la página de resultados de revalidación
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    try:
        return render_template('revalidation_results.html')
    except Exception as e:
        logger.error(f"Error en revalidation_results: {str(e)}")
        return render_template('error.html', message="Error al mostrar resultados de revalidación"), 500


@bp.route('/revalidation_success')
def revalidation_success():
    """
    Renderiza la página de éxito de revalidación
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    try:
        # Guardar información de las variables en la sesión para depuración
        logger.info("Contenido de la sesión en revalidation_success:")
        for key, value in session.items():
            if key != 'webhook_response':
                logger.info(f"  Sesión[{key}] = {value}")
            else:
                logger.info(f"  Sesión[{key}] existe: {value is not None}")
        
        webhook_response = session.get('webhook_response', {})
        table_data = session.get('table_data', [])
        
        # Asegurarse de que tenemos la imagen del tiquete
        image_filename = session.get('image_filename')
        if not image_filename:
            logger.warning("No se encontró la imagen del tiquete en la sesión.")
        
        if not webhook_response or not webhook_response.get('data'):
            # Log para depuración
            logger.warning("No se encontró webhook_response o data en la sesión. webhook_response: %s", webhook_response)
            logger.warning("table_data: %s", table_data)
            flash('El proceso de revalidación ha sido interrumpido o la sesión ha expirado', 'warning')
            return redirect(url_for('entrada.review'))
            
        data = webhook_response['data']
        
        # Determinar qué campos fueron modificados
        modified_fields = {}
        for row in table_data:
            campo = row.get('campo')
            original = row.get('original')
            sugerido = row.get('sugerido')
            if original != sugerido:
                modified_fields[campo] = True
                
        # Log para depuración
        logger.info("Campos modificados: %s", modified_fields)
        
        # Guardar indicadores de campos modificados en la sesión
        session['nombre_modificado'] = bool(modified_fields.get('Nombre del Agricultor'))
        session['codigo_modificado'] = bool(modified_fields.get('Código'))
        session['placa_modificado'] = bool(modified_fields.get('Placa'))
        session['cantidad_de_racimos_modificado'] = bool(modified_fields.get('Cantidad de Racimos'))
        session['acarreo_modificado'] = bool(modified_fields.get('Se Acarreó'))
        session['cargo_modificado'] = bool(modified_fields.get('Se Cargó'))
        session['transportador_modificado'] = bool(modified_fields.get('Transportador'))
        session['fecha_modificado'] = bool(modified_fields.get('Fecha'))
        session.modified = True
        
        logger.info("Guardados en sesión: nombre_modificado=%s, codigo_modificado=%s", 
                   session.get('nombre_modificado'), session.get('codigo_modificado'))
                   
        # Para debugging, muestra todos los datos disponibles
        logger.info("Data para la plantilla: %s", data)
        
        # Para asegurarse de que la sesión se guarde correctamente
        session.modified = True
        
        return render_template('misc/revalidation_success.html',
                             image_filename=image_filename,
                             nombre_agricultor=data.get('nombre_agricultor', 'No disponible'),
                             codigo=data.get('codigo', 'No disponible'),
                             racimos=data.get('racimos', 'No disponible'),
                             placa=data.get('placa', 'No disponible'),
                             acarreo=data.get('acarreo', 'No disponible'),
                             cargo=data.get('cargo', 'No disponible'),
                             transportador=data.get('transportador', 'No disponible'),
                             fecha_tiquete=data.get('fecha_tiquete', 'No disponible'),
                             hora_registro=datetime.now().strftime("%H:%M:%S"),
                             nota=data.get('nota', 'No disponible'),
                             nombre_agricultor_modificado=session.get('nombre_modificado', False),
                             codigo_modificado=session.get('codigo_modificado', False),
                             placa_modificado=session.get('placa_modificado', False),
                             cantidad_de_racimos_modificado=session.get('cantidad_de_racimos_modificado', False),
                             acarreo_modificado=session.get('acarreo_modificado', False),
                             cargo_modificado=session.get('cargo_modificado', False),
                             transportador_modificado=session.get('transportador_modificado', False),
                             fecha_modificado=session.get('fecha_modificado', False))
    except Exception as e:
        logger.error(f"Error en revalidation_success: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al mostrar página de éxito de revalidación"), 500


@bp.route('/ver_resultados_pesaje/<codigo_guia>')
def ver_resultados_pesaje(codigo_guia):
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    # Obtener datos de la sesión actual
    peso_bruto = session.get('peso_bruto')
    estado_actual = session.get('estado_actual')
    current_app.logger.info(f"ver_resultados_pesaje: Datos de sesión: peso_bruto={peso_bruto}, estado_actual={estado_actual}, codigo_guia={codigo_guia}")
    
    # Obtener datos del pesaje si no están en la sesión
    pesaje_data = None
    try:
        # Inicializar la base de datos
        import db_utils
        
        # Buscar el registro de pesaje por código de guía
        from db_operations import get_pesaje_bruto_by_codigo_guia
        pesaje_data = get_pesaje_bruto_by_codigo_guia(codigo_guia)
        
        if not pesaje_data:
            current_app.logger.warning(f"No se encontró registro de pesaje para el código {codigo_guia}")
            return render_template('error.html', mensaje=f"No se encontró registro de pesaje para el código {codigo_guia}")
        
        current_app.logger.info(f"Datos recibidos de la BD para {codigo_guia}: {pesaje_data}")
        
        # Extraer el código de proveedor del código guía
        codigo_proveedor = None
        if '_' in codigo_guia:
            codigo_proveedor = codigo_guia.split('_')[0]
        else:
            codigo_proveedor = codigo_guia[:8] if len(codigo_guia) >= 8 else codigo_guia
        
        current_app.logger.info(f"Extrayendo código de proveedor del código guía: {codigo_proveedor}")
        
        # Normalizar el transportador a transportista
        transportista = pesaje_data.get('transportador', 'No disponible')
        current_app.logger.info(f"Mapeando transportador a transportista: {transportista}")
        
        # Para cada campo faltante, buscar en otros registros SOLO si está ausente en el registro actual
        nombre_proveedor = pesaje_data.get('nombre_proveedor')
        cantidad_racimos = pesaje_data.get('racimos')
        
        # Solo buscar información del proveedor si falta en este registro específico
        if (not nombre_proveedor or nombre_proveedor == 'None' or nombre_proveedor == 'No disponible' or 
            not cantidad_racimos or cantidad_racimos == 'None' or cantidad_racimos == 'No disponible' or
            cantidad_racimos == 'N/A'):
            
            current_app.logger.info(f"Buscando información adicional para el código de proveedor: {codigo_proveedor}")
            
            try:
                from db_operations import get_provider_by_code
                from db_utils import get_entry_records
                
                # Primero intentamos obtener información de registros de entrada con el mismo código de guía
                entry_records = get_entry_records({'codigo_guia': codigo_guia})
                if entry_records and len(entry_records) > 0:
                    current_app.logger.info(f"Encontrados {len(entry_records)} registros de entrada para {codigo_guia}")
                    entry = entry_records[0]  # Tomamos el primer registro
                    
                    # Sólo actualizamos los campos que faltan
                    if (not nombre_proveedor or nombre_proveedor == 'None' or nombre_proveedor == 'No disponible'):
                        nombre_proveedor = entry.get('nombre_proveedor', 'Sin nombre')
                        current_app.logger.info(f"Nombre de proveedor actualizado desde registro de entrada: {nombre_proveedor}")
                    
                    if (not cantidad_racimos or cantidad_racimos == 'None' or cantidad_racimos == 'No disponible' or cantidad_racimos == 'N/A'):
                        cantidad_racimos = entry.get('cantidad_racimos', 'N/A')
                        current_app.logger.info(f"Cantidad de racimos actualizada desde registro de entrada: {cantidad_racimos}")
                    
                    # Actualizar transportista y placa si no están disponibles
                    if (not transportista or transportista == 'None' or transportista == 'No disponible'):
                        transportista = entry.get('transportador', 'No disponible')
                        current_app.logger.info(f"Transportista actualizado desde registro de entrada: {transportista}")
                    
                    placa = pesaje_data.get('placa', 'No disponible')
                    if (not placa or placa == 'None' or placa == 'No disponible'):
                        placa = entry.get('placa', 'No disponible')
                        current_app.logger.info(f"Placa actualizada desde registro de entrada: {placa}")
                else:
                    # Solo si no encontramos registros de entrada para este código de guía específico,
                    # buscamos información del proveedor en general (podría ser de otras entregas)
                    current_app.logger.info(f"No hay registros de entrada para este código de guía, buscando por código de proveedor")
                    provider_info = get_provider_by_code(codigo_proveedor, codigo_guia_actual=codigo_guia)
                    
                    if provider_info:
                        # IMPORTANTE: Solo actualizamos campos que realmente faltan
                        # para no mezclar datos entre diferentes entregas
                        if (not nombre_proveedor or nombre_proveedor == 'None' or nombre_proveedor == 'No disponible'):
                            nombre_proveedor = provider_info.get('nombre', 'Sin nombre')
                            current_app.logger.info(f"Nombre de proveedor actualizado desde información general: {nombre_proveedor}")
                            current_app.logger.warning("Usando información de proveedor de otras entregas, puede no ser exacta para esta guía")
                        
                        if (not cantidad_racimos or cantidad_racimos == 'None' or cantidad_racimos == 'No disponible' or cantidad_racimos == 'N/A'):
                            # Aquí preferimos no asignar racimos de otras entregas ya que puede variar mucho
                            # Solo asignamos un valor general si no hay otra fuente
                            if not provider_info.get('es_dato_otra_entrega', False):
                                cantidad_racimos = provider_info.get('racimos', 'N/A')
                                current_app.logger.info(f"Cantidad de racimos actualizada: {cantidad_racimos}")
                            else:
                                current_app.logger.warning("No se asignan racimos de otras entregas para evitar datos incorrectos")
                
                # Actualizar el registro de pesaje con la información complementaria
                # Solo si encontramos datos reales y no valores por defecto
                update_data = {}
                
                if nombre_proveedor and nombre_proveedor != 'Sin nombre' and nombre_proveedor != 'No disponible':
                    update_data['nombre_proveedor'] = nombre_proveedor
                
                if cantidad_racimos and cantidad_racimos != 'N/A' and cantidad_racimos != 'No disponible':
                    update_data['racimos'] = cantidad_racimos
                
                if transportista and transportista != 'No disponible':
                    update_data['transportador'] = transportista
                
                if placa and placa != 'No disponible':
                    update_data['placa'] = placa
                
                if update_data:
                    try:
                        from db_operations import update_pesaje_bruto
                        update_pesaje_bruto(codigo_guia, update_data)
                        current_app.logger.info(f"Pesaje actualizado con información complementaria: {update_data}")
                    except Exception as e:
                        current_app.logger.error(f"Error al actualizar pesaje: {str(e)}")
                
            except ImportError as e:
                current_app.logger.error(f"Error al importar módulos necesarios: {str(e)}")
            except Exception as e:
                current_app.logger.error(f"Error al buscar información del proveedor: {str(e)}")
        
        # Asegurar que los datos estén correctos antes de enviarlos a la plantilla
        if not nombre_proveedor or nombre_proveedor == 'None' or nombre_proveedor == 'No disponible':
            nombre_proveedor = 'Sin nombre'
        
        if not cantidad_racimos or cantidad_racimos == 'None' or cantidad_racimos == 'No disponible':
            cantidad_racimos = 'N/A'
        
        current_app.logger.info(f"Datos estandarizados para {codigo_guia}: código_proveedor={codigo_proveedor}, nombre_proveedor={nombre_proveedor}, racimos={cantidad_racimos}")
        
        # Variables para la plantilla
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': pesaje_data.get('peso_bruto', 'N/A'),
            'tipo_pesaje': pesaje_data.get('tipo_pesaje', 'N/A'),
            'fecha_pesaje': pesaje_data.get('fecha_pesaje', 'N/A'),
            'hora_pesaje': pesaje_data.get('hora_pesaje', 'N/A'),
            'imagen_pesaje': pesaje_data.get('imagen_pesaje', ''),
            'transportador': transportista,
            'placa': placa,
            'racimos': cantidad_racimos,
            'acarreo': pesaje_data.get('acarreo', 'No'),
            'cargo': pesaje_data.get('cargo', 'No'),
            'fotos_pesaje': pesaje_data.get('fotos_pesaje', []),
            'placa_detectada': pesaje_data.get('placa_detectada', ''),
            'placa_coincide': pesaje_data.get('placa_coincide', False),
            'codigo_guia_transporte_sap': pesaje_data.get('codigo_guia_transporte_sap', 'No disponible')
        }
        
        # Si no existe un estado completado, mostrar un mensaje de advertencia
        if not pesaje_data.get('estado') or pesaje_data.get('estado') != 'pesaje_completado':
            current_app.logger.warning(f"Mostrando resultados para guía {codigo_guia} sin estado completado")
        
        # Renderizar la plantilla con los datos
        return render_template('pesaje/resultados_pesaje.html', **template_data)
        
    except Exception as e:
        current_app.logger.error(f"Error al obtener resultados de pesaje: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        return render_template('error.html', mensaje=f"Error al obtener resultados de pesaje: {str(e)}")


@bp.route('/process_validated_data', methods=['POST'])
def process_validated_data():
    """
    Procesa los datos validados y genera el PDF final.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Logging detallado de la sesión para depuración
        logger.info("Contenido de la sesión en process_validated_data:")
        for key, value in session.items():
            logger.info(f"  Sesión[{key}] = {value if key != 'webhook_response' else 'objeto grande'}")
        
        # Obtener el webhook response guardado en la sesión
        webhook_response = session.get('webhook_response', {})
        webhook_data = webhook_response.get('data', {})
        
        logger.info(f"webhook_response keys: {webhook_response.keys() if isinstance(webhook_response, dict) else 'no es un diccionario'}")
        
        if not webhook_data:
            logger.error("No hay datos validados para procesar")
            logger.error(f"webhook_response: {webhook_response}")
            return jsonify({
                "status": "error",
                "message": "No hay datos validados"
            }), 400
        
        # Logging para depuración
        logger.info(f"Datos recibidos en process_validated_data: {webhook_data}")
        
        # Sanitizar la nota para evitar datos que puedan causar problemas (máximo 500 caracteres)
        if 'nota' in webhook_data and webhook_data['nota']:
            webhook_data['nota'] = webhook_data['nota'][:500]
            logger.info(f"Nota sanitizada: {webhook_data['nota']}")
        
        # Validar que hay datos esenciales
        # Verificar tanto las claves en formato camelCase como las claves en formato con espacios
        codigo = webhook_data.get('codigo') or webhook_data.get('Código', '')
        nombre_agricultor = webhook_data.get('nombre_agricultor') or webhook_data.get('Nombre del Agricultor', '')
        
        if not codigo or not nombre_agricultor:
            logger.error("Faltan datos esenciales en la respuesta del webhook")
            logger.error(f"Datos disponibles: codigo={codigo}, nombre={nombre_agricultor}")
            return jsonify({
                "status": "error", 
                "message": "Faltan datos esenciales (código o nombre)"
            }), 400
        
        # Verificar si el proveedor existe en la base de datos
        from db_operations import get_provider_by_code
        provider_info = get_provider_by_code(codigo)
        
        if not provider_info:
            # Si el proveedor no existe, añadir una nota al respecto
            nota_actual = webhook_data.get('nota', '')
            nota_proveedor = "ADVERTENCIA: El código de proveedor no se encuentra en la base de datos."
            
            if nota_actual:
                webhook_data['nota'] = f"{nota_actual}\n\n{nota_proveedor}"
            else:
                webhook_data['nota'] = nota_proveedor
                
            logger.warning(f"Proveedor con código {codigo} no encontrado en la base de datos")
        
        # Obtener otros datos necesarios
        image_filename = session.get('image_filename')
        fecha_procesamiento = datetime.now().strftime("%d/%m/%Y")
        hora_procesamiento = datetime.now().strftime("%H:%M:%S")
        
        if not image_filename:
            logger.error("No se encontró la imagen del tiquete en la sesión")
            return jsonify({
                "status": "error", 
                "message": "No se encontró la imagen del tiquete"
            }), 400
            
        table_data = session.get('table_data', [])
        
        # Registrar el tiquete generando el PDF y guardando la información
        # Aprovechamos la función generate_pdf para generar el PDF
        try:
            # Generar un nombre por defecto para el QR que usaremos en generate_pdf
            now = datetime.now()
            default_qr_filename = f"default_qr_{now.strftime('%Y%m%d%H%M%S')}.png"
            session['qr_filename'] = default_qr_filename
            session.modified = True
            
            # Generar el PDF
            from app.utils.pdf_generator import Pdf_generatorUtils
            pdf_generator = Pdf_generatorUtils(current_app)
            pdf_filename = pdf_generator.generate_pdf(
                webhook_data,
                image_filename,
                fecha_procesamiento,
                hora_procesamiento,
                webhook_data,  # Pasamos los mismos datos como revalidation_data
                None  # No pasamos código guía para que se genere uno nuevo
            )
            
            if not pdf_filename:
                logger.error("La función generate_pdf no devolvió un nombre de archivo válido")
                return jsonify({
                    "status": "error",
                    "message": "Error generando el PDF: Nombre de archivo no válido"
                }), 500
            
            # Guardar el nombre del PDF en la sesión
            session['pdf_filename'] = pdf_filename
            session.modified = True
            
            # Verificar que el archivo PDF realmente existe
            pdf_path = os.path.join(current_app.config['PDF_FOLDER'], pdf_filename)
            if not os.path.exists(pdf_path):
                logger.error(f"El archivo PDF generado no existe en la ruta: {pdf_path}")
                return jsonify({
                    "status": "error",
                    "message": f"El archivo PDF generado no existe: {pdf_filename}"
                }), 500
            
            # Verificar que el archivo QR existe
            qr_filename = session.get('qr_filename')
            qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
            if not os.path.exists(qr_path):
                logger.error(f"El archivo QR no existe en la ruta: {qr_path}")
                
                # Generar un nuevo QR desde cero con los datos actuales
                try:
                    # Generar un nuevo nombre de archivo para el QR
                    now = datetime.now()
                    new_qr_filename = f"qr_{codigo}_{now.strftime('%Y%m%d%H%M%S')}.png"
                    new_qr_path = os.path.join(current_app.config['QR_FOLDER'], new_qr_filename)
                    
                    # Preparar datos básicos para el QR
                    qr_data = {
                        "codigo": codigo,
                        "nombre": nombre_agricultor,
                        "fecha": now.strftime("%d/%m/%Y %H:%M:%S"),
                        "racimos": webhook_data.get('racimos', ''),
                        "placa": webhook_data.get('placa', '')
                    }
                    
                    # Generar un código guía temporal para la URL
                    temp_codigo_guia = f"{codigo}_{now.strftime('%Y%m%d%H%M%S')}"
                    
                    # Generar URL para el código QR usando url_for
                    qr_url = url_for('entrada.ver_registro_entrada', codigo_guia=temp_codigo_guia, _external=True)
                    
                    # Generar un nuevo QR con la URL dinámica
                    utils.generar_qr(qr_url, new_qr_path)
                    
                    # Verificar que se generó correctamente
                    if os.path.exists(new_qr_path):
                        session['qr_filename'] = new_qr_filename
                        session.modified = True
                        logger.info(f"Se generó un nuevo QR: {new_qr_filename}")
                    else:
                        raise Exception(f"No se pudo generar el archivo QR en: {new_qr_path}")
                        
                except Exception as e:
                    logger.error(f"Error al generar nuevo QR: {str(e)}")
                    logger.error(traceback.format_exc())
                    
                    # Buscar algún QR ya existente como último recurso
                    qr_files = [f for f in os.listdir(current_app.config['QR_FOLDER']) 
                               if os.path.isfile(os.path.join(current_app.config['QR_FOLDER'], f)) and f.endswith('.png')]
                    
                    if qr_files:
                        qr_files.sort(key=lambda x: os.path.getmtime(os.path.join(current_app.config['QR_FOLDER'], x)), reverse=True)
                        qr_filename = qr_files[0]
                        session['qr_filename'] = qr_filename
                        session.modified = True
                        logger.info(f"Se encontró un QR alternativo: {qr_filename}")
                    else:
                        # Si no hay ningún QR, informar del error
                        logger.error("No se encontró ningún archivo QR alternativo")
            
            logger.info(f"PDF generado correctamente: {pdf_filename}")
            logger.info(f"QR guardado en sesión: {session.get('qr_filename')}")
            
            # Obtener el código guía del nombre del archivo
            codigo_guia = pdf_filename.replace('tiquete_', '').replace('.pdf', '')
            if '_' in codigo_guia:
                # Asegurar formato código_YYYYMMDD_HHMM manteniendo las dos primeras partes
                parts = codigo_guia.split('_')
                if len(parts) >= 3:
                    codigo_guia = f"{parts[0]}_{parts[1]}_{parts[2]}"
                else:
                    # Si no tiene el formato esperado, usar como está
                    codigo_guia = codigo_guia
            
            session['codigo_guia'] = codigo_guia
            session.modified = True
            logger.info(f"Código guía guardado en sesión: {codigo_guia}")
            
            # Guardar los datos en la base de datos
            try:
                import db_utils
                
                # Preparar datos para guardar en la base de datos
                datos_registro = {
                    'codigo_guia': codigo_guia,
                    'codigo_proveedor': codigo,
                    'nombre_proveedor': nombre_agricultor,
                    'cantidad_racimos': webhook_data.get('racimos', webhook_data.get('Cantidad de Racimos', '')),
                    'placa': webhook_data.get('placa', webhook_data.get('Placa', '')),
                    'transportador': webhook_data.get('transportador', webhook_data.get('Transportador', '')),
                    'acarreo': webhook_data.get('acarreo', webhook_data.get('Se Acarreó', 'NO')),
                    'cargo': webhook_data.get('cargo', webhook_data.get('Se Cargó', 'NO')),
                    'fecha_registro': datetime.now().strftime("%d/%m/%Y"),
                    'hora_registro': datetime.now().strftime("%H:%M:%S"),
                    'image_filename': image_filename,
                    'pdf_filename': pdf_filename,
                    'qr_filename': session.get('qr_filename', '')
                }
                
                # ---- ADD NOTA TO THE RECORD ----
                datos_registro['nota'] = webhook_data.get('nota', webhook_data.get('Nota', '')) # Add the note here
                
                # Guardar en la base de datos
                db_utils.store_entry_record(datos_registro)
                logger.info(f"Datos guardados en la base de datos para código guía: {codigo_guia}")
            except Exception as db_error:
                logger.error(f"Error guardando en la base de datos: {str(db_error)}")
                logger.error(traceback.format_exc())
                # Continuamos porque el PDF ya fue generado, solo log del error
            
            # Redirigir a la página de revisión del PDF
            return jsonify({
                "status": "success",
                "message": "Datos procesados correctamente",
                "redirect": url_for('entrada.review_pdf', _external=True)
            })
            
        except Exception as e:
            logger.error(f"Error generando el PDF: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                "status": "error",
                "message": f"Error generando el PDF: {str(e)}"
            }), 500
            
    except Exception as e:
        logger.error(f"Error procesando datos validados: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Error procesando datos: {str(e)}"
        }), 500


@bp.route('/generar_pdf_registro/<codigo_guia>', methods=['GET'])
def generar_pdf_registro(codigo_guia):
    """
    Genera un PDF del registro de entrada basado en el código de guía.
    """
    try:
        logger.info(f"Generando PDF para código de guía: {codigo_guia}")
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener datos del registro
        try:
            import db_utils
            registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos: {db_error}")
            registro = None
        
        if not registro:
            registro = utils.get_datos_registro(codigo_guia)
            
        if not registro:
            flash(f'No se encontró el registro con código {codigo_guia}', 'error')
            return redirect(url_for('entrada.lista_registros_entrada'))
        
        # Generar PDF
        pdf_filename = registro.get('pdf_filename')
        
        # Si no hay PDF existente, generarlo
        if not pdf_filename or not os.path.exists(os.path.join(current_app.config['PDF_FOLDER'], pdf_filename)):
            logger.info(f"No se encontró PDF existente, generando uno nuevo para {codigo_guia}")
            try:
                # Generar PDF usando Utils
                from app.utils.pdf_generator import Pdf_generatorUtils
                pdf_generator = Pdf_generatorUtils(current_app)
                pdf_filename = pdf_generator.generate_pdf(
                    registro,
                    registro.get('image_filename', ''),
                    registro.get('fecha_registro', ''),
                    registro.get('hora_registro', ''),
                    registro,
                    codigo_guia
                )
                
                # Si no se pudo generar el PDF
                if not pdf_filename:
                    flash('Error generando el PDF', 'error')
                    return redirect(url_for('entrada.lista_registros_entrada'))
                    
            except Exception as e:
                logger.error(f"Error generando PDF: {e}")
                flash(f'Error generando PDF: {e}', 'error')
                return redirect(url_for('entrada.lista_registros_entrada'))
        
        # Enviar el archivo PDF
        return send_file(
            os.path.join(current_app.config['PDF_FOLDER'], pdf_filename),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f"registro_{codigo_guia}.pdf"
        )
        
    except Exception as e:
        logger.error(f"Error en generar_pdf_registro: {e}")
        flash(f'Error generando PDF: {e}', 'error')
        return redirect(url_for('entrada.lista_registros_entrada'))


@bp.route('/generar_pdf_pesaje/<codigo_guia>')
def generar_pdf_pesaje(codigo_guia):
    """
    Genera un PDF del pesaje basado en el código de guía.
    """
    try:
        logger.info(f"Generando PDF de pesaje para código de guía: {codigo_guia}")
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener datos del registro
        import db_utils
        
        # Intentar obtener datos de pesaje desde la base de datos
        datos_pesaje = db_utils.get_pesaje_bruto_by_codigo_guia(codigo_guia)
        
        if not datos_pesaje:
            flash(f'No se encontraron datos de pesaje para el código {codigo_guia}', 'error')
            return redirect(url_for('misc.ver_resultados_pesaje', codigo_guia=codigo_guia))
        
        # Verificación de placa si existe
        verificacion_placa = datos_pesaje.get('verificacion_placa', {})
        placa_detectada = verificacion_placa.get('placa_detectada', '')
        placa_coincide = verificacion_placa.get('coincide', False)
        
        # Verificar imágenes
        imagen_pesaje = None
        if datos_pesaje.get('imagen_peso'):
            imagen_pesaje = url_for('static', filename=f'uploads/{datos_pesaje["imagen_peso"]}', _external=True)
        
        # Fotos adicionales de pesaje
        fotos_pesaje = datos_pesaje.get('fotos_pesaje', [])
        valid_fotos = []
        
        for foto_path in fotos_pesaje:
            if foto_path and os.path.exists(os.path.join(current_app.static_folder, foto_path.replace('static/', ''))):
                # Convertir ruta relativa a URL absoluta
                valid_fotos.append(url_for('static', filename=foto_path.replace('static/', ''), _external=True))
        
        # Usar un QR existente o uno predeterminado en lugar de generar uno nuevo
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        
        # Verificar si el QR ya existe
        if not os.path.exists(qr_path):
            # Si no existe, usar un QR predeterminado en lugar de generarlo
            logger.info(f"No se encontró QR para {codigo_guia}, usando uno alternativo")
            
            # Buscar cualquier QR existente que podamos usar como alternativa
            qr_files = glob.glob(os.path.join(current_app.config['QR_FOLDER'], 'qr_pesaje_*.png'))
            if qr_files:
                # Usar el primer QR encontrado
                qr_filename = os.path.basename(qr_files[0])
                logger.info(f"Se encontró un QR alternativo: {qr_filename}")
            else:
                # Si no hay ningún QR, usar un archivo estático como fallback
                qr_filename = 'default_qr.png'
                logger.warning(f"No se encontraron QR alternativos, usando default_qr.png")
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        # Fecha y hora de generación del PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF usando el mismo template que la vista
        html = render_template('pdf/pesaje_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_pesaje.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_pesaje.get('nombre_proveedor', 'No disponible'),
            transportador=datos_pesaje.get('transportador', 'No disponible'),
            placa=datos_pesaje.get('placa', 'No disponible'),
            peso_bruto=datos_pesaje.get('peso_bruto', 'No disponible'),
            tipo_pesaje=datos_pesaje.get('tipo_pesaje', 'No disponible'),
            fecha_pesaje=datos_pesaje.get('fecha_pesaje', 'No disponible'),
            hora_pesaje=datos_pesaje.get('hora_pesaje', 'No disponible'),
            racimos=datos_pesaje.get('racimos', 'No disponible'),
            codigo_guia_transporte_sap=datos_pesaje.get('codigo_guia_transporte_sap', ''),
            imagen_pesaje=imagen_pesaje,
            qr_code=qr_code,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            fotos_pesaje=valid_fotos,
            verificacion_placa=verificacion_placa,
            placa_detectada=placa_detectada,
            placa_coincide=placa_coincide
        )
        
        # Generar PDF desde HTML usando WeasyPrint en lugar de pdfkit
        try:
            from weasyprint import HTML
            
            # Crear directorio para guardar PDFs si no existe
            pdf_dir = os.path.join(current_app.static_folder, 'pdfs')
            os.makedirs(pdf_dir, exist_ok=True)
            
            # Nombre del archivo PDF
            pdf_filename = f"pesaje_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
            pdf_path = os.path.join(pdf_dir, pdf_filename)
            
            # Generar el PDF con WeasyPrint
            HTML(string=html, base_url=current_app.static_folder).write_pdf(pdf_path)
            
            logger.info(f"PDF generado correctamente con WeasyPrint: {pdf_filename}")
            
            # Ruta para acceder al PDF
            pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
            
            # Retornar la respuesta
            return redirect(pdf_url)
        except Exception as pdf_error:
            logger.error(f"Error generando PDF con WeasyPrint: {pdf_error}")
            logger.error(traceback.format_exc())
            
            # Si falla WeasyPrint, informar al usuario
            flash("Error generando PDF: No se pudo generar el archivo PDF", "error")
            return redirect(url_for('misc.ver_resultados_pesaje', codigo_guia=codigo_guia))
        
    except Exception as e:
        logger.error(f"Error en generar_pdf_pesaje: {e}")
        logger.error(traceback.format_exc())
        flash(f'Error generando PDF de pesaje: {e}', 'error')
        return redirect(url_for('misc.ver_resultados_pesaje', codigo_guia=codigo_guia))


@bp.route('/guia-centralizada/<path:codigo_guia>')
def ver_guia_centralizada(codigo_guia):
    """
    Muestra una vista consolidada del estado y datos de una guía.
    Ahora también maneja códigos de guía con sufijos como _v1, _v2.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener datos de la guía utilizando el código original
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash(f"No se encontraron datos para la guía {codigo_guia}", "warning")
            return render_template('error.html', message=f"Guía {codigo_guia} no encontrada"), 404
        
        # Determinar el estado actual y pasos completados
        estado_info = utils.determinar_estado_guia(codigo_guia, datos_guia)
        
        # Verificar si el proveedor es 'PEPA' (código '999999')
        es_pepa = datos_guia.get('codigo_proveedor') == '999999'
        if es_pepa:
            # Si es PEPA, marcar clasificación como completada
            if 'clasificacion' not in estado_info['pasos_completados']:
                 estado_info['pasos_completados'].append('clasificacion')
                 # Actualizar porcentaje si es necesario (por ejemplo, 60% si solo estaba en pesaje)
                 if estado_info['porcentaje_avance'] < 60:
                     estado_info['porcentaje_avance'] = 60
                 if estado_info['siguiente_paso'] == 'clasificacion':
                     estado_info['siguiente_paso'] = 'pesaje_neto'
                     estado_info['descripcion'] = 'Clasificación omitida (PEPA)'
        
        # Asegurar que el estado refleje que la clasificación está completa si es Pepa
        if es_pepa and 'clasificacion' not in datos_guia.get('pasos_completados', []):
            if 'pasos_completados' not in datos_guia:
                datos_guia['pasos_completados'] = []
            datos_guia['pasos_completados'].append('clasificacion')
        
        # Generar QR code
        qr_filename = f'qr_guia_{codigo_guia}.png'
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        qr_url_route = url_for('.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        if not os.path.exists(qr_path):
            utils.generar_qr(qr_url_route, qr_path)
        qr_url = url_for('static', filename=f'qr/{qr_filename}')
        
        # Timestamp para cache busting
        now_timestamp = datetime.now().timestamp()
        
        # Preparar el contexto para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia,
            'estado_info': estado_info,
            'es_pepa': es_pepa,
            'qr_url': qr_url,
            'now_timestamp': now_timestamp
            # Ya no pasamos la función aquí
        }
        
        return render_template('guia_centralizada.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar guía centralizada para {codigo_guia}: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al cargar la guía {codigo_guia}: {str(e)}", "error")
        return render_template('error.html', message=f"Error al cargar la guía: {str(e)}")


@bp.route('/guia-alt/<codigo_guia>')
def ver_guia_alternativa(codigo_guia):
    """
    Ruta alternativa para visualizar una guía - usa un método más directo para cargar el template
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = current_app.config.get('utils', Utils(current_app))
    
    try:
        logger.info(f"Accediendo a vista alternativa de guía: {codigo_guia}")
        
        # Obtener datos completos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia}")
            return render_template('error.html', message="Datos de guía no encontrados"), 404
        
        # Verificar si los datos del proveedor están ausentes y buscarlos en otras fuentes
        if (not datos_guia.get('nombre_proveedor') or 
            datos_guia.get('nombre_proveedor') == 'No disponible' or 
            datos_guia.get('nombre_proveedor') == 'N/A'):
            
            # Intentar obtener de registros de entrada
            try:
                import db_utils
                codigo_proveedor = datos_guia.get('codigo_proveedor')
                if not codigo_proveedor and '_' in codigo_guia:
                    codigo_proveedor = codigo_guia.split('_')[0]
                    datos_guia['codigo_proveedor'] = codigo_proveedor
                
                if codigo_proveedor:
                    # Buscar registros de entrada del proveedor
                    entry_records = db_utils.get_entry_records_by_provider_code(codigo_proveedor)
                    if entry_records and len(entry_records) > 0:
                        # Usar el registro más reciente
                        latest_record = entry_records[0]
                        # Campos a verificar y completar
                        campos = [
                            ('nombre_proveedor', 'nombre_proveedor'),
                            ('nombre_agricultor', 'nombre_agricultor'),
                            ('placa', 'placa'),
                            ('transportador', 'transportador'),
                            ('transportista', 'transportista'),
                            ('racimos', 'cantidad_racimos')
                        ]
                        for campo_destino, campo_origen in campos:
                            if latest_record.get(campo_origen) and (
                                not datos_guia.get(campo_destino) or 
                                datos_guia.get(campo_destino) == 'No disponible' or 
                                datos_guia.get(campo_destino) == 'N/A'
                            ):
                                datos_guia[campo_destino] = latest_record.get(campo_origen)
                                logger.info(f"Campo {campo_destino} actualizado desde registro de entrada: {datos_guia[campo_destino]}")
            except Exception as e:
                logger.error(f"Error buscando datos de proveedor: {str(e)}")
        
        # Obtener información del estado actual
        from app.utils.common import get_estado_guia
        estado_info = get_estado_guia(codigo_guia)
        
        # Agregar timestamp para evitar caché en imágenes y recursos
        now_timestamp = int(time.time())
        current_year = datetime.now().year
        
        # Manejo de imagen del tiquete igual que en la vista normal
        # [código existente para manejar la imagen]
        
        # Datos para el template
        datos_template = {
            'estado_info': estado_info,
            'datos_guia': datos_guia,
            'codigo_guia': codigo_guia,
            'now_timestamp': now_timestamp,
            'current_year': current_year,
            'template_version': '1.0.1',
            'qr_url': url_for('static', filename=f'qr/qr_centralizado_{codigo_guia}.png') + f'?v={now_timestamp}'
        }
        
        # Buscar el template manualmente en múltiples ubicaciones
        template_locations = [
            os.path.join(os.getcwd(), 'templates', 'guia_centralizada.html'),
            os.path.join(os.getcwd(), 'app', 'templates', 'guia_centralizada.html'),
            os.path.join(os.getcwd(), 'TiquetesApp', 'templates', 'guia_centralizada.html'),
            os.path.join(os.getcwd(), '..', 'templates', 'guia_centralizada.html'),
        ]
        
        template_content = None
        template_path_used = None
        
        for loc in template_locations:
            if os.path.exists(loc):
                logger.info(f"Encontrado template en: {loc}")
                template_path_used = loc
                with open(loc, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                break
        
        if not template_content:
            logger.error("No se encontró el template en ninguna ubicación")
            return render_template('error.html', message="Error: No se encontró la plantilla en ninguna ubicación")
        
        # Cargar también la plantilla base
        base_template = None
        for loc in [loc.replace('guia_centralizada.html', 'guia_base.html') for loc in template_locations]:
            if os.path.exists(loc):
                logger.info(f"Encontrado template base en: {loc}")
                with open(loc, 'r', encoding='utf-8') as f:
                    base_template = f.read()
                break
        
        # Renderizar manualmente usando Jinja2
        from jinja2 import Environment, FileSystemLoader, Template
        
        # Configurar entorno similar al de Flask
        template_dir = os.path.dirname(template_path_used)
        env = Environment(loader=FileSystemLoader(template_dir))
        
        # Si tenemos el template base, registrarlo primero
        if base_template:
            env.loader.mapping['guia_base.html'] = base_template
        
        # Crear el template y renderizarlo
        template = env.from_string(template_content)
        html_content = template.render(**datos_template)
        
        # Devolver el HTML renderizado
        return html_content
        
    except Exception as e:
        logger.error(f"Error al mostrar vista alternativa para guía {codigo_guia}: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error al mostrar información alternativa de la guía: {str(e)}")


@bp.route('/guardar_captura_tabla', methods=['POST'])
def guardar_captura_tabla():
    """
    Guarda la captura de la tabla de revisión como soporte.
    """
    try:
        # Crear directorio si no existe
        capturas_dir = os.path.join(current_app.static_folder, 'capturas_revision')
        logger.info(f"Intentando crear directorio en: {capturas_dir}")
        os.makedirs(capturas_dir, exist_ok=True)
        
        # Obtener la imagen en base64
        data = request.json
        if not data or 'imagen' not in data:
            logger.error("No se recibió imagen en la solicitud")
            return jsonify({'success': False, 'error': 'No se recibió imagen'})
            
        # Decodificar la imagen
        imagen_data = data['imagen'].split(',')[1]
        imagen_bytes = base64.b64decode(imagen_data)
        
        # Generar nombre único para el archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'revision_tabla_{timestamp}.png'
        filepath = os.path.join(capturas_dir, filename)
        
        logger.info(f"Intentando guardar captura en: {filepath}")
        
        # Guardar la imagen
        with open(filepath, 'wb') as f:
            f.write(imagen_bytes)
            
        logger.info(f"Captura de tabla guardada exitosamente en: {filepath}")
        return jsonify({'success': True, 'filename': filename})
        
    except Exception as e:
        logger.error(f"Error guardando captura de tabla: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)})


def generar_qr_guia(codigo_guia):
    """
    Genera un código QR para una guía específica.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Generar QR si no existe
        qr_filename = f'qr_detalle_proveedor_{codigo_guia}.png'
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('misc.ver_detalle_proveedor', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        return url_for('static', filename=f'qr/{qr_filename}')
    except Exception as e:
        current_app.logger.error(f"Error generando QR para guía {codigo_guia}: {str(e)}")
        return None

def sync_clasificacion_from_json(codigo_guia):
    """
    Sincroniza los datos de clasificación desde el archivo JSON a la base de datos.
    """
    try:
        # Construir la ruta al archivo JSON
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path = os.path.join(current_app.static_folder, 'clasificaciones', json_filename)
        
        if not os.path.exists(json_path):
            logger.warning(f"No existe archivo JSON para la guía {codigo_guia}")
            return False
            
        # Leer el archivo JSON
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
            
        # Conectar a la base de datos
        conn = sqlite3.connect('tiquetes.db')
        cursor = conn.cursor()
        
        # Preparar los datos para la actualización
        datos = {
            'codigo_guia': codigo_guia,
            'fecha_clasificacion': clasificacion_data.get('fecha_registro'),
            'hora_clasificacion': clasificacion_data.get('hora_registro'),
            'clasificacion_manual': json.dumps(clasificacion_data.get('clasificacion_manual', {})),
            'clasificacion_automatica': json.dumps(clasificacion_data.get('clasificacion_automatica', {})),
            'estado': clasificacion_data.get('estado', 'activo')
        }
        
        # Intentar actualizar primero
        cursor.execute("""
            UPDATE clasificaciones 
            SET fecha_clasificacion = :fecha_clasificacion,
                hora_clasificacion = :hora_clasificacion,
                clasificacion_manual = :clasificacion_manual,
                clasificacion_automatica = :clasificacion_automatica,
                estado = :estado
            WHERE codigo_guia = :codigo_guia
        """, datos)
        
        # Si no se actualizó ningún registro, insertar uno nuevo
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO clasificaciones (
                    codigo_guia, fecha_clasificacion, hora_clasificacion,
                    clasificacion_manual, clasificacion_automatica, estado
                ) VALUES (
                    :codigo_guia, :fecha_clasificacion, :hora_clasificacion,
                    :clasificacion_manual, :clasificacion_automatica, :estado
                )
            """, datos)
        
        conn.commit()
        logger.info(f"Datos de clasificación sincronizados para guía {codigo_guia}")
        return True
        
    except Exception as e:
        logger.error(f"Error sincronizando datos de clasificación: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def ensure_entry_records_schema():
    """
    Asegura que la tabla entry_records tenga todas las columnas necesarias.
    """
    try:
        conn = sqlite3.connect('tiquetes.db')
        cursor = conn.cursor()
        
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
        if not cursor.fetchone():
            logger.warning("La tabla entry_records no existe")
            return False
            
        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(entry_records)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Lista de columnas requeridas
        required_columns = [
            'codigo_guia',
            'codigo_proveedor',
            'nombre_proveedor',
            'cantidad_racimos',
            'placa',
            'transportador',
            'fecha_registro',
            'hora_registro'
        ]
        
        # Verificar y añadir columnas faltantes
        for column in required_columns:
            if column not in columns:
                try:
                    cursor.execute(f"ALTER TABLE entry_records ADD COLUMN {column} TEXT")
                    logger.info(f"Columna {column} añadida a entry_records")
                except sqlite3.OperationalError as e:
                    logger.error(f"Error añadiendo columna {column}: {str(e)}")
                    
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error en ensure_entry_records_schema: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def ensure_clasificaciones_schema():
    """
    Asegura que la tabla clasificaciones tenga todas las columnas necesarias.
    """
    try:
        conn = sqlite3.connect('tiquetes.db')
        cursor = conn.cursor()
        
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clasificaciones'")
        if not cursor.fetchone():
            logger.warning("La tabla clasificaciones no existe. Creando tabla...")
            cursor.execute('''
                CREATE TABLE clasificaciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_guia TEXT UNIQUE,
                    codigo_proveedor TEXT,
                    nombre_proveedor TEXT,
                    fecha_clasificacion TEXT,
                    hora_clasificacion TEXT,
                    clasificacion_manual TEXT,
                    clasificacion_automatica TEXT,
                    observaciones TEXT,
                    estado TEXT,
                    clasificaciones TEXT
                )
            ''')
            conn.commit()
            logger.info("Tabla clasificaciones creada correctamente")
            return True
            
        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(clasificaciones)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Lista de columnas requeridas
        required_columns = [
            'codigo_guia',
            'codigo_proveedor',
            'nombre_proveedor',
            'fecha_clasificacion',
            'hora_clasificacion',
            'clasificacion_manual',
            'clasificacion_automatica',
            'observaciones',
            'estado',
            'clasificaciones'
        ]
        
        # Verificar y añadir columnas faltantes
        for column in required_columns:
            if column not in columns:
                try:
                    cursor.execute(f"ALTER TABLE clasificaciones ADD COLUMN {column} TEXT")
                    logger.info(f"Columna {column} añadida a clasificaciones")
                except sqlite3.OperationalError as e:
                    logger.error(f"Error añadiendo columna {column}: {str(e)}")
                    
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error en ensure_clasificaciones_schema: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

@bp.route('/ver_detalle_proveedor/<codigo_guia>')
def ver_detalle_proveedor(codigo_guia):
    """
    Muestra los detalles del proveedor para una guía específica.
    """
    try:
        # Asegurar que la tabla clasificaciones tenga todas las columnas necesarias
        ensure_clasificaciones_schema()
        
        # Sincronizar datos de clasificación antes de mostrar el detalle
        sync_clasificacion_from_json(codigo_guia)
        
        # Asegurar que la tabla entry_records tenga todas las columnas necesarias
        ensure_entry_records_schema()
        
        # Obtener los datos de la guía
        utils = current_app.config.get('utils')
        datos_guia = utils.get_datos_guia(codigo_guia) if utils else None
        
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada", "error")
            return render_template('error.html', mensaje="No se encontraron datos para la guía especificada"), 404
        
        # Imprimir información en el log para depuración
        logger.info(f"Datos de guía para {codigo_guia}:")
        logger.info(f"Claves disponibles: {', '.join(datos_guia.keys())}")
        
        # Buscar específicamente claves relacionadas con SAP
        for key, value in datos_guia.items():
            if 'sap' in key.lower():
                logger.info(f"  - {key}: {value}")
        
        # Generar el código QR
        qr_filename = f'qr_guia_{codigo_guia}.png'
        qr_path = os.path.join(current_app.static_folder, 'qr', qr_filename)
        
        if not os.path.exists(qr_path):
            # URL para la vista centralizada de la guía
            qr_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_url, qr_path)
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        # Obtener timestamp actual para el pie de página
        now_timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
            
        # Añadir datos de clasificación manual y automática si existen
        if datos_guia.get('clasificacion_manual'):
            try:
                datos_guia['clasificacion_manual'] = json.loads(datos_guia['clasificacion_manual'])
                # Convertir a lista de tuplas para iterar en el template
                datos_guia['clasificacion_manual_items'] = list(datos_guia['clasificacion_manual'].items())
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Error decodificando clasificacion_manual para guía {codigo_guia}")
                datos_guia['clasificacion_manual_items'] = []
        
        if datos_guia.get('clasificacion_automatica'):
            try:
                # Decodificar el JSON a un diccionario Python
                datos_guia['clasificacion_automatica'] = json.loads(datos_guia['clasificacion_automatica'])
                # Preparar dos formatos para el template
                datos_guia['clasificacion_automatica_items'] = [(k, v.get('porcentaje', 0) if isinstance(v, dict) else v) 
                                                             for k, v in datos_guia['clasificacion_automatica'].items() 
                                                             if k != 'total_racimos']
                
                # Calcular el total de racimos a partir de los datos si no existe
                if 'total_racimos' not in datos_guia['clasificacion_automatica']:
                    total_racimos = sum(v.get('cantidad', 0) for v in datos_guia['clasificacion_automatica'].values() 
                                     if isinstance(v, dict))
                    datos_guia['clasificacion_automatica']['total_racimos'] = total_racimos
                
                logger.info(f"Datos de clasificación automática procesados correctamente: {datos_guia['clasificacion_automatica']}")
            except (json.JSONDecodeError, TypeError, AttributeError) as e:
                logger.error(f"Error decodificando clasificacion_automatica para guía {codigo_guia}: {str(e)}")
                datos_guia['clasificacion_automatica_items'] = []
        
        # Agregar el total de racimos detectados si está disponible en clasificacion_consolidada
        if 'total_racimos_detectados' not in datos_guia and datos_guia.get('clasificacion_automatica', {}).get('total_racimos'):
            datos_guia['total_racimos_detectados'] = datos_guia['clasificacion_automatica'].get('total_racimos', 0)
        
        # Obtener también clasificación consolidada si existe en la BD
        try:
            conn_detail = sqlite3.connect(DB_PATH) # Use DB_PATH
            cursor_detail = conn_detail.cursor() # Define cursor here
            cursor_detail.execute("""
                SELECT total_racimos_detectados, clasificacion_consolidada 
                FROM clasificaciones 
                WHERE codigo_guia = ?
            """, (codigo_guia,))
            consolidado = cursor_detail.fetchone()
            conn_detail.close() # Close connection
            if consolidado:
                datos_guia['total_racimos_detectados'] = consolidado[0]
                if consolidado[1]:
                    datos_guia['clasificacion_consolidada'] = json.loads(consolidado[1])
                    logger.info(f"Datos consolidados cargados para guía {codigo_guia}: {datos_guia['clasificacion_consolidada']}")
        except Exception as e:
            logger.error(f"Error obteniendo datos consolidados: {str(e)}")
            if 'conn_detail' in locals() and conn_detail:
                 conn_detail.close()
        
        # Para depuración
        logger.info(f"Datos de guía para {codigo_guia}:")
        logger.info(f"Claves disponibles: {', '.join(datos_guia.keys())}")
        for clave, valor in datos_guia.items():
            if clave not in ['clasificacion_manual', 'clasificacion_automatica', 'clasificacion_consolidada'] and valor:
                logger.info(f"  - {clave}: {valor}")
        
        return render_template('detalle_proveedor.html', 
                              datos_guia=datos_guia,
                              codigo_guia=codigo_guia,
                              qr_code=qr_code,
                              now_timestamp=now_timestamp)
        
    except Exception as e:
        logger.error(f"Error al mostrar detalle del proveedor: {str(e)}")
        flash(f"Error al cargar los detalles: {str(e)}", "error")
        return render_template('error.html', mensaje=f"Error al mostrar detalle: {str(e)}"), 500

@bp.route('/dashboard')
def dashboard():
    """
    Ruta para mostrar el dashboard con información general del sistema
    """
    try:
        # Esta ruta simplemente renderiza la plantilla, los datos reales
        # vendrían de rutas API separadas que serían consultadas vía AJAX
        return render_template('dashboard.html')
    except Exception as e:
        logger.error(f"Error al cargar el dashboard: {str(e)}")
        flash(f"Error al cargar el dashboard: {str(e)}", "danger")
        return redirect(url_for('entrada.home'))

@bp.route('/api/dashboard/stats')
def dashboard_stats():
    """
    API para obtener estadísticas básicas para el dashboard, aceptando filtros.
    Filtros soportados (query parameters):
    - startDate (YYYY-MM-DD)
    - endDate (YYYY-MM-DD)
    - proveedores (lista separada por comas de códigos de proveedor)
    - estado (valor del estado)
    """
    # Initialize ALL crucial response variables FIRST with defaults, BEFORE the main try block
    calidad_promedios = {
        'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0,
        'Pendunculo Largo': 0, 'Podrido': 0
    }
    calidad_promedios_auto = {
        'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0,
        'Pendunculo Largo': 0, 'Podrido': 0
    }
    registros_filtrados_count = 0
    total_racimos = 0
    peso_neto_total = 0
    peso_neto_pepa = 0
    pesajes_pendientes = 0
    clasificaciones_pendientes = 0
    peso_neto_hoy = 0
    registros_diarios_chart_data = {'labels': [], 'data': []}
    peso_neto_diario_chart_data = {'labels': [], 'data': []}
    racimos_peso_promedio_chart_data = {'labels': [], 'data_racimos': [], 'data_peso_promedio': []}
    ultimos_registros_tabla = []
    tiempos_promedio_proceso = {
        'entrada_a_bruto': 0.0, 'bruto_a_clasif': 0.0, 'clasif_a_neto': 0.0,
        'neto_a_salida': 0.0, 'total': 0.0
    }
    top_5_peso_neto_tabla = []
    alertas_calidad_tabla = []

    try:
        # Obtener parámetros de filtro de la solicitud
        start_date_str = request.args.get('startDate')
        end_date_str = request.args.get('endDate')
        proveedores_str = request.args.get('proveedores') # Códigos de proveedor
        estado_filter = request.args.get('estado')

        logger.info(f"Filtros recibidos - Start: {start_date_str}, End: {end_date_str}, Proveedores: {proveedores_str}, Estado: {estado_filter}")

        # Convertir fechas si existen
        start_date = None
        end_date = None
        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            if end_date_str:
                # Añadir un día para que la comparación sea inclusiva hasta el final del día
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d') + timedelta(days=1)
        except ValueError:
            logger.warning("Formato de fecha inválido recibido.")
            # Considerar devolver un error o usar valores por defecto
            start_date = None
            end_date = None

        # Convertir lista de proveedores (códigos)
        proveedores_list = []
        if proveedores_str:
            proveedores_list = [p.strip() for p in proveedores_str.split(',') if p.strip()]

        # Obtener todos los registros usando db_utils
        import db_utils
        all_records = db_utils.get_entry_records()
        logger.info(f"Total de registros obtenidos de DB: {len(all_records)}")

        # Filtrar registros en Python
        filtered_records = []
        for record in all_records:
            # 1. Filtrar por fecha
            try:
                # Intentar parsear la fecha del registro (asumiendo DD/MM/YYYY)
                record_date_str = record.get('fecha_registro', '01/01/1970')
                record_date = datetime.strptime(record_date_str, '%d/%m/%Y')

                if start_date and record_date < start_date:
                    continue # Saltar si es anterior a la fecha de inicio
                if end_date and record_date >= end_date:
                     # Saltar si es igual o posterior a la fecha de fin (ya que sumamos 1 día a end_date)
                    continue
            except ValueError:
                 logger.warning(f"Omitiendo registro {record.get('codigo_guia')} por fecha inválida: {record_date_str}")
                 continue # Saltar si la fecha del registro no es válida

            # 2. Filtrar por proveedor (código)
            if proveedores_list:
                codigo_proveedor = record.get('codigo_proveedor')
                if not codigo_proveedor or codigo_proveedor not in proveedores_list:
                    continue # Saltar si no coincide con los proveedores seleccionados

            # 3. Filtrar por estado
            # Asumiendo que el estado se guarda en la tabla 'entry_records' o se debe obtener de otra forma
            # Por ahora, este filtro no se aplica si no hay campo 'estado' en entry_records
            # if estado_filter and estado_filter != "":
            #     record_estado = record.get('estado') # Ajustar si el campo tiene otro nombre
            #     if not record_estado or record_estado != estado_filter:
            #         continue

            # Si pasa todos los filtros, añadir a la lista
            filtered_records.append(record)

        registros_filtrados_count = len(filtered_records)
        logger.info(f"Total de registros después de filtrar: {registros_filtrados_count}")

        # Calcular suma de racimos de los registros filtrados
        total_racimos = 0
        for record in filtered_records:
            try:
                # Intentar convertir a entero, manejar 'N/A' o no numéricos
                racimos_str = record.get('cantidad_racimos', '0')
                if isinstance(racimos_str, str) and racimos_str.isdigit():
                     total_racimos += int(racimos_str)
                elif isinstance(racimos_str, (int, float)): # Si ya es numérico
                     total_racimos += int(racimos_str)
                # Ignorar si no es un número válido
            except (ValueError, TypeError):
                logger.warning(f"Valor no numérico para cantidad_racimos en guía {record.get('codigo_guia')}: {record.get('cantidad_racimos')}")
                continue # Saltar este registro si no se puede convertir
        logger.info(f"Total de racimos calculados (filtrados): {total_racimos}")

        # Obtener códigos de guía de los registros filtrados
        codigos_guia_filtrados = [record.get('codigo_guia') for record in filtered_records if record.get('codigo_guia')]

        # --- Calcular Peso Neto Total (filtrado) --- 
        peso_neto_total = 0
        if codigos_guia_filtrados:
            try:
                conn_peso = sqlite3.connect('tiquetes.db')
                cursor_peso = conn_peso.cursor()
                
                # Crear placeholders para la consulta IN
                placeholders = ', '.join('?' * len(codigos_guia_filtrados))
                query = f"SELECT SUM(peso_neto) FROM pesajes_neto WHERE codigo_guia IN ({placeholders})"
                
                cursor_peso.execute(query, codigos_guia_filtrados)
                result = cursor_peso.fetchone()
                if result and result[0] is not None:
                    peso_neto_total = result[0]
                
                conn_peso.close()
                logger.info(f"Peso Neto Total calculado (filtrado): {peso_neto_total}")
            except sqlite3.Error as db_err:
                 logger.error(f"Error consultando peso_neto: {db_err}")
        else:
            logger.info("No hay guías filtradas para calcular el peso neto.")

        # --- Calcular Promedios de Calidad Manual (filtrado) --- 
        calidad_promedios = {
            'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0, 
            'Pendunculo Largo': 0, 'Podrido': 0 # Añadido Podrido que faltaba
        }
        count_clasificaciones_validas = 0
        sumas_calidad = {k: 0 for k in calidad_promedios.keys()}
        counts_calidad = {k: 0 for k in calidad_promedios.keys()}
        
        logger.info(f"Intentando calcular calidad para {len(codigos_guia_filtrados)} guías filtradas.") # Log guías
        if codigos_guia_filtrados:
            try:
                conn_clasif = sqlite3.connect('tiquetes.db')
                conn_clasif.row_factory = sqlite3.Row # Para acceder por nombre de columna
                cursor_clasif = conn_clasif.cursor()
                
                placeholders = ', '.join('?' * len(codigos_guia_filtrados))
                query = f"SELECT * FROM clasificaciones WHERE codigo_guia IN ({placeholders})"
                cursor_clasif.execute(query, codigos_guia_filtrados)
                clasificaciones_raw = cursor_clasif.fetchall()
                conn_clasif.close()
                
                # Log para ver la fila completa recuperada por Python
                if clasificaciones_raw:
                    logger.debug(f"Contenido completo de la primera fila recuperada: {dict(clasificaciones_raw[0])}")
                else:
                    logger.debug("No se recuperaron filas de clasificaciones.")
                
                logger.info(f"Se encontraron {len(clasificaciones_raw)} registros de clasificación para las guías filtradas.") # Log filas encontradas
                
                # Resetear sumas y conteos antes del bucle
                sumas_calidad = {k: 0 for k in calidad_promedios.keys()}
                counts_calidad = {k: 0 for k in calidad_promedios.keys()}
                count_clasificaciones_validas = 0 # Resetear contador

                for row_index, row in enumerate(clasificaciones_raw):
                    clasif_json_str = row['clasificacion_manual']
                    logger.debug(f"Procesando fila {row_index}, JSON crudo: {clasif_json_str}") # Log JSON crudo
                    if not clasif_json_str:
                        logger.debug(f"  -> JSON vacío, saltando fila.")
                        continue
                    try:
                        clasif_data = json.loads(clasif_json_str)
                        logger.debug(f"  -> JSON parseado: {clasif_data}") # Log JSON parseado
                        # Incrementar conteo general si la clasificación es válida y no vacía
                        if clasif_data: 
                             count_clasificaciones_validas += 1
                        else:
                             logger.debug("  -> JSON parseado vacío, no se cuenta como válida.")
                             continue
                        
                        processed_keys_in_row = set()
                        # Mapeo de la clave interna del código a la clave REAL en el JSON
                        key_mapping_manual = {
                            'Verde': 'verdes',
                            'Sobremaduro': 'sobremaduros',
                            'Daño Corona': 'danio_corona',
                            'Pendunculo Largo': 'pendunculo_largo',
                            'Podrido': 'podridos'
                        }
                        
                        for internal_key, json_key in key_mapping_manual.items():
                            valor_str = None
                            if json_key in clasif_data:
                                valor_str = clasif_data[json_key]
                                found_key = json_key # Guardamos la clave encontrada
                            else:
                                logger.debug(f"    -> Clave JSON esperada '{json_key}' no encontrada para clave interna '{internal_key}'.")
                                continue # Clave no encontrada en este JSON
                            
                            logger.debug(f"    -> Clave encontrada: '{found_key}' (para '{internal_key}'), Valor crudo: '{valor_str}'")
                            processed_keys_in_row.add(internal_key) # Marcar clave INTERNA como procesada
                            
                            try:
                                # Limpiar posible '%' y convertir a float
                                if isinstance(valor_str, str):
                                    valor_num = float(valor_str.replace('%', '').strip())
                                elif isinstance(valor_str, (int, float)):
                                     valor_num = float(valor_str)
                                else:
                                     raise ValueError("Tipo no numérico")
                                     
                                sumas_calidad[internal_key] += valor_num
                                counts_calidad[internal_key] += 1
                                logger.debug(f"      -> Suma[{internal_key}] = {sumas_calidad[internal_key]}, Count[{internal_key}] = {counts_calidad[internal_key]}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"    -> Valor no numérico/inválido para '{internal_key}' ('{found_key}'='{valor_str}'): {e}")
                                pass # Ignorar si no es un número válido
                        
                        # Log si no se procesó ninguna clave esperada en esta fila
                        if not processed_keys_in_row:
                             logger.warning(f"  -> No se procesó ninguna clave de calidad esperada para esta fila.")
                             
                    except json.JSONDecodeError:
                        logger.warning(f"  -> Error parseando JSON: {clasif_json_str}")
                        continue
                
                logger.info(f"Sumas finales: {sumas_calidad}") # Log sumas
                logger.info(f"Conteos finales: {counts_calidad}") # Log conteos
                logger.info(f"Clasificaciones válidas procesadas: {count_clasificaciones_validas}") # Log válidas

                # Calcular promedios Manuales
                for key in calidad_promedios.keys():
                    if counts_calidad[key] > 0:
                        calidad_promedios[key] = sumas_calidad[key] / counts_calidad[key]
                    else:
                        calidad_promedios[key] = 0 # O manejar como N/A
                logger.info(f"Promedios de Calidad Manual calculados: {calidad_promedios}")

                # --- Calcular Promedios de Calidad Automática (filtrado) --- 
                # Initialize OUTSIDE the if block
                calidad_promedios_auto = {
                    'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0,
                    'Pendunculo Largo': 0, 'Podrido': 0
                }
                sumas_calidad_auto = {k: 0 for k in calidad_promedios_auto.keys()} # Also init sums here
                counts_calidad_auto = {k: 0 for k in calidad_promedios_auto.keys()} # And counts
                count_clasificaciones_auto_validas = 0 # And valid count

                # Define mapping outside the loop for efficiency
                key_mapping_auto = {
                    'Verde': 'verde',
                    'Sobremaduro': 'sobremaduro',
                    'Daño Corona': 'danio_corona',
                    'Pendunculo Largo': 'pendunculo_largo',
                    'Podrido': 'podrido'
                }

                logger.info(f"Calculando calidad automática para {len(clasificaciones_raw)} filas crudas.")

                # Check if there are guides before proceeding with DB calls/processing
                if codigos_guia_filtrados: # Keep the check

                    # Remove the old initialization that was here

                    for row_index, row in enumerate(clasificaciones_raw):
                        # --- LEER DE LA NUEVA COLUMNA --- 
                        clasif_auto_json_str = None # Inicializar como None
                        if 'clasificacion_consolidada' in row.keys(): # Verificar si la columna existe
                            clasif_auto_json_str = row['clasificacion_consolidada'] # <--- CAMBIO DE COLUMNA
                        else:
                            logger.warning(f"Columna 'clasificacion_consolidada' no encontrada en la fila {row_index}. Verificando 'clasificacion_automatica' como fallback.")
                            # Fallback a la columna vieja si la nueva no existe (transición)
                            if 'clasificacion_automatica' in row.keys():
                                 clasif_auto_json_str = row['clasificacion_automatica']
                        
                        logger.debug(f"Procesando fila {row_index} para AUTO, JSON crudo leído: {clasif_auto_json_str}") # Log actualizado
                        
                        # --- CORREGIR EL SALTO INNECESARIO --- 
                        # Solo continuar si realmente no hay JSON para procesar
                        if not clasif_auto_json_str: 
                            logger.debug("  -> JSON automático/consolidado realmente vacío o None, saltando fila.") 
                            continue
                            
                        # Si llegamos aquí, tenemos un JSON (de consolidada o automática) para intentar procesar
                        try:
                            clasif_auto_data = json.loads(clasif_auto_json_str)
                            logger.debug(f"  -> JSON automático parseado: {clasif_auto_data}")
                            if clasif_auto_data:
                                count_clasificaciones_auto_validas += 1
                            else:
                                logger.debug("  -> JSON automático parseado vacío, no se cuenta.")
                                continue

                            processed_keys_auto_in_row = set()
                            for internal_key, json_key in key_mapping_auto.items():
                                valor_obj = None
                                if json_key in clasif_auto_data:
                                    valor_obj = clasif_auto_data[json_key]
                                    found_key = json_key
                                    logger.debug(f"    -> AUTO: Got valor_obj for key '{json_key}'. Type: {type(valor_obj)}, Value: {valor_obj}") # Log type and value
                                else:
                                    logger.debug(f"    -> AUTO: Clave JSON '{json_key}' no encontrada para '{internal_key}'.")
                                    continue
                                
                                # Extraer el porcentaje del objeto interno
                                valor_str = None
                                if isinstance(valor_obj, dict) and 'porcentaje' in valor_obj:
                                    valor_str = valor_obj['porcentaje']
                                else:
                                    reason = "Not a dict" if not isinstance(valor_obj, dict) else "Missing 'porcentaje' key"
                                    logger.warning(f"    -> AUTO: Failed to get percentage for '{json_key}'. Reason: {reason}. Object: {valor_obj}")
                                    continue # No podemos obtener el porcentaje

                                logger.debug(f"    -> AUTO: Clave '{found_key}' ('{internal_key}'), Porcentaje crudo: '{valor_str}'")
                                processed_keys_auto_in_row.add(internal_key)
                                
                                try:
                                    if isinstance(valor_str, str):
                                        valor_num = float(valor_str.replace('%', '').strip())
                                    elif isinstance(valor_str, (int, float)):
                                         valor_num = float(valor_str)
                                    else:
                                         raise ValueError("Tipo no numérico")
                                         
                                    sumas_calidad_auto[internal_key] += valor_num
                                    counts_calidad_auto[internal_key] += 1
                                    logger.debug(f"      -> AUTO: Suma[{internal_key}]={sumas_calidad_auto[internal_key]}, Count[{internal_key}]={counts_calidad_auto[internal_key]}")
                                except (ValueError, TypeError) as e:
                                    logger.warning(f"    -> AUTO: Valor no numérico para '{internal_key}' ('{found_key}'='{valor_str}'): {e}")
                                    pass
                                    
                            if not processed_keys_auto_in_row:
                                 logger.warning(f"  -> AUTO: No se procesó ninguna clave esperada.")
                                 
                        except json.JSONDecodeError:
                            logger.warning(f"  -> AUTO: Error parseando JSON: {clasif_auto_json_str}")
                            continue

                    logger.info(f"Sumas finales AUTO: {sumas_calidad_auto}")
                    logger.info(f"Conteos finales AUTO: {counts_calidad_auto}")
                    logger.info(f"Clasificaciones AUTO válidas: {count_clasificaciones_auto_validas}")

                    # Calcular promedios Automáticos
                    # This calculation is now safe even if the loop didn't run
                    for key in calidad_promedios_auto.keys():
                        if counts_calidad_auto[key] > 0: # Check if count for this key is > 0
                            calidad_promedios_auto[key] = sumas_calidad_auto[key] / counts_calidad_auto[key]
                        # No else needed, initialized to 0
                    logger.info(f"Promedios de Calidad Automática calculados: {calidad_promedios_auto}")
                    # -- Fin cálculo calidad automática --

            except sqlite3.Error as db_err:
                 logger.error(f"Error consultando clasificaciones: {db_err}")
        else:
             logger.info("No hay guías filtradas para calcular calidad.")

        # --- Calcular otros KPIs ... ---
        # Por ahora, solo devolvemos el conteo de registros de entrada filtrado
        # Los otros valores se mantienen como estaban (sin filtrar)
        # TODO: Aplicar filtros a los cálculos de pesajes pendientes, clasificaciones, peso neto, etc.
        conn = sqlite3.connect('tiquetes.db') # Conexión temporal para otros KPIs no filtrados
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Pesajes pendientes (sin filtrar por ahora)
        cursor.execute("SELECT COUNT(*) as count FROM entry_records e LEFT JOIN pesajes_neto p ON e.codigo_guia = p.codigo_guia WHERE p.codigo_guia IS NULL")
        pesajes_pendientes = cursor.fetchone()['count']
        # Clasificaciones pendientes (sin filtrar por ahora)
        cursor.execute("SELECT COUNT(*) as count FROM entry_records e LEFT JOIN clasificaciones c ON e.codigo_guia = c.codigo_guia WHERE c.codigo_guia IS NULL")
        clasificaciones_pendientes = cursor.fetchone()['count']
        # Peso neto hoy (sin filtrar por ahora)
        today = datetime.now().strftime('%d/%m/%Y') # Ajustado a formato DD/MM/YYYY
        cursor.execute("SELECT SUM(peso_neto) as total FROM pesajes_neto WHERE fecha_pesaje = ?", (today,))
        result = cursor.fetchone()
        peso_neto_hoy = result['total'] if result and result['total'] is not None else 0
        conn.close()
        # --- Fin cálculos KPIs temporales --- 

        # --- Calcular Peso Neto Pepa --- 
        peso_neto_pepa = 0
        codigos_guia_pepa = []
        for record in filtered_records:
            cantidad_racimos_str = str(record.get('cantidad_racimos', '')).strip().lower()
            if cantidad_racimos_str == 'pepa':
                codigo_guia = record.get('codigo_guia')
                if codigo_guia:
                    codigos_guia_pepa.append(codigo_guia)
        
        logger.info(f"Encontradas {len(codigos_guia_pepa)} guías marcadas como 'Pepa'.")

        if codigos_guia_pepa:
            try:
                conn_pepa = sqlite3.connect('tiquetes.db')
                cursor_pepa = conn_pepa.cursor()
                placeholders_pepa = ', '.join('?' * len(codigos_guia_pepa))
                query_pepa = f"SELECT SUM(peso_neto) FROM pesajes_neto WHERE codigo_guia IN ({placeholders_pepa})"
                cursor_pepa.execute(query_pepa, codigos_guia_pepa)
                result_pepa = cursor_pepa.fetchone()
                if result_pepa and result_pepa[0] is not None:
                    peso_neto_pepa = result_pepa[0]
                conn_pepa.close()
                logger.info(f"Peso Neto Pepa calculado: {peso_neto_pepa}")
            except sqlite3.Error as db_err:
                logger.error(f"Error consultando peso_neto para Pepa: {db_err}")
        # --- Fin Calcular Peso Neto Pepa ---

        # --- Calcular Registros Diarios para Gráfico ---
        registros_diarios_chart_data = {'labels': [], 'data': []}
        if filtered_records:
            # Agrupar registros por fecha
            registros_por_fecha = {}
            for record in filtered_records:
                fecha_str = record.get('fecha_registro')
                if fecha_str:
                    try:
                        # Validar formato DD/MM/YYYY
                        fecha_dt = datetime.strptime(fecha_str, '%d/%m/%Y')
                        fecha_key = fecha_dt.strftime('%Y-%m-%d') # Usar YYYY-MM-DD como clave
                        registros_por_fecha[fecha_key] = registros_por_fecha.get(fecha_key, 0) + 1
                    except ValueError:
                        logger.warning(f"Formato de fecha inválido en registro diario: {fecha_str}")
                        continue

            # Determinar el rango de fechas (últimos 7 días desde endDate o hoy)
            if end_date: # end_date ya tiene sumado 1 día, restamos para obtener el último día real
                fecha_fin_rango = end_date - timedelta(days=1)
            else:
                fecha_fin_rango = datetime.now()
            
            fechas_labels = []
            conteos_data = []
            for i in range(6, -1, -1): # Iterar 7 días hacia atrás
                fecha_actual = fecha_fin_rango - timedelta(days=i)
                fecha_key = fecha_actual.strftime('%Y-%m-%d')
                fechas_labels.append(fecha_actual.strftime('%d/%m')) # Label corto DD/MM
                conteos_data.append(registros_por_fecha.get(fecha_key, 0)) # Conteo para esa fecha, 0 si no hay
            
            registros_diarios_chart_data['labels'] = fechas_labels
            registros_diarios_chart_data['data'] = conteos_data
            logger.info(f"Datos para gráfico Registros Diarios: {registros_diarios_chart_data}")
        else:
             logger.info("No hay registros filtrados para generar gráfico de registros diarios.")
        # --- Fin Calcular Registros Diarios ---

        # --- Calcular Peso Neto Diario para Gráfico ---
        peso_neto_diario_chart_data = {'labels': [], 'data': []}
        if codigos_guia_filtrados: # Solo si hay guías filtradas
            try:
                conn_peso_diario = sqlite3.connect('tiquetes.db')
                conn_peso_diario.row_factory = sqlite3.Row
                cursor_peso_diario = conn_peso_diario.cursor()
                
                placeholders_peso = ', '.join('?' * len(codigos_guia_filtrados))
                query_peso_diario = f"""
                    SELECT fecha_pesaje, SUM(peso_neto) as suma_peso 
            FROM pesajes_neto 
                    WHERE codigo_guia IN ({placeholders_peso}) 
            GROUP BY fecha_pesaje
                """
                cursor_peso_diario.execute(query_peso_diario, codigos_guia_filtrados)
                pesos_por_fecha_raw = cursor_peso_diario.fetchall()
                conn_peso_diario.close()
                logger.info(f"Se encontraron {len(pesos_por_fecha_raw)} días con peso neto para guías filtradas.")

                # Procesar y agrupar por fecha YYYY-MM-DD
                pesos_por_fecha_dict = {}
                for row in pesos_por_fecha_raw:
                    fecha_str = row['fecha_pesaje']
                    suma_peso = row['suma_peso'] if row['suma_peso'] else 0
                    if fecha_str:
                        try:
                            # Asumir formato DD/MM/YYYY
                            fecha_dt = datetime.strptime(fecha_str, '%d/%m/%Y')
                            fecha_key = fecha_dt.strftime('%Y-%m-%d')
                            pesos_por_fecha_dict[fecha_key] = pesos_por_fecha_dict.get(fecha_key, 0) + suma_peso
                        except ValueError:
                            logger.warning(f"Formato de fecha inválido en pesaje neto: {fecha_str}")
                            continue
                
                # Usar el mismo rango de fechas que registros diarios
                # fecha_fin_rango ya está definida arriba
                fechas_labels_peso = []
                pesos_data = []
                for i in range(6, -1, -1): # Iterar 7 días hacia atrás
                    fecha_actual = fecha_fin_rango - timedelta(days=i)
                    fecha_key = fecha_actual.strftime('%Y-%m-%d')
                    fechas_labels_peso.append(fecha_actual.strftime('%d/%m')) # Label corto DD/MM
                    # Convertir kg a toneladas con 1 decimal
                    peso_kg = pesos_por_fecha_dict.get(fecha_key, 0)
                    peso_toneladas = round(peso_kg / 1000, 1)
                    pesos_data.append(peso_toneladas)
                
                peso_neto_diario_chart_data['labels'] = fechas_labels_peso
                peso_neto_diario_chart_data['data'] = pesos_data
                logger.info(f"Datos para gráfico Peso Neto Diario (toneladas): {peso_neto_diario_chart_data}")

            except sqlite3.Error as db_err:
                 logger.error(f"Error consultando peso_neto diario: {db_err}")
        else:
            logger.info("No hay guías filtradas para generar gráfico de peso neto diario.")
        # --- Fin Calcular Peso Neto Diario ---

        # --- Calcular Racimos y Peso Promedio Diario para Gráfico ---
        racimos_peso_promedio_chart_data = {'labels': [], 'data_racimos': [], 'data_peso_promedio': []}
        if filtered_records: # Usamos los registros de entrada ya filtrados
            racimos_por_fecha = {}
            peso_kg_por_fecha = pesos_por_fecha_dict # Usamos el dict ya calculado arriba con peso en KG
            
            # 1. Agrupar racimos por fecha desde entry_records
            for record in filtered_records:
                fecha_str = record.get('fecha_registro')
                racimos_str = record.get('cantidad_racimos', '0')
                if fecha_str:
                    try:
                        fecha_dt = datetime.strptime(fecha_str, '%d/%m/%Y')
                        fecha_key = fecha_dt.strftime('%Y-%m-%d')
                        
                        # Intentar convertir racimos a entero
                        try:
                            racimos_count = int(racimos_str) if racimos_str and racimos_str != 'No disponible' else 0
                        except (ValueError, TypeError):
                            racimos_count = 0
                            logger.warning(f"Valor de racimos no numérico encontrado: '{racimos_str}' para fecha {fecha_key}")
                            
                        racimos_por_fecha[fecha_key] = racimos_por_fecha.get(fecha_key, 0) + racimos_count
                    except ValueError:
                         # Fecha inválida ya advertida en gráfico de registros diarios
                        continue
            
            # 2. Iterar por el rango de fechas y calcular datos
            # fecha_fin_rango y fechas_labels_peso ya están definidas
            data_racimos = []
            data_peso_promedio = []
            
            for i in range(6, -1, -1): # Mismo rango de 7 días
                fecha_actual = fecha_fin_rango - timedelta(days=i)
                fecha_key = fecha_actual.strftime('%Y-%m-%d')
                
                # Obtener total racimos y peso para el día
                total_racimos_dia = racimos_por_fecha.get(fecha_key, 0)
                total_peso_kg_dia = peso_kg_por_fecha.get(fecha_key, 0)
                
                # Calcular peso promedio por racimo (kg/racimo)
                peso_promedio_dia = 0
                if total_racimos_dia > 0:
                    peso_promedio_dia = round(total_peso_kg_dia / total_racimos_dia, 1)
                    
                data_racimos.append(total_racimos_dia)
                data_peso_promedio.append(peso_promedio_dia)
                
            racimos_peso_promedio_chart_data['labels'] = fechas_labels_peso # Usar las mismas labels
            racimos_peso_promedio_chart_data['data_racimos'] = data_racimos
            racimos_peso_promedio_chart_data['data_peso_promedio'] = data_peso_promedio
            logger.info(f"Datos para gráfico Racimos/Peso Promedio: {racimos_peso_promedio_chart_data}")
        else:
             logger.info("No hay registros filtrados para generar gráfico de racimos/peso promedio.")
        # --- Fin Calcular Racimos y Peso Promedio Diario ---

        # --- Preparar datos para Tabla Últimos Registros ---
        ultimos_registros_tabla = []
        codigos_guias_ultimos_5 = [rec.get('codigo_guia') for rec in filtered_records[:5] if rec.get('codigo_guia')]
        
        # Consultar estados de salida para los últimos 5 de una vez
        estados_salida = {}
        if codigos_guias_ultimos_5:
            try:
                conn_salida = sqlite3.connect('tiquetes.db')
                cursor_salida = conn_salida.cursor()
                placeholders_salida = ', '.join('?' * len(codigos_guias_ultimos_5))
                cursor_salida.execute(f"SELECT codigo_guia FROM salidas WHERE codigo_guia IN ({placeholders_salida})", codigos_guias_ultimos_5)
                guias_con_salida = {row[0] for row in cursor_salida.fetchall()}
                estados_salida = {codigo: 'Completado' for codigo in guias_con_salida}
                conn_salida.close()
            except sqlite3.Error as db_err:
                logger.error(f"Error consultando tabla salidas: {db_err}")

        if filtered_records:
            # Iterar sobre los primeros 5 registros (ya están ordenados desc)
            for record in filtered_records[:5]:
                codigo_guia_actual = record.get('codigo_guia', 'N/A')
                cantidad_racimos_str = str(record.get('cantidad_racimos', '')).strip()

                # Determinar Tipo Fruta
                tipo_fruta_display = "N/A"
                if cantidad_racimos_str.isdigit():
                    tipo_fruta_display = "Fruta"
                elif 'pepa' in cantidad_racimos_str.lower():
                    tipo_fruta_display = "Pepa"
                
                # Determinar Estado basado en consulta previa
                estado_display = estados_salida.get(codigo_guia_actual, "En proceso")
                badge_class = "bg-success" if estado_display == "Completado" else "bg-warning"
                
                ultimos_registros_tabla.append({
                    'codigo_guia': codigo_guia_actual,
                    'proveedor': record.get('nombre_proveedor', 'N/A'),
                    'fecha_hora': f"{record.get('fecha_registro', '')} {record.get('hora_registro', '')}",
                    'tipo_fruta': tipo_fruta_display, # Usar el tipo determinado
                    'estado': estado_display, # Usar el estado determinado
                    'badge_class': badge_class # Usar la clase determinada
                })
        # --- Fin Preparar Tabla Últimos Registros ---

        # --- Calcular Tiempos Promedio de Procesos --- 
        tiempos_promedio_proceso = {
            'entrada_a_bruto': 0.0, # Horas
            'bruto_a_clasif': 0.0,
            'clasif_a_neto': 0.0,
            'neto_a_salida': 0.0,
            'total': 0.0
        }
        duraciones = {
            'entrada_a_bruto': [], 
            'bruto_a_clasif': [],
            'clasif_a_neto': [],
            'neto_a_salida': [],
            'total': []
        }
        
        if codigos_guia_filtrados:
            try:
                conn_tiempos = sqlite3.connect('tiquetes.db')
                conn_tiempos.row_factory = sqlite3.Row
                cursor_tiempos = conn_tiempos.cursor()
                
                placeholders_tiempos = ', '.join('?' * len(codigos_guia_filtrados))
                query_tiempos = f"""
                    SELECT 
                        e.codigo_guia, 
                        e.fecha_registro, e.hora_registro, 
                        pb.fecha_pesaje AS fecha_pesaje_bruto, pb.hora_pesaje AS hora_pesaje_bruto, 
                        c.fecha_clasificacion, c.hora_clasificacion, 
                        pn.fecha_pesaje AS fecha_pesaje_neto, pn.hora_pesaje AS hora_pesaje_neto, 
                        s.fecha_salida, s.hora_salida
                    FROM 
                        entry_records e
                    LEFT JOIN pesajes_bruto pb ON e.codigo_guia = pb.codigo_guia
                    LEFT JOIN clasificaciones c ON e.codigo_guia = c.codigo_guia
                    LEFT JOIN pesajes_neto pn ON e.codigo_guia = pn.codigo_guia
                    LEFT JOIN salidas s ON e.codigo_guia = s.codigo_guia
                    WHERE e.codigo_guia IN ({placeholders_tiempos})
                """
                cursor_tiempos.execute(query_tiempos, codigos_guia_filtrados)
                registros_tiempo = cursor_tiempos.fetchall()
                conn_tiempos.close()
                logger.info(f"Se recuperaron {len(registros_tiempo)} registros de tiempo para guías filtradas.")

                for row in registros_tiempo:
                    t_entrada = parse_datetime_str(row['fecha_registro'], row['hora_registro'])
                    t_bruto = parse_datetime_str(row['fecha_pesaje_bruto'], row['hora_pesaje_bruto'])
                    # Usar fecha/hora de actualización de consolidado si existe, si no, la de clasificación
                    t_clasif = parse_datetime_str(row['fecha_actualizacion'], row['hora_actualizacion']) if 'fecha_actualizacion' in row.keys() and row['fecha_actualizacion'] else parse_datetime_str(row['fecha_clasificacion'], row['hora_clasificacion'])
                    t_neto = parse_datetime_str(row['fecha_pesaje_neto'], row['hora_pesaje_neto'])
                    t_salida = parse_datetime_str(row['fecha_salida'], row['hora_salida'])

                    # Calcular duraciones solo si los timestamps necesarios existen
                    if t_entrada and t_bruto:
                        duracion = (t_bruto - t_entrada).total_seconds()
                        if duracion >= 0: duraciones['entrada_a_bruto'].append(duracion)
                    if t_bruto and t_clasif:
                        duracion = (t_clasif - t_bruto).total_seconds()
                        if duracion >= 0: duraciones['bruto_a_clasif'].append(duracion)
                    if t_clasif and t_neto:
                        duracion = (t_neto - t_clasif).total_seconds()
                        if duracion >= 0: duraciones['clasif_a_neto'].append(duracion)
                    if t_neto and t_salida:
                        duracion = (t_salida - t_neto).total_seconds()
                        if duracion >= 0: duraciones['neto_a_salida'].append(duracion)
                    if t_entrada and t_salida:
                        duracion = (t_salida - t_entrada).total_seconds()
                        if duracion >= 0: duraciones['total'].append(duracion)
                
                # Calcular promedios en horas
                for key, lista_duraciones in duraciones.items():
                    if lista_duraciones:
                        promedio_segundos = sum(lista_duraciones) / len(lista_duraciones)
                        tiempos_promedio_proceso[key] = promedio_segundos / 60# Convertir a horas
                
                logger.info(f"Tiempos promedio calculados (horas): {tiempos_promedio_proceso}")

            except sqlite3.Error as db_err:
                logger.error(f"Error consultando datos para tiempos promedio: {db_err}")
            except Exception as e:
                 logger.error(f"Error calculando tiempos promedio: {e}")
                 logger.error(traceback.format_exc())
        else:
            logger.info("No hay guías filtradas para calcular tiempos promedio.")
        
        # Añadir al diccionario de respuesta
        response = {
            # KPI principal filtrado
            'registros_entrada_filtrados': registros_filtrados_count,
            # Nuevo KPI calculado
            'total_racimos_filtrados': total_racimos,
            # Nuevo KPI Peso Neto Total
            'peso_neto_total_filtrado': peso_neto_total,
            # Nuevo KPI Peso Neto Pepa (en kg inicialmente)
            'peso_neto_pepa': peso_neto_pepa, 
            # Nuevos KPIs de Calidad
            'calidad_promedios_manual': calidad_promedios, # Promedios manuales
            'calidad_promedios_automatica': calidad_promedios_auto, # Promedios automáticos
            # Otros KPIs (aún no filtrados - placeholder)
            'pesajes_pendientes': pesajes_pendientes,
            'clasificaciones_pendientes': clasificaciones_pendientes,
            'peso_neto_hoy': peso_neto_hoy,
            # Datos para gráficos (aún no filtrados - placeholder)
            'registros_diarios': {},
            'peso_neto_diario': {},
            'registros_diarios_chart_data': registros_diarios_chart_data,
            'peso_neto_diario_chart_data': peso_neto_diario_chart_data,
            'racimos_peso_promedio_chart_data': racimos_peso_promedio_chart_data,
            'ultimos_registros_tabla': ultimos_registros_tabla
        }
        
        # --- Preparar Tabla Top 5 Guías por Peso Neto ---
        top_5_peso_neto_tabla = []
        try:
            conn_top5 = sqlite3.connect('tiquetes.db')
            conn_top5.row_factory = sqlite3.Row
            cursor_top5 = conn_top5.cursor()

            # 1. Obtener los códigos de guía de los registros filtrados
            filtered_guia_codes = [rec.get('codigo_guia') for rec in filtered_records if rec.get('codigo_guia')]
            
            # 2. Consultar pesajes_neto para esos códigos y ordenar por peso_neto
            top_pesajes = []
            if filtered_guia_codes:
                placeholders_top5 = ', '.join('?' * len(filtered_guia_codes))
                # Asegurarse que peso_neto es numérico antes de ordenar
                query_top5 = f"""
                    SELECT codigo_guia, peso_neto 
                    FROM pesajes_neto 
                    WHERE codigo_guia IN ({placeholders_top5}) AND typeof(peso_neto) IN ('integer', 'real')
                    ORDER BY peso_neto DESC 
                    LIMIT 5
                """
                cursor_top5.execute(query_top5, filtered_guia_codes)
                top_pesajes = cursor_top5.fetchall()
            
            # 3. Obtener información adicional para las guías del top 5
            top_guia_codes = [row['codigo_guia'] for row in top_pesajes]
            if top_guia_codes:
                # Crear diccionarios para buscar info rápidamente
                pesos_netos = {row['codigo_guia']: row['peso_neto'] for row in top_pesajes}
                info_entry = {}
                info_clasif = {}

                placeholders_info = ', '.join('?' * len(top_guia_codes))
                
                # Info de entry_records
                cursor_top5.execute(f"SELECT codigo_guia, nombre_proveedor, cantidad_racimos FROM entry_records WHERE codigo_guia IN ({placeholders_info})", top_guia_codes)
                for row in cursor_top5.fetchall():
                    info_entry[row['codigo_guia']] = {'nombre': row['nombre_proveedor'], 'racimos': row['cantidad_racimos']}
                
                # Info de clasificaciones (manual para calidad simple)
                cursor_top5.execute(f"SELECT codigo_guia, clasificacion_manual FROM clasificaciones WHERE codigo_guia IN ({placeholders_info})", top_guia_codes)
                for row in cursor_top5.fetchall():
                    try:
                        # Usar el campo clasificacion_manual que ahora es JSON
                        manual_data = json.loads(row['clasificacion_manual'] or '{}') 
                        # Calcular calidad simple (ej: % no defectuoso)
                        # Definir defectos (ajustar claves según el JSON real)
                        defectos = ['verde', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido']
                        total_defectos_pct = sum(float(manual_data.get(d, 0) or 0) for d in defectos)
                        calidad_pct = max(0, 100 - total_defectos_pct)
                        info_clasif[row['codigo_guia']] = calidad_pct
                    except (json.JSONDecodeError, ValueError, TypeError):
                         info_clasif[row['codigo_guia']] = 0 # Calidad 0 si hay error

                # 4. Construir la tabla final
                rank = 1
                for codigo_guia in top_guia_codes:
                    entry_data = info_entry.get(codigo_guia, {})
                    peso_neto_kg = pesos_netos.get(codigo_guia, 0)
                    calidad = info_clasif.get(codigo_guia, 0) # 0 si no hay clasificación
                    
                    # Determinar tipo fruta
                    cantidad_racimos_str = str(entry_data.get('racimos', '')).strip()
                    tipo_fruta_display = "N/A"
                    if cantidad_racimos_str.isdigit():
                        tipo_fruta_display = "Fruta"
                    elif 'pepa' in cantidad_racimos_str.lower():
                        tipo_fruta_display = "Pepa"
                    
                    top_5_peso_neto_tabla.append({
                        'rank': rank,
                        'codigo_guia': codigo_guia,
                        'proveedor': entry_data.get('nombre', 'N/A'),
                        'tipo_fruta': tipo_fruta_display,
                        'peso_neto': f"{(peso_neto_kg / 1000):.1f} t" if peso_neto_kg else "0.0 t",
                        'calidad': round(calidad) # Porcentaje de calidad redondeado
                    })
                    rank += 1

            conn_top5.close()
            logger.info(f"Preparada tabla Top 5 Peso Neto con {len(top_5_peso_neto_tabla)} registros.")
        except sqlite3.Error as db_err:
            logger.error(f"Error preparando tabla Top 5 Peso Neto: {db_err}")
            if 'conn_top5' in locals() and conn_top5:
                conn_top5.close()
        except Exception as e:
            logger.error(f"Error inesperado preparando Top 5 Peso Neto: {e}")

        response['top_5_peso_neto_tabla'] = top_5_peso_neto_tabla
        # --- Fin Preparar Tabla Top 5 Guías por Peso Neto ---

        # --- Calcular Promedios de Calidad POR PROVEEDOR ---
        calidad_por_proveedor_manual = {}
        calidad_por_proveedor_auto = {}
        # Asumiendo que 'clasificacion_consolidada' está disponible y actualizada
        # Necesitamos obtener las clasificaciones para los registros filtrados
        codigos_guias_filtradas = [rec['codigo_guia'] for rec in filtered_records if rec.get('codigo_guia')]
        
        if codigos_guias_filtradas:
            try:
                conn_clasif_prov = sqlite3.connect(DB_PATH) # Use DB_PATH
                conn_clasif_prov.row_factory = sqlite3.Row
                cursor_clasif_prov = conn_clasif_prov.cursor()
                
                placeholders_clasif = ', '.join('?' * len(codigos_guias_filtradas))
                # Obtener clasificacion_manual y codigo_proveedor
                query_clasif = f"""
                    SELECT c.codigo_guia, c.codigo_proveedor, c.clasificacion_manual, c.clasificacion_automatica 
                    FROM clasificaciones c 
                    WHERE c.codigo_guia IN ({placeholders_clasif})
                """
                cursor_clasif_prov.execute(query_clasif, codigos_guias_filtradas)
                clasificaciones_filtradas = cursor_clasif_prov.fetchall()
                conn_clasif_prov.close()

                # Agrupar datos por proveedor
                datos_agrupados_manual = {}
                datos_agrupados_auto = {}
                # Define key_mapping_manual here or ensure it's defined/imported above
                key_mapping_manual = {
                    'Verde': 'verdes',
                    'Sobremaduro': 'sobremaduros',
                    'Daño Corona': 'danio_corona',
                    'Pendunculo Largo': 'pendunculo_largo',
                    'Podrido': 'podridos'
                }
                categorias_calidad = list(key_mapping_manual.values()) # Use values from the defined map
                
                for row in clasificaciones_filtradas:
                    proveedor = row['codigo_proveedor'] # Usar código como clave
                    if not proveedor:
                        continue # Omitir si no hay código de proveedor
                        
                    # Inicializar si es la primera vez que vemos al proveedor
                    if proveedor not in datos_agrupados_manual:
                        datos_agrupados_manual[proveedor] = {cat: {'sum': 0, 'count': 0} for cat in categorias_calidad}
                        datos_agrupados_auto[proveedor] = {cat: {'sum': 0, 'count': 0} for cat in categorias_calidad}
                    
                    # Procesar manual
                    try:
                        manual_data = json.loads(row['clasificacion_manual'] or '{}')
                        for key_original, key_mapped in key_mapping_manual.items():
                            valor = manual_data.get(key_original)
                            if valor is not None:
                                try:
                                    valor_float = float(valor)
                                    datos_agrupados_manual[proveedor][key_mapped]['sum'] += valor_float
                                    datos_agrupados_manual[proveedor][key_mapped]['count'] += 1
                                except (ValueError, TypeError):
                                    pass # Ignorar valores no numéricos
                    except json.JSONDecodeError:
                        pass # Ignorar JSON inválido
                        
                    # Procesar automático (similar a manual, usando key_mapping_auto)
                    try:
                        auto_data = json.loads(row['clasificacion_automatica'] or '{}')
                        for key_original, key_mapped in key_mapping_auto.items(): # Reusar el mapeo si es igual o definir uno específico
                            valor = auto_data.get(key_original)
                            if valor is not None:
                                try:
                                    valor_float = float(valor)
                                    datos_agrupados_auto[proveedor][key_mapped]['sum'] += valor_float
                                    datos_agrupados_auto[proveedor][key_mapped]['count'] += 1
                                except (ValueError, TypeError):
                                    pass
                    except json.JSONDecodeError:
                         pass
                         
                # Calcular promedios finales por proveedor
                for proveedor, data in datos_agrupados_manual.items():
                    calidad_por_proveedor_manual[proveedor] = {}
                    for cat, values in data.items():
                        calidad_por_proveedor_manual[proveedor][cat] = (values['sum'] / values['count']) if values['count'] > 0 else 0
                        
                for proveedor, data in datos_agrupados_auto.items():
                     calidad_por_proveedor_auto[proveedor] = {}
                     for cat, values in data.items():
                         calidad_por_proveedor_auto[proveedor][cat] = (values['sum'] / values['count']) if values['count'] > 0 else 0

            except sqlite3.Error as db_err:
                logger.error(f"Error obteniendo clasificaciones por proveedor: {db_err}")
            except Exception as e:
                logger.error(f"Error procesando calidad por proveedor: {e}")
        # --- Fin Calcular Promedios POR PROVEEDOR ---

        # --- Generar Alertas de Calidad ---
        alertas_calidad_tabla = []
        # Mapeo de clave interna a nombre legible para alerta
        nombres_defectos = {
            'verdes': 'Verde', # Match keys used in categorias_calidad
            'sobremaduros': 'Sobremaduro',
            'danio_corona': 'Daño Corona',
            'pendunculo_largo': 'Pedúnculo Largo',
            'podridos': 'Podrido'
        }
        # Usar calidad_por_proveedor_manual para las alertas
        for proveedor_codigo, promedios in calidad_por_proveedor_manual.items():
            # Intentar obtener nombre del proveedor de filtered_records
            nombre_prov = proveedor_codigo # Por defecto usar código
            for rec in filtered_records:
                if rec.get('codigo_proveedor') == proveedor_codigo:
                    nombre_prov = rec.get('nombre_proveedor', proveedor_codigo)
                    break # Encontramos el primero, salir
                    
            for defecto_key, valor_pct in promedios.items():
                severidad_texto = ""
                severidad_badge = ""
                
                if valor_pct > 4:
                    severidad_texto = "Alta"
                    severidad_badge = "bg-danger"
                elif valor_pct > 2:
                    severidad_texto = "Media"
                    severidad_badge = "bg-warning"
                    
                if severidad_texto: # Solo añadir si es Media o Alta
                    nombre_problema = nombres_defectos.get(defecto_key, defecto_key.capitalize())
                    alertas_calidad_tabla.append({
                        'proveedor': f"{nombre_prov} ({proveedor_codigo})",
                        'problema': f"Alto % {nombre_problema}",
                        'valor_problema': f"{valor_pct:.1f}%",
                        'severidad_texto': severidad_texto,
                        'severidad_badge': severidad_badge
                    })
                    
        # Ordenar alertas por proveedor y luego por severidad (Alta primero)
        alertas_calidad_tabla.sort(key=lambda x: (x['proveedor'], 0 if x['severidad_texto'] == 'Alta' else 1))
        response['alertas_calidad_tabla'] = alertas_calidad_tabla
        # --- Fin Generar Alertas de Calidad ---

        # DEBUG: Log the variable right before use
        logger.info(f"DEBUG: Value of calidad_promedios_auto before response: {calidad_promedios_auto}")
        logger.info(f"DEBUG: Type of calidad_promedios_auto before response: {type(calidad_promedios_auto)}")

        # Devolver todos los datos calculados
        response = {
            # KPI principal filtrado
            'registros_entrada_filtrados': registros_filtrados_count,
            # Nuevo KPI calculado
            'total_racimos_filtrados': total_racimos,
            # Nuevo KPI Peso Neto Total
            'peso_neto_total_filtrado': peso_neto_total,
            # Nuevo KPI Peso Neto Pepa (en kg inicialmente)
            'peso_neto_pepa': peso_neto_pepa,
            # Nuevos KPIs de Calidad
            'calidad_promedios_manual': calidad_promedios, # Promedios manuales
            'calidad_promedios_automatica': calidad_promedios_auto, # Promedios automáticos
            # Otros KPIs (aún no filtrados - placeholder)
            'pesajes_pendientes': pesajes_pendientes,
            'clasificaciones_pendientes': clasificaciones_pendientes,
            'peso_neto_hoy': peso_neto_hoy,
            # Datos para gráficos (ya filtrados)
            'registros_diarios_chart_data': registros_diarios_chart_data,
            'peso_neto_diario_chart_data': peso_neto_diario_chart_data,
            'racimos_peso_promedio_chart_data': racimos_peso_promedio_chart_data,
            'ultimos_registros_tabla': ultimos_registros_tabla,
            'tiempos_promedio_proceso': tiempos_promedio_proceso,
            'top_5_peso_neto_tabla': top_5_peso_neto_tabla,
            'alertas_calidad_tabla': alertas_calidad_tabla
            # Note: calidad_por_proveedor results aren't directly returned, used for alerts
        }

        # --- Fin Generar Alertas de Calidad ---

        return jsonify(response)
    except Exception as e:
        logger.error(f"Error al obtener estadísticas del dashboard: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

def parse_datetime_str(date_str, time_str, default_time=None):
    """Parsea fecha (DD/MM/YYYY o YYYY-MM-DD) y hora (HH:MM:SS) a datetime."""
    if not date_str or not time_str:
        return None
    try:
        if '/' in date_str: # Formato DD/MM/YYYY
            dt_obj = datetime.strptime(f"{date_str} {time_str}", '%d/%m/%Y %H:%M:%S')
        else: # Asumir YYYY-MM-DD
            dt_obj = datetime.strptime(f"{date_str} {time_str}", '%Y-%m-%d %H:%M:%S')
        return dt_obj
    except (ValueError, TypeError) as e:
        logger.warning(f"Error parseando fecha/hora: {date_str} {time_str}. Error: {e}")
        # Intentar solo con fecha si la hora falla y hay default_time?
        try:
            if '/' in date_str:
                 date_obj_only = datetime.strptime(date_str, '%d/%m/%Y')
            else:
                 date_obj_only = datetime.strptime(date_str, '%Y-%m-%d')
            if default_time:
                return date_obj_only.replace(hour=default_time[0], minute=default_time[1], second=default_time[2])
        except:
             pass # Ignorar si solo la fecha también falla
        return None

@bp.route('/api/buscar_guias', methods=['GET'])
def buscar_guias():
    """
    API endpoint para buscar guías basado en múltiples criterios.
    """
    try:
        # Leer parámetros específicos y filtros generales
        codigo_guia_term = request.args.get('codigo_guia', '').strip()
        placa_term = request.args.get('placa', '').strip()
        start_date_str = request.args.get('startDate')
        end_date_str = request.args.get('endDate')
        proveedores_str = request.args.get('proveedores') # Comma-separated codes
        estado_filtro = request.args.get('estado_filtro') # 'activo', 'completado', or '' for all

        logger.debug(f"Buscando guías con: cod='{codigo_guia_term}', placa='{placa_term}', start='{start_date_str}', end='{end_date_str}', prov='{proveedores_str}', estado='{estado_filtro}'")

        conn = sqlite3.connect('tiquetes.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Base query
        query = """
            SELECT 
                e.codigo_guia, e.nombre_proveedor, e.fecha_registro, e.hora_registro, 
                e.cantidad_racimos, e.placa
            FROM entry_records e
        """
        conditions = []
        params = []

        # Add date filter
        if start_date_str and end_date_str:
            try:
                # Convert YYYY-MM-DD from filter to DD/MM/YYYY for DB comparison if needed
                # Assuming fecha_registro is stored as DD/MM/YYYY
                # This part might need adjustment based on actual DB format
                dt_start = datetime.strptime(start_date_str, '%Y-%m-%d')
                dt_end = datetime.strptime(end_date_str, '%Y-%m-%d')
                
                # Generate dates between start and end for robust comparison
                current_date = dt_start
                date_list = []
                while current_date <= dt_end:
                    date_list.append(current_date.strftime('%d/%m/%Y')) # Format as in DB
                    current_date += timedelta(days=1)
                
                if date_list:
                    date_placeholders = ', '.join('?' * len(date_list))
                    conditions.append(f"e.fecha_registro IN ({date_placeholders})")
                    params.extend(date_list)

            except ValueError:
                 logger.error("Error parsing date range for search.")


        # Add provider filter
        if proveedores_str:
            proveedor_codes = [p.strip() for p in proveedores_str.split(',') if p.strip()]
            if proveedor_codes:
                placeholders = ', '.join('?' * len(proveedor_codes))
                conditions.append(f"e.codigo_proveedor IN ({placeholders})")
                params.extend(proveedor_codes)

        # Add codigo_guia filter
        if codigo_guia_term:
            conditions.append("e.codigo_guia LIKE ?")
            params.append(f'%{codigo_guia_term}%')

        # Add placa filter
        if placa_term:
            conditions.append("e.placa LIKE ?")
            params.append(f'%{placa_term}%')

        # Build WHERE clause
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Order by most recent
        query += " ORDER BY e.fecha_registro DESC, e.hora_registro DESC"

        logger.debug(f"Executing search query: {query} with params: {params}")
        cursor.execute(query, params)
        initial_results = cursor.fetchall()
        logger.debug(f"Initial results count: {len(initial_results)}")

        # Get codes to check status
        result_guia_codes = [row['codigo_guia'] for row in initial_results]
        
        # Query 'salidas' table to find completed guides
        completed_guides = set()
        if result_guia_codes:
            placeholders_salida = ', '.join('?' * len(result_guia_codes))
            cursor.execute(f"SELECT codigo_guia FROM salidas WHERE codigo_guia IN ({placeholders_salida})", result_guia_codes)
            completed_guides = {row['codigo_guia'] for row in cursor.fetchall()}
            logger.debug(f"Completed guides found: {len(completed_guides)}")


        # Filter results based on estado_filtro and format
        final_results = []
        for row in initial_results:
            codigo_guia = row['codigo_guia']
            is_completed = codigo_guia in completed_guides
            
            # Apply estado_filtro
            if estado_filtro == 'completado' and not is_completed:
                continue
            if estado_filtro == 'activo' and is_completed:
                continue

            # Determine Tipo Fruta
            # Use dictionary access for sqlite3.Row
            cantidad_racimos_str = str(row['cantidad_racimos'] if 'cantidad_racimos' in row.keys() else '').strip()
            tipo_fruta_display = "N/A"
            if cantidad_racimos_str.isdigit():
                tipo_fruta_display = "Fruta"
            elif 'pepa' in cantidad_racimos_str.lower():
                tipo_fruta_display = "Pepa"
            
            # Determine Estado Display
            estado_display = "Completado" if is_completed else "En Proceso"

            final_results.append({
                'codigo_guia': codigo_guia,
                'proveedor': row['nombre_proveedor'], # Use dictionary access
                'fecha_hora': f"{row['fecha_registro']} {row['hora_registro']}", # Use dictionary access
                'tipo_fruta': tipo_fruta_display,
                'estado': estado_display,
                'url_detalle': url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
            })

        conn.close()
        logger.debug(f"Final results count after status filter: {len(final_results)}")
        return jsonify(final_results)

    except sqlite3.Error as db_err:
        logger.error(f"Database error searching guides: {db_err}")
        if 'conn' in locals() and conn:
            conn.close()
        return jsonify({"error": "Error de base de datos al buscar guías"}), 500
    except Exception as e:
        logger.error(f"Unexpected error searching guides: {e}", exc_info=True)
        if 'conn' in locals() and conn:
            conn.close()
        return jsonify({"error": "Error inesperado al buscar guías"}), 500
        
