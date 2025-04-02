import sqlite3
import os
import logging
from datetime import datetime
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'tiquetes.db'

def init_db():
    """Initialize the database and create tables if they don't exist."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create entries table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS entry_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_guia TEXT UNIQUE,
            codigo_proveedor TEXT,
            nombre_proveedor TEXT,
            cantidad_racimos TEXT,
            placa TEXT,
            acarreo TEXT,
            cargo TEXT,
            transportador TEXT,
            fecha_tiquete TEXT,
            fecha_registro TEXT,
            hora_registro TEXT,
            image_filename TEXT,
            plate_image_filename TEXT,
            plate_text TEXT,
            nota TEXT,
            pdf_filename TEXT,
            qr_filename TEXT,
            modified_fields TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        return True
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        return False
    finally:
        if conn:
            conn.close()

def store_entry_record(record_data):
    """
    Store an entry record in the database.
    
    Args:
        record_data (dict): Dictionary containing the entry record data
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        codigo_guia = record_data.get('codigo_guia')
        codigo_proveedor = record_data.get('codigo_proveedor', '')
        
        if not codigo_guia:
            logger.error("No se puede guardar un registro sin código de guía")
            return False
            
        # Verificar posibles duplicados en registros recientes (últimos 10 minutos)
        cursor.execute(
            "SELECT codigo_guia, nombre_proveedor, created_at FROM entry_records " + 
            "WHERE codigo_proveedor = ? AND created_at > datetime('now', '-10 minutes')",
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
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # This enables column access by name
        cursor = conn.cursor()
        
        query = "SELECT * FROM entry_records"
        params = []
        
        # Apply filters if provided
        if filters:
            conditions = []
            
            if filters.get('fecha_desde'):
                conditions.append("fecha_registro >= ?")
                params.append(filters['fecha_desde'])
                
            if filters.get('fecha_hasta'):
                conditions.append("fecha_registro <= ?")
                params.append(filters['fecha_hasta'])
                
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
            # Lista de campos críticos que deben tener un valor
            campos_criticos = [
                'codigo_proveedor', 'nombre_proveedor', 'placa', 
                'cantidad_racimos', 'transportador', 'acarreo', 'cargo'
            ]
            
            # Asignar "No disponible" a campos críticos vacíos
            for campo in campos_criticos:
                if campo not in record or record[campo] is None or record[campo] == '':
                    record[campo] = 'No disponible'
            
            # Verificar otros campos importantes
            if not record.get('fecha_registro'):
                record['fecha_registro'] = '01/01/1970'
            
            if not record.get('hora_registro'):
                record['hora_registro'] = '00:00:00'
                
            # Procesar el código del proveedor para asegurar el formato correcto
            if record.get('codigo_proveedor') and record['codigo_proveedor'] != 'No disponible':
                codigo_proveedor = record['codigo_proveedor']
                # Usar regex para encontrar dígitos seguidos opcionalmente por letras
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_proveedor)
                if match:
                    codigo_base = match.group(1)
                    # Si termina en letra, asegurar que sea A mayúscula
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'
            
            # Extraer código de proveedor desde codigo_guia si es necesario
            if (not record.get('codigo_proveedor') or record['codigo_proveedor'] == 'No disponible') and record.get('codigo_guia'):
                codigo_guia = record['codigo_guia']
                codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                
                # Usar regex para encontrar dígitos seguidos opcionalmente por letras
                import re
                match = re.match(r'(\d+[a-zA-Z]?)', codigo_base)
                if match:
                    codigo_base = match.group(1)
                    # Si termina en letra, asegurar que sea A mayúscula
                    if re.search(r'[a-zA-Z]$', codigo_base):
                        record['codigo_proveedor'] = codigo_base[:-1] + 'A'
                    else:
                        record['codigo_proveedor'] = codigo_base + 'A'
                
            records.append(record)
        
        # Sort records by proper date and time (convert strings to datetime objects)
        def parse_datetime_str(record):
            try:
                # Parse date in DD/MM/YYYY format and time in HH:MM:SS format
                date_str = record.get('fecha_registro', '01/01/1970')
                time_str = record.get('hora_registro', '00:00:00')
                
                if '/' in date_str:  # DD/MM/YYYY format
                    day, month, year = map(int, date_str.split('/'))
                    date_obj = datetime(year, month, day)
                else:  # Fallback to YYYY-MM-DD format
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                
                hours, minutes, seconds = map(int, time_str.split(':'))
                
                # Combine date and time
                return datetime(
                    date_obj.year, date_obj.month, date_obj.day,
                    hours, minutes, seconds
                )
            except Exception as e:
                logger.error(f"Error parsing date/time for record: {e}")
                return datetime(1970, 1, 1)  # Fallback to oldest date
        
        # Sort by parsed datetime in descending order (newest first)
        records.sort(key=parse_datetime_str, reverse=True)
        
        return records
    except sqlite3.Error as e:
        logger.error(f"Error retrieving entry records: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_entry_record_by_guide_code(codigo_guia):
    """
    Retrieve a specific entry record by its guide code.
    
    Args:
        codigo_guia (str): The guide code to search for
        
    Returns:
        dict: The entry record as a dictionary, or None if not found
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            record = {key: row[key] for key in row.keys()}
            
            # Parse modified_fields if it's stored as string
            if record.get('modified_fields') and isinstance(record['modified_fields'], str):
                try:
                    import json
                    record['modified_fields'] = json.loads(record['modified_fields'])
                except:
                    record['modified_fields'] = {}
            
            # Asegurar que campos críticos tengan valores predeterminados
            # Lista de campos críticos que deben tener un valor
            campos_criticos = [
                'codigo_proveedor', 'nombre_proveedor', 'placa', 
                'cantidad_racimos', 'transportador', 'acarreo', 'cargo'
            ]
            
            # Verificar y corregir campos importantes para la interfaz
            # Verificar si 'nombre_proveedor' está vacío pero 'nombre' o 'nombre_agricultor' tienen datos
            if record.get('nombre_proveedor') is None or record.get('nombre_proveedor') == '':
                # Intentar obtener de 'nombre_agricultor'
                if record.get('nombre_agricultor') and record.get('nombre_agricultor') != '':
                    record['nombre_proveedor'] = record['nombre_agricultor']
                # Si no, intentar obtener de 'nombre'
                elif record.get('nombre') and record.get('nombre') != '':
                    record['nombre_proveedor'] = record['nombre']
            
            # Verificar si 'cantidad_racimos' está vacío pero 'racimos' tiene datos
            if record.get('cantidad_racimos') is None or record.get('cantidad_racimos') == '' or record.get('cantidad_racimos') == 'N/A':
                if record.get('racimos') and record.get('racimos') != '' and record.get('racimos') != 'N/A':
                    record['cantidad_racimos'] = record['racimos']
                    logger.info(f"Campo cantidad_racimos actualizado desde racimos: {record['racimos']}")
            
            # También hacer la actualización inversa
            if record.get('racimos') is None or record.get('racimos') == '' or record.get('racimos') == 'N/A':
                if record.get('cantidad_racimos') and record.get('cantidad_racimos') != '' and record.get('cantidad_racimos') != 'N/A':
                    record['racimos'] = record['cantidad_racimos']
                    logger.info(f"Campo racimos actualizado desde cantidad_racimos: {record['cantidad_racimos']}")
            
            # Generar un código de transportista basado en el nombre si no existe
            if (not record.get('codigo_transportista') or record.get('codigo_transportista') == 'N/A') and record.get('transportador'):
                nombre_transportista = record.get('transportador')
                if nombre_transportista and isinstance(nombre_transportista, str):
                    # Extraer iniciales o primeras letras como un código básico
                    iniciales = ''.join([word[0].upper() for word in nombre_transportista.split() if word])
                    if iniciales:
                        record['codigo_transportista'] = f"T-{iniciales}"
                        logger.info(f"Código transportista generado para {codigo_guia}: {record['codigo_transportista']}")
            
            # Asignar "No disponible" a campos críticos vacíos
            for campo in campos_criticos:
                if campo not in record or record[campo] is None or record[campo] == '':
                    record[campo] = 'No disponible'
            
            # Verificar otros campos importantes
            if not record.get('fecha_registro'):
                record['fecha_registro'] = '01/01/1970'
            
            if not record.get('hora_registro'):
                record['hora_registro'] = '00:00:00'
            
            logger.info(f"Obtenido registro para guía {codigo_guia}: proveedor={record['nombre_proveedor']}, racimos={record['cantidad_racimos']}")
            return record
        return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving entry record by guide code: {e}")
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
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Buscar el registro más reciente por código de proveedor
        cursor.execute(
            "SELECT * FROM entry_records WHERE codigo_proveedor = ? ORDER BY created_at DESC LIMIT 1",
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
                    'fecha_registro': entry_record.get('fecha_registro', ''),
                    'hora_registro': entry_record.get('hora_registro', ''),
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
    try:
        conn = sqlite3.connect(DB_PATH)
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
    except Exception as e:
        logger.error(f"Error al obtener registros para el proveedor {codigo_proveedor}: {str(e)}")
        logger.error(traceback.format_exc())
        return []

# Initialize the database when this module is imported
init_db() 