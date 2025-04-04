from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import logging
import traceback
from datetime import datetime, timedelta
import json
import glob
import uuid
import time
import requests
import re
import random
import string
from werkzeug.utils import secure_filename
from app.blueprints.pesaje import bp
from app.utils.common import CommonUtils as Utils
from app.blueprints.misc.routes import allowed_file, ALLOWED_EXTENSIONS, PLACA_WEBHOOK_URL, PESAJE_WEBHOOK_URL
import sqlite3
import pytz
from app.utils.image_processing import process_plate_image

# Configurar logging
logger = logging.getLogger(__name__)

# Definir zona horaria de Bogotá
BOGOTA_TZ = pytz.timezone('America/Bogota')

# Path to the database
DB_PATH = 'tiquetes.db'

# Diccionario para almacenar códigos de autorización temporales
codigos_autorizacion = {}

# Configuración para el webhook de autorización (puedes ajustar esto según necesites)
AUTORIZACION_WEBHOOK_URL = "https://hook.us2.make.com/py29fwgfrehp9il45832acotytu8xr5s"

# Define timezones if not already globally defined
# Assuming they might be needed here as well, or rely on Utils
UTC = pytz.utc

# --- Utility functions potentially replacing get_bogota_datetime ---
def get_utc_timestamp_str():
    """Generates the current UTC timestamp as a string."""
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def get_bogota_datetime():
    """
    Obtiene la fecha y hora actual en la zona horaria de Bogotá.
    Returns:
        tuple: (fecha_str, hora_str) en formato DD/MM/YYYY y HH:MM:SS
    """
    now_utc = datetime.now(pytz.UTC)
    now_bogota = now_utc.astimezone(BOGOTA_TZ)
    return now_bogota.strftime('%d/%m/%Y'), now_bogota.strftime('%H:%M:%S')

# Función para procesar imagen de placa
def process_plate_image(image_path, filename):
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            response = requests.post(PLACA_WEBHOOK_URL, files=files)
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de placa: {response.text}")
            return {"result": "error", "message": f"Error del webhook de placa: {response.text}"}
            
        plate_text = response.text.strip()
        if not plate_text:
            logger.error("Respuesta vacía del webhook de placa")
            return {"result": "error", "message": "No se pudo detectar la placa."}
        
        return {"result": "ok", "plate_text": plate_text}
        
    except Exception as e:
        logger.error(f"Error procesando imagen de placa: {str(e)}")
        return {"result": "error", "message": str(e)}

@bp.route('/pesaje/<codigo>', methods=['GET'])
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        logger.info(f"Iniciando proceso de pesaje para código: {codigo}")
        
        # Verificar formato del código recibido
        if not '_' in codigo:
            # Parece ser solo un código de proveedor, no un código_guia completo
            logger.info(f"El código proporcionado parece ser solo el código del proveedor: {codigo}")
            codigo_proveedor = codigo
            
            # Buscar el registro más reciente para este proveedor
            try:
                from db_utils import get_latest_entry_by_provider_code
                registro = get_latest_entry_by_provider_code(codigo_proveedor)
                if registro:
                    codigo = registro.get('codigo_guia')
                    logger.info(f"Encontrado código_guia más reciente para el proveedor: {codigo}")
            except Exception as e:
                logger.error(f"Error al buscar código_guia para proveedor {codigo_proveedor}: {str(e)}")
        
        # Usar el código original si no tiene formato de guía completa
        codigo_guia_completo = codigo
        logger.info(f"Usando código_guia: {codigo_guia_completo}")
        
        # Intentar obtener datos directamente desde la base de datos (método más fiable)
        datos_guia = None
        try:
            from db_utils import get_entry_record_by_guide_code
            logger.info(f"Buscando registro en base de datos para: {codigo_guia_completo}")
            registro = get_entry_record_by_guide_code(codigo_guia_completo)
            
            if registro:
                logger.info(f"Registro encontrado en base de datos: {registro}")
                # Crear un diccionario con exactamente los campos que espera la plantilla
                datos_guia = {
                    'codigo_guia': codigo_guia_completo,
                    'codigo': registro.get('codigo_proveedor', ''),
                    'nombre': registro.get('nombre_proveedor', ''),
                    'nombre_proveedor': registro.get('nombre_proveedor', ''),
                    'cantidad_racimos': registro.get('cantidad_racimos', ''),
                    'racimos': registro.get('cantidad_racimos', ''),
                    'placa': registro.get('placa', 'No disponible'),
                    'transportador': registro.get('transportador', 'No disponible'),
                    'transportista': registro.get('transportador', 'No disponible'),
                    'fecha_registro': registro.get('fecha_registro', ''),
                    'hora_registro': registro.get('hora_registro', ''),
                    'fecha_tiquete': registro.get('fecha_tiquete', ''),
                    'acarreo': registro.get('acarreo', 'No'),
                    'cargo': registro.get('cargo', 'No'),
                    'estado_actual': 'registro_completado'
                }
                
                # Registrar estos valores en la sesión para garantizar consistencia
                session['codigo_guia'] = codigo_guia_completo
                session['codigo_proveedor'] = registro.get('codigo_proveedor', '')
                session['nombre_proveedor'] = registro.get('nombre_proveedor', '')
                session.modified = True
            else:
                logger.warning(f"No se encontró registro en base de datos para: {codigo_guia_completo}")
        except Exception as e:
            logger.error(f"Error al consultar base de datos: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Si no se encontró en la base de datos, intentar con utils.get_datos_guia
        if not datos_guia:
            try:
                datos_guia = utils.get_datos_guia(codigo_guia_completo)
                if datos_guia:
                    logger.info(f"Datos obtenidos con utils.get_datos_guia para {codigo_guia_completo}")
            except Exception as e:
                logger.error(f"Error al obtener datos con utils.get_datos_guia: {str(e)}")
        
        # Si se encontraron datos, mostrar la página de pesaje
        if datos_guia:
            # Importar función para estandarizar datos
            from app.utils.common import standardize_template_data
            
            # Log de datos antes de estandarizar
            logger.info(f"Datos antes de estandarizar: nombre={datos_guia.get('nombre', datos_guia.get('nombre_proveedor', 'N/A'))}, "
                      f"racimos={datos_guia.get('cantidad_racimos', datos_guia.get('racimos', 'N/A'))}")
            
            # Estandarizar datos para el template
            datos_guia = standardize_template_data(datos_guia, 'pesaje')
            
            # Log detallado de datos estandarizados
            logger.info(f"Datos para template: codigo={datos_guia.get('codigo')}, "
                      f"nombre={datos_guia.get('nombre_proveedor')}, "
                      f"racimos={datos_guia.get('cantidad_racimos')}, "
                      f"transportista={datos_guia.get('transportista')}")
            
            # --- Explicitly fetch Racimos from entry_records DB --- 
            racimos_from_db = datos_guia.get('racimos', datos_guia.get('cantidad_racimos', 'No registrado')) 
            try:
                conn_racimos = sqlite3.connect(DB_PATH)
                cursor_racimos = conn_racimos.cursor()
                # Fetch 'cantidad_racimos' from entry_records
                cursor_racimos.execute("SELECT cantidad_racimos FROM entry_records WHERE codigo_guia = ?", (codigo_guia_completo,))
                racimos_result = cursor_racimos.fetchone()
                conn_racimos.close()
                # Update if found and valid
                if racimos_result and racimos_result[0] and racimos_result[0] not in ('No disponible', 'N/A', ''):
                    racimos_from_db = racimos_result[0]
                    logger.info(f"Updated racimos from DB for {codigo_guia_completo}: {racimos_from_db}")
                else:
                    logger.warning(f"Using racimos from datos_guia for {codigo_guia_completo}: {racimos_from_db}")
            except sqlite3.Error as db_err:
                logger.error(f"DB error fetching racimos for {codigo_guia_completo}: {db_err}")
                if 'conn_racimos' in locals() and conn_racimos:
                    conn_racimos.close() 
            # --- End fetching Racimos ---
            
            return render_template('pesaje/pesaje.html', datos=datos_guia)
        else:
            # Si no se encontraron datos, mostrar error 404
            logger.warning(f"No se encontraron datos para el código: {codigo_guia_completo}")
            return render_template('error.html', message=f"No se encontraron datos para el código {codigo_guia_completo}"), 404
    except Exception as e:
        logger.error(f"Error en la función pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error procesando la solicitud: {str(e)}"), 500


@bp.route('/pesaje-inicial/<codigo>', methods=['GET', 'POST'])
def pesaje_inicial(codigo):
    """Manejo de pesaje inicial (directo o virtual)"""
    pass



@bp.route('/pesaje-tara/<codigo>', methods=['GET', 'POST'])
def pesaje_tara(codigo):
    """
    Maneja la vista de pesaje de tara y el procesamiento del mismo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = current_app.config['GUIAS_FOLDER']
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo

        # Obtener datos de la guía usando el código completo
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Verificar que la clasificación esté completada
        if not datos_guia.get('clasificacion_completada'):
            return render_template('error.html', 
                                message="Debe completar el proceso de clasificación antes de realizar el pesaje de tara"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje.pesaje_tara', codigo=codigo_guia_completo))

        # Renderizar template de pesaje de tara
        return render_template('pesaje/pesaje_tara.html',
                            codigo=codigo_guia_completo,
                            datos=datos_guia)

    except Exception as e:
        logger.error(f"Error en pesaje de tara: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje de tara"), 500



@bp.route('/procesar_pesaje_tara_directo', methods=['POST'])
def procesar_pesaje_tara_directo():
    """
    Procesa el pesaje de tara directo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Verificar que haya un archivo cargado
        if 'imagen' not in request.files:
            logger.error("No se envió archivo de imagen para pesaje de tara")
            return jsonify({"success": False, "message": "No se envió archivo de imagen"}), 400
            
        image_file = request.files['imagen']
        codigo_guia = request.form.get('codigo_guia')
        
        if not image_file:
            logger.error("No se seleccionó archivo de imagen para pesaje de tara")
            return jsonify({"success": False, "message": "No se seleccionó archivo de imagen"}), 400
            
        if not codigo_guia:
            logger.error("No se proporcionó código de guía para pesaje de tara")
            return jsonify({"success": False, "message": "No se proporcionó código de guía"}), 400
        
        # Verificar si la guía ya ha sido procesada con pesaje de tara o más allá
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía con pesaje de tara ya procesado: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya tiene registrada la tara y no se puede modificar'
            }), 403
        
        # Guardar imagen temporalmente
        image_filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
        image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
        image_file.save(image_path)
        
        # Extraer el código del proveedor del codigo_guia
        codigo_proveedor = None
        
        # Si el código de guía contiene un guion, podría seguir el formato FECHA-CODIGO
        if '-' in codigo_guia:
            codigo_proveedor = codigo_guia.split('-')[1]
        # Si el código de guía contiene un guion bajo, podría seguir el formato CODIGO_FECHA_HORA
        elif '_' in codigo_guia:
            codigo_proveedor = codigo_guia.split('_')[0]
        else:
            codigo_proveedor = codigo_guia
            
        # Verificar si hay un código de proveedor específico en la sesión o base de datos
        try:
            # Intentar obtener datos de registro para extraer código de proveedor
            datos_registro = utils.get_datos_registro(codigo_guia)
            if datos_registro and 'codigo_proveedor' in datos_registro and datos_registro['codigo_proveedor']:
                codigo_proveedor = datos_registro['codigo_proveedor']
        except Exception as e:
            logger.warning(f"Error al obtener código proveedor de registro: {str(e)}")
        
        # Enviar al webhook de Make para procesamiento
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            data = {'codigo_proveedor': codigo_proveedor}
            logger.info(f"Enviando imagen al webhook: {PESAJE_WEBHOOK_URL}")
            response = requests.post(PESAJE_WEBHOOK_URL, files=files, data=data)
        
        logger.info(f"Respuesta del Webhook: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({
                'success': False,
                'message': f"Error del webhook: {response.text}"
            }), 500
            
        # Procesar respuesta del webhook
        response_text = response.text.strip()
        if not response_text:
            logger.error("Respuesta vacía del webhook")
            return jsonify({
                'success': False,
                'message': "Respuesta vacía del webhook."
            }), 500

        if "Exitoso!" in response_text:
            import re
            peso_match = re.search(r'El peso tara es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?', response_text)
            if peso_match:
                peso = peso_match.group(1)
                session['imagen_pesaje_tara'] = image_filename
                
                return jsonify({
                    'success': True,
                    'peso': peso,
                    'message': 'Peso tara detectado correctamente'
                })
            else:
                logger.error("No se pudo extraer el peso de la respuesta")
                logger.error(f"Texto de respuesta: {response_text}")
                return jsonify({
                    'success': False,
                    'message': 'No se pudo extraer el peso de la respuesta'
                })
        else:
            logger.error("El código no corresponde a la guía")
            return jsonify({
                'success': False,
                'message': 'El código no corresponde a la guía'
            })
            
    except Exception as e:
        logger.error(f"Error en pesaje tara directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})



@bp.route('/registrar_peso_directo', methods=['POST'])
def registrar_peso_directo():
    """
    Endpoint para registrar el peso directo
    Recibe datos del pesaje (JSON o FormData) y lo guarda en la base de datos
    """
    try:
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Generar timestamp UTC
        timestamp_utc = get_utc_timestamp_str()
        logger.info(f"Generado timestamp UTC para registrar_peso_directo: {timestamp_utc}")
        
        # Determinar si los datos vienen como JSON o como FormData
        if request.is_json:
            data = request.get_json()
            codigo_guia = data.get('codigo_guia')
            peso_bruto = data.get('peso_bruto')
            imagen_pesaje = None
        else:
            # Datos de FormData
            codigo_guia = request.form.get('codigo_guia')
            peso_bruto = request.form.get('peso_bruto')
            imagen_pesaje = None
            
            # Si hay archivos adjuntos, procesarlos
            if 'foto_bascula' in request.files:
                foto_bascula = request.files['foto_bascula']
                if foto_bascula and foto_bascula.filename:
                    # Guardar la imagen
                    filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
                    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                    foto_bascula.save(filepath)
                    imagen_pesaje = filename
                    logger.info(f"Imagen de báscula guardada en: {filepath}")
        
        if not codigo_guia or not peso_bruto:
            logger.error(f"Datos incompletos en registrar_peso_directo: codigo_guia={codigo_guia}, peso_bruto={peso_bruto}")
            return jsonify({
                'success': False,
                'message': 'Datos incompletos'
            }), 400
        
        # Recuperar datos existentes de la guía para conservar información de entrada
        datos_existentes = utils.get_datos_guia(codigo_guia) or {}
        logger.info(f"Datos existentes recuperados: {len(datos_existentes.keys()) if datos_existentes else 0} campos")
        
        # Obtener información del proveedor
        codigo_proveedor = datos_existentes.get('codigo_proveedor') or datos_existentes.get('codigo')
        nombre_proveedor = datos_existentes.get('nombre_proveedor') or datos_existentes.get('nombre')
        
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor or datos_existentes.get('codigo_proveedor', ''),
            'nombre_proveedor': nombre_proveedor or datos_existentes.get('nombre_proveedor', ''),
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'directo',
            'timestamp_pesaje_utc': timestamp_utc,
            'imagen_pesaje': imagen_pesaje or '',
            'codigo_guia_transporte_sap': datos_existentes.get('codigo_guia_transporte_sap', '')
        }
        
        # Almacenar en la base de datos
        from db_operations import store_pesaje_bruto
        result = store_pesaje_bruto(datos_pesaje)
        
        if result:
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
            
            # Actualizar datos en la guía
            datos_existentes.update({
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'directo',
                'timestamp_pesaje_utc': timestamp_utc
            })
            
            if datos_pesaje['codigo_guia_transporte_sap']:
                datos_existentes['codigo_guia_transporte_sap'] = datos_pesaje['codigo_guia_transporte_sap']
                logger.info(f"Guía de transporte SAP {datos_pesaje['codigo_guia_transporte_sap']} almacenada para {codigo_guia}")
                
            # Actualizar la guía
            utils.update_datos_guia(codigo_guia, datos_existentes)
            
            # Generar URL de redirección a la página de resultados
            try:
                redirect_url = url_for('pesaje.ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
                logger.info(f"Redirigiendo a la URL: {redirect_url}")
            except Exception as e:
                logger.error(f"Error generando URL: {str(e)}")
                redirect_url = f"/pesaje/ver_resultados_pesaje/{codigo_guia}"
            
            return jsonify({
                'success': True,
                'message': 'Peso registrado correctamente',
                'redirect_url': redirect_url,
                'peso_bruto': peso_bruto
            })
        else:
            logger.error(f"Error al guardar peso para {codigo_guia}")
            return jsonify({
                'success': False,
                'message': 'Error al guardar el peso'
            }), 500
            
    except Exception as e:
        logger.error(f"Error en registrar_peso_directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al registrar el peso: {str(e)}'
        }), 500


@bp.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    """
    Registra el peso bruto manual o virtual usando la capa de acceso a datos.
    Puede recibir datos en formato JSON o form-data (con imagen).
    """
    try:
        # Verificar si los datos vienen en JSON o en form-data
        if request.is_json:
            data = request.json
            codigo_guia = data.get('codigo_guia')
            peso_bruto = data.get('peso_bruto')
            tipo_pesaje = data.get('tipo_pesaje', 'manual')  # Por defecto es manual
            
            imagen_path = ''  # Sin imagen en solicitud JSON
        else:
            # Datos de formulario
            codigo_guia = request.form.get('codigo_guia')
            peso_bruto = request.form.get('peso_bruto')
            tipo_pesaje = request.form.get('tipo_pesaje', 'manual')
            
            # Procesar imagen si existe
            imagen_path = ''
            if 'imagen' in request.files and request.files['imagen'].filename:
                imagen = request.files['imagen']
                # Crear directorio si no existe
                img_dir = os.path.join(current_app.static_folder, 'pesajes', codigo_guia)
                os.makedirs(img_dir, exist_ok=True)
                
                # Guardar imagen
                filename = f"pesaje_{str(uuid.uuid4())[:8]}.jpg"
                file_path = os.path.join(img_dir, filename)
                imagen.save(file_path)
                
                # Guardar ruta relativa para acceso web
                imagen_path = os.path.join('static', 'pesajes', codigo_guia, filename)
        
        # Validar datos requeridos
        if not codigo_guia or not peso_bruto:
            logger.error(f"Datos incompletos en registrar_peso_virtual: codigo_guia={codigo_guia}, peso_bruto={peso_bruto}")
            return jsonify({'success': False, 'message': 'Faltan datos requeridos: código de guía y peso bruto'}), 400
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))

        # Generar timestamp UTC
        timestamp_utc = get_utc_timestamp_str()
        logger.info(f"Generado timestamp UTC para pesaje virtual: {timestamp_utc}")

        # Obtener datos existentes (si los hay)
        datos_guia = utils.get_datos_guia(codigo_guia) or {}
        
        # Preparar los datos para almacenar
        codigo_proveedor = None
        nombre_proveedor = None
        
        # Extraer información relevante si hay datos previos
        if datos_guia:
            codigo_proveedor = datos_guia.get('codigo_proveedor', datos_guia.get('codigo'))
            nombre_proveedor = datos_guia.get('nombre_proveedor', datos_guia.get('nombre'))
            logger.info(f"Datos previos encontrados para guía {codigo_guia}")
        else:
            # Si no hay datos previos, extraer información del código o sesión
            logger.warning(f"No se encontraron datos previos para la guía {codigo_guia}")
            
            # Intentar obtener de la sesión
            if 'codigo_proveedor' in session:
                codigo_proveedor = session.get('codigo_proveedor')
            
            if 'nombre_proveedor' in session:
                nombre_proveedor = session.get('nombre_proveedor')
            
            # Si no están en la sesión, extraer del código de guía
            if not codigo_proveedor and '_' in codigo_guia:
                codigo_proveedor = codigo_guia.split('_')[0]
        
        # Si después de todo, no se pudo obtener el código de proveedor, usar un valor predeterminado
        if not codigo_proveedor:
            codigo_proveedor = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
            logger.warning(f"Usando código de proveedor predeterminado: {codigo_proveedor}")
        
        # Si no hay nombre de proveedor, usar 'No disponible'
        if not nombre_proveedor:
            nombre_proveedor = "No disponible"
            logger.warning("Nombre de proveedor no disponible")
        
        # Capturar fecha y hora actuales
        fecha_pesaje = datetime.now().strftime('%d/%m/%Y')
        hora_pesaje = datetime.now().strftime('%H:%M:%S')
        
        # Verificar si hay una guía de transporte SAP disponible
        codigo_guia_transporte_sap = request.form.get('codigo_guia_transporte_sap')
        if not codigo_guia_transporte_sap and request.is_json:
            codigo_guia_transporte_sap = data.get('codigo_guia_transporte_sap')
        if not codigo_guia_transporte_sap and 'codigo_guia_transporte_sap' in session:
            codigo_guia_transporte_sap = session.get('codigo_guia_transporte_sap')
            # Limpiar de la sesión después de usarlo
            session.pop('codigo_guia_transporte_sap', None)
            logger.info(f"Recuperada guía de transporte SAP de la sesión: {codigo_guia_transporte_sap}")

        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor or '',
            'nombre_proveedor': nombre_proveedor or '',
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'virtual',
            'timestamp_pesaje_utc': timestamp_utc,
            'imagen_pesaje': imagen_path or '',
            'codigo_guia_transporte_sap': codigo_guia_transporte_sap or datos_guia.get('codigo_guia_transporte_sap', '')
        }
        
        # Almacenar en la base de datos
        from db_operations import store_pesaje_bruto
        result = store_pesaje_bruto(datos_pesaje)
        
        if result:
            logger.info(f"Peso virtual registrado correctamente para {codigo_guia}: {peso_bruto}kg")
            
            # Actualizar datos en la guía
            datos_guia.update({
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'virtual',
                'timestamp_pesaje_utc': timestamp_utc
            })
            
            if codigo_guia_transporte_sap:
                datos_guia['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
                logger.info(f"Guía de transporte SAP {codigo_guia_transporte_sap} almacenada para {codigo_guia}")
                
            # Actualizar la guía
            utils.update_datos_guia(codigo_guia, datos_guia)
            
            # Generar URL de redirección a la página de resultados
            try:
                redirect_url = url_for('pesaje.ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
                logger.info(f"Redirigiendo a la URL: {redirect_url}")
            except Exception as e:
                logger.error(f"Error generando URL: {str(e)}")
                redirect_url = f"/pesaje/ver_resultados_pesaje/{codigo_guia}"
            
            return jsonify({
                'success': True,
                'message': 'Peso registrado correctamente',
                'redirect_url': redirect_url,
                'peso_bruto': peso_bruto
            })
        else:
            logger.error(f"Error al guardar peso para {codigo_guia}")
            return jsonify({
                'success': False,
                'message': 'Error al guardar el peso'
            }), 500
            
    except Exception as e:
        logger.error(f"Error en registrar_peso_virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al registrar el peso: {str(e)}'
        }), 500


@bp.route('/pesajes', methods=['GET'])
def lista_pesajes():
    """
    Muestra la lista de registros de pesaje desde la base de datos SQLite.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        tipo_pesaje = request.args.get('tipo_pesaje', '')

        # Preparar filtros para la consulta a la base de datos
        filtros = {}
        if fecha_desde:
            filtros['fecha_desde'] = fecha_desde
        if fecha_hasta:
            filtros['fecha_hasta'] = fecha_hasta
        if codigo_proveedor:
            filtros['codigo_proveedor'] = codigo_proveedor
        if nombre_proveedor:
            filtros['nombre_proveedor'] = nombre_proveedor
        if tipo_pesaje:
            filtros['tipo_pesaje'] = tipo_pesaje
        
        # Obtener datos de la base de datos
        from db_operations import get_pesajes_bruto, get_clasificacion_by_codigo_guia
        pesajes = get_pesajes_bruto(filtros)
        
        # Verificar el estado de clasificación para cada pesaje
        for pesaje in pesajes:
            # Si no tiene estado_actual, asumimos que está en pesaje_completado
            if not pesaje.get('estado_actual'):
                pesaje['estado_actual'] = 'pesaje_completado'
                
            # Verificar si existe una clasificación para este código de guía
            clasificacion = get_clasificacion_by_codigo_guia(pesaje['codigo_guia'])
            if clasificacion:
                # Si existe clasificación, actualizar el estado
                pesaje['estado_actual'] = 'clasificacion_completada'
            
            # También verificar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
            archivo_clasificacion = os.path.join(clasificaciones_dir, f"clasificacion_{pesaje['codigo_guia']}.json")
            if os.path.exists(archivo_clasificacion):
                pesaje['estado_actual'] = 'clasificacion_completada'
        
        # Preparar filtros para la plantilla
        filtros_template = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'tipo_pesaje': tipo_pesaje
        }
        
        return render_template('pesajes_lista.html', pesajes=pesajes, filtros=filtros_template)
        
    except Exception as e:
        logger.error(f"Error listando pesajes: {str(e)}")
        flash(f"Error al cargar la lista de pesajes: {str(e)}", "error")
        return redirect(url_for('home'))



@bp.route('/verificar_placa_pesaje', methods=['POST'])
def verificar_placa_pesaje():
    """
    Procesa una imagen de placa durante el pesaje para verificar si coincide con la placa registrada.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        logger.info("Iniciando verificación de placa en pesaje")
        
        if 'placa_foto' not in request.files:
            logger.warning("No se encontró imagen de placa en la solicitud")
            return jsonify({
                'success': False,
                'message': 'No se encontró imagen de placa'
            })
        
        placa_foto = request.files['placa_foto']
        codigo_guia = request.form.get('codigo_guia')
        placa_registrada = request.form.get('placa_registrada', '').strip().upper()
        
        if not codigo_guia:
            logger.warning("Falta el código de guía en la solicitud")
            return jsonify({
                'success': False,
                'message': 'Falta el código de guía'
            })
        
        if not placa_registrada:
            logger.warning("No hay placa registrada para comparar")
            return jsonify({
                'success': False,
                'message': 'No hay placa registrada para comparar'
            })
        
        if not placa_foto.filename:
            logger.warning("El archivo de imagen de placa está vacío")
            return jsonify({
                'success': False,
                'message': 'El archivo de imagen está vacío'
            })
        
        if not allowed_file(placa_foto.filename):
            logger.warning(f"Tipo de archivo no permitido: {placa_foto.filename}")
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido'
            })
        
        # Guardar la imagen temporalmente
        filename = secure_filename(f"verificacion_placa_{codigo_guia}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
        temp_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        placa_foto.save(temp_path)
        
        logger.info(f"Imagen de placa guardada temporalmente: {temp_path}")
        
        # Enviar la imagen al webhook para procesamiento
        result = process_plate_image(temp_path, filename)
        
        if result.get("result") != "ok":
            logger.warning(f"Error al procesar la placa: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': f"Error al detectar la placa: {result.get('message')}"
            })
        
        # Obtener el texto de la placa detectada
        placa_detectada = result.get("plate_text", "").strip().upper()
        
        if not placa_detectada:
            logger.warning("No se pudo detectar el texto de la placa")
            return jsonify({
                'success': False,
                'message': 'No se pudo detectar el texto de la placa'
            })
        
        # Comparar la placa detectada con la registrada
        # Normalizamos ambas placas para una comparación más flexible
        placa_registrada_norm = ''.join(c for c in placa_registrada if c.isalnum())
        placa_detectada_norm = ''.join(c for c in placa_detectada if c.isalnum())
        
        # Verificar si las placas coinciden
        coincide = placa_registrada_norm == placa_detectada_norm
        
        logger.info(f"Resultado de verificación: Placa registrada: {placa_registrada}, Placa detectada: {placa_detectada}, Coincide: {coincide}")
        
        # Guardar esta verificación en la información de la guía
        try:
            datos_guia = utils.get_datos_guia(codigo_guia)
            if datos_guia:
                if 'verificaciones_placa' not in datos_guia:
                    datos_guia['verificaciones_placa'] = []
                
                datos_guia['verificaciones_placa'].append({
                    'fecha': datetime.now().strftime('%d/%m/%Y'),
                    'hora': datetime.now().strftime('%H:%M:%S'),
                    'placa_registrada': placa_registrada,
                    'placa_detectada': placa_detectada,
                    'coincide': coincide
                })
        except Exception as e:
            logger.error(f"Error al guardar verificación de placa: {str(e)}")

        return jsonify({
            'success': True,
            'placa_detectada': placa_detectada,
            'placa_registrada': placa_registrada,
            'coincide': coincide
        })
        
    except Exception as e:
        logger.error(f"Error en verificación de placa: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al procesar la imagen: {str(e)}'
        })



@bp.route('/pesaje-neto/<codigo>', methods=['GET'])
def pesaje_neto(codigo):
    """
    Maneja la vista de pesaje neto y el procesamiento del mismo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = current_app.config['GUIAS_FOLDER']
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        
        # Si no se encuentra en utils, buscar directamente en la base de datos
        if not datos_guia:
            logger.info(f"Intentando obtener datos de la guía {codigo_guia_completo} directamente de la base de datos")
            try:
                from db_operations import get_pesaje_bruto_by_codigo_guia
                from db_utils import get_entry_record_by_guide_code
                
                # Intentar obtener desde db_operations
                datos_guia = get_pesaje_bruto_by_codigo_guia(codigo_guia_completo)
                
                # Si todavía no lo encuentra, intentar con entry records
                if not datos_guia:
                    logger.info(f"Intentando obtener desde entry records para {codigo_guia_completo}")
                    registro = get_entry_record_by_guide_code(codigo_guia_completo)
                    if registro:
                        # Convertir registro a formato de datos_guia
                        datos_guia = {
                            'codigo_guia': registro.get('codigo_guia'),
                            'codigo_proveedor': registro.get('codigo_proveedor'),
                            'nombre_proveedor': registro.get('nombre_proveedor'),
                            'placa': registro.get('placa'),
                            'transportador': registro.get('transportador'),
                            'racimos': registro.get('cantidad_racimos'),
                            'fecha_registro': registro.get('fecha_registro'),
                            'hora_registro': registro.get('hora_registro'),
                            'estado_actual': 'registro_completado'
                        }
                        logger.info(f"Datos obtenidos desde entry records para {codigo_guia_completo}")
            except Exception as e:
                logger.error(f"Error al intentar obtener datos de la base de datos: {str(e)}")
                logger.error(traceback.format_exc())
                
        if not datos_guia:
            logger.error(f"No se pudo encontrar información para la guía: {codigo_guia_completo}")
            flash('Guía no encontrada', 'error')
            return render_template('error.html', message="Guía no encontrada"), 404

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje.pesaje_neto', codigo=codigo_guia_completo))

        # Renderizar template de pesaje neto
        return render_template('pesaje/pesaje_neto.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje neto"), 500



@bp.route('/pesajes-neto-lista', methods=['GET'])
def lista_pesajes_neto():
    """
    Muestra la lista de registros de pesaje neto desde la base de datos SQLite.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_inicio = request.args.get('fecha_inicio', '')
        fecha_fin = request.args.get('fecha_fin', '')
        codigo_guia = request.args.get('codigo_guia', '')
        
        # Preparar filtros para la consulta a la base de datos
        filtros = {}
        if fecha_inicio:
            filtros['fecha_desde'] = fecha_inicio
        if fecha_fin:
            filtros['fecha_hasta'] = fecha_fin
        if codigo_guia:
            filtros['codigo_guia'] = codigo_guia
        
        # Obtener datos de la base de datos
        from db_operations import get_pesajes_neto
        pesajes = get_pesajes_neto(filtros)
        
        # Preparar filtros para la plantilla
        filtros_template = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'codigo_guia': codigo_guia
        }
        
        return render_template('pesajes_neto_lista.html', pesajes=pesajes, filtros=filtros_template)
        
    except Exception as e:
        logger.error(f"Error listando pesajes neto: {str(e)}")
        flash(f"Error al cargar la lista de pesajes neto: {str(e)}", "error")
        return redirect(url_for('home'))


@bp.route('/ver_resultados_pesaje/<codigo_guia>')
def ver_resultados_pesaje(codigo_guia):
    """
    Muestra los resultados del pesaje para una guía específica.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))

        logger.info(f"Accediendo a vista de resultados de pesaje para: {codigo_guia}")

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia}")
            return render_template('error.html', message=f"No se encontraron datos para la guía {codigo_guia}"), 404

        # --- CONSULTAR PESAJES_BRUTO DIRECTAMENTE ---
        # Verificar que el pesaje esté completado consultando la DB
        peso_bruto_db = None
        fecha_pesaje_db = None
        hora_pesaje_db = None
        guia_sap_db = None
        try:
            # Usar la ruta configurada en la aplicación Flask
            db_path = current_app.config['TIQUETES_DB_PATH']
            conn_check = sqlite3.connect(db_path) 
            cursor_check = conn_check.cursor()
            logger.info(f"Consultando pesajes_bruto en '{db_path}' para {codigo_guia}")
            cursor_check.execute("""
                SELECT peso_bruto, fecha_pesaje, hora_pesaje, codigo_guia_transporte_sap 
                FROM pesajes_bruto 
                WHERE codigo_guia = ?
            """, (codigo_guia,))
            pesaje_result = cursor_check.fetchone()
            conn_check.close()

            if pesaje_result:
                peso_bruto_db = pesaje_result[0]
                fecha_pesaje_db = pesaje_result[1]
                hora_pesaje_db = pesaje_result[2]
                guia_sap_db = pesaje_result[3]
                logger.info(f"Pesaje bruto encontrado en DB para {codigo_guia}: Peso={peso_bruto_db}, Fecha={fecha_pesaje_db}, Hora={hora_pesaje_db}, SAP={guia_sap_db}")
                # Actualizar datos_guia con valores frescos de la DB
                datos_guia['peso_bruto'] = peso_bruto_db
                datos_guia['fecha_pesaje'] = fecha_pesaje_db
                datos_guia['hora_pesaje'] = hora_pesaje_db
                datos_guia['codigo_guia_transporte_sap'] = guia_sap_db
            else:
                logger.warning(f"No se encontró registro en pesajes_bruto para {codigo_guia}")

        except sqlite3.Error as db_err:
            logger.error(f"DB error consultando pesajes_bruto para {codigo_guia}: {db_err}")
        except NameError:
             logger.error("DB_PATH no está definida. Asegúrate que sea accesible en este contexto.")
             # Podrías intentar obtenerla de current_app.config si está disponible
             # flash("Error de configuración interna al verificar el pesaje.", "error")
             # return redirect(url_for('misc.index')) # O alguna otra página de error/inicio
        except Exception as e:
            logger.error(f"Error inesperado consultando pesajes_bruto para {codigo_guia}: {e}")

        # Verificar si se encontró el peso en la DB (o si ya estaba en datos_guia por si acaso)
        if not peso_bruto_db and not datos_guia.get('peso_bruto'):
            logger.warning(f"La guía {codigo_guia} no tiene pesaje bruto registrado (verificado en DB).")
            flash("No hay datos de pesaje registrados para esta guía.", "warning")
            return redirect(url_for('pesaje.pesaje', codigo=codigo_guia))
        # --- FIN CONSULTA PESAJES_BRUTO ---

        # Agregar timestamp para evitar caché en imágenes
        now_timestamp = int(time.time())

        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        if not os.path.exists(qr_path):
            qr_url = url_for('pesaje.ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            logger.info(f"Generando QR para acceso a resultados de pesaje: {qr_url}")
            utils.generar_qr(qr_url, qr_path)

        # --- Explicitly fetch Racimos from entry_records DB ---
        # Initialize with value from datos_guia as default or 'No registrado' if completely missing
        #racimos_from_db = datos_guia.get('cantidad_racimos', datos_guia.get('racimos', 'No registrado'))
        #logger.debug(f"Initial racimos value for {codigo_guia} from datos_guia: {racimos_from_db}")

        #try:
            # Usar la ruta configurada en la aplicación Flask para buscar racimos
            #db_path_racimos = current_app.config['TIQUETES_DB_PATH']
            #conn_racimos = sqlite3.connect(db_path_racimos) # Use the correct path variable
            #cursor_racimos = conn_racimos.cursor()
            # Fetch 'cantidad_racimos' from entry_records using the specific codigo_guia
            #logger.info(f"Querying racimos in '{db_path_racimos}' for codigo_guia: {codigo_guia}") # Update log message
            #cursor_racimos.execute("SELECT cantidad_racimos FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
            #racimos_result = cursor_racimos.fetchone()
            #conn_racimos.close()

            # Update if a valid result is found in the database
            #if racimos_result and racimos_result[0] and str(racimos_result[0]).strip() not in ('No disponible', 'N/A', '', 'None', None):
                #racimos_from_db = str(racimos_result[0]).strip() # Ensure it's a string and clean
                #logger.info(f"Successfully fetched and updated racimos from DB for {codigo_guia}: {racimos_from_db}")
            #elif racimos_result:
                 # Log if record found but value is invalid
                 #logger.warning(f"Record found for {codigo_guia}, but racimos value ('{racimos_result[0]}') is invalid/empty. Keeping value: {racimos_from_db}")
            #else:
                 # Log if no record was found at all for this codigo_guia
                 #logger.warning(f"No record found in entry_records for racimos lookup using codigo_guia: {codigo_guia}. Keeping value: {racimos_from_db}")

        #except sqlite3.Error as db_err:
            #logger.error(f"DB error fetching racimos for {codigo_guia}: {db_err}")
            # Ensure racimos_from_db has a value even on DB error
            #if 'racimos_from_db' not in locals(): racimos_from_db = 'Error DB'
        #except Exception as e:
             #logger.error(f"Unexpected error fetching racimos for {codigo_guia}: {e}")
             # Ensure racimos_from_db has a value on other errors
             #if 'racimos_from_db' not in locals(): racimos_from_db = 'Error General'
        # --- End fetching Racimos ---

        # Preparar datos para el template
        imagen_pesaje = datos_guia.get('imagen_pesaje')
        if imagen_pesaje and not imagen_pesaje.startswith('/'):
            # Assuming images are stored relative to static/images/
            imagen_pesaje = url_for('static', filename=f'images/{imagen_pesaje}')
        elif imagen_pesaje and imagen_pesaje.startswith('/static/'):
             # Already a static URL, use as is
             imagen_pesaje = imagen_pesaje
        else:
            imagen_pesaje = None # Handle case where image path is invalid or None

        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa', {})
        if not verificacion_placa:
            verificacion_placa = {}

        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia,
            'tipo_pesaje': datos_guia.get('tipo_pesaje', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'N/A'),
            'hora_pesaje': datos_guia.get('hora_pesaje', 'N/A'),
            'comentarios': datos_guia.get('comentarios_pesaje', ''),
            'fotos_pesaje': datos_guia.get('fotos_pesaje', []),
            'codigo_proveedor': datos_guia.get('codigo_proveedor', datos_guia.get('codigo', 'No disponible')),
            'nombre_proveedor': datos_guia.get('nombre_agricultor', datos_guia.get('nombre_proveedor', 'No disponible')),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'racimos': datos_guia.get('cantidad_racimos', datos_guia.get('racimos', 'No registrado')), # Use value directly from datos_guia
            'guia_sap': datos_guia.get('codigo_guia_transporte_sap', datos_guia.get('guia_sap', 'No registrada')),
            'imagen_pesaje': imagen_pesaje, # Use the potentially corrected URL
            'qr_code': url_for('static', filename=f'qr/{qr_filename}'),
            'verificacion_placa': verificacion_placa,
            'now_timestamp': now_timestamp
        }

        # Renderizar la plantilla con los datos
        return render_template('pesaje/resultados_pesaje.html', **context)

    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

@bp.route('/procesar_pesaje_directo', methods=['POST'])
def procesar_pesaje_directo():
    """
    Procesa la validación de foto para pesaje directo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Generar timestamp UTC
        timestamp_utc = get_utc_timestamp_str()
        logger.info(f"Generado timestamp UTC para procesar pesaje directo: {timestamp_utc}")
        
        # Obtener datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        peso_bruto = request.form.get('peso_bruto')
        tipo_pesaje = request.form.get('tipo_pesaje', 'directo')
        # image_filename = request.form.get('image_filename') # Ya no se espera como form data
        codigo_sap = request.form.get('codigo_guia_transporte_sap')

        # Verificar archivo de imagen cargado
        if 'imagen' not in request.files:
            logger.error("No se envió archivo de imagen para pesaje directo")
            return jsonify({"success": False, "message": "No se envió archivo de imagen"}), 400
        image_file = request.files['imagen']
        if not image_file or image_file.filename == '':
            logger.error("No se seleccionó archivo de imagen o está vacío para pesaje directo")
            return jsonify({"success": False, "message": "No se seleccionó archivo de imagen o está vacío"}), 400

        # Generar nombre de archivo seguro
        image_filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")

        # Validar otros datos
        if not codigo_guia or not peso_bruto or not tipo_pesaje:
            logger.error("Datos incompletos para procesar pesaje directo (faltan código, peso o tipo)")
            return jsonify({"success": False, "message": "Datos incompletos para procesar pesaje directo (faltan código, peso o tipo)"}), 400
        
        # Guardar imagen temporalmente
        image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
        image_file.save(image_path) # Guardar el archivo cargado
        
        # Enviar al webhook de Make para procesamiento
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            data = {'codigo_proveedor': codigo_sap}
            logger.info(f"Enviando imagen al webhook: {PESAJE_WEBHOOK_URL}")
            response = requests.post(PESAJE_WEBHOOK_URL, files=files, data=data)
        
        logger.info(f"Respuesta del Webhook: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({
                'success': False,
                'message': f"Error del webhook: {response.text}"
            }), 500
            
        # Procesar respuesta del webhook
        response_text = response.text.strip()
        if not response_text:
            logger.error("Respuesta vacía del webhook")
            return jsonify({
                'success': False,
                'message': "Respuesta vacía del webhook."
            }), 500

        # Verificar si la respuesta es exitosa
        if "Exitoso" not in response_text:
            logger.error(f"Respuesta no exitosa: {response_text}")
            return jsonify({
                'success': False,
                'message': f"Respuesta no exitosa: {response_text}"
            })

        # Extraer la guía de transporte SAP
        codigo_guia_transporte_sap = None
        match_guia_sap = re.search(r'Guia de transporte SAP:\s*"?(\d+)"?', response_text, re.IGNORECASE)
        if match_guia_sap:
            codigo_guia_transporte_sap = match_guia_sap.group(1)
            # Guardar en la sesión para su uso posterior
            session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
            logger.info(f"Guía de transporte SAP extraída: {codigo_guia_transporte_sap}")

        # Buscar el peso en la respuesta usando diferentes patrones
        peso = None
        patrones = [
            r'El peso es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?',
            r'El peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?',
            r'peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?',
            r'peso es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?',
            r'Peso Bruto:\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?',
            r'Exitoso!\s*"?(\d+(?:\.\d+)?)"?\s*(?:kg)?'
        ]
        
        for patron in patrones:
            match = re.search(patron, response_text, re.IGNORECASE)
            if match:
                peso = match.group(1)
                break
        
        if peso:
            session['imagen_pesaje'] = image_filename
            result = {
                'success': True,
                'peso': peso,
                'message': 'Peso detectado correctamente'
            }
            # Añadir la guía de transporte SAP a la respuesta si está disponible
            if codigo_guia_transporte_sap:
                result['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
            
            return jsonify(result)
        else:
            # Intentar una búsqueda más general para cualquier número en la respuesta
            # como último recurso
            general_match = re.search(r'(\d+(?:\.\d+)?)', response_text)
            if general_match and "Exitoso" in response_text:
                peso = general_match.group(1)
                session['imagen_pesaje'] = image_filename
                result = {
                    'success': True,
                    'peso': peso,
                    'message': 'Peso detectado correctamente (búsqueda general)'
                }
                if codigo_guia_transporte_sap:
                    result['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
                
                return jsonify(result)
            else:
                logger.error("No se pudo extraer el peso de la respuesta")
                logger.error(f"Texto de respuesta: {response_text}")
                return jsonify({
                    'success': False,
                    'message': 'No se pudo extraer el peso de la respuesta. Por favor, intente de nuevo o use el modo manual.'
                })
            
    except Exception as e:
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/solicitar_autorizacion_pesaje', methods=['POST'])
def solicitar_autorizacion_pesaje():
    """
    Solicita autorización para realizar un pesaje manual enviando datos al webhook.
    """
    try:
        # Determinar si los datos vienen como JSON o como FormData
        if request.is_json:
            data = request.get_json()
            codigo_guia = data.get('codigo_guia')
            comentarios = data.get('comentarios', 'No especificado')
            peso_manual = data.get('peso_manual')  # Opcional
            nombre_usuario = data.get('nombre_usuario', 'Usuario no especificado')
        else:
            # Datos de FormData
            codigo_guia = request.form.get('codigo_guia')
            comentarios = request.form.get('comentarios', request.form.get('motivo', 'No especificado'))
            peso_manual = request.form.get('peso_manual')  # Opcional
            nombre_usuario = request.form.get('nombre_usuario', 'Usuario no especificado')
        
        logger.info(f"Datos recibidos en solicitud de autorización: codigo_guia={codigo_guia}, comentarios={comentarios}")
        
        if not codigo_guia:
            logger.error("Datos incompletos en solicitud de autorización: falta código de guía")
            return jsonify({
                'success': False,
                'message': 'Falta el código de guía en la solicitud'
            }), 400
        
        # Obtener datos de la guía para incluir información relevante
        utils = current_app.config.get('utils')
        datos_guia = utils.get_datos_guia(codigo_guia) or {}
        
        # Generar la URL de la guía centralizada
        from flask import url_for
        url_guia_centralizada = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        logger.info(f"URL de guía centralizada generada: {url_guia_centralizada}")
        
        # Generar código de autorización temporal
        codigo_auth = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Almacenar el código con los datos relevantes (expira en 30 minutos)
        codigos_autorizacion[codigo_auth] = {
            'codigo_guia': codigo_guia,
            'peso_manual': peso_manual,
            'fecha_solicitud': datetime.now().isoformat(),
            'expira': (datetime.now() + timedelta(minutes=30)).isoformat()
        }
        
        # Preparar datos para enviar al webhook - Incluimos toda la información en un solo payload
        payload = {
            'tipo_solicitud': 'autorizacion_pesaje',
            'codigo_guia': codigo_guia,
            'comentarios': comentarios,
            'peso_manual': peso_manual or 'No especificado',
            'nombre_usuario': nombre_usuario,
            'fecha_solicitud': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'No disponible'),
            'transportista': datos_guia.get('transportador', datos_guia.get('transportista', 'No disponible')),
            'placa': datos_guia.get('placa', 'No disponible'),
            'url_guia_centralizada': url_guia_centralizada,
            'codigo_autorizacion': codigo_auth  # Incluimos el código en el mismo payload
        }
        
        # Enviar solicitud al webhook
        logger.info(f"Enviando solicitud de autorización con código {codigo_auth} a: {AUTORIZACION_WEBHOOK_URL}")
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL, 
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        # Verificar respuesta del webhook
        if response.status_code != 200:
            logger.error(f"Error del webhook de autorización: {response.status_code} - {response.text}")
            return jsonify({
                'success': False,
                'message': f'Error al procesar la solicitud: {response.text}'
            }), 500
        
        # Procesar respuesta exitosa
        logger.info(f"Solicitud de autorización con código {codigo_auth} enviada exitosamente: {response.text}")
        
        # Retornar respuesta exitosa sin incluir el código de autorización
        return jsonify({
            'success': True,
            'message': 'Solicitud enviada correctamente. El código de autorización le será proporcionado por el personal autorizado.'
        })
    
    except Exception as e:
        logger.error(f"Error en solicitud de autorización: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al procesar la solicitud: {str(e)}'
        }), 500


@bp.route('/validar_codigo_autorizacion', methods=['POST'])
def validar_codigo_autorizacion():
    """
    Valida un código de autorización temporal para pesaje manual.
    El código debe existir en el diccionario de códigos de autorización.
    """
    try:
        # Determinar si los datos vienen como JSON o FormData
        if request.is_json:
            data = request.get_json()
            codigo_guia = data.get('codigo_guia')
            codigo_auth = data.get('codigoAutorizacion')
        else:
            codigo_guia = request.form.get('codigo_guia')
            codigo_auth = request.form.get('codigoAutorizacion')

        logger.info(f"Validando código de autorización: {codigo_auth} para guía: {codigo_guia}")

        if not codigo_guia or not codigo_auth:
            logger.error("Datos incompletos para validar código de autorización")
            return jsonify({
                'success': False,
                'message': 'Faltan datos necesarios para validar el código'
            }), 400

        # Verificar si el código de autorización existe y está vigente
        if codigo_auth in codigos_autorizacion:
            auth_data = codigos_autorizacion[codigo_auth]
            
            # Verificar que corresponda a la misma guía
            if auth_data['codigo_guia'] != codigo_guia:
                logger.warning(f"Código de autorización para guía incorrecta: esperada={auth_data['codigo_guia']}, recibida={codigo_guia}")
                return jsonify({
                    'success': False,
                    'message': 'Código de autorización no corresponde a esta guía'
                })
            
            # Verificar que no haya expirado
            expira = datetime.fromisoformat(auth_data['expira'])
            if expira < datetime.now():
                logger.warning(f"Código de autorización expirado: {codigo_auth}")
                # Eliminar código expirado
                codigos_autorizacion.pop(codigo_auth, None)
                return jsonify({
                    'success': False,
                    'message': 'Código de autorización expirado'
                })
            
            # Código válido - registrar en la sesión
            logger.info(f"Código de autorización validado correctamente: {codigo_auth}")
            
            # Guardar en la sesión si se proporcionó un peso
            if 'peso_manual' in auth_data and auth_data['peso_manual']:
                session['peso_manual_autorizado'] = auth_data['peso_manual']
                
            # Eliminar el código usado para evitar reutilización
            # codigos_autorizacion.pop(codigo_auth, None)
            
            return jsonify({
                'success': True,
                'message': 'Código de autorización validado correctamente'
            })
        else:
            logger.warning(f"Código de autorización no encontrado: {codigo_auth}")
            return jsonify({
                'success': False,
                'message': 'Código de autorización inválido'
            })
    
    except Exception as e:
        logger.error(f"Error validando código de autorización: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error validando código: {str(e)}'
        }), 500


