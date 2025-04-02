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
from bs4 import BeautifulSoup
import db_schema
import copy
import threading
import shutil
import sqlite3

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear tablas de la base de datos si no existen
db_schema.create_tables()
logger.info("Tablas de la base de datos verificadas/creadas correctamente.")

# Configuración de Roboflow
ROBOFLOW_API_KEY = "huyFoCQs7090vfjDhfgK"
# Updated API URL - using the direct API endpoint format
ROBOFLOW_API_URL = "https://api.roboflow.com/workflow"
WORKSPACE_NAME = "enrique-p-workspace"
WORKFLOW_ID = "clasificacion-racimos-3"

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
    GUIAS_DIR='guias',  # Directorio para archivos JSON de guías
    UPLOAD_FOLDER=os.path.join(app.static_folder, 'uploads'),
    PDF_FOLDER=os.path.join(app.static_folder, 'pdfs'),
    EXCEL_FOLDER=os.path.join(app.static_folder, 'excels'),
    SECRET_KEY='tu_clave_secreta_aquí'
)

# Crear directorios necesarios
for folder in ['GUIAS_FOLDER', 'UPLOAD_FOLDER', 'PDF_FOLDER', 'EXCEL_FOLDER']:
    os.makedirs(app.config[folder], exist_ok=True)

# Crear directorio para GUIAS_DIR si no existe
os.makedirs(app.config['GUIAS_DIR'], exist_ok=True)

# Filtro para verificar si un archivo existe en la carpeta static
@app.template_filter('file_exists')
def file_exists_filter(path):
    """
    Filtro Jinja2 para verificar si un archivo existe en la carpeta static
    Uso en plantillas: {% if 'path/to/file.jpg'|file_exists %}
    """
    full_path = os.path.join(app.static_folder, path)
    return os.path.exists(full_path)

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
REGISTRO_PESO_NETO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"  # Using the same URL as REGISTRO_PESO_WEBHOOK_URL for now

codigos_autorizacion = {}


# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    """
    Handles file upload and processing
    """
    if request.method == 'POST':
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
    else:
        # Si es una solicitud GET, redirigir a home
        return redirect(url_for('home'))

@app.route('/index')
def index():
    """
    Renders the index page
    """
    return render_template('index.html')

@app.route('/home')
def home():
    """
    Renders the home page - dashboard for all app sections
    """
    return render_template('home.html')

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
        
        logger.info(f"Iniciando procesamiento de imagen: {image_filename}")
        
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
            logger.error(f"Error en el procesamiento del tiquete: {tiquete_result.get('message')}")
            return jsonify({"result": "error", "message": tiquete_result.get("message", "Error en el procesamiento")}), 400
        
        # Guardar resultados en sesión
        try:
            session['parsed_data'] = tiquete_result.get("parsed_data", {})
            logger.info(f"Datos parseados guardados en sesión: {session['parsed_data']}")
            
            if placa_result.get("result") != "error":
                session['plate_text'] = placa_result.get("plate_text")
                logger.info(f"Texto de placa guardado en sesión: {session['plate_text']}")
            else:
                session['plate_error'] = placa_result.get("message")
                logger.warning(f"Error en placa guardado en sesión: {session['plate_error']}")
            
            return jsonify({"result": "ok", "redirect": "/review"})
        except Exception as e:
            logger.error(f"Error al guardar datos en sesión: {str(e)}")
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
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            response = requests.post(PROCESS_WEBHOOK_URL, files=files)
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de tiquete: {response.text}")
            return {"result": "error", "message": f"Error del webhook de tiquete: {response.text}"}
            
        response_text = response.text.strip()
        # Registra la respuesta raw del webhook para debugging
        logger.info(f"Respuesta raw del webhook de tiquete: {response_text}")
        
        if not response_text:
            logger.error("Respuesta vacía del webhook de tiquete")
            return {"result": "error", "message": "Respuesta vacía del webhook de tiquete."}
            
        parsed_data = parse_markdown_response(response_text)
        # Registra los datos parseados para debugging
        logger.info(f"Datos parseados del tiquete: {parsed_data}")
        
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
        
        # Guardar table_data en la sesión independientemente del resultado del webhook
        session['table_data'] = table_data
        session.modified = True
        
        # Convertir los datos de la tabla a un formato compatible con la plantilla
        formatted_data = {}
        for item in payload["datos"]:
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
            elif campo == "Nota":
                formatted_data["nota"] = valor
                formatted_data["Nota"] = valor  # Mantener ambos formatos
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
        # Log para depuración
        logger.warning("No se encontró webhook_response o data en la sesión. webhook_response: %s", webhook_response)
        logger.warning("table_data: %s", table_data)
        flash('El proceso de revalidación ha sido interrumpido o la sesión ha expirado', 'warning')
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
    logger.info(f"Data para la plantilla: {data}")
    
    # Asegurar que todos los campos necesarios estén presentes
    nombre_agricultor = data.get('Nombre del Agricultor') or data.get('nombre_agricultor', '')
    codigo = data.get('Código') or data.get('codigo', '')
    racimos = data.get('Cantidad de Racimos') or data.get('racimos', '')
    placa = data.get('Placa') or data.get('placa', '')
    acarreo = data.get('Se Acarreó') or data.get('acarreo', '')
    cargo = data.get('Se Cargó') or data.get('cargo', '')
    transportador = data.get('Transportador') or data.get('transportador', '')
    fecha_tiquete = data.get('Fecha') or data.get('fecha_tiquete', '')
    nota = data.get('Nota') or data.get('nota', '')
    
    return render_template('revalidation_success.html',
                         image_filename=session.get('image_filename'),
                         nombre_agricultor=nombre_agricultor,
                         codigo=codigo,
                         racimos=racimos,
                         placa=placa,
                         acarreo=acarreo,
                         cargo=cargo,
                         transportador=transportador,
                         fecha_tiquete=fecha_tiquete,
                         hora_registro=datetime.now().strftime('%H:%M:%S'),
                         nota=nota,
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
        # Eliminar cualquier sufijo "_R1" o similar para usar el código base
        if "_R" in codigo and codigo.split("_R")[-1].isdigit():
            codigo_limpio = codigo.split("_R")[0]
            logger.info(f"Eliminando sufijo de revisión, usando código base: {codigo_limpio}")
        else:
            codigo_limpio = codigo
        
        # Verificar si tenemos un código guía original guardado en la sesión
        original_codigo_guia = session.get('codigo_guia_original')
        if original_codigo_guia:
            logger.info(f"Usando código guía original de sesión {original_codigo_guia}")
            codigo_guia_completo = original_codigo_guia
            # Guardar en la sesión para mantener consistencia
            session['codigo_guia'] = codigo_guia_completo
            session.modified = True
            
            # Intentar obtener datos con este código
            datos_guia = utils.get_datos_guia(codigo_guia_completo)
            if datos_guia:
                # Si encontramos datos, no necesitamos buscar más
                return render_template('pesaje.html', datos=datos_guia)
        
        # Si no tenemos un código de guía original o no se encontraron datos, continuar con el flujo normal
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo_limpio.split('_')[0] if '_' in codigo_limpio else codigo_limpio
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            
            # Verificar y eliminar sufijo "_R1" si existe
            if "_R" in codigo_guia_completo and codigo_guia_completo.split("_R")[-1].isdigit():
                codigo_guia_completo = codigo_guia_completo.split("_R")[0]
                logger.info(f"Eliminando sufijo de revisión del archivo, usando: {codigo_guia_completo}")
        else:
            codigo_guia_completo = codigo_limpio

        # Intentar obtener datos usando múltiples métodos
        datos_guia = None
        
        # 1. Primero intentar con utils.get_datos_guia
        try:
            datos_guia = utils.get_datos_guia(codigo_guia_completo)
            if datos_guia:
                logger.info(f"Datos obtenidos con utils.get_datos_guia para {codigo_guia_completo}")
        except Exception as e:
            logger.error(f"Error al obtener datos con utils.get_datos_guia: {str(e)}")
        
        # 2. Si no funciona, intentar con la capa DAL
        if not datos_guia:
            try:
                from data_access import DataAccess
                dal = DataAccess(app)
                datos_dal = dal.get_guia_complete_data(codigo_guia_completo)
                if datos_dal:
                    logger.info(f"Datos obtenidos con DataAccess para {codigo_guia_completo}")
                    datos_guia = datos_dal
            except Exception as e:
                logger.error(f"Error al obtener datos con DataAccess: {str(e)}")
        
        # 3. Si todavía no hay datos, intentar con db_operations y db_utils
        if not datos_guia:
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
                        # Crear un diccionario con exactamente los campos que espera la plantilla
                        datos_guia = {
                            'codigo_guia': codigo_guia_completo,
                            'codigo': registro.get('codigo_proveedor', ''),
                            'nombre': registro.get('nombre_proveedor', ''),
                            'cantidad_racimos': registro.get('cantidad_racimos', ''),
                            'placa': registro.get('placa', 'No disponible'),
                            'transportador': registro.get('transportador', 'No disponible'),
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
                        session['placa'] = registro.get('placa', 'No disponible')
                        session['transportador'] = registro.get('transportador', 'No disponible')
                        session['racimos'] = registro.get('cantidad_racimos', '')
                        session.modified = True
                        
                        logger.info(f"Datos obtenidos desde entry records para {codigo_guia_completo}: proveedor={datos_guia['nombre']}, racimos={datos_guia['cantidad_racimos']}")
            except Exception as e:
                logger.error(f"Error al intentar obtener datos de la base de datos: {str(e)}")
                logger.error(traceback.format_exc())
        
        # 4. Como último recurso, utilizar datos de la sesión
        if not datos_guia:
            logger.info(f"No se encontraron datos para {codigo_guia_completo}, intentando usar datos de sesión")
            if session.get('codigo_guia') and session.get('codigo_proveedor'):
                datos_guia = {
                    'codigo_guia': session.get('codigo_guia', codigo_guia_completo),
                    'codigo': session.get('codigo_proveedor', 'No disponible'),
                    'nombre': session.get('nombre_proveedor', 'No disponible'),
                    'cantidad_racimos': session.get('racimos', 'No disponible'),
                    'placa': session.get('placa', 'No disponible'),
                    'transportador': session.get('transportador', 'No disponible'),
                    'estado_actual': 'registro_completado'
                }
                logger.info(f"Usando datos de sesión para {codigo_guia_completo}")
                
        if not datos_guia:
            logger.error(f"No se pudo encontrar información para la guía: {codigo_guia_completo}")
            flash('Guía no encontrada', 'error')
            return render_template('error.html', message='Guía no encontrada'), 404
            
        # Verificar si la guía ya ha sido procesada más allá del pesaje
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.info(f"La guía {codigo_guia_completo} ya ha sido procesada. Continuando con el mismo código.")
            
            # Limpiar datos de sesión relacionados con la guía anterior pero preservar información de proveedor
            session_keys_to_reset = ['estado_actual', 'peso_bruto', 'tipo_pesaje', 'fecha_pesaje', 'hora_pesaje']
            for key in session_keys_to_reset:
                if key in session:
                    del session[key]
            
            # Guardar el código en la sesión sin sufijo R
            # También guardar como código original si aún no existe
            if 'codigo_guia_original' not in session:
                session['codigo_guia_original'] = codigo_guia_completo
            session['codigo_guia'] = codigo_guia_completo
            session.modified = True
            
        # Asegurarse de que los datos del proveedor estén completos
        if datos_guia:
            # Si falta el campo 'codigo', intentar obtenerlo de otros campos
            if not datos_guia.get('codigo') or datos_guia.get('codigo') == 'N/A':
                # Intentar extraer del codigo_proveedor
                datos_guia['codigo'] = datos_guia.get('codigo_proveedor', 'N/A')
                
            # Si falta el campo 'nombre', intentar obtenerlo de otros campos
            if not datos_guia.get('nombre') or datos_guia.get('nombre') == 'N/A':
                # Intentar extraer del nombre_proveedor
                datos_guia['nombre'] = datos_guia.get('nombre_proveedor', 
                                      datos_guia.get('nombre_agricultor', 'N/A'))
                
            # Si falta el campo 'cantidad_racimos', intentar obtenerlo de otros campos
            if not datos_guia.get('cantidad_racimos') or datos_guia.get('cantidad_racimos') == 'N/A':
                # Intentar extraer del campo racimos
                datos_guia['cantidad_racimos'] = datos_guia.get('racimos', 'N/A')
                
            # Añadir datos adicionales de la sesión si están disponibles
            if session.get('codigo_proveedor') and (not datos_guia.get('codigo') or datos_guia.get('codigo') == 'N/A'):
                datos_guia['codigo'] = session.get('codigo_proveedor')
                
            if session.get('nombre_proveedor') and (not datos_guia.get('nombre') or datos_guia.get('nombre') == 'N/A'):
                datos_guia['nombre'] = session.get('nombre_proveedor')
                
            if session.get('racimos') and (not datos_guia.get('cantidad_racimos') or datos_guia.get('cantidad_racimos') == 'N/A'):
                datos_guia['cantidad_racimos'] = session.get('racimos')
                
            # También actualizar la sesión con estos datos para mantener consistencia
            session['codigo_proveedor'] = datos_guia.get('codigo', session.get('codigo_proveedor', 'N/A'))
            session['nombre_proveedor'] = datos_guia.get('nombre', session.get('nombre_proveedor', 'N/A'))
            session['racimos'] = datos_guia.get('cantidad_racimos', session.get('racimos', 'N/A'))
            session.modified = True
                
        # Log para depuración
        logger.info(f"Datos para template: codigo={datos_guia.get('codigo', 'N/A')}, nombre={datos_guia.get('nombre', 'N/A')}, racimos={datos_guia.get('cantidad_racimos', 'N/A')}")
        
        # Si el código en la URL tiene sufijo pero el real no, redirigir
        if codigo != codigo_limpio:
            logger.info(f"Redirigiendo de URL con sufijo {codigo} a URL sin sufijo {codigo_limpio}")
            return redirect(url_for('pesaje', codigo=codigo_limpio))

        # Renderizar template de pesaje
        return render_template('pesaje.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error al procesar la solicitud: {str(e)}"), 500
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
        
        # Obtener el código base (sin timestamp ni versión)
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
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

        # Verificar si ya existe un archivo de clasificación para este código de guía COMPLETO
        # (no solo el código base como antes)
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        archivo_clasificacion_exacto = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_completo}.json")
        
        if os.path.exists(archivo_clasificacion_exacto):
            logger.info(f"Se encontró un archivo de clasificación exacto para la guía actual: {codigo_guia_completo}")
            # Redirigir a la página de resultados de clasificación si ya existe para esta guía específica
            return redirect(url_for('ver_resultados_clasificacion', url_guia=codigo_guia_completo))

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá de la clasificación
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            flash("Esta guía ya ha sido clasificada y no se puede modificar.", "warning")
            return render_template('error.html', 
                          message="Esta guía ya ha sido clasificada y no se puede modificar. Por favor, contacte al administrador si necesita realizar cambios."), 403

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
                            nombre=datos_guia.get('nombre') or datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                            peso_bruto=datos_guia.get('peso_bruto'),
                            tipo_pesaje=datos_guia.get('tipo_pesaje'),
                            fecha_registro=datos_guia.get('fecha_registro'),
                            hora_registro=datos_guia.get('hora_registro'),
                            fecha_pesaje=datos_guia.get('fecha_pesaje'),
                            hora_pesaje=datos_guia.get('hora_pesaje'),
                            transportador=datos_guia.get('transportador'),
                            placa=datos_guia.get('placa'),
                            guia_transporte=datos_guia.get('guia_transito'),
                            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap'))
                           
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
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
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

@app.route('/procesar_pesaje_directo', methods=['POST'])
def procesar_pesaje_directo():
    try:
        # Verificar que haya un archivo cargado
        if 'imagen' not in request.files:
            logger.error("No se envió archivo de imagen")
            return jsonify({"success": False, "message": "No se envió archivo de imagen"}), 400
            
        image_file = request.files['imagen']
        codigo_guia = request.form.get('codigo_guia')
        
        if not image_file:
            logger.error("No se seleccionó archivo de imagen")
            return jsonify({"success": False, "message": "No se seleccionó archivo de imagen"}), 400
            
        if not codigo_guia:
            logger.error("No se proporcionó código de guía")
            return jsonify({"success": False, "message": "No se proporcionó código de guía"}), 400
        
        # Verificar si la guía ya ha sido procesada
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía ya procesada: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya ha sido procesada y no se puede modificar'
            }), 403
            
        # Guardar imagen temporalmente
        image_filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
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
            r'El peso tara es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'El peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'peso es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'Peso Bruto:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'Exitoso!\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?'
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
                    'message': 'Peso detectado (método alternativo)'
                }
                if codigo_guia_transporte_sap:
                    result['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
                
                return jsonify(result)
            
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
    """
    Registra el peso bruto directo y lo almacena en la base de datos SQLite
    usando la nueva capa de acceso a datos.
    """
    try:
        # Obtener datos de la solicitud
        data = request.json
        logger.info(f"Datos recibidos para registro de peso directo: {data}")
        
        # Validar datos requeridos
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        if not codigo_guia or not peso_bruto:
            return jsonify({'success': False, 'message': 'Faltan datos requeridos: código de guía y peso bruto'})
        
        # Usar la nueva capa de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos existentes (si los hay)
        datos_guia = dal.get_guia_complete_data(codigo_guia)
        
        # Preparar los datos para almacenar
        codigo_proveedor = None
        nombre_proveedor = None
        
        # Extraer información relevante si hay datos previos
        if datos_guia:
            codigo_proveedor = datos_guia.get('codigo_proveedor')
            nombre_proveedor = datos_guia.get('nombre_proveedor')
            logger.info(f"Datos previos encontrados para guía {codigo_guia}: proveedor={codigo_proveedor}")
        else:
            # Si no hay datos previos, extraer información del código o sesión
            logger.warning(f"No se encontraron datos previos para la guía {codigo_guia}")
            
            # Intentar obtener de la sesión
            if 'codigo_proveedor' in session:
                codigo_proveedor = session.get('codigo_proveedor')
                logger.info(f"Usando código de proveedor de sesión: {codigo_proveedor}")
            
            if 'nombre_proveedor' in session:
                nombre_proveedor = session.get('nombre_proveedor')
                logger.info(f"Usando nombre de proveedor de sesión: {nombre_proveedor}")
            
            # Si no están en la sesión, extraer del código de guía
            if not codigo_proveedor and '_' in codigo_guia:
                codigo_proveedor = codigo_guia.split('_')[0]
                logger.info(f"Extraído código de proveedor del código de guía: {codigo_proveedor}")
        
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
        codigo_guia_transporte_sap = data.get('codigo_guia_transporte_sap')
        if not codigo_guia_transporte_sap and 'codigo_guia_transporte_sap' in session:
            codigo_guia_transporte_sap = session.get('codigo_guia_transporte_sap')
            
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'directo',
            'fecha_pesaje': fecha_pesaje,
            'hora_pesaje': hora_pesaje,
            'imagen_pesaje': '',  # No hay imagen en pesaje directo
            'codigo_guia_transporte_sap': codigo_guia_transporte_sap
        }
        
        # Guardar usando la nueva capa de acceso a datos
        if dal.save_pesaje_bruto(datos_pesaje):
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
            if codigo_guia_transporte_sap:
                logger.info(f"Guía de transporte SAP guardada: {codigo_guia_transporte_sap}")
        else:
            logger.warning(f"Posible problema al guardar peso para {codigo_guia}")
        
        # Actualizar datos en sesión
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = 'directo'
        session['fecha_pesaje'] = fecha_pesaje
        session['hora_pesaje'] = hora_pesaje
        if codigo_guia_transporte_sap:
            session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
        
        # Generar URL de redirección a la página de resultados
        redirect_url = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        
        # Registrar la URL para depuración
        logger.info(f"Redirigiendo a la URL: {redirect_url}")
        
        return jsonify({
            'success': True,
            'message': f'Peso bruto registrado: {peso_bruto}kg',
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error en registrar_peso_directo: {str(e)}")
        logger.error(traceback.format_exc())  # Añadir stack trace para mejor diagnóstico
        return jsonify({
            'success': False,
            'message': f'Error al registrar peso: {str(e)}'
        })

@app.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    """
    Registra el peso bruto manual o virtual usando la nueva capa de acceso a datos.
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
                img_dir = os.path.join(app.static_folder, 'pesajes', codigo_guia)
                os.makedirs(img_dir, exist_ok=True)
                
                # Guardar imagen
                filename = f"pesaje_{utils.generate_unique_id()}.jpg"
                file_path = os.path.join(img_dir, filename)
                imagen.save(file_path)
                
                # Guardar ruta relativa para acceso web
                imagen_path = os.path.join('static', 'pesajes', codigo_guia, filename)
        
        # Validar datos requeridos
        if not codigo_guia or not peso_bruto:
            return jsonify({'success': False, 'message': 'Faltan datos requeridos: código de guía y peso bruto'})
        
        # Usar la nueva capa de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos existentes (si los hay)
        datos_guia = dal.get_guia_complete_data(codigo_guia)
        
        # Preparar los datos para almacenar
        codigo_proveedor = None
        nombre_proveedor = None
        
        # Extraer información relevante si hay datos previos
        if datos_guia:
            codigo_proveedor = datos_guia.get('codigo_proveedor')
            nombre_proveedor = datos_guia.get('nombre_proveedor')
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
        
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': peso_bruto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_pesaje,
            'hora_pesaje': hora_pesaje,
            'imagen_pesaje': imagen_path
        }
        
        # Guardar usando la nueva capa de acceso a datos
        if dal.save_pesaje_bruto(datos_pesaje):
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
        else:
            logger.warning(f"Posible problema al guardar peso para {codigo_guia}")
        
        # Actualizar datos en sesión
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = tipo_pesaje
        session['fecha_pesaje'] = fecha_pesaje
        session['hora_pesaje'] = hora_pesaje
        
        # Generar URL de redirección a la página de resultados
        redirect_url = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        
        # Registrar la URL para depuración
        logger.info(f"Redirigiendo a la URL después de pesaje virtual: {redirect_url}")
        
        return jsonify({
            'success': True,
            'message': f'Peso bruto registrado: {peso_bruto}kg',
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error en registrar_peso_virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False, 
            'message': f'Error al registrar peso: {str(e)}'
        })

@app.route('/registrar_clasificacion', methods=['POST'])
def registrar_clasificacion():
    """
    Registra la clasificación manual de racimos.
    """
    try:
        codigo_guia = request.form.get('codigo_guia')
        if not codigo_guia:
            logger.error("No se proporcionó un código de guía")
            return jsonify({
                'success': False,
                'message': 'Error: No se proporcionó un código de guía'
            })
        
        # Crear directorios para imágenes y clasificaciones si no existen
        fotos_temp_dir = os.path.join(app.static_folder, 'fotos_racimos_temp')
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        os.makedirs(fotos_temp_dir, exist_ok=True)
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Guardar el código original para referencia
        codigo_guia_original = codigo_guia
        
        # Obtener el código base (sin timestamp ni versión)
        codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        
        # Extraer código proveedor y asegurar formato correcto
        codigo_proveedor = codigo_base
        if re.match(r'\d+[aA]?$', codigo_proveedor):
            if codigo_proveedor.endswith('a'):
                codigo_proveedor = codigo_proveedor[:-1] + 'A'
            elif not codigo_proveedor.endswith('A'):
                codigo_proveedor = codigo_proveedor + 'A'
                
        # Intentar encontrar el código guía completo del archivo HTML más reciente
        # para asegurar consistencia con el proceso de pesaje
        guias_folder = app.config['GUIAS_FOLDER']
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_a_usar = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            logger.info(f"Código guía completo obtenido del archivo HTML: {codigo_guia_a_usar}")
        else:
            # Si no hay archivos HTML con este código base, intentar buscar en la base de datos
            from db_operations import get_pesaje_bruto_by_codigo_guia
            pesaje = get_pesaje_bruto_by_codigo_guia(codigo_base)
            if pesaje and 'codigo_guia' in pesaje:
                codigo_guia_a_usar = pesaje['codigo_guia']
                logger.info(f"Código guía completo obtenido de la base de datos: {codigo_guia_a_usar}")
            else:
                # Si no se encuentra, usar el código original
                codigo_guia_a_usar = codigo_guia_original
                logger.info(f"Usando código guía original: {codigo_guia_a_usar}")
        
        # Obtener datos de la guía para recuperar el nombre del proveedor
        datos_guia = utils.get_datos_guia(codigo_guia_a_usar)
        nombre_proveedor = datos_guia.get('nombre') if datos_guia else 'No disponible'
        
        # Preparar datos de clasificación
        fecha_clasificacion = datetime.now().strftime('%d/%m/%Y')
        hora_clasificacion = datetime.now().strftime('%H:%M:%S')
        
        datos_clasificacion = {
            'codigo_guia': codigo_guia_a_usar,
            'codigo_guia_original': codigo_guia_original,
            'codigo_proveedor': codigo_proveedor,  # Guardar el código del proveedor
            'nombre_proveedor': nombre_proveedor,  # Guardar el nombre del proveedor
            'fecha_clasificacion': fecha_clasificacion,
            'hora_clasificacion': hora_clasificacion,
            'clasificacion_manual': {},
            'imagenes': {}
        }
        
        # Recopilar datos de clasificación manual
        clasificacion_manual = {}
        
        # Verificar primero si hay datos en el formato "cantidad_*"
        for key in request.form:
            if key.startswith('cantidad_'):
                categoria = key.replace('cantidad_', '')
                try:
                    clasificacion_manual[categoria] = int(request.form[key])
                except:
                    clasificacion_manual[categoria] = 0
        
        # Verificar si hay datos en el formato usado por el formulario de clasificación.html
        # donde los IDs son directamente los nombres de las categorías
        categoria_mapping = {
            'verdes': 'verdes',
            'sobremaduros': 'sobremaduros', 
            'danio-corona': 'danio_corona',
            'pendunculo-largo': 'pendunculo_largo',
            'podridos': 'podridos'
        }
        
        # Si no se han encontrado datos por el primer método, revisar en el formato directo
        if not clasificacion_manual:
            for form_id, categoria in categoria_mapping.items():
                if form_id in request.form and request.form[form_id]:
                    try:
                        clasificacion_manual[categoria] = int(float(request.form[form_id]))
                    except:
                        clasificacion_manual[categoria] = 0
        
        # También verificar el formato "clasificacion_X_peso" que viene del JS
        if not clasificacion_manual:
            for i, categoria in enumerate(['verdes', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']):
                key_name = f'clasificacion_{i}_peso'
                if key_name in request.form and request.form[key_name]:
                    try:
                        clasificacion_manual[categoria] = int(float(request.form[key_name]))
                    except:
                        clasificacion_manual[categoria] = 0
        
        # Registrar las cantidades de clasificación y el formato en que se encontraron
        logger.info(f"Clasificación manual registrada: {clasificacion_manual}")
        logger.info(f"Claves del formulario: {list(request.form.keys())}")
        datos_clasificacion['clasificacion_manual'] = clasificacion_manual
        
        # Guardar imágenes adjuntas
        imagenes = {}
        fotos_paths = []
        
        # Procesar cada imagen regular (no asociada a una clasificación específica)
        for idx in range(1, 4):  # Permitimos hasta 3 fotos regulares
            foto_key = f'foto{idx}'
            if foto_key in request.files:
                file = request.files[foto_key]
                if file and file.filename and allowed_file(file.filename):
                    # Usar el nombre de la guía para prevenir colisiones
                    filename = f"foto{idx}_{codigo_guia_a_usar}.jpg"
                    file_path = os.path.join(fotos_temp_dir, filename)
                    file.save(file_path)
                    
                    # Guardar rutas para el procesamiento automático
                    fotos_paths.append(file_path)
                    
                    # Guardar ruta web para la interfaz
                    web_path = f"fotos_racimos_temp/{filename}"
                    imagenes[foto_key] = web_path
                    datos_clasificacion['imagenes'][foto_key] = web_path
        
        # Almacenar datos en la base de datos
        from db_operations import store_clasificacion
        store_clasificacion(datos_clasificacion)
        
        # Preparar datos para el procesamiento automático
        clasificacion_data = {
            'id': f"Clasificacion_{codigo_guia_a_usar}",
            'fecha_registro': fecha_clasificacion,
            'hora_registro': hora_clasificacion,
            'codigo_proveedor': codigo_proveedor,  # Incluir código del proveedor
            'nombre_proveedor': nombre_proveedor,  # Incluir nombre del proveedor
            'fotos': fotos_paths,
            'estado': 'en_proceso',
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': {
                "verdes": {"cantidad": 0, "porcentaje": 0},
                "maduros": {"cantidad": 0, "porcentaje": 0}, 
                "sobremaduros": {"cantidad": 0, "porcentaje": 0},
                "podridos": {"cantidad": 0, "porcentaje": 0},
                "danio_corona": {"cantidad": 0, "porcentaje": 0},
                "pendunculo_largo": {"cantidad": 0, "porcentaje": 0}
            },
            'resultados_por_foto': {}
        }
        
        # Guardar en archivo JSON para procesamiento automático
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_a_usar}.json")
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
            
        logger.info(f"Guardados datos de clasificación para guía {codigo_guia_a_usar} con clasificación manual: {clasificacion_manual}")
        
        # Crear directorio específico para las fotos de esta guía
        guia_fotos_dir = os.path.join(fotos_temp_dir, codigo_guia_a_usar)
        os.makedirs(guia_fotos_dir, exist_ok=True)
        
        # Mover las fotos al directorio específico de la guía
        for foto_path in fotos_paths:
            filename = os.path.basename(foto_path)
            dest_path = os.path.join(guia_fotos_dir, filename)
            if os.path.exists(foto_path) and foto_path != dest_path:
                try:
                    shutil.copy2(foto_path, dest_path)
                    logger.info(f"Copiada foto {foto_path} a {dest_path}")
                except Exception as e:
                    logger.error(f"Error copiando foto: {str(e)}")
        
        # Crear la URL de redirección para ver los resultados
        redirect_url = url_for('ver_resultados_clasificacion', url_guia=codigo_guia_a_usar)
        logger.info(f"Redirección a: {redirect_url}")
        
        return jsonify({
            'success': True,
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error registrando clasificación: {str(e)}")
        import traceback
        traceback.print_exc()  # Imprimir el traceback completo
        return jsonify({
            'success': False,
            'message': f'Error al registrar clasificación: {str(e)}'
        })

def process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Procesa las imágenes a través de la API de Roboflow y actualiza el archivo JSON.
    """
    logger.info(f"Iniciando procesamiento automático para guía: {codigo_guia}")
    
    # Función auxiliar para decodificar base64 correctamente, incluso si tiene prefijo data:image
    def decode_image_data(data):
        """Decodifica datos de imagen en base64, manejando prefijos de data URI si están presentes."""
        try:
            # Si es un string vacío o None, retornar None
            if not data:
                return None
                
            # Si parece ser una data URI, extraer solo la parte de datos
            if isinstance(data, str) and data.startswith('data:image'):
                # Formato típico: data:image/jpeg;base64,/9j/4AAQ...
                base64_data = data.split(',', 1)[1]
            else:
                base64_data = data
                
            # Decodificar los datos en base64
            return base64.b64decode(base64_data)
        except Exception as e:
            logger.error(f"Error decodificando datos de imagen: {str(e)}")
            return None
            
    try:
        # Leer el archivo JSON actual para inicializar los datos de clasificación
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Inicializar resultados de clasificación automática con la estructura esperada
        clasificacion_automatica = {
            "verdes": {"cantidad": 0, "porcentaje": 0},
            "maduros": {"cantidad": 0, "porcentaje": 0},
            "sobremaduros": {"cantidad": 0, "porcentaje": 0},
            "podridos": {"cantidad": 0, "porcentaje": 0},
            "danio_corona": {"cantidad": 0, "porcentaje": 0},
            "pendunculo_largo": {"cantidad": 0, "porcentaje": 0}
        }
        
        # Definir un mapeo de claves de Roboflow a claves internas
        # Esto permitirá manejar diferentes formatos de nombres desde Roboflow
        mapeo_categorias = {
            # Mapeo para verdes
            'racimos verdes': 'verdes',
            'racimo verde': 'verdes',
            'racimos_verdes': 'verdes',
            'racimo_verde': 'verdes',
            'verde': 'verdes',
            'verdes': 'verdes',
            'racimo verde inm.': 'verdes',
            'racimos verde inm.': 'verdes',
            'Racimos verdes': 'verdes',
            
            # Mapeo para maduros
            'racimos maduros': 'maduros',
            'racimo maduro': 'maduros',
            'racimos_maduros': 'maduros',
            'racimo_maduro': 'maduros',
            'maduro': 'maduros',
            'maduros': 'maduros',
            'Racimos maduros': 'maduros',
            
            # Mapeo para sobremaduros
            'racimos sobremaduros': 'sobremaduros',
            'racimo sobremaduro': 'sobremaduros',
            'racimos_sobremaduros': 'sobremaduros',
            'racimo_sobremaduro': 'sobremaduros',
            'sobremaduro': 'sobremaduros',
            'sobremaduros': 'sobremaduros',
            'racimo sobre maduro': 'sobremaduros',
            'Racimos sobremaduros': 'sobremaduros',
            
            # Mapeo para podridos
            'racimos podridos': 'podridos',
            'racimo podrido': 'podridos',
            'racimos_podridos': 'podridos',
            'racimo_podrido': 'podridos',
            'podrido': 'podridos',
            'podridos': 'podridos',
            'Racimos podridos': 'podridos',
            
            # Mapeo para daño en corona
            'daño corona': 'danio_corona',
            'racimo con daño en corona': 'danio_corona',
            'racimos con daño en corona': 'danio_corona',
            'danio_corona': 'danio_corona',
            'daño_corona': 'danio_corona',
            'corona': 'danio_corona',
            'Daño corona': 'danio_corona',
            
            # Mapeo para pedúnculo largo
            'pedunculo largo': 'pendunculo_largo',
            'racimo con pedunculo largo': 'pendunculo_largo',
            'racimos con pedunculo largo': 'pendunculo_largo',
            'pedunculo_largo': 'pendunculo_largo',
            'pendunculo_largo': 'pendunculo_largo',
            'Pedunculo largo': 'pendunculo_largo'
        }
        
        resultados_por_foto = {}
        tiempo_inicio = time.time()
        
        # Procesar cada foto secuencialmente
        for idx, foto_path in enumerate(fotos_paths, 1):
            # Guardar una copia de la foto original en el directorio de la guía
            foto_nombre = f"foto_{idx}.jpg"
            foto_destino = os.path.join(guia_fotos_dir, foto_nombre)
            # Copiar la imagen original
            from shutil import copyfile
            copyfile(foto_path, foto_destino)
            
            logger.info(f"Procesando imagen {idx}/{len(fotos_paths)}: {foto_path}")
            # Redimensionar imagen para asegurar que no sea demasiado grande
            # Roboflow limita las imágenes a 1152x2048
            from PIL import Image
            try:
                image = Image.open(foto_path)
                
                # Verificar si la imagen necesita redimensionamiento
                width, height = image.size
                max_width = 1152
                max_height = 2048
                
                if width > max_width or height > max_height:
                    # Calcular ratio de aspecto
                    ratio = min(max_width/width, max_height/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    
                    # Redimensionar la imagen
                    image = image.resize(new_size, Image.LANCZOS)
                    
                    # Guardar la imagen redimensionada
                    new_path = foto_path.replace('.jpg', '_resized.jpg')
                    image.save(new_path, 'JPEG')
                    foto_path = new_path
            except Exception as e:
                logger.warning(f"No se pudo redimensionar la imagen: {e}")
            
            # Convertir la imagen a base64 para enviar en formato JSON
            try:
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
                    logger.info(f"Respuesta Completa: {response.text[:500]}...")
                    
                    # Procesar la respuesta
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"TODAS LAS CLAVES de la respuesta: {list(result.keys())}")
                        logger.info(f"DUMP de respuesta completa: {json.dumps(result, indent=2)[:1000]}...")
                        
                        # Imprimir información sobre la estructura de outputs
                        if 'outputs' in result:
                            logger.info(f"OUTPUTS: Hay {len(result['outputs'])} elementos")
                            if result['outputs'] and len(result['outputs']) > 0:
                                for i, output in enumerate(result['outputs']):
                                    if isinstance(output, dict):
                                        logger.info(f"OUTPUT[{i}] CLAVES: {list(output.keys())}")
                                    else:
                                        logger.info(f"OUTPUT[{i}] NO ES DICCIONARIO: {type(output)}")
                        
                        # Extraer conteos de racimos por categoría utilizando el mapeo
                        detecciones = {
                            "verdes": 0,
                            "maduros": 0, 
                            "sobremaduros": 0,
                            "podridos": 0,
                            "danio_corona": 0,
                            "pendunculo_largo": 0
                        }
                        
                        # Extraer el número total de racimos detectados (potholes_detected)
                        total_racimos_detectados = 0
                        if 'potholes_detected' in result:
                            try:
                                total_racimos_detectados = int(result['potholes_detected'])
                                logger.info(f"Total racimos detectados (potholes_detected): {total_racimos_detectados}")
                            except (ValueError, TypeError):
                                logger.warning(f"No se pudo convertir potholes_detected a entero: {result['potholes_detected']}")
                        
                        # Extraer racimos detectados usando el mapeo de categorías
                        for key, value in result.items():
                            logger.info(f"Verificando clave: {key} (valor: {value})")
                            
                            # Verificar si la clave está en nuestro mapeo
                            key_lower = key.lower()
                            for roboflow_key, internal_key in mapeo_categorias.items():
                                if roboflow_key.lower() == key_lower:
                                    try:
                                        if isinstance(value, (int, float)):
                                            detecciones[internal_key] = int(value)
                                        elif isinstance(value, str) and value.isdigit():
                                            detecciones[internal_key] = int(value)
                                        elif isinstance(value, dict) and 'count' in value:
                                            detecciones[internal_key] = int(value['count'])
                                        logger.info(f"Coincidencia encontrada: {key} -> {internal_key} = {detecciones[internal_key]}")
                                    except (ValueError, TypeError):
                                        logger.warning(f"No se pudo convertir a entero: {value} para la clave {key}")
                                    break
                        
                        # Buscar en la estructura de outputs si está disponible
                        if 'outputs' in result and isinstance(result['outputs'], list) and len(result['outputs']) > 0:
                            for output in result['outputs']:
                                if isinstance(output, dict):
                                    for key, value in output.items():
                                        # Intentar buscar en el mapeo primero
                                        key_lower = key.lower()
                                        for roboflow_key, internal_key in mapeo_categorias.items():
                                            if roboflow_key.lower() == key_lower:
                                                try:
                                                    if isinstance(value, (int, float)):
                                                        detecciones[internal_key] += int(value)
                                                    elif isinstance(value, str) and value.isdigit():
                                                        detecciones[internal_key] += int(value)
                                                    elif isinstance(value, dict) and 'count' in value:
                                                        detecciones[internal_key] += int(value['count'])
                                                    logger.info(f"Coincidencia en outputs: {key} -> {internal_key} = {value}")
                                                except (ValueError, TypeError):
                                                    logger.warning(f"No se pudo convertir a entero en outputs: {value}")
                                                break
                                            
                                            # Si el valor es un diccionario, buscar dentro de él
                                            if isinstance(value, dict):
                                                for subkey, subvalue in value.items():
                                                    subkey_lower = subkey.lower()
                                                    for roboflow_key, internal_key in mapeo_categorias.items():
                                                        if roboflow_key.lower() == subkey_lower:
                                                            try:
                                                                if isinstance(subvalue, (int, float)):
                                                                    detecciones[internal_key] += int(subvalue)
                                                                elif isinstance(subvalue, str) and subvalue.isdigit():
                                                                    detecciones[internal_key] += int(subvalue)
                                                                elif isinstance(subvalue, dict) and 'count' in subvalue:
                                                                    detecciones[internal_key] += int(subvalue['count'])
                                                                logger.info(f"Coincidencia en subclave: {subkey} -> {internal_key} = {subvalue}")
                                                            except (ValueError, TypeError):
                                                                logger.warning(f"No se pudo convertir subclave a entero: {subvalue}")
                                                            break
                        
                        # Si no se detectaron racimos específicos pero hay un total, asignar proporciones por defecto
                        if total_racimos_detectados > 0 and sum(detecciones.values()) == 0:
                            # Asignar todos como maduros por defecto, pero puede cambiarse a una distribución si se conoce
                            detecciones["maduros"] = total_racimos_detectados
                            logger.info(f"No se detectaron categorías específicas, asignando {total_racimos_detectados} racimos como maduros")
                        
                        # Si no hay total pero hay detecciones, calcular el total
                        if total_racimos_detectados == 0 and sum(detecciones.values()) > 0:
                            total_racimos_detectados = sum(detecciones.values())
                            logger.info(f"Total racimos calculado de detecciones: {total_racimos_detectados}")
                        
                        # Actualizar conteo global
                        for categoria, cantidad in detecciones.items():
                            if cantidad > 0:
                                clasificacion_automatica[categoria]["cantidad"] += cantidad
                        
                        # Guardar resultados para esta foto
                        resultados_por_foto[str(idx)] = {
                            "potholes_detected": total_racimos_detectados,
                            "detecciones": detecciones
                        }
                        
                        logger.info(f"Detecciones finales para imagen {idx}: {detecciones}")
                        logger.info(f"Total racimos detectados: {total_racimos_detectados}")
                        
                        # Guardar imágenes anotadas si están disponibles
                        if 'annotated_image' in result:
                            try:
                                logger.info("Encontrada imagen anotada en la respuesta principal")
                                if isinstance(result['annotated_image'], dict) and 'value' in result['annotated_image']:
                                    img_data = decode_image_data(result['annotated_image']['value'])
                                else:
                                    img_data = decode_image_data(result['annotated_image'])
                                    
                                if img_data:
                                    img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data)
                                    logger.info(f"Imagen anotada guardada en {img_path}")
                            except Exception as e:
                                logger.error(f"Error al guardar imagen anotada: {str(e)}")
                        
                        # Comprobar si hay label_visualization
                        if 'label_visualization_1' in result:
                            try:
                                logger.info("Encontrada visualización de etiquetas en la respuesta")
                                if isinstance(result['label_visualization_1'], dict):
                                    if 'value' in result['label_visualization_1']:
                                        img_data = decode_image_data(result['label_visualization_1']['value'])
                                else:
                                    # Decodificar como cadena normal
                                    img_data = decode_image_data(result['label_visualization_1'])
                                
                                if img_data:
                                    img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_etiquetas.jpg")
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data)
                                    logger.info(f"Visualización de etiquetas guardada en {img_path}")
                            except Exception as e:
                                logger.error(f"Error al procesar label_visualization_1: {str(e)}")
                        
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
                                                img_data = decode_image_data(output[img_field]['value'])
                                            else:
                                                img_data = decode_image_data(output[img_field])
                                                
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
                            for field_name in ['visualization', 'visualizations', 'image', 'processed_image', 'annotated', 'predictions', 'annotated_image']:
                                if field_name in result:
                                    try:
                                        logger.info(f"Intentando procesar campo de imagen: {field_name}")
                                        # Manejar tanto cadenas base64 como listas de cadenas
                                        if isinstance(result[field_name], list) and len(result[field_name]) > 0:
                                            if isinstance(result[field_name][0], dict) and 'value' in result[field_name][0]:
                                                img_data = decode_image_data(result[field_name][0]['value'])
                                            else:
                                                img_data = decode_image_data(result[field_name][0])
                                        elif isinstance(result[field_name], dict):
                                            if 'value' in result[field_name]:
                                                img_data = decode_image_data(result[field_name]['value'])
                                            elif 'image' in result[field_name] and isinstance(result[field_name]['image'], str):
                                                img_data = decode_image_data(result[field_name]['image'])
                                            elif 'base64' in result[field_name] and isinstance(result[field_name]['base64'], str):
                                                img_data = decode_image_data(result[field_name]['base64'])
                                            else:
                                                for subfield in ['data', 'image_data', 'base64_data']:
                                                    if subfield in result[field_name] and isinstance(result[field_name][subfield], str):
                                                        img_data = decode_image_data(result[field_name][subfield])
                                                        break
                                                else:
                                                    logger.warning(f"No se pudo extraer datos de imagen de {field_name}")
                                                    continue
                                        else:
                                            img_data = decode_image_data(result[field_name])
                                            
                                        # Guardar la imagen procesada
                                        img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                        with open(img_path, 'wb') as f:
                                            f.write(img_data)
                                        logger.info(f"Imagen procesada guardada desde campo '{field_name}'")
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
        
        # Calcular tiempo total de procesamiento
        tiempo_fin = time.time()
        tiempo_procesamiento = round(tiempo_fin - tiempo_inicio, 2)
        
        # Calcular porcentajes para cada categoría
        total_racimos = sum(valor["cantidad"] for valor in clasificacion_automatica.values())
        if total_racimos > 0:
            for categoria in clasificacion_automatica:
                clasificacion_automatica[categoria]["porcentaje"] = round(
                    (clasificacion_automatica[categoria]["cantidad"] / total_racimos) * 100, 2
                ) if total_racimos > 0 else 0
                
        # Actualizar datos de clasificación
        clasificacion_data['clasificacion_automatica'] = clasificacion_automatica
        clasificacion_data['resultados_por_foto'] = resultados_por_foto
        clasificacion_data['estado'] = 'completado'
        clasificacion_data['workflow_completado'] = True
        clasificacion_data['tiempo_procesamiento'] = f"{tiempo_procesamiento} segundos"
        clasificacion_data['modelo_utilizado'] = f"{WORKSPACE_NAME}/{WORKFLOW_ID}"
        clasificacion_data['total_racimos_detectados'] = sum(cat["cantidad"] for cat in clasificacion_automatica.values())
        
        # Guardar datos actualizados
        logger.info(f"Guardando clasificación_data en: {json_path}")
        logger.info(f"Estructura clasificacion_automatica: {clasificacion_automatica}")
        logger.info(f"DUMP de clasificacion_data completo antes de guardar: {json.dumps(clasificacion_data, indent=2)}")
        try:
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
            logger.info(f"Datos JSON guardados correctamente")
        except Exception as e:
            logger.error(f"Error al guardar datos JSON: {str(e)}")
            logger.error(traceback.format_exc())
        
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
        
        # Importar función para obtener registros de la base de datos
        from db_utils import get_entry_record_by_guide_code
        
        # Crear un diccionario para rastrear códigos de guía base ya procesados
        # Esto evitará procesar múltiples versiones del mismo código base
        codigos_base_procesados = {}
        
        # Leer todos los archivos JSON de clasificaciones
        for filename in os.listdir(clasificaciones_dir):
            if filename.startswith('clasificacion_') and filename.endswith('.json'):
                try:
                    with open(os.path.join(clasificaciones_dir, filename), 'r') as f:
                        clasificacion_data = json.load(f)
                    
                    # Extraer el código de guía del nombre del archivo
                    codigo_guia = filename.replace('clasificacion_', '').replace('.json', '')
                    
                    # Extraer el código base (sin timestamp ni versión)
                    codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                    
                    # Si ya procesamos este código base y tiene un timestamp más reciente, omitir este archivo
                    if codigo_base in codigos_base_procesados:
                        # Comparar timestamps si existen
                        if '_' in codigo_guia and '_' in codigos_base_procesados[codigo_base]:
                            timestamp_actual = codigo_guia.split('_')[1] if len(codigo_guia.split('_')) > 1 else ''
                            timestamp_previo = codigos_base_procesados[codigo_base].split('_')[1] if len(codigos_base_procesados[codigo_base].split('_')) > 1 else ''
                            
                            # Si el timestamp actual es menor que el previo, omitir este archivo
                            if timestamp_actual < timestamp_previo:
                                logger.info(f"Omitiendo clasificación duplicada anterior: {codigo_guia}, ya existe una más reciente: {codigos_base_procesados[codigo_base]}")
                                continue
                    
                    # Registrar este código base con su versión completa
                    codigos_base_procesados[codigo_base] = codigo_guia
                    
                    # Inicializar valores por defecto
                    nombre_proveedor_actual = 'No disponible'
                    codigo_proveedor_actual = ''
                    cantidad_racimos = 'No disponible'
                    
                    # 1. Primero intentar obtener de la base de datos - PRIORIDAD MÁXIMA
                    entry_record = get_entry_record_by_guide_code(codigo_guia)
                    
                    if entry_record:
                        # Obtener datos directamente con las claves específicas
                        nombre_proveedor_actual = entry_record.get('nombre_proveedor', 'No disponible')
                        codigo_proveedor_actual = entry_record.get('codigo_proveedor', '')
                        cantidad_racimos = entry_record.get('cantidad_racimos', 'No disponible')
                        
                        # Log para debug
                        logger.info(f"Datos de DB para {codigo_guia}: Proveedor={nombre_proveedor_actual}, Racimos={cantidad_racimos}")
                    else:
                        # 2. Si no hay en DB, extraer código de proveedor del código de guía
                        if '_' in codigo_guia:
                            codigo_base = codigo_guia.split('_')[0]
                            # Asegurarse de que termine con A mayúscula si corresponde
                            if re.match(r'\d+[aA]?$', codigo_base):
                                if codigo_base.endswith('a'):
                                    codigo_proveedor_actual = codigo_base[:-1] + 'A'
                                elif not codigo_base.endswith('A'):
                                    codigo_proveedor_actual = codigo_base + 'A'
                                else:
                                    codigo_proveedor_actual = codigo_base
                        else:
                            codigo_proveedor_actual = codigo_base
                        codigo_proveedor_actual = codigo_guia
                    
                    # 3. Buscar datos en utils.get_datos_registro
                    # 3. Buscar datos en utils.get_datos_registro
                        try:
                            datos_registro = utils.get_datos_registro(codigo_guia)
                            if datos_registro:
                                nombre_proveedor_actual = datos_registro.get("nombre_proveedor", "No disponible")
                                if not codigo_proveedor_actual:
                                    codigo_proveedor_actual = datos_registro.get("codigo_proveedor", "")
                                cantidad_racimos = datos_registro.get("cantidad_racimos", "No disponible")

                            # Log para debug
                            logger.info(f"Datos de archivo para {codigo_guia}: Proveedor={nombre_proveedor_actual}, Racimos={cantidad_racimos}")
                        except Exception as e:
                            logger.warning(f"Error obteniendo datos de registro desde archivo: {str(e)}")
                    
                    # 4. Buscar datos en el propio archivo de clasificación como último recurso
                    if nombre_proveedor_actual == 'No disponible' and 'nombre_proveedor' in clasificacion_data:
                            nombre_proveedor_actual = clasificacion_data.get('nombre_proveedor', 'No disponible')
                    
                    if not codigo_proveedor_actual and 'codigo_proveedor' in clasificacion_data:
                            codigo_proveedor_actual = clasificacion_data.get('codigo_proveedor', '')
                    
                    if cantidad_racimos == 'No disponible' and 'cantidad_racimos' in clasificacion_data:
                            cantidad_racimos = clasificacion_data.get('cantidad_racimos', 'No disponible')
                    
                    # Limpiar nombres inadecuados
                    if nombre_proveedor_actual in ['No disponible', 'del Agricultor', '', None]:
                        # Como último recurso, usar una descripción basada en el código
                        if codigo_proveedor_actual:
                            nombre_proveedor_actual = f"Proveedor {codigo_proveedor_actual}"
                        else:
                            nombre_proveedor_actual = "Proveedor sin nombre"
                    
                    # Preparar los datos para la plantilla
                    item = {
                        'codigo_guia': codigo_guia,
                        'nombre_proveedor': nombre_proveedor_actual,
                        'codigo_proveedor': codigo_proveedor_actual,
                        'fecha_clasificacion': clasificacion_data.get('fecha_registro', 'No disponible'),
                        'hora_clasificacion': clasificacion_data.get('hora_registro', 'No disponible'),
                        'cantidad_racimos': cantidad_racimos if cantidad_racimos else 'No disponible',
                        'estado': clasificacion_data.get('estado', 'en_proceso'),
                        'manual_completado': 'clasificacion_manual' in clasificacion_data and clasificacion_data['clasificacion_manual'] is not None,
                        'automatica_completado': 'clasificacion_automatica' in clasificacion_data and clasificacion_data['clasificacion_automatica'] is not None,
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
        
        # Ordenar por fecha y hora convertidas a objetos datetime
        from datetime import datetime
        
        def parse_datetime_str(clasificacion):
            try:
                # Parsear fecha en formato DD/MM/YYYY y hora en formato HH:MM:SS
                fecha_str = clasificacion.get('fecha_clasificacion', '01/01/1970')
                hora_str = clasificacion.get('hora_clasificacion', '00:00:00')
                
                if '/' in fecha_str:  # Formato DD/MM/YYYY
                    dia, mes, anio = map(int, fecha_str.split('/'))
                    fecha_obj = datetime(anio, mes, dia)
                else:  # Alternativa formato YYYY-MM-DD
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
                
                # Asegurar que hora_str tiene el formato esperado
                if not hora_str or hora_str == 'No disponible':
                    hora_str = '00:00:00'
                
                # Dividir la hora, asegurando que tiene suficientes partes
                hora_parts = hora_str.split(':')
                horas = int(hora_parts[0]) if len(hora_parts) > 0 else 0
                minutos = int(hora_parts[1]) if len(hora_parts) > 1 else 0
                segundos = int(hora_parts[2]) if len(hora_parts) > 2 else 0
                
                # Combinar fecha y hora
                return datetime(
                    fecha_obj.year, fecha_obj.month, fecha_obj.day,
                    horas, minutos, segundos
                )
            except Exception as e:
                logger.error(f"Error al parsear fecha/hora para clasificación: {str(e)}")
                return datetime(1970, 1, 1)  # Fecha más antigua como fallback
        
        # Ordenar por fecha y hora parseadas en orden descendente (más recientes primero)
        clasificaciones.sort(key=parse_datetime_str, reverse=True)
        
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
        return render_template('error.html', mensaje=f"Error al listar clasificaciones: {str(e)}")

@app.route('/ver_resultados_clasificacion/<path:url_guia>')
def ver_resultados_clasificacion(url_guia):
    try:
        logger.info(f"Mostrando resultados clasificación para guía: {url_guia}")
        
        # Obtener datos de clasificación desde la base de datos
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(url_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {url_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
                logger.info(f"Claves en clasificacion_data: {clasificacion_data.keys()}")
            else:
                return render_template('error.html', message="Clasificación no encontrada")
            
        # Extraer el código de proveedor del código de guía
        codigo_proveedor = url_guia.split('_')[0] if '_' in url_guia else url_guia
        # Asegurarse de que termina con 'A' correctamente
        if re.match(r'\d+[aA]?$', codigo_proveedor):
            if codigo_proveedor.endswith('a'):
                codigo_proveedor = codigo_proveedor[:-1] + 'A'
            elif not codigo_proveedor.endswith('A'):
                codigo_proveedor = codigo_proveedor + 'A'
            
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Datos de guía no encontrados"), 404
            
        # Procesar clasificaciones si están en formato JSON
        clasificaciones = []
        if isinstance(clasificacion_data.get('clasificaciones'), str):
            try:
                clasificaciones = json.loads(clasificacion_data['clasificaciones'])
            except json.JSONDecodeError:
                clasificaciones = []
        else:
            clasificaciones = clasificacion_data.get('clasificaciones', [])
            
        # Convertir los datos de clasificación de texto a objetos Python, si es necesario
        if clasificacion_data and isinstance(clasificacion_data.get('clasificacion_manual'), str):
            try:
                clasificacion_data['clasificacion_manual'] = json.loads(clasificacion_data['clasificacion_manual'])
            except json.JSONDecodeError:
                clasificacion_data['clasificacion_manual'] = {}
                
        # Si clasificacion_data tiene nombre o codigo_proveedor, usarlo para datos_guia
        if not datos_guia.get('nombre') and clasificacion_data.get('nombre_proveedor'):
            datos_guia['nombre'] = clasificacion_data.get('nombre_proveedor')
            
        if not datos_guia.get('codigo') and clasificacion_data.get('codigo_proveedor'):
            datos_guia['codigo'] = clasificacion_data.get('codigo_proveedor')
            
        # Asegurar que tenemos cantidad_racimos
        if not datos_guia.get('cantidad_racimos') and clasificacion_data.get('racimos'):
            datos_guia['cantidad_racimos'] = clasificacion_data.get('racimos')
            
        # Asegurar que tenemos código guía transporte SAP
        if not datos_guia.get('codigo_guia_transporte_sap') and clasificacion_data.get('codigo_guia_transporte_sap'):
            datos_guia['codigo_guia_transporte_sap'] = clasificacion_data.get('codigo_guia_transporte_sap')
            
        # Preparar datos para la plantilla de resultados
        template_data = {
            'codigo_guia': url_guia,
            'codigo_proveedor': codigo_proveedor,  # Agregar código de proveedor extraído
            'id': clasificacion_data.get('id', ''),  # Añadir el ID para las rutas de imágenes
            'fecha_registro': datos_guia.get('fecha_registro'),
            'hora_registro': datos_guia.get('hora_registro'),
            'fecha_clasificacion': clasificacion_data.get('fecha_clasificacion'),
            'hora_clasificacion': clasificacion_data.get('hora_clasificacion'),
            'nombre': clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre')),
            'nombre_proveedor': clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre')),
            'cantidad_racimos': datos_guia.get('cantidad_racimos') or clasificacion_data.get('racimos'),
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {}),
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'total_racimos_detectados': clasificacion_data.get('total_racimos_detectados', 0),
            'resultados_por_foto': clasificacion_data.get('resultados_por_foto', {}),  # Añadir resultados por foto
            'clasificaciones': clasificaciones,
            'fotos': clasificacion_data.get('fotos', []),
            'modelo_utilizado': clasificacion_data.get('modelo_utilizado', 'No especificado'),
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap') or clasificacion_data.get('codigo_guia_transporte_sap'),
            'automatica_completado': 'clasificacion_automatica' in clasificacion_data and any(
                isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), dict) and 
                clasificacion_data['clasificacion_automatica'][categoria].get('cantidad', 0) > 0
                for categoria in ['verdes', 'maduros', 'sobremaduros', 'podridos', 'danio_corona', 'pendunculo_largo']
            ),
            'datos_guia': datos_guia  # Incluir datos_guia completo para la plantilla
        }
        
        # Registrar lo que estamos enviando a la plantilla
        logger.info(f"Enviando a template - código_proveedor: {template_data['codigo_proveedor']}")
        logger.info(f"Enviando a template - clasificacion_manual: {json.dumps(template_data.get('clasificacion_manual', {}))}")
        logger.info(f"Enviando a template - clasificacion_automatica: {json.dumps(template_data.get('clasificacion_automatica', {}))}")
        logger.info(f"Enviando a template - total_racimos_detectados: {template_data.get('total_racimos_detectados', 0)}")
        logger.info(f"Enviando a template - codigo_guia_transporte_sap: {template_data.get('codigo_guia_transporte_sap', 'No disponible')}")
        
        logger.info(f"Mostrando resultados de clasificación para: {url_guia}")
        return render_template('resultados_clasificacion.html', **template_data)
    except Exception as e:
        logger.error(f"Error en ver_resultados_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al cargar los resultados de clasificación")

@app.route('/ver_resultados_pesaje/<codigo_guia>')
def ver_resultados_pesaje(codigo_guia):
    try:
        codigo = codigo_guia
        
        # Variables para seguimiento
        datos_encontrados = False
        fuente_datos = None
        
        
        # Verificar si tenemos un código guía original guardado en la sesión
        original_codigo_guia = session.get('codigo_guia_original')
        if original_codigo_guia and original_codigo_guia != codigo_guia:
            logger.info(f"Usando código guía original de sesión {original_codigo_guia} en lugar de {codigo_guia}")
            codigo_guia = original_codigo_guia
        
        # Verificar si hay datos en la sesión
        peso_bruto_session = session.get('peso_bruto')
        estado_actual_session = session.get('estado_actual')
        fotos_pesaje_session = session.get('fotos_pesaje', [])
        
        logger.info(f"ver_resultados_pesaje: Datos de sesión: peso_bruto={peso_bruto_session}, estado_actual={estado_actual_session}, codigo_guia={codigo_guia}")
        
        # Utilizar el helper de datos para obtener datos completos y normalizados
        from data_helper import init_data_helper
        data_helper = init_data_helper(app)
        datos_guia = data_helper.obtener_datos_completos_guia(codigo_guia)
        
        # Si aún no hay datos, mostrar error
        if not datos_guia:
            return render_template('error.html', message=f"No se encontraron datos para la guía {codigo_guia}"), 404
        
        # Verificar que el pesaje esté completado - Preferir el estado de la sesión si está disponible
        if estado_actual_session == 'pesaje_completado':
            datos_guia['estado_actual'] = 'pesaje_completado'
        
        # Si el pesaje no está completado, simplemente mostrar los datos disponibles
        # y no redireccionar automáticamente a pesaje
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            logger.warning(f"Mostrando resultados para guía {codigo_guia} sin estado completado")
            # Añadir un mensaje de advertencia en el contexto
            datos_guia['advertencia'] = "Esta guía aún no tiene un pesaje completado."
        
        # Asegurar que el estado se actualice a pesaje_completado en la sesión si hay peso
        if peso_bruto_session:
            session['estado_actual'] = 'pesaje_completado'
            session.modified = True
            
            # Guardar el peso en los datos si no existe
            if not datos_guia.get('peso_bruto'):
                datos_guia['peso_bruto'] = peso_bruto_session
                
            # Guardar los datos actualizados
            data_helper.guardar_datos_combinados(codigo_guia, datos_guia)
        
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
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa')
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if verificacion_placa is None:
            verificacion_placa = {}
            
        placa_detectada = verificacion_placa.get('placa_detectada', '')
        placa_coincide = verificacion_placa.get('coincide', False)
        
        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia,
            'tiene_peso': True if datos_guia.get('peso_bruto') else False,
            'tiene_clasificacion': True if datos_guia.get('clasificacion') else False,
            'tipo_pesaje': datos_guia.get('tipo_pesaje', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'N/A'),
            'hora_pesaje': datos_guia.get('hora_pesaje', 'N/A'),
            'clasificacion': datos_guia.get('clasificacion', 'N/A'),
            'peso_neto': datos_guia.get('peso_neto', 'N/A'),
            'fecha_clasificacion': datos_guia.get('fecha_clasificacion', 'N/A'),
            'hora_clasificacion': datos_guia.get('hora_clasificacion', 'N/A'),
            'fotos_pesaje': datos_guia.get('fotos_pesaje', []),
            'codigo_proveedor': datos_guia.get('codigo', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'racimos': datos_guia.get('racimos', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', ''),
            'imagen_pesaje': imagen_pesaje,
            'qr_code': qr_code,
            'verificacion_placa': verificacion_placa,
            'placa_detectada': placa_detectada,
            'placa_coincide': placa_coincide
        }
        
        return render_template('resultados_pesaje.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

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
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa', {})
        placa_detectada = verificacion_placa.get('placa_detectada', '')
        placa_coincide = verificacion_placa.get('coincide', False)
        
        # Obtener fotos de pesaje si existen
        fotos_pesaje = []
        # Verificar si hay fotos en los datos de la guía
        if 'fotos_pesaje' in datos_guia and datos_guia['fotos_pesaje']:
            fotos_pesaje = datos_guia['fotos_pesaje']
        else:
            # Verificar si hay fotos en la sesión
            session_fotos = session.get('fotos_pesaje', [])
            if session_fotos:
                fotos_pesaje = session_fotos
            else:
                # Buscar fotos en el directorio del código guía
                fotos_dir = os.path.join(app.static_folder, 'fotos_pesaje', codigo_guia)
                if os.path.exists(fotos_dir):
                    for foto_file in os.listdir(fotos_dir):
                        if foto_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            fotos_pesaje.append(os.path.join('static', 'fotos_pesaje', codigo_guia, foto_file))
        
        # Asegurar que las fotos existen físicamente
        valid_fotos = []
        for foto in fotos_pesaje:
            foto_path = foto.replace('static/', '')
            full_path = os.path.join(app.static_folder, foto_path)
            if os.path.exists(full_path):
                valid_fotos.append(foto)
                
        logger.info(f"Fotos de pesaje encontradas para PDF: {len(valid_fotos)}")
        
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
            hora_generacion=hora_generacion,
            fotos_pesaje=valid_fotos,
            verificacion_placa=verificacion_placa,
            placa_detectada=placa_detectada,
            placa_coincide=placa_coincide
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
                logger.warning(f"Error al buscar wkhtmltopdf: {e}")
            
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
                hora_generacion=hora_generacion,
                fotos_pesaje=valid_fotos
            )
        
    except Exception as e:
        logger.error(f"Error general en generar_pdf_pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar el PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_pesaje', codigo_guia=codigo_guia))

@app.route('/pesajes', methods=['GET'])
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
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
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
        return redirect(url_for('upload_file'))

def obtener_registros_desde_archivos(filtros):
    """
    Función auxiliar para obtener registros desde archivos HTML (método antiguo).
    
    Args:
        filtros (dict): Diccionario con filtros a aplicar
    
    Returns:
        list: Lista de registros encontrados
    """
    # Extraer filtros
    fecha_desde = filtros.get('fecha_desde', '')
    fecha_hasta = filtros.get('fecha_hasta', '')
    codigo_proveedor = filtros.get('codigo_proveedor', '')
    nombre_proveedor = filtros.get('nombre_proveedor', '')
    placa = filtros.get('placa', '')
    
    # Preparar lista de registros
    registros = []
    
    # Verificar si el directorio de guías existe
    guias_dir = os.path.join(app.static_folder, 'guias')
    
    # Mapa para agrupar guías por código base
    guias_por_codigo_base = {}
    
    if os.path.exists(guias_dir):
        for filename in os.listdir(guias_dir):
            if filename.startswith('guia_') and filename.endswith('.html'):
                codigo_guia = filename.replace('guia_', '').replace('.html', '')
                
                # Extraer el código base (sin timestamp ni versión)
                codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                
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
                        
                    # Añadir fecha de modificación del archivo para ordenar correctamente
                    file_path = os.path.join(guias_dir, filename)
                    try:
                        mod_time = os.path.getmtime(file_path)
                        datos['file_mod_time'] = mod_time
                    except Exception:
                        datos['file_mod_time'] = 0
                        
                    # Guardar guías agrupadas por código base
                    if codigo_base not in guias_por_codigo_base:
                        guias_por_codigo_base[codigo_base] = []
                    
                    guias_por_codigo_base[codigo_base].append(datos)
    
    # Ahora procesamos cada grupo de guías con el mismo código base
    for codigo_base, guias_grupo in guias_por_codigo_base.items():
        # Ordenar por tiempo de modificación, más reciente primero
        guias_grupo.sort(key=lambda x: x.get('file_mod_time', 0), reverse=True)
        
        # Para cada grupo, tomamos solo la versión más reciente
        # A menos que tenga un sufijo "_R" que indica una revisión/actualización
        guias_filtradas = []
        ultima_guia = guias_grupo[0]  # La más reciente
        guias_filtradas.append(ultima_guia)
        
        # Buscar si hay revisiones (sufijo _R) y agregarlas también
        for guia in guias_grupo[1:]:
            codigo_guia = guia.get('codigo_guia', '')
            if '_R' in codigo_guia and codigo_guia not in [g.get('codigo_guia', '') for g in guias_filtradas]:
                guias_filtradas.append(guia)
        
        # Convertir las guías filtradas a registros
        for datos in guias_filtradas:
            # Asegurar que el código proveedor termine con A mayúscula
            codigo_proveedor = datos.get('codigo_proveedor', '')
            if codigo_proveedor and codigo_proveedor.endswith('a'):
                datos['codigo_proveedor'] = codigo_proveedor[:-1] + 'A'
            
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
        
    # Ordenar por fecha y hora más reciente
    def parse_datetime(registro):
        """
        Convierte fecha y hora de un registro a un objeto datetime para ordenamiento.
        Si no hay fecha o hay un error en el formato, devuelve una fecha muy antigua.
        """
        fecha = registro.get('fecha_registro', '')
        hora = registro.get('hora_registro', '')
        
        # Si no hay fecha y/o hora, intentar extraer del código_guia
        if not fecha or fecha == 'No disponible':
            codigo_guia = registro.get('codigo_guia', '')
            parts = codigo_guia.split('_')
            if len(parts) >= 2 and len(parts[1]) == 8 and parts[1].isdigit():
                try:
                    # Intentar extraer fecha del código_guia formato YYYYMMDD
                    fecha_obj = datetime.strptime(parts[1], '%Y%m%d')
                    fecha = fecha_obj.strftime('%d/%m/%Y')
                except:
                    return datetime(1900, 1, 1)
            else:
                return datetime(1900, 1, 1)
        
        try:
            # Intentar convertir fecha y hora
            fecha_obj = datetime.strptime(f"{fecha} {hora}", "%d/%m/%Y %H:%M:%S")
            return fecha_obj
        except Exception:
            # Intentar solo con la fecha si falla la conversión con hora
            try:
                fecha_obj = datetime.strptime(fecha, "%d/%m/%Y")
                return fecha_obj
            except Exception:
                return None
    
    # Ordenar registros por fecha y hora, más reciente primero
    registros.sort(key=parse_datetime, reverse=True)
    
    return registros

@app.route('/registro-entrada/<codigo_guia>', methods=['GET'])
def ver_registro_entrada(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    registro = None
    # Intentar obtener el registro desde la base de datos primero
    try:
        import db_utils
        registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
    except Exception as db_error:
        logger.error(f"Error accediendo a la base de datos: {db_error}")
        
    if registro:
        logger.info(f"Registro encontrado en la base de datos: {codigo_guia}")
    
    # Si no se encontró en la base de datos, intentar obtenerlo del archivo
    if not registro:
            logger.info(f"Buscando registro en archivos: {codigo_guia}")
            registro = utils.get_datos_registro(codigo_guia)
            
            if not registro:
                # Mensaje específico cuando el código no se encuentra en la base de datos ni en archivos
                flash(f'El registro con código {codigo_guia} no fue encontrado ni en la base de datos ni en los archivos', 'warning')
                return redirect(url_for('lista_registros_entrada'))
            try:
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
        registro = None
        
        # Intentar obtener el registro desde la base de datos primero
        try:
            import db_utils
            registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
            
            if registro:
                logger.info(f"Registro encontrado en la base de datos para PDF: {codigo_guia}")
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos para PDF: {db_error}")
        
        # Si no se encontró en la base de datos, intentar obtenerlo del archivo
        if not registro:
            logger.info(f"Buscando registro en archivos para PDF: {codigo_guia}")
            registro = utils.get_datos_registro(codigo_guia)
        
        if not registro:
            # Mensaje específico cuando el código no se encuentra en la base de datos ni en archivos
            flash(f'El registro con código {codigo_guia} no fue encontrado ni en la base de datos ni en los archivos', 'warning')
            return redirect(url_for('lista_registros_entrada'))
        
        # Verificar si el PDF ya existe
        pdf_filename = f"registro_{codigo_guia}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Obtener fotos de pesaje si existen
        fotos_pesaje = []
        # Verificar si hay fotos en el registro
        if 'fotos_pesaje' in registro and registro['fotos_pesaje']:
            fotos_pesaje = registro['fotos_pesaje']
        else:
            # Verificar si hay fotos en la sesión
            session_fotos = session.get('fotos_pesaje', [])
            if session_fotos:
                fotos_pesaje = session_fotos
            else:
                # Buscar fotos en el directorio del código guía
                fotos_dir = os.path.join(app.static_folder, 'fotos_pesaje', codigo_guia)
                if os.path.exists(fotos_dir):
                    for foto_file in os.listdir(fotos_dir):
                        if foto_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            fotos_pesaje.append(os.path.join('static', 'fotos_pesaje', codigo_guia, foto_file))
        
        # Asegurar que las fotos existen físicamente
        valid_fotos = []
        for foto in fotos_pesaje:
            foto_path = foto.replace('static/', '')
            full_path = os.path.join(app.static_folder, foto_path)
            if os.path.exists(full_path):
                valid_fotos.append(foto)
        
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
                # Agregar fotos de pesaje
                fotos_pesaje=valid_fotos,
                peso_bruto=registro.get('peso_bruto', ''),
                tipo_pesaje=registro.get('tipo_pesaje', ''),
                fecha_pesaje=registro.get('fecha_pesaje', ''),
                hora_pesaje=registro.get('hora_pesaje', ''),
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
        
        # Normalizar los datos para asegurar que todas las claves necesarias estén presentes
        normalized_data = {
            'nombre_agricultor': nombre_agricultor,
            'codigo': codigo,
            'racimos': webhook_data.get('racimos') or webhook_data.get('Cantidad de Racimos', ''),
            'placa': webhook_data.get('placa') or webhook_data.get('Placa', ''),
            'acarreo': webhook_data.get('acarreo') or webhook_data.get('Se Acarreó', ''),
            'cargo': webhook_data.get('cargo') or webhook_data.get('Se Cargó', ''),
            'transportador': webhook_data.get('transportador') or webhook_data.get('Transportador', ''),
            'fecha_tiquete': webhook_data.get('fecha_tiquete') or webhook_data.get('Fecha', ''),
            'nota': webhook_data.get('nota') or webhook_data.get('Nota', '')
        }
        
        # Guardar todos los datos relevantes en la sesión para uso posterior
        session['nombre_agricultor'] = normalized_data['nombre_agricultor']
        session['codigo'] = normalized_data['codigo']
        session['racimos'] = normalized_data['racimos']
        session['placa'] = normalized_data['placa']
        session['acarreo'] = normalized_data['acarreo']
        session['cargo'] = normalized_data['cargo']
        session['transportador'] = normalized_data['transportador']
        session['fecha_tiquete'] = normalized_data['fecha_tiquete']
        session['nota'] = normalized_data['nota']
        
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
        
        # Generar código único para la guía usando la función estándar de utils
        codigo_proveedor = normalized_data['codigo']
        codigo_guia = utils.generar_codigo_guia(codigo_proveedor)
        session['codigo_guia'] = codigo_guia
        
        # Registro de fecha y hora
        fecha_registro = datetime.now().strftime("%d/%m/%Y")
        hora_registro = datetime.now().strftime("%H:%M:%S")
        
        session['fecha_registro'] = fecha_registro
        session['hora_registro'] = hora_registro
        
        # Generar PDF con los datos validados
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        
        # Preparar los datos para el PDF
        parsed_data = {
            "codigo": normalized_data['codigo'],
            "nombre_agricultor": normalized_data['nombre_agricultor'],
            "cantidad_de_racimos": normalized_data['racimos'],
            "placa": normalized_data['placa'],
            "acarreo": normalized_data['acarreo'],
            "cargo": normalized_data['cargo'],
            "transportador": normalized_data['transportador'],
            "fecha": normalized_data['fecha_tiquete'],
            "codigo_guia": codigo_guia,
            "nota": normalized_data['nota']
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
            qr_filename = "default_qr.png"
        
        session.modified = True
        
        # Guardar en sesión
        session['pdf_filename'] = pdf_filename
        
        # Crear directorio para guardar la guía
        guias_dir = os.path.join(app.static_folder, 'guias')
        if not os.path.exists(guias_dir):
            os.makedirs(guias_dir)
            
        # Guardar una copia del HTML como guía
        guia_path = os.path.join(guias_dir, f"guia_{codigo_guia}.html")
        
        # Crear objeto con indicadores de campos modificados
        modified_fields = {
            'nombre_agricultor': nombre_agricultor_modificado,
            'codigo': codigo_modificado,
            'racimos': cantidad_de_racimos_modificado,
            'placa': placa_modificado,
            'acarreo': acarreo_modificado,
            'cargo': cargo_modificado,
            'transportador': transportador_modificado,
            'fecha_tiquete': fecha_modificado
        }
        
        # Convertir a JSON string para almacenar en la base de datos
        modified_fields_json = json.dumps(modified_fields)
        
        # Datos del registro completo
        datos_registro = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': normalized_data['codigo'],
            'nombre_proveedor': normalized_data['nombre_agricultor'],
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro,
            'placa': webhook_data.get('placa', ''),
            'cantidad_racimos': webhook_data.get('racimos', ''),
            'transportador': webhook_data.get('transportador', ''),
            'acarreo': webhook_data.get('acarreo', ''),
            'cargo': webhook_data.get('cargo', ''),
            'fecha_tiquete': webhook_data.get('fecha_tiquete', ''),
            'image_filename': image_filename,
            'plate_image_filename': plate_image_filename,
            'pdf_filename': pdf_filename,
            'qr_filename': qr_filename,
            'plate_text': session.get('plate_text', ''),
            'nota': webhook_data.get('nota', ''),
            'modified_fields': modified_fields_json
        }
        
        # Guardar datos en el archivo HTML (mantener compatibilidad con el sistema actual)
        with open(guia_path, 'w') as f:
            f.write(json.dumps(datos_registro))
            
        logger.info(f"Guía generada: {guia_path}")
        
        # Guardar en la base de datos SQLite
        try:
            import db_utils
            db_utils.store_entry_record(datos_registro)
            logger.info(f"Registro guardado en la base de datos: {codigo_guia}")
        except Exception as e:
            logger.error(f"Error guardando registro en la base de datos: {str(e)}")
            logger.error(traceback.format_exc())
            # Continuar con el proceso aunque falle la base de datos
        
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

@app.route('/verificar_placa_pesaje', methods=['POST'])
def verificar_placa_pesaje():
    """
    Procesa una imagen de placa durante el pesaje para verificar si coincide con la placa registrada.
    """
    try:
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
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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

@app.route('/pesaje-neto/<codigo>', methods=['GET'])
def pesaje_neto(codigo):
    """
    Maneja la vista de pesaje neto y el procesamiento del mismo
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
            return redirect(url_for('pesaje_neto', codigo=codigo_guia_completo))

        # Verificar si la guía ya tiene registrado el peso neto (para tara) o ha sido completada
        if datos_guia.get('estado_actual') in ['pesaje_tara_completado', 'registro_completado']:
            flash("Esta guía ya tiene registrado el peso neto y no se puede modificar.", "warning")
            return render_template('error.html', 
                          message="Esta guía ya tiene registrado el peso neto y no se puede modificar. Por favor, contacte al administrador si necesita realizar cambios."), 403

        # Verificar que el pesaje esté completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            flash("El pesaje no ha sido completado para esta guía.", "warning")
            return redirect(url_for('pesaje', codigo=codigo_guia_completo))

        # Renderizar template de pesaje neto
        return render_template('pesaje_neto.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje neto"), 500

@app.route('/registrar_peso_neto_directo', methods=['POST'])
def registrar_peso_neto_directo():
    """Registra el peso neto para una guía específica usando el método directo."""
    
    # Inicializar variables
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        logger.info("Procesando solicitud de registro de peso neto directo")
        
        # Obtener datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        peso_tara = request.form.get('peso_tara')
        peso_producto = request.form.get('peso_producto', '')
        
        data_received = {k: v for k, v in request.form.items()}
        logger.info(f"Datos recibidos para pesaje neto directo: {data_received}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos del pesaje
        now = datetime.now()
        
        # Manejar archivos de imágenes si están presentes
        fotos_guardadas = []
        
        if 'fotos[]' in request.files:
            fotos = request.files.getlist('fotos[]')
            
            if fotos and any(foto.filename for foto in fotos):
                # Crear directorio para las fotos si no existe
                fotos_pesaje_neto_dir = os.path.join(app.static_folder, 'fotos_pesaje_neto', codigo_guia)
                os.makedirs(fotos_pesaje_neto_dir, exist_ok=True)
                
                # Guardar cada foto
                for foto in fotos:
                    if foto and foto.filename:
                        # Crear nombre de archivo único
                        timestamp = now.strftime("%Y%m%d%H%M%S")
                        random_suffix = os.urandom(4).hex()
                        filename = f"neto_{timestamp}_{random_suffix}.jpg"
                        
                        # Guardar archivo
                        filepath = os.path.join(fotos_pesaje_neto_dir, filename)
                        foto.save(filepath)
                        
                        # Guardar ruta relativa
                        fotos_guardadas.append(os.path.join('fotos_pesaje_neto', codigo_guia, filename))
        
        # Actualizar la sesión
        session['codigo_guia'] = codigo_guia
        session['peso_tara'] = peso_tara
        session['tipo_pesaje_neto'] = 'directo'
        session['hora_pesaje_neto'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje_neto'] = now.strftime('%d/%m/%Y')
        
        if fotos_guardadas:
            session['fotos_pesaje_neto'] = fotos_guardadas
            
        # Guardar en la base de datos usando DAL
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara,
            'peso_producto': peso_producto if peso_producto else None,
            'tipo_pesaje_neto': 'directo',
            'fecha_pesaje_neto': now.strftime('%d/%m/%Y'),
            'hora_pesaje_neto': now.strftime('%H:%M:%S'),
            'fotos_pesaje_neto': fotos_guardadas
        }
        
        if dal.save_pesaje_neto(datos_pesaje):
            logger.info(f"Pesaje neto directo guardado correctamente para guía {codigo_guia}")
            
            # Redirigir a la página de resultados
            return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))
        else:
            logger.error(f"Error al guardar pesaje neto directo en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
            
    except Exception as e:
        logger.error(f"Error al registrar peso neto directo: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar peso neto directo: {str(e)}"
            
        flash(error_message, 'danger')
        return redirect(url_for('pesaje_neto', codigo=codigo_guia if 'codigo_guia' in locals() else None))
@app.route('/registrar_peso_neto_virtual', methods=['POST'])
def registrar_peso_neto_virtual():
    """Registra el peso neto para una guía específica usando el método virtual."""
    
    # Inicializar variables
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        logger.info("Procesando solicitud de registro de peso neto virtual")
        
        # Primero procesamos los datos JSON de la solicitud
        if not request.is_json:
            error_message = "Se esperaba una solicitud JSON"
            raise ValueError(error_message)
        
        data = request.get_json()
        data_received = data
        
        # Obtener datos de la solicitud JSON
        codigo_guia = data.get('codigo_guia')
        peso_tara = data.get('peso_tara')
        peso_producto = data.get('peso_producto', '')
        imagen_base64 = data.get('imagen')
        
        logger.info(f"Datos recibidos para pesaje neto virtual: codigo_guia={codigo_guia}, peso_tara={peso_tara}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos del pesaje
        now = datetime.now()
        
        # Manejar la imagen base64 si está presente
        fotos_guardadas = []
        
        if imagen_base64:
            try:
                # Decodificar la imagen base64
                import base64
                imagen_bytes = base64.b64decode(imagen_base64.split(',')[1] if ',' in imagen_base64 else imagen_base64)
                
                # Crear directorio para la imagen si no existe
                fotos_pesaje_neto_dir = os.path.join(app.static_folder, 'fotos_pesaje_neto', codigo_guia)
                os.makedirs(fotos_pesaje_neto_dir, exist_ok=True)
                
                # Crear nombre de archivo único
                timestamp = now.strftime("%Y%m%d%H%M%S")
                random_suffix = os.urandom(4).hex()
                filename = f"neto_virtual_{timestamp}_{random_suffix}.jpg"
                
                # Guardar archivo
                filepath = os.path.join(fotos_pesaje_neto_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(imagen_bytes)
                
                # Guardar ruta relativa
                fotos_guardadas.append(os.path.join('fotos_pesaje_neto', codigo_guia, filename))
                
            except Exception as e:
                logger.error(f"Error al procesar imagen base64: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Actualizar la sesión
        session['codigo_guia'] = codigo_guia
        session['peso_tara'] = peso_tara
        session['tipo_pesaje_neto'] = 'virtual'
        session['hora_pesaje_neto'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje_neto'] = now.strftime('%d/%m/%Y')
        session['fotos_pesaje_neto'] = fotos_guardadas
        
        # Registro para depuración
        logger.info(f"  codigo_guia: {session.get('codigo_guia')}")
        logger.info(f"  peso_tara: {session.get('peso_tara')}")
        logger.info(f"  tipo_pesaje_neto: {session.get('tipo_pesaje_neto')}")
        logger.info(f"  fotos_pesaje_neto: {session.get('fotos_pesaje_neto')}")
        
        # Guardar en la base de datos usando DAL
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara,
            'peso_producto': peso_producto if peso_producto else None,
            'tipo_pesaje_neto': 'virtual',
            'fecha_pesaje_neto': now.strftime('%d/%m/%Y'),
            'hora_pesaje_neto': now.strftime('%H:%M:%S'),
            'fotos_pesaje_neto': fotos_guardadas
        }
        
        if dal.save_pesaje_neto(datos_pesaje):
            logger.info(f"Pesaje neto virtual guardado correctamente para guía {codigo_guia}")
            
            # Devolver respuesta JSON con la URL de redirección
            return jsonify({
                'status': 'success',
                'message': 'Pesaje neto virtual registrado correctamente',
                'redirect_url': url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
            })
        else:
            logger.error(f"Error al guardar pesaje neto virtual en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
            
    except Exception as e:
        logger.error(f"Error al registrar peso neto virtual: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar peso neto virtual: {str(e)}"
            
        return jsonify({
            'status': 'error',
            'message': error_message
        }), 400
@app.route('/ver_resultados_pesaje_neto/<codigo_guia>')
def ver_resultados_pesaje_neto(codigo_guia):
    """
    Muestra los resultados del pesaje neto para una guía específica.
    """
    try:
        codigo = codigo_guia
        
        # Verificar si hay datos en la sesión
        peso_neto_session = session.get('peso_neto')
        peso_producto_session = session.get('peso_producto')
        fotos_pesaje_neto_session = session.get('fotos_pesaje_neto', [])
        
        logger.info(f"Datos de sesión: peso_neto={peso_neto_session}, peso_producto={peso_producto_session}")
        
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
            return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia_completo))

        # Verificar que el pesaje neto esté registrado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia_completo))

        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_neto_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para la plantilla
        imagen_bascula_neto = datos_guia.get('foto_bascula_neto')
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa')
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if verificacion_placa is None:
            verificacion_placa = {}
        
        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia_completo,
            'datos_guia': datos_guia,
            'tipo_pesaje_neto': datos_guia.get('tipo_pesaje_neto', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'peso_neto': datos_guia.get('peso_neto', 'N/A'),
            'peso_producto': datos_guia.get('peso_producto', 'N/A'),
            'fecha_pesaje_neto': datos_guia.get('fecha_pesaje_neto', 'N/A'),
            'hora_pesaje_neto': datos_guia.get('hora_pesaje_neto', 'N/A'),
            'comentarios_neto': datos_guia.get('comentarios_neto', ''),
            'fotos_pesaje_neto': datos_guia.get('fotos_pesaje_neto', []),
            'foto_bascula_neto': imagen_bascula_neto,
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_agricultor', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'racimos': datos_guia.get('racimos', 'No disponible'),
            'qr_code': qr_code,
            'verificacion_placa': verificacion_placa
        }
        
        return render_template('resultados_pesaje_neto.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

@app.route('/pesajes-neto-lista', methods=['GET'])
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

@app.route('/generar_pdf_pesaje_neto/<codigo_guia>')
def generar_pdf_pesaje_neto(codigo_guia):
    """
    Genera un PDF con los resultados del pesaje neto.
    """
    try:
        logger.info(f"Generando PDF de pesaje neto para guía: {codigo_guia}")
            
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el pesaje neto está registrado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia))
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_neto_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para el PDF
        imagen_bascula_neto = datos_guia.get('foto_bascula_neto')
        qr_code = url_for('static', filename=f'qr/{qr_filename}', _external=True)
        
        # Obtener fotos de pesaje neto si existen
        fotos_pesaje_neto = []
        # Verificar si hay fotos en los datos de la guía
        if 'fotos_pesaje_neto' in datos_guia and datos_guia['fotos_pesaje_neto']:
            fotos_pesaje_neto = datos_guia['fotos_pesaje_neto']
        
        # Filtrar fotos válidas (que existan en el sistema de archivos)
        valid_fotos = []
        for foto_path in fotos_pesaje_neto:
            if foto_path and os.path.exists(os.path.join(app.root_path, foto_path)):
                # Convertir ruta relativa a URL absoluta
                valid_fotos.append(url_for('static', filename=foto_path.replace('static/', ''), _external=True))
        
        # Fecha y hora de generación del PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF usando el mismo template que la vista
        html = render_template('pesaje_neto_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
            transportador=datos_guia.get('transportador', 'No disponible'),
            placa=datos_guia.get('placa', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            peso_neto=datos_guia.get('peso_neto', 'No disponible'),
            peso_producto=datos_guia.get('peso_producto', 'No disponible'),
            tipo_pesaje_neto=datos_guia.get('tipo_pesaje_neto', 'No disponible'),
            fecha_pesaje_neto=datos_guia.get('fecha_pesaje_neto', 'No disponible'),
            hora_pesaje_neto=datos_guia.get('hora_pesaje_neto', 'No disponible'),
            racimos=datos_guia.get('racimos', 'No disponible'),
            imagen_bascula_neto=imagen_bascula_neto,
            qr_code=qr_code,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            fotos_pesaje_neto=valid_fotos,
            comentarios_neto=datos_guia.get('comentarios_neto', '')
        )
        
        # Generar PDF desde HTML
        options = {
            'page-size': 'Letter',
            'margin-top': '0.5in',
            'margin-right': '0.5in',
            'margin-bottom': '0.5in',
            'margin-left': '0.5in',
            'encoding': "UTF-8"
        }
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"pesaje_neto_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF
        pdfkit.from_string(html, pdf_path, options=options)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))

@app.route('/ver_detalles_registro/<codigo_guia>')
def ver_detalles_registro(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    registro = None
    
    try:
        # Intentar obtener el registro desde la base de datos primero
        archivos = glob.glob(os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html'))
        if archivos:
            archivo_reciente = max(archivos, key=os.path.getmtime)
    except Exception as e:
        logger.error(f"Error al buscar archivo de guía: {str(e)}")
        flash("Error al buscar el registro", "error")
        return redirect(url_for('index'))
        
        with open(archivo_reciente, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            registro = {
                'codigo_guia': codigo_guia,
                'nombre': soup.find('span', {'id': 'nombre'}).text if soup.find('span', {'id': 'nombre'}) else 'No disponible',
                    'codigo': soup.find('span', {'id': 'codigo'}).text if soup.find('span', {'id': 'codigo'}) else 'No disponible',
                    'fecha_registro': soup.find('span', {'id': 'fecha_registro'}).text if soup.find('span', {'id': 'fecha_registro'}) else 'No disponible',
                    'hora_registro': soup.find('span', {'id': 'hora_registro'}).text if soup.find('span', {'id': 'hora_registro'}) else 'No disponible'
                }

@app.route('/procesar_clasificacion', methods=['POST'])
def procesar_clasificacion():
    try:
        # Obtener datos del formulario
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        clasificacion_manual = data.get('clasificacion_manual', {})
        
        if not codigo_guia:
            logger.error("Falta código guía en la solicitud de clasificación")
            return jsonify({"success": False, "message": "Falta código guía"}), 400
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía ya clasificada: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya ha sido clasificada y no se puede modificar'
            }), 403
            
        # Verificar que el pesaje esté completado
        if not datos_guia or datos_guia.get('estado_actual') != 'pesaje_completado':
            logger.error(f"Intento de clasificar una guía sin pesaje completado: {codigo_guia}")
            return jsonify({
                'success': False,
                'message': 'Debe completar el proceso de pesaje antes de realizar la clasificación'
            }), 400
        
        # Crear directorio para clasificaciones si no existe
        clasificaciones_dir = os.path.join(app.config['CLASIFICACIONES_FOLDER'])
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Guardar la clasificación manual
        now = datetime.now()
        fecha_registro = now.strftime('%d/%m/%Y')
        hora_registro = now.strftime('%H:%M:%S')
        
        clasificacion_data = {
            'codigo_guia': codigo_guia,
            'clasificacion_manual': clasificacion_manual,
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro
        }
        
        # Guardar en archivo JSON
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path = os.path.join(clasificaciones_dir, json_filename)
        
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
            
        # Actualizar el estado en la guía
        datos_guia.update({
            'clasificacion_completa': True,
            'fecha_clasificacion': fecha_registro,
            'hora_clasificacion': hora_registro,
            'tipo_clasificacion': 'manual',
            'clasificacion_manual': clasificacion_manual,
            'estado_actual': 'clasificacion_completada'
        })
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        return jsonify({
            'success': True,
            'message': 'Clasificación guardada exitosamente',
            'redirect_url': url_for('pesaje_neto', codigo=codigo_guia, _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error al procesar clasificación: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error al procesar la clasificación: {str(e)}'
        }), 500

@app.route('/registrar_peso_neto', methods=['POST'])
def registrar_peso_neto():
    """Registra el peso neto para una guía específica."""
    
    # Inicializar registro de errores con información detallada
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos de la solicitud
        if request.is_json:
            data = request.get_json()
            data_received = data
            codigo_guia = data.get('codigo_guia')
            peso_tara = data.get('peso_tara')
            tipo_pesaje = data.get('tipo_pesaje', 'directo')
        else:
            data_received = {k: v for k, v in request.form.items()}
            codigo_guia = request.form.get('codigo_guia')
            peso_tara = request.form.get('peso_tara')
            tipo_pesaje = request.form.get('tipo_pesaje', 'directo')
        
        logger.info(f"Registrando pesaje neto para guía {codigo_guia}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos para guardar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara
        }
        
        # Obtener datos adicionales del formulario o JSON
        for key in ['peso_bruto', 'peso_producto', 'tipo_pesaje_neto', 'imagen_pesaje_neto']:
            if request.is_json:
                if key in data:
                    datos_pesaje[key] = data.get(key)
            else:
                if key in request.form:
                    datos_pesaje[key] = request.form.get(key)
        
        # Manejar imagen si está presente
        if 'imagen_pesaje_neto' not in datos_pesaje and 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename:
                # Guardar imagen temporalmente
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"pesaje_neto_{codigo_guia}_{timestamp}.jpg"
                
                # Asegurarse de que el directorio existe
                os.makedirs('static/uploads', exist_ok=True)
                
                # Guardar archivo
                filepath = os.path.join('static/uploads', filename)
                file.save(filepath)
                
                # Guardar ruta relativa en datos_pesaje
                datos_pesaje['imagen_pesaje_neto'] = f"uploads/{filename}"
        
        # Establecer fecha y hora actuales si no se proporcionan
        if 'fecha_pesaje_neto' not in datos_pesaje:
            datos_pesaje['fecha_pesaje_neto'] = datetime.now().strftime('%d/%m/%Y')
        
        if 'hora_pesaje_neto' not in datos_pesaje:
            datos_pesaje['hora_pesaje_neto'] = datetime.now().strftime('%H:%M:%S')
        
        # Guardar datos utilizando la capa DAL
        if dal.save_pesaje_neto(datos_pesaje):
            # Actualizar datos en sesión
            session['codigo_guia'] = codigo_guia
            session['peso_tara'] = peso_tara
            
            # Si peso_neto está en datos_pesaje, usarlo; si no, será calculado por la función DAL
            if 'peso_neto' in datos_pesaje:
                session['peso_neto'] = datos_pesaje['peso_neto']
            
            # Determinar redirección basada en si es una solicitud AJAX
            if request.is_json:
                return jsonify({
                    'status': 'success',
                    'message': 'Pesaje neto registrado correctamente',
                    'redirect_url': url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
                })
            else:
                return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))
        else:
            logger.error(f"Error al guardar pesaje neto en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
    
    except Exception as e:
        logger.error(f"Error al registrar pesaje neto: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar pesaje neto: {str(e)}"
        
        if request.is_json:
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 400
        else:
            flash(error_message, 'danger')
            return redirect(url_for('pesaje_neto'))
@app.route('/admin/migrar-registros')
def migrar_registros():
    """
    Ruta administrativa para migrar registros de entrada a la base de datos.
    """
    try:
        # Importar la función de migración
        from migrate_records import migrate_entry_records
        
        # Ejecutar la migración
        result = migrate_entry_records()
        
        if result:
            return render_template('admin/resultado_operacion.html', 
                                   titulo="Migración de Registros", 
                                   mensaje="Migración de registros completada correctamente. Consulte los logs para más detalles.",
                                   exito=True)
        else:
            return render_template('admin/resultado_operacion.html', 
                                   titulo="Migración de Registros", 
                                   mensaje="Error en la migración de registros. Consulte los logs para más detalles.",
                                   exito=False)
    except Exception as e:
        logger.error(f"Error en migración de registros: {str(e)}")
        return render_template('error.html', mensaje=f"Error en migración de registros: {str(e)}")

@app.route('/procesar_clasificacion_manual/<path:url_guia>', methods=['GET', 'POST'])
def procesar_clasificacion_manual(url_guia):
    """
    Muestra la pantalla de procesamiento para clasificación automática manual
    """
    try:
        logger.info(f"Iniciando pantalla de procesamiento para clasificación manual de: {url_guia}")
        
        # Obtener datos de clasificación desde el archivo JSON
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
        
        # Variables por defecto
        nombre = "No disponible"
        codigo_proveedor = ""
        fotos = []
        
        # Cargar el archivo JSON si existe
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                    
                # Obtener las fotos del archivo de clasificación
                fotos = clasificacion_data.get('fotos', [])
                
                # Intentar obtener los datos del proveedor
                datos_registro = utils.get_datos_registro(url_guia)
                if datos_registro:
                    nombre = datos_registro.get('nombre_proveedor', 'No disponible')
                    codigo_proveedor = datos_registro.get('codigo_proveedor', '')
            except Exception as e:
                logger.error(f"Error al cargar el archivo JSON: {str(e)}")
        else:
            logger.warning(f"No se encontró el archivo de clasificación para: {url_guia}")
        
        return render_template('procesando_clasificacion.html', 
                              codigo_guia=url_guia, 
                              nombre=nombre,
                              codigo_proveedor=codigo_proveedor,
                              cantidad_fotos=len(fotos))
    except Exception as e:
        logger.error(f"Error al mostrar la pantalla de procesamiento: {str(e)}")
        return render_template('error.html', 
                              mensaje=f"Error al preparar el procesamiento de clasificación: {str(e)}",
                              volver_url=url_for('ver_resultados_automaticos', url_guia=url_guia))

# Dictionary to track the progress of image processing
processing_status = {}

@app.route('/iniciar_procesamiento/<path:url_guia>', methods=['POST'])
def iniciar_procesamiento(url_guia):
    """
    Inicia el procesamiento de imágenes con Roboflow para una guía específica.
    """
    logger.info(f"Iniciando procesamiento manual con Roboflow para guía: {url_guia}")
    
    try:
        # Verificar si existe el archivo de clasificación
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f'clasificacion_{url_guia}.json')
        
        if not os.path.exists(json_path):
            logger.error(f"No se encontró archivo de clasificación para {url_guia}")
            return jsonify({
                'status': 'error',
                'message': f"No se encontró archivo de clasificación para {url_guia}"
            }), 404
        
        # Leer información sobre la guía y sus fotos
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Buscar fotos en diferentes ubicaciones posibles
        fotos_paths = []
        
        # 1. Primero buscar en el directorio temporal de fotos
        guia_fotos_temp_dir = os.path.join(app.static_folder, 'fotos_racimos_temp', url_guia)
        if os.path.exists(guia_fotos_temp_dir):
            logger.info(f"Buscando fotos en directorio temporal: {guia_fotos_temp_dir}")
            for filename in os.listdir(guia_fotos_temp_dir):
                if filename.startswith('foto_') and filename.endswith(('.jpg', '.jpeg', '.png')):
                    fotos_paths.append(os.path.join(guia_fotos_temp_dir, filename))
        
        # 2. Si no hay fotos en el directorio temporal, buscar en el directorio principal de fotos
        if not fotos_paths:
            guia_fotos_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
            if os.path.exists(guia_fotos_dir):
                logger.info(f"Buscando fotos en directorio principal: {guia_fotos_dir}")
                for filename in os.listdir(guia_fotos_dir):
                    if utils.es_archivo_imagen(filename):
                        fotos_paths.append(os.path.join(guia_fotos_dir, filename))
        
        if not fotos_paths:
            logger.error(f"No se encontraron imágenes para procesar en {url_guia}")
            return jsonify({
                'status': 'error',
                'message': "No se encontraron imágenes para procesar"
            }), 404
        
        # Inicializar el estado de procesamiento
        processing_status[url_guia] = {
            'status': 'processing',
            'progress': 5,
            'step': 1,
            'message': 'Preparando imágenes para procesamiento...',
            'total_images': len(fotos_paths),
            'processed_images': 0
        }
        
        # Iniciar procesamiento en un hilo separado
        def process_thread():
            try:
                # Log para depuración de rutas de fotos encontradas
                logger.info(f"Procesando {len(fotos_paths)} fotos para la guía {url_guia}")
                for i, foto_path in enumerate(fotos_paths):
                    logger.info(f"Foto {i+1}: {foto_path}")
                
                # Determinar el directorio de fotos para guardar resultados
                if os.path.exists(guia_fotos_temp_dir):
                    guia_fotos_dir_para_resultados = guia_fotos_temp_dir
                else:
                    guia_fotos_dir_para_resultados = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
                    
                # Usar la función existente process_images_with_roboflow
                process_images_with_roboflow(url_guia, fotos_paths, guia_fotos_dir_para_resultados, json_path)
                # Marcar como completado
                processing_status[url_guia] = {
                    'status': 'completed',
                    'progress': 100,
                    'step': 5,
                    'message': 'Procesamiento completado correctamente',
                    'redirect_url': f'/mostrar_resultados_automaticos/{url_guia}'
                }
            except Exception as e:
                logger.error(f"Error en el procesamiento de imágenes: {str(e)}")
                logger.error(traceback.format_exc())
                processing_status[url_guia] = {
                    'status': 'error',
                    'progress': 0,
                    'step': 1,
                    'message': f"Error en el procesamiento: {str(e)}"
                }
        
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': 'Procesamiento iniciado correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error al iniciar procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f"Error al iniciar procesamiento: {str(e)}"
        }), 500

@app.route('/check_procesamiento_status/<path:url_guia>', methods=['GET'])
def check_procesamiento_status(url_guia):
    """
    Verifica el estado del procesamiento de imágenes con Roboflow para una guía específica.
    """
    try:
        # Si el estado está en el diccionario, devolverlo
        global processing_status
        if url_guia in processing_status:
            status_data = processing_status[url_guia]
            
            # Si el procesamiento ha terminado, podemos limpiar el estado
            if status_data['status'] in ['completed', 'error']:
                status_copy = status_data.copy()
                
                # Eliminar del diccionario después de un tiempo para liberar memoria
                # (pero mantenerlo para esta respuesta)
                if status_data['status'] == 'completed':
                    del processing_status[url_guia]
                
                return jsonify(status_copy)
            
            return jsonify(status_data)
        
        # Si no está en el diccionario, verificar si existe un archivo JSON que indique que se ha completado
        clasificaciones_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f'clasificacion_{url_guia}.json')
        
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                clasificacion_data = json.load(f)
                
            if 'clasificacion_automatica' in clasificacion_data:
                # Si hay clasificación automática, asumimos que se ha completado
                return jsonify({
                    'status': 'completed',
                    'progress': 100,
                    'step': 5,
                    'message': 'Procesamiento completado',
                    'redirect_url': f'/mostrar_resultados_automaticos/{url_guia}'
                })
        
        # Si no hay información, asumimos que nunca se inició o hubo un error
        return jsonify({
            'status': 'error',
            'progress': 0,
            'step': 1,
            'message': 'No se encontró información sobre el procesamiento'
        }), 404
        
    except Exception as e:
        logger.error(f"Error al verificar estado de procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'progress': 0,
            'step': 1,
            'message': f"Error al verificar estado: {str(e)}"
        }), 500

@app.route('/procesar_imagenes/<path:url_guia>')
def procesar_imagenes(url_guia):
    """
    Muestra la pantalla de procesamiento para una guía específica.
    """
    try:
        return render_template('procesando_clasificacion.html', codigo_guia=url_guia)
    except Exception as e:
        logger.error(f"Error al mostrar pantalla de procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al preparar el procesamiento: {str(e)}", 'error')
        return redirect(url_for('ver_resultados_automaticos', url_guia=url_guia))

@app.route('/mostrar_resultados_automaticos/<path:url_guia>')
def mostrar_resultados_automaticos(url_guia):
    """
    Muestra los resultados de la clasificación automática a partir del JSON generado.
    """
    try:
        datos_guia = utils.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        json_path = os.path.join(app.config['FOTOS_RACIMOS_FOLDER'], f'clasificacion_{url_guia}.json')
        
        if not os.path.exists(json_path):
            flash("No se encontraron resultados de clasificación automática para esta guía.", "warning")
            return redirect(url_for('procesar_clasificacion_manual', url_guia=url_guia))
            
        with open(json_path, 'r') as file:
            clasificacion_data = json.load(file)
            
        logger.info(f"Clasificación data: {clasificacion_data}")
        
        # Comprobar si hay clasificación automática
        if not clasificacion_data.get('clasificacion_automatica'):
            flash("No se han procesado imágenes automáticamente para esta guía.", "warning")
            return redirect(url_for('procesar_clasificacion_manual', url_guia=url_guia))

        # Obtener fotos procesadas y sus resultados
        fotos_procesadas = []
        if 'resultados_por_foto' in clasificacion_data:
            for idx, (foto_path, resultados) in enumerate(clasificacion_data['resultados_por_foto'].items()):
                # Convertir ruta absoluta a relativa para servir la imagen
                foto_path = os.path.basename(foto_path)
                foto_url = url_for('static', filename=f'fotos_racimos_procesadas/{foto_path}')
                
                # También buscar la imagen de clusters correspondiente
                foto_clusters = f'clusters_{url_guia}_foto{idx+1}.jpg'
                foto_clusters_url = url_for('static', filename=f'fotos_racimos_procesadas/{foto_clusters}')
                
                fotos_procesadas.append({
                    'original': foto_url,
                    'clusters': foto_clusters_url,
                    'resultados': resultados
                })
        
        # Actualizar los datos de la guía con la información de clasificación
        datos_guia.update({
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'fotos_procesadas': fotos_procesadas,
            'estado_clasificacion': clasificacion_data.get('estado', 'completado')
        })
        
        return render_template('auto_clasificacion_resultados.html', datos=datos_guia)
    except Exception as e:
        logger.error(f"Error al mostrar resultados automáticos: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/registro-salida/<codigo_guia>')
def registro_salida(codigo_guia):
    """
    Muestra la vista de registro de salida para una guía específica.
    Esta es la etapa final del proceso después del pesaje neto.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar que el pesaje neto esté completado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia))
            
        # Obtener fecha y hora actuales para mostrar en el formulario
        now = datetime.now()
        now_date = now.strftime('%d/%m/%Y')
        now_time = now.strftime('%H:%M:%S')
        
        return render_template('registro_salida.html', 
                              datos=datos_guia,
                              now_date=now_date,
                              now_time=now_time)
    except Exception as e:
        logger.error(f"Error al mostrar registro de salida: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar registro de salida: {str(e)}", "error")
        return redirect(url_for('index'))

@app.route('/completar_registro_salida', methods=['POST'])
def completar_registro_salida():
    """
    Procesa el formulario de registro de salida y completa el proceso.
    """
    try:
        # Obtener datos del formulario
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        fecha_salida = data.get('fecha_salida')
        hora_salida = data.get('hora_salida')
        comentarios = data.get('comentarios', '')
        firma_base64 = data.get('firma')
        
        if not codigo_guia:
            return jsonify({
                'success': False,
                'message': 'Falta el código de guía'
            }), 400
            
        # Obtener datos actuales de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Guía no encontrada'
            }), 404
            
        # Guardar la firma si se proporcionó
        firma_filename = None
        if firma_base64 and firma_base64.startswith('data:image/png;base64,'):
            # Extraer la parte de datos base64
            firma_data = firma_base64.split(',')[1]
            # Decodificar y guardar como archivo
            firma_filename = f'firma_{codigo_guia}.png'
            firma_path = os.path.join(app.config['STATIC_FOLDER'], 'firmas', firma_filename)
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(firma_path), exist_ok=True)
            
            # Guardar el archivo
            with open(firma_path, 'wb') as f:
                f.write(base64.b64decode(firma_data))
        
        # Actualizar datos de la guía
        datos_guia.update({
            'fecha_salida': fecha_salida,
            'hora_salida': hora_salida,
            'comentarios_salida': comentarios,
            'firma_salida': firma_filename,
            'estado_actual': 'registro_completado'
        })
        
        # Guardar en la base de datos si está configurado
        try:
            import db_operations
            db_operations.store_registro_salida({
                'codigo_guia': codigo_guia,
                'fecha_salida': fecha_salida,
                'hora_salida': hora_salida,
                'comentarios': comentarios,
                'firma_path': firma_filename,
                'fecha_registro': datetime.now().strftime('%d/%m/%Y'),
                'hora_registro': datetime.now().strftime('%H:%M:%S')
            })
        except Exception as db_error:
            logger.error(f"Error al guardar en la base de datos: {str(db_error)}")
            # Continuamos aunque falle la base de datos
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Generar un nuevo PDF con los datos actualizados
        try:
            pdf_filename = f'guia_{codigo_guia}.pdf'
            pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
            utils.generate_pdf(datos_guia, None, fecha_salida, hora_salida, None, codigo_guia)
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF: {str(pdf_error)}")
            # Continuamos aunque falle la generación del PDF
        
        return jsonify({
            'success': True,
            'message': 'Registro de salida completado exitosamente',
            'redirect_url': url_for('ver_resultados_salida', codigo_guia=codigo_guia)
        })
    except Exception as e:
        logger.error(f"Error al completar registro de salida: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al completar registro de salida: {str(e)}'
        }), 500

@app.route('/ver_resultados_salida/<codigo_guia>')
def ver_resultados_salida(codigo_guia):
    """
    Muestra los resultados del registro de salida para una guía específica.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la salida ha sido registrada
        if 'fecha_salida' not in datos_guia or not datos_guia['fecha_salida']:
            flash("El registro de salida no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Asegurarse de que todos los datos necesarios estén disponibles
        datos_completos = {
            # Datos básicos
            'codigo_guia': codigo_guia,
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'cantidad_racimos': datos_guia.get('cantidad_racimos', 'No disponible'),
            
            # Datos de registro de entrada
            'fecha_registro': datos_guia.get('fecha_registro', 'No disponible'),
            'hora_registro': datos_guia.get('hora_registro', 'No disponible'),
            
            # Datos de pesaje bruto
            'peso_bruto': datos_guia.get('peso_bruto', 'No disponible'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'No disponible'),
            'hora_pesaje': datos_guia.get('hora_pesaje', 'No disponible'),
            'imagen_peso': datos_guia.get('imagen_peso', None),
            
            # Datos de pesaje neto
            'peso_neto': datos_guia.get('peso_neto', 'No disponible'),
            'peso_producto': datos_guia.get('peso_producto', 'No disponible'),
            'fecha_pesaje_neto': datos_guia.get('fecha_pesaje_neto', 'No disponible'),
            'hora_pesaje_neto': datos_guia.get('hora_pesaje_neto', 'No disponible'),
            'imagen_peso_neto': datos_guia.get('imagen_peso_neto', None),
            
            # Datos de registro de salida
            'fecha_salida': datos_guia.get('fecha_salida', 'No disponible'),
            'hora_salida': datos_guia.get('hora_salida', 'No disponible'),
            'comentarios_salida': datos_guia.get('comentarios_salida', ''),
            'firma_salida': datos_guia.get('firma_salida', None),
            
            # Datos adicionales
            'verificacion_placa': datos_guia.get('verificacion_placa')
        }
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if datos_completos['verificacion_placa'] is None:
            datos_completos['verificacion_placa'] = {}
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_salida_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_salida', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
            
        datos_completos['qr_code'] = url_for('static', filename=f'qr/{qr_filename}')
        
        # Si hay firma, asegurarse de que se pueda mostrar correctamente
        if datos_completos['firma_salida']:
            datos_completos['firma_salida_url'] = url_for('static', filename=f'firmas/{datos_completos["firma_salida"]}')
        
        # Generar PDF completo si no existe
        try:
            pdf_filename = generar_pdf_completo(codigo_guia)
            if pdf_filename:
                datos_completos['pdf_url'] = url_for('static', filename=f'pdf/{pdf_filename}')
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF completo: {str(pdf_error)}")
            datos_completos['pdf_error'] = str(pdf_error)
        
        return render_template('resultados_salida.html', datos=datos_completos)
        
    except Exception as e:
        logger.error(f"Error al mostrar resultados de salida: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

# Función deshabilitada - El usuario prefiere impresión directa desde el navegador
# @app.route('/generar_pdf_completo/<codigo_guia>')
def generar_pdf_completo(codigo_guia):
    """
    Genera un PDF completo con toda la información del proceso.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el registro de salida está completado
        if datos_guia.get('estado_actual') != 'registro_completado':
            flash("El proceso no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Preparar datos para el PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('resultados_salida.html',
            datos=datos_guia,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            is_pdf=True
        )
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"proceso_completo_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF usando WeasyPrint
        HTML(
            string=html,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF completo: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_salida', codigo_guia=codigo_guia))

# Función deshabilitada - El usuario prefiere impresión directa desde el navegador
# @app.route('/generar_pdf_proceso_completo/<codigo_guia>')
def generar_pdf_proceso_completo(codigo_guia):
    """
    Genera un PDF completo con toda la información del proceso.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el registro de salida está completado
        if datos_guia.get('estado_actual') != 'registro_completado':
            flash("El proceso no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Preparar datos para el PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('resultados_salida.html',
            datos=datos_guia,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            is_pdf=True
        )
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"proceso_completo_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF usando WeasyPrint
        HTML(
            string=html,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF completo: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_salida', codigo_guia=codigo_guia))

@app.route('/verificar_placa', methods=['POST'])
def verificar_placa():
    """
    Procesa una imagen para verificar si la placa detectada coincide con la placa registrada.
    """
    try:
        logger.info("Iniciando verificación de placa")
        
        if 'foto' not in request.files:
            logger.warning("No se encontró imagen en la solicitud")
            return jsonify({
                'success': False,
                'message': 'No se encontró imagen para verificar'
            })
        
        foto = request.files['foto']
        placa_registrada = request.form.get('placa_registrada', '').strip().upper()
        
        if not placa_registrada:
            logger.warning("No hay placa registrada para comparar")
            return jsonify({
                'success': False,
                'message': 'No hay placa registrada para comparar'
            })
        
        if not foto.filename:
            logger.warning("El archivo de imagen está vacío")
            return jsonify({
                'success': False,
                'message': 'El archivo de imagen está vacío'
            })
        
        if not allowed_file(foto.filename):
            logger.warning(f"Tipo de archivo no permitido: {foto.filename}")
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido'
            })
        
        # Guardar la imagen temporalmente
        filename = secure_filename(f"verificacion_placa_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
        logger.info(f"Imagen guardada temporalmente: {temp_path}")
        
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

@app.route('/generar_pdf_clasificacion/<codigo_guia>')
def generar_pdf_clasificacion(codigo_guia):
    """
    Genera un PDF con los resultados de la clasificación.
    """
    try:
        logger.info(f"Generando PDF de clasificación para guía: {codigo_guia}")
            
        # Obtener datos de clasificación
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(codigo_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {codigo_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                flash("No se encontró la clasificación para la guía especificada.", "error")
                return redirect(url_for('index'))
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Procesar clasificaciones si están en formato JSON
        clasificaciones = []
        if isinstance(clasificacion_data.get('clasificaciones'), str):
            try:
                clasificaciones = json.loads(clasificacion_data['clasificaciones'])
            except json.JSONDecodeError:
                clasificaciones = []
        else:
            clasificaciones = clasificacion_data.get('clasificaciones', [])
            
        # Convertir los datos de clasificación de texto a objetos Python, si es necesario
        if clasificacion_data and isinstance(clasificacion_data.get('clasificacion_manual'), str):
            try:
                clasificacion_data['clasificacion_manual'] = json.loads(clasificacion_data['clasificacion_manual'])
            except json.JSONDecodeError:
                clasificacion_data['clasificacion_manual'] = {}
                
        # Generar QR para la guía si no existe
        qr_filename = f'qr_clasificacion_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_clasificacion', url_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Obtener fotos de clasificación
        fotos = clasificacion_data.get('fotos', [])
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('clasificacion_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', clasificacion_data.get('codigo_proveedor', 'No disponible')),
            nombre_proveedor=datos_guia.get('nombre', clasificacion_data.get('nombre_proveedor', 'No disponible')),
            fecha_clasificacion=clasificacion_data.get('fecha_clasificacion', clasificacion_data.get('fecha_registro', 'No disponible')),
            hora_clasificacion=clasificacion_data.get('hora_clasificacion', clasificacion_data.get('hora_registro', 'No disponible')),
            cantidad_racimos=datos_guia.get('cantidad_racimos', clasificacion_data.get('racimos', 'No disponible')),
            clasificacion_manual=clasificacion_data.get('clasificacion_manual', {}),
            clasificacion_automatica=clasificacion_data.get('clasificacion_automatica', {}),
            clasificaciones=clasificaciones,
            fotos=fotos,
            qr_code=url_for('static', filename=f'qr/{qr_filename}', _external=True),
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            datos_guia=datos_guia
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
                logger.warning(f"Error al buscar wkhtmltopdf: {e}")
            
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
            response.headers['Content-Disposition'] = f'inline; filename=clasificacion_{codigo_guia}.pdf'
            
            return response
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF con pdfkit: {str(pdf_error)}")
            
            # Fallback method - Redirect to rendering the template directly
            flash("Generando versión imprimible del documento.", "info")
            return render_template('clasificacion_print_view.html',
                codigo_guia=codigo_guia,
                codigo_proveedor=datos_guia.get('codigo_proveedor', clasificacion_data.get('codigo_proveedor', 'No disponible')),
                nombre_proveedor=datos_guia.get('nombre', clasificacion_data.get('nombre_proveedor', 'No disponible')),
                fecha_clasificacion=clasificacion_data.get('fecha_clasificacion', clasificacion_data.get('fecha_registro', 'No disponible')),
                hora_clasificacion=clasificacion_data.get('hora_clasificacion', clasificacion_data.get('hora_registro', 'No disponible')),
                cantidad_racimos=datos_guia.get('cantidad_racimos', clasificacion_data.get('racimos', 'No disponible')),
                clasificacion_manual=clasificacion_data.get('clasificacion_manual', {}),
                clasificacion_automatica=clasificacion_data.get('clasificacion_automatica', {}),
                clasificaciones=clasificaciones,
                fotos=fotos,
                qr_code=url_for('static', filename=f'qr/{qr_filename}', _external=True),
                fecha_generacion=fecha_generacion,
                hora_generacion=hora_generacion,
                codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', 'No disponible'),
                peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
                datos_guia=datos_guia
            )
            
    except Exception as e:
        logger.error(f"Error al generar PDF de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_clasificacion', url_guia=codigo_guia))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
