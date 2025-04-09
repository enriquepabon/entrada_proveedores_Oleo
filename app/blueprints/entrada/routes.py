from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import logging
import traceback
from datetime import datetime
import json
import requests
import qrcode
import time
import sqlite3
from weasyprint import HTML
from concurrent.futures import ThreadPoolExecutor
from app.blueprints.entrada import bp
from app.utils.common import CommonUtils as Utils
from app.blueprints.misc.routes import PROCESS_WEBHOOK_URL, PLACA_WEBHOOK_URL, REVALIDATION_WEBHOOK_URL, REGISTER_WEBHOOK_URL
import glob
from app.utils.image_processing import process_plate_image
import db_utils  # Importar db_utils para operaciones de base de datos
import db_operations  # Importar db_operations
from tiquete_parser import parse_markdown_response
import pytz

# Configurar logging
logger = logging.getLogger(__name__)

# Definir zona horaria de Bogotá
BOGOTA_TZ = pytz.timezone('America/Bogota')

def get_bogota_datetime():
    """
    Obtiene la fecha y hora actual en la zona horaria de Bogotá.
    Returns:
        tuple: (fecha_str, hora_str) en formato DD/MM/YYYY y HH:MM:SS
    """
    now_utc = datetime.now(pytz.UTC)
    now_bogota = now_utc.astimezone(BOGOTA_TZ)
    return now_bogota.strftime('%d/%m/%Y'), now_bogota.strftime('%H:%M:%S')

@bp.route('/index')
def index():
    """
    Renders the index page
    """
    return render_template('index.html')



@bp.route('/home')
def home():
    """
    Renders the home page - dashboard for all app sections
    """
    return render_template('home.html')



@bp.route('/processing')
def processing():
    image_filename = session.get('image_filename')
    if not image_filename:
        return render_template('error.html', message="No se encontró una imagen para procesar.")
    return render_template('entrada/processing.html')



@bp.route('/process_image', methods=['POST'])
def process_image():
    try:
        # Verificar si hay datos en la sesión
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        
        logger.info(f"Iniciando procesamiento de imagen: {image_filename}")
        
        if not image_filename:
            logger.error("No se encontró imagen en la sesión")
            return jsonify({"result": "error", "message": "No se encontró una imagen para procesar."}), 400
        
        # Verificar si la imagen existe en el sistema de archivos
        upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(os.getcwd(), 'static', 'uploads'))
        image_path = os.path.join(upload_folder, image_filename)
        
        logger.info(f"Buscando imagen en: {image_path}")
        
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return jsonify({"result": "error", "message": f"Archivo no encontrado: {image_filename}"}), 404
        
        # Procesar imagen del tiquete y placa en paralelo
        tiquete_future = None
        placa_future = None
        tiquete_result = None
        placa_result = None
        
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                # Iniciar procesamiento del tiquete
                tiquete_future = executor.submit(process_tiquete_image, image_path, image_filename)
                
                # Iniciar procesamiento de la placa si existe
                if plate_image_filename:
                    plate_path = os.path.join(upload_folder, plate_image_filename)
                    if os.path.exists(plate_path):
                        placa_future = executor.submit(process_plate_image, plate_path, plate_image_filename)
            
            # Obtener resultados
            tiquete_result = tiquete_future.result() if tiquete_future else {"result": "error", "message": "Error procesando tiquete"}
            placa_result = placa_future.result() if placa_future else {"result": "warning", "message": "No se procesó imagen de placa"}
        except Exception as e:
            logger.error(f"Error en el procesamiento paralelo: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"result": "error", "message": f"Error en el procesamiento: {str(e)}"}), 500
        
        # Verificar resultado del tiquete
        if tiquete_result.get("result") == "error":
            error_msg = tiquete_result.get('message', "Error en el procesamiento del tiquete")
            logger.error(f"Error en el procesamiento del tiquete: {error_msg}")
            return jsonify({"result": "error", "message": error_msg}), 400
        
        # Manejar el caso de advertencia (imagen no es un tiquete válido)
        if tiquete_result.get("result") == "warning":
            logger.warning(f"Advertencia en el procesamiento: {tiquete_result.get('message')}")
            try:
                session['parsed_data'] = tiquete_result.get("parsed_data", {})
                session['warning_message'] = tiquete_result.get("message")
                logger.info(f"Datos de advertencia guardados en sesión")
                return jsonify({
                    "result": "warning", 
                    "message": tiquete_result.get("message"),
                    "redirect": url_for('entrada.review')
                })
            except Exception as e:
                logger.error(f"Error al guardar datos de advertencia en sesión: {str(e)}")
                logger.error(traceback.format_exc())
                return jsonify({"result": "error", "message": f"Error al guardar datos en sesión: {str(e)}"}), 500
        
        # Guardar resultados en sesión
        try:
            session['parsed_data'] = tiquete_result.get("parsed_data", {})
            logger.info(f"Datos parseados guardados en sesión: {session['parsed_data']}")
            
            if placa_result and placa_result.get("result") != "error":
                session['plate_text'] = placa_result.get("plate_text")
                logger.info(f"Texto de placa guardado en sesión: {session['plate_text']}")
            elif placa_result:
                session['plate_error'] = placa_result.get("message")
                logger.warning(f"Error en placa guardado en sesión: {session['plate_error']}")
            
            return jsonify({"result": "ok", "redirect": url_for('entrada.review')})
        except Exception as e:
            logger.error(f"Error al guardar datos en sesión: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({"result": "error", "message": f"Error al guardar datos en sesión: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "result": "error", 
            "message": f"Error al procesar la imagen: {str(e)}"
        }), 500

def process_tiquete_image(image_path, filename):
    try:
        logger.info(f"Enviando imagen {filename} al webhook {PROCESS_WEBHOOK_URL}")
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            try:
                response = requests.post(PROCESS_WEBHOOK_URL, files=files, timeout=30)
                
                logger.info(f"Respuesta del webhook: Status {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
                
                if response.status_code != 200:
                    error_msg = f"Error del webhook de tiquete (código {response.status_code}): {response.text}"
                    logger.error(error_msg)
                    return {"result": "error", "message": error_msg}
                    
                response_text = response.text.strip()
                # Registra la respuesta raw del webhook para debugging
                logger.info(f"Respuesta raw del webhook de tiquete: {response_text}")
                
                if not response_text:
                    logger.error("Respuesta vacía del webhook de tiquete")
                    return {"result": "error", "message": "Respuesta vacía del webhook de tiquete."}
            except requests.exceptions.RequestException as e:
                error_msg = f"Error de conexión con el webhook: {str(e)}"
                logger.error(error_msg)
                logger.error(traceback.format_exc())
                return {"result": "error", "message": error_msg}
        
        # Importar la función de parser.py
        from tiquete_parser import parse_markdown_response
        
        parsed_data = parse_markdown_response(response_text)
        
        # Verificar si los datos parseados son válidos
        if not parsed_data:
            error_msg = "No se pudieron extraer datos de la imagen. Respuesta del webhook no válida."
            logger.error(error_msg)
            logger.error(f"Datos parseados: {parsed_data}")
            return {"result": "error", "message": error_msg}
        
        # Si tenemos una descripción pero no datos de tabla, es una imagen que no es un tiquete
        if parsed_data.get('descripcion') and not parsed_data.get('table_data'):
            logger.info("La imagen no es un tiquete válido, pero se obtuvo una descripción")
            return {
                "result": "warning",
                "parsed_data": parsed_data,
                "message": "La imagen no parece ser un tiquete válido. Se muestra una descripción general."
            }
        
        # Si no tenemos ni descripción ni datos de tabla, hay un problema
        if not parsed_data.get('table_data') and not parsed_data.get('descripcion'):
            error_msg = "No se pudieron extraer datos del tiquete. Formato de respuesta no reconocido."
            logger.error(error_msg)
            logger.error(f"Datos parseados: {parsed_data}")
            return {"result": "error", "message": error_msg}
        
        return {
            "result": "ok",
            "parsed_data": parsed_data
        }
    except Exception as e:
        error_msg = f"Error procesando imagen de tiquete: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return {"result": "error", "message": error_msg}

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



@bp.route('/review', methods=['GET'])
def review():
    parsed_data = session.get('parsed_data', {})
    image_filename = session.get('image_filename', '')
    plate_image_filename = session.get('plate_image_filename', '')
    plate_text = session.get('plate_text', '')
    plate_error = session.get('plate_error', '')
    
    if not parsed_data or not image_filename:
        return render_template('error.html', message="No hay datos para revisar.")
    
    if 'table_data' not in parsed_data:
        logger.error("Formato de datos incorrecto")
        return render_template('error.html', message="Error en el formato de los datos.")
    
    timestamp = datetime.now().timestamp()
    
    return render_template(
        'entrada/review.html',
        image_filename=image_filename,
        parsed_data=parsed_data,
        timestamp=timestamp,
        plate_image_filename=plate_image_filename,
        plate_text=plate_text,
        plate_error=plate_error
    )



@bp.route('/update_data', methods=['POST'])
def update_data():
    """
    Envía todos los datos al webhook de revalidación y procesa la respuesta.
    """
    try:
        # Obtener datos del request
        request_data = request.get_json()
        if not request_data or 'table_data' not in request_data:
            logger.error("Datos inválidos recibidos en el request")
            return jsonify({
                "status": "error",
                "message": "Datos inválidos",
                "redirect": url_for('entrada.review', _external=True)
            }), 400

        table_data = request_data['table_data']
        
        # Obtener el código del agricultor
        codigo = next((row.get('sugerido', row.get('original', '')) 
                     for row in table_data if row.get('campo') == 'Código'), '')
        
        if not codigo:
            logger.error("Código faltante en los datos")
            return jsonify({
                "status": "error",
                "message": "Código faltante en los datos",
                "redirect": url_for('entrada.review', _external=True)
            }), 400

        # Preparar datos para el webhook
        payload = {
            "codigo": codigo,
            "datos": [
                {"campo": row.get('campo', ''), 
                 "valor": row.get('sugerido', row.get('original', ''))}
                for row in table_data
            ]
        }
        
        logger.info(f"Enviando datos al webhook: {payload}")
        
        # Fetch original parsed data to get the note
        original_parsed_data = session.get('parsed_data', {})
        original_note = original_parsed_data.get('nota', '')
        
        # Guardar table_data en la sesión independientemente del resultado del webhook
        session['table_data'] = table_data
        session.modified = True
        
        # Convertir los datos de la tabla a un formato compatible con la plantilla
        formatted_data = {}
        for item in payload["datos"]:
            # --- Add the original note to formatted_data for fallback ---
            if original_note:
                formatted_data["nota"] = original_note
                formatted_data["Nota"] = original_note
            # --- End note addition ---
            
            campo = item["campo"]
            valor = item["valor"]
            # Mapear los nombres de campos a las claves esperadas por la plantilla
            if campo == "Nombre del Agricultor":
                formatted_data["nombre_agricultor"] = valor
                formatted_data["Nombre del Agricultor"] = valor  # Mantener ambos formatos
            elif campo == "Código":
                formatted_data["codigo"] = valor
                formatted_data["Código"] = valor  # Mantener ambos formatos
            elif campo == "Cantidad de Racimos":
                formatted_data["racimos"] = valor
                formatted_data["Cantidad de Racimos"] = valor  # Mantener ambos formatos
            elif campo == "Placa":
                formatted_data["placa"] = valor
                formatted_data["Placa"] = valor  # Mantener ambos formatos
            elif campo == "Se Acarreó":
                formatted_data["acarreo"] = valor
                formatted_data["Se Acarreó"] = valor  # Mantener ambos formatos
            elif campo == "Se Cargó":
                formatted_data["cargo"] = valor
                formatted_data["Se Cargó"] = valor  # Mantener ambos formatos
            elif campo == "Transportador":
                formatted_data["transportador"] = valor
                formatted_data["Transportador"] = valor  # Mantener ambos formatos
            elif campo == "Fecha":
                formatted_data["fecha_tiquete"] = valor
                formatted_data["Fecha"] = valor  # Mantener ambos formatos
            else:
                # Para cualquier otro campo, usar el nombre original
                formatted_data[campo.lower().replace(" ", "_")] = valor
                formatted_data[campo] = valor  # Mantener el formato original también
        
        # Registrar los datos formateados para depuración
        logger.info(f"Datos formateados localmente: {formatted_data}")
        
        try:
            # Aumentar el timeout a 60 segundos
            response = requests.post(
                REVALIDATION_WEBHOOK_URL, 
                json=payload, 
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
        
            # Limpiar la respuesta si contiene backticks
            response_text = response.text
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            try:
                response_data = json.loads(response_text)
                logger.info(f"Respuesta recibida del webhook: {response_data}")
                
                # Verificar si la respuesta tiene el formato esperado
                if 'status' in response_data and 'data' in response_data:
                    # Asegurarse de que los datos tengan el formato correcto
                    if isinstance(response_data['data'], dict):
                        # Combinar los datos formateados con los datos de la respuesta
                        # para asegurar que tenemos todas las claves necesarias
                        for key, value in formatted_data.items():
                            if key not in response_data['data']:
                                response_data['data'][key] = value
                    else:
                        logger.warning(f"La respuesta del webhook no tiene el formato esperado: {response_data}")
                        response_data = {
                            "status": "success",
                            "data": formatted_data
                        }
                else:
                    logger.warning(f"La respuesta del webhook no tiene el formato esperado: {response_data}")
                    response_data = {
                        "status": "success",
                        "data": formatted_data
                    }
            except json.JSONDecodeError as e:
                logger.error(f"Error decodificando la respuesta JSON del webhook: {str(e)}")
                response_data = {
                    "status": "success",
                    "data": formatted_data
                }
            
            # Guardar datos en la sesión
            session['webhook_response'] = response_data
            session.modified = True
            
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.error(f"Error en la comunicación con el webhook: {str(e)}")
            # Crear respuesta local con los datos del formulario
            response_data = {
                "status": "success",
                "data": formatted_data
            }
            
            # Guardar datos en la sesión
            session['webhook_response'] = response_data
            session.modified = True
                
        if response_data.get('status') == 'success':
                logger.info("Datos guardados en sesión, redirigiendo a revalidation_success")
                return jsonify({
                    "status": "success",
                    "redirect": url_for('misc.revalidation_success', _external=True)
                })
        else:
            logger.error("Error en la validación")
            return jsonify({
                "status": "error", 
                "message": response_data.get('message', 'Error en la validación'),
                    "redirect": url_for('misc.revalidation_results', _external=True)
            })
            
    except Exception as e:
        logger.error(f"Error en update_data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e),
            "redirect": url_for('entrada.review', _external=True)
        })



@bp.route('/processing', methods=['GET'])
def processing_screen():
    """
    Pantalla de carga mientras se procesa la revalidación.
    """
    return render_template('processing.html')


# >>> NUEVO: Función para generar QR y devolver su nombre o ruta
def generate_qr_image(codigo, nombre, fruta):
    """
    Genera un archivo PNG de código QR que contenga info clave (código, agricultor, fruta).
    Retorna el nombre de archivo PNG.
    """
    content = f"Código: {codigo}\nAgricultor: {nombre}\nFruta: {fruta}"
    qr_img = qrcode.make(content)
    
    # Guardarlo en static con un nombre único
    qr_filename = f"qr_{codigo}_{int(time.time())}.png"
    qr_path = os.path.join(current_app.static_folder, 'qr', qr_filename)
    qr_img.save(qr_path)
    
    # Retornar sólo el nombre, para usarlo en la plantilla
    return qr_filename


def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
    try:
        logger.info("Iniciando generación de PDF")
        logger.info(f"Datos de revalidación: {revalidation_data}")
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        fecha_registro = None
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_registro = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                break
        
        if not fecha_registro:
            fecha_registro = datetime.now().strftime("%d-%m-%Y")
       
        qr_data = {
            "codigo": revalidation_data.get('Código') if revalidation_data else parsed_data.get('codigo', ''),
            "nombre": revalidation_data.get('Nombre del Agricultor') if revalidation_data else parsed_data.get('nombre_agricultor', ''),
            "fecha": fecha_registro,
            "placa": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Placa'), ''),
            "transportador": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Transportador'), ''),
            "cantidad_racimos": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Cantidad de Racimos'), '')
        }
        
        # Extraer o generar un código de guía si no existe
        codigo = qr_data['codigo']
        now_time = int(time.time())
        codigo_guia = f"{codigo}_{now_time}"
        qr_filename = f"qr_{codigo}_{now_time}.png"
        qr_path = os.path.join(current_app.static_folder, 'qr', qr_filename)
        
        # Utilizar utils.generar_qr en lugar de generate_qr para usar URLs dinámicas
        # La URL se generará dinámicamente usando url_for dentro de la función
        utils.generar_qr(
            url_for('entrada.ver_registro_entrada', codigo_guia=codigo_guia, _external=True),
            qr_path
        )
        
        # Renderizar plantilla
        rendered = render_template(
            'pdf_template.html',
            parsed_data=parsed_data,
            revalidation_data=revalidation_data,
            image_filename=image_filename,
            fecha_registro=fecha_registro,
            fecha_procesamiento=fecha_registro,  # Usar la fecha del tiquete
            hora_procesamiento=hora_procesamiento,
            fecha_emision=datetime.now().strftime("%d-%m-%Y"),
            hora_emision=datetime.now().strftime("%H:%M:%S"),
            qr_filename=qr_filename
        )
        
        # Generar PDF
        pdf_filename = f'tiquete_{qr_data["codigo"]}_{fecha_registro}.pdf'
        pdf_path = os.path.join(current_app.config['PDF_FOLDER'], pdf_filename)
        
        HTML(
            string=rendered,
            base_url=current_app.static_folder
        ).write_pdf(pdf_path)
        
        logger.info(f"PDF generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error en generate_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception(f"Error generando PDF: {str(e)}")



@bp.route('/register', methods=['POST'])
def register():
    try:
        logger.info("Iniciando proceso de registro")
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener datos del webhook response
        webhook_response = session.get('webhook_response', {})
        if not webhook_response or not webhook_response.get('data'):
            return jsonify({
                "status": "error",
                "message": "No hay datos del webhook para registrar."
            }), 400

        # Obtener datos del webhook
        webhook_data = webhook_response.get('data', {})
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_registro = now.strftime("%d/%m/%Y")
        hora_registro = now.strftime("%H:%M:%S")
        
        # Obtener código del agricultor
        codigo = webhook_data.get('codigo', '').strip()
        if not codigo:
            return jsonify({
                "status": "error",
                "message": "No se encontró el código del agricultor en los datos del webhook."
            }), 400
            
        # Generar código de guía único usando la función en Utils
        codigo_guia = utils.generar_codigo_guia(codigo)
        
        # Guardar en sesión
        session['fecha_registro'] = fecha_registro
        session['hora_registro'] = hora_registro
        session['codigo_guia'] = codigo_guia
        
        # Generar QR
        qr_filename = f"qr_{codigo}_{now.strftime('%Y%m%d_%H%M%S')}.png"
        
        # Preparar datos para el QR
        qr_data = {
            "codigo": webhook_data.get('codigo', ''),
            "nombre": webhook_data.get('nombre_agricultor', ''),
            "placa": webhook_data.get('placa', ''),
            "transportador": webhook_data.get('transportador', ''),
            "cantidad_racimos": webhook_data.get('racimos', ''),
            "acarreo": webhook_data.get('acarreo', 'No'),
            "cargo": webhook_data.get('cargo', 'No'),
            "nota": webhook_data.get('nota', ''),
            "codigo_guia": codigo_guia
        }
        
        logger.info(f"Generando QR con datos: {qr_data}")
        
        # Generar QR usando la utilidad correcta
        # Usar generar_qr con url_for en lugar de generate_qr que usa URLs hardcodeadas
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        
        # Generar URL del código QR correctamente - url_for genera URL absoluta
        url_qr = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        
        # Usar utils.generar_qr que acepta directamente la URL generada por url_for
        utils.generar_qr(url_qr, qr_path)
        session['qr_filename'] = qr_filename
        
        # Enviar datos al webhook de registro
        try:
            response = requests.post(
                REGISTER_WEBHOOK_URL,
                json={
                    "codigo": webhook_data.get('codigo', ''),
                    "nombre": webhook_data.get('nombre_agricultor', ''),
                    "placa": webhook_data.get('placa', ''),
                    "transportador": webhook_data.get('transportador', ''),
                    "racimos": webhook_data.get('racimos', ''),
                    "acarreo": webhook_data.get('acarreo', 'No'),
                    "cargo": webhook_data.get('cargo', 'No'),
                    "nota": webhook_data.get('nota', ''),
                    "fecha": fecha_registro,
                    "hora": hora_registro,
                    "fecha_tiquete": webhook_data.get('fecha_tiquete', ''),
                    "se_transporto": webhook_data.get('se_transporto', 'No'),
                    "url_qr": url_qr,  # Usamos la URL generada dinámicamente
                    "codigo_guia": codigo_guia
                },
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                logger.error(f"Error en webhook de registro: {response.text}")
                raise Exception("Error al registrar en el sistema central")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error llamando webhook de registro: {str(e)}")
            raise Exception("Error de conexión con el sistema central")
        
        # Generar PDF
        pdf_filename = utils.generate_pdf(
            parsed_data=None,
            image_filename=session.get('image_filename', ''),
            fecha_procesamiento=fecha_registro,
            hora_procesamiento=hora_registro,
            revalidation_data=None,
            codigo_guia=codigo_guia
        )
        
        session['pdf_filename'] = pdf_filename
        session['estado_actual'] = 'pesaje'
        
        # Obtener el código guía completo del nombre del archivo PDF
        codigo_guia_completo = pdf_filename[8:-4]  # Remover 'tiquete_' y '.pdf'
        
        # Generar datos para el almacenamiento local
        datos_para_almacenar = {
            "codigo_guia": codigo_guia,
            "codigo_proveedor": qr_data["codigo"],
            "nombre_proveedor": qr_data["nombre"],
            "fecha_registro": fecha_registro,
            "hora_registro": hora_registro,
            "cantidad_racimos": qr_data["cantidad_racimos"],
            "placa": qr_data["placa"],
            "transportador": qr_data["transportador"],
            "tiquete_imagen": session.get('image_filename', ''),
            "url_pdf": f"/pdfs/{pdf_filename}",
            "url_qr": url_qr,
            "estado": "pendiente"
        }
        
        return jsonify({
            "status": "success",
            "message": "Registro completado exitosamente",
            "pdf_filename": pdf_filename,
            "qr_filename": qr_filename,
            "redirect_url": url_for('pesaje', codigo=codigo_guia_completo, _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error general en registro: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error al registrar: {str(e)}"
        }), 500


    


@bp.route('/review_pdf')
def review_pdf():
    """
    Vista para mostrar el PDF antes de registrarlo
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # NUEVO: Forzar eliminación del QR problemático específico y regeneración del QR
        codigo_guia = session.get('codigo_guia')
        
        # Lista específica de QRs problemáticos que deben ser eliminados completamente
        specific_problem_qrs = [
            os.path.join(current_app.config['QR_FOLDER'], 'default_qr_20250311143540.png'),
            os.path.join(current_app.config['QR_FOLDER'], 'default_qr.png')
        ]
        
        # Eliminar los QRs específicamente problemáticos
        for bad_qr in specific_problem_qrs:
            if os.path.exists(bad_qr):
                try:
                    # Intentar eliminar directamente
                    os.remove(bad_qr)
                    logger.info(f"QR problemático eliminado: {bad_qr}")
                except Exception as e:
                    # Si la eliminación falla, intentar renombrar
                    try:
                        backup_path = f"{bad_qr}.eliminated"
                        os.rename(bad_qr, backup_path)
                        logger.info(f"QR problemático renombrado: {bad_qr} → {backup_path}")
                    except Exception as rename_error:
                        logger.error(f"No se pudo eliminar ni renombrar el QR problemático {bad_qr}: {str(rename_error)}")
        
        # También limpiar QRs que podrían estar usando el código_guia actual
        if codigo_guia:
            problematic_qrs = [
                os.path.join(current_app.config['QR_FOLDER'], f'default_qr_{datetime.now().strftime("%Y%m%d")}*.png'),
                os.path.join(current_app.config['QR_FOLDER'], f'qr_{codigo_guia}*.png'),
                os.path.join(current_app.config['QR_FOLDER'], f'qr_review_{codigo_guia}*.png')
            ]
            
            for qr_pattern in problematic_qrs:
                try:
                    matching_files = glob.glob(qr_pattern)
                    for old_qr in matching_files:
                        if os.path.exists(old_qr):
                            # Renombrar en lugar de eliminar para preservar historial
                            backup_path = f"{old_qr}.old"
                            os.rename(old_qr, backup_path)
                            logger.info(f"QR antiguo renombrado: {old_qr} → {backup_path}")
                except Exception as e:
                    logger.error(f"Error al intentar renombrar QR: {str(e)}")
            
            # SIEMPRE generar un nuevo QR con la URL correcta usando url_for
            timestamp = int(time.time())
            qr_filename = f"qr_review_{codigo_guia}_{timestamp}.png"
            qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
            
            # Usar la nueva vista centralizada para todos los QRs
            qr_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
            logger.info(f"Generando nuevo QR con URL: {qr_url}")
            utils.generar_qr(qr_url, qr_path)
            
            # Actualizar la sesión para usar el nuevo QR
            session['qr_filename'] = qr_filename
            session.modified = True
            
            # Verificar que el archivo se haya creado correctamente
            if os.path.exists(qr_path):
                logger.info(f"Nuevo QR generado exitosamente: {qr_filename}")
            else:
                logger.error(f"No se pudo verificar la creación del nuevo QR: {qr_path}")
        else:
            # Si no hay código_guia, generar uno temporal para tener un QR válido
            temp_codigo_guia = f"temp_{int(time.time())}"
            timestamp = int(time.time())
            qr_filename = f"qr_temp_{temp_codigo_guia}_{timestamp}.png"
            qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
            
            # URL temporal que apunte a la página principal
            qr_url = url_for('misc.upload_file', _external=True)
            logger.info(f"Generando QR temporal con URL: {qr_url}")
            utils.generar_qr(qr_url, qr_path)
            
            session['qr_filename'] = qr_filename
            session.modified = True
        
        pdf_filename = session.get('pdf_filename')
        qr_filename = session.get('qr_filename')  # Usar el que acabamos de actualizar
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        codigo_guia = session.get('codigo_guia')
        
        # Verificar que los archivos existen
        pdf_exists = False
        if pdf_filename:
            pdf_path = os.path.join(current_app.config['PDF_FOLDER'], pdf_filename)
            pdf_exists = os.path.exists(pdf_path)
            if not pdf_exists:
                logger.error(f"El archivo PDF no existe en la ruta: {pdf_path}")
                # Intentar buscar algún PDF generado recientemente con un patrón similar
                parts = pdf_filename.split('_')
                if len(parts) > 1:
                    # Si el nombre tiene partes separadas por _
                    base_pattern = parts[0] + '_' + parts[1]
                    pdf_files = [f for f in os.listdir(current_app.config['PDF_FOLDER']) 
                                if f.startswith(base_pattern) and f.endswith('.pdf')]
                    if pdf_files:
                        pdf_files.sort(key=lambda x: os.path.getmtime(os.path.join(current_app.config['PDF_FOLDER'], x)), reverse=True)
                        pdf_filename = pdf_files[0]
                        session['pdf_filename'] = pdf_filename
                        pdf_exists = True
                        logger.info(f"Se encontró un PDF alternativo: {pdf_filename}")
        
        # Verificar que el QR existe (debería existir porque acabamos de crearlo)
        qr_exists = False
        if qr_filename:
            qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
            qr_exists = os.path.exists(qr_path)
            if not qr_exists:
                logger.error(f"El archivo QR no existe en la ruta: {qr_path}")
                # Este caso no debería ocurrir, pero por si acaso, generamos un nuevo QR
                timestamp = int(time.time())
                qr_filename = f"qr_emergency_{timestamp}.png"
                qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
                
                # URL de emergencia que apunte a la página principal
                qr_url = url_for('misc.upload_file', _external=True)
                logger.info(f"Generando QR de emergencia con URL: {qr_url}")
                utils.generar_qr(qr_url, qr_path)
                
                session['qr_filename'] = qr_filename
                qr_exists = os.path.exists(qr_path)
        
        # Recuperar datos del webhook response guardados en session
        webhook_response = session.get('webhook_response', {})
        webhook_data = webhook_response.get('data', {})
        
        # Intentar obtener todos los datos validados de la revalidation_success
        # Si no están disponibles, usar los datos del webhook_response
        if webhook_data:
            nombre_agricultor = webhook_data.get('nombre_agricultor', 'No disponible')
            codigo = webhook_data.get('codigo', 'No disponible')
            racimos = webhook_data.get('racimos', 'No disponible')
            placa = webhook_data.get('placa', 'No disponible')
            acarreo = webhook_data.get('acarreo', 'No disponible')
            cargo = webhook_data.get('cargo', 'No disponible')
            transportador = webhook_data.get('transportador', 'No disponible')
            fecha_tiquete = webhook_data.get('fecha_tiquete', 'No disponible')
        else:
            # Usar los datos guardados directamente en la sesión
            nombre_agricultor = session.get('nombre_agricultor', 'No disponible')
            codigo = session.get('codigo', 'No disponible')
            racimos = session.get('racimos', 'No disponible')
            placa = session.get('placa', 'No disponible')
            acarreo = session.get('acarreo', 'No disponible')
            cargo = session.get('cargo', 'No disponible')
            transportador = session.get('transportador', 'No disponible')
            fecha_tiquete = session.get('fecha_tiquete', 'No disponible')
        
        # Obtener fecha y hora de registro
        fecha_registro = session.get('fecha_registro', datetime.now().strftime("%d/%m/%Y"))
        hora_registro = session.get('hora_registro', datetime.now().strftime("%H:%M:%S"))
        plate_text = session.get('plate_text', '')
        
        # Si después de intentar encontrar alternativas, aún no se encuentran los archivos,
        # mostrar un mensaje de error
        if not pdf_exists or not qr_exists:
            logger.error(f"No se encontraron archivos. PDF: {pdf_exists}, QR: {qr_exists}")
            
            # Si hay datos suficientes, intentar regenerar los archivos
            if codigo and nombre_agricultor and image_filename:
                logger.info("Intentando regenerar PDF y QR...")
                try:
                    # Generar un nombre por defecto para el QR
                    now = datetime.now()
                    default_qr_filename = f"default_qr_{now.strftime('%Y%m%d%H%M%S')}.png"
                    
                    # Crear datos para regenerar
                    datos_regenerar = {
                        'codigo': codigo,
                        'nombre_agricultor': nombre_agricultor,
                        'racimos': racimos,
                        'placa': placa,
                        'acarreo': acarreo,
                        'cargo': cargo,
                        'transportador': transportador,
                        'fecha_tiquete': fecha_tiquete,
                        'codigo_guia': codigo_guia  # Incluir el código de guía para generar correctamente el QR
                    }
                    
                    # Regenerar el PDF
                    pdf_regenerado = utils.generate_pdf(
                        datos_regenerar,
                        image_filename,
                        fecha_registro,
                        hora_registro,
                        datos_regenerar
                    )
                    
                    if pdf_regenerado:
                        pdf_filename = pdf_regenerado
                        session['pdf_filename'] = pdf_filename
                        logger.info(f"PDF regenerado exitosamente: {pdf_filename}")
                        pdf_exists = True
                    
                    # Verificar el QR
                    qr_filename = session.get('qr_filename')
                    qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
                    qr_exists = os.path.exists(qr_path)
                    
                except Exception as e:
                    logger.error(f"Error al intentar regenerar archivos: {str(e)}")
                    logger.error(traceback.format_exc())
            
            # Si aún no se pueden encontrar, mostrar mensaje de error
            if not pdf_exists or not qr_exists:
                error_msg = "No se encontró "
                if not pdf_exists and not qr_exists:
                    error_msg += "el PDF ni el código QR generados."
                elif not pdf_exists:
                    error_msg += "el PDF generado."
                else:
                    error_msg += "el código QR generado."
                
                flash(error_msg, "error")
                # Continuamos para mostrar los datos disponibles de todos modos
        
        # Agregar logs para depuración
        logger.info(f"Datos para PDF: nombre={nombre_agricultor}, codigo={codigo}, racimos={racimos}, nota={webhook_data.get('nota', 'No disponible')}")
        logger.info(f"Archivos: pdf={pdf_filename} (existe: {pdf_exists}), qr={qr_filename} (existe: {qr_exists})")
        
        # Recuperar indicadores de campos modificados
        nombre_agricultor_modificado = session.get('nombre_agricultor_modificado', False)
        codigo_modificado = session.get('codigo_modificado', False)
        cantidad_de_racimos_modificado = session.get('cantidad_de_racimos_modificado', False)
        placa_modificado = session.get('placa_modificado', False)
        acarreo_modificado = session.get('acarreo_modificado', False)
        cargo_modificado = session.get('cargo_modificado', False)
        transportador_modificado = session.get('transportador_modificado', False)
        fecha_modificado = session.get('fecha_modificado', False)
        
        # Get the note/observations - Use 'nota' if present, fallback to 'observaciones'
        nota_value = webhook_data.get('nota', webhook_data.get('observaciones', 'No disponible'))
        
        # --- Explicitly fetch Note from DB as it might be missed by get_datos_guia ---
        try:
            conn_note = sqlite3.connect('tiquetes.db')
            cursor_note = conn_note.cursor()
            cursor_note.execute("SELECT nota FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
            note_result = cursor_note.fetchone()
            conn_note.close()
            if note_result and note_result[0]:
                nota_value = note_result[0]
                logger.info(f"Successfully fetched note from DB for {codigo_guia}")
            else:
                 logger.warning(f"Note not found in DB for {codigo_guia}, using value from datos_guia: {nota_value}")
        except sqlite3.Error as db_err:
            logger.error(f"DB error fetching note for {codigo_guia}: {db_err}")
            if 'conn_note' in locals() and conn_note:
                 conn_note.close()
        # --- End fetching Note ---
        
        context = {
            'pdf_filename': pdf_filename,
            'qr_filename': qr_filename,
            'image_filename': image_filename,
            'plate_image_filename': plate_image_filename,
            'codigo_guia': codigo_guia,
            'nombre_agricultor': nombre_agricultor,
            'codigo': codigo,
            'racimos': racimos,
            'placa': placa,
            'acarreo': acarreo,
            'cargo': cargo,
            'transportador': transportador,
            'fecha_tiquete': fecha_tiquete,
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro,
            'plate_text': plate_text,
            'nota': nota_value,
            'nombre_agricultor_modificado': nombre_agricultor_modificado,
            'codigo_modificado': codigo_modificado,
            'cantidad_de_racimos_modificado': cantidad_de_racimos_modificado,
            'placa_modificado': placa_modificado,
            'acarreo_modificado': acarreo_modificado,
            'cargo_modificado': cargo_modificado, 
            'transportador_modificado': transportador_modificado,
            'fecha_modificado': fecha_modificado,
            'pdf_exists': pdf_exists,
            'qr_exists': qr_exists,
            'now_timestamp': int(time.time()),  # Timestamp actual para evitar caché
            'qr_url': qr_url
        }
        
        return render_template('entrada/review_pdf.html', **context)
    except Exception as e:
        logger.error(f"Error en review_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al mostrar el PDF antes de registrarlo', 'error')
        return redirect(url_for('entrada.review'))



@bp.route('/registros-entrada', methods=['GET'])
def lista_registros_entrada():
    """
    Muestra la lista de registros de entrada.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        placa = request.args.get('placa', '')

        # Preparar filtros para la consulta
        filtros = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'placa': placa
        }
        
        # Inicializar la lista de registros
        registros = []
        
        # Intentar obtener registros de la base de datos
        try:
            import db_utils
            from db_operations import get_pesaje_bruto_by_codigo_guia
            
            registros_db = db_utils.get_entry_records(filtros)
            
            if registros_db:
                logger.info(f"Obtenidos {len(registros_db)} registros de la base de datos")
                # Ya están ordenados por fecha_registro DESC, hora_registro DESC
                registros = registros_db
                
                # Cargar los pesajes existentes para verificar cuáles tienen pesaje
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para cada registro
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
            else:
                logger.info("No se encontraron registros en la base de datos. Buscando en archivos.")
                
                # Si no hay registros en la base de datos, buscar en archivos (compatibilidad)
                registros = obtener_registros_desde_archivos(filtros)
                
                # Cargar los pesajes existentes para verificar cuáles tienen pesaje
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para registros de archivos
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos: {db_error}")
            # En caso de error con la base de datos, buscar en archivos
            registros = obtener_registros_desde_archivos(filtros)
            
            # Cargar los pesajes existentes para verificar cuáles tienen pesaje
            try:
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para registros de archivos
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
            except Exception as e:
                logger.error(f"Error al verificar pesajes existentes: {str(e)}")
                # En caso de error, asumir que ningún registro tiene pesaje
                for registro in registros:
                    registro['tiene_pesaje'] = False
        
        
        return render_template('registros_entrada.html', registros=registros, filtros=filtros)
        
    except Exception as e:
        logger.error(f"Error listando registros de entrada: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al listar registros de entrada', 'error')
        return redirect(url_for('misc.upload_file'))

def obtener_registros_desde_archivos(filtros):
    """
    Obtiene registros de entrada desde archivos HTML
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    registros = []
    guias_dir = os.path.join(current_app.static_folder, 'guias')
    
    # Verificar si el directorio de guías existe
    if os.path.exists(guias_dir):
        for filename in os.listdir(guias_dir):
            if filename.startswith('guia_') and filename.endswith('.html'):
                codigo_guia = filename.replace('guia_', '').replace('.html', '')
                
                # Extraer el código base (sin timestamp ni versión)
                if '_' in codigo_guia:
                    # Código base es la primera parte del código guía (código del proveedor)
                    codigo_base = codigo_guia.split('_')[0]
                else:
                    codigo_base = codigo_guia
                
                # Obtener datos de la guía usando la función mejorada get_datos_guia 
                # que primero busca en DB, luego en archivos y finalmente en sesión
                try:
                    # Usar el método mejorado get_datos_guia en lugar de get_datos_registro
                    datos = utils.get_datos_guia(codigo_guia)
                except Exception as e:
                    logger.error(f"Error obteniendo datos para {codigo_guia}: {str(e)}")
                    continue
                
                if datos:
                    # Filtrar por fecha
                    if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                        # Convertir fecha de registro a formato comparable (aaaa-mm-dd)
                        try:
                            fecha_obj = datetime.strptime(datos.get('fecha_registro', ''), '%d/%m/%Y')
                            fecha_registro_str = fecha_obj.strftime('%Y-%m-%d')
                            
                            if fecha_registro_str < filtros['fecha_desde'] or fecha_registro_str > filtros['fecha_hasta']:
                                continue
                        except:
                            pass
                    
                    # Filtrar por código de proveedor
                    if filtros.get('codigo_proveedor') and filtros['codigo_proveedor'].lower() not in datos.get('codigo_proveedor', '').lower():
                        continue
                    
                    # Filtrar por nombre de proveedor
                    if filtros.get('nombre_proveedor') and filtros['nombre_proveedor'].lower() not in datos.get('nombre_proveedor', '').lower():
                        continue
                    
                    # Filtrar por placa
                    if filtros.get('placa') and filtros['placa'].lower() not in datos.get('placa', '').lower():
                        continue
                        
                    # Añadir registro a la lista
                    registros.append({
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': datos.get('codigo_proveedor', ''),
                        'nombre_proveedor': datos.get('nombre_proveedor', ''),
                        'placa': datos.get('placa', ''),
                        'fecha_registro': datos.get('fecha_registro', ''),
                        'cantidad_racimos': datos.get('cantidad_racimos', ''),
                        'estado': 'Registrado'
                    })
    
    return registros



@bp.route('/registro-entrada/<codigo_guia>', methods=['GET', 'POST'])
def ver_registro_entrada(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    # Verificar si debemos redirigir a la vista dinámica
    usar_vista_dinamica = current_app.config.get('USAR_VISTA_DINAMICA', False)
    if usar_vista_dinamica:
        return redirect(url_for('entrada.ver_guia_estado', codigo_guia=codigo_guia))
    
    # Continuar con la lógica original si no se usa la vista dinámica
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    registro = None
    # Intentar obtener el registro desde la base de datos primero
    try:
        import db_utils
        registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
        if registro:
            logger.debug(f"Estructura de datos desde db_utils: {registro}")
    except Exception as db_error:
        logger.error(f"Error accediendo a la base de datos: {db_error}")
        
    if registro:
        logger.info(f"Registro encontrado en la base de datos: {codigo_guia}")
    
        # --- INICIO: Conversión de Timestamp UTC a Bogotá para Template ---
        from datetime import datetime
        import pytz
        BOGOTA_TZ = pytz.timezone('America/Bogota')
        UTC = pytz.utc

        utc_timestamp_str = registro.get('timestamp_registro_utc')
        fecha_local = None
        hora_local = None
        if utc_timestamp_str:
            try:
                dt_utc = datetime.strptime(utc_timestamp_str, "%Y-%m-%d %H:%M:%S")
                dt_utc = UTC.localize(dt_utc)
                dt_local = dt_utc.astimezone(BOGOTA_TZ)
                fecha_local = dt_local.strftime('%d/%m/%Y')
                hora_local = dt_local.strftime('%H:%M:%S')
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse/convert timestamp '{utc_timestamp_str}' in ver_registro_entrada: {e}")
        
        # Añadir los campos formateados al diccionario registro
        registro['fecha_registro'] = fecha_local
        registro['hora_registro'] = hora_local
        # --- FIN: Conversión de Timestamp UTC a Bogotá para Template ---
    
    # Si no se encontró en la base de datos, intentar obtenerlo del archivo
    if not registro:
        logger.info(f"Buscando registro en archivos: {codigo_guia}")
        registro = utils.get_datos_registro(codigo_guia)
        if registro:
            logger.debug(f"Estructura de datos desde utils.get_datos_registro: {registro}")
    
    # Si se encontró el registro, estandarizar los datos y mostrar la plantilla
    if registro:
        # Importar función para estandarizar datos
        from app.utils.common import standardize_template_data
        
        # Estandarizar datos para el template
        registro = standardize_template_data(registro, 'entrada')
        
        # Log detallado de datos estandarizados
        logger.info(f"Datos para template: codigo={registro.get('codigo')}, nombre={registro.get('nombre_proveedor')}, racimos={registro.get('cantidad_racimos')}")
        
        return render_template('registro_entrada_detalle.html', registro=registro)
    else:
        # Mensaje específico cuando el código no se encuentra en la base de datos ni en archivos
        flash(f'El registro con código {codigo_guia} no fue encontrado ni en la base de datos ni en los archivos', 'warning')
        return redirect(url_for('misc.upload_file'))

# Nuevas rutas experimentales con feature flags
@bp.route('/nueva-entrada')
def nueva_entrada():
    """
    Ruta experimental para el nuevo formulario de entrada
    """
    if current_app.config.get('USAR_NUEVOS_TEMPLATES_ENTRADA', False):
        return render_template('entrada/entrada_form.html')
    else:
        # Redireccionar a la ruta antigua si los templates nuevos están desactivados
        return redirect(url_for('misc.upload_file'))

@bp.route('/entradas')
def lista_entradas():
    """
    Ruta para la lista de entradas
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_inicio = request.args.get('fecha_inicio', '')
        fecha_fin = request.args.get('fecha_fin', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        placa = request.args.get('placa', '')
        estado = request.args.get('estado', '')

        # Preparar filtros para la consulta
        filtros = {
            'fecha_desde': fecha_inicio,
            'fecha_hasta': fecha_fin,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'placa': placa,
            'estado': estado
        }
        
        # Inicializar la lista de registros
        registros = []
        
        # Importar función para estandarizar datos
        from app.utils.common import standardize_template_data
        
        # Intentar obtener registros de la base de datos
        try:
            import db_utils
            
            registros_db = db_utils.get_entry_records(filtros)
            
            if registros_db:
                logger.info(f"Obtenidos {len(registros_db)} registros de la base de datos")
                
                # Estandarizar cada registro
                registros = []
                for registro in registros_db:
                    # Estandarizar datos para el template
                    registro_std = standardize_template_data(registro, 'entrada')
                    registros.append(registro_std)
                
                # Cargar los pesajes existentes para verificar cuáles tienen pesaje
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para cada registro
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                        registro['estado'] = 'pesado'
                    else:
                        registro['tiene_pesaje'] = False
                        registro['estado'] = 'pendiente'
                        
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos: {db_error}")
            # Si hay un error en la base de datos, intentar obtener registros de archivos
            registros_archivos = obtener_registros_desde_archivos(filtros)
            
            # Estandarizar cada registro de archivos
            registros = []
            for registro in registros_archivos:
                # Estandarizar datos para el template
                registro_std = standardize_template_data(registro, 'entrada')
                registros.append(registro_std)
        
        # Log para verificar la estructura de los datos
        logger.debug(f"Enviando {len(registros)} registros estandarizados al template")
        if registros:
            logger.debug(f"Ejemplo de registro estandarizado: {registros[0]}")
        
        # Usar el template corregido entrada/entradas_lista.html
        return render_template('entrada/entradas_lista.html', entradas=registros, filtros=filtros)
            
    except Exception as e:
        logger.error(f"Error obteniendo registros de entrada: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al obtener registros de entrada. Por favor intente nuevamente.', 'error')
        return redirect(url_for('misc.upload_file'))

@bp.route('/entrada/<codigo_guia>')
def ver_entrada(codigo_guia):
    """
    Redirige a la vista centralizada de guía
    """
    logger.info(f"Redirigiendo a vista centralizada: {codigo_guia}")
    return redirect(url_for('misc.ver_guia_alternativa', codigo_guia=codigo_guia))

@bp.route('/guia/<codigo_guia>')
def ver_guia_estado(codigo_guia):
    """
    Redirige a la vista centralizada de guía
    """
    logger.info(f"Redirigiendo a vista centralizada: {codigo_guia}")
    return redirect(url_for('misc.ver_guia_alternativa', codigo_guia=codigo_guia))

@bp.route('/registrar-entrada', methods=['POST'])
def registrar_entrada():
    """
    Ruta experimental para procesar el formulario de nueva entrada
    """
    if not current_app.config.get('USAR_NUEVOS_TEMPLATES_ENTRADA', False):
        # Si los templates nuevos están desactivados, redirigir a la ruta antigua
        return redirect(url_for('misc.upload_file'))
    
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener fecha y hora en zona horaria de Bogotá
        fecha_actual, hora_actual = get_bogota_datetime()
        
        # Obtener datos del formulario
        codigo_proveedor = request.form.get('codigo_proveedor', '')
        nombre_proveedor = request.form.get('nombre_proveedor', '')
        placa = request.form.get('placa', '')
        transportador = request.form.get('transportador', '')
        cantidad_racimos = request.form.get('cantidad_racimos', '')
        codigo_guia_transporte_sap = request.form.get('codigo_guia_transporte_sap', '')
        observaciones = request.form.get('observaciones', '')
        
        # Verificar si se subió un archivo
        if 'imagen_tiquete' not in request.files:
            flash('No se seleccionó ninguna imagen', 'error')
            return redirect(url_for('entrada.nueva_entrada'))
        
        archivo = request.files['imagen_tiquete']
        
        if archivo.filename == '':
            flash('No se seleccionó ningún archivo', 'error')
            return redirect(url_for('entrada.nueva_entrada'))
        
        # Guardar datos en sesión
        session['codigo_proveedor'] = codigo_proveedor
        session['nombre_proveedor'] = nombre_proveedor
        session['placa'] = placa
        session['transportador'] = transportador
        session['cantidad_racimos'] = cantidad_racimos
        session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
        session['observaciones'] = observaciones
        
        # Guardar la imagen
        utils = Utils(current_app)
        
        # Generar código único para la guía
        from datetime import datetime
        import uuid
        
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        codigo_guia = f"{codigo_proveedor}_{timestamp}"
        session['codigo_guia'] = codigo_guia
        
        # Guardar imagen
        if archivo:
            # Obtener extensión original del archivo
            filename_parts = os.path.splitext(archivo.filename)
            extension = filename_parts[1] if len(filename_parts) > 1 else '.jpg'
            
            # Crear nombre de archivo seguro con la extensión original
            image_filename = f"ticket_{codigo_guia}{extension}"
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], image_filename)
            archivo.save(filepath)
            
            # Almacenar nombre del archivo en la sesión
            session['image_filename'] = image_filename
            
            logger.info(f"Imagen guardada: {filepath}")
            
            # Si se marca la opción de procesar OCR, redireccionar a la pantalla de procesamiento
            if procesar_ocr:
                return redirect(url_for('entrada.processing'))
            else:
                # Registrar directamente sin OCR
                try:
                    # Crear diccionario con todos los datos recolectados
                    datos_registro = {
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': codigo_proveedor,
                        'nombre_proveedor': nombre_proveedor,
                        'placa': placa,
                        'transportador': transportador,
                        'cantidad_racimos': cantidad_racimos,
                        'codigo_guia_transporte_sap': codigo_guia_transporte_sap,
                        'observaciones': observaciones,
                        'image_filename': image_filename,
                        # Use UTC timestamp in standard format
                        'timestamp_registro_utc': datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    
                    # Guardar en la base de datos
                    import db_utils
                    db_utils.store_entry_record(datos_registro)
                    
                    # Redireccionar a la vista de detalles
                    flash('Entrada registrada exitosamente', 'success')
                    return redirect(url_for('entrada.ver_entrada', codigo_guia=codigo_guia))
                except Exception as e:
                    logger.error(f"Error registrando entrada: {str(e)}")
                    logger.error(traceback.format_exc())
                    flash('Error registrando la entrada. Por favor intente nuevamente.', 'error')
                    return redirect(url_for('entrada.nueva_entrada'))
        else:
            flash('Error al procesar la imagen', 'error')
            return redirect(url_for('entrada.nueva_entrada'))
        
    except Exception as e:
        logger.error(f"Error en el registro de entrada: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error en el procesamiento del formulario', 'error')
        return redirect(url_for('entrada.nueva_entrada'))

@bp.route('/editar-entrada/<codigo_guia>', methods=['GET', 'POST'])
def editar_entrada(codigo_guia):
    """
    Ruta para editar un registro de entrada existente
    """
    # Inicializar Utils dentro del contexto de la aplicación
    utils = Utils(current_app)
    
    # Obtener el registro existente
    registro = None
    try:
        import db_utils
        registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
    except Exception as db_error:
        logger.error(f"Error accediendo a la base de datos: {db_error}")
    
    if not registro:
        registro = utils.get_datos_registro(codigo_guia)
    
    if not registro:
        flash(f'El registro con código {codigo_guia} no fue encontrado', 'warning')
        return redirect(url_for('entrada.lista_entradas'))
    
    # Si es una solicitud POST, procesar la edición
    if request.method == 'POST':
        try:
            # Obtener datos del formulario
            codigo_proveedor = request.form.get('codigo_proveedor', '')
            nombre_proveedor = request.form.get('nombre_proveedor', '')
            placa = request.form.get('placa', '')
            transportador = request.form.get('transportador', '')
            cantidad_racimos = request.form.get('cantidad_racimos', '')
            observaciones = request.form.get('observaciones', '')
            
            # Actualizar datos
            datos_actualizados = {
                'codigo_proveedor': codigo_proveedor,
                'nombre_proveedor': nombre_proveedor,
                'placa': placa,
                'transportador': transportador,
                'cantidad_racimos': cantidad_racimos,
                'nota': observaciones
            }
            
            # Actualizar en base de datos o archivos según corresponda
            try:
                import db_utils
                db_utils.update_entry_record(codigo_guia, datos_actualizados)
                flash('Registro actualizado exitosamente', 'success')
            except Exception as db_error:
                logger.error(f"Error actualizando en base de datos: {db_error}")
                # Intentar actualizar en archivos
                utils.update_datos_guia(codigo_guia, datos_actualizados)
                flash('Registro actualizado exitosamente (almacenamiento de archivos)', 'success')
            
            return redirect(url_for('entrada.ver_entrada', codigo_guia=codigo_guia))
        except Exception as e:
            logger.error(f"Error editando entrada: {str(e)}")
            logger.error(traceback.format_exc())
            flash('Error al actualizar el registro', 'error')
    
    # Para solicitudes GET, mostrar el formulario de edición
    if current_app.config.get('USAR_NUEVOS_TEMPLATES_ENTRADA', False):
        return render_template('entrada/entrada_form.html', 
                              modo='editar', 
                              registro=registro, 
                              codigo_guia=codigo_guia)
    else:
        # Usar template antiguo o redirigir
        flash('La funcionalidad de edición solo está disponible con los nuevos templates', 'warning')
        return redirect(url_for('entrada.lista_entradas'))

@bp.route('/diagnostico-entradas')
def diagnostico_entradas():
    """
    Herramienta de diagnóstico para revisar los registros de entrada
    """
    try:
        # Obtener todos los archivos HTML y JSON en la carpeta de guías
        guias_folder = current_app.config['GUIAS_FOLDER']
        archivos_html = glob.glob(os.path.join(guias_folder, "*.html"))
        archivos_json = glob.glob(os.path.join(guias_folder, "*.json"))
        
        # Ordenar por fecha de modificación, más reciente primero
        archivos_html.sort(key=os.path.getmtime, reverse=True)
        archivos_json.sort(key=os.path.getmtime, reverse=True)
        
        return render_template(
            'diagnostico_entradas.html',
            archivos_html=archivos_html,
            archivos_json=archivos_json
        )
        
    except Exception as e:
        logger.error(f"Error en diagnóstico de entradas: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error en diagnóstico de entradas: {str(e)}", "error")
        return redirect(url_for('misc.upload_file'))

@bp.route('/detalles-registro/<codigo_guia>')
def detalles_registro(codigo_guia):
    """
    Muestra los detalles completos de un registro de entrada específico,
    utilizando un formato similar a review_pdf pero para un código de guía existente.
    """
    try:
        # Obtener datos completos de la guía
        utils = current_app.config.get('utils')
        if not utils:
            from app.utils.common import CommonUtils
            utils = CommonUtils(current_app)
            
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontró la guía especificada.", "warning")
            return redirect(url_for('entrada.lista_entradas'))
        
        # --- Find QR and PDF files --- 
        qr_folder = current_app.config['QR_FOLDER']
        pdf_folder = current_app.config['PDF_FOLDER']
        qr_filename = None
        qr_exists = False
        pdf_filename = None
        pdf_exists = False

        # Search for the QR file (prioritize review QR, then others)
        # Use glob to find matching files
        qr_patterns = [
            f"qr_review_{codigo_guia}_*.png",
            f"qr_{codigo_guia}_*.png",
            f"qr_guia_{codigo_guia}.png", # Older pattern?
            f"qr_centralizado_{codigo_guia}.png" # Pattern from central view
        ]
        for pattern in qr_patterns:
            qr_files = glob.glob(os.path.join(qr_folder, pattern))
            if qr_files:
                qr_files.sort(key=os.path.getmtime, reverse=True) # Get the latest
                qr_filename = os.path.basename(qr_files[0])
                qr_exists = True
                logger.info(f"Found QR file for details page: {qr_filename}")
                break

        # Search for the PDF file
        pdf_patterns = [
            f"tiquete_{codigo_guia}.pdf", 
            f"registro_{codigo_guia}.pdf"
        ]
        # Extract code part if codigo_guia has timestamp
        codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        pdf_patterns.insert(0, f"tiquete_{codigo_base}_*.pdf") # More robust pattern

        for pattern in pdf_patterns:
            pdf_files = glob.glob(os.path.join(pdf_folder, pattern))
            if pdf_files:
                pdf_files.sort(key=os.path.getmtime, reverse=True) # Get the latest
                pdf_filename = os.path.basename(pdf_files[0])
                pdf_exists = True
                logger.info(f"Found PDF file for details page: {pdf_filename}")
                break
        # --- End Find QR and PDF files --- 
        
        # Timestamp actual para prevenir caché de imágenes
        now_timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        
        # Get the note/observations - Use 'nota' if present, fallback to 'observaciones'
        nota_value = datos_guia.get('nota', datos_guia.get('observaciones', 'No disponible'))
        
        # --- Explicitly fetch Note from DB as it might be missed by get_datos_guia ---
        try:
            conn_note = sqlite3.connect('tiquetes.db')
            cursor_note = conn_note.cursor()
            cursor_note.execute("SELECT nota FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
            note_result = cursor_note.fetchone()
            conn_note.close()
            if note_result and note_result[0]:
                nota_value = note_result[0]
                logger.info(f"Successfully fetched note from DB for {codigo_guia}")
            else:
                 logger.warning(f"Note not found in DB for {codigo_guia}, using value from datos_guia: {nota_value}")
        except sqlite3.Error as db_err:
            logger.error(f"DB error fetching note for {codigo_guia}: {db_err}")
            if 'conn_note' in locals() and conn_note:
                 conn_note.close()
        # --- End fetching Note ---
        
        # Preparar datos para la plantilla
        context = {
            'codigo': datos_guia.get('codigo_proveedor', 'No disponible'),
            'codigo_guia': codigo_guia,
            'nombre_agricultor': datos_guia.get('nombre_agricultor', datos_guia.get('nombre_proveedor', 'No disponible')),
            'racimos': datos_guia.get('racimos', datos_guia.get('cantidad_racimos', 'No disponible')),
            'placa': datos_guia.get('placa', 'No disponible'),
            'acarreo': datos_guia.get('acarreo', 'No disponible'),
            'cargo': datos_guia.get('cargo', 'No disponible'),
            'transportador': datos_guia.get('transportador', datos_guia.get('transportista', 'No disponible')),
            'fecha_tiquete': datos_guia.get('fecha_tiquete', 'No disponible'),
            'fecha_registro': datos_guia.get('fecha_registro', 'No disponible'),
            'hora_registro': datos_guia.get('hora_registro', 'No disponible'),
            'image_filename': datos_guia.get('image_filename'),
            'qr_filename': qr_filename,
            'pdf_filename': pdf_filename,
            'qr_exists': qr_exists,
            'pdf_exists': pdf_exists,
            'now_timestamp': now_timestamp,
            'qr_url': url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        }
        
        return render_template('entrada/detalles_registro.html', **context)
        
    except Exception as e:
        logger.error(f"Error al mostrar detalles de registro: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al cargar los detalles: {str(e)}", "error")
        return redirect(url_for('entrada.lista_entradas'))



