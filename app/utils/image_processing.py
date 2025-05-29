import os
import logging
import traceback
from datetime import datetime
import json
import qrcode
import requests
from flask import current_app, render_template, session, url_for

# Configurar logging
logger = logging.getLogger(__name__)

def process_plate_image(image_path, filename):
    """
    Procesa una imagen de placa usando el webhook actualizado.
    """
    try:
        # Verificar que el archivo existe
        if not os.path.exists(image_path):
            logger.error(f"No se encontró el archivo de imagen: {image_path}")
            return {"result": "error", "message": "No se encontró el archivo de imagen"}
        
        # Leer el archivo de imagen
        with open(image_path, 'rb') as f:
            image_data = f.read()
            
        # Determinar el tipo de contenido basado en la extensión del archivo
        content_type = 'image/jpeg'
        if filename.lower().endswith('.png'):
            content_type = 'image/png'
        elif filename.lower().endswith('.gif'):
            content_type = 'image/gif'
        elif filename.lower().endswith('.bmp'):
            content_type = 'image/bmp'
        
        headers = {
            'Content-Type': content_type,
            'Content-Length': str(len(image_data))
        }
        
        # Obtener la URL del webhook desde misc.routes
        from app.blueprints.misc.routes import PLACA_WEBHOOK_URL
        
        logger.info(f"Enviando imagen de placa al webhook: {PLACA_WEBHOOK_URL}")
        logger.info(f"Tamaño de imagen: {len(image_data)} bytes, Content-Type: {content_type}")
        
        response = requests.post(PLACA_WEBHOOK_URL, data=image_data, headers=headers)
        
        logger.info(f"Respuesta del webhook de placa - Status: {response.status_code}")
        logger.info(f"Headers de respuesta: {dict(response.headers)}")
        logger.info(f"Respuesta raw del webhook de placa: '{response.text}'")
        logger.info(f"Longitud de respuesta: {len(response.text)}")
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de placa: {response.text}")
            return {"result": "error", "message": f"Error del webhook de placa: {response.text}"}
            
        plate_text = response.text.strip()
        logger.info(f"Texto de placa después de strip(): '{plate_text}' (longitud: {len(plate_text)})")
        
        if not plate_text:
            logger.error("Respuesta vacía del webhook de placa")
            logger.error(f"Respuesta original antes de strip: '{repr(response.text)}'")
            return {"result": "error", "message": "No se pudo detectar la placa."}
        
        logger.info(f"Placa detectada exitosamente: '{plate_text}'")
        return {"result": "ok", "plate_text": plate_text}
                
    except Exception as e:
        logger.error(f"Error procesando imagen de placa: {str(e)}")
        logger.error(traceback.format_exc())
        return {"result": "error", "message": str(e)}

class Image_processingUtils:
    def __init__(self, app):
        self.app = app
        
    def generate_qr(self, qr_data, filename):
        try:
            logger.info("Iniciando generación de QR")
            
            # Asegurar que existe el directorio qr
            qr_dir = os.path.join(self.app.static_folder, 'qr')
            os.makedirs(qr_dir, exist_ok=True)
            
            # Obtener datos del webhook response
            data = {}
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                data = {
                    'codigo': webhook_data.get('codigo', ''),
                    'nombre': webhook_data.get('nombre_agricultor', ''),
                    'fecha_tiquete': webhook_data.get('fecha_tiquete', ''),
                    'placa': webhook_data.get('placa', ''),
                    'transportador': webhook_data.get('transportador', ''),
                    'racimos': webhook_data.get('racimos', ''),
                    'acarreo': webhook_data.get('acarreo', 'No'),
                    'cargo': webhook_data.get('cargo', 'No'),
                    'nota': webhook_data.get('nota', '')
                }
            else:
                logger.warning("No se encontró webhook_response en la sesión")
                data = qr_data
            
            # Generar nuevo código de guía usando el código validado
            now = datetime.now()
            codigo = data.get('codigo', '').strip()
            fecha_formateada = now.strftime('%Y%m%d')
            hora_formateada = now.strftime('%H%M%S')
            codigo_guia = f"{codigo}_{fecha_formateada}_{hora_formateada}"
            
            if not codigo:
                raise ValueError("Código no proporcionado")
            
            # Generar el nombre del archivo HTML de la guía
            html_filename = f"guia_{codigo_guia}.html"
            
            # Obtener la hora actual si no viene en los datos
            hora_registro = session.get('hora_registro', now.strftime("%H:%M:%S"))
            
            # Obtener datos de pesaje de la sesión o base de datos
            peso_data = session.get('peso_data', {})
            
            # Generar contenido HTML para la guía
            html_content = render_template(
                'guia_template.html',
                codigo=data.get('codigo', ''),
                nombre=data.get('nombre', ''),
                fecha_registro=session.get('fecha_registro', ''),
                hora_registro=hora_registro,
                fecha_tiquete=data.get('fecha_tiquete', ''),
                placa=data.get('placa', ''),
                transportador=data.get('transportador', ''),
                cantidad_racimos=data.get('racimos', ''),
                acarreo=data.get('acarreo', 'No'),
                cargo=data.get('cargo', 'No'),
                estado_actual='pesaje',
                codigo_guia=codigo_guia,
                pdf_filename=session.get('pdf_filename', ''),
                # Datos de pesaje
                peso_bruto=peso_data.get('peso_bruto'),
                tipo_pesaje=peso_data.get('tipo_pesaje'),
                hora_pesaje=peso_data.get('hora_pesaje'),
                pesaje_pdf=peso_data.get('pesaje_pdf'),
                nota=data.get('nota', '')
            )
            
            # Guardar el archivo HTML
            html_path = os.path.join(self.app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            # Usar la vista centralizada para todos los QRs
            from flask import url_for
            url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
            logger.info(f"Usando URL centralizada para QR: {url}")
                
            # Generar QR con la URL dinámica generada correctamente
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Crear y guardar imagen QR
            qr_image = qr.make_image(fill_color="black", back_color="white")
            qr_path = os.path.join(qr_dir, filename)
            qr_image.save(qr_path)
            
            # Verificar que el archivo se guardó correctamente
            if os.path.exists(qr_path):
                logger.info(f"QR verificado en: {qr_path}")
            else:
                raise Exception("Error al verificar archivo QR guardado")
            
            return filename
            
        except Exception as e:
            logger.error(f"Error en generación QR: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def generar_qr(self, url, output_path):
        try:
            # Crear el código QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            # Crear la imagen
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Guardar la imagen
            img.save(output_path)
            
            # Verificar que se guardó correctamente
            if os.path.exists(output_path):
                logger.info(f"QR generado correctamente en: {output_path}")
                return True
            else:
                logger.error(f"No se pudo verificar la creación del QR en: {output_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error generando QR: {str(e)}")
            logger.error(traceback.format_exc())
            return False

# Export the utils class for use in the app
image_processing_utils = None

def init_image_processing_utils(app):
    global image_processing_utils
    image_processing_utils = Image_processingUtils(app)
    return image_processing_utils



