from flask import (
    render_template, request, redirect, url_for, session, 
    jsonify, flash, send_file, make_response, current_app, send_from_directory, abort, Blueprint, Response
)
import os
import logging
import traceback
from datetime import datetime, timedelta, time
import json
import glob
from werkzeug.utils import secure_filename
from app.blueprints.misc import bp
from app.utils.common import CommonUtils as Utils, standardize_template_data, get_estado_guia, UTC, BOGOTA_TZ
import time
import sqlite3
import base64
import qrcode
from app.utils.image_processing import process_plate_image
from app.utils.common import get_estado_guia
import pytz
from app.blueprints.clasificacion.routes import get_clasificacion_by_codigo_guia
# Importar la nueva función de operaciones de presupuesto
from app.utils.db_budget_operations import obtener_datos_presupuesto
# Importar funciones de db_operations y db_utils desde la raíz
from db_operations import get_clasificaciones, get_pesajes_neto, get_pesaje_bruto_by_codigo_guia
from db_utils import get_entry_records # Corregido para buscar en la raíz

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
        
        # TODO (Plan Timestamps): Convertir timestamp_pesaje_utc a local para mostrar
        fecha_pesaje_local = "N/A"
        hora_pesaje_local = "N/A"
        timestamp_utc_str = pesaje_data.get('timestamp_pesaje_utc')
        if timestamp_utc_str:
            try:
                dt_utc = datetime.strptime(timestamp_utc_str, "%Y-%m-%d %H:%M:%S")
                dt_utc = UTC.localize(dt_utc)
                dt_bogota = dt_utc.astimezone(BOGOTA_TZ)
                fecha_pesaje_local = dt_bogota.strftime('%d/%m/%Y')
                hora_pesaje_local = dt_bogota.strftime('%H:%M:%S')
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"Could not parse timestamp_pesaje_utc '{timestamp_utc_str}' for {codigo_guia}: {e}")
                # Fallback to potentially incorrect old values if parsing fails, or keep N/A
                fecha_pesaje_local = pesaje_data.get('fecha_pesaje', 'N/A') # Old field fallback
                hora_pesaje_local = pesaje_data.get('hora_pesaje', 'N/A')   # Old field fallback
        
        # Variables para la plantilla
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': pesaje_data.get('peso_bruto', 'N/A'),
            'tipo_pesaje': pesaje_data.get('tipo_pesaje', 'N/A'),
            # 'fecha_pesaje': pesaje_data.get('fecha_pesaje', 'N/A'), # OLD FIELD
            # 'hora_pesaje': pesaje_data.get('hora_pesaje', 'N/A'),   # OLD FIELD
            'fecha_pesaje': fecha_pesaje_local, # Use converted local date
            'hora_pesaje': hora_pesaje_local,   # Use converted local time
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
                    'timestamp_registro_utc': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), # <-- NEW UTC timestamp
                    'image_filename': image_filename,
                    'pdf_filename': pdf_filename,
                    'qr_filename': session.get('qr_filename', '')
                }
                
                # ---- ADD NOTA TO THE RECORD ----
                datos_registro['nota'] = webhook_data.get('nota', webhook_data.get('Nota', '')) # Add the note here
                
                # Guardar en la base de datos
                if db_utils.store_entry_record(datos_registro):
                    logger.info(f"Datos guardados en la base de datos para código guía: {codigo_guia}")
                else:
                    logger.error(f"FALLO al guardar datos en la base de datos para {codigo_guia}. Abortando.")
                    # Si la base de datos falla, es un error crítico
                    return jsonify({
                        "status": "error",
                        "message": f"Error crítico: no se pudieron guardar los datos del registro en la base de datos para {codigo_guia}"
                    }), 500
                    
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
    Vista centralizada de una guía, mostrando toda la información relevante.
    """
    try:
        import db_utils
        from flask import current_app
        
        # Inicializar utils desde la configuración de la aplicación
        utils = current_app.config.get('utils')
        if not utils:
            logger.error("Utils no disponible en la configuración de la aplicación")
            flash("Error: configuración de utilidades no disponible", "danger")
            return redirect(url_for('misc.index'))
        
        logger.info(f"Accediendo a vista centralizada de guía: {codigo_guia}")
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        logger.info(f"Datos de guía obtenidos: {datos_guia}")

        # >> ADD CHECK FOR NONE HERE <<
        if datos_guia is None:
            logger.error(f"No se encontraron datos para la guía {codigo_guia} al renderizar la vista centralizada.")
            flash(f"Error: No se encontraron datos para la guía especificada ({codigo_guia}). Puede que haya sido eliminada o nunca existió.", "danger")
            # Redirect to a safe page, like the main list or index
            return redirect(url_for('entrada.lista_entradas')) # Or misc.index or another suitable route

        # --- INICIO: Conversión de Timestamps UTC a Bogotá para Template --- 
        if datos_guia:
            from datetime import datetime
            import pytz
            BOGOTA_TZ = pytz.timezone('America/Bogota')
            UTC = pytz.utc

            timestamp_fields = {
                'timestamp_registro_utc': ('fecha_registro', 'hora_registro'),
                'timestamp_pesaje_utc': ('fecha_pesaje', 'hora_pesaje'),
                'timestamp_clasificacion_utc': ('fecha_clasificacion', 'hora_clasificacion'),
                'timestamp_pesaje_neto_utc': ('fecha_pesaje_neto', 'hora_pesaje_neto'),
                'timestamp_salida_utc': ('fecha_salida', 'hora_salida')
            }

            for utc_field, (local_date_field, local_time_field) in timestamp_fields.items():
                utc_timestamp_str = datos_guia.get(utc_field)
                # --- DEBUG LOGGING START ---
                logger.info(f"Processing timestamp for {utc_field}: Value='{utc_timestamp_str}' (Type: {type(utc_timestamp_str)})")
                # --- DEBUG LOGGING END ---
                fecha_local = None
                hora_local = None
                if utc_timestamp_str:
                    try:
                        # Parsear el string UTC y localizarlo como UTC
                        dt_utc = datetime.strptime(utc_timestamp_str, "%Y-%m-%d %H:%M:%S")
                        dt_utc = UTC.localize(dt_utc)
                        # Convertir a Bogotá
                        dt_local = dt_utc.astimezone(BOGOTA_TZ)
                        # Formatear
                        fecha_local = dt_local.strftime('%d/%m/%Y')
                        hora_local = dt_local.strftime('%H:%M:%S')
                        # --- DEBUG LOGGING START ---
                        logger.info(f"Successfully converted {utc_field}: Fecha={fecha_local}, Hora={hora_local}")
                        # --- DEBUG LOGGING END ---
                    except (ValueError, TypeError) as e:
                        # --- DEBUG LOGGING START ---
                        logger.warning(f"FAILED to parse/convert timestamp '{utc_timestamp_str}' for field {utc_field} in ver_guia_centralizada: {e}")
                        # --- DEBUG LOGGING END ---
                # else: # Add log if the string is None or empty
                    # logger.info(f"Skipping conversion for {utc_field} because value is None or empty.")
                
                # Añadir los campos formateados directamente a datos_guia
                datos_guia[local_date_field] = fecha_local
                datos_guia[local_time_field] = hora_local
        # --- FIN: Conversión de Timestamps UTC a Bogotá para Template ---

        # Verificar y corregir la ruta de la imagen si es necesario
        if datos_guia and datos_guia.get('image_filename'):
            logger.info(f"Nombre de archivo de imagen encontrado: {datos_guia['image_filename']}")
            
            # Verificar si la imagen existe en la ruta esperada
            image_path = os.path.join(current_app.static_folder, 'uploads', datos_guia['image_filename'])
            logger.info(f"Ruta completa de la imagen: {image_path}")
            
            if not os.path.exists(image_path):
                logger.warning(f"Imagen no encontrada en ruta principal: {image_path}")
                
                # Buscar en registros de entrada para obtener el nombre correcto del archivo
                try:
                    entry_record = db_utils.get_entry_record_by_guide_code(codigo_guia)
                    logger.info(f"Registro de entrada encontrado: {entry_record}")
                    
                    if entry_record and entry_record.get('image_filename'):
                        datos_guia['image_filename'] = entry_record['image_filename']
                        logger.info(f"Nombre de imagen actualizado desde registro de entrada: {datos_guia['image_filename']}")
                        
                        # Verificar si la imagen actualizada existe
                        updated_image_path = os.path.join(current_app.static_folder, 'uploads', datos_guia['image_filename'])
                        if os.path.exists(updated_image_path):
                            logger.info(f"Imagen encontrada en ruta actualizada: {updated_image_path}")
                    else:
                        logger.warning("No se encontró nombre de imagen en el registro de entrada")
                except Exception as e:
                    logger.error(f"Error buscando imagen en registros de entrada: {str(e)}")
        else:
            logger.warning(f"No se encontró nombre de archivo de imagen para la guía: {codigo_guia}")

        # Obtener datos del registro de entrada
        try:
            entry_record = db_utils.get_entry_record_by_guide_code(codigo_guia)
            if entry_record:
                # Actualizar datos_guia con la información del registro de entrada
                datos_guia.update({
                    'codigo_proveedor': entry_record.get('codigo_proveedor'),
                    'nombre_proveedor': entry_record.get('nombre_proveedor'),
                    'nombre_agricultor': entry_record.get('nombre_proveedor'),  # Para compatibilidad
                    'transportador': entry_record.get('transportador'),
                    'placa': entry_record.get('placa'),
                    'racimos': entry_record.get('cantidad_racimos'),
                    'cantidad_racimos': entry_record.get('cantidad_racimos'),
                    'acarreo': entry_record.get('acarreo'),
                    'cargo': entry_record.get('cargo')
                })
                logger.info(f"Datos de registro de entrada obtenidos para {codigo_guia}")
            else:
                logger.warning(f"No se encontró registro de entrada para la guía {codigo_guia}")
        except Exception as e:
            logger.error(f"Error obteniendo registros de entrada: {str(e)}")

        # NUEVO: Verificar directamente si existe una clasificación para esta guía
        clasificacion_completada = False
        fecha_clasificacion = None
        hora_clasificacion = None
        
        try:
            # Verificar en la tabla de clasificaciones
            conn = sqlite3.connect('tiquetes.db')
            cursor = conn.cursor()
            cursor.execute("SELECT fecha_clasificacion, hora_clasificacion FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
            result = cursor.fetchone()
            if result:
                clasificacion_completada = True
                fecha_clasificacion = result[0]
                hora_clasificacion = result[1]
                logger.info(f"Encontrada clasificación para {codigo_guia} en tabla clasificaciones: fecha={fecha_clasificacion}, hora={hora_clasificacion}")
                
                # Actualizar datos_guia con esta información
                datos_guia['clasificacion_completada'] = True
                datos_guia['estado_clasificacion'] = 'completado'
                datos_guia['fecha_clasificacion'] = fecha_clasificacion
                datos_guia['hora_clasificacion'] = hora_clasificacion
                
                # También verificar si existen archivos de clasificación
                clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
                json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
                if os.path.exists(json_path):
                    logger.info(f"Encontrado archivo de clasificación: {json_path}")
                    datos_guia['archivo_clasificacion'] = True
            else:
                logger.info(f"No se encontró clasificación en tabla clasificaciones para {codigo_guia}")
            
            # NUEVO: Verificar si existe un pesaje neto para la guía
            cursor.execute("SELECT fecha_pesaje, hora_pesaje, peso_neto FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia,))
            result = cursor.fetchone()
            pesaje_neto_completado = False
            if result:
                fecha_pesaje_neto = result[0]
                hora_pesaje_neto = result[1]
                peso_neto = result[2]
                
                if fecha_pesaje_neto and hora_pesaje_neto and peso_neto:
                    pesaje_neto_completado = True
                    logger.info(f"Encontrado pesaje neto para {codigo_guia}: fecha={fecha_pesaje_neto}, hora={hora_pesaje_neto}, peso={peso_neto}")
                    
                    # Actualizar datos_guia con esta información
                    datos_guia['pesaje_neto_completado'] = True
                    datos_guia['fecha_pesaje_neto'] = fecha_pesaje_neto
                    datos_guia['hora_pesaje_neto'] = hora_pesaje_neto
                    datos_guia['peso_neto'] = peso_neto
            else:
                # Si no hay en la DB, pero existe en los datos_guia, considerarlo completado
                if datos_guia.get('peso_neto') and datos_guia.get('peso_neto') != 'Pendiente' and datos_guia.get('peso_neto') != 'N/A':
                    pesaje_neto_completado = True
                    datos_guia['pesaje_neto_completado'] = True
                    logger.info(f"Pesaje neto encontrado en datos_guia para {codigo_guia}")
            
            # NUEVO: Verificar si existe registro de salida para la guía
            # Seleccionar timestamp UTC en lugar de fecha/hora local
            cursor.execute("SELECT timestamp_salida_utc, comentarios_salida FROM salidas WHERE codigo_guia = ?", (codigo_guia,))
            result = cursor.fetchone()
            salida_completada = False
            if result:
                timestamp_utc = result[0]
                # fecha_salida = result[0] # Remover variable antigua
                # hora_salida = result[1] # Remover variable antigua
                comentarios_salida = result[1] # Indice ahora es 1
                
                # Verificar si el timestamp existe
                if timestamp_utc:
                    salida_completada = True
                    logger.info(f"Encontrado registro de salida para {codigo_guia}: timestamp={timestamp_utc}")
                    
                    # Actualizar datos_guia con esta información
                    datos_guia['timestamp_salida_utc'] = timestamp_utc
                    # datos_guia['fecha_salida'] = fecha_salida # Remover asignación antigua
                    # datos_guia['hora_salida'] = hora_salida # Remover asignación antigua
                    datos_guia['comentarios_salida'] = comentarios_salida
                    datos_guia['estado_salida'] = 'Completado'
                    datos_guia['estado_final'] = 'completado'
                    datos_guia['estado_actual'] = 'proceso_completado'
            else:
                logger.info(f"No se encontró registro de salida en tabla salidas para {codigo_guia}")
            
            conn.close()
        except Exception as e:
            logger.error(f"Error verificando datos en tabla: {str(e)}")

        # --- INICIO LÓGICA PEPA --- (Moved outside the exception block)
        # CORRECCIÓN Attribute Error: Manejar el caso donde tipo_fruta puede ser None
        tipo_fruta_str = datos_guia.get('tipo_fruta') or '' # Paso 1: Asegurar que sea string
        es_pepa = tipo_fruta_str.strip().upper() == 'PEPA' # Paso 2: Calcular es_pepa
        
        # Se eliminó la comprobación basada en racimos_valor, usar solo tipo_fruta
        # racimos_valor = str(datos_guia.get('cantidad_racimos', datos_guia.get('racimos', ''))).strip().lower()
        # if racimos_valor == 'pepa':
        
        if es_pepa:
            logger.info(f"Guía {codigo_guia} es de PEPA. Omitiendo clasificación.")
            # Marcar clasificación como completada/omitida para el flujo
            clasificacion_completada = True # Update local variable if used later
            datos_guia['clasificacion_completada'] = True
            datos_guia['estado_clasificacion'] = 'Omitido (Pepa)'
            # Asignar fecha/hora de pesaje como placeholder si no existen para clasificación
            if not datos_guia.get('fecha_clasificacion'):
                datos_guia['fecha_clasificacion'] = datos_guia.get('fecha_pesaje', 'N/A')
            if not datos_guia.get('hora_clasificacion'):
                 datos_guia['hora_clasificacion'] = datos_guia.get('hora_pesaje', 'N/A')
            # Añadir a pasos completados si la lista existe y no está ya
            if 'pasos_completados' in datos_guia and isinstance(datos_guia['pasos_completados'], list) and 'clasificacion' not in datos_guia['pasos_completados']:
                 datos_guia['pasos_completados'].append('clasificacion')
            if 'datos_disponibles' in datos_guia and isinstance(datos_guia['datos_disponibles'], list) and 'clasificacion' not in datos_guia['datos_disponibles']:
                 datos_guia['datos_disponibles'].append('clasificacion')
        # --- FIN LÓGICA PEPA ---

        # Recalcular estado_info basado en los datos actualizados (importante DESPUÉS de la lógica PEPA)
        # Re-import locally to try and resolve UnboundLocalError
        # ELIMINADO: Se construirá estado_info manualmente
        # from app.utils.common import get_estado_guia
        # estado_info = get_estado_guia(codigo_guia)
        # logger.info(f"Estado Info recalculado (post-pepa check): {estado_info}")
        
        # --- CONSTRUIR estado_info MANUALMENTE --- (Mover construcción aquí después de lógica PEPA)
        clasificacion_registrada = datos_guia.get('clasificacion_completada', False) # Usar el valor posiblemente actualizado por PEPA
        pesaje_neto_completado = bool(datos_guia.get('timestamp_pesaje_neto_utc') or 
                                    (datos_guia.get('peso_neto') is not None and 
                                     str(datos_guia.get('peso_neto')).lower() not in ['pendiente', 'n/a', '']))
        salida_completada = bool(datos_guia.get('timestamp_salida_utc'))

        pasos_completados = ['entrada', 'pesaje']
        if clasificacion_registrada: # Usar la variable local actualizada
            pasos_completados.append('clasificacion')
        if pesaje_neto_completado:
            pasos_completados.append('pesaje_neto')
        if salida_completada:
            pasos_completados.append('salida')

        siguiente_paso = None
        descripcion = "Desconocido"
        porcentaje_avance = 0

        if 'salida' in pasos_completados:
            descripcion = "Proceso completado"
            siguiente_paso = None
            porcentaje_avance = 100
        elif 'pesaje_neto' in pasos_completados:
            descripcion = "Pesaje neto completado, pendiente salida"
            siguiente_paso = 'salida'
            porcentaje_avance = 80
        elif 'clasificacion' in pasos_completados: # Ya incluye el caso PEPA
             # Si es PEPA, ya ajustamos la descripción antes, mantenerla
             if es_pepa:
                 descripcion = "PEPA registrada, pendiente pesaje neto"
             else:
                 descripcion = "Clasificación completada, pendiente pesaje neto"
             siguiente_paso = 'pesaje_neto'
             porcentaje_avance = 60
        elif 'pesaje' in pasos_completados:
            descripcion = "Pesaje bruto completado, pendiente clasificación"
            siguiente_paso = 'clasificacion'
            porcentaje_avance = 40
        elif 'entrada' in pasos_completados:
             descripcion = "Registro de entrada completado, pendiente pesaje bruto"
             siguiente_paso = 'pesaje'
             porcentaje_avance = 20
        else:
             descripcion = "Guía no encontrada o inválida"
             siguiente_paso = 'entrada'
             porcentaje_avance = 0
             
        estado_info = {
            'pasos_completados': pasos_completados,
            'siguiente_paso': siguiente_paso,
            'descripcion': descripcion,
            'porcentaje_avance': porcentaje_avance,
            'datos_disponibles': pasos_completados # Usar los mismos por ahora
        }
        datos_guia['estado_info'] = estado_info # Añadir al diccionario principal
        # --- FIN CONSTRUCCIÓN estado_info ---
        
        # Logging detallado para diagnóstico del problema
        logger.info(f"----- DATOS GUÍA CENTRALIZADA PRE-ESTADO ({codigo_guia}) (Post Manual Build) -----")
        logger.info(f"Estado Info Construido: {estado_info}")
        logger.info(f"Es Pepa: {es_pepa}")
        # ... (otros logs) ...

        # Asegurar que clasificacion_manual sea un diccionario
        if not isinstance(datos_guia.get('clasificacion_manual'), dict):
            datos_guia['clasificacion_manual'] = {}

        # Generar QR Code
        try:
            from .routes import generar_qr_guia
        except ImportError:
            def generar_qr_guia(code): logger.error("generar_qr_guia no encontrada!"); return None
            logger.error("No se pudo importar generar_qr_guia desde .routes")
        qr_url = generar_qr_guia(codigo_guia)

        # Renderizar la plantilla
        return render_template(
            'guia_centralizada.html',
            datos_guia=datos_guia,
            codigo_guia=codigo_guia,
            qr_url=qr_url,
            es_pepa=es_pepa,
            estado_info=estado_info,
            clasificacion_registrada=clasificacion_registrada,
            pesaje_neto_completado=pesaje_neto_completado,
            salida_completada=salida_completada,
            manual_registrada = clasificacion_registrada, # Revisar esta lógica
            now_timestamp=datetime.now().timestamp()
        )
        
    except Exception as e:
        # Contenido correcto del bloque except original
        logger.error(f"Error en ver_guia_centralizada para {codigo_guia}: {str(e)}")
        logger.error(traceback.format_exc())
        flash("Ocurrió un error inesperado al cargar la guía.", "danger")
        return redirect(url_for('entrada.lista_entradas')) # Redirige a una página segura


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
    Muestra una vista detallada de todo el proceso para una guía específica,
    incluyendo registro, pesaje, clasificación y salida.
    """
    try:
        utils = Utils(current_app)
        logger = logging.getLogger(__name__) # Ensure logger is available

        # Obtener datos principales de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash(f"No se encontraron datos para la guía: {codigo_guia}", "error")
            # Consider redirecting to a more appropriate page if needed, e.g., dashboard or search
            return render_template('error.html', message=f"Guía {codigo_guia} no encontrada"), 404

        # --- Fetch and Merge Classification Data ---
        try:
            clasificacion_data = get_clasificacion_by_codigo_guia(codigo_guia)
            if clasificacion_data:
                logger.info(f"Clasificación encontrada para {codigo_guia}")
                
                # Merge manual classification (ensure it's a dict)
                clasificacion_manual = clasificacion_data.get('clasificacion_manual')
                if isinstance(clasificacion_manual, str):
                    try:
                        datos_guia['clasificacion_manual'] = json.loads(clasificacion_manual)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not decode clasificacion_manual JSON string for {codigo_guia}")
                        datos_guia['clasificacion_manual'] = {} # Default to empty dict on error
                elif isinstance(clasificacion_manual, dict):
                    datos_guia['clasificacion_manual'] = clasificacion_manual
                else:
                     datos_guia['clasificacion_manual'] = {} # Default if missing or wrong type

                # Merge automatic/consolidated classification if needed by the template
                # Example: Merging consolidated if it exists
                clasificacion_consolidada = clasificacion_data.get('clasificacion_consolidada')
                if isinstance(clasificacion_consolidada, str):
                     try:
                         datos_guia['clasificacion_consolidada'] = json.loads(clasificacion_consolidada)
                     except json.JSONDecodeError:
                         datos_guia['clasificacion_consolidada'] = {}
                elif isinstance(clasificacion_consolidada, dict):
                     datos_guia['clasificacion_consolidada'] = clasificacion_consolidada
                
                # Also merge simple automatic classification fields if available and needed
                clasificacion_automatica = clasificacion_data.get('clasificacion_automatica')
                if isinstance(clasificacion_automatica, str):
                     try:
                         datos_guia['clasificacion_automatica'] = json.loads(clasificacion_automatica)
                     except json.JSONDecodeError:
                         datos_guia['clasificacion_automatica'] = {}
                elif isinstance(clasificacion_automatica, dict):
                     datos_guia['clasificacion_automatica'] = clasificacion_automatica

                # Merge classification timestamp if available
                datos_guia['fecha_clasificacion'] = clasificacion_data.get('fecha_clasificacion', datos_guia.get('fecha_clasificacion'))
                datos_guia['hora_clasificacion'] = clasificacion_data.get('hora_clasificacion', datos_guia.get('hora_clasificacion'))

            else:
                logger.warning(f"No se encontró clasificación para {codigo_guia}. Se usarán valores por defecto.")
                # Ensure default empty dicts if no classification found
                datos_guia.setdefault('clasificacion_manual', {})
                datos_guia.setdefault('clasificacion_consolidada', {})
                datos_guia.setdefault('clasificacion_automatica', {})

        except Exception as classif_error:
            logger.error(f"Error obteniendo o procesando datos de clasificación para {codigo_guia}: {str(classif_error)}")
            # Ensure default empty dicts on error
            datos_guia.setdefault('clasificacion_manual', {})
            datos_guia.setdefault('clasificacion_consolidada', {})
            datos_guia.setdefault('clasificacion_automatica', {})
        # --- End Fetch and Merge ---

        # Generar QR para la guía si no existe
        qr_filename = f'qr_guia_{codigo_guia}.png'
        qr_folder = current_app.config.get('QR_FOLDER', os.path.join(current_app.static_folder, 'qr'))
        os.makedirs(qr_folder, exist_ok=True) # Ensure QR folder exists
        qr_path = os.path.join(qr_folder, qr_filename)
        
        qr_code_url = url_for('static', filename=f'qr/{qr_filename}') # Default URL

        if not os.path.exists(qr_path):
            try:
                # Use the central guide URL for the QR code data
                qr_data = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
                utils.generar_qr(qr_data, qr_path)
                logger.info(f"QR generado para {codigo_guia} en {qr_path}")
            except Exception as qr_err:
                 logger.error(f"Error generando QR para {codigo_guia}: {str(qr_err)}")
                 # Provide a fallback or default QR if generation fails
                 qr_code_url = url_for('static', filename='images/default_qr.png') 

        # Timestamp para el footer
        now_timestamp = datetime.now(pytz.timezone('America/Bogota')).strftime('%d/%m/%Y %H:%M:%S %Z')

        # Preparar contexto para la plantilla
        context = {
            'datos_guia': datos_guia,
            'qr_code': qr_code_url,
            'now_timestamp': now_timestamp,
        }

        return render_template('detalle_proveedor.html', **context)

    except Exception as e:
        logger.error(f"Error al mostrar detalle de proveedor para guía {codigo_guia}: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar detalles: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar detalles: {str(e)}")

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

@bp.route('/api/dashboard/stats', methods=['GET'])
def dashboard_stats():
    logger.info("API endpoint /api/dashboard/stats called")
    
    # Definir zonas horarias
    # UTC = pytz.utc <-- Eliminado
    # BOGOTA_TZ = pytz.timezone('America/Bogota') <-- Eliminado

    # Inicializar respuestas
    response = {
        'calidad_promedios': {
        'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0,
        'Pendunculo Largo': 0, 'Podrido': 0
        },
        'calidad_promedios_auto': {
        'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0,
        'Pendunculo Largo': 0, 'Podrido': 0
        },
        'registros_filtrados_count': 0,
        'total_racimos': 0,
        'peso_neto_total': 0,
        'peso_neto_pepa': 0,
        'pesajes_pendientes': 0,
        'clasificaciones_pendientes': 0,
        'peso_neto_hoy': 0,
        'registros_diarios_chart_data': {'labels': [], 'data': []},
        'peso_neto_diario_chart_data': {'labels': [], 'data': []},
        'racimos_peso_promedio_chart_data': {'labels': [], 'data_racimos': [], 'data_peso_promedio': []},
        'ultimos_registros_tabla': [],
        'tiempos_promedio_proceso': {
        'entrada_a_bruto': 0.0, 'bruto_a_clasif': 0.0, 'clasif_a_neto': 0.0,
        'neto_a_salida': 0.0, 'total': 0.0
        },
        'top_5_peso_neto_tabla': [],
        'alertas_calidad_tabla': []
    }

    try:
        # Obtener parámetros de filtro de la solicitud
        start_date_str = request.args.get('startDate')
        end_date_str = request.args.get('endDate')
        proveedores_str = request.args.get('proveedores') # Códigos de proveedor separados por coma
        estado_filtro = request.args.get('estado') # 'activo', 'completado', o None

        logger.debug(f"Filtros recibidos: startDate={start_date_str}, endDate={end_date_str}, proveedores={proveedores_str}, estado={estado_filtro}")

        # --- Validación y conversión INICIAL de fechas ---
        # Convertir las strings de fecha del filtro a objetos datetime (naive)
        # La conversión a UTC para la consulta se hace en las funciones get_...
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError) as e:
            logger.error(f"Fechas de filtro inválidas: {start_date_str}, {end_date_str}. Usando últimos 7 días. Error: {e}")
            end_date = datetime.now(BOGOTA_TZ).date()
            start_date = end_date - timedelta(days=6)
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')


        # Preparar lista de códigos de proveedor
        lista_codigos_proveedor = []
        if proveedores_str:
            lista_codigos_proveedor = [p.strip() for p in proveedores_str.split(',') if p.strip()]
            logger.debug(f"Filtrando por códigos de proveedor: {lista_codigos_proveedor}")

        # --- Obtención de Datos (usando funciones que ya convierten filtros) ---
        # Crear diccionario de filtros para pasar a las funciones
        db_filtros = {
            'fecha_desde': start_date_str,
            'fecha_hasta': end_date_str,
        }
        if lista_codigos_proveedor:
             # Asumimos que las funciones de BD esperan 'codigo_proveedor' como filtro
             # Si esperan una lista, adaptar aquí. Por ahora, filtro simple si es un solo proveedor
             # o se omite si son varios (dejando que el filtro post-obtención actúe)
             if len(lista_codigos_proveedor) == 1:
                 db_filtros['codigo_proveedor'] = lista_codigos_proveedor[0]
             # Nota: Si las funciones 'get_*' pueden aceptar una lista de códigos,
             # se debería pasar 'lista_codigos_proveedor' directamente en db_filtros.


        # Importar funciones de DB aquí para asegurar contexto de app
        from db_operations import get_clasificaciones, get_pesajes_neto
        from db_utils import get_entry_records, get_pesaje_bruto_by_codigo_guia # Asumiendo que get_pesajes_bruto no se usa directamente para stats

        # Obtener todos los registros relevantes DENTRO del rango UTC equivalente a Bogotá
        # Las funciones get_* ya hacen la conversión UTC internamente para estos filtros
        logger.info(f"Llamando get_entry_records con filtros: {db_filtros}")
        all_entry_records = get_entry_records(db_filtros)
        logger.info(f"Llamando get_clasificaciones con filtros: {db_filtros}")
        all_clasificaciones = get_clasificaciones(db_filtros)
        logger.info(f"Llamando get_pesajes_neto con filtros: {db_filtros}")
        all_pesajes_neto = get_pesajes_neto(db_filtros)

        # --- Filtrado POST-obtención (si es necesario) y combinación de datos ---
        # Combinar datos y aplicar filtros adicionales (proveedor si eran múltiples, estado)

        # Crear un diccionario para unificar datos por codigo_guia
        datos_combinados = {}

        # Procesar entry_records
        for record in all_entry_records:
            cg = record.get('codigo_guia')
            if not cg: continue
            # Aplicar filtro de proveedor si había múltiples seleccionados
            if lista_codigos_proveedor and len(lista_codigos_proveedor) > 1:
                 if record.get('codigo_proveedor') not in lista_codigos_proveedor:
                     continue # Saltar si no coincide

            datos_combinados[cg] = record.copy() # Copiar para no modificar original
            datos_combinados[cg]['clasificacion'] = {} # Inicializar sub-diccionarios
            datos_combinados[cg]['pesaje_neto'] = {}
            datos_combinados[cg]['pesaje_bruto'] = {} # Aunque no llamamos a get_pesajes_bruto, preparamos

        # Procesar clasificaciones
        for clasif in all_clasificaciones:
            cg = clasif.get('codigo_guia')
            if cg in datos_combinados:
                # Solo añadir si el proveedor coincide (si aplica filtro múltiple)
                 if lista_codigos_proveedor and len(lista_codigos_proveedor) > 1:
                    if datos_combinados[cg].get('codigo_proveedor') != clasif.get('codigo_proveedor'):
                         logger.warning(f"Inconsistencia de proveedor para {cg} entre entry y clasif.")
                         continue # O manejar como se prefiera
                 datos_combinados[cg]['clasificacion'] = clasif
            # Considerar qué hacer si hay una clasificación sin registro de entrada (poco probable)

        # Procesar pesajes neto
        for p_neto in all_pesajes_neto:
            cg = p_neto.get('codigo_guia')
            if cg in datos_combinados:
                if lista_codigos_proveedor and len(lista_codigos_proveedor) > 1:
                    if datos_combinados[cg].get('codigo_proveedor') != p_neto.get('codigo_proveedor'):
                         logger.warning(f"Inconsistencia de proveedor para {cg} entre entry y p.neto.")
                         continue
                datos_combinados[cg]['pesaje_neto'] = p_neto
            # Considerar p.neto sin entrada

        # Obtener datos de pesaje bruto individualmente (necesario para tiempos)
        # Esto podría ser ineficiente si hay muchas guías
        for cg in list(datos_combinados.keys()): # Usar list para evitar modificar dict durante iteración
            pesaje_bruto_data = get_pesaje_bruto_by_codigo_guia(cg)
            if pesaje_bruto_data:
                 datos_combinados[cg]['pesaje_bruto'] = pesaje_bruto_data

        # --- Filtrar por estado final ---
        registros_filtrados_final = []
        for cg, data in datos_combinados.items():
            # Determinar estado (podríamos reusar get_estado_guia o una lógica similar aquí)
            # Por simplicidad, asumimos que necesitamos datos de salida para 'completado'
            es_completado = bool(data.get('pesaje_neto') and data['pesaje_neto'].get('timestamp_pesaje_neto_utc')) # Simplificado
            # O usar el estado almacenado si existe
            estado_actual_db = data.get('estado') or data.get('pesaje_bruto', {}).get('estado') or data.get('pesaje_neto', {}).get('estado')

            if estado_actual_db == 'completado':
                 es_completado = True

            if estado_filtro == 'completado' and not es_completado:
                        continue
            if estado_filtro == 'activo' and es_completado:
                             continue
                        
            registros_filtrados_final.append(data) # Añadir el diccionario completo

        logger.info(f"Total registros combinados: {len(datos_combinados)}. Después de filtro estado '{estado_filtro}': {len(registros_filtrados_final)}")


        # --- Cálculos para KPIs y Gráficos ---
        # Utilizar 'registros_filtrados_final' para todos los cálculos

        total_racimos = 0
        peso_neto_total = 0.0
        peso_neto_pepa = 0.0 # Sumar 'peso_producto' si existe

        # Para promedios de calidad
        calidad_sumas_manual = {'Verde': 0, 'Sobremaduro': 0, 'Daño Corona': 0, 'Pendunculo Largo': 0, 'Podrido': 0}
        calidad_contadores_manual = calidad_sumas_manual.copy() # Contador por categoría
        calidad_sumas_automatica = calidad_sumas_manual.copy()
        calidad_contadores_automatica = calidad_sumas_manual.copy()
        num_guias_con_clasif_manual = 0
        num_guias_con_clasif_automatica = 0

        # Para tiempos promedio
        tiempos_diff = {
            'entrada_a_bruto': [], 'bruto_a_clasif': [], 'clasif_a_neto': [], 'neto_a_salida': [], 'total': []
        }

        # Para gráficos diarios
        registros_por_dia = {}
        peso_neto_por_dia = {}
        racimos_por_dia = {} # Para nuevo gráfico
        peso_prom_por_dia_sum = {} # Suma de pesos para promedio
        peso_prom_por_dia_count = {} # Conteo para promedio

        # Generar rango de fechas completo para los gráficos
        date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]


        for data in registros_filtrados_final:
            # --- Racimos ---
            try:
                racimos_guia = int(data.get('cantidad_racimos', 0) or 0)
                total_racimos += racimos_guia
            except (ValueError, TypeError):
                pass # Ignorar si no es un número

            # --- Peso Neto y Pepa ---
            p_neto_data = data.get('pesaje_neto', {})
            try:
                peso_neto_guia = float(p_neto_data.get('peso_neto', 0.0) or 0.0)
                peso_neto_total += peso_neto_guia
            except (ValueError, TypeError):
                pass
            try:
                # Usar 'peso_producto' para pepa si existe, si no, default a 0
                peso_pepa_guia = float(p_neto_data.get('peso_producto', 0.0) or 0.0)
                peso_neto_pepa += peso_pepa_guia
            except (ValueError, TypeError):
                 pass # Ignorar si no se puede convertir


            # --- Calidad Manual ---
            clasif_data = data.get('clasificacion', {})
            manual_json_str = clasif_data.get('clasificacion_manual_json')
            manual_data = {}
            if manual_json_str:
                try:
                    manual_data = json.loads(manual_json_str)
                except json.JSONDecodeError: pass

            # Mapeo nombres JSON a claves internas
            map_manual = {'verdes': 'Verde', 'sobremaduros': 'Sobremaduro', 'danio_corona': 'Daño Corona', 'pedunculo_largo': 'Pendunculo Largo', 'podridos': 'Podrido'}
            tiene_clasif_manual = False
            for json_key, internal_key in map_manual.items():
                try:
                    valor = float(manual_data.get(json_key, 0.0) or 0.0) # Asegurar float
                    calidad_sumas_manual[internal_key] += valor
                    calidad_contadores_manual[internal_key] += 1 # Contar si hay dato
                    tiene_clasif_manual = True
                except (ValueError, TypeError):
                    pass # Ignorar si no es número

            if tiene_clasif_manual:
                 num_guias_con_clasif_manual += 1


            # --- Calidad Automática ---
            auto_json_str = clasif_data.get('clasificacion_automatica_json')
            auto_data = {}
            if auto_json_str:
                try:
                    auto_data = json.loads(auto_json_str)
                except json.JSONDecodeError: pass

            # Mapeo nombres JSON a claves internas (asumiendo estructura anidada)
            # {'verdes': {'cantidad': X, 'porcentaje': Y}, ...}
            map_auto = {'verdes': 'Verde', 'sobremaduros': 'Sobremaduro', 'danio_corona': 'Daño Corona', 'pedunculo_largo': 'Pendunculo Largo', 'podridos': 'Podrido'}
            tiene_clasif_automatica = False
            for json_key, internal_key in map_auto.items():
                 try:
                    # Obtener el porcentaje
                    valor_pct = float(auto_data.get(json_key, {}).get('porcentaje', 0.0) or 0.0)
                    calidad_sumas_automatica[internal_key] += valor_pct
                    calidad_contadores_automatica[internal_key] += 1
                    tiene_clasif_automatica = True
                 except (ValueError, TypeError):
                     pass

            if tiene_clasif_automatica:
                 num_guias_con_clasif_automatica += 1

            # --- Tiempos Promedio ---
            # Helper para parsear timestamp UTC y manejar errores
            def parse_utc_timestamp(ts_str):
                if not ts_str: return None
                try:
                    # Asegurar formato YYYY-MM-DD HH:MM:SS
                    return datetime.strptime(ts_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    logger.warning(f"No se pudo parsear timestamp: {ts_str}")
                    return None

            # !! CORRECCIÓN DE COLUMNA !! Usar timestamp_registro_utc
            ts_entrada = parse_utc_timestamp(data.get('timestamp_registro_utc'))
            ts_bruto = parse_utc_timestamp(data.get('pesaje_bruto', {}).get('timestamp_pesaje_utc'))
            ts_clasif = parse_utc_timestamp(clasif_data.get('timestamp_clasificacion_utc'))
            ts_neto = parse_utc_timestamp(p_neto_data.get('timestamp_pesaje_neto_utc'))
            # ts_salida no está en el modelo actual, estimar o usar p_neto como fin temporal

            if ts_entrada and ts_bruto:
                tiempos_diff['entrada_a_bruto'].append((ts_bruto - ts_entrada).total_seconds() / 60)
            if ts_bruto and ts_clasif:
                tiempos_diff['bruto_a_clasif'].append((ts_clasif - ts_bruto).total_seconds() / 60)
            if ts_clasif and ts_neto:
                tiempos_diff['clasif_a_neto'].append((ts_neto - ts_clasif).total_seconds() / 60)
            # if ts_neto and ts_salida: # Si tuviéramos salida
            #     tiempos_diff['neto_a_salida'].append((ts_salida - ts_neto).total_seconds() / 60)
            if ts_entrada and ts_neto: # Usar neto como fin temporal para 'total'
                 tiempos_diff['total'].append((ts_neto - ts_entrada).total_seconds() / 60)


            # --- Agrupación para Gráficos Diarios (CON CONVERSIÓN A BOGOTÁ) ---
            ts_referencia_utc_str = data.get('timestamp_registro_utc') # Usar registro como referencia
            if ts_referencia_utc_str:
                 try:
                     # Timezones UTC and BOGOTA_TZ are now available from the function scope
                     
                     # Parsear UTC
                     naive_utc = datetime.strptime(ts_referencia_utc_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
                     aware_utc = UTC.localize(naive_utc)
                     # Convertir a Bogotá
                     bogota_dt = aware_utc.astimezone(BOGOTA_TZ)
                     # Obtener la FECHA LOCAL de Bogotá para agrupar
                     fecha_local_bogota = bogota_dt.strftime('%d/%m') # Formato para label de gráfico

                     # Solo considerar si la fecha local está dentro del rango del filtro original
                     if start_date <= bogota_dt.date() <= end_date:
                        registros_por_dia[fecha_local_bogota] = registros_por_dia.get(fecha_local_bogota, 0) + 1
                        peso_neto_por_dia[fecha_local_bogota] = peso_neto_por_dia.get(fecha_local_bogota, 0.0) + peso_neto_guia
                        racimos_por_dia[fecha_local_bogota] = racimos_por_dia.get(fecha_local_bogota, 0) + racimos_guia

                        # Para peso promedio por racimo
                        if racimos_guia > 0:
                             peso_prom_por_dia_sum[fecha_local_bogota] = peso_prom_por_dia_sum.get(fecha_local_bogota, 0.0) + peso_neto_guia
                             peso_prom_por_dia_count[fecha_local_bogota] = peso_prom_por_dia_count.get(fecha_local_bogota, 0) + racimos_guia
                 except Exception as e: # Asegurar que el except esté al nivel del try
                     logger.error(f"Error procesando fecha para gráfico diario: {ts_referencia_utc_str} - {e}")


        # --- Finalizar Cálculos ---
        # Promedios de Calidad
        calidad_promedios_manual = {k: (calidad_sumas_manual[k] / num_guias_con_clasif_manual if num_guias_con_clasif_manual > 0 else 0) for k in calidad_sumas_manual}
        calidad_promedios_automatica = {k: (calidad_sumas_automatica[k] / num_guias_con_clasif_automatica if num_guias_con_clasif_automatica > 0 else 0) for k in calidad_sumas_automatica}

        # Promedios de Tiempos
        tiempos_promedio_proceso = {}
        for key, times in tiempos_diff.items():
            if times:
                tiempos_promedio_proceso[key] = sum(times) / len(times)
            else:
                tiempos_promedio_proceso[key] = 0.0

        # Datos para gráficos diarios (asegurando todas las fechas del rango)
        labels_diarios = [d.strftime('%d/%m') for d in date_range]
        data_registros_diarios = [registros_por_dia.get(label, 0) for label in labels_diarios]
        # Convertir peso neto a toneladas para el gráfico
        data_peso_neto_diario = [(peso_neto_por_dia.get(label, 0.0) / 1000.0) for label in labels_diarios]
        data_racimos_diarios = [racimos_por_dia.get(label, 0) for label in labels_diarios]
        # Calcular peso promedio por racimo (kg)
        data_peso_prom_diario = []
        for label in labels_diarios:
            suma_peso = peso_prom_por_dia_sum.get(label, 0.0)
            conteo_racimos = peso_prom_por_dia_count.get(label, 0)
            promedio = (suma_peso / conteo_racimos) if conteo_racimos > 0 else 0.0
            data_peso_prom_diario.append(promedio)

        # --- NUEVO: Obtener Datos del Presupuesto ---
        logger.info(f"Obteniendo datos de presupuesto para el rango: {start_date_str} a {end_date_str}")
        datos_presupuesto_dict = obtener_datos_presupuesto(start_date_str, end_date_str)
        logger.debug(f"Datos de presupuesto obtenidos: {datos_presupuesto_dict}")
        # --- FIN NUEVO ---

        # --- Finalizar Cálculos ---
        # ... (promedios de calidad, tiempos, datos para gráficos diarios) ...


        # --- Preparar Respuesta JSON ---
        response_data = {
            "registros_entrada_filtrados": len(registros_filtrados_final), 
            "total_racimos_filtrados": total_racimos,
            "peso_neto_total_filtrado": peso_neto_total, 
            "peso_neto_pepa": peso_neto_pepa, 

            "calidad_promedios_manual": calidad_promedios_manual,
            "calidad_promedios_automatica": calidad_promedios_automatica, 

            "tiempos_promedio_proceso": tiempos_promedio_proceso,

            # Datos para gráficos
            "registros_diarios_chart_data": {
                "labels": labels_diarios,
                "data": data_registros_diarios
            },
            "peso_neto_diario_chart_data": {
                "labels": labels_diarios,
                "data": data_peso_neto_diario 
            },
             "racimos_peso_promedio_chart_data": {
                "labels": labels_diarios,
                "data_racimos": data_racimos_diarios,
                "data_peso_promedio": data_peso_prom_diario 
            },
            
            # --- NUEVO: Añadir datos de presupuesto a la respuesta --- 
            "datos_presupuesto": datos_presupuesto_dict, # { 'YYYY-MM-DD': toneladas, ... }
            # --- FIN NUEVO ---

            # Datos para tablas (simplificado, adaptar según necesidad real)
            "ultimos_registros_tabla": [
                # ... 
            ],
            "top_5_peso_neto_tabla": [
                 # ... 
            ],
             "alertas_calidad_tabla": [
                 # ... 
             ]

        }

        logger.info("--- Finalizando /api/dashboard/stats exitosamente ---")
        # logger.debug(f"Response data: {response_data}")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error en dashboard_stats: {str(e)}", exc_info=True)
        # Devolver error 500 con un JSON que indique el problema
        return jsonify({"error": "Error interno procesando estadísticas del dashboard", "details": str(e)}), 500

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
        
