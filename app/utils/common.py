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

def format_datetime_filter(utc_timestamp_str, format='%d/%m/%Y %H:%M:%S'):
    """
    Jinja2 filter to convert a UTC timestamp string (YYYY-MM-DD HH:MM:SS)
    to Bogota local time and format it.
    """
    if not utc_timestamp_str or not isinstance(utc_timestamp_str, str):
        return 'N/A' # O '' o None, según el resultado deseado para entrada inválida

    try:
        # Parsear el string del timestamp UTC
        utc_dt = datetime.strptime(utc_timestamp_str, '%Y-%m-%d %H:%M:%S')
        # Hacerlo consciente de la zona horaria (asumiendo que el string es UTC)
        utc_dt = UTC.localize(utc_dt)
        # Convertir a la zona horaria de Bogotá
        bogota_dt = utc_dt.astimezone(BOGOTA_TZ)
        # Formatearlo
        return bogota_dt.strftime(format)
    except (ValueError, TypeError) as e:
        logger.error(f"Error formateando timestamp '{utc_timestamp_str}' con formato '{format}': {e}")
        return f"ErrFmt: {utc_timestamp_str}" # Devolver original o indicador de error
    except Exception as e:
        logger.error(f"Error inesperado formateando timestamp '{utc_timestamp_str}': {e}")
        return "Error"

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
                    c.timestamp_clasificacion_utc, 
                    c.clasificacion_manual_json, 
                    c.clasificacion_automatica_json,
                    c.verde_manual, 
                    c.sobremaduro_manual, 
                    c.danio_corona_manual, 
                    c.pendunculo_largo_manual, 
                    c.podrido_manual, 
                    c.verde_automatico,
                    c.sobremaduro_automatico,
                    c.danio_corona_automatico,
                    c.pendunculo_largo_automatico,
                    c.podrido_automatico,
                    c.total_racimos_detectados,
                    c.clasificacion_consolidada,
                    pn.peso_tara, pn.peso_neto, pn.peso_producto, 
                    pn.timestamp_pesaje_neto_utc,
                    pn.tipo_pesaje_neto, pn.comentarios as comentarios_neto, pn.respuesta_sap,
                    s.timestamp_salida_utc, s.comentarios_salida
                FROM entry_records e
                LEFT JOIN pesajes_bruto pb ON e.codigo_guia = pb.codigo_guia
                LEFT JOIN clasificaciones c ON e.codigo_guia = c.codigo_guia
                LEFT JOIN pesajes_neto pn ON e.codigo_guia = pn.codigo_guia
                LEFT JOIN salidas s ON e.codigo_guia = s.codigo_guia
                WHERE e.codigo_guia = ?
            """
            
            cursor.execute(query, (codigo_guia,))
            result = cursor.fetchone()

            # Log the raw database result
            logger.info(f"--- get_datos_guia DB Raw Result for {codigo_guia}: {result} ---")
            if result:
                 logger.info(f"--- Raw Result Keys: {result.keys()} ---")
                 # Explicitly log the timestamp value from the raw result
                 try:
                     raw_timestamp = result['timestamp_clasificacion_utc']
                     logger.info(f"--- Raw Result timestamp_clasificacion_utc: {raw_timestamp} (Type: {type(raw_timestamp)}) ---")
                 except IndexError:
                     logger.warning("--- Column 'timestamp_clasificacion_utc' not found in raw DB result keys! Check SQL Query. ---")

            if not result:
                logger.warning(f"No entry_record found for codigo_guia: {codigo_guia}")
                # Close connection before returning None
                if conn:
                    conn.close()
                return None

            # Convert Row object to a mutable dictionary
            datos_guia = dict(result)
            # Log after conversion to dict
            logger.info(f"--- get_datos_guia Dict Conversion for {codigo_guia}: {datos_guia} ---")
            logger.info(f"--- Dict timestamp_clasificacion_utc after conversion: {datos_guia.get('timestamp_clasificacion_utc')} ---")

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
            datos_guia['tipo_pesaje_neto'] = datos_guia.get('tipo_pesaje_neto')
            datos_guia['comentarios_neto'] = datos_guia.get('comentarios_neto')
            datos_guia['respuesta_sap'] = datos_guia.get('respuesta_sap')

            datos_guia['comentarios_salida'] = datos_guia.get('comentarios_salida')

            # --- Procesar datos de clasificación manual --- 
            clasif_manual_dict = {}
            try:
                # 1. Intentar leer desde la columna JSON
                manual_json_str = datos_guia.get('clasificacion_manual_json')
                if manual_json_str:
                    logger.debug(f"Procesando clasificacion_manual_json para {codigo_guia}: {manual_json_str}")
                    clasif_manual_dict = json.loads(manual_json_str)
                else:
                    logger.debug(f"Columna clasificacion_manual_json vacía para {codigo_guia}. Intentando columnas individuales.")
                    # 2. Si JSON está vacío, intentar leer de columnas individuales (como respaldo)
                    clasif_manual_dict = {
                        'verdes': datos_guia.get('verde_manual'),
                        'sobremaduros': datos_guia.get('sobremaduro_manual'),
                        'danio_corona': datos_guia.get('danio_corona_manual'),
                        'pedunculo_largo': datos_guia.get('pendunculo_largo_manual'),
                        'podridos': datos_guia.get('podrido_manual')
                    }
                    # Filtrar valores None si se leyeron de columnas individuales
                    clasif_manual_dict = {k: v for k, v in clasif_manual_dict.items() if v is not None}
            except json.JSONDecodeError as json_err:
                logger.error(f"Error decodificando clasificacion_manual_json para {codigo_guia}: {json_err}. Contenido: {manual_json_str}")
                clasif_manual_dict = {} # Dejar vacío si hay error
            except Exception as e:
                 logger.error(f"Error inesperado procesando clasificación manual para {codigo_guia}: {e}")
                 clasif_manual_dict = {}
            
            # Asegurar que el diccionario final exista y tenga las claves esperadas (con None si falta)
            final_manual = {}
            claves_esperadas = ['verdes', 'sobremaduros', 'danio_corona', 'pedunculo_largo', 'podridos']
            for clave in claves_esperadas:
                # Usar .get() para evitar KeyError si la clave no existe en clasif_manual_dict
                valor = clasif_manual_dict.get(clave)
                try:
                    # Intentar convertir a float, manejar None o string vacío
                    final_manual[clave] = float(valor) if valor is not None and str(valor).strip() != '' else 0.0
                except (ValueError, TypeError):
                    logger.warning(f"No se pudo convertir el valor '{valor}' para '{clave}' a float en guía {codigo_guia}. Usando 0.0.")
                    final_manual[clave] = 0.0 # Usar 0.0 si la conversión falla
                    
            datos_guia['clasificacion_manual'] = final_manual
            logger.info(f"Clasificación manual procesada para {codigo_guia}: {datos_guia['clasificacion_manual']}")
            # --- Fin Procesar datos de clasificación manual --- 

            # Process classification data (automatic)
            auto_data_str = datos_guia.get('clasificacion_automatica_json')
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
            
            # --- Determine Current Status and Next Step --- 
            estado_actual = 'pendiente'
            siguiente_paso = 'entrada' # Default start
            
            # Final check for essential fields, setting defaults if needed
            essential_fields = ['placa', 'transportador', 'acarreo', 'cargo']
            for field in essential_fields:
                if not datos_guia.get(field):
                    datos_guia[field] = 'No disponible'
            
            # Log the final dictionary before returning
            logger.info(f"--- get_datos_guia Final Dict Before Return for {codigo_guia}: {datos_guia} ---")
            logger.info(f"--- Final Dict timestamp_clasificacion_utc before return: {datos_guia.get('timestamp_clasificacion_utc')} ---")
            
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
                        # Filtrar datos_guia para pasar solo las claves relevantes a store_pesaje_neto
                        keys_pesaje_neto = [
                            'codigo_guia', 'peso_bruto', 'peso_tara', 'peso_neto',
                            'timestamp_pesaje_bruto_utc', 'timestamp_pesaje_neto_utc'
                        ]
                        # Asegurarse de que codigo_guia siempre esté presente si se llama a store_pesaje_neto
                        if 'codigo_guia' not in datos_guia:
                             datos_guia['codigo_guia'] = codigo # Añadir codigo_guia si falta

                        datos_para_pesaje_neto = {k: datos_guia[k] for k in keys_pesaje_neto if k in datos_guia}

                        # Solo llamar a store_pesaje_neto si tenemos los datos necesarios y el código de guía
                        if 'peso_neto' in datos_para_pesaje_neto and 'peso_tara' in datos_para_pesaje_neto and 'codigo_guia' in datos_para_pesaje_neto:
                             store_pesaje_neto(datos_para_pesaje_neto) # Pasar el diccionario filtrado
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
    Determina el estado actual de la guía y los pasos completados.
    Devuelve un diccionario con:
        - pasos_completados: lista de strings
        - siguiente_paso: string
        - descripcion: string
        - porcentaje_avance: int
        - datos_disponibles: lista de strings
    """
    pasos_completados = []
    datos_disponibles = []
    siguiente_paso = None
    descripcion = ""
    porcentaje_avance = 0

    # Obtener datos de la guía
    datos_guia = None
    try:
        from app.utils.common import CommonUtils
        utils = CommonUtils(current_app)
        datos_guia = utils.get_datos_guia(codigo_guia)
    except Exception as e:
        print(f"Error obteniendo datos de guía en get_estado_guia: {e}")
        return {
            "pasos_completados": [],
            "siguiente_paso": "entrada",
            "descripcion": "Error obteniendo datos",
            "porcentaje_avance": 0,
            "datos_disponibles": []
        }

    # Paso 1: Registro de entrada
    if datos_guia and datos_guia.get("timestamp_registro_utc"):
        pasos_completados.append("entrada")
        datos_disponibles.append("entrada")
        porcentaje_avance = 20
        descripcion = "Registro de entrada completado"
        siguiente_paso = "pesaje"
    else:
        siguiente_paso = "entrada"
        descripcion = "Pendiente registro de entrada"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": descripcion,
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": datos_disponibles
        }

    # Paso 2: Pesaje bruto
    peso_bruto = datos_guia.get("peso_bruto")
    logger.info(f"[ESTADO] peso_bruto: {peso_bruto!r} (type: {type(peso_bruto)})")
    pesaje_completado = False
    try:
        if peso_bruto is not None and str(peso_bruto).strip() not in ["", "Pendiente", "N/A"]:
            if isinstance(peso_bruto, str):
                peso_bruto_float = float(peso_bruto.replace(",", "."))
            else:
                peso_bruto_float = float(peso_bruto)
            pesaje_completado = peso_bruto_float > 0
    except Exception as e:
        logger.warning(f"[ESTADO] No se pudo convertir peso_bruto a float: {peso_bruto!r} ({e})")
        pesaje_completado = False

    if pesaje_completado:
        pasos_completados.append("pesaje")
        datos_disponibles.append("pesaje")
        porcentaje_avance = 40
        descripcion = "Pesaje bruto completado, pendiente clasificación"
        siguiente_paso = "clasificacion"
    else:
        siguiente_paso = "pesaje"
        descripcion = "Pendiente pesaje bruto"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": descripcion,
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": datos_disponibles
        }

    # Paso 3: Clasificación
    if datos_guia.get("timestamp_clasificacion_utc"):
        pasos_completados.append("clasificacion")
        datos_disponibles.append("clasificacion")
        porcentaje_avance = 60
        descripcion = "Clasificación completada, pendiente pesaje neto"
        siguiente_paso = "pesaje_neto"
    else:
        siguiente_paso = "clasificacion"
        descripcion = "Pendiente clasificación"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": descripcion,
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": datos_disponibles
        }

    # Paso 4: Pesaje neto
    if datos_guia.get("peso_neto") and datos_guia["peso_neto"] not in [None, "", "Pendiente", "N/A"]:
        pasos_completados.append("pesaje_neto")
        datos_disponibles.append("pesaje_neto")
        porcentaje_avance = 80
        descripcion = "Pesaje neto completado, pendiente salida"
        siguiente_paso = "salida"
    else:
        siguiente_paso = "pesaje_neto"
        descripcion = "Pendiente pesaje neto"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": descripcion,
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": datos_disponibles
        }

    # Paso 5: Salida
    if datos_guia.get("timestamp_salida_utc"):
        pasos_completados.append("salida")
        datos_disponibles.append("salida")
        porcentaje_avance = 100
        descripcion = "Proceso completado"
        siguiente_paso = None
    else:
        siguiente_paso = "salida"
        descripcion = "Pendiente salida"

    return {
        "pasos_completados": pasos_completados,
        "siguiente_paso": siguiente_paso,
        "descripcion": descripcion,
        "porcentaje_avance": porcentaje_avance,
        "datos_disponibles": datos_disponibles
    }

def get_estado_guia_dict(datos_guia):
    pasos_completados = []
    porcentaje_avance = 0
    siguiente_paso = 'entrada'

    # Paso 1: Entrada
    if datos_guia.get('codigo_guia'):
        pasos_completados.append('entrada')
        porcentaje_avance = 20
        siguiente_paso = 'pesaje'
    else:
        return {
            'pasos_completados': pasos_completados,
            'siguiente_paso': siguiente_paso,
            'descripcion': 'Pendiente registro de entrada',
            'porcentaje_avance': porcentaje_avance,
            'datos_disponibles': pasos_completados.copy()
        }

    # Paso 2: Pesaje
    peso_bruto = datos_guia.get('peso_bruto')
    print(f"[ESTADO] peso_bruto: {peso_bruto} (type: {type(peso_bruto)})")
    if (
        peso_bruto is not None
        and isinstance(peso_bruto, (int, float))
        and peso_bruto > 0
    ):
        pasos_completados.append('pesaje')
        porcentaje_avance = 40
        siguiente_paso = 'clasificacion'
    else:
        return {
            'pasos_completados': pasos_completados,
            'siguiente_paso': 'pesaje',
            'descripcion': 'Pendiente pesaje bruto',
            'porcentaje_avance': porcentaje_avance,
            'datos_disponibles': pasos_completados.copy()
        }

    # Paso 3: Clasificación
    if datos_guia.get("timestamp_clasificacion_utc"):
        pasos_completados.append("clasificacion")
        porcentaje_avance = 60
        siguiente_paso = "pesaje_neto"
    else:
        siguiente_paso = "clasificacion"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": "Pendiente clasificación",
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": pasos_completados.copy()
        }

    # Paso 4: Pesaje neto
    if datos_guia.get("peso_neto") and datos_guia["peso_neto"] not in [None, "", "Pendiente", "N/A"]:
        pasos_completados.append("pesaje_neto")
        porcentaje_avance = 80
        siguiente_paso = "salida"
    else:
        siguiente_paso = "pesaje_neto"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": "Pendiente pesaje neto",
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": pasos_completados.copy()
        }

    # Paso 5: Salida
    if datos_guia.get("timestamp_salida_utc"):
        pasos_completados.append("salida")
        porcentaje_avance = 100
        siguiente_paso = None
    else:
        siguiente_paso = "salida"
        return {
            "pasos_completados": pasos_completados,
            "siguiente_paso": siguiente_paso,
            "descripcion": "Pendiente salida",
            "porcentaje_avance": porcentaje_avance,
            "datos_disponibles": pasos_completados.copy()
        }

    return {
        "pasos_completados": pasos_completados,
        "siguiente_paso": siguiente_paso,
        "descripcion": "Proceso completado",
        "porcentaje_avance": porcentaje_avance,
        "datos_disponibles": pasos_completados.copy()
    }

def get_db_connection():
    """
    Establece y devuelve una conexión a la base de datos utilizando la ruta
    configurada en la aplicación.

    Returns:
        sqlite3.Connection: Objeto de conexión a la base de datos.

    Raises:
        KeyError: Si 'TIQUETES_DB_PATH' no está en current_app.config.
        sqlite3.Error: Si ocurre un error al conectar a la base de datos.
        Exception: Para cualquier otro error inesperado.
    """
    try:
        # Asegurarse de importar current_app aquí si no está disponible globalmente en este punto
        from flask import current_app, g 
        # También importar sqlite3 y logging si es necesario
        import sqlite3
        import logging
        logger = logging.getLogger(__name__)

        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # Mantener consistencia con get_datos_guia
        logger.debug(f"Conexión a BD establecida: {db_path}")
        return conn
    except KeyError as ke:
        logger.error(f"Error de configuración: {ke}. Asegúrese que TIQUETES_DB_PATH esté configurado.", exc_info=True)
        raise # Relanzar para que el error sea visible en la capa superior
    except sqlite3.Error as e:
        logger.error(f"Error al conectar a la base de datos en {db_path}: {e}", exc_info=True)
        raise # Relanzar para que el error sea visible
    except Exception as e:
        logger.error(f"Error inesperado al obtener conexión a BD: {e}", exc_info=True)
        raise

def get_utc_timestamp_str():
    """
    Devuelve el timestamp actual en UTC como un string formateado.
    """
    # Asegurarse de importar datetime y pytz si no están globales
    from datetime import datetime
    import pytz
    
    return datetime.now(pytz.utc).strftime('%Y-%m-%d %H:%M:%S')

