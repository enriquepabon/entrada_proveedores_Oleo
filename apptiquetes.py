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
            
            return jsonify({
                "status": "success",
                "message": "Registro completado exitosamente",
                "pdf_filename": pdf_filename,
                "qr_filename": qr_filename,
                "codigo_guia": codigo_guia
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

@app.route('/clasificacion/<codigo>', methods=['GET', 'POST'])
def clasificacion(codigo):
    """Manejo de clasificación de fruta (automático o manual)"""
    try:
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Verificar que el pesaje esté completo
        if not datos_guia.get('peso_bruto'):
            return render_template('error.html', message="Debe completar el pesaje antes de la clasificación"), 400

        # Verificar que la clasificación no esté ya completa
        if datos_guia.get('clasificacion_completa'):
            return render_template('error.html', message="La clasificación ya fue completada"), 400

        # Renderizar template de clasificación con los datos necesarios
        return render_template('clasificacion.html', 
                           codigo=codigo,
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
    """Manejo de pesaje tara y generación de documentos"""
    pass

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

@app.route('/pesaje/<codigo>', methods=['GET', 'POST'])
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
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
            
            # Actualizar estado
            actualizar_estado_guia(codigo, {
                'estado': 'pesaje_completado',
                'peso_bruto': peso_bruto,
                'tipo_pesaje': tipo_pesaje
            })
            
            return redirect(url_for('ver_guia', codigo=codigo))
            
        # Renderizar template de pesaje
        return render_template('pesaje.html', 
                            codigo=codigo,
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
        codigo = request.form.get('codigo')
        
        if not foto:
            return jsonify({'success': False, 'message': 'Archivo no válido'})
            
        # Guardar la imagen temporalmente
        filename = secure_filename(foto.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
        # Obtener el código de guía correcto de la sesión
        codigo_guia = session.get('codigo_guia')
        if not codigo_guia:
            logger.error("No se encontró codigo_guia en la sesión")
            return jsonify({'success': False, 'message': 'No se encontró el código de guía'})
        
        # Enviar al webhook de Make para procesamiento
        with open(temp_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            data = {'codigo': codigo, 'codigo_guia': codigo_guia}
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
        codigo = data.get('codigo')
        peso_bruto = data.get('peso_bruto')
        codigo_guia = data.get('codigo_guia')
        
        if not all([codigo, peso_bruto, codigo_guia]):
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
                'codigo': codigo,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'directo',
                'fecha': fecha_hora_actual.strftime("%Y-%m-%d"),
                'hora': fecha_hora_actual.strftime("%H:%M:%S"),
                'codigo_guia': codigo_guia
            }
        )
        
        if registro_response.status_code != 200:
            logger.error(f"Error en registro de peso: {registro_response.text}")
            return jsonify({
                'success': False,
                'message': 'Error registrando el peso en el sistema'
            })
        
        # Generar PDF de pesaje
        pdf_pesaje = generar_pdf_pesaje(
            codigo=codigo,
            peso_bruto=peso_bruto,
            tipo_pesaje='directo',
            imagen_peso=session.get('imagen_pesaje')
        )
        
        if not pdf_pesaje:
            logger.error("Error generando el PDF de pesaje")
            return jsonify({
                'success': False,
                'message': 'Error generando el PDF de pesaje'
            })
        
        # Construir datos completos para guardar
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
        actualizar_estado_guia(codigo, datos_pesaje)
        
        # Obtener datos actualizados de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos actualizados de la guía'
            })
            
        # Actualizar el archivo HTML usando la nueva función
        if not actualizar_html_guia(codigo_guia, datos_guia):
            return jsonify({
                'success': False,
                'message': 'Error actualizando el archivo HTML de la guía'
            })
        
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
        codigo = data.get('codigo')
        comentarios = data.get('comentarios')
        
        if not codigo or not comentarios:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Generar código aleatorio de 6 caracteres
        codigo_autorizacion = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Obtener datos de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos de la guía'
            })
        
        # Construir URL de la guía
        guia_url = request.host_url.rstrip('/') + url_for('serve_guia', filename=f"guia_{datos_guia['codigo_guia']}.html")
        
        # Guardar código con expiración de 1 hora
        codigos_autorizacion[codigo] = {
            'codigo': codigo_autorizacion,
            'expiracion': datetime.now() + timedelta(hours=1)
        }
        
        # Enviar solicitud a Make
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL,
            json={
                'codigo': codigo,
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
        codigo = data.get('codigo')
        codigo_autorizacion = data.get('codigoAutorizacion')
        
        if not codigo or not codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Verificar código
        auth_data = codigos_autorizacion.get(codigo)
        if not auth_data:
            return jsonify({
                'success': False,
                'message': 'No hay solicitud de autorización activa'
            })
            
        # Verificar expiración
        if datetime.now() > auth_data['expiracion']:
            codigos_autorizacion.pop(codigo)
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
    
def generar_pdf_pesaje(codigo, peso_bruto, tipo_pesaje, imagen_peso=None):
    try:
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            logger.error("No se pudieron obtener los datos de la guía")
            return None
            
        # Preparar datos para el PDF
        fecha_actual = datetime.now()
        
        # Usar fecha actual si no hay fecha de registro
        fecha_registro = fecha_actual.strftime('%Y%m%d')
        
        datos_pdf = {
            'codigo': datos_guia.get('codigo_validado', codigo),
            'nombre': datos_guia.get('nombre_validado', 'No disponible'),
            'peso_bruto': peso_bruto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_actual.strftime('%d/%m/%Y'),
            'hora_pesaje': fecha_actual.strftime('%H:%M:%S'),
            'fecha_generacion': fecha_actual.strftime('%d/%m/%Y'),
            'hora_generacion': fecha_actual.strftime('%H:%M:%S'),
            'imagen_peso': imagen_peso,
            'qr_filename': session.get('qr_filename'),
            'codigo_guia': datos_guia.get('codigo_guia')
        }
        
        # Generar PDF
        rendered = render_template('pesaje_pdf_template.html', **datos_pdf)
        pdf_filename = f"pesaje_{datos_guia.get('codigo_guia', codigo)}_{fecha_actual.strftime('%Y%m%d_%H%M%S')}.pdf"
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
        codigo = data.get('codigo')
        peso_bruto = data.get('peso_bruto')
        codigo_guia = data.get('codigo_guia')
        
        if not all([codigo, peso_bruto, codigo_guia]):
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
                'codigo': codigo,
                'peso_bruto': peso_bruto,
                'tipo_pesaje': 'virtual',
                'fecha': fecha_hora.strftime("%Y-%m-%d"),
                'hora': fecha_hora.strftime("%H:%M:%S"),
                'codigo_guia': codigo_guia
            }
        )
        
        if registro_response.status_code != 200:
            logger.error(f"Error en registro de peso: {registro_response.text}")
            return jsonify({
                'success': False,
                'message': 'Error registrando el peso en el sistema'
            })
        
        # Generar PDF de pesaje
        pdf_filename = generar_pdf_pesaje(
            codigo=codigo,
            peso_bruto=peso_bruto,
            tipo_pesaje='virtual',
            imagen_peso=None
        )
        
        if not pdf_filename:
            logger.error("Error generando el PDF de pesaje")
            return jsonify({
                'success': False,
                'message': 'Error generando el PDF de pesaje'
            })
        
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
        actualizar_estado_guia(codigo, datos_pesaje)
        
        # Obtener datos actualizados de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Error obteniendo datos actualizados de la guía'
            })
            
        # Actualizar el archivo HTML
        if not actualizar_html_guia(codigo_guia, datos_guia):
            return jsonify({
                'success': False,
                'message': 'Error actualizando el archivo HTML de la guía'
            })
        
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

def obtener_datos_guia(codigo):
    try:
        # Obtener datos validados del webhook
        webhook_response = session.get('webhook_response', {})
        webhook_data = webhook_response.get('data', {})
        
        # Si webhook_data es string (JSON), intentar parsearlo
        if isinstance(webhook_data, str):
            try:
                webhook_data = json.loads(webhook_data)
            except json.JSONDecodeError:
                app.logger.error("Error parseando webhook_data")
                webhook_data = {}

        # Extraer el codigo_guia del nombre del PDF
        pdf_filename = session.get('pdf_filename')
        if pdf_filename and pdf_filename.startswith('tiquete_'):
            codigo_guia = pdf_filename[8:-4]  # Remover 'tiquete_' y '.pdf'
        else:
            app.logger.warning(f"No se encontró pdf_filename en la sesión para el código {codigo}")
            return None

        # Preparar datos usando los valores validados del webhook
        datos = {
            # Datos de registro
            'codigo': codigo,
            'codigo_validado': webhook_data.get('codigo', codigo),
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
            'pdf_filename': pdf_filename,
            'codigo_guia': codigo_guia,
            'nota': webhook_data.get('nota', ''),

            # Datos de pesaje
            'peso_bruto': session.get('peso_bruto'),
            'tipo_pesaje': session.get('tipo_pesaje'),
            'fecha_pesaje': session.get('fecha_pesaje'),
            'hora_pesaje': session.get('hora_pesaje'),
            'pesaje_pdf': session.get('pdf_pesaje'),

            # Datos de clasificación
            'clasificacion_completa': session.get('clasificacion_completa', False),
            'tipo_clasificacion': session.get('tipo_clasificacion'),
            'fecha_clasificacion': session.get('fecha_clasificacion'),
            'hora_clasificacion': session.get('hora_clasificacion'),

            # Datos de peso tara
            'peso_tara': session.get('peso_tara'),
            'tipo_peso_tara': session.get('tipo_peso_tara'),
            'fecha_peso_tara': session.get('fecha_peso_tara'),
            'hora_peso_tara': session.get('hora_peso_tara'),
            'peso_neto': session.get('peso_neto'),

            # Datos de salida
            'salida_completa': session.get('salida_completa', False),
            'fecha_salida': session.get('fecha_salida'),
            'hora_salida': session.get('hora_salida')
        }

        app.logger.info(f"Datos obtenidos para guía {codigo}: {datos}")
        return datos
    except Exception as e:
        app.logger.error(f"Error al obtener datos de la guía: {str(e)}")
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
        # Generar el HTML actualizado
        html_content = render_template('guia_template.html', **datos_guia)
        
        # Guardar el HTML actualizado
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        logger.info(f"Archivo HTML de guía actualizado: {guia_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error actualizando archivo HTML de guía: {str(e)}")
        return False

def actualizar_estado_guia(codigo, datos):
    """
    Actualiza el estado y datos de la guía
    """
    try:
        # Actualizar datos en la sesión
        for key, value in datos.items():
            session[key] = value
            
        # Obtener datos completos de la guía
        datos_guia = obtener_datos_guia(codigo)
        if not datos_guia:
            logger.error(f"Error obteniendo datos actualizados de la guía {codigo}")
            return False
            
        # Obtener el codigo_guia
        codigo_guia = datos_guia.get('codigo_guia')
        if not codigo_guia:
            logger.error(f"No se encontró codigo_guia para la guía {codigo}")
            return False
            
        # Actualizar el archivo HTML usando la nueva función
        if not actualizar_html_guia(codigo_guia, datos_guia):
            logger.error(f"Error actualizando HTML de la guía {codigo}")
            return False
            
        logger.info(f"Estado y archivo de guía actualizados para guía {codigo}: {datos}")
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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)
