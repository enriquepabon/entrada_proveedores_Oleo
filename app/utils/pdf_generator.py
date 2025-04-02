import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template, session
import time
import re
from weasyprint import HTML

# Configurar logging
logger = logging.getLogger(__name__)

class Pdf_generatorUtils:
    def __init__(self, app):
        self.app = app
        
    def generate_pdf(self, parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None, codigo_guia=None):
        """
        Genera un PDF a partir de los datos del webhook.
        """
        try:
            logger.info("Iniciando generación de PDF")
            
            # Verificar que tengamos la configuración de carpetas
            if 'PDF_FOLDER' not in self.app.config:
                logger.warning("PDF_FOLDER no definido en la configuración, usando ruta por defecto")
                self.app.config['PDF_FOLDER'] = os.path.join(self.app.static_folder, 'pdfs')
                
            # Asegurar que el directorio existe
            pdf_dir = self.app.config['PDF_FOLDER']
            os.makedirs(pdf_dir, exist_ok=True)
            
            logger.info(f"Directorio verificado: PDF_FOLDER={pdf_dir}")
            
            now = datetime.now()
            
            # Extraer datos del webhook response
            data = {}
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                data = {
                    'codigo': webhook_data.get('codigo', ''),
                    'nombre_agricultor': webhook_data.get('nombre_agricultor', ''),
                    'racimos': webhook_data.get('racimos', ''),
                    'placa': webhook_data.get('placa', ''),
                    'acarreo': webhook_data.get('acarreo', 'No'),
                    'cargo': webhook_data.get('cargo', 'No'),
                    'transportador': webhook_data.get('transportador', 'No registrado'),
                    'fecha_tiquete': webhook_data.get('fecha_tiquete', ''),
                    'nota': webhook_data.get('nota', '')
                }
            else:
                logger.warning("No se encontró webhook_response en la sesión")
                # Tratar de obtener datos básicos de los parámetros
                if revalidation_data:
                    data = revalidation_data
                elif parsed_data:
                    # Intentar extraer datos básicos
                    data = {
                        'codigo': parsed_data.get('codigo', ''),
                        'nombre_agricultor': parsed_data.get('nombre_agricultor', ''),
                        'racimos': parsed_data.get('racimos', ''),
                        'placa': parsed_data.get('placa', ''),
                        'fecha_tiquete': parsed_data.get('fecha_tiquete', '')
                    }
                else:
                    logger.error("No se encontraron datos suficientes para generar el PDF")
                    return None

            # Obtener el QR filename de la sesión
            qr_filename = session.get('qr_filename')
            if not qr_filename:
                # Si no hay QR filename, crear uno predeterminado
                qr_filename = f"default_qr_{now.strftime('%Y%m%d%H%M%S')}.png"
                try:
                    # Generar un QR simple con el código de guía
                    codigo = data.get('codigo', 'unknown')
                    # Usar el código_guia si está disponible, si no generar un ID único
                    codigo_guia_for_qr = codigo_guia if codigo_guia else f"{codigo}_{now.strftime('%Y%m%d%H%M%S')}"
                    # Crear datos para generar el QR
                    qr_data_simple = {
                        'codigo': codigo,
                        'nombre': data.get('nombre_agricultor', ''),
                        'cantidad_racimos': data.get('racimos', ''),
                        'codigo_guia': codigo_guia_for_qr
                    }
                    # Generar el QR con los datos actualizados
                    from app.utils.image_processing import Image_processingUtils
                    image_utils = Image_processingUtils(self.app)
                    image_utils.generate_qr(qr_data_simple, qr_filename)
                    session['qr_filename'] = qr_filename
                    session.modified = True
                except Exception as e:
                    logger.error(f"Error generando QR predeterminado: {str(e)}")
                    # Si todo falla, usar un QR estático
                    qr_filename = "default_qr.png"

            # Preparar datos para el template
            template_data = {
                'image_filename': image_filename,
                'codigo': data.get('codigo', ''),
                'nombre_agricultor': data.get('nombre_agricultor', ''),
                'racimos': data.get('racimos', ''),
                'placa': data.get('placa', ''),
                'acarreo': data.get('acarreo', 'No'),
                'cargo': data.get('cargo', 'No'),
                'transportador': data.get('transportador', 'No registrado'),
                'fecha_tiquete': data.get('fecha_tiquete', ''),
                'hora_registro': hora_procesamiento,
                'fecha_emision': now.strftime("%d/%m/%Y"),
                'hora_emision': now.strftime("%H:%M:%S"),
                'nota': data.get('nota', ''),
                'qr_filename': qr_filename,
                # Agregar indicadores de campos modificados
                'codigo_modificado': session.get('modified_fields', {}).get('codigo', False),
                'nombre_agricultor_modificado': session.get('modified_fields', {}).get('nombre_agricultor', False),
                'cantidad_de_racimos_modificado': session.get('modified_fields', {}).get('racimos', False),
                'placa_modificado': session.get('modified_fields', {}).get('placa', False),
                'acarreo_modificado': session.get('modified_fields', {}).get('acarreo', False),
                'cargo_modificado': session.get('modified_fields', {}).get('cargo', False),
                'transportador_modificado': session.get('modified_fields', {}).get('transportador', False),
                'fecha_modificado': session.get('modified_fields', {}).get('fecha_tiquete', False)
            }

            # Renderizar plantilla
            rendered = render_template(
                'pdf/pdf_template.html',
                **template_data
            )
            
            # Generar nombre del archivo usando el código_guia para mantener consistencia
            # Si hay un código_guia proporcionado, usar ese; si no, generarlo con el código original
            if codigo_guia:
                pdf_filename = f'tiquete_{codigo_guia}.pdf'
            else:
                # Mantener el formato original del código del proveedor (sin normalizar)
                codigo_original = data.get('codigo', 'unknown')
                fecha_hora = now.strftime("%Y%m%d_%H%M%S")
                pdf_filename = f'tiquete_{codigo_original}_{fecha_hora}.pdf'
                
            pdf_path = os.path.join(self.app.config['PDF_FOLDER'], pdf_filename)
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Generar PDF
            try:
                HTML(string=rendered, base_url=self.app.static_folder).write_pdf(pdf_path)
                logger.info(f"PDF generado: {pdf_path}")
                return pdf_filename
            except Exception as e:
                logger.error(f"Error al generar PDF con WeasyPrint: {str(e)}")
                logger.error(traceback.format_exc())
                # Intentar guardar como HTML en lugar de PDF como fallback
                html_filename = pdf_filename.replace('.pdf', '.html')
                html_path = os.path.join(self.app.config['GUIAS_FOLDER'], html_filename)
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(rendered)
                logger.info(f"HTML guardado como alternativa: {html_path}")
                return html_filename
                
        except Exception as e:
            logger.error(f"Error en generate_pdf: {str(e)}")
            logger.error(traceback.format_exc())
            # Devolver None pero no levantar excepción para no romper el flujo
            return None

# Export the utils class for use in the app
pdf_generator_utils = None

def init_pdf_generator_utils(app):
    global pdf_generator_utils
    pdf_generator_utils = Pdf_generatorUtils(app)
    return pdf_generator_utils


