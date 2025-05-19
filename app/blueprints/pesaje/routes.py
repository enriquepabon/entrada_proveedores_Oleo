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
# Importar login_required
from flask_login import login_required
from db_utils import get_entry_record_by_guide_code, get_pesaje_bruto_by_codigo_guia
from db_operations import get_pesajes_neto

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
@login_required # Añadir protección
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        logger.info(f"Iniciando proceso de pesaje para código: {codigo}")
        
        # --- START: Lógica para determinar codigo_guia_completo (se mantiene igual) ---
        codigo_guia_completo = codigo # Asumir inicialmente que es el código completo
        if not '_' in codigo:
            # Parece ser solo un código de proveedor, no un código_guia completo
            logger.info(f"El código proporcionado parece ser solo el código del proveedor: {codigo}")
            codigo_proveedor = codigo
            
            # Buscar el registro más reciente para este proveedor
            try:
                from db_utils import get_latest_entry_by_provider_code
                registro = get_latest_entry_by_provider_code(codigo_proveedor)
                if registro and registro.get('codigo_guia'): # Asegurarse que se encontró y tiene codigo_guia
                    codigo_guia_completo = registro.get('codigo_guia')
                    logger.info(f"Encontrado código_guia más reciente para el proveedor: {codigo_guia_completo}")
                else:
                    logger.warning(f"No se encontró registro reciente para proveedor {codigo_proveedor}, usando código original: {codigo}")
            except ImportError:
                 logger.error("Error al importar db_utils.get_latest_entry_by_provider_code. Asegúrese que db_utils.py está accesible.")
                 # Continuar con el código original como fallback
            except Exception as e:
                logger.error(f"Error al buscar código_guia para proveedor {codigo_proveedor}: {str(e)}")
                # Continuar con el código original como fallback
        
        logger.info(f"Usando código_guia para obtener datos: {codigo_guia_completo}")
        # --- END: Lógica para determinar codigo_guia_completo ---
        
        # --- CAMBIO PRINCIPAL: Usar SIEMPRE utils.get_datos_guia ---
        datos_guia = None
        try:
            datos_guia = utils.get_datos_guia(codigo_guia_completo)
            if datos_guia:
                logger.info(f"Datos obtenidos exitosamente con utils.get_datos_guia para {codigo_guia_completo}")
                # Guardar información relevante en sesión si se obtuvieron datos
                session['codigo_guia'] = codigo_guia_completo
                session['codigo_proveedor'] = datos_guia.get('codigo_proveedor', datos_guia.get('codigo', ''))
                session['nombre_proveedor'] = datos_guia.get('nombre_proveedor', datos_guia.get('nombre', ''))
                session.modified = True
            else:
                 logger.warning(f"utils.get_datos_guia no devolvió datos para {codigo_guia_completo}")
                 # No asignar nada a datos_guia, el bloque 'if datos_guia:' más abajo manejará el caso de no encontrado

        except Exception as e:
            logger.error(f"Error crítico al obtener datos con utils.get_datos_guia para {codigo_guia_completo}: {str(e)}")
            logger.error(traceback.format_exc())
            # Asegurar que datos_guia sea None para que se muestre el error 404
            datos_guia = None
        # --- FIN CAMBIO PRINCIPAL ---
        
        # Si se encontraron datos, mostrar la página de pesaje
        if datos_guia:
            # Importar función para estandarizar datos (se mantiene igual)
            from app.utils.common import standardize_template_data
            
            # Log de datos antes de estandarizar (se mantiene igual)
            logger.info(f"Datos antes de estandarizar: nombre={datos_guia.get('nombre', datos_guia.get('nombre_proveedor', 'N/A'))}, "
                      f"racimos={datos_guia.get('cantidad_racimos', datos_guia.get('racimos', 'N/A'))}")
            
            # Estandarizar datos para el template (se mantiene igual)
            datos_guia = standardize_template_data(datos_guia, 'pesaje')
            
            # Log detallado de datos estandarizados (se mantiene igual)
            logger.info(f"Datos para template: codigo={datos_guia.get('codigo')}, "
                      f"nombre={datos_guia.get('nombre_proveedor')}, "
                      f"racimos={datos_guia.get('cantidad_racimos')}, "
                      f"transportista={datos_guia.get('transportista')}")
            
            # --- Explicitly fetch Racimos from entry_records DB (se mantiene igual) --- 
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
                    # --- CORRECCIÓN: Actualizar el valor en datos_guia ---
                    datos_guia['cantidad_racimos'] = racimos_from_db
                    datos_guia['racimos'] = racimos_from_db # Asegurar consistencia
                    logger.info(f"Updated racimos from DB for {codigo_guia_completo}: {racimos_from_db}")
                else:
                    logger.warning(f"Using racimos from datos_guia for {codigo_guia_completo}: {racimos_from_db}")
            except sqlite3.Error as db_err:
                logger.error(f"DB error fetching racimos for {codigo_guia_completo}: {db_err}")
                if 'conn_racimos' in locals() and conn_racimos:
                    conn_racimos.close() 
            except NameError:
                 logger.error("DB_PATH no está definida al buscar racimos.")
            # --- End fetching Racimos ---
            
            # --- Asegurar que datos_guia tenga fecha_registro y hora_registro ---
            # get_datos_guia ya debería haberlas creado, pero verificamos por si acaso
            if 'fecha_registro' not in datos_guia:
                logger.warning(f"fecha_registro no encontrada en datos_guia para {codigo_guia_completo}, usando 'N/A'")
                datos_guia['fecha_registro'] = 'N/A'
            if 'hora_registro' not in datos_guia:
                logger.warning(f"hora_registro no encontrada en datos_guia para {codigo_guia_completo}, usando 'N/A'")
                datos_guia['hora_registro'] = 'N/A'
            # Hacer lo mismo para fecha/hora de pesaje si es relevante aquí
            if 'fecha_pesaje' not in datos_guia:
                datos_guia['fecha_pesaje'] = 'Pendiente'
            if 'hora_pesaje' not in datos_guia:
                 datos_guia['hora_pesaje'] = ''
            # --- Fin asegurar fechas ---

            return render_template('pesaje/pesaje.html', datos=datos_guia)
        else:
            # Si no se encontraron datos, mostrar error 404 (se mantiene igual)
            logger.warning(f"No se encontraron datos para el código: {codigo_guia_completo}")
            return render_template('error.html', message=f"No se encontraron datos para el código {codigo_guia_completo}"), 404
    except Exception as e:
        # Manejo de errores generales (se mantiene igual)
        logger.error(f"Error en la función pesaje para código '{codigo}': {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error procesando la solicitud: {str(e)}"), 500


@bp.route('/pesaje-inicial/<codigo>', methods=['GET', 'POST'])
@login_required # Añadir protección
def pesaje_inicial(codigo):
    """Manejo de pesaje inicial (directo o virtual)"""
    pass



@bp.route('/pesaje-tara/<codigo>', methods=['GET', 'POST'])
@login_required # Añadir protección
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
@login_required # Añadir protección
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
@login_required # Añadir protección
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
        
        # Get SAP code: Prioritize session, then existing data, then None
        # The webhook response in procesar_pesaje_directo stored it in the session
        codigo_sap = session.get('codigo_guia_transporte_sap', datos_existentes.get('codigo_guia_transporte_sap', None))
        if not codigo_sap or codigo_sap == 'No registrada': # Handle empty strings or default placeholders
            codigo_sap = None
        
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor or '',
            'nombre_proveedor': nombre_proveedor or '',
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'directo',
            'timestamp_pesaje_utc': timestamp_utc,
            'imagen_pesaje': imagen_pesaje or '',
            'codigo_guia_transporte_sap': codigo_sap # Use the prioritized value
        }
        
        # Remove the SAP code from session after using it (good practice)
        session.pop('codigo_guia_transporte_sap', None)
        
        # Almacenar en la base de datos
        from db_operations import store_pesaje_bruto
        result = store_pesaje_bruto(datos_pesaje)
        
        if result:
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
            
            # Ensure the SAP code used for saving is also updated in datos_existentes
            if datos_pesaje.get('codigo_guia_transporte_sap'):
                datos_existentes['codigo_guia_transporte_sap'] = datos_pesaje['codigo_guia_transporte_sap']
                logger.info(f"Guía de transporte SAP {datos_pesaje['codigo_guia_transporte_sap']} preparada para actualizar en guía para {codigo_guia}")
            else:
                # If no SAP code was found/used, ensure it's not present or set to a default in datos_existentes
                datos_existentes['codigo_guia_transporte_sap'] = None # Or 'No registrada'
            
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
@login_required # Añadir protección
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
@login_required # Añadir protección
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
@login_required # Añadir protección
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
@login_required # Añadir protección
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
@login_required # Añadir protección
def lista_pesajes_neto():
    """
    Muestra la lista de registros de pesaje neto desde la base de datos SQLite.
    """
    try:
        current_app.logger.info("Accediendo a la lista de pesajes neto.")
        
        # Leer filtros de la request
        fecha_desde_str = request.args.get('fecha_desde')
        fecha_hasta_str = request.args.get('fecha_hasta')
        # Para el proveedor, permitimos buscar por código o nombre
        proveedor_term = request.args.get('codigo_proveedor', '').strip()

        filtros_db = {}
        if fecha_desde_str:
            filtros_db['fecha_desde'] = fecha_desde_str
        if fecha_hasta_str:
            filtros_db['fecha_hasta'] = fecha_hasta_str
        if proveedor_term:
            # La función get_pesajes_neto (de db_operations.py) deberá manejar este filtro.
            # Si get_pesajes_neto espera 'codigo_proveedor' o 'nombre_proveedor' específicamente,
            # podrías necesitar lógica adicional aquí para determinar cuál enviar o modificar get_pesajes_neto.
            # Por ahora, se pasa como 'proveedor_term' y se asume que get_pesajes_neto lo maneja.
            filtros_db['proveedor_term'] = proveedor_term 

        current_app.logger.info(f"Filtros para get_pesajes_neto: {filtros_db}")
        # Ahora get_pesajes_neto se importa desde db_operations.py (raíz)
        pesajes_neto_raw = get_pesajes_neto(filtros_db) 
        current_app.logger.info(f"Obtenidos {len(pesajes_neto_raw)} registros de pesaje neto de la BD.")

        lista_final = []
        for p_neto in pesajes_neto_raw:
            codigo_guia = p_neto.get('codigo_guia')
            if not codigo_guia:
                current_app.logger.warning(f"Registro de pesaje neto sin código de guía: {p_neto}")
                continue

            entry_data = get_entry_record_by_guide_code(codigo_guia)
            nombre_proveedor = entry_data.get('nombre_proveedor', "No disponible") if entry_data else "No disponible"
            codigo_proveedor = entry_data.get('codigo_proveedor', p_neto.get('codigo_proveedor', "N/A")) if entry_data else p_neto.get('codigo_proveedor', "N/A")
            # NUEVO: Obtener Placa y Cantidad de Racimos
            placa = entry_data.get('placa', "N/A") if entry_data else "N/A"
            cantidad_racimos = entry_data.get('cantidad_racimos', "N/A") if entry_data else "N/A"

            datos_bruto = get_pesaje_bruto_by_codigo_guia(codigo_guia)
            peso_bruto = datos_bruto.get('peso_bruto', "N/A") if datos_bruto else "N/A"
            # NUEVO: Obtener Código SAP
            codigo_sap = datos_bruto.get('codigo_guia_transporte_sap', "N/A") if datos_bruto else "N/A"

            fecha_pesaje_neto_local, hora_pesaje_neto_local = "N/A", "N/A"
            timestamp_utc_str = p_neto.get('timestamp_pesaje_neto_utc')
            if timestamp_utc_str:
                try:
                    dt_utc_aware = UTC.localize(datetime.strptime(timestamp_utc_str, "%Y-%m-%d %H:%M:%S"))
                    dt_bogota = dt_utc_aware.astimezone(BOGOTA_TZ)
                    fecha_pesaje_neto_local = dt_bogota.strftime('%d/%m/%Y')
                    hora_pesaje_neto_local = dt_bogota.strftime('%H:%M:%S')
                except ValueError as e:
                    current_app.logger.error(f"Error convirtiendo timestamp '{timestamp_utc_str}' para guía {codigo_guia}: {e}")
            
            lista_final.append({
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'nombre_proveedor': nombre_proveedor,
                'fecha_pesaje_neto': fecha_pesaje_neto_local,
                'hora_pesaje_neto': hora_pesaje_neto_local,
                'peso_bruto': peso_bruto, 
                'peso_tara': p_neto.get('peso_tara', "N/A"), 
                'peso_neto': p_neto.get('peso_neto', "N/A"),
                # NUEVO: Añadir los campos al diccionario
                'placa': placa,
                'cantidad_racimos': cantidad_racimos,
                'codigo_sap': codigo_sap
            })
        
        def sort_key(item):
            try:
                date_part = datetime.strptime(item['fecha_pesaje_neto'], '%d/%m/%Y').strftime('%Y-%m-%d')
                return (date_part, item['hora_pesaje_neto'])
            except (ValueError, TypeError):
                return ('0000-00-00', '00:00:00') 

        lista_final.sort(key=sort_key, reverse=True)

        current_app.logger.info(f"Renderizando plantilla con {len(lista_final)} registros de pesaje neto.")
        return render_template(
            'pesaje_neto/lista_pesaje_neto.html',
            pesajes_neto=lista_final,
            filtros={
                'fecha_desde': fecha_desde_str or '', 
                'fecha_hasta': fecha_hasta_str or '', 
                'codigo_proveedor': proveedor_term or ''
            }
        )
    except Exception as e:
        current_app.logger.error(f"Error en lista_pesajes_neto: {str(e)}", exc_info=True)
        flash(f"Error al cargar la lista de pesajes neto: {str(e)}", "danger")
        return redirect(url_for('entrada.home'))


@bp.route('/ver_resultados_pesaje/<codigo_guia>')
@login_required # Añadir protección
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
        guia_sap_db = None
        try:
            # Usar la ruta configurada en la aplicación Flask
            db_path = current_app.config['TIQUETES_DB_PATH']
            conn_check = sqlite3.connect(db_path) 
            cursor_check = conn_check.cursor()
            logger.info(f"Consultando pesajes_bruto en '{db_path}' para {codigo_guia}")
            cursor_check.execute("""
                SELECT peso_bruto, timestamp_pesaje_utc, codigo_guia_transporte_sap 
                FROM pesajes_bruto 
                WHERE codigo_guia = ?
            """, (codigo_guia,))
            pesaje_result = cursor_check.fetchone()
            conn_check.close()

            # --- RESTORE: Initialize local date/time variables --- 
            fecha_pesaje_local = "N/A"
            hora_pesaje_local = "N/A"
            timestamp_utc_str = None

            if pesaje_result:
                peso_bruto_db = pesaje_result[0]
                timestamp_utc_str = pesaje_result[1] # Get UTC timestamp string
                guia_sap_db = pesaje_result[2]       # Get SAP code
                logger.info(f"Pesaje bruto encontrado en DB para {codigo_guia}: Peso={peso_bruto_db}, TimestampUTC={timestamp_utc_str}, SAP={guia_sap_db}")

                # --- RESTORE: Convert timestamp to local --- 
                if timestamp_utc_str:
                    try:
                        dt_utc = datetime.strptime(timestamp_utc_str, "%Y-%m-%d %H:%M:%S")
                        dt_utc = UTC.localize(dt_utc)
                        dt_bogota = dt_utc.astimezone(BOGOTA_TZ)
                        fecha_pesaje_local = dt_bogota.strftime('%d/%m/%Y')
                        hora_pesaje_local = dt_bogota.strftime('%H:%M:%S')
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Could not parse timestamp_pesaje_utc '{timestamp_utc_str}' in pesaje/routes: {e}")
                        # Fallback if needed
                        fecha_pesaje_local = "Err Fmt"
                        hora_pesaje_local = "Err Fmt"

                # Actualizar datos_guia con valores frescos de la DB
                datos_guia['peso_bruto'] = peso_bruto_db
                # --- RESTORE: Use converted local date/time --- 
                datos_guia['fecha_pesaje'] = fecha_pesaje_local
                datos_guia['hora_pesaje'] = hora_pesaje_local
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
            'racimos': datos_guia.get('cantidad_racimos', datos_guia.get('racimos', 'No registrado')),
            'guia_sap': datos_guia.get('codigo_guia_transporte_sap', datos_guia.get('guia_sap', 'No registrada')),
            'imagen_pesaje': imagen_pesaje,
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
@login_required # Añadir protección
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
        # peso_bruto = request.form.get('peso_bruto') # Peso bruto no se usa en la validación inicial
        # tipo_pesaje = request.form.get('tipo_pesaje', 'directo') # Tipo no relevante aquí
        # image_filename = request.form.get('image_filename') # Ya no se espera como form data
        # codigo_sap = request.form.get('codigo_guia_transporte_sap') # Se extrae de la respuesta, no se envía

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

        # Ensure codigo_guia is present before proceeding
        if not codigo_guia:
            logger.error("Código de guía es requerido para procesar pesaje directo.")
            return jsonify({"success": False, "message": "Código de guía es requerido."}), 400

        # --- Inicio: Obtener código de proveedor real ---
        codigo_proveedor_real = None
        try:
            datos_guia = utils.get_datos_guia(codigo_guia)
            if datos_guia:
                # Priorizar 'codigo_proveedor', luego 'codigo'
                codigo_proveedor_real = datos_guia.get('codigo_proveedor', datos_guia.get('codigo'))
                if codigo_proveedor_real:
                     logger.info(f"Código de proveedor recuperado para {codigo_guia}: {codigo_proveedor_real}")
                else:
                     logger.warning(f"No se encontró 'codigo_proveedor' o 'codigo' en datos_guia para {codigo_guia}")
            else:
                 logger.warning(f"No se pudieron obtener datos_guia para {codigo_guia} al buscar código de proveedor.")

            # Fallback: si no se pudo obtener de datos_guia, intentar extraer del codigo_guia
            if not codigo_proveedor_real and '_' in codigo_guia:
                codigo_proveedor_real = codigo_guia.split('_')[0]
                logger.warning(f"Usando código de proveedor extraído del código_guia: {codigo_proveedor_real}")
            elif not codigo_proveedor_real:
                 codigo_proveedor_real = 'desconocido' # O algún valor por defecto si es absolutamente necesario
                 logger.error(f"No se pudo determinar el código de proveedor para {codigo_guia}. Usando '{codigo_proveedor_real}'")

        except Exception as e:
            logger.error(f"Error al obtener datos de guía para extraer código proveedor ({codigo_guia}): {str(e)}")
            codigo_proveedor_real = 'error' # Indicar error en la obtención
        # --- Fin: Obtener código de proveedor real ---
            
        # Guardar imagen temporalmente
        image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
        image_file.save(image_path) # Guardar el archivo cargado
        
        # Enviar al webhook de Make para procesamiento
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            # --- Cambio: Enviar el código de proveedor real ---
            data = {'codigo_proveedor': codigo_proveedor_real}
            logger.info(f"Enviando imagen y código proveedor '{codigo_proveedor_real}' al webhook: {PESAJE_WEBHOOK_URL}")
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
            # --- MEJORA: Añadir log con más detalle en caso de NO Exitoso ---
            logger.error(f"Respuesta NO exitosa del webhook para {codigo_guia} (Proveedor enviado: {codigo_proveedor_real}): {response_text}")
            return jsonify({
                'success': False,
                'message': f"Respuesta no exitosa del webhook: {response_text}" # Mostrar el mensaje de error del webhook al usuario
            })

        # Extraer la guía de transporte SAP
        codigo_guia_transporte_sap = None
        match_guia_sap = re.search(r'Guia de transporte SAP:\s*"?(\d+)"?', response_text, re.IGNORECASE)
        if match_guia_sap:
            codigo_guia_transporte_sap = match_guia_sap.group(1)
            # Guardar en la sesión para su uso posterior
            session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
            logger.info(f"Guía de transporte SAP extraída: {codigo_guia_transporte_sap}")
        else:
             logger.warning(f"No se encontró Guía de transporte SAP en la respuesta exitosa para {codigo_guia}: {response_text}")

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
                logger.error("No se pudo extraer el peso de la respuesta exitosa")
                logger.error(f"Texto de respuesta: {response_text}")
                return jsonify({
                    'success': False,
                    'message': 'Se procesó la imagen pero no se pudo extraer el peso de la respuesta. Verifique la imagen o use el modo manual.'
                })
            
    except Exception as e:
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})


@bp.route('/solicitar_autorizacion_pesaje', methods=['POST'])
@login_required # Añadir protección
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
@login_required # Añadir protección
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


# --- NUEVO ENDPOINT PARA PROCESO PEPA ---
@bp.route('/registrar_y_marcar_pepa', methods=['POST'])
@login_required # Añadir protección
def registrar_y_marcar_pepa():
    """
    Registra el peso bruto para el proceso Pepa y marca la clasificación como completada.
    """
    logger.info("Iniciando registro de peso y marcado de clasificación para Pepa")
    try:
        # Verificar datos recibidos
        codigo_guia = request.form.get('codigo_guia')
        peso_bruto = request.form.get('peso_bruto')
        proceso_pepa = request.form.get('proceso_pepa') == 'true'

        if not codigo_guia or not peso_bruto or not proceso_pepa:
            logger.error(f"Datos incompletos en registrar_y_marcar_pepa: guia={codigo_guia}, peso={peso_bruto}, pepa={proceso_pepa}")
            return jsonify({'success': False, 'message': 'Datos incompletos o proceso no marcado como Pepa'}), 400

        # Procesar imagen adjunta
        imagen_pesaje_rel_path = None
        if 'imagen_pesaje' in request.files:
            foto_bascula = request.files['imagen_pesaje']
            if foto_bascula and foto_bascula.filename:
                try:
                    upload_folder = current_app.config['UPLOAD_FOLDER']
                    # Usar un nombre de archivo consistente con otros pesajes
                    filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
                    filepath_abs = os.path.join(upload_folder, filename)
                    foto_bascula.save(filepath_abs)
                    # Guardar la ruta relativa para la base de datos o template
                    # Asumiendo que UPLOAD_FOLDER es accesible como /static/uploads/
                    static_folder_name = os.path.basename(current_app.static_folder) # 'static'
                    upload_folder_name = os.path.basename(upload_folder) # 'uploads'
                    imagen_pesaje_rel_path = f"{static_folder_name}/{upload_folder_name}/{filename}"
                    logger.info(f"Imagen de báscula Pepa guardada en: {filepath_abs}, ruta relativa: {imagen_pesaje_rel_path}")
                except Exception as img_e:
                     logger.error(f"Error al guardar imagen de pesaje Pepa: {str(img_e)}")
                     # Continuar sin imagen si falla el guardado?
                     imagen_pesaje_rel_path = None 
            else:
                logger.warning("Archivo de imagen de pesaje Pepa vacío o sin nombre")
        else:
             logger.warning("No se recibió archivo 'imagen_pesaje' para Pepa")

        # Generar timestamp UTC
        timestamp_utc = get_utc_timestamp_str()
        
        # Obtener datos existentes de la guía para info de proveedor, etc.
        utils = current_app.config.get('utils', Utils(current_app))
        datos_existentes = utils.get_datos_guia(codigo_guia) or {}
        codigo_proveedor = datos_existentes.get('codigo_proveedor') or datos_existentes.get('codigo')
        nombre_proveedor = datos_existentes.get('nombre_proveedor') or datos_existentes.get('nombre')
        codigo_sap = session.get('codigo_guia_transporte_sap', datos_existentes.get('codigo_guia_transporte_sap', None))
        session.pop('codigo_guia_transporte_sap', None) # Limpiar sesión

        # 1. Guardar el peso bruto en pesajes_bruto
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor or '',
            'nombre_proveedor': nombre_proveedor or '',
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'pepa', # Marcar como tipo 'pepa'
            'timestamp_pesaje_utc': timestamp_utc,
            'imagen_pesaje': imagen_pesaje_rel_path or '',
            'codigo_guia_transporte_sap': codigo_sap
        }
        
        from db_operations import store_pesaje_bruto
        result_peso = store_pesaje_bruto(datos_pesaje)
        if not result_peso:
            logger.error(f"Error al guardar peso bruto Pepa para {codigo_guia}")
            return jsonify({'success': False, 'message': 'Error al guardar el peso bruto'}), 500
        logger.info(f"Peso bruto Pepa registrado para {codigo_guia}")

        # 2. Marcar clasificación como completada (insertando en tabla clasificaciones)
        now_bogota_dt = datetime.now(BOGOTA_TZ)
        fecha_clasificacion_str = now_bogota_dt.strftime('%d/%m/%Y')
        hora_clasificacion_str = now_bogota_dt.strftime('%H:%M:%S')
        
        conn_clasif = None
        try:
            db_path = current_app.config.get('TIQUETES_DB_PATH', DB_PATH) # Usar DB_PATH como fallback
            conn_clasif = sqlite3.connect(db_path)
            cursor_clasif = conn_clasif.cursor()
            
            # Verificar si ya existe una clasificación para evitar duplicados
            cursor_clasif.execute("SELECT COUNT(*) FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
            existe = cursor_clasif.fetchone()[0]
            
            if existe == 0:
                cursor_clasif.execute("""
                    INSERT INTO clasificaciones (codigo_guia, fecha_clasificacion, hora_clasificacion, 
                                               clasificacion_manual, clasificacion_automatica, estado)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (codigo_guia, fecha_clasificacion_str, hora_clasificacion_str, 
                      json.dumps({}), json.dumps({}), 'activo'))
                conn_clasif.commit()
                logger.info(f"Clasificación marcada como completada (registro insertado) para Pepa {codigo_guia}")
            else:
                logger.warning(f"Ya existe una clasificación para {codigo_guia}, no se insertó nuevo registro.")
                # Opcional: podrías actualizar el estado si es necesario
                # cursor_clasif.execute("UPDATE clasificaciones SET estado = ? WHERE codigo_guia = ?", ('activo', codigo_guia))
                # conn_clasif.commit()

        except sqlite3.Error as db_err:
            logger.error(f"Error DB al marcar clasificación Pepa para {codigo_guia}: {db_err}")
            # Decidir si fallar toda la operación o solo loggear el error
            if conn_clasif: conn_clasif.rollback()
            return jsonify({'success': False, 'message': f'Error al marcar clasificación: {db_err}'}), 500
        except Exception as e_clasif:
             logger.error(f"Error inesperado al marcar clasificación Pepa para {codigo_guia}: {e_clasif}")
             if conn_clasif: conn_clasif.rollback()
             return jsonify({'success': False, 'message': f'Error inesperado al marcar clasificación: {e_clasif}'}), 500
        finally:
            if conn_clasif: conn_clasif.close()

        # 3. Generar URL de redirección a resultados
        try:
            redirect_url = url_for('pesaje.ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            logger.info(f"Redirigiendo a la URL de resultados: {redirect_url}")
        except Exception as e_url:
            logger.error(f"Error generando URL de resultados: {str(e_url)}")
            redirect_url = f"/pesaje/ver_resultados_pesaje/{codigo_guia}" # Fallback relativo
            
        return jsonify({
            'success': True,
            'message': 'Peso Pepa registrado y clasificación marcada correctamente.',
            'redirect_url': redirect_url
        })
            
    except Exception as e:
        logger.error(f"Error general en registrar_y_marcar_pepa: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error general al procesar el pesaje Pepa: {str(e)}'
        }), 500
# --- FIN NUEVO ENDPOINT ---


