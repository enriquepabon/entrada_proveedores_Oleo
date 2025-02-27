from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, current_app, flash, send_file, make_response
import os
import requests
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from weasyprint import HTML
import tempfile
import logging
import traceback
import mimetypes
import time
import json
import qrcode
from io import BytesIO
from PIL import Image
import io
import base64
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as ExcelImage
from parser import parse_markdown_response
from config import app
from utils import Utils
import random
import string
from knowledge_updater import knowledge_bp
import glob
from fpdf import FPDF
import re
import pdfkit
from concurrent.futures import ThreadPoolExecutor

# Configuración de Roboflow
ROBOFLOW_API_KEY = "huyFoCQs7090vfjDhfgK"
# Updated API URL - using the direct API endpoint format
ROBOFLOW_API_URL = "https://api.roboflow.com/workflow"
WORKSPACE_NAME = "enrique-p-workspace"
WORKFLOW_ID = "clasificacion-racimos-3"

# Configuración de Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Inicializar Utils
utils = Utils(app)

app.register_blueprint(knowledge_bp)

# En apptiquetes.py, al inicio después de las importaciones
# Configuración de carpetas usando Utils
REQUIRED_FOLDERS = [
    os.path.join(app.static_folder, 'images'),
    os.path.join(app.static_folder, 'uploads'),
    os.path.join(app.static_folder, 'pdfs'),
    os.path.join(app.static_folder, 'guias'),
    os.path.join(app.static_folder, 'qr')
]

utils.ensure_directories(REQUIRED_FOLDERS)

for folder in REQUIRED_FOLDERS:
    os.makedirs(folder, exist_ok=True)

# Configuración de carpetas
app.config.update(
    GUIAS_FOLDER=os.path.join(app.static_folder, 'guias'),
    UPLOAD_FOLDER=os.path.join(app.static_folder, 'uploads'),
    PDF_FOLDER=os.path.join(app.static_folder, 'pdfs'),
    EXCEL_FOLDER=os.path.join(app.static_folder, 'excels'),
    SECRET_KEY='tu_clave_secreta_aquí'
)

# Crear directorios necesarios
for folder in ['GUIAS_FOLDER', 'UPLOAD_FOLDER', 'PDF_FOLDER', 'EXCEL_FOLDER']:
    os.makedirs(app.config[folder], exist_ok=True)

# Constantes para clasificación
CLASIFICACION_TEMP_DIR = os.path.join('static', 'uploads', 'Racimos_clasificacion_temp')
CLASIFICACION_ETIQUETADA_DIR = os.path.join('static', 'uploads', 'Racimos_clasificacion_etiquetadas')
CLASIFICACION_RESULTADOS_DIR = os.path.join('static', 'clasificaciones')

# Asegurar que existan los directorios necesarios
for dir_path in [CLASIFICACION_TEMP_DIR, CLASIFICACION_ETIQUETADA_DIR, CLASIFICACION_RESULTADOS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

@app.route('/guias/<filename>')
def serve_guia(filename):
    """
    Sirve los archivos HTML de las guías de proceso
    """
    try:
        logger.info(f"Intentando servir guía: {filename}")
        
        # Extraer el código de guía del nombre del archivo
        codigo_guia = filename.replace('guia_', '').replace('.html', '')
        
        # Ruta del archivo de guía solicitado
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], filename)
        
        # Si el archivo no existe, verificar si tenemos que buscar por código base
        if not os.path.exists(guia_path):
            logger.info(f"Archivo de guía no encontrado directamente: {guia_path}")
            # Extraer el código base si el código contiene guión bajo
            if '_' in codigo_guia:
                codigo_base = codigo_guia.split('_')[0]
                guias_folder = app.config['GUIAS_FOLDER']
                # Buscar las guías con ese código base
                guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}*.html'))
                
                if guias_files:
                    # Ordenar por fecha de modificación, más reciente primero
                    guias_files.sort(key=os.path.getmtime, reverse=True)
                    latest_guia = os.path.basename(guias_files[0])
                    logger.info(f"Redirigiendo a la guía más reciente: {latest_guia}")
                    # Redirigir a la versión más reciente
                    return redirect(url_for('serve_guia', filename=latest_guia))
            
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
        return send_from_directory(app.config['GUIAS_FOLDER'], filename)
        
    except Exception as e:
        logger.error(f"Error sirviendo guía: {str(e)}")
        return render_template('error.html', message="Error al servir la guía"), 500

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

codigos_autorizacion = {}


# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    session.clear()
    
    if request.method == 'POST':
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
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(image_path)
                session['image_filename'] = filename

                # Procesar imagen de placa si existe
                if plate_file and plate_file.filename != '' and allowed_file(plate_file.filename):
                    plate_filename = secure_filename(plate_file.filename)
                    plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_filename)
                    plate_file.save(plate_path)
                    session['plate_image_filename'] = plate_filename
                
                return redirect(url_for('processing'))
            except Exception as e:
                logger.error(f"Error guardando archivo: {str(e)}")
                return render_template('error.html', message="Error procesando el archivo.")
        else:
            return render_template('error.html', message="Tipo de archivo no permitido.")
    
    return render_template('index.html')

@app.route('/index')
def index():
    """
    Render the index page template.
    """
    return render_template('index.html')

@app.route('/processing')
def processing():
    image_filename = session.get('image_filename')
    if not image_filename:
        return render_template('error.html', message="No se encontró una imagen para procesar.")
    return render_template('processing.html')

@app.route('/process_image', methods=['POST'])
def process_image():
    try:
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        
        if not image_filename:
            logger.error("No se encontró imagen en la sesión")
            return jsonify({"result": "error", "message": "No se encontró una imagen para procesar."}), 400
        
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return jsonify({"result": "error", "message": "Archivo no encontrado."}), 404
        
        # Procesar imagen del tiquete y placa en paralelo
        tiquete_future = None
        placa_future = None
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Iniciar procesamiento del tiquete
            tiquete_future = executor.submit(process_tiquete_image, image_path, image_filename)
            
            # Iniciar procesamiento de la placa si existe
            if plate_image_filename:
                plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_image_filename)
                if os.path.exists(plate_path):
                    placa_future = executor.submit(process_plate_image, plate_path, plate_image_filename)
        
        # Obtener resultados
        tiquete_result = tiquete_future.result() if tiquete_future else {"result": "error", "message": "Error procesando tiquete"}
        placa_result = placa_future.result() if placa_future else {"result": "warning", "message": "No se procesó imagen de placa"}
        
        # Verificar resultado del tiquete
        if tiquete_result.get("result") == "error":
            return jsonify(tiquete_result), 500
        
        # Guardar resultados en sesión
        session['parsed_data'] = tiquete_result.get("parsed_data", {})
        if placa_result.get("result") != "error":
            session['plate_text'] = placa_result.get("plate_text")
        else:
            session['plate_error'] = placa_result.get("message")
        
        return jsonify({"result": "ok"})
        
    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "result": "error", 
            "message": f"Error al procesar la imagen: {str(e)}"
        }), 500

def process_tiquete_image(image_path, filename):
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            response = requests.post(PROCESS_WEBHOOK_URL, files=files)
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de tiquete: {response.text}")
            return {"result": "error", "message": f"Error del webhook de tiquete: {response.text}"}
            
        response_text = response.text.strip()
        if not response_text:
            logger.error("Respuesta vacía del webhook de tiquete")
            return {"result": "error", "message": "Respuesta vacía del webhook de tiquete."}
            
        parsed_data = parse_markdown_response(response_text)
        if not parsed_data:
            logger.error("No se pudieron parsear los datos de la respuesta del tiquete")
            return {"result": "error", "message": "No se pudieron parsear los datos del tiquete."}
        
        return {"result": "ok", "parsed_data": parsed_data}
        
    except Exception as e:
        logger.error(f"Error procesando imagen de tiquete: {str(e)}")
        return {"result": "error", "message": str(e)}

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

@app.route('/review', methods=['GET'])
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
        'review.html',
        image_filename=image_filename,
        parsed_data=parsed_data,
        timestamp=timestamp,
        plate_image_filename=plate_image_filename,
        plate_text=plate_text,
        plate_error=plate_error
    )

@app.route('/reprocess_plate', methods=['POST'])
def reprocess_plate():
    try:
        plate_image_filename = session.get('plate_image_filename')
        if not plate_image_filename:
            return jsonify({
                'success': False,
                'message': 'No hay imagen de placa para procesar'
            })
        
        plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_image_filename)
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

@app.route('/update_data', methods=['POST'])
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
                "redirect": url_for('review', _external=True)
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
                "redirect": url_for('review', _external=True)
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
            
            response_data = json.loads(response_text)
            
        except (requests.exceptions.Timeout, json.JSONDecodeError) as e:
            logger.error(f"Error en la comunicación con el webhook: {str(e)}")
            # Crear respuesta local con los datos del formulario
            response_data = {
                "status": "success",
                "data": table_data
            }
            
        # Guardar datos en la sesión
        session['webhook_response'] = response_data
        session['table_data'] = table_data
        session.modified = True
        
        if response_data.get('status') == 'success':
            logger.info("Datos guardados en sesión, redirigiendo a revalidation_success")
            return jsonify({
                "status": "success",
                "redirect": url_for('revalidation_success', _external=True)
            })
        else:
            logger.error("Error en la validación")
            return jsonify({
                "status": "error",
                "message": response_data.get('message', 'Error en la validación'),
                "redirect": url_for('revalidation_results', _external=True)
            })
            
    except Exception as e:
        logger.error(f"Error en update_data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e),
            "redirect": url_for('review', _external=True)
        }), 500

@app.route('/processing', methods=['GET'])
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
    qr_path = os.path.join(app.static_folder, qr_filename)
    qr_img.save(qr_path)
    
    # Retornar sólo el nombre, para usarlo en la plantilla
    return qr_filename


def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
    try:
        logger.info("Iniciando generación de PDF")
        logger.info(f"Datos de revalidación: {revalidation_data}")
        
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
        
        qr_filename = f"qr_{qr_data['codigo']}_{int(time.time())}.png"
        qr_path = os.path.join(app.static_folder, qr_filename)
        utils.generate_qr(qr_data, qr_path)
        
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
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        HTML(
            string=rendered,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        logger.info(f"PDF generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error en generate_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception(f"Error generando PDF: {str(e)}")

@app.route('/register', methods=['POST'])
def register():
    try:
        logger.info("Iniciando proceso de registro")
        
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
        
        # Generar QR usando la utilidad
        utils.generate_qr(qr_data, qr_filename)
        session['qr_filename'] = qr_filename
        
        # Generar URL del código QR
        base_url = "http://localhost:5002"  # Ajusta según tu configuración
        url_qr = f"{base_url}/guias/guia_{codigo_guia}.html"
        
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
                    "url_qr": f"http://localhost:5002/guias/guia_{codigo_guia}.html",
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


    
@app.route('/review_pdf')
def review_pdf():
    """
    Muestra una página con el enlace del PDF generado y el código QR.
    """
    pdf_filename = session.get('pdf_filename')
    qr_filename = session.get('qr_filename')
    image_filename = session.get('image_filename')
    plate_image_filename = session.get('plate_image_filename')
    codigo_guia = session.get('codigo_guia')
    
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
        nota = webhook_data.get('nota', 'No disponible')
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
        nota = session.get('nota', 'No disponible')
    
    # Obtener fecha y hora de registro
    fecha_registro = session.get('fecha_registro', datetime.now().strftime("%d/%m/%Y"))
    hora_registro = session.get('hora_registro', datetime.now().strftime("%H:%M:%S"))
    plate_text = session.get('plate_text', '')
    
    if not pdf_filename or not qr_filename:
        return render_template('error.html', message="No se encontró el PDF o QR generado.")
    
    # Agregar logs para depuración
    logger.info(f"Datos para PDF: nombre={nombre_agricultor}, codigo={codigo}, racimos={racimos}, nota={nota}")
    
    # Recuperar indicadores de campos modificados
    nombre_agricultor_modificado = session.get('nombre_agricultor_modificado', False)
    codigo_modificado = session.get('codigo_modificado', False)
    cantidad_de_racimos_modificado = session.get('cantidad_de_racimos_modificado', False)
    placa_modificado = session.get('placa_modificado', False)
    acarreo_modificado = session.get('acarreo_modificado', False)
    cargo_modificado = session.get('cargo_modificado', False)
    transportador_modificado = session.get('transportador_modificado', False)
    fecha_modificado = session.get('fecha_modificado', False)
    
    return render_template('review_pdf.html', 
                          pdf_filename=pdf_filename,
                          qr_filename=qr_filename,
                          image_filename=image_filename,
                          plate_image_filename=plate_image_filename,
                          codigo_guia=codigo_guia,
                          nombre_agricultor=nombre_agricultor,
                          codigo=codigo,
                          racimos=racimos,
                          placa=placa,
                          acarreo=acarreo,
                          cargo=cargo,
                          transportador=transportador,
                          fecha_tiquete=fecha_tiquete,
                          fecha_registro=fecha_registro,
                          hora_registro=hora_registro,
                          plate_text=plate_text,
                          nota=nota,
                          nombre_agricultor_modificado=nombre_agricultor_modificado,
                          codigo_modificado=codigo_modificado,
                          cantidad_de_racimos_modificado=cantidad_de_racimos_modificado,
                          placa_modificado=placa_modificado,
                          acarreo_modificado=acarreo_modificado,
                          cargo_modificado=cargo_modificado, 
                          transportador_modificado=transportador_modificado,
                          fecha_modificado=fecha_modificado)

@app.route('/test_webhook', methods=['GET'])
def test_webhook():
    """
    Ruta de prueba para verificar la conectividad con el webhook.
    """
    try:
        response = requests.get(PROCESS_WEBHOOK_URL)
        return jsonify({
            "status": "webhook accessible" if response.status_code == 200 else "webhook error",
            "status_code": response.status_code,
            "response": response.text
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', message="Página no encontrada."), 404

@app.route('/test_revalidation', methods=['GET'])
def test_revalidation():
    test_payload = {
        "modificaciones": [
            {
                "campo": "Nombre del Agricultor",
                "valor_anterior": "Test Nombre",
                "valor_modificado": "Test Modificado"
            }
        ]
    }
    
    try:
        response = requests.post(
            REVALIDATION_WEBHOOK_URL,
            json=test_payload,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify({
            "status": response.status_code,
            "response": response.text,
            "sent_payload": test_payload
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/revalidation_results')
def revalidation_results():
    """
    Renderiza la página de resultados de revalidación
    """
    return render_template('revalidation_results.html')

@app.route('/revalidation_success')
def revalidation_success():
    """
    Renderiza la página de éxito de revalidación
    """
    webhook_response = session.get('webhook_response', {})
    table_data = session.get('table_data', [])
    
    if not webhook_response or not webhook_response.get('data'):
        return redirect(url_for('review'))
        
    data = webhook_response['data']
    
    # Determinar qué campos fueron modificados
    modified_fields = {}
    for row in table_data:
        campo = row.get('campo')
        original = row.get('original')
        sugerido = row.get('sugerido')
        if original != sugerido:
            modified_fields[campo] = True
    
    # Guardar los indicadores de campos modificados en la sesión
    session['nombre_agricultor_modificado'] = modified_fields.get('Nombre del Agricultor', False)
    session['codigo_modificado'] = modified_fields.get('Código', False)
    session['cantidad_de_racimos_modificado'] = modified_fields.get('Cantidad de Racimos', False)
    session['placa_modificado'] = modified_fields.get('Placa', False)
    session['acarreo_modificado'] = modified_fields.get('Se Acarreó', False)
    session['cargo_modificado'] = modified_fields.get('Se Cargó', False)
    session['transportador_modificado'] = modified_fields.get('Transportador', False)
    session['fecha_modificado'] = modified_fields.get('Fecha', False)
    session.modified = True
    
    # Logging para verificar
    logger.info(f"Campos modificados: {modified_fields}")
    logger.info(f"Guardados en sesión: nombre_modificado={session.get('nombre_agricultor_modificado')}, codigo_modificado={session.get('codigo_modificado')}")
    
    return render_template('revalidation_success.html',
                         image_filename=session.get('image_filename'),
                         nombre_agricultor=data.get('nombre_agricultor'),
                         codigo=data.get('codigo'),
                         racimos=data.get('racimos'),
                         placa=data.get('placa'),
                         acarreo=data.get('acarreo'),
                         cargo=data.get('cargo'),
                         transportador=data.get('transportador'),
                         fecha_tiquete=data.get('fecha_tiquete'),
                         hora_registro=datetime.now().strftime('%H:%M:%S'),
                         nota=data.get('nota'),
                         plate_text=session.get('plate_text'),
                         nombre_agricultor_modificado=modified_fields.get('Nombre del Agricultor'),
                         codigo_modificado=modified_fields.get('Código'),
                         cantidad_de_racimos_modificado=modified_fields.get('Cantidad de Racimos'),
                         placa_modificado=modified_fields.get('Placa'),
                         acarreo_modificado=modified_fields.get('Se Acarreó'),
                         cargo_modificado=modified_fields.get('Se Cargó'),
                         transportador_modificado=modified_fields.get('Transportador'),
                         fecha_modificado=modified_fields.get('Fecha'))

@app.route('/pesaje/<codigo>', methods=['GET'])
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
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
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje', codigo=codigo_guia_completo))

        # Renderizar template de pesaje
        return render_template('pesaje.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje"), 500

@app.route('/pesaje-inicial/<codigo>', methods=['GET', 'POST'])
def pesaje_inicial(codigo):
    """Manejo de pesaje inicial (directo o virtual)"""
    pass

@app.route('/clasificacion/<codigo>', methods=['GET'])
def clasificacion(codigo):
    """
    Maneja la vista de clasificación y el procesamiento de la misma
    """
    try:
        logger.info(f"Iniciando vista de clasificación para código: {codigo}")
        
        # Revisar la sesión actual para verificar si hay datos de peso
        peso_bruto_session = session.get('peso_bruto')
        estado_actual_session = session.get('estado_actual')
        
        logger.info(f"Datos de sesión: peso_bruto={peso_bruto_session}, estado_actual={estado_actual_session}")
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            logger.info(f"Código guía completo obtenido del archivo HTML: {codigo_guia_completo}")
        else:
            codigo_guia_completo = codigo
            logger.info(f"No se encontró archivo HTML, usando código original: {codigo_guia_completo}")

        # Verificar si hay datos en la sesión para peso
        tiene_peso_en_sesion = False
        if peso_bruto_session and estado_actual_session == 'pesaje_completado':
            tiene_peso_en_sesion = True
            logger.info(f"La sesión tiene datos de peso: {peso_bruto_session}, estado: {estado_actual_session}")

        # Obtener datos de la guía usando el código completo
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia_completo}")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        logger.info(f"Datos de guía obtenidos: peso_bruto={datos_guia.get('peso_bruto')}, estado_actual={datos_guia.get('estado_actual')}")

        # Si hay peso en la sesión, asegurarnos de que datos_guia también lo tenga
        if tiene_peso_en_sesion and not datos_guia.get('peso_bruto'):
            logger.info(f"Actualizando datos_guia con información de la sesión")
            datos_guia['peso_bruto'] = peso_bruto_session
            datos_guia['tipo_pesaje'] = session.get('tipo_pesaje')
            datos_guia['hora_pesaje'] = session.get('hora_pesaje')
            datos_guia['fecha_pesaje'] = session.get('fecha_pesaje')
            datos_guia['estado_actual'] = 'pesaje_completado'
            
            # También actualizamos el archivo HTML
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            html_filename = f'guia_{codigo_guia_completo}.html'
            html_path = os.path.join(app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Archivo de guía actualizado con datos de sesión: {html_path}")

        # Verificar que el pesaje esté completado (desde datos_guia o desde la sesión)
        tiene_peso_en_guia = datos_guia.get('peso_bruto') and datos_guia.get('estado_actual') == 'pesaje_completado'
        pesaje_completado = tiene_peso_en_guia or tiene_peso_en_sesion
        
        logger.info(f"Verificación de pesaje completado: {pesaje_completado} (guía: {tiene_peso_en_guia}, sesión: {tiene_peso_en_sesion})")
        
        if not pesaje_completado:
            logger.error(f"Pesaje no completado para guía {codigo_guia_completo}. Estado en guía: {datos_guia.get('estado_actual')}, Estado en sesión: {estado_actual_session}")
            return render_template('error.html', 
                                message="¡Error! Debe completar el proceso de pesaje antes de realizar la clasificación"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            logger.info(f"Redirigiendo a URL con código guía completo: {codigo_guia_completo}")
            return redirect(url_for('clasificacion', codigo=codigo_guia_completo))

        # Renderizar template de clasificación
        return render_template('clasificacion.html', 
                            codigo=datos_guia.get('codigo'),
                            codigo_guia=codigo_guia_completo,
                            nombre=datos_guia.get('nombre'),
                            cantidad_racimos=datos_guia.get('cantidad_racimos'),
                            peso_bruto=datos_guia.get('peso_bruto'),
                            tipo_pesaje=datos_guia.get('tipo_pesaje'),
                            fecha_registro=datos_guia.get('fecha_registro'),
                            hora_registro=datos_guia.get('hora_registro'),
                            fecha_pesaje=datos_guia.get('fecha_pesaje'),
                            hora_pesaje=datos_guia.get('hora_pesaje'),
                            transportador=datos_guia.get('transportador'),
                            placa=datos_guia.get('placa'),
                            guia_transito=datos_guia.get('guia_transito'))
                           
    except Exception as e:
        logger.error(f"Error en clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando clasificación"), 500

@app.route('/pesaje-tara/<codigo>', methods=['GET', 'POST'])
def pesaje_tara(codigo):
    """
    Maneja la vista de pesaje de tara y el procesamiento del mismo
    """
    try:
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
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
        if not datos_guia.get('clasificacion_completa'):
            return render_template('error.html', 
                                message="Debe completar el proceso de clasificación antes de realizar el pesaje de tara"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje_tara', codigo=codigo_guia_completo))

        # Renderizar template de pesaje de tara
        return render_template('pesaje_tara.html',
                            codigo=codigo_guia_completo,
                            datos=datos_guia)

    except Exception as e:
        logger.error(f"Error en pesaje de tara: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje de tara"), 500

@app.route('/procesar_pesaje_tara_directo', methods=['POST'])
def procesar_pesaje_tara_directo():
    try:
        if 'foto' not in request.files:
            return jsonify({'success': False, 'message': 'No se encontró la imagen'})
        
        foto = request.files['foto']
        codigo_guia = request.form.get('codigo_guia')
        
        if not foto:
            return jsonify({'success': False, 'message': 'Archivo no válido'})
            
        # Guardar la imagen temporalmente
        filename = secure_filename(foto.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
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
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
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
                session['imagen_pesaje_tara'] = filename
                
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

@app.route('/procesar_pesaje_directo', methods=['POST'])
def procesar_pesaje_directo():
    try:
        if 'foto' not in request.files:
            return jsonify({'success': False, 'message': 'No se encontró la imagen'})
        
        foto = request.files['foto']
        codigo_guia = request.form.get('codigo_guia')
        
        if not foto:
            return jsonify({'success': False, 'message': 'Archivo no válido'})
            
        # Guardar la imagen temporalmente
        filename = secure_filename(foto.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
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
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            # Enviar tanto el código de proveedor como el código de guía
            data = {
                'codigo_proveedor': codigo_proveedor,
                'codigo_guia': codigo_guia
            }
            
            logger.info(f"Enviando al webhook con datos: {data}")
            response = requests.post(PESAJE_WEBHOOK_URL, files=files, data=data)
        
        logger.info(f"Respuesta del webhook: {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({
                'success': False,
                'message': f"Error del webhook: {response.text}"
            }), 500
            
        # Procesar respuesta del webhook
        response_text = response.text.strip()
        if not response_text:
            return jsonify({
                'success': False,
                'message': "Respuesta vacía del webhook."
            }), 500
            
        # Buscar el peso en la respuesta usando diferentes patrones
        peso = None
        patrones = [
            r'El peso tara es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?',
            r'El peso bruto es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?',
            r'peso bruto es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?',
            r'peso es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?',
            r'Exitoso!\s*(\d+(?:\.\d+)?)\s*(?:tm)?',
            r'(\d+(?:\.\d+)?)\s*(?:tm)?'
        ]
        
        for patron in patrones:
            match = re.search(patron, response_text, re.IGNORECASE)
            if match:
                peso = match.group(1)
                break
        
        if peso:
            session['imagen_pesaje'] = filename
            return jsonify({
                'success': True,
                'peso': peso,
                'message': 'Peso detectado correctamente'
            })
        else:
            logger.error(f"No se pudo extraer el peso de la respuesta: {response_text}")
            return jsonify({
                'success': False,
                'message': 'No se pudo extrair el peso de la respuesta'
            })
            
    except Exception as e:
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/solicitar_autorizacion_pesaje', methods=['POST'])
def solicitar_autorizacion_pesaje():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        comentarios = data.get('comentarios')
        
        if not codigo_guia or not comentarios:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Generar código de autorización aleatorio
        codigo_autorizacion = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Guardar el código en el diccionario con tiempo de expiración
        codigos_autorizacion[codigo_guia] = {
            'codigo': codigo_autorizacion,
            'expira': datetime.now() + timedelta(minutes=30)  # Expira en 30 minutos
        }
        
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
        
        # Generar URL de la guía
        url_guia = url_for('pesaje', codigo=codigo_guia, _external=True)
        
        # Enviar solicitud al webhook de autorización
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'url_guia': url_guia,
                'comentarios': comentarios,
                'codigo_autorizacion': codigo_autorizacion
            }
        )
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Error al enviar la solicitud de autorización'
            })
            
        return jsonify({
            'success': True,
            'message': 'Solicitud enviada correctamente'
            })
            
    except Exception as e:
        logger.error(f"Error en solicitud de autorización: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/validar_codigo_autorizacion', methods=['POST'])
def validar_codigo_autorizacion():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        codigo_autorizacion = data.get('codigoAutorizacion')
        
        if not codigo_guia or not codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Verificar si existe el código para esta guía
        if codigo_guia not in codigos_autorizacion:
            return jsonify({
                'success': False,
                'message': 'No hay código de autorización pendiente para esta guía'
            })
            
        # Obtener datos del código
        auth_data = codigos_autorizacion[codigo_guia]
        
        # Verificar si el código ha expirado
        if datetime.now() > auth_data['expira']:
            del codigos_autorizacion[codigo_guia]
            return jsonify({
                'success': False,
                'message': 'El código de autorización ha expirado'
            })
            
        # Verificar el código
        if auth_data['codigo'] != codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Código de autorización inválido'
            })
            
        # Si el código es válido, eliminarlo para que no se pueda usar nuevamente
        del codigos_autorizacion[codigo_guia]
        
        return jsonify({
            'success': True,
            'message': 'Código validado correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error en validación de código: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/registrar_peso_directo', methods=['POST'])
def registrar_peso_directo():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        if not codigo_guia or not peso_bruto:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
        
        # Registrar el peso en el sistema
        now = datetime.now()
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = 'directo'
        session['hora_pesaje'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje'] = now.strftime('%d/%m/%Y')
        session['estado_actual'] = 'pesaje_completado'
        
        # Enviar datos al webhook de registro de peso
        response = requests.post(
            REGISTRO_PESO_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'directo',
                'fecha_pesaje': now.strftime('%d/%m/%Y'),
                'hora_pesaje': now.strftime('%H:%M:%S'),
                'estado': 'pesaje_completado'
            }
        )

        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Error al registrar el peso'
            })
        
        # Actualizar los datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia:
            datos_guia['estado_actual'] = 'pesaje_completado'
            datos_guia['peso_bruto'] = peso_bruto
            datos_guia['tipo_pesaje'] = 'directo'
            datos_guia['fecha_pesaje'] = now.strftime('%d/%m/%Y')
            datos_guia['hora_pesaje'] = now.strftime('%H:%M:%S')
            
            # Generar el HTML actualizado de la guía
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            # Guardar el archivo HTML actualizado
            html_filename = f'guia_{codigo_guia}.html'
            html_path = os.path.join(app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        
        return jsonify({
            'success': True,
            'message': 'Peso registrado correctamente',
            'redirect_url': url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        })
        
    except Exception as e:
        logger.error(f"Error en registro de peso directo: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        logger.info(f"Iniciando registro de peso virtual para guía: {codigo_guia}, peso: {peso_bruto}")
        
        if not codigo_guia or not peso_bruto:
            logger.error(f"Faltan datos requeridos: codigo_guia={codigo_guia}, peso_bruto={peso_bruto}")
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Obtener fecha y hora actual
        now = datetime.now()
        
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
        
        # Actualizar los valores en la sesión
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = 'virtual'
        session['hora_pesaje'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje'] = now.strftime('%d/%m/%Y')
        session['estado_actual'] = 'pesaje_completado'
        
        # Forzar que la sesión se guarde inmediatamente
        session.modified = True
        
        # Loguear los valores actuales de la sesión
        logger.info(f"Valores de la sesión después de la actualización:")
        logger.info(f"  peso_bruto: {session.get('peso_bruto')}")
        logger.info(f"  tipo_pesaje: {session.get('tipo_pesaje')}")
        logger.info(f"  hora_pesaje: {session.get('hora_pesaje')}")
        logger.info(f"  fecha_pesaje: {session.get('fecha_pesaje')}")
        logger.info(f"  estado_actual: {session.get('estado_actual')}")
        
        # Generar URL de la guía
        url_guia = url_for('serve_guia', filename=f'guia_{codigo_guia}.html', _external=True)
        
        # Enviar datos al webhook de registro de peso
        response = requests.post(
            REGISTRO_PESO_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'url_guia': url_guia,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'virtual',
                'fecha_pesaje': now.strftime('%d/%m/%Y'),
                'hora_pesaje': now.strftime('%H:%M:%S'),
                'estado': 'pesaje_completado'  # Incluimos el estado en el webhook
            }
        )

        if response.status_code != 200:
            logger.error(f"Error al enviar datos al webhook: {response.status_code}, {response.text}")
            return jsonify({
                'success': False,
                'message': 'Error al registrar el peso'
            })
        
        # En lugar de obtener datos de la guía, construimos un diccionario directamente con los valores
        # de la sesión para asegurar que los valores más recientes se usen
        try:
            # Primero obtenemos los datos base de la guía
            datos_guia_base = utils.get_datos_guia(codigo_guia)
            if not datos_guia_base:
                logger.error(f"No se pudieron obtener los datos base de la guía: {codigo_guia}")
                return jsonify({
                    'success': False,
                    'message': 'No se pudieron obtener los datos de la guía'
                })
            
            # Aseguramos que los datos de pesaje estén actualizados con los valores de la sesión
            datos_guia = datos_guia_base.copy()
            datos_guia['estado_actual'] = session.get('estado_actual', 'pesaje_completado')
            datos_guia['peso_bruto'] = session.get('peso_bruto', peso_bruto)
            datos_guia['tipo_pesaje'] = session.get('tipo_pesaje', 'virtual')
            datos_guia['fecha_pesaje'] = session.get('fecha_pesaje', now.strftime('%d/%m/%Y'))
            datos_guia['hora_pesaje'] = session.get('hora_pesaje', now.strftime('%H:%M:%S'))
            
            logger.info(f"Datos de guía preparados para actualizar HTML:")
            logger.info(f"  estado_actual: {datos_guia['estado_actual']}")
            logger.info(f"  peso_bruto: {datos_guia['peso_bruto']}")
            
            # Generar el HTML actualizado de la guía
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            # Guardar el archivo HTML actualizado
            html_filename = f'guia_{codigo_guia}.html'
            html_path = os.path.join(app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Archivo de guía actualizado: {html_path}")
            
        except Exception as file_error:
            logger.error(f"Error al actualizar archivo HTML: {str(file_error)}")
            logger.error(traceback.format_exc())

        # Redirigir al usuario a la página de resultados de pesaje (modificado)
        return jsonify({
            'success': True,
            'message': 'Peso registrado correctamente',
            'redirect_url': url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        })
    except Exception as e:
        logger.error(f"Error en registro de peso virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/registrar_clasificacion', methods=['POST'])
def registrar_clasificacion():
    try:
        # 1. Crear directorios si no existen
        racimos_temp_dir = os.path.join(app.static_folder, 'fotos_racimos_temp')
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        os.makedirs(racimos_temp_dir, exist_ok=True)
        os.makedirs(clasificaciones_dir, exist_ok=True)

        # Crear directorio para fotos procesadas
        fotos_procesadas_dir = os.path.join(app.static_folder, 'clasificaciones', 'fotos')
        os.makedirs(fotos_procesadas_dir, exist_ok=True)

        # 2. Obtener datos del formulario
        webhook_data = json.loads(request.form['webhookData'])
        codigo_guia = webhook_data['codigo_guia']
        
        # Asegurarse de que se está usando el código de guía completo
        if '_' not in codigo_guia:
            # Si sólo tenemos el código del proveedor, buscar el código completo
            guias_folder = app.config['GUIAS_FOLDER']
            guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_guia}_*.html'))
            
            if guias_files:
                # Ordenar por fecha de modificación, más reciente primero
                guias_files.sort(key=os.path.getmtime, reverse=True)
                # Extraer el codigo_guia del nombre del archivo más reciente
                latest_guia = os.path.basename(guias_files[0])
                codigo_guia = latest_guia[5:-5]  # Remover 'guia_' y '.html'
                logger.info(f"Usando código guía completo: {codigo_guia}")

        # 3. Guardar las fotos
        fotos_paths = []
        for i in range(1, 4):
            if f'foto{i}' in request.files:
                foto = request.files[f'foto{i}']
                if foto:
                    filename = f"foto{i}_{codigo_guia}.{foto.filename.split('.')[-1]}"
                    filepath = os.path.join(racimos_temp_dir, filename)
                    foto.save(filepath)
                    fotos_paths.append(filepath)

        # 4. Guardar datos de clasificación
        clasificacion_data = {
            'id': f"Clasificacion_{codigo_guia}",
            'fecha_registro': webhook_data['fecha_clasificacion'],
            'hora_registro': webhook_data['hora_clasificacion'],
            'fotos': fotos_paths,
            'estado': 'en_proceso',
            'clasificacion_manual': webhook_data['clasificacion'],
            'clasificacion_automatica': None,
            'resultados_por_foto': {}
        }

        # 5. Guardar en archivo JSON
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)

        # 6. Actualizar estado en la sesión
        session['estado_clasificacion'] = 'en_proceso'
        session['clasificacion_manual'] = webhook_data['clasificacion']
        session['fecha_clasificacion'] = webhook_data['fecha_clasificacion']
        session['hora_clasificacion'] = webhook_data['hora_clasificacion']
        session['codigo_guia_completo'] = codigo_guia

        # 7. Iniciar procesamiento con Roboflow en segundo plano
        # Crear directorio específico para las fotos de esta guía
        guia_fotos_dir = os.path.join(fotos_procesadas_dir, codigo_guia)
        os.makedirs(guia_fotos_dir, exist_ok=True)

        # Iniciar procesamiento en segundo plano
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(process_images_with_roboflow, codigo_guia, fotos_paths, guia_fotos_dir, json_path)

        # 8. Preparar respuesta
        return jsonify({
            'success': True,
            'redirect_url': url_for('ver_resultados_clasificacion', url_guia=codigo_guia)
        })
        
    except Exception as e:
        logger.error(f"Error en registrar_clasificacion: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })

def process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Procesa imágenes a través de la API de Roboflow y actualiza el archivo JSON con los resultados.
    
    Args:
        codigo_guia: El código de la guía
        fotos_paths: Lista de rutas de las fotos a procesar
        guia_fotos_dir: Directorio donde guardar las fotos procesadas
        json_path: Ruta al archivo JSON con los datos de clasificación
    """
    try:
        logger.info(f"Iniciando procesamiento automático para guía: {codigo_guia}")
        
        # Leer el archivo JSON actual
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Inicializar resultados de clasificación automática
        clasificacion_automatica = {
            "racimos_verdes": 0,
            "racimos_maduros": 0,
            "racimos_sobremaduros": 0,
            "racimos_podridos": 0
        }
        
        resultados_por_foto = {}
        tiempo_inicio = time.time()
        
        # Procesar cada foto secuencialmente
        for idx, foto_path in enumerate(fotos_paths, 1):
            try:
                # Guardar una copia de la foto original en el directorio de la guía
                foto_nombre = f"foto_{idx}.jpg"
                foto_destino = os.path.join(guia_fotos_dir, foto_nombre)
                
                # Copiar la imagen original
                from shutil import copyfile
                copyfile(foto_path, foto_destino)
                
                logger.info(f"Procesando imagen {idx}/{len(fotos_paths)}: {foto_path}")
                
                # Redimensionar imagen para asegurar que no sea demasiado grande
                # Roboflow limita las imágenes a 1152x2048
                try:
                    from PIL import Image
                    image = Image.open(foto_path)
                    
                    # Verificar si la imagen necesita redimensionamiento
                    max_width, max_height = 1152, 2048
                    if image.width > max_width or image.height > max_height:
                        # Calcular la relación de aspecto
                        ratio = min(max_width / image.width, max_height / image.height)
                        new_size = (int(image.width * ratio), int(image.height * ratio))
                        
                        # Redimensionar la imagen
                        image = image.resize(new_size, Image.LANCZOS)
                        
                        # Guardar la imagen redimensionada
                        temp_path = f"{foto_path}_resized.jpg"
                        image.save(temp_path, quality=95)
                        logger.info(f"Imagen redimensionada de {image.width}x{image.height} a {new_size[0]}x{new_size[1]}")
                        
                        # Usar la imagen redimensionada para la API
                        foto_path = temp_path
                except Exception as e:
                    logger.warning(f"No se pudo redimensionar la imagen: {e}")
                
                # Convertir la imagen a base64 para enviar en formato JSON
                try:
                    import base64
                    with open(foto_path, 'rb') as image_file:
                        image_bytes = image_file.read()
                        encoded_image = base64.b64encode(image_bytes).decode('utf-8')
                        
                        # Configurar la URL de la API y encabezados según la documentación
                        url = f"https://detect.roboflow.com/infer/workflows/{WORKSPACE_NAME}/{WORKFLOW_ID}"
                        
                        # Enviar la solicitud en el formato esperado por Roboflow
                        headers = {
                            'Content-Type': 'application/json'
                        }
                        
                        # Preparar el cuerpo de la solicitud según la documentación
                        payload = {
                            'api_key': ROBOFLOW_API_KEY,
                            'inputs': {
                                'image': {
                                    'type': 'base64',
                                    'value': encoded_image
                                }
                            }
                        }
                        
                        # Registrar detalles de la solicitud (sin la imagen por razones de espacio)
                        logger.info(f"Enviando solicitud a URL: {url}")
                        
                        # Realizar la solicitud
                        response = requests.post(url, json=payload, headers=headers, timeout=60)
                        
                        # Registrar la respuesta detallada para diagnóstico
                        logger.info(f"Respuesta de Roboflow para imagen {idx}: Código {response.status_code}")
                        logger.info(f"Respuesta Completa: {response.text[:500]}...")  # Primeros 500 caracteres
                        
                        if response.status_code == 200:
                            result = response.json()
                            logger.info(f"Respuesta exitosa de Roboflow para imagen {idx}")
                            
                            # Log para depuración - estructura completa de la respuesta
                            logger.info(f"Estructura de la respuesta: {json.dumps(result, indent=2)[:500]}...")
                            
                            # Añadir log detallado para mejor depuración de los resultados
                            logger.info(f"TODAS LAS CLAVES de la respuesta: {list(result.keys())}")
                            
                            # Si existe la clave 'outputs', verificar sus claves
                            if 'outputs' in result and isinstance(result['outputs'], list) and len(result['outputs']) > 0:
                                logger.info(f"OUTPUTS: Hay {len(result['outputs'])} elementos")
                                for i, output in enumerate(result['outputs']):
                                    if isinstance(output, dict):
                                        logger.info(f"OUTPUT[{i}] CLAVES: {list(output.keys())}")
                                        
                                        # Si hay potholes_detected, reportarlo
                                        if 'potholes_detected' in output:
                                            logger.info(f"potholes_detected en output[{i}]: {output['potholes_detected']}")
                            
                            # Extraer conteos de racimos por categoría
                            detecciones = {
                                "racimos_verdes": 0,
                                "racimos_maduros": 0, 
                                "racimos_sobremaduros": 0,
                                "racimos_podridos": 0
                            }
                            
                            # Extraer racimos detectados y sus conteos
                            # Buscar en el resultado principal primero
                            for key, value in result.items():
                                logger.info(f"Verificando clave: {key}")
                                
                                # Comprobar coincidencias exactas y similares
                                if 'racimo verde' in key.lower() or 'racimos verdes' in key.lower() or 'verde' in key.lower():
                                    detecciones["racimos_verdes"] = int(value)
                                    logger.info(f"Coincidencia para racimos_verdes: {key} = {value}")
                                elif 'racimo maduro' in key.lower() or 'racimos maduros' in key.lower() or 'maduro' in key.lower():
                                    detecciones["racimos_maduros"] = int(value)
                                    logger.info(f"Coincidencia para racimos_maduros: {key} = {value}")
                                elif 'racimo sobremaduro' in key.lower() or 'racimos sobremaduros' in key.lower() or 'sobremaduro' in key.lower():
                                    detecciones["racimos_sobremaduros"] = int(value)
                                    logger.info(f"Coincidencia para racimos_sobremaduros: {key} = {value}")
                                elif 'racimo podrido' in key.lower() or 'racimos podridos' in key.lower() or 'podrido' in key.lower():
                                    detecciones["racimos_podridos"] = int(value)
                                    logger.info(f"Coincidencia para racimos_podridos: {key} = {value}")
                            
                            # Buscar en la estructura de outputs si está disponible
                            if 'outputs' in result and isinstance(result['outputs'], list) and len(result['outputs']) > 0:
                                for output in result['outputs']:
                                    if isinstance(output, dict):
                                        for key, value in output.items():
                                            # Buscar en outputs para posibles coincidencias
                                            if isinstance(value, dict):  # Si el valor es un diccionario, buscar dentro de él
                                                for subkey, subvalue in value.items():
                                                    logger.info(f"Verificando subclave: {subkey}")
                                                    # Comprobar coincidencias en subclaves
                                                    if 'verde' in subkey.lower():
                                                        detecciones["racimos_verdes"] += int(subvalue)
                                                        logger.info(f"Coincidencia para racimos_verdes en subclave: {subkey} = {subvalue}")
                                                    elif 'maduro' in subkey.lower() and 'sobre' not in subkey.lower():
                                                        detecciones["racimos_maduros"] += int(subvalue)
                                                        logger.info(f"Coincidencia para racimos_maduros en subclave: {subkey} = {subvalue}")
                                                    elif 'sobremaduro' in subkey.lower():
                                                        detecciones["racimos_sobremaduros"] += int(subvalue)
                                                        logger.info(f"Coincidencia para racimos_sobremaduros en subclave: {subkey} = {subvalue}")
                                                    elif 'podrido' in subkey.lower():
                                                        detecciones["racimos_podridos"] += int(subvalue)
                                                        logger.info(f"Coincidencia para racimos_podridos en subclave: {subkey} = {subvalue}")
                            
                            # Calcular total de racimos detectados
                            total_racimos = sum(detecciones.values())
                            logger.info(f"Total racimos detectados: {total_racimos}")
                            
                            # Actualizar conteo global
                            for categoria, cantidad in detecciones.items():
                                if cantidad > 0:
                                    clasificacion_automatica[categoria] += cantidad
                            
                            # Guardar resultados para esta foto
                            resultados_por_foto[str(idx)] = {
                                "potholes_detected": total_racimos,
                                "detecciones": detecciones
                            }
                            
                            logger.info(f"Detecciones finales para imagen {idx}: {detecciones}")
                            logger.info(f"Total racimos detectados: {total_racimos}")
                            
                            # Guardar imágenes anotadas si están disponibles
                            if 'annotated_image' in result:
                                try:
                                    # Verificar si es un diccionario o una cadena
                                    if isinstance(result['annotated_image'], dict):
                                        logger.info(f"annotated_image es un diccionario, buscando campo 'value'")
                                        if 'value' in result['annotated_image']:
                                            img_data = base64.b64decode(result['annotated_image']['value'])
                                            img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                            with open(img_path, 'wb') as f:
                                                f.write(img_data)
                                            logger.info(f"Imagen anotada guardada en {img_path} (desde value)")
                                    else:
                                        # Decodificar imagen anotada como cadena normal
                                        img_data = base64.b64decode(result['annotated_image'])
                                        img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                        with open(img_path, 'wb') as f:
                                            f.write(img_data)
                                        logger.info(f"Imagen anotada guardada en {img_path} (desde resultado principal)")
                                except Exception as e:
                                    logger.error(f"Error al guardar imagen anotada del resultado principal: {str(e)}")
                            
                            # Guardar visualización de etiquetas si está disponible
                            if 'label_visualization_1' in result:
                                try:
                                    # Verificar si es un diccionario o una cadena
                                    if isinstance(result['label_visualization_1'], dict):
                                        logger.info(f"label_visualization_1 es un diccionario, buscando campo 'value'")
                                        if 'value' in result['label_visualization_1']:
                                            img_data = base64.b64decode(result['label_visualization_1']['value'])
                                            img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_etiquetas.jpg")
                                            with open(img_path, 'wb') as f:
                                                f.write(img_data)
                                            logger.info(f"Etiquetas guardadas en {img_path} (desde value)")
                                    else:
                                        # Decodificar como cadena normal
                                        img_data = base64.b64decode(result['label_visualization_1'])
                                        img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_etiquetas.jpg")
                                        with open(img_path, 'wb') as f:
                                            f.write(img_data)
                                        logger.info(f"Visualización de etiquetas guardada en {img_path}")
                                except Exception as e:
                                    logger.error(f"Error al guardar visualización de etiquetas: {str(e)}")
                            
                            # Buscar más campos de imágenes en la estructura de respuesta
                            for i, output in enumerate(result.get('outputs', [])):
                                if isinstance(output, dict):
                                    # Intentar extraer imágenes de la salida
                                    logger.info(f"Revisando output[{i}] para imágenes: {list(output.keys())[:10]}")
                                    
                                    # Buscar campos comunes de imágenes
                                    for img_field in ['annotated_image', 'visualization', 'image', 'processed_image']:
                                        if img_field in output:
                                            try:
                                                logger.info(f"Encontrado campo de imagen {img_field}")
                                                # Manejar si es dict o string
                                                if isinstance(output[img_field], dict) and 'value' in output[img_field]:
                                                    img_data = base64.b64decode(output[img_field]['value'])
                                                else:
                                                    img_data = base64.b64decode(output[img_field])
                                                
                                                img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                                with open(img_path, 'wb') as f:
                                                    f.write(img_data)
                                                logger.info(f"Imagen guardada desde output[{i}].{img_field}")
                                                break
                                            except Exception as e:
                                                logger.error(f"Error guardando imagen desde output[{i}].{img_field}: {str(e)}")
                            
                            # Intentar encontrar imágenes anotadas en otras ubicaciones de la respuesta
                            if not os.path.exists(os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")):
                                # Buscar en campos comunes donde la API podría devolver imágenes procesadas
                                for field_name in ['visualization', 'visualizations', 'image', 'processed_image', 'annotated']:
                                    if field_name in result:
                                        try:
                                            # Manejar tanto cadenas base64 como listas de cadenas
                                            if isinstance(result[field_name], list) and len(result[field_name]) > 0:
                                                if isinstance(result[field_name][0], dict) and 'value' in result[field_name][0]:
                                                    img_data = base64.b64decode(result[field_name][0]['value'])
                                                else:
                                                    img_data = base64.b64decode(result[field_name][0])
                                            elif isinstance(result[field_name], dict) and 'value' in result[field_name]:
                                                img_data = base64.b64decode(result[field_name]['value'])
                                            else:
                                                img_data = base64.b64decode(result[field_name])
                                            
                                            img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                            with open(img_path, 'wb') as f:
                                                f.write(img_data)
                                            logger.info(f"Imagen procesada encontrada en campo '{field_name}'")
                                            break
                                        except Exception as e:
                                            logger.error(f"Error procesando campo '{field_name}': {str(e)}")
                                            continue
                except Exception as e:
                    logger.error(f"Error enviando imagen a Roboflow: {str(e)}")
                    logger.error(traceback.format_exc())
                    resultados_por_foto[str(idx)] = {"error": str(e)}
                
                # Eliminar archivos temporales si existen
                if foto_path.endswith("_resized.jpg"):
                    try:
                        os.remove(foto_path)
                    except:
                        pass
            
            except Exception as e:
                logger.error(f"Error procesando imagen {idx}: {str(e)}")
                logger.error(traceback.format_exc())
                resultados_por_foto[str(idx)] = {"error": str(e)}
        
        # Calcular tiempo total de procesamiento
        tiempo_fin = time.time()
        tiempo_procesamiento = round(tiempo_fin - tiempo_inicio, 2)
        
        # Actualizar datos de clasificación
        clasificacion_data['clasificacion_automatica'] = clasificacion_automatica
        clasificacion_data['resultados_por_foto'] = resultados_por_foto
        clasificacion_data['estado'] = 'completado'
        clasificacion_data['workflow_completado'] = True
        clasificacion_data['tiempo_procesamiento'] = f"{tiempo_procesamiento} segundos"
        clasificacion_data['modelo_utilizado'] = f"{WORKSPACE_NAME}/{WORKFLOW_ID}"
        
        # Guardar datos actualizados
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
        
        logger.info(f"Procesamiento automático completado para guía: {codigo_guia}")
        
    except Exception as e:
        logger.error(f"Error en el procesamiento automático: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar actualizar el estado en caso de error
        try:
            with open(json_path, 'r') as f:
                clasificacion_data = json.load(f)
            
            clasificacion_data['estado'] = 'error'
            clasificacion_data['error_mensaje'] = str(e)
            
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
        except Exception as inner_e:
            logger.error(f"Error al actualizar estado en archivo JSON: {str(inner_e)}")


@app.route('/clasificaciones')
def listar_clasificaciones():
    # Redirigir a la nueva ruta
    return redirect('/clasificaciones/lista')

@app.route('/clasificaciones/lista')
def listar_clasificaciones_filtradas():
    try:
        # Obtener parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        estado = request.args.get('estado', '')
        
        clasificaciones = []
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        
        # Asegurar que el directorio existe
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Leer todos los archivos JSON de clasificaciones
        for filename in os.listdir(clasificaciones_dir):
            if filename.startswith('clasificacion_') and filename.endswith('.json'):
                try:
                    with open(os.path.join(clasificaciones_dir, filename), 'r') as f:
                        clasificacion_data = json.load(f)
                    
                    # Extraer el código de guía del nombre del archivo
                    codigo_guia = filename.replace('clasificacion_', '').replace('.json', '')
                    
                    # Obtener datos adicionales de la guía
                    datos_guia = utils.get_datos_guia(codigo_guia)
                    
                    if not datos_guia:
                        logger.warning(f"No se encontraron datos para la guía: {codigo_guia}")
                        continue
                        
                    # Extraer el código del proveedor del código de guía
                    codigo_proveedor_actual = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                    
                    # Preparar los datos para la plantilla
                    item = {
                        'codigo_guia': codigo_guia,
                        'nombre_proveedor': datos_guia.get('nombre', 'No disponible'),
                        'codigo_proveedor': codigo_proveedor_actual,
                        'fecha_clasificacion': clasificacion_data.get('fecha_registro', 'No disponible'),
                        'hora_clasificacion': clasificacion_data.get('hora_registro', 'No disponible'),
                        'cantidad_racimos': datos_guia.get('cantidad_racimos', 'No disponible'),
                        'estado': clasificacion_data.get('estado', 'en_proceso'),
                        'manual_completado': True,  # Si existe el archivo, la clasificación manual está completada
                        'automatica_completado': clasificacion_data.get('clasificacion_automatica') is not None,
                        'automatica_en_proceso': clasificacion_data.get('estado') == 'en_proceso'
                    }
                    
                    # Aplicar filtros
                    if fecha_desde and item['fecha_clasificacion'] < fecha_desde:
                        continue
                    if fecha_hasta and item['fecha_clasificacion'] > fecha_hasta:
                        continue
                    if codigo_proveedor and codigo_proveedor.lower() not in item['codigo_proveedor'].lower():
                        continue
                    if nombre_proveedor and nombre_proveedor.lower() not in item['nombre_proveedor'].lower():
                        continue
                    if estado and estado != item['estado']:
                        continue
                        
                    clasificaciones.append(item)
                except Exception as e:
                    logger.error(f"Error procesando archivo {filename}: {str(e)}")
                    continue
        
        # Ordenar por fecha y hora, más recientes primero
        clasificaciones.sort(key=lambda x: (x['fecha_clasificacion'], x['hora_clasificacion']), reverse=True)
        
        return render_template('clasificaciones_lista.html', 
                               clasificaciones=clasificaciones,
                               filtros={
                                   'fecha_desde': fecha_desde,
                                   'fecha_hasta': fecha_hasta,
                                   'codigo_proveedor': codigo_proveedor,
                                   'nombre_proveedor': nombre_proveedor,
                                   'estado': estado
                               })
    except Exception as e:
        logger.error(f"Error listando clasificaciones: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al listar clasificaciones")

@app.route('/ver_resultados_clasificacion/<url_guia>')
def ver_resultados_clasificacion(url_guia):
    try:
        # Obtener el directorio de clasificaciones
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Construir la ruta al archivo JSON
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
        
        if not os.path.exists(json_path):
            logger.error(f"Archivo de clasificación no encontrado: {json_path}")
            return render_template('error.html', message="Clasificación no encontrada")
        
        # Leer los datos de clasificación
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
            
        # Obtener datos de la guía
        # Asegurarnos de que estamos usando el código de guía completo
        datos_guia = utils.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Datos de guía no encontrados"), 404
            
        # Actualizar datos de la guía con la información de clasificación
        datos_guia.update({
            'clasificacion_completa': True,
            'fecha_clasificacion': clasificacion_data.get('fecha_registro'),
            'hora_clasificacion': clasificacion_data.get('hora_registro'),
            'tipo_clasificacion': 'manual',
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {}),
            'estado_actual': 'clasificacion_completada'
        })
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{url_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Preparar datos para la plantilla de resultados
        # Usar el código guía completo (código_proveedor + fecha + hora)
        template_data = {
            'codigo_guia': url_guia,  # Este es el código de guía completo
            'fecha_registro': datos_guia.get('fecha_registro'),
            'hora_registro': datos_guia.get('hora_registro'),
            'fecha_clasificacion': clasificacion_data.get('fecha_registro'),
            'hora_clasificacion': clasificacion_data.get('hora_registro'),
            'nombre': datos_guia.get('nombre'),
            'cantidad_racimos': datos_guia.get('cantidad_racimos'),
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {})
        }
        
        return render_template('resultados_clasificacion.html', **template_data)
        
    except Exception as e:
        logger.error(f"Error en ver_resultados_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al cargar los resultados de clasificación")

@app.route('/ver_resultados_automaticos/<url_guia>')
def ver_resultados_automaticos(url_guia):
    """
    Muestra los resultados de la clasificación automática para una guía específica.
    """
    try:
        # Directorio de clasificaciones
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        os.makedirs(clasificaciones_dir, exist_ok=True)
        # Ruta al archivo JSON de clasificación
    except Exception as e:
        logger.error(f"Error al crear directorio de clasificaciones: {str(e)}")
        return render_template('error.html', message="Error al acceder a las clasificaciones")
        
    try:
        # Ruta al archivo JSON de clasificación
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
        
        # Verificar si existe el archivo de clasificación
        if not os.path.exists(json_path):
            logger.error(f"No se encontró el archivo de clasificación para la guía: {url_guia}")
            return render_template('error.html', message=f"No se encontró información de clasificación para la guía: {url_guia}")
            
        # Leer los datos de clasificación
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
            
        # Verificar si existe información de clasificación automática
        if 'clasificacion_automatica' not in clasificacion_data or not clasificacion_data['clasificacion_automatica']:
            return render_template('error.html', message="No hay resultados de clasificación automática disponibles para esta guía")
            
        # Obtener datos adicionales de la guía
        codigo_proveedor = url_guia.split('_')[0] if '_' in url_guia else url_guia
        datos_guia = utils.get_datos_guia(url_guia)
        
        if not datos_guia:
            logger.warning(f"No se encontraron datos para la guía: {url_guia}")
            datos_guia = {'nombre': 'No disponible', 'cantidad_racimos': 'No disponible'}
        
        # Obtener imágenes procesadas de clasificación si existen
        imagenes_procesadas = []
        fotos_dir = os.path.join(app.static_folder, 'clasificaciones', 'fotos', url_guia)
        if os.path.exists(fotos_dir):
            for i in range(1, 4):  # Buscamos las 3 fotos tomadas durante la clasificación
                foto_original = f"foto_{i}.jpg"
                foto_procesada = f"foto_{i}_procesada.jpg"
                
                ruta_original = os.path.join(fotos_dir, foto_original)
                ruta_procesada = os.path.join(fotos_dir, foto_procesada)
                
                if os.path.exists(ruta_original):
                    imagen = {
                        'numero': i,
                        'original': f"clasificaciones/fotos/{url_guia}/{foto_original}",
                        'procesada': f"clasificaciones/fotos/{url_guia}/{foto_procesada}" if os.path.exists(ruta_procesada) else None,
                        'resultado': clasificacion_data.get('resultados_por_foto', {}).get(str(i), {})
                    }
                    imagenes_procesadas.append(imagen)
            
        # Calcular totales y porcentajes para las categorías
        categorias = clasificacion_data.get('clasificacion_automatica', {})
        total_racimos = datos_guia.get('cantidad_racimos', 0)
        if not isinstance(total_racimos, (int, float)):
            try:
                total_racimos = int(total_racimos)
            except:
                total_racimos = sum(cantidad for categoria, cantidad in categorias.items() if isinstance(cantidad, (int, float)))
        
        resultados_con_porcentaje = {}
        for categoria, cantidad in categorias.items():
            if isinstance(cantidad, (int, float)):
                porcentaje = (cantidad / float(total_racimos) * 100) if float(total_racimos) > 0 else 0
                resultados_con_porcentaje[categoria] = {
                    'cantidad': cantidad,
                    'porcentaje': round(porcentaje, 2)
                }
            else:
                resultados_con_porcentaje[categoria] = cantidad
            
        # Preparar datos para la plantilla
        template_data = {
            'codigo_guia': url_guia,
            'nombre_proveedor': datos_guia.get('nombre', 'No disponible'),
            'codigo_proveedor': codigo_proveedor,
            'cantidad_racimos': total_racimos,
            'fecha_registro': clasificacion_data.get('fecha_registro', 'No disponible'),
            'hora_registro': clasificacion_data.get('hora_registro', 'No disponible'),
            'resultados_automaticos': resultados_con_porcentaje,
            'imagenes_procesadas': imagenes_procesadas,
            'total_racimos_detectados': sum(cantidad for categoria, cantidad in categorias.items() if isinstance(cantidad, (int, float))),
            'workflow_completado': clasificacion_data.get('workflow_completado', False),
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'No disponible'),
            'modelo_utilizado': clasificacion_data.get('modelo_utilizado', 'No especificado')
        }
        
        # Renderizar la plantilla con los datos
        try:
            return render_template('resultados_automaticos.html', **template_data)
        except Exception as e:
            logger.error(f"Error al mostrar resultados automáticos: {str(e)}")
            logger.error(traceback.format_exc())
            return render_template('error.html', message="Error al mostrar los resultados de clasificación automática")
    except Exception as e:
        logger.error(f"Error procesando datos de clasificación automática: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al procesar los datos de clasificación automática")

@app.route('/ver_resultados_pesaje/<codigo_guia>')
def ver_resultados_pesaje(codigo_guia):
    """
    Muestra los resultados del pesaje para una guía específica.
    """
    try:
        logger.info(f"Mostrando resultados de pesaje para guía: {codigo_guia}")
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el pesaje está completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            flash("El pesaje no ha sido completado para esta guía.", "warning")
            return redirect(url_for('pesaje', codigo=codigo_guia))
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para la plantilla
        imagen_pesaje = None
        if datos_guia.get('imagen_peso'):
            imagen_pesaje = url_for('static', filename=f'uploads/{datos_guia["imagen_peso"]}')
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        return render_template('resultados_pesaje.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
            transportador=datos_guia.get('transportador', 'No disponible'),
            placa=datos_guia.get('placa', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            tipo_pesaje=datos_guia.get('tipo_pesaje', 'No disponible'),
            fecha_pesaje=datos_guia.get('fecha_pesaje', 'No disponible'),
            hora_pesaje=datos_guia.get('hora_pesaje', 'No disponible'),
            racimos=datos_guia.get('racimos', 'No disponible'),
            codigo_guia_transporte_sap='',  # Nuevo campo para código guía transporte SAP
            imagen_pesaje=imagen_pesaje,
            qr_code=qr_code
        )
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/generar_pdf_pesaje/<codigo_guia>')
def generar_pdf_pesaje(codigo_guia):
    """
    Genera un PDF con los resultados del pesaje.
    """
    try:
        logger.info(f"Generando PDF de pesaje para guía: {codigo_guia}")
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el pesaje está completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            flash("El pesaje no ha sido completado para esta guía.", "warning")
            return redirect(url_for('pesaje', codigo=codigo_guia))
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para el PDF
        imagen_pesaje = None
        if datos_guia.get('imagen_peso'):
            imagen_pesaje = url_for('static', filename=f'uploads/{datos_guia["imagen_peso"]}', _external=True)
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}', _external=True)
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF usando el mismo template que la vista
        html = render_template('pesaje_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
            transportador=datos_guia.get('transportador', 'No disponible'),
            placa=datos_guia.get('placa', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            tipo_pesaje=datos_guia.get('tipo_pesaje', 'No disponible'),
            fecha_pesaje=datos_guia.get('fecha_pesaje', 'No disponible'),
            hora_pesaje=datos_guia.get('hora_pesaje', 'No disponible'),
            racimos=datos_guia.get('racimos', 'No disponible'),
            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', ''),
            imagen_pesaje=imagen_pesaje,
            qr_code=qr_code,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion
        )
        
        try:
            # Configuración para pdfkit
            options = {
                'page-size': 'Letter',
                'encoding': 'UTF-8',
                'margin-top': '0.5in',
                'margin-right': '0.5in',
                'margin-bottom': '0.5in',
                'margin-left': '0.5in',
                'dpi': 300,
                'disable-smart-shrinking': True
            }
            
            # Intentar encontrar el binario de wkhtmltopdf con which
            wkhtmltopdf_path = None
            try:
                import subprocess
                result = subprocess.run(['which', 'wkhtmltopdf'], capture_output=True, text=True)
                if result.returncode == 0:
                    wkhtmltopdf_path = result.stdout.strip()
                    logger.info(f"wkhtmltopdf encontrado en: {wkhtmltopdf_path}")
            except Exception as e:
                logger.warning(f"Error al buscar wkhtmltopdf: {str(e)}")
            
            # Si hay una ruta válida, crear configuración personalizada
            if wkhtmltopdf_path:
                config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                pdf = pdfkit.from_string(html, False, options=options, configuration=config)
            else:
                # Si no se encuentra wkhtmltopdf, intentar sin configuración específica
                pdf = pdfkit.from_string(html, False, options=options)
            
            # Preparar respuesta
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=pesaje_{codigo_guia}.pdf'
            
            return response
            
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF con pdfkit: {str(pdf_error)}")
            
            # Fallback method - Redirect to rendering the template directly
            flash("Generando versión imprimible del documento.", "info")
            return render_template('pesaje_print_view.html',
                codigo_guia=codigo_guia,
                codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
                nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
                transportador=datos_guia.get('transportador', 'No disponible'),
                placa=datos_guia.get('placa', 'No disponible'),
                peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
                tipo_pesaje=datos_guia.get('tipo_pesaje', 'No disponible'),
                fecha_pesaje=datos_guia.get('fecha_pesaje', 'No disponible'),
                hora_pesaje=datos_guia.get('hora_pesaje', 'No disponible'),
                racimos=datos_guia.get('racimos', 'No disponible'),
                codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', ''),
                imagen_pesaje=imagen_pesaje,
                qr_code=qr_code,
                fecha_generacion=fecha_generacion,
                hora_generacion=hora_generacion
            )
            
    except Exception as e:
        logger.error(f"Error al generar PDF de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar el PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_pesaje', codigo_guia=codigo_guia))

@app.route('/pesajes', methods=['GET'])
def lista_pesajes():
    """
    Muestra la lista de registros de pesaje.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        tipo_pesaje = request.args.get('tipo_pesaje', '')

        # Preparar lista de pesajes
        pesajes = []
        
        # Verificar si el directorio de guías existe
        guias_dir = os.path.join(app.static_folder, 'guias')
        
        # Obtener últimos registros por guía
        guias_dict = {}
        
        if os.path.exists(guias_dir):
            for filename in os.listdir(guias_dir):
                if filename.startswith('guia_') and filename.endswith('.html'):
                    codigo_guia = filename.replace('guia_', '').replace('.html', '')
                    
                    # Obtener datos de la guía
                    datos = utils.get_datos_guia(codigo_guia)
                    
                    if datos and datos.get('peso_bruto'):  # Solo si tiene peso
                        # Solo filtrar si hay peso_bruto
                        if not datos.get('peso_bruto'):
                            continue
                        
                        # Filtrar por fecha
                        if fecha_desde and fecha_hasta:
                            # Convertir fecha de pesaje a formato comparable (aaaa-mm-dd)
                            try:
                                fecha_obj = datetime.strptime(datos.get('fecha_pesaje', ''), '%d/%m/%Y')
                                fecha_pesaje_str = fecha_obj.strftime('%Y-%m-%d')
                                
                                if fecha_pesaje_str < fecha_desde or fecha_pesaje_str > fecha_hasta:
                                    continue
                            except:
                                # Si hay error al parsear, no filtrar por fecha
                                pass
                        
                        # Filtrar por código de proveedor
                        if codigo_proveedor and codigo_proveedor.lower() not in datos.get('codigo', '').lower():
                            continue
                        
                        # Filtrar por nombre de proveedor
                        if nombre_proveedor and nombre_proveedor.lower() not in datos.get('nombre', '').lower():
                            continue
                        
                        # Filtrar por tipo de pesaje
                        if tipo_pesaje and tipo_pesaje.lower() != datos.get('tipo_pesaje', '').lower():
                            continue
                            
                        # Crear clave única para cada proveedor
                        clave_guia = f"{datos.get('codigo', '')}"
                        
                        # Verificar si ya tenemos un registro para este proveedor
                        if clave_guia in guias_dict:
                            # Convertir fechas para comparar
                            fecha_actual = datetime.strptime(datos.get('fecha_pesaje', '01/01/2000'), '%d/%m/%Y')
                            fecha_existente = datetime.strptime(guias_dict[clave_guia].get('fecha_pesaje', '01/01/2000'), '%d/%m/%Y')
                            
                            # Si la fecha actual es más reciente, reemplazar el registro
                            if fecha_actual > fecha_existente:
                                guias_dict[clave_guia] = datos
                        else:
                            # Si no existe, agregarlo al diccionario
                            guias_dict[clave_guia] = datos
                        
        # Convertir el diccionario a lista
        for datos in guias_dict.values():
            # Añadir información estructurada para la tabla
            pesaje = {
                'codigo_guia': datos.get('codigo_guia', ''),
                'codigo_proveedor': datos.get('codigo', ''),
                'nombre_proveedor': datos.get('nombre', ''),
                'fecha_pesaje': datos.get('fecha_pesaje', ''),
                'hora_pesaje': datos.get('hora_pesaje', ''),
                'tipo_pesaje': datos.get('tipo_pesaje', ''),
                'peso_bruto': datos.get('peso_bruto', '')
            }
            pesajes.append(pesaje)
            
        # Ordenar por fecha más reciente
        pesajes.sort(key=lambda x: datetime.strptime(x['fecha_pesaje'], '%d/%m/%Y') if x['fecha_pesaje'] else datetime(1900, 1, 1), reverse=True)
        
        # Preparar filtros para la plantilla
        filtros = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'tipo_pesaje': tipo_pesaje
        }
        
        return render_template('pesajes_lista.html', pesajes=pesajes, filtros=filtros)
        
    except Exception as e:
        logger.error(f"Error listando pesajes: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al listar pesajes', 'error')
        return redirect(url_for('upload_file'))

@app.route('/registros-entrada', methods=['GET'])
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

        # Preparar lista de registros
        registros = []
        
        # Verificar si el directorio de guías existe
        guias_dir = os.path.join(app.static_folder, 'guias')
        
        # Obtener últimos registros por guía
        guias_dict = {}
        
        if os.path.exists(guias_dir):
            for filename in os.listdir(guias_dir):
                if filename.startswith('guia_') and filename.endswith('.html'):
                    codigo_guia = filename.replace('guia_', '').replace('.html', '')
                    
                    # Obtener datos de la guía usando la función existente
                    datos = utils.get_datos_registro(codigo_guia)
                    
                    if datos:
                        # Filtrar por fecha
                        if fecha_desde and fecha_hasta:
                            # Convertir fecha de registro a formato comparable (aaaa-mm-dd)
                            try:
                                fecha_obj = datetime.strptime(datos.get('fecha_registro', ''), '%d/%m/%Y')
                                fecha_registro_str = fecha_obj.strftime('%Y-%m-%d')
                                
                                if fecha_registro_str < fecha_desde or fecha_registro_str > fecha_hasta:
                                    continue
                            except:
                                # Si hay error al parsear, no filtrar por fecha
                                pass
                        
                        # Filtrar por código de proveedor
                        if codigo_proveedor and codigo_proveedor.lower() not in datos.get('codigo_proveedor', '').lower():
                            continue
                        
                        # Filtrar por nombre de proveedor
                        if nombre_proveedor and nombre_proveedor.lower() not in datos.get('nombre_proveedor', '').lower():
                            continue
                        
                        # Filtrar por placa
                        if placa and placa.lower() not in datos.get('placa', '').lower():
                            continue
                            
                        # Crear clave única para cada registro
                        clave_guia = codigo_guia
                        
                        # Verificar si ya tenemos un registro para este código de guía
                        if clave_guia in guias_dict:
                            # Convertir fechas para comparar (si tienen el mismo código, usar el más reciente)
                            try:
                                fecha_actual = datetime.strptime(datos.get('fecha_registro', '01/01/2000'), '%d/%m/%Y')
                                fecha_existente = datetime.strptime(guias_dict[clave_guia].get('fecha_registro', '01/01/2000'), '%d/%m/%Y')
                                
                                if fecha_actual > fecha_existente:
                                    guias_dict[clave_guia] = datos
                            except:
                                # Si hay error al parsear, usar el registro actual
                                guias_dict[clave_guia] = datos
                        else:
                            guias_dict[clave_guia] = datos
        
        # Convertir el diccionario a lista de registros
        for datos in guias_dict.values():
            # Añadir información estructurada para la tabla
            registro = {
                'codigo_guia': datos.get('codigo_guia', ''),
                'codigo_proveedor': datos.get('codigo_proveedor', ''),
                'nombre_proveedor': datos.get('nombre_proveedor', ''),
                'fecha_registro': datos.get('fecha_registro', ''),
                'hora_registro': datos.get('hora_registro', ''),
                'placa': datos.get('placa', ''),
                'cantidad_racimos': datos.get('cantidad_racimos', ''),
                'transportador': datos.get('transportador', ''),
                'acarreo': datos.get('acarreo', ''),
                'cargo': datos.get('cargo', ''),
                'image_filename': datos.get('image_filename', '')
            }
            registros.append(registro)
            
        # Ordenar por fecha y hora más reciente (combinados)
        def parse_datetime(registro):
            """
            Convierte fecha y hora de un registro a un objeto datetime para ordenamiento.
            Si no hay fecha o hay un error en el formato, devuelve una fecha muy antigua.
            """
            fecha = registro.get('fecha_registro', '')
            hora = registro.get('hora_registro', '')
            
            # Si no hay fecha y/o hora, devolver fecha antigua
            if not fecha or fecha == 'No disponible':
                return datetime(1900, 1, 1)
            
            try:
                # Convertir la fecha a objeto datetime
                fecha_obj = datetime.strptime(fecha, '%d/%m/%Y')
                
                # Si hay hora, combinarla con la fecha
                if hora and hora != 'No disponible':
                    try:
                        # Extraer horas, minutos y segundos
                        if ':' in hora:
                            # Formato HH:MM:SS
                            h, m, s = hora.split(':')
                            return fecha_obj.replace(hour=int(h), minute=int(m), second=int(s))
                        elif len(hora) == 6:
                            # Formato HHMMSS
                            h, m, s = int(hora[0:2]), int(hora[2:4]), int(hora[4:6])
                            return fecha_obj.replace(hour=h, minute=m, second=s)
                    except:
                        # Si hay error al parsear la hora, solo usar la fecha
                        pass
                
                return fecha_obj
            except:
                # En caso de cualquier error de formato, devolver una fecha antigua
                return datetime(1900, 1, 1)
        
        # Ordenar usando la función de parseo de fecha y hora
        registros.sort(key=parse_datetime, reverse=True)
        
        # Preparar filtros para la plantilla
        filtros = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'placa': placa
        }
        
        return render_template('registros_entrada.html', registros=registros, filtros=filtros)
        
    except Exception as e:
        logger.error(f"Error listando registros de entrada: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al listar registros de entrada', 'error')
        return redirect(url_for('upload_file'))

@app.route('/registro-entrada/<codigo_guia>', methods=['GET'])
def ver_registro_entrada(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    try:
        # Obtener datos del registro
        registro = utils.get_datos_registro(codigo_guia)
        
        if not registro:
            flash('Registro no encontrado', 'error')
            return redirect(url_for('lista_registros_entrada'))
        
        return render_template('registro_entrada_detalle.html', registro=registro)
        
    except Exception as e:
        logger.error(f"Error obteniendo detalles del registro: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al obtener detalles del registro', 'error')
        return redirect(url_for('lista_registros_entrada'))

@app.route('/generar-pdf-registro/<codigo_guia>', methods=['GET'])
def generar_pdf_registro(codigo_guia):
    """
    Genera un PDF para un registro de entrada específico.
    """
    try:
        # Obtener datos del registro
        registro = utils.get_datos_registro(codigo_guia)
        
        if not registro:
            flash('Registro no encontrado', 'error')
            return redirect(url_for('lista_registros_entrada'))
        
        # Verificar si el PDF ya existe
        pdf_filename = f"registro_{codigo_guia}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Si el PDF no existe, generarlo
        if not os.path.exists(pdf_path):
            # Obtener información de campos modificados
            modified_fields = registro.get('modified_fields', {})
            
            # Renderizar la plantilla para el PDF
            rendered = render_template(
                'pdf_template.html',
                codigo=registro.get('codigo_proveedor', ''),
                nombre_agricultor=registro.get('nombre_proveedor', ''),
                racimos=registro.get('cantidad_racimos', ''),
                placa=registro.get('placa', ''),
                acarreo=registro.get('acarreo', 'No'),
                cargo=registro.get('cargo', 'No'),
                transportador=registro.get('transportador', ''),
                fecha_tiquete=registro.get('fecha_tiquete', ''),
                hora_registro=registro.get('hora_registro', ''),
                fecha_emision=datetime.now().strftime("%d/%m/%Y"),
                hora_emision=datetime.now().strftime("%H:%M:%S"),
                nota=registro.get('nota', ''),
                qr_filename=registro.get('qr_filename', ''),
                image_filename=registro.get('image_filename', ''),
                # Agregar indicadores de campos modificados
                codigo_modificado=modified_fields.get('codigo', False),
                nombre_agricultor_modificado=modified_fields.get('nombre_agricultor', False),
                cantidad_de_racimos_modificado=modified_fields.get('racimos', False),
                placa_modificado=modified_fields.get('placa', False),
                acarreo_modificado=modified_fields.get('acarreo', False),
                cargo_modificado=modified_fields.get('cargo', False),
                transportador_modificado=modified_fields.get('transportador', False),
                fecha_modificado=modified_fields.get('fecha_tiquete', False)
            )
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Generar PDF
            HTML(
                string=rendered,
                base_url=app.static_folder
            ).write_pdf(pdf_path)
            
            logger.info(f"PDF generado exitosamente: {pdf_filename}")
        
        # Retornar el archivo PDF
        return send_file(pdf_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Error generando PDF del registro: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al generar PDF del registro', 'error')
        return redirect(url_for('lista_registros_entrada'))

@app.route('/process_validated_data', methods=['POST'])
def process_validated_data():
    """
    Procesa los datos validados y genera el PDF final.
    """
    try:
        # Obtener el webhook response guardado en la sesión
        webhook_response = session.get('webhook_response', {})
        webhook_data = webhook_response.get('data', {})
        
        if not webhook_data:
            logger.error("No hay datos validados para procesar")
            return jsonify({
                "status": "error",
                "message": "No hay datos validados"
            }), 400
        
        # Guardar todos los datos relevantes en la sesión para uso posterior
        session['nombre_agricultor'] = webhook_data.get('nombre_agricultor')
        session['codigo'] = webhook_data.get('codigo')
        session['racimos'] = webhook_data.get('racimos')
        session['placa'] = webhook_data.get('placa')
        session['acarreo'] = webhook_data.get('acarreo')
        session['cargo'] = webhook_data.get('cargo')
        session['transportador'] = webhook_data.get('transportador')
        session['fecha_tiquete'] = webhook_data.get('fecha_tiquete')
        session['nota'] = webhook_data.get('nota', '')
        
        # Verificar y registrar el estado de los indicadores de campos modificados
        nombre_agricultor_modificado = session.get('nombre_agricultor_modificado', False)
        codigo_modificado = session.get('codigo_modificado', False)
        cantidad_de_racimos_modificado = session.get('cantidad_de_racimos_modificado', False)
        placa_modificado = session.get('placa_modificado', False)
        acarreo_modificado = session.get('acarreo_modificado', False)
        cargo_modificado = session.get('cargo_modificado', False)
        transportador_modificado = session.get('transportador_modificado', False)
        fecha_modificado = session.get('fecha_modificado', False)
        
        logger.info(f"Indicadores de modificación recuperados: nombre={nombre_agricultor_modificado}, " 
                 f"codigo={codigo_modificado}, racimos={cantidad_de_racimos_modificado}, "
                 f"placa={placa_modificado}, acarreo={acarreo_modificado}, "
                 f"cargo={cargo_modificado}, transportador={transportador_modificado}, "
                 f"fecha={fecha_modificado}")
        
        # Preservar los indicadores de campos modificados
        session['nombre_agricultor_modificado'] = nombre_agricultor_modificado
        session['codigo_modificado'] = codigo_modificado
        session['cantidad_de_racimos_modificado'] = cantidad_de_racimos_modificado
        session['placa_modificado'] = placa_modificado
        session['acarreo_modificado'] = acarreo_modificado
        session['cargo_modificado'] = cargo_modificado
        session['transportador_modificado'] = transportador_modificado
        session['fecha_modificado'] = fecha_modificado
        
        session.modified = True
        
        # Generar código único para la guía
        codigo_guia = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
        session['codigo_guia'] = codigo_guia
        
        # Registro de fecha y hora
        fecha_registro = datetime.now().strftime("%d/%m/%Y")
        hora_registro = datetime.now().strftime("%H:%M:%S")
        
        session['fecha_registro'] = fecha_registro
        session['hora_registro'] = hora_registro
        
        # Generar PDF con los datos validados
        image_filename = session.get('image_filename')
        
        # Preparar los datos para el PDF
        parsed_data = {
            "codigo": webhook_data.get('codigo'),
            "nombre_agricultor": webhook_data.get('nombre_agricultor'),
            "cantidad_de_racimos": webhook_data.get('racimos'),
            "placa": webhook_data.get('placa'),
            "acarreo": webhook_data.get('acarreo'),
            "cargo": webhook_data.get('cargo'),
            "transportador": webhook_data.get('transportador'),
            "fecha": webhook_data.get('fecha_tiquete'),
            "codigo_guia": codigo_guia,
            "nota": webhook_data.get('nota', '')
        }
        
        # Generar PDF
        pdf_filename = utils.generate_pdf(
            parsed_data,
            image_filename,
            fecha_registro,
            hora_registro,
            revalidation_data=None,
            codigo_guia=codigo_guia
        )
        
        # Generar QR
        qr_filename = f"qr_{codigo_guia}.png"
        try:
            utils.generate_qr(codigo_guia, qr_filename)
            # Guardar en sesión
            session['qr_filename'] = qr_filename
        except Exception as e:
            logger.error(f"Error generando QR: {str(e)}")
            # Fallback para asegurar que siempre tenemos un valor para qr_filename
            session['qr_filename'] = "default_qr.png"
        
        session.modified = True
        
        # Guardar en sesión
        session['pdf_filename'] = pdf_filename
        
        # Crear directorio para guardar la guía
        guias_dir = os.path.join(app.static_folder, 'guias')
        if not os.path.exists(guias_dir):
            os.makedirs(guias_dir)
            
        # Guardar una copia del HTML como guía
        guia_path = os.path.join(guias_dir, f"guia_{codigo_guia}.html")
        
        # Datos del registro completo
        datos_registro = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': webhook_data.get('codigo'),
            'nombre_proveedor': webhook_data.get('nombre_agricultor'),
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro,
            'placa': webhook_data.get('placa'),
            'cantidad_racimos': webhook_data.get('racimos'),
            'transportador': webhook_data.get('transportador'),
            'acarreo': webhook_data.get('acarreo'),
            'cargo': webhook_data.get('cargo'),
            'fecha_tiquete': webhook_data.get('fecha_tiquete'),
            'image_filename': image_filename,
            'pdf_filename': pdf_filename,
            'qr_filename': qr_filename,
            'plate_text': session.get('plate_text', ''),
            'nota': webhook_data.get('nota', '')
        }
        
        # Guardar datos en el archivo HTML
        with open(guia_path, 'w') as f:
            f.write(json.dumps(datos_registro))
            
        logger.info(f"Guía generada: {guia_path}")
        
        # Guardamos el estado actual en la sesión
        session['estado_actual'] = 'registro_completado'
        session.modified = True
        
        return jsonify({
            "status": "success",
            "redirect": url_for('review_pdf', _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error procesando datos validados: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
