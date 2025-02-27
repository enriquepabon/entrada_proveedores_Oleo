import os
import qrcode
import time
from datetime import datetime
import json
import traceback
import logging
from weasyprint import HTML
from flask import session, render_template, current_app
from bs4 import BeautifulSoup
import re

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
        Genera un PDF a partir de los datos del webhook.
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
                return None

            # Obtener el QR filename de la sesión
            qr_filename = session.get('qr_filename')
            if not qr_filename:
                # Si no hay QR filename, crear uno predeterminado
                qr_filename = f"default_qr_{now.strftime('%Y%m%d%H%M%S')}.png"
                try:
                    # Generar un QR simple con el código de guía
                    codigo = data.get('codigo', 'unknown')
                    default_qr_data = f"codigo:{codigo}_fecha:{now.strftime('%Y%m%d%H%M%S')}"
                    self.generate_qr(default_qr_data, qr_filename)
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
            
            # Limpiar el código de proveedor (eliminar espacios y caracteres especiales)
            codigo_proveedor = re.sub(r'[^a-zA-Z0-9]', '', codigo_proveedor)
            
            # Generar formato estándar: CODIGO_AAAAMMDD_HHMMSS
            now = datetime.now()
            fecha_formateada = now.strftime('%Y%m%d')
            hora_formateada = now.strftime('%H%M%S')
            return f"{codigo_proveedor}_{fecha_formateada}_{hora_formateada}"
        except Exception as e:
            logger.error(f"Error generando código de guía: {str(e)}")
            # Fallback seguro con formato consistente
            return f"{re.sub(r'[^a-zA-Z0-9]', '', str(codigo_proveedor))}_{int(time.time())}"

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
            
            # Obtener el peso bruto directamente de la sesión
            peso_bruto = session.get('peso_bruto', '')
            
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

            # Datos de pesaje directo de la sesión
            datos.update({
                'peso_bruto': peso_bruto,
                'tipo_pesaje': session.get('tipo_pesaje', ''),
                'hora_pesaje': session.get('hora_pesaje', ''),
                'pdf_pesaje': session.get('pdf_pesaje', ''),
                'fecha_pesaje': session.get('fecha_pesaje', '')
            })
            
            # Añadir campos con nombres alternativos para mantener compatibilidad
            datos.update({
                'codigo_proveedor': datos.get('codigo', ''),  # Alias para código
                'nombre_agricultor': datos.get('nombre', ''), # Alias para nombre
                'racimos': datos.get('cantidad_racimos', ''), # Alias para cantidad_racimos
                'imagen_peso': session.get('imagen_peso', '') # Imagen del pesaje
            })
            
            # Asegurar que el estado se actualice correctamente si hay peso
            if peso_bruto:
                datos['estado_actual'] = 'pesaje_completado'
                # También actualizamos la sesión para mantener coherencia
                session['estado_actual'] = 'pesaje_completado'
                session.modified = True
                logger.info(f"Estado actualizado a pesaje_completado debido a peso_bruto={peso_bruto}")

            logger.info(f"Datos obtenidos para guía {codigo}: estado_actual={datos['estado_actual']}, peso_bruto={datos['peso_bruto']}")
            return datos

        except Exception as e:
            logger.error(f"Error obteniendo datos de guía: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def get_datos_registro(self, codigo_guia):
        """
        Obtiene los datos de un registro a partir del código de guía.
        
        Args:
            codigo_guia (str): Código de guía del registro
            
        Returns:
            dict: Diccionario con los datos del registro
        """
        logger.info(f"Intentando recuperar datos para el registro de guía {codigo_guia}")
        
        try:
            # Verificar si el archivo de guía existe
            ruta_guia = os.path.join(current_app.static_folder, 'guias', f'guia_{codigo_guia}.html')
            if not os.path.exists(ruta_guia):
                logger.warning(f"Archivo de guía no encontrado para {codigo_guia}")
                return None
            
            # Normalizar el código de guía para buscar patrones
            codigo_guia_std = codigo_guia.strip().lower()
            
            # Intentar extraer información del código de guía
            # Patrón 1: codigo_AAAAMMDD_HHMMSS (ej. 12345_20230401_120000)
            pattern1 = r'^([^_]+)_(\d{8})_(\d{6})$'
            # Patrón 2: fecha-codigo (ej. 20230401-12345)
            pattern2 = r'^(\d{8})-(.+)$'
            
            # Valores por defecto
            codigo_proveedor = 'No disponible'
            fecha_str = 'No disponible'
            hora_str = 'No disponible'
            
            # Intentar extraer información del código de guía
            match1 = re.match(pattern1, codigo_guia_std)
            
            if match1:
                codigo_proveedor = match1.group(1)
                fecha_str = match1.group(2)
                hora_str = match1.group(3)
                # Formatear fecha de AAAAMMDD a DD/MM/AAAA
                if len(fecha_str) == 8:
                    try:
                        fecha_obj = datetime.strptime(fecha_str, '%Y%m%d')
                        fecha_str = fecha_obj.strftime('%d/%m/%Y')
                    except:
                        pass
                # Formatear hora de HHMMSS a HH:MM:SS
                if len(hora_str) == 6:
                    try:
                        hora_fmt = f"{hora_str[0:2]}:{hora_str[2:4]}:{hora_str[4:6]}"
                        hora_str = hora_fmt
                    except:
                        pass
            else:
                match2 = re.match(pattern2, codigo_guia_std)
                if match2:
                    codigo_proveedor = match2.group(2)
                    fecha_str = match2.group(1)
                    if len(fecha_str) == 8:
                        try:
                            fecha_obj = datetime.strptime(fecha_str, '%Y%m%d')
                            fecha_str = fecha_obj.strftime('%d/%m/%Y')
                        except:
                            pass
            
            # Leer el archivo
            with open(ruta_guia, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Inicializar diccionario para almacenar los datos del registro
            registro = {
                'codigo_guia': codigo_guia,
                'nombre_proveedor': 'No disponible',
                'codigo_proveedor': codigo_proveedor,  # Usar el valor extraído del código de guía
                'cantidad_racimos': 'No disponible',
                'placa': 'No disponible',
                'acarreo': 'No',
                'cargo': 'No',
                'transportador': 'No disponible',
                'fecha_tiquete': 'No disponible',
                'fecha_registro': fecha_str,  # Usar la fecha extraída del código de guía
                'hora_registro': hora_str,    # Usar la hora extraída del código de guía
                'image_filename': None,
                'nota': '',
                'modified_fields': {}
            }
            
            # Intentar cargar como JSON primero
            try:
                json_data = json.loads(content)
                logger.info(f"Datos cargados como JSON para guía {codigo_guia}")
                
                # Asignar valores del JSON al registro
                for key, value in json_data.items():
                    registro[key] = value
                
                # Asegurar que tenemos valores para campos críticos
                if 'codigo' in json_data and not registro.get('codigo_proveedor') or registro.get('codigo_proveedor') == 'No disponible':
                    registro['codigo_proveedor'] = json_data.get('codigo', codigo_proveedor)
                
                if 'nombre' in json_data and not registro.get('nombre_proveedor') or registro.get('nombre_proveedor') == 'No disponible':
                    registro['nombre_proveedor'] = json_data.get('nombre', '')
                
                if 'racimos' in json_data and not registro.get('cantidad_racimos') or registro.get('cantidad_racimos') == 'No disponible':
                    registro['cantidad_racimos'] = json_data.get('racimos', '')
                
                # Si no hay modified_fields en el JSON, crear un diccionario vacío
                if 'modified_fields' not in registro:
                    registro['modified_fields'] = {}
                
                return registro
                
            except json.JSONDecodeError:
                # Si no es JSON, continuar con el parseo de HTML
                logger.info(f"El archivo no es JSON, intentando parsear como HTML para guía {codigo_guia}")
                
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extraer los datos de la tabla
                details_table = soup.find('table', {'class': 'data-table'})
                if details_table:
                    rows = details_table.find_all('tr')
                    for row in rows:
                        header = row.find('th')
                        value_cell = row.find('td')
                        
                        if header and value_cell:
                            titulo = header.text.strip()
                            valor = value_cell.text.strip()
                            
                            if "Nombre del Agricultor" in titulo:
                                registro['nombre_proveedor'] = valor
                            elif "Código" in titulo:
                                registro['codigo_proveedor'] = valor
                            elif "Cantidad de Racimos" in titulo:
                                registro['cantidad_racimos'] = valor
                            elif "Placa" in titulo:
                                registro['placa'] = valor
                            elif "Se Acarreó" in titulo:
                                registro['acarreo'] = valor
                            elif "Se Cargó" in titulo:
                                registro['cargo'] = valor
                            elif "Transportador" in titulo:
                                registro['transportador'] = valor
                            elif "Fecha" in titulo and not "Fecha de Emisión" in titulo and not "Hora de Registro" in titulo:
                                registro['fecha_tiquete'] = valor
                            elif "Hora de Registro" in titulo:
                                registro['hora_registro'] = valor
                
                # Si no se encontró una tabla de detalles, buscar en otras estructuras HTML
                if registro['nombre_proveedor'] == 'No disponible' or registro['codigo_proveedor'] == 'No disponible':
                    # Buscar en elementos con id o class específicos
                    nombre_element = soup.find(id='nombre') or soup.find(class_='nombre')
                    if nombre_element:
                        registro['nombre_proveedor'] = nombre_element.text.strip()
                    
                    codigo_element = soup.find(id='codigo') or soup.find(class_='codigo')
                    if codigo_element:
                        registro['codigo_proveedor'] = codigo_element.text.strip()
                    
                    racimos_element = soup.find(id='racimos') or soup.find(class_='racimos')
                    if racimos_element:
                        registro['cantidad_racimos'] = racimos_element.text.strip()
                
                # Buscar en cualquier texto dentro del documento
                if registro['nombre_proveedor'] == 'No disponible':
                    nombre_pattern = re.compile(r'nombre\s*(?:del\s*agricultor|proveedor)?[:\s]+([^<>\n]+)', re.IGNORECASE)
                    nombre_match = re.search(nombre_pattern, content)
                    if nombre_match:
                        registro['nombre_proveedor'] = nombre_match.group(1).strip()
                
                if registro['codigo_proveedor'] == 'No disponible':
                    codigo_pattern = re.compile(r'código[:\s]+(\d+)', re.IGNORECASE)
                    codigo_match = re.search(codigo_pattern, content)
                    if codigo_match:
                        registro['codigo_proveedor'] = codigo_match.group(1).strip()
                
                if registro['cantidad_racimos'] == 'No disponible':
                    racimos_pattern = re.compile(r'(?:cantidad\s*de\s*)?racimos[:\s]+(\d+)', re.IGNORECASE)
                    racimos_match = re.search(racimos_pattern, content)
                    if racimos_match:
                        registro['cantidad_racimos'] = racimos_match.group(1).strip()
                    
                # Buscar la imagen del tiquete
                img_tag = soup.find('img', {'alt': 'Tiquete'})
                if img_tag and 'src' in img_tag.attrs:
                    src = img_tag['src']
                    # Extraer el nombre de archivo de la URL
                    matches = re.search(r'uploads/([^/]+)', src)
                    if matches:
                        registro['image_filename'] = matches.group(1)
                
                # Buscar la nota
                nota_div = soup.find('div', {'class': 'validation-note'})
                if nota_div:
                    nota_p = nota_div.find('p')
                    if nota_p:
                        registro['nota'] = nota_p.text.strip()
                
                # Buscar indicadores de edición manual
                modified_fields = {}
                
                # Buscar todos los indicadores de edición
                edit_indicators = soup.find_all('span', {'class': 'edit-indicator'})
                for indicator in edit_indicators:
                    parent_row = indicator.find_parent('tr')
                    if parent_row:
                        header = parent_row.find('th')
                        if header:
                            field_title = header.text.strip(':').strip().lower()
                            if "nombre del agricultor" in field_title:
                                modified_fields['nombre_agricultor'] = True
                            elif "código" in field_title:
                                modified_fields['codigo'] = True
                            elif "cantidad de racimos" in field_title:
                                modified_fields['racimos'] = True
                            elif "placa" in field_title:
                                modified_fields['placa'] = True
                            elif "se acarreó" in field_title:
                                modified_fields['acarreo'] = True
                            elif "se cargó" in field_title:
                                modified_fields['cargo'] = True
                            elif "transportador" in field_title:
                                modified_fields['transportador'] = True
                            elif "fecha" in field_title and not "emisión" in field_title and not "registro" in field_title:
                                modified_fields['fecha_tiquete'] = True
                
                # Almacenar los campos modificados en el registro
                registro['modified_fields'] = modified_fields
                
                # Buscar la fecha de emisión (podemos usarla como fecha de registro si no hay otra)
                footer = soup.find('div', {'class': 'footer'})
                if footer:
                    fecha_emisión_p = footer.find('p', string=re.compile(r'Fecha de Emisión:'))
                    if fecha_emisión_p:
                        match = re.search(r'Fecha de Emisión: (\d{2}/\d{2}/\d{4})', fecha_emisión_p.text)
                        if match:
                            registro['fecha_registro'] = match.group(1)
                
                # Intentar extraer la fecha del nombre del archivo si no se encontró en el HTML
                if registro['fecha_registro'] == 'No disponible':
                    # El formato de nombre de archivo suele ser: guia_CODIGO_AAAAMMDD_HHMMSS.html
                    date_match = re.search(r'_(\d{8})_', codigo_guia)
                    if date_match:
                        date_str = date_match.group(1)
                        try:
                            # Convertir de AAAAMMDD a DD/MM/AAAA
                            date_obj = datetime.strptime(date_str, '%Y%m%d')
                            registro['fecha_registro'] = date_obj.strftime('%d/%m/%Y')
                        except:
                            pass
            
            logger.info(f"Datos recuperados para el registro de guía {codigo_guia}")
            return registro
            
        except Exception as e:
            logger.error(f"Error obteniendo datos de registro: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    def generar_qr(self, url, output_path):
        """
        Genera un código QR simple para una URL dada y lo guarda en la ruta especificada
        
        Args:
            url (str): La URL o texto a codificar en el QR
            output_path (str): La ruta donde guardar el archivo QR generado
            
        Returns:
            bool: True si se generó correctamente, False en caso contrario
        """
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

# Para mantener compatibilidad con código existente que no use la clase
utils = None

def init_utils(app):
    global utils
    utils = Utils(app)
    return utils