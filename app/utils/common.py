import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template, session
import time
import re
import glob
from urllib.parse import urlparse
import sqlite3
import qrcode
from io import BytesIO
import base64
import pytz

# Configurar logging
logger = logging.getLogger(__name__)

# Define timezones
UTC = pytz.utc
BOGOTA_TZ = pytz.timezone('America/Bogota')

def format_datetime_bogota(date_str, time_str):
    """
    Combines date and time strings, assumes UTC, converts to Bogota TZ, and formats.
    
    Args:
        date_str (str): Date string in DD/MM/YYYY format
        time_str (str): Time string in HH:MM:SS format
        
    Returns:
        tuple: (formatted_date, formatted_time) in Bogota timezone
    """
    if not date_str or not time_str:
        return None, None # Return None for both if either is missing
    
    try:
        # Parse the input strings into a datetime object
        dt_str = f"{date_str} {time_str}"
        naive_dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
        
        # Make it UTC aware
        utc_dt = UTC.localize(naive_dt)
        
        # Convert to Bogota timezone
        bogota_dt = utc_dt.astimezone(BOGOTA_TZ)
        
        # Format back to strings
        formatted_date = bogota_dt.strftime('%d/%m/%Y')
        formatted_time = bogota_dt.strftime('%H:%M:%S')
        
        logger.debug(f"Timezone conversion: UTC {utc_dt} -> Bogota {bogota_dt}")
        logger.debug(f"Formatted result: date={formatted_date}, time={formatted_time}")
        
        return formatted_date, formatted_time
    except (ValueError, TypeError) as e:
        logger.error(f"Error formatting datetime ({date_str} {time_str}): {e}")
        return date_str, time_str # Return original strings on error

class CommonUtils:
    def __init__(self, app):
        self.app = app
        
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
    
    def generar_codigo_guia(self, codigo_proveedor):
        """
        Genera un código de guía único basado en el código del proveedor
        """
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
            
            # Generar un código más simple y legible
            # Usar solo los últimos 4 caracteres del timestamp para tener un código más corto pero único
            timestamp_short = str(int(time.time()))[-4:]
            codigo_guia = f"{codigo_original}_{fecha_actual}_{timestamp_short}"
            
            logger.info(f"Generando nuevo código de guía único: {codigo_guia}")
            
            # Registrar guías existentes para el mismo proveedor (solo para información)
            try:
                conn = sqlite3.connect('tiquetes.db')
                conn.row_factory = sqlite3.Row
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
            # Fallback seguro con formato consistente y timestamp único pero corto
            return f"{re.sub(r'[^a-zA-Z0-9]', '', str(codigo_proveedor))}_{int(time.time())%10000}"
    
    def get_datos_guia(self, codigo_guia, force_reload=False):
        """
        Obtiene todos los datos relacionados con una guía específica usando LEFT JOINs.
        """
        conn = None # Initialize conn
        try:
            # Use the configured DB path
            db_path = current_app.config['TIQUETES_DB_PATH']
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Single query using LEFT JOINs
            query = """
                SELECT 
                    e.*, 
                    pb.peso_bruto, pb.timestamp_pesaje_utc, pb.tipo_pesaje, pb.codigo_guia_transporte_sap, 
                    c.fecha_clasificacion, c.hora_clasificacion, c.clasificacion_manual, c.clasificacion_automatica,
                    pn.peso_tara, pn.peso_neto, pn.peso_producto, 
                    pn.fecha_pesaje as fecha_pesaje_neto_db, pn.hora_pesaje as hora_pesaje_neto_db,
                    pn.tipo_pesaje_neto, pn.comentarios as comentarios_neto, pn.respuesta_sap,
                    s.fecha_salida, s.hora_salida, s.comentarios_salida
                FROM entry_records e
                LEFT JOIN pesajes_bruto pb ON e.codigo_guia = pb.codigo_guia
                LEFT JOIN clasificaciones c ON e.codigo_guia = c.codigo_guia
                LEFT JOIN pesajes_neto pn ON e.codigo_guia = pn.codigo_guia
                LEFT JOIN salidas s ON e.codigo_guia = s.codigo_guia
                WHERE e.codigo_guia = ?
            """
            
            cursor.execute(query, (codigo_guia,))
            row = cursor.fetchone()

            if not row:
                logger.warning(f"No entry_record found for codigo_guia: {codigo_guia}")
                return None

            # Log raw timestamp values retrieved from DB
            logger.debug(f"Raw data for {codigo_guia} from DB - fecha_clasificacion: {row['fecha_clasificacion']}, hora_clasificacion: {row['hora_clasificacion']}")
            logger.debug(f"Raw data for {codigo_guia} from DB - fecha_pesaje_neto_db: {row['fecha_pesaje_neto_db']}, hora_pesaje_neto_db: {row['hora_pesaje_neto_db']}")
            
            # Convert the row to a dictionary
            datos_guia = dict(row)
            logger.info(f"Datos combinados obtenidos para guía {codigo_guia}")

            # --- Timezone Conversion --- 
            # Process entry record timestamp
            # TODO (Plan Timestamps): Mover la conversión de zona horaria a la capa de vista/plantilla.
            # Esta conversión está aquí temporalmente por compatibilidad con plantillas existentes.
            # Ref: REFACTORING_PLAN.md
            ts_registro_utc_str = datos_guia.get('timestamp_registro_utc')
            fecha_registro_bogota = None
            hora_registro_bogota = None
            if ts_registro_utc_str:
                try:
                    # Parse the UTC timestamp string
                    dt_utc = datetime.strptime(ts_registro_utc_str, "%Y-%m-%d %H:%M:%S")
                    # Make it timezone aware (UTC)
                    dt_utc = UTC.localize(dt_utc)
                    # Convert to Bogota timezone
                    dt_bogota = dt_utc.astimezone(BOGOTA_TZ)
                    # Format into separate date and time strings
                    fecha_registro_bogota = dt_bogota.strftime('%d/%m/%Y')
                    hora_registro_bogota = dt_bogota.strftime('%H:%M:%S')
                except ValueError as e:
                    logger.warning(f"Could not parse timestamp_registro_utc '{ts_registro_utc_str}' for {codigo_guia}: {e}")
            # Assign converted values (or None if parsing failed) back for compatibility
            datos_guia['fecha_registro'] = fecha_registro_bogota
            datos_guia['hora_registro'] = hora_registro_bogota
            
            # Process pesaje_bruto timestamp
            # TODO (Plan Timestamps): Mover la conversión de zona horaria a la capa de vista/plantilla.
            # Esta conversión está aquí temporalmente por compatibilidad con plantillas existentes.
            # Ref: REFACTORING_PLAN.md
            ts_pesaje_utc_str = datos_guia.get('timestamp_pesaje_utc')
            fecha_pesaje_bogota = None
            hora_pesaje_bogota = None
            if ts_pesaje_utc_str:
                try:
                    # Parse the UTC timestamp string
                    dt_utc = datetime.strptime(ts_pesaje_utc_str, "%Y-%m-%d %H:%M:%S")
                    # Make it timezone aware (UTC)
                    dt_utc = UTC.localize(dt_utc)
                    # Convert to Bogota timezone
                    dt_bogota = dt_utc.astimezone(BOGOTA_TZ)
                    # Format into separate date and time strings
                    fecha_pesaje_bogota = dt_bogota.strftime('%d/%m/%Y')
                    hora_pesaje_bogota = dt_bogota.strftime('%H:%M:%S')
                except ValueError as e:
                    logger.warning(f"Could not parse timestamp_pesaje_utc '{ts_pesaje_utc_str}' for {codigo_guia}: {e}")
            # Assign converted values (or None if parsing failed) back for compatibility
            datos_guia['fecha_pesaje'] = fecha_pesaje_bogota
            datos_guia['hora_pesaje'] = hora_pesaje_bogota
            
            # TODO (Plan Timestamps): Revisar y mover la conversión de zona horaria para clasificacion, pesaje_neto, salida.
            datos_guia['fecha_clasificacion'], datos_guia['hora_clasificacion'] = format_datetime_bogota(
                datos_guia.get('fecha_clasificacion'), datos_guia.get('hora_clasificacion')
            )
            datos_guia['fecha_pesaje_neto'], datos_guia['hora_pesaje_neto'] = format_datetime_bogota(
                datos_guia.get('fecha_pesaje_neto_db'), datos_guia.get('hora_pesaje_neto_db')
            )
            datos_guia['fecha_salida'], datos_guia['hora_salida'] = format_datetime_bogota(
                datos_guia.get('fecha_salida'), datos_guia.get('hora_salida')
            )
            # --- End Timezone Conversion ---

            # --- Data Cleaning and Structuring ---
            
            # Ensure provider fields are present and consistent
            datos_guia['codigo_proveedor'] = datos_guia.get('codigo_proveedor') or datos_guia.get('codigo') or (codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia)
            datos_guia['nombre_proveedor'] = datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor') or datos_guia.get('nombre') or 'No disponible'
            datos_guia['racimos'] = datos_guia.get('cantidad_racimos') or datos_guia.get('racimos') # Prioritize cantidad_racimos
            if not datos_guia.get('racimos'): # If still None or empty, set default
                datos_guia['racimos'] = 'No registrado' # Set default if missing

            # Handle potentially missing values from JOINs with defaults
            datos_guia['peso_bruto'] = datos_guia.get('peso_bruto')
            datos_guia['tipo_pesaje'] = datos_guia.get('tipo_pesaje')
            datos_guia['codigo_guia_transporte_sap'] = datos_guia.get('codigo_guia_transporte_sap') or datos_guia.get('guia_sap')

            datos_guia['peso_tara'] = datos_guia.get('peso_tara')
            datos_guia['peso_neto'] = datos_guia.get('peso_neto')
            datos_guia['peso_producto'] = datos_guia.get('peso_producto')
            datos_guia['fecha_pesaje_neto'] = datos_guia.get('fecha_pesaje_neto_db') # Use corrected alias
            datos_guia['hora_pesaje_neto'] = datos_guia.get('hora_pesaje_neto_db') # Use corrected alias
            datos_guia['tipo_pesaje_neto'] = datos_guia.get('tipo_pesaje_neto')
            datos_guia['comentarios_neto'] = datos_guia.get('comentarios_neto')
            datos_guia['respuesta_sap'] = datos_guia.get('respuesta_sap')

            datos_guia['fecha_salida'] = datos_guia.get('fecha_salida')
            datos_guia['hora_salida'] = datos_guia.get('hora_salida')
            # datos_guia['nota_salida'] = datos_guia.get('nota_salida') # Comment out attempt to access potentially non-existent key
            datos_guia['comentarios_salida'] = datos_guia.get('comentarios_salida')

            # Process classification data (manual)
            manual_data_str = datos_guia.get('clasificacion_manual')
            manual_data = None
            if manual_data_str:
                try:
                    manual_data = json.loads(manual_data_str)
                except json.JSONDecodeError:
                    manual_data = {}
            datos_guia['clasificacion_manual'] = {
                'verde': manual_data.get('verdes') if manual_data else None,
                'sobremaduro': manual_data.get('sobremaduros') if manual_data else None,
                'danio_corona': manual_data.get('danio_corona') if manual_data else None,
                'pendunculo_largo': manual_data.get('pendunculo_largo') if manual_data else None,
                'podrido': manual_data.get('podridos') if manual_data else None
            }

            # Process classification data (automatic)
            auto_data_str = datos_guia.get('clasificacion_automatica')
            auto_data = None
            if auto_data_str:
                try:
                    auto_data = json.loads(auto_data_str)
                except json.JSONDecodeError:
                    auto_data = {}
            datos_guia['clasificacion_automatica'] = {
                'verde': auto_data.get('verdes', {}).get('porcentaje') if auto_data else None,
                'sobremaduro': auto_data.get('sobremaduros', {}).get('porcentaje') if auto_data else None,
                'danio_corona': auto_data.get('danio_corona', {}).get('porcentaje') if auto_data else None,
                'pendunculo_largo': auto_data.get('pendunculo_largo', {}).get('porcentaje') if auto_data else None,
                'podrido': auto_data.get('podridos', {}).get('porcentaje') if auto_data else None
            }
            # Add classification date/time if available
            datos_guia['fecha_clasificacion'] = datos_guia.get('fecha_clasificacion')
            datos_guia['hora_clasificacion'] = datos_guia.get('hora_clasificacion')
            
            # Final check for essential fields, setting defaults if needed
            essential_fields = ['placa', 'transportador', 'acarreo', 'cargo']
            for field in essential_fields:
                if not datos_guia.get(field):
                    datos_guia[field] = 'No disponible'
            
            # Log the final combined data for debugging
            # Be careful logging potentially sensitive data in production
            # logger.debug(f"Final combined datos_guia for {codigo_guia}: {datos_guia}")

            return datos_guia

        except KeyError as ke:
            logger.error(f"Configuration error in get_datos_guia: {ke}. Ensure TIQUETES_DB_PATH is set.")
            return None
        except sqlite3.Error as e:
            logger.error(f"Database error getting data for guide {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting data for guide {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
        finally:
            if conn:
                conn.close()
    
    def _verificar_y_corregir_campos(self, datos, codigo):
        """
        Verifica y corrige campos faltantes o inconsistentes en los datos de guía
        """
        if not datos:
            return datos
            
        # Si no existe código, intentar extraerlo del código de guía
        if not datos.get('codigo') and '_' in codigo:
            datos['codigo'] = codigo.split('_')[0]
        
        # Verificar campos importantes y copiar de campos alternativos si es necesario
        key_mappings = {
            'codigo': ['codigo_proveedor', 'Código'],
            'codigo_proveedor': ['codigo', 'Código'],
            'nombre': ['nombre_proveedor', 'nombre_agricultor', 'Nombre del Agricultor'],
            'nombre_proveedor': ['nombre', 'nombre_agricultor', 'Nombre del Agricultor'], 
            'nombre_agricultor': ['nombre', 'nombre_proveedor', 'Nombre del Agricultor'],
            'cantidad_racimos': ['racimos', 'Cantidad de Racimos', 'cantidad_de_racimos'],
            'racimos': ['cantidad_racimos', 'Cantidad de Racimos', 'cantidad_de_racimos'],
            'transportador': ['transportista', 'conductor'],
            'transportista': ['transportador', 'conductor'],
            'placa': ['placa_vehiculo', 'num_placa'],
            'acarreo': ['se_acarreo', 'acarreo_realizado'],
            'cargo': ['se_cargo', 'cargo_realizado'],
            'codigo_transportista': ['codigo_transportador', 'id_transportista']
        }
        
        # Valor que indica un campo vacío o no disponible
        valores_vacios = ['N/A', 'No disponible', 'None', None, '', 'nan', 'NaN']
        
        for target_key, source_keys in key_mappings.items():
            # Verificar si el campo objetivo está vacío o tiene un valor por defecto
            if target_key not in datos or datos.get(target_key) in valores_vacios:
                for source_key in source_keys:
                    if source_key in datos and datos.get(source_key) not in valores_vacios:
                        datos[target_key] = datos[source_key]
                        logger.info(f"Campo {target_key} actualizado desde {source_key}: {datos[target_key]}")
                        break
            # Si el campo existe pero tiene un valor por defecto, intentar actualizarlo
            elif datos.get(target_key) in valores_vacios:
                for source_key in source_keys:
                    if source_key in datos and datos.get(source_key) not in valores_vacios:
                        datos[target_key] = datos[source_key]
                        logger.info(f"Campo {target_key} actualizado desde {source_key}: {datos[target_key]}")
                        break
        
        # Asegurarse de que estos campos siempre tengan un valor
        campos_requeridos = [
            'codigo', 'codigo_proveedor', 'nombre', 'nombre_proveedor', 
            'cantidad_racimos', 'racimos', 'transportador', 'transportista', 
            'placa', 'acarreo', 'cargo', 'codigo_transportista'
        ]
        
        # Asegurarse explícitamente que cantidad_racimos y racimos son consistentes
        if 'cantidad_racimos' in datos and datos['cantidad_racimos'] not in valores_vacios:
            datos['racimos'] = datos['cantidad_racimos']
        elif 'racimos' in datos and datos['racimos'] not in valores_vacios:
            datos['cantidad_racimos'] = datos['racimos']
            
        # Intentar extraer código_transportista a partir de otros campos si está vacío
        if datos.get('codigo_transportista') in valores_vacios and datos.get('transportista') not in valores_vacios:
            # Si hay un transportista pero no hay código, asignar un valor predeterminado basado en el nombre
            nombre_transportista = datos.get('transportista')
            if nombre_transportista and isinstance(nombre_transportista, str):
                # Extraer iniciales o primeras letras como un código básico
                iniciales = ''.join([word[0].upper() for word in nombre_transportista.split() if word])
                if iniciales:
                    datos['codigo_transportista'] = f"T-{iniciales}"
                    logger.info(f"Código transportista generado: {datos['codigo_transportista']}")
        
        for field in campos_requeridos:
            if field not in datos or datos.get(field) in valores_vacios:
                datos[field] = 'N/A'
                
        return datos
    
    def update_datos_guia(self, codigo, datos_guia):
        """
        Actualiza los datos de una guía existente
        """
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
    
    def get_datos_registro(self, codigo_guia):
        """
        Obtiene los datos de un registro de entrada a partir del código de guía
        """
        try:
            logger.info(f"Obteniendo datos para registro de guía {codigo_guia}")
            
            # Inicializar valores por defecto
            fecha_str = 'No disponible'
            hora_str = 'No disponible'
            
            # Intentar obtener los datos de la base de datos primero
            try:
                import db_utils
                registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
                if registro:
                    logger.info(f"Registro encontrado en la base de datos: {codigo_guia}")
                    return registro
            except Exception as db_error:
                logger.error(f"Error accediendo a la base de datos: {db_error}")
            
            # Si no se encuentra en la base de datos, buscar en archivos
            html_path = os.path.join(self.app.config.get('GUIAS_DIR', 'guias'), f'guia_{codigo_guia}.html')
            json_path = os.path.join(self.app.config.get('GUIAS_DIR', 'guias'), f'guia_{codigo_guia}.json')
            
            # Verificar si existe alguno de los archivos
            if not os.path.exists(html_path) and not os.path.exists(json_path):
                logger.warning(f"No se encontraron archivos para {codigo_guia}")
                return None
            
            # Preferir JSON si existe
            if os.path.exists(json_path):
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        datos = json.load(f)
                    
                    # Asegurarse de que el registro tiene los campos necesarios
                    datos = self._verificar_y_corregir_campos(datos, codigo_guia)
                    logger.info(f"Datos obtenidos del archivo JSON para {codigo_guia}")
                    return datos
                except Exception as e:
                    logger.error(f"Error al leer archivo JSON {json_path}: {str(e)}")
            
            # Si no hay JSON o hubo un error, intentar con HTML
            if os.path.exists(html_path):
                try:
                    # Extraer fecha y hora de creación del archivo
                    file_mtime = os.path.getmtime(html_path)
                    file_datetime = datetime.fromtimestamp(file_mtime)
                    fecha_str = file_datetime.strftime('%Y-%m-%d')
                    hora_str = file_datetime.strftime('%H:%M:%S')
                    
                    # Extraer datos del codigo_guia
                    parts = codigo_guia.split('_')
                    codigo_proveedor = parts[0] if len(parts) > 0 else 'N/A'
                    
                    # Si hay más partes, intentar extraer fecha
                    if len(parts) > 1 and len(parts[1]) == 8 and parts[1].isdigit():
                        fecha = parts[1]
                        fecha_str = f"{fecha[:4]}-{fecha[4:6]}-{fecha[6:8]}"
                    
                    # Si hay más partes, intentar extraer hora
                    if len(parts) > 2 and len(parts[2]) == 6 and parts[2].isdigit():
                        hora = parts[2]
                        hora_str = f"{hora[:2]}:{hora[2:4]}:{hora[4:6]}"
                    
                    # Intentar extraer información adicional del HTML
                    registro_info = {
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': codigo_proveedor,
                        'fecha_registro': fecha_str,
                        'hora_registro': hora_str,
                        'html_path': html_path
                    }
                    
                    # Intentar extraer el contenido del HTML para obtener más datos
                    try:
                        with open(html_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                            
                        # Extraer nombre del proveedor si está en el HTML
                        nombre_match = re.search(r'<h3[^>]*>Proveedor:\s*([^<]+)</h3>', html_content)
                        if nombre_match:
                            registro_info['nombre_proveedor'] = nombre_match.group(1).strip()
                        
                        # Extraer cantidad de racimos si está en el HTML
                        racimos_match = re.search(r'<p[^>]*>Cantidad de Racimos:\s*([^<]+)</p>', html_content)
                        if racimos_match:
                            registro_info['cantidad_racimos'] = racimos_match.group(1).strip()
                        
                        # Extraer placa si está en el HTML
                        placa_match = re.search(r'<p[^>]*>Placa:\s*([^<]+)</p>', html_content)
                        if placa_match:
                            registro_info['placa'] = placa_match.group(1).strip()
                        
                        # Extraer transportista si está en el HTML
                        transportista_match = re.search(r'<p[^>]*>Transportista:\s*([^<]+)</p>', html_content)
                        if transportista_match:
                            registro_info['transportista'] = transportista_match.group(1).strip()
                    except Exception as html_error:
                        logger.error(f"Error al extraer datos del HTML {html_path}: {str(html_error)}")
                    
                    # Verificar y corregir campos
                    registro_info = self._verificar_y_corregir_campos(registro_info, codigo_guia)
                    logger.info(f"Datos obtenidos del archivo HTML para {codigo_guia}")
                    return registro_info
                    
                except Exception as e:
                    logger.error(f"Error al procesar archivo HTML {html_path}: {str(e)}")
            
            logger.warning(f"No se pudieron obtener datos para {codigo_guia}")
            return None
            
        except Exception as e:
            logger.error(f"Error al obtener datos de registro {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def generate_unique_id(self):
        """
        Genera un identificador único basado en timestamp
        """
        timestamp = int(time.time() * 1000)
        random_part = os.urandom(4).hex()
        return f"{timestamp}_{random_part}"

    def generar_qr(self, url, path):
        """
        Genera una imagen QR a partir de una URL y la guarda en la ruta especificada.
        
        Args:
            url (str): URL a la que apuntará el código QR
            path (str): Ruta donde guardar la imagen QR
            
        Returns:
            str|None: Ruta del archivo QR generado o None si ocurre un error
        """
        try:
            import qrcode
            import os
            
            # Verificar que la URL sea válida y comience con http:// o https://
            if not url:
                raise ValueError("La URL no puede estar vacía")
                
            # Verificar si la URL comienza con http:// o https://
            parsed_url = urlparse(url)
            if not parsed_url.scheme or not parsed_url.netloc:
                logger.warning(f"La URL proporcionada '{url}' no es una URL absoluta válida")
                # En lugar de manipular la URL o usar una hardcodeada, lanzar error
                raise ValueError("Se requiere una URL absoluta (comenzando con http:// o https://)")
            
            # Asegurarse de que el directorio existe
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
            # Crear un objeto QR
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_H,
                box_size=10,
                border=4,
            )
            
            # Usar la URL tal como viene - nunca manipularla manualmente
            logger.info(f"Generando QR con URL: {url}")
            qr.add_data(url)
            qr.make(fit=True)
            
            # Crear imagen y guardarla
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(path)
            
            # Verificar que se haya guardado correctamente
            if not os.path.exists(path):
                raise FileNotFoundError(f"No se pudo verificar que el archivo QR fue guardado en {path}")
                
            logger.info(f"QR generado correctamente en {path}")
            return path
        except Exception as e:
            logger.error(f"Error al generar QR: {str(e)}")
            logger.error(traceback.format_exc())
            return None

def init_utils(app):
    global utils
    utils = CommonUtils(app)
    return utils

def standardize_template_data(data, record_type="generic"):
    """
    Estandariza los datos que se pasan a los templates, asegurando que todos los campos
    comunes estén presentes y con valores predeterminados adecuados cuando sea necesario.
    
    Args:
        data (dict): Diccionario con los datos a estandarizar
        record_type (str): Tipo de registro ('pesaje', 'entrada', etc.) para campos específicos
        
    Returns:
        dict: Diccionario con datos estandarizados
    """
    if not data:
        logger.warning(f"No se proporcionaron datos para estandarizar ({record_type})")
        data = {}
    
    # Crear una copia para no modificar el original
    standardized = data.copy() if data else {}
    
    # Campos comunes para todos los tipos de registros
    common_fields = {
        'codigo': 'Sin código',
        'codigo_guia': 'Sin código guía',
        'codigo_proveedor': 'Sin código',
        'nombre_proveedor': 'Sin nombre',
        'nombre': 'Sin nombre',
        'cantidad_racimos': 'N/A',
        'fecha': 'Sin fecha',
        'hora': 'Sin hora',
        'finca': 'Sin información',
        'transportista': 'Sin información',
        'placa': 'Sin información',
        'observaciones': '',
    }
    
    # Campos específicos por tipo de registro
    specific_fields = {
        'pesaje': {
            'peso_bruto': 0,
            'peso_tara': 0,
            'peso_neto': 0,
            'estado': 'Pendiente'
        },
        'entrada': {
            'estado': 'Registrado'
        }
    }
    
    # Unificar los campos entre diferentes nombres usados
    field_mappings = {
        'codigo': ['codigo_proveedor', 'Código'],
        'nombre': ['nombre_proveedor', 'nombre_agricultor', 'Nombre del Agricultor'],
        'nombre_proveedor': ['nombre', 'nombre_agricultor', 'Nombre del Agricultor'],
        'cantidad_racimos': ['racimos', 'Cantidad de Racimos'],
        'transportista': ['transportador']
    }
    
    # Aplicar mapeos antes de completar campos faltantes
    for target_field, source_fields in field_mappings.items():
        if target_field not in standardized or not standardized[target_field] or standardized[target_field] in ['N/A', 'None', 'No disponible', None]:
            for source_field in source_fields:
                if source_field in standardized and standardized[source_field] and standardized[source_field] not in ['N/A', 'None', 'No disponible', None]:
                    standardized[target_field] = standardized[source_field]
                    logger.debug(f"Campo {target_field} asignado desde {source_field} con valor: {standardized[source_field]}")
                    break
    
    # Aplicar campos comunes para los que aún falten
    for field, default in common_fields.items():
        if field not in standardized or standardized[field] is None or standardized[field] in ['N/A', 'None', 'No disponible']:
            standardized[field] = default
    
    # Aplicar campos específicos según el tipo
    if record_type in specific_fields:
        for field, default in specific_fields[record_type].items():
            if field not in standardized or standardized[field] is None:
                standardized[field] = default
    
    # Asegurarse de que ciertos campos críticos estén completos en ambas versiones
    standardized['nombre'] = standardized.get('nombre', standardized.get('nombre_proveedor', 'Sin nombre'))
    standardized['nombre_proveedor'] = standardized.get('nombre_proveedor', standardized.get('nombre', 'Sin nombre'))
    
    logger.debug(f"Datos estandarizados ({record_type}): {standardized}")
    return standardized

def get_estado_guia(codigo_guia):
    """
    Determina el estado actual de una guía basado en los datos disponibles.
    
    Args:
        codigo_guia (str): Código de la guía a verificar
        
    Returns:
        dict: Diccionario con la información de estado de la guía
    """
    try:
        # Estado por defecto (guía creada pero sin procesos completados)
        estado_info = {
            'estado': 'creada',
            'descripcion': 'Guía registrada sin procesos completados',
            'porcentaje_avance': 0,
            'clase_css': 'bg-secondary',
            'texto_css': 'text-white',
            'pasos_completados': [],
            'acciones_disponibles': ['entrada'],
            'datos_disponibles': [],
            'siguiente_paso': 'entrada'
        }
        
        # Obtener datos de la guía - versión local
        from flask import current_app
        utils_instance = current_app.config.get('utils')
        if not utils_instance:
            logger.warning("Utils no disponible en configuración, usando método local")
            datos_guia = utils_instance.get_datos_guia(codigo_guia)
        else:
            datos_guia = utils_instance.get_datos_guia(codigo_guia)
        
        if not datos_guia:
            return estado_info
        
        # PRIORIDAD: Verificar si hay datos de salida (esto es lo más importante)
        # Si hay datos de salida, el proceso está completado
        if (datos_guia.get('fecha_salida') and datos_guia.get('hora_salida')) or datos_guia.get('estado_final') == 'completado' or datos_guia.get('estado_actual') == 'proceso_completado':
            estado_info['estado'] = 'proceso_completado'
            estado_info['descripcion'] = 'Proceso completado'
            estado_info['porcentaje_avance'] = 100
            estado_info['clase_css'] = 'bg-success'
            # Asegurar que todos los pasos se marquen como completados
            pasos_completos = ['entrada', 'pesaje', 'clasificacion', 'pesaje_neto', 'salida']
            for paso in pasos_completos:
                if paso not in estado_info['pasos_completados']:
                    estado_info['pasos_completados'].append(paso)
                if paso not in estado_info['datos_disponibles']:
                    estado_info['datos_disponibles'].append(paso)
            estado_info['siguiente_paso'] = None
            logger.info(f"Estado determinado para guía {codigo_guia}: {estado_info['estado']} (proceso completado)")
            return estado_info
        
        # SEGUNDA PRIORIDAD: Verificar si ya se completó la clasificación
        # Cualquiera de estos indicadores muestra que la clasificación está completada
        if (datos_guia.get('estado_actual') == 'clasificacion_completada' or 
            datos_guia.get('clasificacion_completada') is True or 
            datos_guia.get('estado_clasificacion') == 'completado' or
            (datos_guia.get('pasos_completados') and 'clasificacion' in datos_guia.get('pasos_completados'))):
            estado_info['estado'] = 'clasificacion_completada'
            estado_info['descripcion'] = 'Clasificación completada'
            estado_info['porcentaje_avance'] = 70
            estado_info['clase_css'] = 'bg-success'
            estado_info['pasos_completados'] = ['entrada', 'pesaje', 'clasificacion']
            estado_info['acciones_disponibles'] = ['entrada', 'pesaje', 'clasificacion', 'pesaje_neto']
            estado_info['datos_disponibles'] = ['entrada', 'pesaje', 'clasificacion']
            estado_info['siguiente_paso'] = 'pesaje_neto'
            return estado_info
        
        # Verificar primero si hay datos de pesaje
        peso_bruto = datos_guia.get('peso_bruto')
        
        # Si hay datos de pesaje
        if peso_bruto and str(peso_bruto) not in ['Pendiente', 'N/A', 'No disponible'] and float(str(peso_bruto).replace(',', '.')) > 0:
            estado_info['estado'] = 'pesaje_completado'
            estado_info['descripcion'] = 'Pesaje completado'
            estado_info['porcentaje_avance'] = 50
            estado_info['clase_css'] = 'bg-info'
            estado_info['pasos_completados'] = ['entrada', 'pesaje']
            estado_info['acciones_disponibles'] = ['entrada', 'pesaje', 'clasificacion']
            estado_info['datos_disponibles'] = ['entrada', 'pesaje']
            estado_info['siguiente_paso'] = 'clasificacion'
        else:
            # Solo hay datos de entrada
            estado_info['estado'] = 'entrada_completada'
            estado_info['descripcion'] = 'Entrada registrada'
            estado_info['porcentaje_avance'] = 25
            estado_info['clase_css'] = 'bg-primary'
            estado_info['pasos_completados'] = ['entrada']
            estado_info['acciones_disponibles'] = ['entrada', 'pesaje']
            estado_info['datos_disponibles'] = ['entrada']
            estado_info['siguiente_paso'] = 'pesaje'
        
        # Verificar si hay datos de clasificación
        clasificacion_completada = datos_guia.get('clasificacion_completada')
        if clasificacion_completada:
            estado_info['estado'] = 'clasificacion_completada'
            estado_info['descripcion'] = 'Clasificación completada'
            estado_info['porcentaje_avance'] = 70
            estado_info['clase_css'] = 'bg-success'
            if 'clasificacion' not in estado_info['pasos_completados']:
                estado_info['pasos_completados'].append('clasificacion')
            if 'clasificacion' not in estado_info['acciones_disponibles']:
                estado_info['acciones_disponibles'].append('clasificacion')
            if 'pesaje_neto' not in estado_info['acciones_disponibles']:
                estado_info['acciones_disponibles'].append('pesaje_neto')
            if 'clasificacion' not in estado_info['datos_disponibles']:
                estado_info['datos_disponibles'].append('clasificacion')
            estado_info['siguiente_paso'] = 'pesaje_neto'
        
        # Verificar si hay datos de peso neto
        peso_neto = datos_guia.get('peso_neto')
        pesaje_neto_completado = datos_guia.get('pesaje_neto_completado', False)
        
        if (pesaje_neto_completado or 
            (peso_neto and str(peso_neto) not in ['Pendiente', 'N/A', 'No disponible'] and float(str(peso_neto).replace(',', '.')) > 0)):
            estado_info['estado'] = 'pesaje_neto_completado'
            estado_info['descripcion'] = 'Pesaje neto completado'
            estado_info['porcentaje_avance'] = 80  # Actualizado al 80% para pesaje neto
            estado_info['clase_css'] = 'bg-success'
            if 'pesaje_neto' not in estado_info['pasos_completados']:
                estado_info['pasos_completados'].append('pesaje_neto')
            if 'salida' not in estado_info['acciones_disponibles']:
                estado_info['acciones_disponibles'].append('salida')
            if 'pesaje_neto' not in estado_info['datos_disponibles']:
                estado_info['datos_disponibles'].append('pesaje_neto')
            estado_info['siguiente_paso'] = 'salida'
            
        # Verificar si hay datos específicos de salida (como respaldo al check inicial)
        if datos_guia.get('fecha_salida') and datos_guia.get('hora_salida'):
            estado_info['estado'] = 'proceso_completado'
            estado_info['descripcion'] = 'Proceso completado'
            estado_info['porcentaje_avance'] = 100
            estado_info['clase_css'] = 'bg-success'
            if 'salida' not in estado_info['pasos_completados']:
                estado_info['pasos_completados'].append('salida')
            if 'salida' not in estado_info['datos_disponibles']:
                estado_info['datos_disponibles'].append('salida')
            estado_info['siguiente_paso'] = None
        elif datos_guia.get('estado_salida') == 'Completado':
            estado_info['estado'] = 'proceso_completado'
            estado_info['descripcion'] = 'Proceso completado'
            estado_info['porcentaje_avance'] = 100
            estado_info['clase_css'] = 'bg-success'
            if 'salida' not in estado_info['pasos_completados']:
                estado_info['pasos_completados'].append('salida')
            if 'salida' not in estado_info['datos_disponibles']:
                estado_info['datos_disponibles'].append('salida')
            estado_info['siguiente_paso'] = None
                
        # Si hay algún campo extra que indique estado final (como respaldo)
        estado_final = datos_guia.get('estado_final')
        if estado_final == 'completado':
            estado_info['estado'] = 'proceso_completado'
            estado_info['descripcion'] = 'Proceso completado'
            estado_info['porcentaje_avance'] = 100
            estado_info['clase_css'] = 'bg-success'
            # Asegurar que todos los pasos se marquen como completados
            pasos_completos = ['entrada', 'pesaje', 'clasificacion', 'pesaje_neto', 'salida']
            for paso in pasos_completos:
                if paso not in estado_info['pasos_completados']:
                    estado_info['pasos_completados'].append(paso)
                if paso not in estado_info['datos_disponibles']:
                    estado_info['datos_disponibles'].append(paso)
            estado_info['siguiente_paso'] = None
        
        logger.info(f"Estado determinado para guía {codigo_guia}: {estado_info['estado']}")
        return estado_info
    except Exception as e:
        logger.error(f"Error determinando estado de guía: {str(e)}")
        return {
            'estado': 'error',
            'descripcion': f'Error: {str(e)}',
            'porcentaje_avance': 0,
            'clase_css': 'bg-danger',
            'texto_css': 'text-white',
            'pasos_completados': [],
            'acciones_disponibles': [],
            'datos_disponibles': [],
            'siguiente_paso': None
        }

