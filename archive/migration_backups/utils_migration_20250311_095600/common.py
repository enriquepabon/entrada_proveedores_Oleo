import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template

# Configurar logging
logger = logging.getLogger(__name__)

class CommonUtils:
    def __init__(self, app):
        self.app = app
        
    def ensure_directories(self, ...):
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



    def generar_codigo_guia(self, ...):
try:
            # Intentar obtener el código del webhook response
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                codigo_proveedor = webhook_data.get('codigo', codigo_proveedor)
            
            # Guardar el código original
            codigo_original = codigo_proveedor
            
            # Para búsquedas y comparaciones, usar una versión normalizada sin guiones ni símbolos especiales
            codigo_normalizado = re.sub(r'[^a-zA-Z0-9]', '', codigo_proveedor)
            
            # Obtener la fecha actual para crear un código único
            now = datetime.now()
            fecha_actual = now.strftime('%Y%m%d')
            hora_formateada = now.strftime('%H%M%S')
            
            # Generar un código único con milisegundos para garantizar unicidad
            timestamp_ms = int(time.time() * 1000)
            codigo_guia = f"{codigo_original}_{fecha_actual}_{hora_formateada}_{timestamp_ms}"
            
            logger.info(f"Generando nuevo código de guía único: {codigo_guia}")
            
            # Registrar guías existentes para el mismo proveedor (solo para información)
            try:
                import sqlite3
                from db_schema import DB_PATH
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                
                # Buscar guías existentes para este proveedor desde el inicio del día actual
                today_start = f"{fecha_actual[:4]}-{fecha_actual[4:6]}-{fecha_actual[6:8]} 00:00:00"
                cursor.execute(
                    "SELECT codigo_guia FROM entry_records WHERE codigo_proveedor = ? AND created_at >= ?",
                    (codigo_normalizado, today_start)
                )
                db_guides = cursor.fetchall()
                conn.close()
                
                if db_guides:
                    existing_guides = [g[0] for g in db_guides]
                    logger.info(f"Guías previas encontradas para {codigo_proveedor} hoy: {existing_guides} - Generando nueva guía única")
            except Exception as db_error:
                logger.warning(f"Error al verificar guías existentes en BD (solo informativo): {str(db_error)}")
            
            return codigo_guia
            
        except Exception as e:
            logger.error(f"Error generando código de guía: {str(e)}")
            # Fallback seguro con formato consistente y timestamp único
            return f"{re.sub(r'[^a-zA-Z0-9]', '', str(codigo_proveedor))}_{int(time.time()*1000)}"



    def get_datos_guia(self, ...):
try:
            logger.info(f"Buscando datos de guía: {codigo}")
            
            # Primero, intentar obtener los datos desde la base de datos
            with self.app.app_context():
                from db_operations import get_pesaje_bruto_by_codigo_guia
                
                # Verificar si existe en la base de datos
                datos_guia = get_pesaje_bruto_by_codigo_guia(codigo)
                if datos_guia:
                    logger.info(f"Datos de guía encontrados en la base de datos: {codigo}")
                    # Si hay peso_bruto pero no estado_actual, establecer estado_actual
                    if datos_guia.get('peso_bruto') and not datos_guia.get('estado_actual'):
                        datos_guia['estado_actual'] = 'pesaje_completado'
                        logger.info(f"Estado actualizado a pesaje_completado debido a peso_bruto={datos_guia.get('peso_bruto')}")
                    
                    # Verificar y corregir campos clave antes de devolver
                    datos_guia = self._verificar_y_corregir_campos(datos_guia, codigo)
                    return datos_guia
            
            # Si no se encuentra en la base de datos, buscar en archivos JSON
            directorio_guias = self.app.config.get('GUIAS_DIR', 'guias')
            
            # Asegurarse de que el directorio existe
            if not os.path.exists(directorio_guias):
                os.makedirs(directorio_guias, exist_ok=True)
                logger.warning(f"Directorio de guías creado: {directorio_guias}")
            
            # Buscar archivo exacto
            guias_files = glob.glob(os.path.join(directorio_guias, f'guia_{codigo}.json'))
            
            if guias_files:
                logger.info(f"Encontrado archivo de guía: {guias_files[0]}")
                with open(guias_files[0], 'r', encoding='utf-8') as file:
                    datos_guia = json.load(file)
                    datos_guia = self._verificar_y_corregir_campos(datos_guia, codigo)
                    return datos_guia
            
            # Si todavía no se encuentra, buscar en archivos con código parcial
            codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
            guias_files_partial = glob.glob(os.path.join(directorio_guias, f'guia_{codigo_base}_*.json'))
            
            if guias_files_partial:
                # Ordenar por fecha de modificación, más reciente primero
                guias_files_partial.sort(key=os.path.getmtime, reverse=True)
                logger.info(f"Encontrado archivo de guía parcial: {guias_files_partial[0]}")
                with open(guias_files_partial[0], 'r', encoding='utf-8') as file:
                    datos_guia = json.load(file)
                    datos_guia = self._verificar_y_corregir_campos(datos_guia, codigo)
                    return datos_guia
            
            logger.warning(f"No se encontraron datos para la guía: {codigo}")
            return None
            
        except Exception as e:
            logger.error(f"Error al obtener datos de guía {codigo}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    


    def _verificar_y_corregir_campos(self, ...):
if not datos:
            return datos
            
        # Si no existe código, intentar extraerlo del código de guía
        if not datos.get('codigo') and '_' in codigo:
            datos['codigo'] = codigo.split('_')[0]
        
        # Verificar campos importantes y copiar de campos alternativos si es necesario
        key_mappings = {
            'codigo': ['codigo_proveedor', 'Código'],
            'nombre': ['nombre_proveedor', 'nombre_agricultor', 'Nombre del Agricultor'],
            'cantidad_racimos': ['racimos', 'Cantidad de Racimos']
        }
        
        for target_key, source_keys in key_mappings.items():
            if not datos.get(target_key):
                for source_key in source_keys:
                    if datos.get(source_key):
                        datos[target_key] = datos[source_key]
                        break
        
        # Asegurarse de que estos campos siempre tengan un valor
        for field in ['codigo', 'nombre', 'cantidad_racimos']:
            if not datos.get(field):
                datos[field] = 'N/A'
                
        return datos



    def update_datos_guia(self, ...):
try:
            logger.info(f"Actualizando datos de guía: {codigo}")
            
            # Primero, intentar actualizar los datos en la base de datos
            with self.app.app_context():
                from db_operations import get_pesaje_bruto_by_codigo_guia, store_pesaje_neto
                
                # Verificar si existe en la base de datos
                pesaje_existente = get_pesaje_bruto_by_codigo_guia(codigo)
                if pesaje_existente:
                    logger.info(f"Actualizando datos en la base de datos para: {codigo}")
                    # Si tiene información de peso neto, guardarlo
                    if 'peso_neto' in datos_guia and 'peso_tara' in datos_guia:
                        store_pesaje_neto(datos_guia)
                        logger.info(f"Datos de pesaje neto guardados en la base de datos para: {codigo}")
                    return True
            
            # Si no está en la base de datos o no se pudo actualizar, usar JSON
            try:
                directorio_guias = self.app.config.get('GUIAS_DIR', 'guias')
                
                # Asegurarse de que el directorio existe
                if not os.path.exists(directorio_guias):
                    os.makedirs(directorio_guias, exist_ok=True)
                    logger.warning(f"Directorio de guías creado: {directorio_guias}")
                
                archivo_guia = os.path.join(directorio_guias, f'guia_{codigo}.json')
                
                # Verificar si existe el archivo
                if os.path.exists(archivo_guia):
                    # Guardar los datos actualizados
                    with open(archivo_guia, 'w', encoding='utf-8') as file:
                        json.dump(datos_guia, file, ensure_ascii=False, indent=4)
                    logger.info(f"Datos de guía actualizados en archivo: {archivo_guia}")
                    return True
                else:
                    # Si no existe, crear un nuevo archivo
                    with open(archivo_guia, 'w', encoding='utf-8') as file:
                        json.dump(datos_guia, file, ensure_ascii=False, indent=4)
                    logger.info(f"Nuevo archivo de guía creado: {archivo_guia}")
                    return True
            except Exception as e:
                logger.error(f"Error al guardar en archivo JSON: {str(e)}")
                logger.error(traceback.format_exc())
                return False
        
        except Exception as e:
            logger.error(f"Error al actualizar datos de guía {codigo}: {str(e)}")
            logger.error(traceback.format_exc())
            return False



    def get_datos_registro(self, ...):
try:
            logger.info(f"Obteniendo datos para registro de guía {codigo_guia}")
            
            # Inicializar valores por defecto
            fecha_str = 'No disponible'
            hora_str = 'No disponible'
            codigo_proveedor = ''
            
            # Intentar extraer datos del código de guía (formato: CODIGO_AAAAMMDD_HHMMSS)
            if '_' in codigo_guia:
                parts = codigo_guia.split('_')
                if len(parts) >= 1:
                    # Extraer código de proveedor - asegurar que termine con A mayúscula
                    codigo_raw = parts[0]
                    # Usar regex para encontrar dígitos seguidos opcionalmente por letras
                    match = re.match(r'(\d+[a-zA-Z]?)', codigo_raw)
                    if match:
                        codigo_base = match.group(1)
                        # Si termina en letra, asegurar que sea A mayúscula
                        if re.search(r'[a-zA-Z]$', codigo_base):
                            codigo_proveedor = codigo_base[:-1] + 'A'
                        else:
                            codigo_proveedor = codigo_base + 'A'
                    else:
                        codigo_proveedor = codigo_raw

                # Extraer fecha si está disponible
                if len(parts) >= 2 and len(parts[1]) == 8:
                    try:
                        # Convertir AAAAMMDD a DD/MM/AAAA
                        fecha_obj = datetime.strptime(parts[1], '%Y%m%d')
                        fecha_str = fecha_obj.strftime('%d/%m/%Y')
                    except:
                        pass

                # Extraer hora si está disponible
                if len(parts) >= 3 and len(parts[2]) == 6:
                    try:
                        # Convertir HHMMSS a HH:MM:SS
                        hora_obj = datetime.strptime(parts[2], '%H%M%S')
                        hora_str = hora_obj.strftime('%H:%M:%S')
                    except:
                        pass
            # Intentar extraer datos para el formato alternativo (ejemplo: 20250227105313-8867)
            elif '-' in codigo_guia:
                parts = codigo_guia.split('-')
                if len(parts) >= 2:
                    # El segundo elemento suele contener el código de proveedor
                    codigo_raw = parts[1]
                    # Usar regex para encontrar dígitos seguidos opcionalmente por letras
                    match = re.match(r'(\d+[a-zA-Z]?)', codigo_raw)
                    if match:
                        codigo_base = match.group(1)
                        # Si termina en letra, asegurar que sea A mayúscula
                        if re.search(r'[a-zA-Z]$', codigo_base):
                            codigo_proveedor = codigo_base[:-1] + 'A'
                        else:
                            codigo_proveedor = codigo_base + 'A'
                    else:
                        codigo_proveedor = codigo_raw
                    
                    # Si el primer elemento tiene 14 caracteres, podría contener fecha y hora
                    if len(parts[0]) == 14:
                        try:
                            timestamp = parts[0]
                            # Extraer fecha (AAAAMMDD)
                            fecha_part = timestamp[:8]
                            fecha_obj = datetime.strptime(fecha_part, '%Y%m%d')
                            fecha_str = fecha_obj.strftime('%d/%m/%Y')
                            
                            # Extraer hora (HHMMSS)
                            hora_part = timestamp[8:14]
                            hora_obj = datetime.strptime(hora_part, '%H%M%S')
                            hora_str = hora_obj.strftime('%H:%M:%S')
                        except:
                            pass
            
            # Preparar la ruta al archivo HTML o JSON de la guía
            html_file = os.path.join(self.app.static_folder, 'guias', f'guia_{codigo_guia}.html')
            
            # Verificar si el archivo existe
            if not os.path.exists(html_file):
                logger.warning(f"Archivo de guía no encontrado: {html_file}")
                # Crear un registro básico con la información disponible del código
                registro = {
                    'codigo_guia': codigo_guia,
                    'codigo_proveedor': codigo_proveedor,
                    'nombre_proveedor': '',
                    'fecha_registro': fecha_str,
                    'hora_registro': hora_str,
                    'placa': '',
                    'cantidad_racimos': '',
                    'transportador': '',
                    'acarreo': '',
                    'cargo': '',
                    'modified_fields': [],
                    'image_filename': ''
                }
                return registro
            
            # Leer el contenido del archivo
            with open(html_file, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Inicializar el diccionario del registro
            registro = {
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'nombre_proveedor': '',
                'fecha_registro': fecha_str,
                'hora_registro': hora_str,
                'placa': '',
                'cantidad_racimos': '',
                'transportador': '',
                'acarreo': '',
                'cargo': '',
                'modified_fields': [],
                'image_filename': ''
            }
            
            # Intentar cargar como JSON primero
            try:
                data = json.loads(content)
                logger.info(f"Datos JSON cargados correctamente desde {html_file}")
                
                # Asignar valores del JSON al registro
                registro['codigo_proveedor'] = data.get('codigo_proveedor', codigo_proveedor)
                # Normalizar código de proveedor para que termine en A mayúscula
                if registro['codigo_proveedor'] and registro['codigo_proveedor'].endswith('a'):
                    registro['codigo_proveedor'] = registro['codigo_proveedor'][:-1] + 'A'
                
                registro['nombre_proveedor'] = data.get('nombre_proveedor', '')
                registro['fecha_registro'] = data.get('fecha_registro', fecha_str)
                registro['hora_registro'] = data.get('hora_registro', hora_str)
                registro['placa'] = data.get('placa', '')
                registro['cantidad_racimos'] = data.get('cantidad_racimos', '')
                registro['transportador'] = data.get('transportador', '')
                registro['acarreo'] = data.get('acarreo', '')
                registro['cargo'] = data.get('cargo', '')
                registro['image_filename'] = data.get('image_filename', '')
                registro['modified_fields'] = data.get('modified_fields', [])
                
            except json.JSONDecodeError:
                logger.info(f"El archivo {html_file} no es JSON. Procesando como HTML.")
                
                # Analizar el HTML usando BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                
                # Buscar las tablas en el HTML
                tables = soup.find_all('table')
                
                # Intentar extraer datos de tablas
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        if len(cells) >= 2:
                            # Extraer el nombre del campo y su valor
                            field_name = cells[0].get_text().strip().lower()
                            field_value = cells[1].get_text().strip()
                            
                            # Asignar valores según el nombre del campo
                            if 'código proveedor' in field_name or 'codigo proveedor' in field_name:
                                # Asegurarse de que el código de proveedor termine con A mayúscula
                                if field_value and field_value.endswith('a'):
                                    registro['codigo_proveedor'] = field_value[:-1] + 'A'
                                else:
                                    registro['codigo_proveedor'] = field_value
                            elif 'nombre proveedor' in field_name or 'nombre del proveedor' in field_name:
                                registro['nombre_proveedor'] = field_value
                            elif 'placa' in field_name:
                                registro['placa'] = field_value
                            elif 'racimos' in field_name or 'cantidad' in field_name:
                                registro['cantidad_racimos'] = field_value
                            elif 'transportador' in field_name:
                                registro['transportador'] = field_value
                            elif 'acarreo' in field_name:
                                registro['acarreo'] = field_value
                            elif 'cargo' in field_name:
                                registro['cargo'] = field_value
                
                # Si no se encontró información en tablas, buscar mediante patrones en el texto
                if not registro['codigo_proveedor'] or not registro['nombre_proveedor']:
                    # Buscar códigos y nombres de proveedores
                    code_pattern = r'Código(?:\s+de)?(?:\s+Proveedor)?:\s*(\d+[A-Za-z]?)'
                    name_pattern = r'Nombre(?:\s+del)?(?:\s+Proveedor)?:\s*([^\n<>]+)'
                    
                    code_match = re.search(code_pattern, content, re.IGNORECASE)
                    name_match = re.search(name_pattern, content, re.IGNORECASE)
                    
                    if code_match:
                        code_value = code_match.group(1).strip()
                        # Asegurarse de que termine con A mayúscula
                        if code_value.endswith('a'):
                            registro['codigo_proveedor'] = code_value[:-1] + 'A'
                        elif not code_value.endswith('A'):
                            registro['codigo_proveedor'] = code_value + 'A'
                        else:
                            registro['codigo_proveedor'] = code_value
                    
                    if name_match:
                        name_value = name_match.group(1).strip()
                        if name_value and name_value != "del Agricultor":
                            registro['nombre_proveedor'] = name_value
                
                # Buscar placa y cantidad de racimos si no se encontraron en tablas
                if not registro['placa']:
                    placa_pattern = r'Placa:\s*([A-Z0-9-]+)'
                    placa_match = re.search(placa_pattern, content, re.IGNORECASE)
                    if placa_match:
                        registro['placa'] = placa_match.group(1).strip()
                
                if not registro['cantidad_racimos']:
                    racimos_pattern = r'Racimos:\s*(\d+)'
                    racimos_match = re.search(racimos_pattern, content, re.IGNORECASE)
                    if racimos_match:
                        registro['cantidad_racimos'] = racimos_match.group(1).strip()
                
                # Buscar imágenes en el HTML
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    if src and not src.startswith('data:'):
                        # Extraer el nombre del archivo de la imagen
                        registro['image_filename'] = os.path.basename(src)
                        break
                
                # Comprobar si hay campos modificados
                modified_fields = []
                modified_divs = soup.find_all('div', {'class': 'modified'})
                for div in modified_divs:
                    field_name = div.get('data-field', '')
                    if field_name:
                        modified_fields.append(field_name)
                
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
                if not registro['fecha_registro'] or registro['fecha_registro'] == 'No disponible':
                    # Intentar varios formatos de código de guía
                    if '_' in codigo_guia:
                        # Formato: CODIGO_AAAAMMDD_HHMMSS
                        date_match = re.search(r'_(\d{8})_', codigo_guia)
                        if date_match:
                            date_str = date_match.group(1)
                            try:
                                # Convertir de AAAAMMDD a DD/MM/AAAA
                                date_obj = datetime.strptime(date_str, '%Y%m%d')
                                registro['fecha_registro'] = date_obj.strftime('%d/%m/%Y')
                            except:
                                pass
                    elif '-' in codigo_guia:
                        # Formato: AAAAMMDDHHMMSS-CODIGO
                        timestamp_part = codigo_guia.split('-')[0]
                        if len(timestamp_part) >= 8:
                            date_str = timestamp_part[:8]
                            try:
                                # Convertir de AAAAMMDD a DD/MM/AAAA
                                date_obj = datetime.strptime(date_str, '%Y%m%d')
                                registro['fecha_registro'] = date_obj.strftime('%d/%m/%Y')
                            except:
                                pass
            
            # Normalización final de los datos
            
            # Búsqueda adicional de nombre si está vacío o es "del Agricultor"
            if not registro['nombre_proveedor'] or registro['nombre_proveedor'] == "del Agricultor":
                # Intentar buscar un nombre asociado con el código en alguna base de datos o 
                # tabla de proveedores comunes si está disponible
                
                # También podemos buscar en el código HTML completo
                if registro['codigo_proveedor']:
                    # Buscar patrones como "CÓDIGO - NOMBRE" o tablas donde aparecen ambos
                    name_search = re.search(rf'{registro["codigo_proveedor"]}.*?[<>\-:,\s]+([^<>\n]{3,50}?)[\s<]', content, re.IGNORECASE)
                    if name_search:
                        potential_name = name_search.group(1).strip()
                        if potential_name and len(potential_name) > 3 and potential_name != "del Agricultor":
                            registro['nombre_proveedor'] = potential_name
                    
                    # Buscar con patrón alternativo para casos especiales
                    if not registro['nombre_proveedor'] or registro['nombre_proveedor'] == "del Agricultor":
                        alternate_search = re.search(r'(?:proveedor|agricultor)[:<>\s]+(?:\w+\s*)+', content, re.IGNORECASE)
                        if alternate_search:
                            potential_name = alternate_search.group(0).split(':')[-1].strip()
                            if potential_name and len(potential_name) > 3 and potential_name != "del Agricultor":
                                registro['nombre_proveedor'] = potential_name
            
            # Convertir valores vacíos a "No disponible" solo en la presentación final
            for key in registro:
                if key not in ['modified_fields', 'image_filename'] and (registro[key] is None or registro[key] == ''):
                    registro[key] = 'No disponible'
            
            logger.info(f"Datos recuperados para el registro de guía {codigo_guia}")
            return registro
            
        except Exception as e:
            logger.error(f"Error obteniendo datos de registro: {str(e)}")
            logger.error(traceback.format_exc())
            return None



    def generate_unique_id(self, ...):
try:
            # Generar timestamp con milisegundos
            timestamp = datetime.now().strftime('%Y%m%d%H%M%S%f')
            return timestamp[:17]  # Truncar a 17 caracteres para mayor legibilidad
        except Exception as e:
            logger.error(f"Error generando ID único: {str(e)}")
            # Fallback seguro usando time.time()
            return str(int(time.time() * 1000))

# Para mantener compatibilidad con código existente que no use la clase
utils = None

def init_utils(app):
    global utils
    utils = Utils(app)
    return utils

