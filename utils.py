import os
import qrcode
import time
from datetime import datetime
import json
import traceback
import logging
from weasyprint import HTML
from flask import session, render_template, current_app

logger = logging.getLogger(__name__)

class Utils:
    def __init__(self, app):
        self.app = app
        self.ensure_directories()

    def ensure_directories(self, additional_directories=None):
        """
        Crea los directorios necesarios si no existen
        """
        try:
            # Directorios base
            directories = [
                os.path.join(self.app.static_folder, 'uploads'),
                os.path.join(self.app.static_folder, 'pdfs'),
                os.path.join(self.app.static_folder, 'guias'),
                os.path.join(self.app.static_folder, 'qr'),
                os.path.join(self.app.static_folder, 'images'),
                os.path.join(self.app.static_folder, 'excels')
            ]
            
            # Agregar directorios adicionales si existen
            if additional_directories:
                directories.extend(additional_directories)
                
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Directorio asegurado: {directory}")
                
        except Exception as e:
            logger.error(f"Error creando directorios: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def generate_qr(self, qr_data, filename):
        """
        Genera un archivo QR que contiene la URL de la guía de proceso
        """
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

    def generate_pdf(self, parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None, codigo_guia=None):
        """
        Genera un PDF a partir de los datos del tiquete.
        """
        try:
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

            # Obtener el QR filename de la sesión
            qr_filename = session.get('qr_filename')
            if qr_filename:
                # Verificar si el archivo existe
                qr_path = os.path.join(self.app.static_folder, 'qr', qr_filename)
                if not os.path.exists(qr_path):
                    logger.warning(f"Archivo QR no encontrado en: {qr_path}")
                    qr_filename = None

            # Log para debugging
            logger.info(f"Datos validados para PDF: {data}")
            logger.info(f"Datos de revalidación: {revalidation_data}")
            logger.info(f"Datos originales del tiquete: {parsed_data}")

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
                'qr_filename': qr_filename
            }

            # Renderizar plantilla
            rendered = render_template(
                'pdf_template.html',
                **template_data
            )
            
            # Generar nombre del archivo
            pdf_filename = f'tiquete_{data["codigo"]}_{now.strftime("%Y%m%d_%H%M%S")}.pdf'
            pdf_path = os.path.join(self.app.config['PDF_FOLDER'], pdf_filename)

            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Generar PDF
            HTML(
                string=rendered,
                base_url=self.app.static_folder
            ).write_pdf(pdf_path)
            
            logger.info(f"PDF generado exitosamente: {pdf_filename}")
            return pdf_filename
            
        except Exception as e:
            logger.error(f"Error en generate_pdf: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def format_date(self, parsed_data):
        """
        Formatea la fecha del tiquete en un formato consistente
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            return datetime.strptime(fecha_str, fmt).strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")

    def get_codigo_from_data(self, parsed_data):
        """
        Obtiene el código del tiquete de los datos parseados
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Código':
                return row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
        return 'desconocido'

    def generar_codigo_guia(self, codigo_proveedor):
        """
        Genera un código único para la guía usando el código validado del webhook
        """
        try:
            # Intentar obtener el código del webhook response
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                codigo_proveedor = webhook_data.get('codigo', codigo_proveedor)
            
            now = datetime.now()
            fecha_formateada = now.strftime('%Y%m%d')
            hora_formateada = now.strftime('%H%M%S')
            return f"{codigo_proveedor}_{fecha_formateada}_{hora_formateada}"
        except Exception as e:
            logger.error(f"Error generando código de guía: {str(e)}")
            return f"{codigo_proveedor}_{int(time.time())}"

    def registrar_fecha_porteria(self):
        """
        Registra la fecha actual de entrada en portería
        """
        return datetime.now().strftime('%d/%m/%Y %H:%M')

    def get_ticket_date(self, parsed_data):
        """
        Obtiene la fecha del tiquete de los datos parseados
        """
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            fecha_obj = datetime.strptime(fecha_str, fmt)
                            return fecha_obj.strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")

    def prepare_revalidation_data(self, parsed_data, data):
        """
        Prepara los datos de revalidación
        """
        revalidation_data = {}
        for row in parsed_data.get('table_data', []):
            campo = row['campo']
            valor = row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
            revalidation_data[campo] = valor

        if data:
            if data.get('Nombre'):
                revalidation_data['Nombre del Agricultor'] = data['Nombre']
            if data.get('Codigo'):
                revalidation_data['Código'] = data['Codigo']
            if data.get('Nota'):
                revalidation_data['nota'] = data['Nota']

        return revalidation_data

    def get_datos_guia(self, codigo):
        """
        Obtiene los datos necesarios para generar la guía de proceso
        """
        try:
            data = {}
            
            # Obtener datos del webhook response
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                data = {
                    'codigo': webhook_data.get('codigo', codigo),
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

            # Preparar datos finales
            datos = {
                'codigo': data.get('codigo', codigo),
                'nombre': data.get('nombre', ''),
                'fecha_registro': session.get('fecha_registro', ''),
                'hora_registro': session.get('hora_registro', ''),
                'fecha_tiquete': data.get('fecha_tiquete', ''),
                'placa': data.get('placa', ''),
                'transportador': data.get('transportador', ''),
                'cantidad_racimos': data.get('racimos', ''),
                'acarreo': data.get('acarreo', ''),
                'cargo': data.get('cargo', ''),
                'estado_actual': session.get('estado_actual', ''),
                'image_filename': session.get('image_filename', ''),
                'pdf_filename': session.get('pdf_filename', ''),
                'codigo_guia': session.get('codigo_guia', ''),
                'nota': data.get('nota', '')
            }

            # Obtener datos de pesaje
            datos.update({
                'peso_bruto': session.get('peso_bruto', ''),
                'tipo_pesaje': session.get('tipo_pesaje', ''),
                'hora_pesaje': session.get('hora_pesaje', ''),
                'pdf_pesaje': session.get('pdf_pesaje', ''),
                'fecha_pesaje': session.get('fecha_pesaje', '')
            })

            logger.info(f"Datos obtenidos para guía {codigo}: {datos}")
            return datos

        except Exception as e:
            logger.error(f"Error obteniendo datos de guía: {str(e)}")
            raise

# Para mantener compatibilidad con código existente que no use la clase
utils = None

def init_utils(app):
    global utils
    utils = Utils(app)
    return utils