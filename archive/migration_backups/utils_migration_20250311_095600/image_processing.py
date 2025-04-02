import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template

# Configurar logging
logger = logging.getLogger(__name__)

class Image_processingUtils:
    def __init__(self, app):
        self.app = app
        
    def generate_qr(self, ...):
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
            
            # Generar URL para el QR
            base_url = "http://localhost:5002"  # Ajusta según tu configuración
            url = f"{base_url}/guias/{html_filename}"
            
            # Generar QR con la URL
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



    def generar_qr(self, ...):
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



