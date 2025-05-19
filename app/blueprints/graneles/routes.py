from flask import render_template, request, jsonify, url_for, current_app, abort, send_file, make_response, redirect, flash # abort añadido
from flask_login import login_required, current_user
from . import graneles_bp  # Importa el Blueprint desde el __init__.py del mismo paquete
from app.utils.google_sheets_api import find_granel_record_by_placa
import logging
import sqlite3 # Para interactuar con la BD
import os # Para manejo de rutas de archivo
import qrcode # Importar la librería qrcode
from datetime import datetime # Asegurar datetime
import pytz # Para zonas horarias
from weasyprint import HTML, CSS # Importar WeasyPrint
import traceback # Para manejar excepciones
import requests
from werkzeug.utils import secure_filename
import json
import io
import base64

# Configuración de logging
logger = logging.getLogger(__name__)

# Definición de Zonas Horarias
UTC = pytz.utc
BOGOTA_TZ = pytz.timezone('America/Bogota')

def get_db_connection_graneles():
    # Asumimos que tiquetes.db está en la raíz del proyecto
    # y que la configuración de la app tiene TIQUETES_DB_PATH
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
    except KeyError:
        # Fallback si no está en la config, aunque debería estarlo
        db_path = os.path.join(current_app.root_path, '..', 'tiquetes.db')
        current_app.logger.warning(f"TIQUETES_DB_PATH no encontrada en config, usando fallback: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def convertir_timestamp_a_fecha_hora(timestamp_utc_str, formato_salida_fecha='%d/%m/%Y', formato_salida_hora='%H:%M:%S'):
    """Convierte un string timestamp UTC a fecha y hora local (Bogotá) en formatos separados."""
    if not timestamp_utc_str or timestamp_utc_str in [None, '', 'N/A', 'None']: # Manejar 'None' string
        return "N/A", "N/A"
    try:
        # SQLite podría devolver el timestamp como string.
        # Si ya es un objeto datetime, no necesita strptime.
        if isinstance(timestamp_utc_str, datetime):
            dt_utc_naive = timestamp_utc_str
        else:
            # Intentar parsear formatos comunes, incluyendo aquellos con fracciones de segundo
            try:
                dt_utc_naive = datetime.strptime(timestamp_utc_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            except ValueError:
                # Fallback a ISO format si el anterior falla
                dt_utc_naive = datetime.fromisoformat(timestamp_utc_str.replace('Z', '+00:00'))


        if dt_utc_naive.tzinfo is None:
            dt_utc_aware = UTC.localize(dt_utc_naive)
        else:
            dt_utc_aware = dt_utc_naive.astimezone(UTC)

        dt_bogota = dt_utc_aware.astimezone(BOGOTA_TZ)
        return dt_bogota.strftime(formato_salida_fecha), dt_bogota.strftime(formato_salida_hora)
    except Exception as e:
        logger.error(f"Error convirtiendo timestamp '{timestamp_utc_str}': {e}")
        return "Error Fmt.", "Error Fmt."

@graneles_bp.route('/registro_entrada')
@login_required
def registro_entrada():
    """Renderiza la página para el registro de entrada de vehículos de graneles."""
    # render_template buscará 'registro_entrada_graneles.html' en la template_folder definida en graneles_bp
    # (es decir, app/templates/graneles/registro_entrada_graneles.html)
    return render_template('registro_entrada_graneles.html', flask_debug=current_app.debug)

@graneles_bp.route('/buscar_placa_granel', methods=['POST'])
@login_required
def buscar_placa_granel():
    """Busca la información de una placa en Google Sheets y la devuelve como JSON."""
    try:
        data = request.json
        placa = data.get('placa', '').strip().upper()
        if not placa:
            return jsonify({'success': False, 'message': 'La placa no puede estar vacía.'}), 400

        logger.info(f"Buscando placa en Google Sheets: {placa}")
        resultado = find_granel_record_by_placa(placa)

        if resultado:
            logger.info(f"Placa '{placa}' encontrada en Google Sheets: {resultado}")
            return jsonify({'success': True, 'data': resultado})
        else:
            logger.info(f"Placa '{placa}' NO encontrada en Google Sheets.")
            return jsonify({'success': False, 'message': 'Placa no encontrada en el registro de autorizaciones.'})
    except Exception as e:
        logger.error(f"Error en buscar_placa_granel: {e}")
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500

@graneles_bp.route('/guardar_registro_granel', methods=['POST'])
@login_required
def guardar_registro_granel():
    """Guarda los datos del formulario de entrada de graneles en la base de datos."""
    try:
        data = request.form 
        
        producto = data.get('producto')
        fecha_autorizacion = data.get('fecha_autorizacion')
        placa = data.get('placa')
        trailer = data.get('trailer')
        cedula_conductor = data.get('cedula_conductor')
        nombre_conductor = data.get('nombre_conductor')
        origen = data.get('origen')
        destino = data.get('destino')
        tipo_registro = data.get('tipo_registro', 'manual') 
        observaciones = data.get('observacionesGranel')

        usuario_que_registra = current_user.username

        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO RegistroEntradaGraneles 
            (producto, fecha_autorizacion, placa, trailer, cedula_conductor, nombre_conductor, origen, destino, tipo_registro, observaciones, usuario_registro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (producto, fecha_autorizacion, placa, trailer, cedula_conductor, nombre_conductor, origen, destino, tipo_registro, observaciones, usuario_que_registra))
        
        id_insertado = cursor.lastrowid
        conn.commit()
        conn.close()

        logger.info(f"Registro de granel guardado exitosamente para placa '{placa}' con ID: {id_insertado} por usuario: {usuario_que_registra}")
        return jsonify({'success': True, 'message': 'Registro guardado exitosamente.', 'id_registro': id_insertado})

    except sqlite3.Error as e:
        logger.error(f"Error de base de datos al guardar registro de granel: {e} - Data: {request.form}")
        return jsonify({'success': False, 'message': f'Error de base de datos: {e}'}), 500
    except Exception as e:
        logger.error(f"Error inesperado al guardar registro de granel: {e} - Data: {request.form}")
        return jsonify({'success': False, 'message': f'Error inesperado: {e}'}), 500

# --- INICIO: Lógica de QR y vista de detalle --- 
def generar_y_guardar_qr_granel(id_registro_granel):
    """Genera y guarda un código QR para un registro de granel específico.
       Devuelve un diccionario con 'path' (ruta relativa del archivo QR) y 'url' (URL completa del QR).
       Retorna None si hay un error.
    """
    try:
        qr_folder_name = 'graneles'
        qr_base_path = os.path.join(current_app.static_folder, 'qr', qr_folder_name)
        os.makedirs(qr_base_path, exist_ok=True)

        qr_filename = f"granel_qr_{id_registro_granel}.png"
        qr_filepath_absolute = os.path.join(qr_base_path, qr_filename)
        qr_filepath_relative = os.path.join('qr', qr_folder_name, qr_filename) 

        url_guia = url_for('graneles.vista_guia_centralizada_granel', id_registro_granel=id_registro_granel, _external=True)
        
        # Solo generar si no existe para evitar regenerar innecesariamente
        if not os.path.exists(qr_filepath_absolute):
            qr_img = qrcode.make(url_guia)
            qr_img.save(qr_filepath_absolute)
            logger.info(f"Código QR generado para granel ID {id_registro_granel} en {qr_filepath_absolute}")
        
        return {"path": qr_filepath_relative, "url": url_guia}
    except Exception as e:
        logger.error(f"Error generando QR para granel ID {id_registro_granel}: {e}")
        return None

@graneles_bp.route('/guia/<int:id_registro_granel>')
@login_required
def vista_detalle_granel(id_registro_granel):
    """Muestra los detalles de un registro de granel específico y su QR."""
    conn = None
    try:
        conn = get_db_connection_graneles()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM RegistroEntradaGraneles WHERE id = ?", (id_registro_granel,))
        registro = cursor.fetchone()

        if not registro:
            flash(f'Registro de granel con ID {id_registro_granel} no encontrado.', 'error')
            return redirect(url_for('graneles.registro_entrada')) # O a alguna lista si la tienes

        datos_granel = dict(registro) # Convertir sqlite3.Row a dict

        # Formatear fecha y hora del registro para mostrar
        fecha_reg_local, hora_reg_local = "N/A", "N/A"
        if datos_granel.get('timestamp_registro'):
            fecha_reg_local, hora_reg_local = convertir_timestamp_a_fecha_hora(datos_granel['timestamp_registro'])
        datos_granel['fecha_registro_fmt'] = fecha_reg_local
        datos_granel['hora_registro_fmt'] = hora_reg_local

        # Generar QR y obtener su ruta relativa y la URL completa de los datos del QR
        qr_info = generar_y_guardar_qr_granel(id_registro_granel)
        if qr_info:
            datos_granel['qr_code_path'] = qr_info.get('path')
            datos_granel['qr_url'] = qr_info.get('url')
        else:
            datos_granel['qr_code_path'] = None
            datos_granel['qr_url'] = None
            logger.error(f"No se pudo obtener información del QR para granel ID {id_registro_granel}")

        current_app.logger.info(f"Mostrando detalles para registro de granel ID: {id_registro_granel}. Datos: {datos_granel}")
        
        return render_template('detalle_registro_granel.html', 
                               datos_granel=datos_granel,
                               current_timestamp=datetime.now().timestamp() # Añadir timestamp para cache busting
                              )

    except sqlite3.Error as e:
        logger.error(f"Error de base de datos al obtener registro de granel ID {id_registro_granel}: {e}")
        abort(500, description="Error interno del servidor al consultar la base de datos.")
    except Exception as e:
        logger.error(f"Error inesperado al obtener detalles de granel ID {id_registro_granel}: {e}")
        abort(500, description="Error inesperado del servidor.")
# --- FIN: Lógica de QR y vista de detalle --- 

# --- NUEVA RUTA PARA GENERAR PDF DE GRANEL ---
@graneles_bp.route('/generar_pdf/<int:id_registro_granel>')
@login_required
def generar_pdf_granel(id_registro_granel):
    """Genera un PDF para un registro de granel específico y lo ofrece para descarga."""
    conn = None
    try:
        conn = get_db_connection_graneles()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM RegistroEntradaGraneles WHERE id = ?", (id_registro_granel,))
        registro_granel = cursor.fetchone()

        if not registro_granel:
            logger.warning(f"PDF: No se encontró el registro de granel con ID: {id_registro_granel}")
            abort(404, description="Registro de granel no encontrado para generar PDF.")

        datos_granel = dict(registro_granel)

        if 'fecha_registro_fmt' not in datos_granel or 'hora_registro_fmt' not in datos_granel:
            fecha_reg, hora_reg = convertir_timestamp_a_fecha_hora(datos_granel.get('timestamp_registro'))
            datos_granel['fecha_registro_fmt'] = fecha_reg
            datos_granel['hora_registro_fmt'] = hora_reg
        
        qr_info = generar_y_guardar_qr_granel(id_registro_granel)
        if qr_info and qr_info['path']:
            datos_granel['qr_url'] = qr_info['url'] # Para mostrar en el PDF
            qr_absolute_path = os.path.join(current_app.static_folder, qr_info['path'])
            datos_granel['qr_code_path_absolute'] = "file://" + qr_absolute_path.replace('\\', '/')
        else:
            logger.warning(f"PDF: No se pudo generar/encontrar QR para granel ID {id_registro_granel}")
            datos_granel['qr_code_path_absolute'] = None
            datos_granel['qr_url'] = None

        html_string = render_template('pdf_template_granel.html', datos_granel=datos_granel)
        pdf_bytes = HTML(string=html_string, base_url=current_app.config['BASE_DIR']).write_pdf()

        pdf_folder = os.path.join(current_app.static_folder, 'pdfs', 'graneles')
        os.makedirs(pdf_folder, exist_ok=True)
        pdf_filename = f"granel_registro_{id_registro_granel}.pdf"
        pdf_filepath = os.path.join(pdf_folder, pdf_filename)
        with open(pdf_filepath, 'wb') as f:
            f.write(pdf_bytes)
        logger.info(f"PDF para granel ID {id_registro_granel} guardado en {pdf_filepath}")

        response = make_response(pdf_bytes)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={pdf_filename}'
        return response

    except sqlite3.Error as e:
        logger.error(f"PDF: Error de BD generando PDF para granel ID {id_registro_granel}: {e}")
        abort(500, description=f"Error de BD generando PDF: {e}")
    except Exception as e:
        logger.error(f"PDF: Error inesperado generando PDF para granel ID {id_registro_granel}: {e}")
        logger.error(traceback.format_exc())
        abort(500, description=f"Error inesperado generando PDF: {e}")
    finally:
        if conn:
            conn.close()

@graneles_bp.route('/guia-centralizada/<int:id_registro_granel>')
@login_required
def vista_guia_centralizada_granel(id_registro_granel):
    """
    Muestra la vista centralizada del proceso para un registro de granel.
    """
    conn = None
    try:
        conn = get_db_connection_graneles()
        cursor = conn.cursor()
        
        # Obtener datos del registro de entrada
        cursor.execute("SELECT * FROM RegistroEntradaGraneles WHERE id = ?", (id_registro_granel,))
        registro_granel = cursor.fetchone()

        if not registro_granel:
            flash('Registro de granel no encontrado.', 'error')
            return redirect(url_for('graneles.registro_entrada'))

        datos_guia = dict(registro_granel)

        fecha_reg_local, hora_reg_local = "N/A", "N/A"
        if datos_guia.get('timestamp_registro'):
            fecha_reg_local, hora_reg_local = convertir_timestamp_a_fecha_hora(datos_guia['timestamp_registro'])
        datos_guia['fecha_registro_fmt'] = fecha_reg_local
        datos_guia['hora_registro_fmt'] = hora_reg_local
        
        # Obtener datos del primer pesaje (NUEVO)
        cursor.execute("SELECT * FROM PrimerPesajeGranel WHERE id_registro_granel = ? ORDER BY timestamp_primer_pesaje DESC LIMIT 1", (id_registro_granel,))
        primer_pesaje_db = cursor.fetchone()
        datos_primer_pesaje = None
        if primer_pesaje_db:
            datos_primer_pesaje = dict(primer_pesaje_db)
            fecha_pesaje, hora_pesaje = convertir_timestamp_a_fecha_hora(datos_primer_pesaje['timestamp_primer_pesaje'])
            datos_primer_pesaje['fecha_pesaje_fmt'] = fecha_pesaje
            datos_primer_pesaje['hora_pesaje_fmt'] = hora_pesaje
            if datos_primer_pesaje.get('foto_soporte_path'):
                datos_primer_pesaje['foto_soporte_url'] = url_for('static', filename=datos_primer_pesaje['foto_soporte_path'])


        qr_info = generar_y_guardar_qr_granel(id_registro_granel)
        
        qr_img_rel_path = None
        qr_data_url = None
        if qr_info:
            qr_img_rel_path = qr_info.get('path')
            qr_data_url = qr_info.get('url')
        else:
            logger.error(f"No se pudo obtener información del QR para granel ID {id_registro_granel} en guía centralizada.")

        qr_url_para_template = None
        if qr_img_rel_path:
            qr_url_para_template = url_for('static', filename=qr_img_rel_path)

        current_app.logger.info(f"Vista Guía Centralizada para Granel ID: {id_registro_granel}. QR Path: {qr_img_rel_path}, QR Data URL: {qr_data_url}, QR Template URL: {qr_url_para_template}")

        return render_template(
            'guia_centralizada_graneles.html',
            datos_guia=datos_guia,
            datos_primer_pesaje=datos_primer_pesaje, # <-- NUEVO
            qr_url=qr_url_para_template,
            qr_url_completa=qr_data_url,
            current_timestamp=datetime.now().timestamp()
        )

    except sqlite3.Error as e:
        current_app.logger.error(f"Error de base de datos en vista_guia_centralizada_granel para ID {id_registro_granel}: {e}")
        flash('Error al acceder a los datos del registro de granel.', 'error')
        return redirect(url_for('graneles.registro_entrada'))
    except Exception as e:
        current_app.logger.error(f"Error inesperado en vista_guia_centralizada_granel para ID {id_registro_granel}: {e}")
        flash('Ocurrió un error inesperado al mostrar la guía centralizada.', 'error')
        return redirect(url_for('graneles.registro_entrada'))
    finally:
        if conn:
            conn.close()

# --- NUEVA RUTA PARA VALIDAR FOTO DE PESAJE CON BASCULA EXTERNA ---
@graneles_bp.route('/validar_foto_pesaje/<int:id_registro_granel>', methods=['POST'])
@login_required
def validar_foto_pesaje(id_registro_granel):
    """Recibe una foto y datos, llama al webhook de validación y devuelve el resultado."""
    logger.info(f"Recibida solicitud para validar foto de pesaje para ID: {id_registro_granel}")

    # 1. Verificar si se recibió la foto
    if 'foto' not in request.files:
        logger.warning("No se encontró el archivo 'foto' en la solicitud.")
        return jsonify({'success': False, 'message': 'No se envió ninguna foto.'}), 400

    foto = request.files['foto']

    if foto.filename == '':
        logger.warning("El nombre del archivo de la foto está vacío.")
        return jsonify({'success': False, 'message': 'Nombre de archivo de foto vacío.'}), 400

    # 2. Obtener otros datos del formulario (se envían junto con la foto)
    placa = request.form.get('placa')
    conductor = request.form.get('conductor')
    producto = request.form.get('producto')
    trailer = request.form.get('trailer')

    logger.debug(f"Datos recibidos para validación: Placa={placa}, Conductor={conductor}, Producto={producto}, Trailer={trailer}")

    # Aunque el formulario JS los pide, el webhook podría no necesitarlos todos.
    # No haremos que la validación falle aquí si faltan, pero sí loggearemos.
    if not all([placa, conductor, producto, trailer]):
        logger.warning(f"Algunos datos textuales pueden faltar en la solicitud de validación para el webhook: {request.form}")
        pass # Continuar si al menos la foto está

    # 3. Guardar la imagen 
    upload_folder = os.path.join(current_app.static_folder, 'uploads', 'graneles', 'pesajes')
    os.makedirs(upload_folder, exist_ok=True)
    
    # Crear un nombre de archivo seguro y único
    timestamp_str = datetime.now().strftime('%Y%m%d%H%M%S%f')
    base_filename = secure_filename(foto.filename if foto.filename else 'foto_pesaje')
    filename = f"pesaje_{id_registro_granel}_{timestamp_str}_{base_filename}.jpg" 
    # Limitar longitud del nombre de archivo por si acaso
    max_len = 100
    if len(filename) > max_len:
        name, ext = os.path.splitext(filename)
        filename = name[:max_len - len(ext) -1] + ext
        
    filepath_absolute = os.path.join(upload_folder, filename)
    # Ruta relativa para guardar en BD y usar en URL
    filepath_relative = os.path.join('uploads', 'graneles', 'pesajes', filename).replace('\\', '/') 

    try:
        foto.save(filepath_absolute)
        logger.info(f"Foto de soporte para validación guardada en: {filepath_absolute}")
    except Exception as e:
        logger.error(f"Error guardando la foto de soporte para validación: {e}")
        return jsonify({'success': False, 'message': 'Error al guardar la imagen de soporte para validación.'}), 500

    # 4. Llamar al Webhook de Validación
    webhook_url = "https://primary-production-6eccf.up.railway.app/webhook/782f58fe-6037-4c23-87a2-bf402faf9766"
    files_for_webhook = None
    payload_for_webhook = {
        'placa': placa,
        'conductor': conductor,
        'producto': producto,
        'trailer': trailer,
        'id_registro': id_registro_granel
    }

    logger.info(f"Llamando al webhook de validación: {webhook_url} con payload: {payload_for_webhook}")

    try:
        # Abrir el archivo en modo binario para enviarlo
        with open(filepath_absolute, 'rb') as f_bytes:
            files_for_webhook = {'foto_vehiculo': (filename, f_bytes, foto.content_type)}
            response = requests.post(webhook_url, files=files_for_webhook, data=payload_for_webhook, timeout=30) # Timeout de 30s
        
        response.raise_for_status() 

        webhook_response_data = response.json()
        logger.info(f"Respuesta del webhook de validación: {webhook_response_data}")

        # 5. Procesar la respuesta del Webhook
        text_response = webhook_response_data.get('text')

        if text_response:
            logger.info(f"Procesando respuesta de texto del webhook: {text_response}")
            # Parsear la respuesta de texto
            parsed_data = {}
            for line in text_response.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if ':' in line:
                    key, value = line.split(':', 1)
                    parsed_data[key.strip()] = value.strip()
            
            logger.info(f"Datos parseados del texto: {parsed_data}")

            # Obtener valores de forma más robusta y loguearlos
            peso_kg_raw = parsed_data.get('Peso Tara')
            # Intentar obtener la guía con y sin tilde
            codigo_sap_raw = parsed_data.get('Guía de transporte') 
            if codigo_sap_raw is None:
                logger.warning("No se encontró 'Guía de transporte' con tilde, intentando con 'Guia de transporte' sin tilde.")
                codigo_sap_raw = parsed_data.get('Guia de transporte')
            
            logger.info(f"Valor extraído para 'Peso Tara': '{peso_kg_raw}' (Tipo: {type(peso_kg_raw)})")
            logger.info(f"Valor final para 'Guia/Guía de transporte': '{codigo_sap_raw}' (Tipo: {type(codigo_sap_raw)})")

            nota = parsed_data.get('Nota', '')
            equipo_status = parsed_data.get('Equipo', '')

            is_success = "no valido" not in equipo_status.lower() and "no coincide" not in nota.lower()
            
            if not is_success:
                logger.warning(f"Validación marcada como NO exitosa. Equipo: '{equipo_status}', Nota: '{nota}'")

            if peso_kg_raw is None or codigo_sap_raw is None:
                logger.error(f"No se pudieron extraer Peso Tara o Guía de transporte del texto. Datos parseados: {parsed_data}")
                return jsonify({'success': False, 'message': 'Respuesta incompleta del servicio de validación (faltan peso o guía en el texto).'}), 500
            
            try:
                peso_kg_str_cleaned = str(peso_kg_raw).upper().replace('KG','').strip()
                peso_kg_float = float(peso_kg_str_cleaned)
            except (ValueError, TypeError):
                logger.error(f"Texto del webhook devolvió un peso no numérico: {peso_kg_raw}")
                return jsonify({'success': False, 'message': f'El servicio de validación devolvió un peso inválido en el texto: {peso_kg_raw}.'}), 500

            message_to_return = nota
            if is_success:
                if not nota:
                    message_to_return = 'Validación de texto exitosa.'
            elif not nota:
                message_to_return = "Error en la validación de datos del vehículo."

            return jsonify({
                'success': is_success,
                'peso_kg': peso_kg_float,
                'codigo_sap_granel': str(codigo_sap_raw),
                'ruta_imagen_soporte': filepath_relative, 
                'message': message_to_return
            })

        elif webhook_response_data.get('status') == 'success' or webhook_response_data.get('success'):
            peso_kg_raw = webhook_response_data.get('peso_kg') or webhook_response_data.get('peso')
            codigo_sap = webhook_response_data.get('codigo_sap_granel') or webhook_response_data.get('codigo_sap')

            if peso_kg_raw is None or codigo_sap is None:
                logger.error(f"Webhook devolvió éxito pero faltan datos clave: peso_raw={peso_kg_raw}, sap={codigo_sap}")
                return jsonify({'success': False, 'message': 'Respuesta incompleta del servicio de validación (faltan peso o SAP).'}), 500
            
            try:
                peso_kg_str_cleaned = str(peso_kg_raw).upper().replace('KG','').strip()
                peso_kg_float = float(peso_kg_str_cleaned)
            except (ValueError, TypeError):
                logger.error(f"Webhook devolvió un peso no numérico o no convertible: {peso_kg_raw} (limpio: {peso_kg_str_cleaned if 'peso_kg_str_cleaned' in locals() else 'N/A'})")
                return jsonify({'success': False, 'message': f'El servicio de validación devolvió un peso inválido: {peso_kg_raw}.'}), 500

            return jsonify({
                'success': True,
                'peso_kg': peso_kg_float,
                'codigo_sap_granel': str(codigo_sap),
                'ruta_imagen_soporte': filepath_relative, 
                'message': webhook_response_data.get('message', 'Validación exitosa.')
            })
        else:
            error_message = webhook_response_data.get('message', 'Error desconocido desde el servicio de validación (formato no reconocido).')
            logger.error(f"El webhook de validación devolvió un error o formato no reconocido: {error_message}. Respuesta completa: {webhook_response_data}")
            return jsonify({'success': False, 'message': f'Validación fallida: {error_message}'}), 500

    except requests.exceptions.Timeout:
        logger.error(f"Timeout llamando al webhook de validación: {webhook_url}")
        return jsonify({'success': False, 'message': 'El servicio de validación tardó demasiado en responder.'}), 504 # Gateway Timeout
    except requests.exceptions.RequestException as e:
        logger.error(f"Error de conexión llamando al webhook de validación: {e}")
        return jsonify({'success': False, 'message': 'Error de conexión con el servicio de validación externo.'}), 502 # Bad Gateway
    except json.JSONDecodeError:
        logger.error(f"Error decodificando respuesta JSON del webhook. Status: {response.status_code}, Respuesta: {response.text[:500]}")
        return jsonify({'success': False, 'message': 'Respuesta inválida (no JSON) del servicio de validación.'}), 500
    except Exception as e:
        logger.error(f"Error inesperado durante la validación de foto: {e}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': 'Error interno del servidor durante la validación.'}), 500
    # No es necesario el finally para cerrar el archivo si se usa 'with open'
# --- FIN RUTA VALIDACIÓN ---

# --- RUTA PARA REGISTRAR EL PRIMER PESAJE (MODIFICADA PARA NUEVO FLUJO) ---
@graneles_bp.route('/registrar-primer-pesaje/<int:id_registro_granel>', methods=['GET', 'POST'])
@login_required
def registrar_primer_pesaje_granel(id_registro_granel):
    conn = get_db_connection_graneles()
    cursor = conn.cursor()
    cursor.execute("SELECT id, placa, producto, nombre_conductor, trailer FROM RegistroEntradaGraneles WHERE id = ?", (id_registro_granel,))
    registro_entrada = cursor.fetchone()

    if not registro_entrada:
        flash('Registro de entrada de granel no encontrado.', 'error')
        return redirect(url_for('graneles.registro_entrada')) # Redirige si no encuentra el registro

    datos_entrada_dict = dict(registro_entrada)

    if request.method == 'POST':
        peso_primer_kg_str = request.form.get('peso_primer_kg')
        codigo_sap_granel = request.form.get('codigo_sap_granel') # Nuevo campo del form
        ruta_imagen_validada = request.form.get('ruta_imagen_validada') # Nuevo campo del form (path relativo desde static)
        foto_nueva = request.files.get('foto_nueva') # Campo para una foto subida directamente al guardar

        logger.info(f"Datos POST recibidos para registrar pesaje ID {id_registro_granel}: "
                    f"Peso='{peso_primer_kg_str}', SAP='{codigo_sap_granel}', "
                    f"RutaValidada='{ruta_imagen_validada}', "
                    f"FotoNueva?={'Sí' if foto_nueva else 'No'}")

        if not peso_primer_kg_str or not codigo_sap_granel:
            flash('Faltan datos esenciales (peso validado o código SAP). Por favor, valide la foto primero.', 'warning')
            # Renderizar de nuevo el formulario con los datos GET
            return render_template('registrar_primer_pesaje.html',
                                   id_registro_granel=id_registro_granel,
                                   datos_entrada=datos_entrada_dict)

        try:
            peso_primer_kg = float(peso_primer_kg_str)
        except ValueError:
            flash('El valor del peso no es válido.', 'error')
            # Renderizar de nuevo el formulario con los datos GET
            return render_template('registrar_primer_pesaje.html',
                                   id_registro_granel=id_registro_granel,
                                   datos_entrada=datos_entrada_dict)

        # --- Lógica para determinar la ruta de la imagen a guardar ---
        foto_path_para_db = None
        if foto_nueva and foto_nueva.filename != '':
            # Si se sube una NUEVA foto al guardar, se usa esa
            logger.info("Se subió una foto nueva al momento de guardar.")
            try:
                # Crear una estructura similar a FileStorage si viene de base64
                if isinstance(foto_nueva, str) and foto_nueva.startswith('data:image'):
                    header, encoded = foto_nueva.split(',', 1)
                    file_ext = header.split(';')[0].split('/')[1]
                    file_data = base64.b64decode(encoded)
                    temp_filename = f"captura_pantalla_{id_registro_granel}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file_ext}"

                    # Simular FileStorage para la función save
                    class SimpleFileStorage:
                        def __init__(self, stream, filename, content_type=f'image/{file_ext}'):
                            self.stream = io.BytesIO(stream)
                            self.filename = filename
                            self.content_type = content_type

                        def save(self, dst):
                            with open(dst, 'wb') as f:
                                f.write(self.stream.read())

                        def __bool__(self):
                            return bool(self.filename)


                    foto_nueva = SimpleFileStorage(file_data, temp_filename)
                    logger.info(f"Se procesó imagen base64 como: {temp_filename}")


                upload_folder_pesajes = os.path.join(current_app.static_folder, 'uploads', 'graneles', 'pesajes')
                os.makedirs(upload_folder_pesajes, exist_ok=True)

                timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
                # Usar secure_filename para seguridad
                base_filename, file_extension = os.path.splitext(secure_filename(foto_nueva.filename))
                final_filename = f"pesaje1_{id_registro_granel}_{timestamp_str}{file_extension}"
                filepath_absolute = os.path.join(upload_folder_pesajes, final_filename)

                # Guardar la nueva foto
                try: # Bloque try para la operación de guardado
                    foto_nueva.save(filepath_absolute)
                    # CORRECCIÓN: Escapar correctamente la barra invertida
                    foto_path_para_db = os.path.join('uploads', 'graneles', 'pesajes', final_filename).replace('\\', '/')
                    logger.info(f"Nueva foto de soporte guardada en: {filepath_absolute} (DB path: {foto_path_para_db})")
                except Exception as e_save:
                    logger.error(f"Error guardando nueva foto de soporte: {e_save}")
                    flash(f"Error al guardar la nueva imagen de soporte: {e_save}", "error")
                    # Continuar sin foto o manejar el error como crítico? Por ahora continuamos.
                    foto_path_para_db = None # No se guarda la ruta si falla


            except Exception as e_proc_foto:
                 logger.error(f"Error procesando la foto nueva: {e_proc_foto}")
                 flash(f"Error al procesar la imagen: {e_proc_foto}", "error")
                 foto_path_para_db = None

        elif ruta_imagen_validada:
            # Si no hay foto nueva, pero sí una ruta validada, se usa esa
            logger.info(f"Usando ruta de imagen validada previamente: {ruta_imagen_validada}")
            # Asume que ruta_imagen_validada ya es relativa a 'static/'
            foto_path_para_db = ruta_imagen_validada
        else:
            # Si no hay ni foto nueva ni ruta validada, no se guarda ruta
            logger.warning("No se proporcionó foto nueva ni ruta de imagen validada. No se guardará soporte fotográfico.")
            foto_path_para_db = None


        # --- Inserción en la base de datos ---
        try:
            cursor.execute("""
                INSERT INTO PrimerPesajeGranel
                (id_registro_granel, peso_primer_kg, codigo_sap_granel, usuario_pesaje, foto_soporte_path, timestamp_primer_pesaje)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                id_registro_granel,
                peso_primer_kg,
                codigo_sap_granel,
                current_user.username,
                foto_path_para_db, # Puede ser None
                datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S") # MODIFICADO AQUÍ: Usar UTC
            ))
            conn.commit()
            flash('Primer pesaje registrado exitosamente.', 'success')
            logger.info(f"Primer pesaje para ID {id_registro_granel} guardado correctamente por {current_user.username}.")
            # Redirigir a la guía centralizada después de guardar
            return redirect(url_for('graneles.vista_guia_centralizada_granel', id_registro_granel=id_registro_granel))

        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Error al guardar el primer pesaje en la BD para ID {id_registro_granel}: {e}")
            flash(f'Error al guardar en la base de datos: {e}', 'error')
            # Renderizar de nuevo el formulario con los datos GET en caso de error de BD
            return render_template('registrar_primer_pesaje.html',
                                   id_registro_granel=id_registro_granel,
                                   datos_entrada=datos_entrada_dict)
        finally:
            if conn:
                conn.close()

    # Método GET: Renderizar el formulario inicial
    else:
        # Verificar si ya existe un pesaje para esta guía
        cursor.execute("SELECT id FROM PrimerPesajeGranel WHERE id_registro_granel = ?", (id_registro_granel,))
        pesaje_existente = cursor.fetchone()
        if conn: # Cerrar conexión después de la consulta GET
            conn.close()

        if pesaje_existente:
            flash('Ya existe un primer pesaje registrado para esta guía.', 'info')
            # Podrías redirigir a la guía centralizada o mostrar la página deshabilitada
            return redirect(url_for('graneles.vista_guia_centralizada_granel', id_registro_granel=id_registro_granel))

        return render_template('registrar_primer_pesaje.html',
                               id_registro_granel=id_registro_granel,
                               datos_entrada=datos_entrada_dict)
