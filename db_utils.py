import sqlite3
import os
import logging
from datetime import datetime, time
import traceback
from flask import current_app
import pytz

# Define timezones
UTC = pytz.utc
BOGOTA_TZ = pytz.timezone('America/Bogota')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def store_entry_record(record_data):
    """
    Store an entry record in the database.
    Expects 'timestamp_registro_utc' field instead of 'fecha_registro' and 'hora_registro'.
    
    Args:
        record_data (dict): Dictionary containing the entry record data
        
    Returns:
        bool: True if successful, False otherwise
    """
    conn = None
    try:
        # Get DB path from app config
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        codigo_guia = record_data.get('codigo_guia')
        codigo_proveedor = record_data.get('codigo_proveedor', '')
        
        if not codigo_guia:
            logger.error("No se puede guardar un registro sin código de guía")
            return False
            
        # Verificar posibles duplicados en registros recientes (últimos 10 minutos)
        cursor.execute(
            "SELECT codigo_guia, nombre_proveedor, fecha_creacion FROM entry_records " + 
            "WHERE codigo_proveedor = ? AND fecha_creacion > datetime('now', '-10 minutes')",
            (codigo_proveedor,)
        )
        existing_records = cursor.fetchall()
        
        if existing_records:
            logger.warning(f"Se encontraron {len(existing_records)} registros recientes para el proveedor {codigo_proveedor}")
            for record in existing_records:
                logger.info(f"Registro existente: codigo_guia={record[0]}, nombre={record[1]}, fecha={record[2]}")
                
            # Si el registro exacto ya existe, agregamos identificador de versión
            if any(record[0] == codigo_guia for record in existing_records):
                logger.warning(f"Guía duplicada detectada: {codigo_guia}. Agregando versión.")
                record_data['codigo_guia'] = f"{codigo_guia}_v{len(existing_records)}"
                codigo_guia = record_data['codigo_guia']
                logger.info(f"Nuevo código de guía generado: {codigo_guia}")
        
        # Check if record already exists with exactly the same codigo_guia
        cursor.execute("SELECT id FROM entry_records WHERE codigo_guia = ?", 
                      (codigo_guia,))
        existing = cursor.fetchone()
        
        if existing:
            # Update existing record
            update_cols = []
            params = []
            
            for key, value in record_data.items():
                if key != 'codigo_guia':  # Skip the primary key
                    update_cols.append(f"{key} = ?")
                    params.append(value)
            
            # Add the WHERE condition parameter
            params.append(codigo_guia)
            
            update_query = f"UPDATE entry_records SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            logger.info(f"Updated existing record for guide: {codigo_guia}")
        else:
            # Insert new record
            columns = ', '.join(record_data.keys())
            placeholders = ', '.join(['?' for _ in record_data])
            values = list(record_data.values())
            
            insert_query = f"INSERT INTO entry_records ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, values)
            logger.info(f"Inserted new record for guide: {codigo_guia}")
        
        conn.commit()
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error storing entry record: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_entry_records(filters=None):
    """
    Retrieve entry records from the database, optionally filtered.
    
    Args:
        filters (dict, optional): Dictionary with filter conditions
        
    Returns:
        list: List of entry records as dictionaries
    """
    conn = None
    try:
        # Get DB path from app config
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        query = "SELECT * FROM entry_records"
        params = []
        
        # Apply filters if provided
        if filters:
            conditions = []
            
            # Use timestamp_registro_utc for date filtering
            if filters.get('fecha_desde'):
                try:
                    fecha_desde_str = filters['fecha_desde'] # YYYY-MM-DD
                    # Crear datetime naive al inicio del día en Bogotá
                    naive_dt_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                    naive_dt_desde = datetime.combine(naive_dt_desde.date(), time.min)
                    # Localizar a Bogotá
                    bogota_dt_desde = BOGOTA_TZ.localize(naive_dt_desde)
                    # Convertir a UTC
                    utc_dt_desde = bogota_dt_desde.astimezone(UTC)
                    # Formatear para SQL
                    utc_timestamp_desde = utc_dt_desde.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_registro_utc >= ?")
                    params.append(utc_timestamp_desde)
                    logger.info(f"Filtro fecha_desde (Bogotá: {fecha_desde_str} 00:00:00) convertido a UTC: {utc_timestamp_desde}")
                except (ValueError, TypeError) as e:
                     logger.warning(f"Error procesando fecha_desde '{filters['fecha_desde']}': {e}. Saltando filtro de fecha.")
                
            if filters.get('fecha_hasta'):
                try:
                    fecha_hasta_str = filters['fecha_hasta'] # YYYY-MM-DD
                    # Crear datetime naive al final del día en Bogotá
                    naive_dt_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                    naive_dt_hasta = datetime.combine(naive_dt_hasta.date(), time.max.replace(microsecond=0)) # time.max para 23:59:59
                    # Localizar a Bogotá
                    bogota_dt_hasta = BOGOTA_TZ.localize(naive_dt_hasta)
                    # Convertir a UTC
                    utc_dt_hasta = bogota_dt_hasta.astimezone(UTC)
                    # Formatear para SQL
                    utc_timestamp_hasta = utc_dt_hasta.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_registro_utc <= ?")
                    params.append(utc_timestamp_hasta)
                    logger.info(f"Filtro fecha_hasta (Bogotá: {fecha_hasta_str} 23:59:59) convertido a UTC: {utc_timestamp_hasta}")
                except (ValueError, TypeError) as e:
                     logger.warning(f"Error procesando fecha_hasta '{filters['fecha_hasta']}': {e}. Saltando filtro de fecha.")
                
            if filters.get('codigo_proveedor'):
                conditions.append("codigo_proveedor LIKE ?")
                params.append(f"%{filters['codigo_proveedor']}%")
                
            if filters.get('nombre_proveedor'):
                conditions.append("nombre_proveedor LIKE ?")
                params.append(f"%{filters['nombre_proveedor']}%")
                
            if filters.get('placa'):
                conditions.append("placa LIKE ?")
                params.append(f"%{filters['placa']}%")
            
            if filters.get('codigo_guia'):
                conditions.append("codigo_guia LIKE ?")
                params.append(f"%{filters['codigo_guia']}%")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        # Execute the query without ordering to fetch all records
        cursor.execute(query, params)
        
        # Convert rows to dictionaries
        records = []
        for row in cursor.fetchall():
            record = {key: row[key] for key in row.keys()}
            
            # Parse modified_fields if it's stored as string
            if record.get('modified_fields') and isinstance(record['modified_fields'], str):
                try:
                    import json
                    record['modified_fields'] = json.loads(record['modified_fields'])
                except:
                    record['modified_fields'] = {}
            
            # Asegurar que campos críticos tengan valores predeterminados
            campos_criticos = [
                'codigo_proveedor', 'nombre_proveedor', 'placa', 
                'cantidad_racimos', 'transportador', 'acarreo', 'cargo'
            ]
            for campo in campos_criticos:
                if campo not in record or record[campo] is None or record[campo] == '':
                    record[campo] = 'No disponible'
            
            # Handle new timestamp field
            if not record.get('timestamp_registro_utc'):
                record['timestamp_registro_utc'] = '1970-01-01 00:00:00' # Default timestamp
                
            # Convertir timestamp UTC a fecha y hora local de Bogotá
            try:
                if record.get('timestamp_registro_utc'):
                    dt_utc = datetime.strptime(record['timestamp_registro_utc'], "%Y-%m-%d %H:%M:%S")
                    dt_utc = UTC.localize(dt_utc)
                    dt_bogota = dt_utc.astimezone(BOGOTA_TZ)
                    record['fecha_registro'] = dt_bogota.strftime('%d/%m/%Y')
                    record['hora_registro'] = dt_bogota.strftime('%H:%M:%S')
                else:
                    record['fecha_registro'] = 'N/A'
                    record['hora_registro'] = 'N/A'
            except (ValueError, TypeError) as e:
                logger.warning(f"Error convirtiendo timestamp '{record.get('timestamp_registro_utc')}' a hora local: {e}")
                record['fecha_registro'] = 'Error Fmt'
                record['hora_registro'] = 'Error Fmt'
                
            # Remove old date/time fields if they still exist somehow (optional cleanup)
            record.pop('fecha_registro_old', None)
            record.pop('hora_registro_old', None)
                
            # Procesar el código del proveedor para asegurar el formato correcto
            if record.get('codigo_proveedor') and record['codigo_proveedor'] != 'No disponible':
                codigo_proveedor = record['codigo_proveedor']
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_proveedor)
                if match:
                    codigo_base = match.group(1)
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'
            
            # Extraer código de proveedor desde codigo_guia si es necesario
            if (not record.get('codigo_proveedor') or record['codigo_proveedor'] == 'No disponible') and record.get('codigo_guia'):
                codigo_guia = record['codigo_guia']
                codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_base)
                if match:
                    codigo_base = match.group(1)
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'
                
            records.append(record)
        
        # Sort records by timestamp_registro_utc (string comparison works for YYYY-MM-DD HH:MM:SS)
        records.sort(key=lambda r: r.get('timestamp_registro_utc', '1970-01-01 00:00:00'), reverse=True)
        
        return records
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return []
    except sqlite3.Error as e:
        logger.error(f"Error retrieving entry records: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_entry_record_by_guide_code(codigo_guia):
    """
    Retrieve a single entry record by its codigo_guia.
    """
    conn = None
    try:
        # Get DB path from app config
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        cursor = conn.cursor()
        
        # Select all columns for the given codigo_guia
        cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            # Convert row to dictionary
            record = {key: row[key] for key in row.keys()}

            # Parse modified_fields if it's stored as string
            if record.get('modified_fields') and isinstance(record['modified_fields'], str):
                try:
                    import json
                    record['modified_fields'] = json.loads(record['modified_fields'])
                except:
                    record['modified_fields'] = {}
            
            # Ensure critical fields have default values
            campos_criticos = [
                'codigo_proveedor', 'nombre_proveedor', 'placa', 
                'cantidad_racimos', 'transportador', 'acarreo', 'cargo'
            ]
            for campo in campos_criticos:
                if campo not in record or record[campo] is None or record[campo] == '':
                    record[campo] = 'No disponible'
            
            # Handle new timestamp field and remove old ones if present
            if not record.get('timestamp_registro_utc'):
                record['timestamp_registro_utc'] = '1970-01-01 00:00:00' # Default timestamp
            # record.pop('fecha_registro', None) # Keep this commented or remove
            # record.pop('hora_registro', None) # Keep this commented or remove

            # Process provider code (same logic as get_entry_records)
            if record.get('codigo_proveedor') and record['codigo_proveedor'] != 'No disponible':
                codigo_proveedor = record['codigo_proveedor']
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_proveedor)
                if match:
                    codigo_base = match.group(1)
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'

            if (not record.get('codigo_proveedor') or record['codigo_proveedor'] == 'No disponible') and record.get('codigo_guia'):
                codigo_guia = record['codigo_guia']
                codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_base)
                if match:
                    codigo_base = match.group(1)
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'
            
            return record
        else:
            logger.warning(f"No entry record found for guide code: {codigo_guia}")
            return None
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving entry record {codigo_guia}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_latest_entry_by_provider_code(codigo_proveedor):
    """
    Obtiene el registro de entrada más reciente para un código de proveedor.
    
    Args:
        codigo_proveedor (str): Código del proveedor a buscar
        
    Returns:
        dict: Datos del registro más reciente o None si no se encuentra
    """
    conn = None
    try:
        # Get DB path from app config
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Buscar el registro más reciente por código de proveedor
        cursor.execute(
            "SELECT * FROM entry_records WHERE codigo_proveedor = ? ORDER BY fecha_creacion DESC LIMIT 1",
            (codigo_proveedor,)
        )
        row = cursor.fetchone()
        
        if row:
            # Convertir el objeto Row a diccionario
            registro = dict(row)
            logger.info(f"Encontrado registro más reciente para proveedor {codigo_proveedor}: {registro.get('codigo_guia')}")
            return registro
        else:
            logger.warning(f"No se encontraron registros para el proveedor {codigo_proveedor}")
            return None
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error al buscar registro por código de proveedor: {e}")
        return None
    finally:
        if conn:
            conn.close()

def update_pesaje_bruto(codigo_guia, datos_pesaje):
    """
    Actualiza un registro de pesaje bruto existente o lo crea si no existe.
    
    Args:
        codigo_guia (str): Código de guía del pesaje a actualizar
        datos_pesaje (dict): Datos actualizados del pesaje
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    try:
        # Utilizamos db_operations para almacenar el pesaje
        import db_operations
        
        # Asegurarse de que el código guía esté en los datos
        datos_pesaje['codigo_guia'] = codigo_guia
        
        # Almacenar el pesaje bruto utilizando la función existente
        result = db_operations.store_pesaje_bruto(datos_pesaje)
        
        if result:
            logger.info(f"Pesaje bruto actualizado para guía: {codigo_guia}")
            return True
        else:
            logger.error(f"Error al actualizar pesaje bruto para guía: {codigo_guia}")
            return False
    except Exception as e:
        logger.error(f"Error en update_pesaje_bruto: {e}")
        logger.error(traceback.format_exc())
        return False

def get_pesaje_bruto_by_codigo_guia(codigo_guia):
    """
    Obtiene los datos de un pesaje bruto por su código de guía.
    
    Args:
        codigo_guia (str): Código de guía del pesaje a buscar
        
    Returns:
        dict: Datos del pesaje bruto o None si no se encuentra
    """
    try:
        # Utilizamos db_operations para obtener el pesaje
        import db_operations
        
        # Obtener el pesaje bruto utilizando la función existente en db_operations
        pesaje = db_operations.get_pesaje_bruto_by_codigo_guia(codigo_guia)
        
        if pesaje:
            logger.info(f"Pesaje bruto encontrado para guía: {codigo_guia}")
            return pesaje
        else:
            logger.warning(f"No se encontró pesaje bruto para guía: {codigo_guia}")
            
            # Si no se encuentra en la base de datos, buscar en registros de entrada
            # y complementar con datos básicos
            entry_record = get_entry_record_by_guide_code(codigo_guia)
            if entry_record:
                logger.info(f"Se encontró registro de entrada para la guía: {codigo_guia}")
                # Convertir a un formato compatible con pesaje bruto
                datos_basicos = {
                    'codigo_guia': codigo_guia,
                    'codigo_proveedor': entry_record.get('codigo_proveedor', ''),
                    'nombre_proveedor': entry_record.get('nombre_proveedor', ''),
                    'placa': entry_record.get('placa', ''),
                    'transportador': entry_record.get('transportador', ''),
                    'racimos': entry_record.get('cantidad_racimos', ''),
                    'acarreo': entry_record.get('acarreo', 'NO'),
                    'cargo': entry_record.get('cargo', 'NO'),
                    'timestamp_registro_utc': entry_record.get('timestamp_registro_utc', ''),
                    'estado_actual': 'pendiente'
                }
                return datos_basicos
            return None
    except Exception as e:
        logger.error(f"Error en get_pesaje_bruto_by_codigo_guia: {e}")
        return None

def get_entry_records_by_provider_code(codigo_proveedor):
    """
    Obtiene todos los registros de entrada para un código de proveedor específico,
    ordenados por fecha de creación descendente (más reciente primero)
    
    Args:
        codigo_proveedor (str): Código del proveedor a buscar
        
    Returns:
        list: Lista de diccionarios con los registros de entrada encontrados
    """
    conn = None
    try:
        # Get DB path from app config
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        # Verificar si existe la tabla
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
        if not c.fetchone():
            logger.warning(f"No existe la tabla entry_records para buscar registros del proveedor {codigo_proveedor}")
            return []
        
        # Consultar registros - Sólo buscar por codigo_proveedor (el campo codigo no existe)
        c.execute("""
            SELECT * FROM entry_records 
            WHERE codigo_proveedor = ?
            ORDER BY fecha_creacion DESC, id DESC
        """, (codigo_proveedor,))
        
        records = []
        for row in c.fetchall():
            record = {}
            for key in row.keys():
                record[key] = row[key]
            records.append(record)
        
        conn.close()
        logger.info(f"Encontrados {len(records)} registros para el proveedor {codigo_proveedor}")
        return records
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return []
    except Exception as e:
        logger.error(f"Error al obtener registros para el proveedor {codigo_proveedor}: {str(e)}")
        logger.error(traceback.format_exc())
        return []
    finally:
        if conn:
            conn.close() 