from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_from_directory, current_app, flash
import os
import requests
from werkzeug.utils import secure_filename
from datetime import datetime
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
from datetime import datetime, timedelta
from knowledge_updater import knowledge_bp
import glob
from fpdf import FPDF
import re
import pdfkit

# Configuración de Roboflow
ROBOFLOW_API_KEY = "huyFoCQs7090vfjDhfgK"
ROBOFLOW_API_URL = "https://detect.roboflow.com/infer/workflows"
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

@app.route('/guias/<filename>')
def serve_guia(filename):
    """
    Sirve los archivos HTML de las guías de proceso
    """
    try:
        logger.info(f"Intentando servir guía: {filename}")
        return send_from_directory(app.config['GUIAS_FOLDER'], filename)
    except Exception as e:
        logger.error(f"Error sirviendo guía: {str(e)}")
        return render_template('error.html', message="Guía no encontrada"), 404

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
        if file.filename == '':
            return render_template('error.html', message="No se ha seleccionado ningún archivo.")
            
        if file and allowed_file(file.filename):
            try:
                # Generar nombre seguro para el archivo
                filename = secure_filename(file.filename)
                # Asegurar que el directorio de uploads existe
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
                
                # Guardar el archivo
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(image_path)
                
                # Verificar que el archivo se guardó correctamente
                if os.path.exists(image_path):
                    session['image_filename'] = filename
                    logger.info(f"Imagen guardada exitosamente: {image_path}")
                    return redirect(url_for('processing'))
                else:
                    logger.error(f"Error: El archivo no se guardó correctamente en {image_path}")
                    return render_template('error.html', message="Error al guardar el archivo.")
                    
            except Exception as e:
                logger.error(f"Error guardando archivo: {str(e)}")
                return render_template('error.html', message="Error procesando el archivo.")
        else:
            return render_template('error.html', message="Tipo de archivo no permitido.")
    
    return render_template('index.html')

@app.route('/processing')
def processing():
    image_filename = session.get('image_filename')
    if not image_filename:
        return render_template('error.html', message="No se encontró una imagen para procesar.")
    return render_template('processing.html')

@app.route('/process_image', methods=['POST'])
def process_image():
    """
    Ruta que maneja el envío de la imagen al webhook y retorna la respuesta parseada.
    """
    try:
        image_filename = session.get('image_filename')
        if not image_filename:
            logger.error("No se encontró imagen en la sesión")
            return jsonify({"result": "error", "message": "No se encontró una imagen para procesar."}), 400
        
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return jsonify({"result": "error", "message": "Archivo no encontrado."}), 404
        
        # Enviar la imagen al webhook
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            logger.info(f"Enviando imagen al webhook: {PROCESS_WEBHOOK_URL}")
            response = requests.post(PROCESS_WEBHOOK_URL, files=files)
            
        logger.info(f"Respuesta del Webhook: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({"result": "error", "message": f"Error del webhook: {response.text}"}), 500
            
        # Obtener y verificar la respuesta del texto
        response_text = response.text.strip()
        if not response_text:
            logger.error("Respuesta vacía del webhook")
            return jsonify({"result": "error", "message": "Respuesta vacía del webhook."}), 500
            
        # Procesar la respuesta
        parsed_data = parse_markdown_response(response_text)
        if not parsed_data:
            logger.error("No se pudieron parsear los datos de la respuesta")
            return jsonify({"result": "error", "message": "No se pudieron parsear los datos."}), 500
        
        # Guardar en sesión
        session['parsed_data'] = parsed_data
        logger.info("Datos parseados guardados en sesión")
        return jsonify({"result": "ok"})
        
    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "result": "error", 
            "message": f"Error al procesar la imagen: {str(e)}"
        }), 500

@app.route('/review', methods=['GET'])
def review():
    """
    Muestra la página de revisión con la tabla de tres columnas.
    """
    parsed_data = session.get('parsed_data', {})
    image_filename = session.get('image_filename', '')
    
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
        timestamp=timestamp
    )

# En apptiquetes.py, ruta update_data
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
        
        # Enviar datos al webhook
        response = requests.post(
            REVALIDATION_WEBHOOK_URL, 
            json=payload, 
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        response_text = response.text
        logger.info(f"Respuesta del webhook (raw): {response_text}")
        
        # Validar respuesta del webhook
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response_text}")
            return jsonify({
                "status": "error",
                "message": "Error en la comunicación con el webhook",
                "redirect": url_for('review', _external=True)
            }), 500
        
        try:
            # Limpiar la respuesta de caracteres de escape
            cleaned_response = response_text.replace('\\"', '"').strip()
            if cleaned_response.startswith('"') and cleaned_response.endswith('"'):
                cleaned_response = cleaned_response[1:-1]
            
            logger.info(f"Respuesta limpia antes de parsear: {cleaned_response}")
            
            try:
                response_data = json.loads(cleaned_response)
                logger.info(f"Respuesta parseada exitosamente: {response_data}")
            except json.JSONDecodeError as je:
                # Intentar un segundo método de limpieza si el primero falla
                cleaned_response = response_text.encode('utf-8').decode('unicode_escape')
                logger.info(f"Segundo intento de limpieza: {cleaned_response}")
                response_data = json.loads(cleaned_response)
                logger.info(f"Respuesta parseada en segundo intento: {response_data}")
            
            if response_data.get('status') == 'success':
                # Guardar datos en la sesión
                session['webhook_response'] = response_data
                session['table_data'] = table_data
                session.modified = True
                
                logger.info("Datos guardados en sesión, redirigiendo a revalidation_success")
                
                success_url = url_for('revalidation_success', _external=True)
                return jsonify({
                    "status": "success",
                    "message": "Validación exitosa",
                    "redirect": success_url
                })
            else:
                logger.error("El webhook devolvió un error en la validación")
                error_url = url_for('revalidation_results', _external=True)
                return jsonify({
                    "status": "error",
                    "message": response_data.get('message', 'Error en la validación'),
                    "redirect": error_url
                }), 400
                
        except json.JSONDecodeError as e:
            logger.error(f"Error al parsear JSON: {str(e)}")
            logger.error(f"JSON con error: {cleaned_response}")
            return jsonify({
                "status": "error",
                "message": "Error al procesar la respuesta del servidor",
                "redirect": url_for('review', _external=True)
            }), 500
            
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
        
        # Obtener datos necesarios de la sesión
        parsed_data = session.get('parsed_data', {})
        image_filename = session.get('image_filename', '')
        webhook_response = session.get('webhook_response', {})
        webhook_body = webhook_response.get('Body', {})
        
        if not parsed_data or not image_filename:
            return jsonify({
                "status": "error",
                "message": "No hay datos para registrar."
            }), 400

        try:
            # Obtener fecha y hora actual
            now = datetime.now()
            fecha_registro = now.strftime("%d/%m/%Y")
            hora_registro = now.strftime("%H:%M:%S")
            
            # Obtener código del agricultor y nombre del webhook
            codigo = webhook_body.get('Codigo', '').strip('"')
            nombre = webhook_body.get('Nombre', '').strip('"')
            
            if not codigo:
                # Si no está en el webhook, intentar obtenerlo de parsed_data
                codigo = next((row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
                             for row in parsed_data.get('table_data', [])
                             if row['campo'] == 'Código'), '')
            
            logger.info(f"Código obtenido para registro: {codigo}")
            
            # Generar código de guía único
            codigo_guia = f"{codigo}_{now.strftime('%Y%m%d_%H%M%S')}"
            
            # Guardar en sesión
            session['fecha_registro'] = fecha_registro
            session['hora_registro'] = hora_registro
            session['codigo_guia'] = codigo_guia
            
            # Preparar datos para el registro
            revalidation_data = {
                'Código': codigo,
                'Nombre del Agricultor': nombre,
                'Placa': next((row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
                             for row in parsed_data.get('table_data', [])
                             if row['campo'] == 'Placa'), ''),
                'Transportador': next((row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
                                    for row in parsed_data.get('table_data', [])
                                    if row['campo'] == 'Nombre Transportador'), ''),
                'Cantidad de Racimos': next((row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
                                          for row in parsed_data.get('table_data', [])
                                          if row['campo'] == 'Racimos'), '')
            }
            
            logger.info(f"Datos de revalidación preparados: {revalidation_data}")
            
            # Enviar datos al webhook de registro
            try:
                response = requests.post(
                    REGISTER_WEBHOOK_URL,
                    json={
                        "parsed_data": parsed_data,
                        "revalidation_data": revalidation_data,
                        "fecha": fecha_registro,
                        "hora": hora_registro,
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
            
            # Generar QR
            qr_filename = f"qr_{codigo}_{now.strftime('%Y%m%d_%H%M%S')}.png"
            
            # Preparar datos para el QR
            qr_data = {
                "codigo": codigo,
                "nombre": nombre,
                "fecha": fecha_registro,
                "placa": revalidation_data['Placa'],
                "transportador": revalidation_data['Transportador'],
                "cantidad_racimos": revalidation_data['Cantidad de Racimos'],
                "codigo_guia": codigo_guia
            }
            
            logger.info(f"Generando QR con datos: {qr_data}")
            
            # Generar QR usando la utilidad
            utils.generate_qr(qr_data, qr_filename)
            session['qr_filename'] = qr_filename
            
            # Generar PDF
            pdf_filename = utils.generate_pdf(
                parsed_data=parsed_data,
                image_filename=image_filename,
                fecha_procesamiento=fecha_registro,
                hora_procesamiento=hora_registro,
                revalidation_data=revalidation_data,
                codigo_guia=codigo_guia
            )
            
            session['pdf_filename'] = pdf_filename
            session['revalidation_data'] = revalidation_data
            session['estado_actual'] = 'pesaje'
            
            # Obtener el código guía completo del nombre del archivo PDF
            codigo_guia_completo = pdf_filename[8:-4]  # Remover 'tiquete_' y '.pdf'
            
            return jsonify({
                "status": "success",
                "message": "Registro completado exitosamente",
                "pdf_filename": pdf_filename,
                "qr_filename": qr_filename,
                "redirect_url": url_for('pesaje', codigo_guia=codigo_guia_completo)
            })
            
        except Exception as e:
            logger.error(f"Error procesando registro: {str(e)}")
            return jsonify({
                "status": "error",
                "message": f"Error procesando registro: {str(e)}"
            }), 500
            
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
    qr_filename = session.get('qr_filename')  # Asegúrate de que este valor se está guardando en la sesión
    
    if not pdf_filename or not qr_filename:
        return render_template('error.html', message="No se encontró el PDF o QR generado.")
    
    return render_template('review_pdf.html', 
                         pdf_filename=pdf_filename,
                         qr_filename=qr_filename)

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
        datos_guia = obtener_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Verificar que el pesaje esté completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            return render_template('error.html', 
                                message="Debe completar el proceso de pesaje antes de realizar la clasificación"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('clasificacion', codigo=codigo_guia_completo))

        # Renderizar template de clasificación
        return render_template('clasificacion.html', 
                            codigo=codigo_guia_completo,
                           codigo_guia=datos_guia.get('codigo_guia'),
                           nombre=datos_guia.get('nombre'),
                           cantidad_racimos=datos_guia.get('cantidad_racimos'),
                           peso_bruto=datos_guia.get('peso_bruto'),
                           tipo_pesaje=datos_guia.get('tipo_pesaje'),
                           fecha_registro=datos_guia.get('fecha_registro'),
                           hora_registro=datos_guia.get('hora_registro'),
                           transportador=datos_guia.get('transportador'),
                           placa=datos_guia.get('placa'))
                           
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
        datos_guia = obtener_datos_guia(codigo_guia_completo)
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
        codigo_proveedor = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        
        # Enviar al webhook de Make para procesamiento
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            data = {'codigo': codigo_proveedor}
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

@app.route('/registrar_peso_tara_directo', methods=['POST'])
def registrar_peso_tara_directo():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        peso_tara = data.get('peso_tara')
        
        if not all([codigo_guia, peso_tara]):
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })

        # Obtener fecha y hora actual
        fecha_hora_actual = datetime.now()
        
        # Obtener datos de la guía para calcular peso neto
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos de la guía'
            })
            
        # Calcular peso neto
        peso_bruto = float(datos_guia.get('peso_bruto', 0))
        peso_tara = float(peso_tara)
        peso_neto = peso_bruto - peso_tara
        
        # Registrar en Make.com
        registro_response = requests.post(
            REGISTRO_PESO_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'peso_tara': peso_tara,
                'peso_neto': peso_neto,
                'tipo_pesaje': 'directo',
                'fecha': fecha_hora_actual.strftime("%Y-%m-%d"),
                'hora': fecha_hora_actual.strftime("%H:%M:%S")
            }
        )
        
        if registro_response.status_code != 200:
            logger.error(f"Error en registro de peso tara: {registro_response.text}")
            return jsonify({
                'success': False,
                'message': 'Error registrando el peso en el sistema'
            }), 500
        
        # Generar PDF de pesaje tara
        pdf_tara = generar_pdf_pesaje_tara(
            codigo_guia=codigo_guia,
            peso_tara=peso_tara,
            peso_neto=peso_neto,
            tipo_pesaje='directo',
            imagen_peso=session.get('imagen_pesaje_tara')
        )
        
        if not pdf_tara:
            logger.error("Error generando el PDF de pesaje tara")
            return jsonify({
                'success': False,
                'message': 'Error generando el PDF de pesaje tara'
            }), 500
        
        # Datos a guardar
        datos_pesaje = {
            'estado': 'pesaje_tara_completado',
            'estado_actual': 'pesaje_tara_completado',
            'peso_tara': peso_tara,
            'peso_neto': peso_neto,
            'tipo_peso_tara': 'directo',
            'fecha_peso_tara': fecha_hora_actual.strftime("%Y-%m-%d"),
            'hora_peso_tara': fecha_hora_actual.strftime("%H:%M:%S"),
            'pdf_pesaje_tara': pdf_tara
        }
        
        # Guardar en sesión
        session.update(datos_pesaje)
        
        # Actualizar estado en la guía
        actualizar_estado_guia(codigo_guia, datos_pesaje)
        
        # Obtener datos actualizados de la guía
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos actualizados de la guía'
            }), 500
            
        # Actualizar el archivo HTML
        if not actualizar_html_guia(codigo_guia, datos_guia):
            return jsonify({
                'success': False,
                'message': 'Error actualizando el archivo HTML de la guía'
            }), 500
        
        # Construir la URL de la guía
        guia_url = f"/guias/guia_{codigo_guia}.html"
        
        return jsonify({
            'success': True,
            'message': 'Peso tara registrado correctamente',
            'redirect_url': guia_url
        })
        
    except Exception as e:
        logger.error(f"Error en registro de peso tara directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': str(e)
        })

def generar_pdf_pesaje_tara(codigo_guia, peso_tara, peso_neto, tipo_pesaje, imagen_peso=None):
    try:
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error("No se pudieron obtener los datos de la guía")
            return None
            
        # Preparar datos para el PDF
        fecha_actual = datetime.now()
        
        datos_pdf = {
            'codigo': datos_guia.get('codigo'),
            'nombre': datos_guia.get('nombre_validado', 'No disponible'),
            'peso_bruto': datos_guia.get('peso_bruto'),
            'peso_tara': peso_tara,
            'peso_neto': peso_neto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_actual.strftime('%d/%m/%Y'),
            'hora_pesaje': fecha_actual.strftime('%H:%M:%S'),
            'fecha_generacion': fecha_actual.strftime('%d/%m/%Y'),
            'hora_generacion': fecha_actual.strftime('%H:%M:%S'),
            'imagen_peso': imagen_peso,
            'qr_filename': session.get('qr_filename'),
            'codigo_guia': datos_guia.get('codigo_guia')
        }
        
        # Generar PDF usando el código guía existente
        rendered = render_template('pesaje_tara_pdf_template.html', **datos_pdf)
        pdf_filename = f"pesaje_tara_{datos_guia.get('codigo_guia')}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        
        HTML(string=rendered, base_url=app.static_folder).write_pdf(pdf_path)
        logger.info(f"PDF de pesaje tara generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error generando PDF de pesaje tara: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@app.route('/salida/<codigo>', methods=['GET', 'POST'])
def salida(codigo):
    """Manejo de proceso de salida y cierre de guía"""
    pass

@app.route('/seguimiento-guia/<codigo>')
def seguimiento_guia(codigo):
    """Vista de seguimiento completo del proceso"""
    pass

@app.route('/actualizar-estado/<codigo>', methods=['POST'])
def actualizar_estado(codigo):
    """API para actualizar el estado de cualquier etapa del proceso"""
    pass

@app.route('/pesaje/<codigo_guia>', methods=['GET', 'POST'])
def pesaje(codigo_guia):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo_guia
        
        # Obtener datos de la guía usando el código completo
        datos_guia = obtener_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        if request.method == 'POST':
            tipo_pesaje = request.form.get('tipo_pesaje')
            peso_bruto = request.form.get('peso_bruto')
            
            # Guardar datos de pesaje
            session['peso_bruto'] = peso_bruto
            session['tipo_pesaje'] = tipo_pesaje
            session['fecha_pesaje'] = datetime.now().strftime("%Y-%m-%d")
            session['hora_pesaje'] = datetime.now().strftime("%H:%M:%S")
            
            # Actualizar estado usando el código guía completo
            actualizar_estado_guia(codigo_guia_completo, {
                'estado': 'pesaje_completado',
                'peso_bruto': peso_bruto,
                'tipo_pesaje': tipo_pesaje
            })
            
            return redirect(url_for('ver_guia', codigo_guia=codigo_guia_completo))
            
        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo_guia != codigo_guia_completo:
            return redirect(url_for('pesaje', codigo_guia=codigo_guia_completo))
            
        # Renderizar template de pesaje
        return render_template('pesaje.html', 
                            codigo_guia=codigo_guia_completo,
                            datos=datos_guia)
                            
    except Exception as e:
        logger.error(f"Error en pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje"), 500

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
        codigo_proveedor = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        
        # Enviar al webhook de Make para procesamiento
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            data = {'codigo': codigo_proveedor}  # Enviamos solo el código del proveedor
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
            # Actualizar el patrón regex para manejar decimales
            peso_match = re.search(r'El peso bruto es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?', response_text)
            if peso_match:
                peso = peso_match.group(1)
                session['imagen_pesaje'] = filename
                
                return jsonify({
                    'success': True,
                    'peso': peso,
                    'message': 'Peso detectado correctamente'
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
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/registrar_peso_directo', methods=['POST'])
def registrar_peso_directo():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        if not all([codigo_guia, peso_bruto]):
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })

        # Obtener fecha y hora actual
        fecha_hora_actual = datetime.now()
        
        # Registrar en Make.com
        registro_response = requests.post(
            REGISTRO_PESO_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'directo',
                'fecha': fecha_hora_actual.strftime("%Y-%m-%d"),
                'hora': fecha_hora_actual.strftime("%H:%M:%S")
            }
        )
        
        if registro_response.status_code != 200:
            logger.error(f"Error en registro de peso: {registro_response.text}")
            return jsonify({
                'success': False,
                'message': 'Error registrando el peso en el sistema'
            }), 500
        
        # Generar PDF de pesaje
        pdf_pesaje = generar_pdf_pesaje(
            codigo_guia=codigo_guia,
            peso_bruto=peso_bruto,
            tipo_pesaje='directo',
            imagen_peso=session.get('imagen_pesaje')
        )
        
        if not pdf_pesaje:
            logger.error("Error generando el PDF de pesaje")
            return jsonify({
                'success': False,
                'message': 'Error generando el PDF de pesaje'
            }), 500
        
        # Datos a guardar
        datos_pesaje = {
            'estado': 'pesaje_completado',
            'estado_actual': 'pesaje_completado',
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'directo',
            'fecha_pesaje': fecha_hora_actual.strftime("%Y-%m-%d"),
            'hora_pesaje': fecha_hora_actual.strftime("%H:%M:%S"),
            'pdf_pesaje': pdf_pesaje
        }
        
        # Guardar en sesión
        session.update(datos_pesaje)
        
        # Actualizar estado en la guía
        actualizar_estado_guia(codigo_guia, datos_pesaje)
        
        # Obtener datos actualizados de la guía
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos actualizados de la guía'
            }), 500
            
        # Actualizar el archivo HTML usando la nueva función
        if not actualizar_html_guia(codigo_guia, datos_guia):
            return jsonify({
                'success': False,
                'message': 'Error actualizando el archivo HTML de la guía'
            }), 500
        
        # Construir la URL de la guía
        guia_url = f"/guias/guia_{codigo_guia}.html"
        
        return jsonify({
            'success': True,
            'message': 'Peso registrado correctamente',
            'redirect_url': guia_url
        })
        
    except Exception as e:
        logger.error(f"Error en registro de peso directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/solicitar_autorizacion_pesaje', methods=['POST'])
def solicitar_autorizacion_pesaje():
    """
    Procesa la solicitud de autorización para pesaje virtual
    """
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        comentarios = data.get('comentarios')
        
        if not codigo_guia or not comentarios:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Generar código aleatorio de 6 caracteres
        codigo_autorizacion = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos de la guía'
            })
        
        # Construir URL de la guía
        guia_url = request.host_url.rstrip('/') + url_for('serve_guia', filename=f"guia_{codigo_guia}.html")
        
        # Guardar código con expiración de 1 hora
        codigos_autorizacion[codigo_guia] = {
            'codigo': codigo_autorizacion,
            'expiracion': datetime.now() + timedelta(hours=1)
        }
        
        # Enviar solicitud a Make
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'url_guia': guia_url,
                'comentarios': comentarios,
                'codigo_autorizacion': codigo_autorizacion
            }
        )
        
        if response.status_code == 200:
            return jsonify({'success': True})
        else:
            return jsonify({
                'success': False,
                'message': 'Error enviando la solicitud'
            })
            
    except Exception as e:
        logger.error(f"Error en solicitud de autorización: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/validar_codigo_autorizacion', methods=['POST'])
def validar_codigo_autorizacion():
    """
    Valida el código de autorización para pesaje virtual
    """
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        codigo_autorizacion = data.get('codigoAutorizacion')
        
        if not codigo_guia or not codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Verificar código
        auth_data = codigos_autorizacion.get(codigo_guia)
        if not auth_data:
            return jsonify({
                'success': False,
                'message': 'No hay solicitud de autorización activa'
            })
            
        # Verificar expiración
        if datetime.now() > auth_data['expiracion']:
            codigos_autorizacion.pop(codigo_guia)
            return jsonify({
                'success': False,
                'message': 'El código ha expirado'
            })
            
        # Verificar código
        if auth_data['codigo'] != codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Código inválido'
            })
            
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f"Error validando código: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})
    
def generar_pdf_pesaje(codigo_guia, peso_bruto, tipo_pesaje, imagen_peso=None):
    try:
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error("No se pudieron obtener los datos de la guía")
            return None
            
        # Preparar datos para el PDF
        fecha_actual = datetime.now()
        
        datos_pdf = {
            'codigo': datos_guia.get('codigo'),  # Código del proveedor
            'nombre': datos_guia.get('nombre_validado', 'No disponible'),
            'peso_bruto': peso_bruto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_actual.strftime('%d/%m/%Y'),
            'hora_pesaje': fecha_actual.strftime('%H:%M:%S'),
            'fecha_generacion': fecha_actual.strftime('%d/%m/%Y'),
            'hora_generacion': fecha_actual.strftime('%H:%M:%S'),
            'imagen_peso': imagen_peso,
            'qr_filename': session.get('qr_filename'),
            'codigo_guia': datos_guia.get('codigo_guia')  # Usar el código guía existente
        }
        
        # Generar PDF usando el código guía existente
        rendered = render_template('pesaje_pdf_template.html', **datos_pdf)
        pdf_filename = f"pesaje_{datos_guia.get('codigo_guia')}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        
        HTML(string=rendered, base_url=app.static_folder).write_pdf(pdf_path)
        logger.info(f"PDF de pesaje generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error generando PDF de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@app.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        if not all([codigo_guia, peso_bruto]):
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
        
        # Fecha y hora actual
        fecha_hora = datetime.now()
        
        # Registrar en Make.com
        registro_response = requests.post(
            REGISTRO_PESO_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'virtual',
                'fecha': fecha_hora.strftime("%Y-%m-%d"),
                'hora': fecha_hora.strftime("%H:%M:%S")
            }
        )
        
        if registro_response.status_code != 200:
            logger.error(f"Error en registro de peso: {registro_response.text}")
            return jsonify({
                'success': False,
                'message': 'Error registrando el peso en el sistema'
            }), 500
        
        # Generar PDF de pesaje
        pdf_filename = generar_pdf_pesaje(
            codigo_guia=codigo_guia,
            peso_bruto=peso_bruto,
            tipo_pesaje='virtual',
            imagen_peso=None
        )
        
        if not pdf_filename:
            logger.error("Error generando el PDF de pesaje")
            return jsonify({
                'success': False,
                'message': 'Error generando el PDF de pesaje'
            }), 500
        
        # Datos a guardar
        datos_pesaje = {
            'estado': 'pesaje_completado',
            'estado_actual': 'pesaje_completado',
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'virtual',
            'fecha_pesaje': fecha_hora.strftime("%Y-%m-%d"),
            'hora_pesaje': fecha_hora.strftime("%H:%M:%S"),
            'pdf_pesaje': pdf_filename
        }
        
        # Guardar en sesión
        session.update(datos_pesaje)
        
        # Actualizar estado
        actualizar_estado_guia(codigo_guia, datos_pesaje)
        
        # Obtener datos actualizados de la guía
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos actualizados de la guía'
            }), 500
            
        # Actualizar el archivo HTML
        if not actualizar_html_guia(codigo_guia, datos_guia):
            return jsonify({
                'success': False,
                'message': 'Error actualizando el archivo HTML de la guía'
            }), 500
        
        # Construir la URL de la guía
        guia_url = f"/guias/guia_{codigo_guia}.html"
        
        return jsonify({
            'success': True,
            'message': 'Peso registrado correctamente',
            'redirect_url': guia_url
        })
        
    except Exception as e:
        logger.error(f"Error registrando peso virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

def obtener_datos_guia(codigo_guia):
    """
    Obtiene los datos completos de una guía basado en su código.
    """
    try:
        # Obtener datos validados del webhook
        webhook_response = session.get('webhook_response', {})
        webhook_data = {}
        
        if webhook_response:
            try:
                if isinstance(webhook_response, str):
                    webhook_data = json.loads(webhook_response)
                else:
                    webhook_data = webhook_response
            except Exception as e:
                app.logger.error(f"Error parseando webhook_data: {str(e)}")
                webhook_data = {}

        # Extraer el código base (código del proveedor)
        codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        app.logger.info(f"Buscando guía para código base: {codigo_base}")

        # 1. Intentar encontrar el archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        codigo_guia_completo = None
        source = None
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            source = 'html'
            app.logger.info(f"Código guía encontrado en archivo HTML: {codigo_guia_completo}")
        
        # 2. Si no hay HTML, buscar en archivos QR
        if not codigo_guia_completo:
            qr_files = glob.glob(os.path.join(app.config['QR_FOLDER'], f'qr_{codigo_base}_*.png'))
            if qr_files:
                qr_files.sort(key=os.path.getmtime, reverse=True)
                latest_qr = os.path.basename(qr_files[0])
                codigo_guia_completo = latest_qr[3:-4]  # Remover 'qr_' y '.png'
                source = 'qr'
                app.logger.info(f"Código guía encontrado en archivo QR: {codigo_guia_completo}")
        
        # 3. Si no hay QR, buscar en archivos PDF
        if not codigo_guia_completo:
            pdf_files = glob.glob(os.path.join(app.config['PDF_FOLDER'], f'tiquete_{codigo_base}_*.pdf'))
            if pdf_files:
                pdf_files.sort(key=os.path.getmtime, reverse=True)
                latest_pdf = os.path.basename(pdf_files[0])
                codigo_guia_completo = latest_pdf[8:-4]  # Remover 'tiquete_' y '.pdf'
                source = 'pdf'
                app.logger.info(f"Código guía encontrado en archivo PDF: {codigo_guia_completo}")
        
        # 4. Si no se encontró en archivos, intentar obtener de la sesión
        if not codigo_guia_completo:
            qr_filename = session.get('qr_filename')
            pdf_filename = session.get('pdf_filename')
            
            if qr_filename and qr_filename.startswith('qr_'):
                codigo_guia_completo = qr_filename[3:-4]
                source = 'session_qr'
                app.logger.info(f"Código guía encontrado en sesión (QR): {codigo_guia_completo}")
            elif pdf_filename and pdf_filename.startswith('tiquete_'):
                codigo_guia_completo = pdf_filename[8:-4]
                source = 'session_pdf'
                app.logger.info(f"Código guía encontrado en sesión (PDF): {codigo_guia_completo}")
        
        # 5. Validar que el código guía completo tenga el formato correcto
        if not codigo_guia_completo:
            app.logger.warning(f"No se pudo encontrar un código guía completo para {codigo_base}")
            if '_' in codigo_guia and len(codigo_guia.split('_')) >= 2:
                codigo_guia_completo = codigo_guia
                source = 'input'
                app.logger.info(f"Usando código guía de entrada: {codigo_guia_completo}")
            else:
                app.logger.error(f"No se pudo determinar un código guía válido para {codigo_base}")
                return None
        
        # Validar formato del código guía completo
        if not re.match(r'^[A-Z0-9]+_\d{8}_\d{6}$', codigo_guia_completo):
            app.logger.error(f"Formato de código guía inválido: {codigo_guia_completo}")
            return None
            
        app.logger.info(f"Código guía completo obtenido de {source}: {codigo_guia_completo}")

        # Preparar datos usando los valores validados y de la sesión
        datos = {
            # Datos de registro
            'codigo': codigo_base,  # Solo el código del proveedor
            'codigo_validado': webhook_data.get('codigo', codigo_base),
            'nombre': webhook_data.get('nombre_agricultor', 'No disponible'),
            'nombre_validado': webhook_data.get('nombre_agricultor', 'No disponible'),
            'fecha_registro': webhook_data.get('fecha_tiquete', datetime.now().strftime("%d-%m-%Y")),
            'hora_registro': session.get('hora_registro'),
            'placa': webhook_data.get('placa', 'No disponible'),
            'transportador': webhook_data.get('transportador', 'No disponible'),
            'cantidad_racimos': webhook_data.get('racimos', 'No disponible'),
            'acarreo': webhook_data.get('acarreo', 'No'),
            'cargo': webhook_data.get('cargo', 'No'),
            'estado_actual': session.get('estado_actual', 'registro'),
            'image_filename': session.get('image_filename'),
            'pdf_filename': session.get('pdf_filename'),
            'codigo_guia': codigo_guia_completo,  # Usar el código guía completo validado
            'nota': webhook_data.get('nota', ''),

            # Datos de pesaje
            'peso_bruto': session.get('peso_bruto'),
            'tipo_pesaje': session.get('tipo_pesaje'),
            'fecha_pesaje': session.get('fecha_pesaje'),
            'hora_pesaje': session.get('hora_pesaje'),
            'imagen_pesaje': session.get('imagen_pesaje'),
            'pdf_pesaje': session.get('pdf_pesaje'),

            # Datos de clasificación
            'clasificacion_completa': session.get('clasificacion_completa', False),
            'tipo_clasificacion': session.get('tipo_clasificacion'),
            'fecha_clasificacion': session.get('fecha_clasificacion'),
            'hora_clasificacion': session.get('hora_clasificacion'),
            'clasificacion_manual': session.get('clasificacion_manual'),  # Obtener de la sesión
            'clasificacion_automatica': session.get('clasificacion_automatica'),
            'pdf_clasificacion': session.get('pdf_clasificacion'),

            # Datos de pesaje tara
            'peso_tara': session.get('peso_tara'),
            'peso_neto': session.get('peso_neto'),
            'tipo_peso_tara': session.get('tipo_peso_tara'),
            'fecha_peso_tara': session.get('fecha_peso_tara'),
            'hora_peso_tara': session.get('hora_peso_tara'),
            'pdf_pesaje_tara': session.get('pdf_pesaje_tara'),

            # Datos de salida
            'fecha_salida': session.get('fecha_salida'),
            'hora_salida': session.get('hora_salida')
        }

        app.logger.info(f"Datos obtenidos para guía {codigo_guia_completo}: {datos}")
        return datos
        
    except Exception as e:
        app.logger.error(f"Error al obtener datos de la guía: {str(e)}")
        app.logger.error(traceback.format_exc())
        return None

def actualizar_html_guia(codigo_guia, datos_guia):
    """
    Actualiza el archivo HTML de la guía con los datos más recientes.
    
    Args:
        codigo_guia: El código único de la guía
        datos_guia: Diccionario con todos los datos de la guía
    
    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario
    """
    try:
        # Asegurarnos de usar el código guía correcto
        codigo_guia_completo = datos_guia.get('codigo_guia', codigo_guia)
        
        # Generar el HTML actualizado
        html_content = render_template('guia_template.html', **datos_guia)
        
        # Guardar el HTML actualizado usando el código guía completo
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia_completo}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Archivo HTML de guía actualizado: {guia_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando archivo HTML de guía: {str(e)}")
        return False

def actualizar_estado_guia(codigo_guia, datos):
    """
    Actualiza el estado y datos de la guía
    """
    try:
        # Obtener datos completos de la guía
        datos_guia = obtener_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error(f"Error obteniendo datos actualizados de la guía {codigo_guia}")
            return False
            
        # Actualizar datos en la sesión
        for key, value in datos.items():
            session[key] = value
            # También actualizar en datos_guia para que se refleje en el HTML
            datos_guia[key] = value
            
        # Obtener el codigo_guia
        codigo_guia = datos_guia.get('codigo_guia')
        if not codigo_guia:
            logger.error(f"No se encontró codigo_guia para la guía {codigo_guia}")
            return False
            
        # Actualizar el archivo HTML usando la nueva función
        if not actualizar_html_guia(codigo_guia, datos_guia):
            logger.error(f"Error actualizando HTML de la guía {codigo_guia}")
            return False
            
        logger.info(f"Estado y archivo de guía actualizados para guía {codigo_guia}: {datos}")
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando estado de guía: {str(e)}")
        return False
    
@app.route('/ver_guia/<codigo>')
def ver_guia(codigo):
    """
    Muestra la vista actual de la guía según el estado del proceso
    """
    try:
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
        
        # Obtener el estado actual del proceso
        estado_actual = datos_guia.get('estado_actual', 'registro')
        
        # Renderizar el template con los datos y el estado actual
        return render_template('guia_template.html', **datos_guia)
        
    except Exception as e:
        logger.error(f"Error mostrando guía: {str(e)}")
        return render_template('error.html', message="Error mostrando guía"), 500
    
@app.route('/notify-admin', methods=['POST'])
def notify_admin():
    try:
        data = request.get_json()
        
        # Preparar los datos para el webhook de notificación
        notification_data = {
            "codigo": data.get('codigo', ''),
            "nombre": data.get('nombre', ''),
            "nota": data.get('nota', ''),
            "fecha_notificacion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tipo_error": "Validación fallida"
        }
        
        # Llamar al webhook de notificación
        response = requests.post(
            ADMIN_NOTIFICATION_WEBHOOK_URL,
            json=notification_data,
            headers={'Content-Type': 'application/json'}
        )
        
        logger.info(f"Notificación admin enviada: {response.status_code}")
        logger.info(f"Respuesta webhook: {response.text}")
        
        if response.status_code == 200:
            return jsonify({
                "status": "success",
                "message": "Administrador notificado exitosamente"
            })
        else:
            raise Exception(f"Error en webhook: {response.text}")
            
    except Exception as e:
        logger.error(f"Error notificando admin: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": f"Error al notificar: {str(e)}"
        }), 500

@app.route('/revalidation_success')
def revalidation_success():
    """
    Muestra la página de éxito después de la revalidación.
    """
    try:
        logger.info("Iniciando revalidation_success")
        logger.info(f"Contenido de session: {dict(session)}")

        if 'webhook_response' not in session:
            logger.error("No hay datos de webhook en la sesión")
            flash('No hay datos de validación disponibles', 'error')
            return redirect(url_for('review'))

        webhook_data = session.get('webhook_response', {})
        table_data = session.get('table_data', [])
        
        logger.info(f"webhook_data: {webhook_data}")
        logger.info(f"table_data: {table_data}")

        # Extraer datos del webhook_data
        data = webhook_data.get('data', {})
        if not data and isinstance(webhook_data, str):
            try:
                # Intentar parsear si es una cadena JSON
                webhook_data = json.loads(webhook_data)
                data = webhook_data.get('data', {})
            except json.JSONDecodeError:
                logger.error(f"Error parseando webhook_data como JSON: {webhook_data}")
                data = {}

        # Preparar datos para la plantilla
        template_data = {
            'image_filename': session.get('image_filename'),
            'nombre_agricultor': data.get('nombre_agricultor', 'No disponible'),
            'codigo': data.get('codigo', 'No disponible'),
            'racimos': data.get('racimos', 'No disponible'),
            'placa': data.get('placa', 'No disponible'),
            'acarreo': data.get('acarreo', 'No disponible'),
            'cargo': data.get('cargo', 'No disponible'),
            'transportador': data.get('transportador', 'No disponible'),
            'fecha_tiquete': data.get('fecha_tiquete', 'No disponible'),
            'hora_registro': datetime.now().strftime("%H:%M:%S"),
            'nota': data.get('nota', 'Sin notas')
        }

        # Verificar si hay campos modificados comparando con table_data
        for campo in table_data:
            original = campo.get('original', '')
            sugerido = campo.get('sugerido', '')
            if original != sugerido and sugerido != 'No disponible':
                campo_key = campo['campo'].lower().replace(' ', '_')
                template_data[f"{campo_key}_modificado"] = True
                logger.info(f"Campo modificado: {campo_key} (original: {original}, sugerido: {sugerido})")

        logger.info(f"template_data preparado: {template_data}")
        return render_template('revalidation_success.html', **template_data)

    except Exception as e:
        logger.error(f"Error en revalidation_success: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al mostrar la página de éxito', 'error')
        return redirect(url_for('review'))

@app.route('/procesar_clasificacion_automatica', methods=['POST'])
def procesar_clasificacion_automatica():
    try:
        if 'foto' not in request.files:
            return jsonify({'success': False, 'message': 'No se encontró archivo de imagen'})
        
        foto = request.files['foto']
        if foto.filename == '':
            return jsonify({'success': False, 'message': 'No se seleccionó ningún archivo'})

        # Guardar y redimensionar imagen
        original_filename = secure_filename(foto.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)
        foto.save(file_path)

        # Redimensionar imagen
        try:
            with Image.open(file_path) as img:
                img = img.resize((1152, 2048), Image.Resampling.LANCZOS)
                resized_path = os.path.join(app.config['UPLOAD_FOLDER'], f"resized_{original_filename}")
                img.save(resized_path, quality=85)
                file_path = resized_path
        except Exception as e:
            logger.error(f"Error al redimensionar imagen: {e}")

        # Preparar imagen para Roboflow
        try:
            with open(file_path, "rb") as image_file:
                image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
                payload = {
                    "api_key": ROBOFLOW_API_KEY,
                    "inputs": {
                        "image": {"type": "base64", "value": image_base64}
                    }
                }
                
                headers = {
                    "Content-Type": "application/json"
                }
                
                # Hacer la petición a Roboflow
                response = requests.post(
                    f"{ROBOFLOW_API_URL}/{WORKSPACE_NAME}/{WORKFLOW_ID}",
                    json=payload,
                    headers=headers
                )

                if response.status_code != 200:
                    logger.error(f"Error en Roboflow: {response.text}")
                    return jsonify({
                        'success': False,
                        'message': 'Error en el servicio de clasificación'
                    })

                result = response.json()
                logger.info(f"Respuesta de Roboflow: {result}")
                
                # Si la respuesta es una lista, tomamos el primer elemento
                if isinstance(result, list) and len(result) > 0:
                    result = result[0]
                
                # Extraer outputs si existe
                outputs = result.get("outputs", [])
                if isinstance(outputs, list) and len(outputs) > 0:
                    out_dict = outputs[0]
                else:
                    out_dict = result  # Si no hay outputs, usar el resultado directamente
                
                logger.info(f"Diccionario de salida: {out_dict}")
                
                # Extraer clasificaciones del diccionario de salida
                clasificacion = {
                    'verde': int(out_dict.get('Racimos verdes', 0)),
                    'sobremaduro': int(out_dict.get('racimo sobremaduro', 0)),
                    'danio_corona': int(out_dict.get('racimo daño en corona', 0)),
                    'pendunculo_largo': int(out_dict.get('racimo pedunculo largo', 0)),
                    'podrido': int(out_dict.get('racimo podrido', 0))
                }

                # Obtener el total de racimos detectados
                total_racimos = int(out_dict.get('potholes_detected', 0))
                if total_racimos == 0:
                    # Si no hay total, calcularlo de la suma de clasificaciones
                    total_racimos = sum(clasificacion.values())

                logger.info(f"Clasificación extraída: {clasificacion}")
                logger.info(f"Total de racimos detectados: {total_racimos}")

                # Calcular porcentajes
                porcentajes = {}
                if total_racimos > 0:
                    for key, value in clasificacion.items():
                        porcentajes[key] = round((value / total_racimos) * 100, 2)

                # Guardar imágenes resultantes
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                imagenes_guardadas = {}

                # Guardar imagen anotada si existe
                annotated_obj = out_dict.get('annotated_image', {})
                if isinstance(annotated_obj, dict):
                    ann_val = annotated_obj.get('value', '')
                    if ann_val:
                        ann_filename = f"annotated_{timestamp}_{original_filename}"
                        ann_path = os.path.join(app.config['UPLOAD_FOLDER'], ann_filename)
                        with open(ann_path, 'wb') as f:
                            f.write(base64.b64decode(ann_val))
                        imagenes_guardadas['annotated'] = ann_filename

                # Guardar visualización de etiquetas si existe
                label_vis_obj = out_dict.get('label_visualization_1', {})
                if isinstance(label_vis_obj, dict):
                    label_val = label_vis_obj.get('value', '')
                    if label_val:
                        label_filename = f"labeled_{timestamp}_{original_filename}"
                        label_path = os.path.join(app.config['UPLOAD_FOLDER'], label_filename)
                        with open(label_path, 'wb') as f:
                            f.write(base64.b64decode(label_val))
                        imagenes_guardadas['labeled'] = label_filename

                # Guardar resultados en la sesión
                if 'resultados_individuales' not in session:
                    session['resultados_individuales'] = []
                if 'imagenes_clasificacion' not in session:
                    session['imagenes_clasificacion'] = []

                # Agregar resultados individuales con más detalle
                resultado_individual = {
                    'verde': clasificacion['verde'],
                    'sobremaduro': clasificacion['sobremaduro'],
                    'danio_corona': clasificacion['danio_corona'],
                    'pendunculo_largo': clasificacion['pendunculo_largo'],
                    'podrido': clasificacion['podrido'],
                    'total_racimos': total_racimos,
                    'porcentajes': porcentajes,
                    'imagenes': imagenes_guardadas  # Incluir las imágenes con cada resultado
                }
                
                session['resultados_individuales'].append(resultado_individual)
                session.modified = True

                return jsonify({
                    'success': True,
                    'clasificacion': clasificacion,
                    'total_racimos': total_racimos,
                    'porcentajes': porcentajes,
                    'imagenes': imagenes_guardadas
                })

        except Exception as e:
            logger.error(f"Error procesando con Roboflow: {str(e)}")
            logger.error(traceback.format_exc())
            return jsonify({
                'success': False,
                'message': f'Error en el procesamiento: {str(e)}'
            })

    except Exception as e:
        logger.error(f"Error general en clasificación automática: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})

@app.route('/generar_pdf_clasificacion', methods=['POST'])
def generar_pdf_clasificacion():
    try:
        datos = request.get_json()
        
        # Obtener los resultados individuales y las imágenes de la sesión
        resultados_individuales = session.get('resultados_individuales', [])[:3]  # Limitar a 3 resultados
        
        # Verificar que tenemos todos los datos necesarios
        if not resultados_individuales:
            logger.error("No se encontraron resultados individuales en la sesión")
            return jsonify({
                'success': False,
                'error': 'No se encontraron datos de clasificación'
            }), 400

        # Estructurar datos de clasificación manual si existe
        clasificacion_manual = {}
        if datos.get('clasificacion_manual'):
            # Determinar el total de racimos basado en el valor inicial
            valor_inicial = datos.get('valor_inicial', 0)
            total_manual = 100 if valor_inicial > 1000 else 28
            
            # Excluir 'cantidad_racimos' del cálculo de porcentajes
            categorias_validas = {k: v for k, v in datos['clasificacion_manual'].items() if k != 'cantidad_racimos'}
            
            for categoria, cantidad in categorias_validas.items():
                porcentaje = (cantidad / total_manual * 100) if total_manual > 0 else 0
                clasificacion_manual[categoria] = {
                    'cantidad': cantidad,
                    'porcentaje': porcentaje,
                    'total_racimos': total_manual
                }

        # Estructurar datos de clasificación automática si existe
        clasificacion_automatica = {}
        if datos.get('clasificacion_automatica'):
            # Calcular el total sumando los totales individuales
            total_auto = sum(resultado.get('total_racimos', 0) for resultado in resultados_individuales)
            
            # Excluir 'cantidad_racimos' del cálculo
            categorias_validas = {k: v for k, v in datos['clasificacion_automatica'].items() if k != 'cantidad_racimos'}
            
            for categoria, cantidad in categorias_validas.items():
                porcentaje = (cantidad / total_auto * 100) if total_auto > 0 else 0
                clasificacion_automatica[categoria] = {
                    'cantidad': cantidad,
                    'porcentaje': porcentaje,
                    'total_racimos': total_auto
                }

        # Generar nombre del archivo PDF
        fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"clasificacion_{datos['codigo_proveedor']}_{fecha_actual}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Obtener la ruta absoluta del directorio static
        static_folder = os.path.abspath(app.static_folder)
        
        # Renderizar el template HTML
        html_content = render_template(
            'clasificacion_pdf_template.html',
            nombre_proveedor=datos['nombre_proveedor'],
            codigo_proveedor=datos['codigo_proveedor'],
            codigo_guia=datos['codigo_guia'],
            guia_url=datos['guia_url'],
            fecha_clasificacion=datos['fecha_clasificacion'],
            hora_clasificacion=datos['hora_clasificacion'],
            tipo_clasificacion=datos['tipo_clasificacion'],
            clasificacion_manual=clasificacion_manual,
            clasificacion_automatica=clasificacion_automatica,
            resultados_individuales=resultados_individuales,
            static_folder=static_folder
        )
        
        # Generar PDF usando WeasyPrint con la URL base correcta
        HTML(
            string=html_content,
            base_url=static_folder
        ).write_pdf(pdf_path)
        
        # Actualizar datos de la sesión
        session['pdf_clasificacion'] = pdf_filename
        session['clasificacion_completa'] = True
        session['estado_actual'] = 'peso_tara'
        session['fecha_clasificacion'] = datos['fecha_clasificacion']
        session['hora_clasificacion'] = datos['hora_clasificacion']
        session['tipo_clasificacion'] = datos['tipo_clasificacion']
        session['clasificacion_manual'] = clasificacion_manual
        session['clasificacion_automatica'] = clasificacion_automatica
        session.modified = True
        
        # Actualizar estado de la guía
        datos_actualizacion = {
            'estado': 'clasificacion_completada',
            'estado_actual': 'peso_tara',
            'clasificacion_completa': True,
            'pdf_clasificacion': pdf_filename,
            'fecha_clasificacion': datos['fecha_clasificacion'],
            'hora_clasificacion': datos['hora_clasificacion'],
            'tipo_clasificacion': datos['tipo_clasificacion'],
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': clasificacion_automatica
        }
        
        # Actualizar el estado de la guía
        actualizar_estado_guia(datos['codigo_proveedor'], datos_actualizacion)
        
        # Enviar datos al webhook de registro de clasificación
        try:
            response = requests.post(
                REGISTRO_CLASIFICACION_WEBHOOK_URL,
                json={
                    'codigo': datos['codigo_proveedor'],
                    'codigo_guia': datos['codigo_guia'],
                    'clasificacion_manual': clasificacion_manual,
                    'clasificacion_automatica': clasificacion_automatica,
                    'fecha_clasificacion': datos['fecha_clasificacion'],
                    'hora_clasificacion': datos['hora_clasificacion'],
                    'tipo_clasificacion': datos['tipo_clasificacion']
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Error en webhook de registro de clasificación: {response.text}")
        except Exception as e:
            logger.error(f"Error enviando datos al webhook de clasificación: {str(e)}")
        
        # Construir la URL de redirección usando el código de guía completo
        redirect_url = datos['guia_url']
        
        # Limpiar datos temporales de la sesión
        session.pop('resultados_individuales', None)
        session.modified = True
        
        return jsonify({
            'success': True,
            'pdf_filename': pdf_filename,
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error generando PDF de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/registrar_clasificacion_manual', methods=['POST'])
def registrar_clasificacion_manual():
    try:
        logger.info("Iniciando registro de clasificación manual")
        data = request.get_json()
        logger.info(f"Datos recibidos: {data}")
        
        codigo = data.get('codigo')
        clasificacion = data.get('clasificacion')
        
        if not all([codigo, clasificacion]):
            logger.error("Faltan datos requeridos")
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Obtener fecha y hora actual
        fecha_hora = datetime.now()
            
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
        logger.info(f"Datos de la guía obtenidos: {datos_guia}")
        
        if not datos_guia:
            logger.error("Error obteniendo datos de la guía")
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos de la guía'
            }), 500
            
        # Obtener el código guía completo
        codigo_guia_completo = datos_guia.get('codigo_guia')
        if not codigo_guia_completo:
            logger.error("No se encontró el código guía completo")
            return jsonify({
                'success': False,
                'message': 'Error obteniendo el código guía'
            }), 500
            
        # Obtener y validar cantidad_racimos
        cantidad_racimos_str = datos_guia.get('cantidad_racimos', '0')
        try:
            cantidad_racimos = int(cantidad_racimos_str)
        except (ValueError, TypeError):
            cantidad_racimos = 0
            
        # Calcular total de racimos basado en la cantidad inicial
        total_racimos = 100 if cantidad_racimos >= 1000 else 28
            
        # Preparar datos de clasificación manual
        clasificacion_manual = {
            'verde': int(clasificacion.get('verde', 0)),
            'sobremaduro': int(clasificacion.get('sobremaduro', 0)),
            'danio_corona': int(clasificacion.get('danio_corona', 0)),
            'pendunculo_largo': int(clasificacion.get('pendunculo_largo', 0)),
            'podrido': int(clasificacion.get('podrido', 0)),
            'total_racimos': total_racimos
        }
        
        # Calcular porcentajes
        if total_racimos > 0:
            clasificacion_manual['porcentaje_verde'] = (clasificacion_manual['verde'] / total_racimos * 100)
            clasificacion_manual['porcentaje_sobremaduro'] = (clasificacion_manual['sobremaduro'] / total_racimos * 100)
            clasificacion_manual['porcentaje_danio_corona'] = (clasificacion_manual['danio_corona'] / total_racimos * 100)
            clasificacion_manual['porcentaje_pendunculo_largo'] = (clasificacion_manual['pendunculo_largo'] / total_racimos * 100)
            clasificacion_manual['porcentaje_podrido'] = (clasificacion_manual['podrido'] / total_racimos * 100)
        
        # Guardar en la sesión
        session['clasificacion_manual'] = clasificacion_manual
        logger.info(f"Clasificación manual guardada en sesión: {clasificacion_manual}")
        
        # Preparar datos para actualizar
        datos_actualizacion = {
            'estado': 'clasificacion_completa',
            'estado_actual': 'clasificacion_completa',
            'clasificacion_completa': True,
            'tipo_clasificacion': 'manual',
            'fecha_clasificacion': fecha_hora.strftime("%Y-%m-%d"),
            'hora_clasificacion': fecha_hora.strftime("%H:%M:%S"),
            'clasificacion_manual': clasificacion_manual
        }
        
        logger.info(f"Actualizando estado con datos: {datos_actualizacion}")
        
        # Actualizar estado usando el código guía completo
        if not actualizar_estado_guia(codigo_guia_completo, datos_actualizacion):
            logger.error("Error actualizando estado de la guía")
            return jsonify({
                'success': False,
                'message': 'Error actualizando estado de la guía'
            }), 500
        
        # Preparar datos para el webhook
        webhook_data = {
            'codigo': datos_guia.get('codigo'),  # Código del proveedor
            'codigo_guia': codigo_guia_completo,
            'verde_manual': clasificacion_manual['verde'],
            'sobremadura_manual': clasificacion_manual['sobremaduro'],
            'danio_corona_manual': clasificacion_manual['danio_corona'],
            'pendunculo_largo_manual': clasificacion_manual['pendunculo_largo'],
            'podrido_manual': clasificacion_manual['podrido'],
            'cantidad_racimo_manual': total_racimos,
            'fecha_clasificacion': fecha_hora.strftime("%Y-%m-%d"),
            'hora_clasificacion': fecha_hora.strftime("%H:%M:%S"),
            'tipo_clasificacion': 'manual'
        }
        
        logger.info(f"Enviando datos al webhook: {webhook_data}")
        
        # Enviar datos al webhook
        try:
            response = requests.post(REGISTRO_CLASIFICACION_WEBHOOK_URL, json=webhook_data)
            if not response.ok:
                logger.error(f"Error enviando datos al webhook: {response.text}")
                return jsonify({
                    'success': False,
                    'message': 'Error enviando datos al webhook'
                }), 500
        except Exception as e:
            logger.error(f"Error enviando datos al webhook: {str(e)}")
            return jsonify({
                'success': False,
                'message': 'Error enviando datos al webhook'
            }), 500
            
        return jsonify({
            'success': True,
            'message': 'Clasificación manual registrada correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error registrando clasificación manual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/guardar_clasificacion_final', methods=['POST'])
def guardar_clasificacion_final():
    try:
        logger.info("Iniciando guardado de clasificación final")
        data = request.get_json()
        if not data or 'codigo' not in data or 'tipo_clasificacion' not in data:
            return jsonify({'success': False, 'message': 'Datos incompletos'}), 400

        codigo = data['codigo']
        tipo_clasificacion = data['tipo_clasificacion']
        
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return jsonify({'success': False, 'message': 'No se encontró la guía'}), 404

        # Obtener el código guía completo
        codigo_guia_completo = datos_guia.get('codigo_guia')
        if not codigo_guia_completo:
            return jsonify({'success': False, 'message': 'Error obteniendo el código guía'}), 500

        # Actualizar estado de la guía
        fecha_actual = datetime.now()
        datos_guia['clasificacion_completa'] = True
        datos_guia['tipo_clasificacion'] = tipo_clasificacion
        datos_guia['fecha_clasificacion'] = fecha_actual.strftime('%Y-%m-%d')
        datos_guia['hora_clasificacion'] = fecha_actual.strftime('%H:%M:%S')
        
        # Obtener datos de clasificación de la sesión
        clasificacion_manual = session.get('clasificacion_manual')
        logger.info(f"Datos de clasificación manual en sesión: {clasificacion_manual}")
        
        if tipo_clasificacion in ['manual', 'ambas'] and clasificacion_manual:
            datos_guia['clasificacion_manual'] = clasificacion_manual
            logger.info(f"Agregando clasificación manual a datos_guia: {clasificacion_manual}")
            
        if tipo_clasificacion in ['automatica', 'ambas']:
            datos_guia['clasificacion_automatica'] = {
                'verde': session.get('verde_automatica', 0),
                'sobremaduro': session.get('sobremadura_automatica', 0),
                'danio_corona': session.get('danio_corona_automatica', 0),
                'pendunculo_largo': session.get('pendunculo_largo_automatica', 0),
                'podrido': session.get('podrido_automatica', 0)
            }
        
        # Generar nombre del PDF de clasificación usando el código guía completo
        clasificacion_pdf = f"clasificacion_{codigo_guia_completo}.pdf"
        datos_guia['clasificacion_pdf'] = clasificacion_pdf

        logger.info(f"Datos de clasificación preparados: {datos_guia}")

        # Guardar los cambios en la guía usando el código guía completo
        if not guardar_datos_guia(datos_guia):
            logger.error("Error guardando datos de la guía")
            return jsonify({'success': False, 'message': 'Error guardando datos de la guía'}), 500

        # Generar el PDF de clasificación
        logger.info("Intentando generar PDF de clasificación")
        try:
            if not generar_pdf_clasificacion(datos_guia):
                logger.error("Error generando PDF de clasificación")
                return jsonify({'success': False, 'message': 'Error generando PDF de clasificación'}), 500
                
            # Verificar que el archivo PDF existe
            pdf_path = os.path.join(app.config['PDF_FOLDER'], clasificacion_pdf)
            if not os.path.exists(pdf_path):
                logger.error(f"El archivo PDF no se generó en la ruta esperada: {pdf_path}")
                return jsonify({'success': False, 'message': 'Error: El PDF no se generó correctamente'}), 500
                
            logger.info(f"PDF generado exitosamente en: {pdf_path}")
            
        except Exception as pdf_error:
            logger.error(f"Error específico generando PDF: {str(pdf_error)}")
            logger.error(traceback.format_exc())
            return jsonify({'success': False, 'message': f'Error generando PDF: {str(pdf_error)}'}), 500

        logger.info("Clasificación guardada exitosamente")
        return jsonify({
            'success': True,
            'message': 'Clasificación guardada exitosamente',
            'redirect_url': f"/ver_guia/{codigo_guia_completo}"
        })
        
    except Exception as e:
        logger.error(f"Error en guardar_clasificacion_final: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error al guardar la clasificación: {str(e)}'}), 500

def generar_pdf_clasificacion(datos_guia):
    """
    Genera el PDF de clasificación
    """
    try:
        logger.info("Iniciando generación de PDF de clasificación")
        
        # Preparar datos para el template
        datos_template = {
            'codigo': datos_guia.get('codigo'),  # Código del proveedor
            'nombre': datos_guia.get('nombre', 'No disponible'),
            'fecha': datos_guia.get('fecha_clasificacion'),
            'hora': datos_guia.get('hora_clasificacion'),
            'tipo_clasificacion': datos_guia.get('tipo_clasificacion')
        }
        
        # Procesar datos de clasificación manual
        clasificacion_manual = datos_guia.get('clasificacion_manual')
        logger.info(f"Datos de clasificación manual obtenidos de datos_guia: {clasificacion_manual}")
        
        if not clasificacion_manual:
            # Intentar obtener del webhook
            try:
                payload = {
                    'codigo': datos_guia.get('codigo'),
                    'codigo_guia': datos_guia.get('codigo_guia'),
                    'obtener_datos': True
                }
                response = requests.post(REGISTRO_CLASIFICACION_WEBHOOK_URL, json=payload)
                if response.ok:
                    webhook_data = response.json()
                    logger.info(f"Datos de clasificación manual obtenidos del webhook: {webhook_data}")
                    
                    # Obtener y validar cantidad_racimos
                    cantidad_racimos_str = datos_guia.get('cantidad_racimos', '0')
                    try:
                        cantidad_racimos = int(cantidad_racimos_str)
                    except (ValueError, TypeError):
                        cantidad_racimos = 0
                        
                    # Calcular total de racimos basado en la cantidad inicial
                    total_racimos = 100 if cantidad_racimos >= 1000 else 28
                    
                    # Extraer datos del webhook
                    clasificacion_manual = {
                        'verde': int(webhook_data.get('verde_manual', 0)),
                        'sobremaduro': int(webhook_data.get('sobremadura_manual', 0)),
                        'danio_corona': int(webhook_data.get('danio_corona_manual', 0)),
                        'pendunculo_largo': int(webhook_data.get('pendunculo_largo_manual', 0)),
                        'podrido': int(webhook_data.get('podrido_manual', 0)),
                        'total_racimos': total_racimos
                    }
                    
                    # Calcular porcentajes
                    if total_racimos > 0:
                        clasificacion_manual['porcentaje_verde'] = (clasificacion_manual['verde'] / total_racimos * 100)
                        clasificacion_manual['porcentaje_sobremaduro'] = (clasificacion_manual['sobremaduro'] / total_racimos * 100)
                        clasificacion_manual['porcentaje_danio_corona'] = (clasificacion_manual['danio_corona'] / total_racimos * 100)
                        clasificacion_manual['porcentaje_pendunculo_largo'] = (clasificacion_manual['pendunculo_largo'] / total_racimos * 100)
                        clasificacion_manual['porcentaje_podrido'] = (clasificacion_manual['podrido'] / total_racimos * 100)
                    
                    logger.info(f"Datos de clasificación manual procesados del webhook: {clasificacion_manual}")
            except Exception as e:
                logger.error(f"Error obteniendo datos del webhook: {str(e)}")
                
        # Si no hay datos del webhook, intentar obtener de la sesión
        if not clasificacion_manual:
            clasificacion_manual = session.get('clasificacion_manual')
            logger.info(f"Datos de clasificación manual obtenidos de la sesión: {clasificacion_manual}")
            
        # Agregar datos de clasificación manual al template
        if clasificacion_manual:
            datos_template['clasificacion_manual'] = clasificacion_manual
            logger.info(f"Datos de clasificación manual agregados al template: {clasificacion_manual}")
        
        # Procesar datos de clasificación automática
        resultados_individuales = session.get('resultados_individuales', [])
        if resultados_individuales:
            total_verde = 0
            total_sobremaduro = 0
            total_danio_corona = 0
            total_pendunculo_largo = 0
            total_podrido = 0
            total_racimos = 0
            
            for resultado in resultados_individuales:
                total_verde += int(resultado.get('verde', 0))
                total_sobremaduro += int(resultado.get('sobremaduro', 0))
                total_danio_corona += int(resultado.get('danio_corona', 0))
                total_pendunculo_largo += int(resultado.get('pendunculo_largo', 0))
                total_podrido += int(resultado.get('podrido', 0))
                
                # Usar el total_racimos que viene del procesamiento de la imagen
                total_individual = int(resultado.get('total_racimos', 0))
                total_racimos += total_individual
                
                # Calcular porcentajes para cada resultado individual
                resultado['total_racimos'] = total_individual
                if total_individual > 0:
                    resultado['porcentaje_verde'] = (int(resultado.get('verde', 0)) / total_individual * 100)
                    resultado['porcentaje_sobremaduro'] = (int(resultado.get('sobremaduro', 0)) / total_individual * 100)
                    resultado['porcentaje_danio_corona'] = (int(resultado.get('danio_corona', 0)) / total_individual * 100)
                    resultado['porcentaje_pendunculo_largo'] = (int(resultado.get('pendunculo_largo', 0)) / total_individual * 100)
                    resultado['porcentaje_podrido'] = (int(resultado.get('podrido', 0)) / total_individual * 100)
            
            datos_template['resultados_individuales'] = resultados_individuales
            
            # Usar los totales calculados para la clasificación automática
            datos_template['clasificacion_automatica'] = {
                'verde': total_verde,
                'sobremaduro': total_sobremaduro,
                'danio_corona': total_danio_corona,
                'pendunculo_largo': total_pendunculo_largo,
                'podrido': total_podrido,
                'total_racimos': total_racimos,
                'porcentaje_verde': (total_verde / total_racimos * 100) if total_racimos > 0 else 0,
                'porcentaje_sobremaduro': (total_sobremaduro / total_racimos * 100) if total_racimos > 0 else 0,
                'porcentaje_danio_corona': (total_danio_corona / total_racimos * 100) if total_racimos > 0 else 0,
                'porcentaje_pendunculo_largo': (total_pendunculo_largo / total_racimos * 100) if total_racimos > 0 else 0,
                'porcentaje_podrido': (total_podrido / total_racimos * 100) if total_racimos > 0 else 0
            }
            logger.info(f"Datos de clasificación automática procesados: {datos_template['clasificacion_automatica']}")

        # Generar nombre del archivo PDF
        codigo_guia = datos_guia.get('codigo_guia')
        if not codigo_guia:
            logger.error("No se encontró codigo_guia en los datos")
            return None
            
        pdf_filename = f"clasificacion_{codigo_guia}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Renderizar el template HTML
        html_content = render_template('clasificacion_pdf_template.html', **datos_template)
        
        # Convertir HTML a PDF usando WeasyPrint
        HTML(string=html_content, base_url=app.static_folder).write_pdf(pdf_path)
        
        logger.info(f"PDF de clasificación generado exitosamente: {pdf_path}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error generando PDF de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def guardar_datos_guia(datos_guia):
    """
    Guarda los datos de la guía en el archivo HTML y actualiza la sesión
    
    Args:
        datos_guia: Diccionario con todos los datos de la guía
    
    Returns:
        bool: True si el guardado fue exitoso, False en caso contrario
    """
    try:
        # Actualizar datos en la sesión
        for key, value in datos_guia.items():
            session[key] = value
        
        # Obtener el código guía
        codigo_guia = datos_guia.get('codigo_guia')
        if not codigo_guia:
            logger.error("No se encontró codigo_guia en los datos")
            return False
            
        # Actualizar el archivo HTML
        if not actualizar_html_guia(codigo_guia, datos_guia):
            logger.error(f"Error actualizando HTML de la guía {codigo_guia}")
            return False
            
        logger.info(f"Datos de guía guardados exitosamente para guía {codigo_guia}")
        return True
        
    except Exception as e:
        logger.error(f"Error guardando datos de guía: {str(e)}")
        return False

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
