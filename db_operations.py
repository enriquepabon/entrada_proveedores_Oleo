"""
Módulo para las operaciones CRUD de la base de datos.
Contiene funciones para guardar y recuperar datos de todas las tablas.
"""

import sqlite3
import os
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = 'tiquetes.db'

#-----------------------
# Operaciones para Pesajes Bruto
#-----------------------

def store_pesaje_bruto(pesaje_data):
    """
    Almacena un registro de pesaje bruto en la base de datos.
    
    Args:
        pesaje_data (dict): Diccionario con los datos del pesaje bruto
        
    Returns:
        bool: True si se almacenó correctamente, False en caso contrario
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar si ya existe un registro con este código_guia
        cursor.execute("SELECT id FROM pesajes_bruto WHERE codigo_guia = ?", 
                      (pesaje_data.get('codigo_guia'),))
        existing = cursor.fetchone()
        
        if existing:
            # Actualizar el registro existente
            update_cols = []
            params = []
            
            for key, value in pesaje_data.items():
                if key != 'codigo_guia':  # Excluir la clave primaria
                    update_cols.append(f"{key} = ?")
                    params.append(value)
            
            # Agregar el parámetro para WHERE
            params.append(pesaje_data.get('codigo_guia'))
            
            update_query = f"UPDATE pesajes_bruto SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            logger.info(f"Actualizado registro de pesaje bruto para guía: {pesaje_data.get('codigo_guia')}")
        else:
            # Insertar nuevo registro
            columns = ', '.join(pesaje_data.keys())
            placeholders = ', '.join(['?' for _ in pesaje_data])
            values = list(pesaje_data.values())
            
            insert_query = f"INSERT INTO pesajes_bruto ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, values)
            logger.info(f"Insertado nuevo registro de pesaje bruto para guía: {pesaje_data.get('codigo_guia')}")
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error almacenando registro de pesaje bruto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_pesajes_bruto(filtros=None):
    """
    Recupera los registros de pesajes brutos, opcionalmente filtrados.
    Consulta tanto database.db (primario) como tiquetes.db (secundario)
    y combina los resultados, priorizando database.db.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de pesajes brutos como diccionarios
    """
    try:
        # Definir bases de datos a consultar
        dbs = ['database.db', DB_PATH]
        todos_pesajes = []
        codigos_procesados = set()  # Para evitar duplicados
        
        for db_path in dbs:
            if not os.path.exists(db_path):
                logger.warning(f"Base de datos {db_path} no encontrada.")
                continue
                
            try:
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
                cursor = conn.cursor()
                
                # Verificar si existe la tabla entry_records
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
                entry_exists = cursor.fetchone() is not None
                
                # Si entry_records existe, obtener columnas
                entry_columns = []
                if entry_exists:
                    try:
                        cursor.execute("PRAGMA table_info(entry_records)")
                        entry_columns = [row['name'] for row in cursor.fetchall()]
                    except:
                        entry_exists = False
                
                # Verificar si existe la tabla pesajes_bruto
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
                pesajes_exists = cursor.fetchone() is not None
                
                if not pesajes_exists:
                    logger.warning(f"Tabla pesajes_bruto no encontrada en {db_path}.")
                    conn.close()
                    continue
                
                # Obtener columnas de pesajes_bruto
                cursor.execute("PRAGMA table_info(pesajes_bruto)")
                pesajes_columns = [row['name'] for row in cursor.fetchall()]
                
                # Crear lista de columnas para SELECT
                select_clause = []
                
                # Añadir columnas de pesajes_bruto
                for col in pesajes_columns:
                    select_clause.append(f"p.{col}")
                
                # Si entry_records existe, añadir JOIN con las columnas que existan
                if entry_exists:
                    join_clause = "LEFT JOIN entry_records e ON p.codigo_guia = e.codigo_guia"
                    
                    # Añadir columnas de entry_records si existen
                    if 'nombre_proveedor' in entry_columns:
                        select_clause.append("COALESCE(e.nombre_proveedor, p.nombre_proveedor) as nombre_proveedor")
                    
                    if 'codigo_proveedor' in entry_columns:
                        select_clause.append("COALESCE(e.codigo_proveedor, p.codigo_proveedor) as codigo_proveedor")
                        
                    if 'fecha_registro' in entry_columns:
                        select_clause.append("e.fecha_registro")
                    else:
                        select_clause.append("NULL as fecha_registro")
                        
                    if 'hora_registro' in entry_columns:
                        select_clause.append("e.hora_registro")
                    else:
                        select_clause.append("NULL as hora_registro")
                        
                    if 'acarreo' in entry_columns:
                        select_clause.append("e.acarreo")
                    else:
                        select_clause.append("'No' as acarreo")
                        
                    if 'cargo' in entry_columns:
                        select_clause.append("e.cargo")
                    else:
                        select_clause.append("'No' as cargo")
                        
                    if 'transportador' in entry_columns:
                        select_clause.append("e.transportador")
                    else:
                        select_clause.append("'No disponible' as transportador")
                    
                    # Añadir código guía transporte SAP si existe
                    if 'codigo_guia_transporte_sap' in entry_columns:
                        select_clause.append("e.codigo_guia_transporte_sap")
                    elif 'codigo_guia_transporte_sap' in pesajes_columns:
                        select_clause.append("p.codigo_guia_transporte_sap")
                    else:
                        select_clause.append("NULL as codigo_guia_transporte_sap")
                else:
                    join_clause = ""
                    # Añadir valores por defecto si entry_records no existe
                    select_clause.extend([
                        "NULL as fecha_registro",
                        "NULL as hora_registro",
                        "'No' as acarreo",
                        "'No' as cargo",
                        "'No disponible' as transportador",
                        "NULL as codigo_guia_transporte_sap"
                    ])
                
                # Construir la consulta completa
                query = f"""
                SELECT 
                    {', '.join(select_clause)}
                FROM 
                    pesajes_bruto p
                """
                
                if entry_exists:
                    query += f"\n{join_clause}"
                
                params = []
                
                # Aplicar filtros si se proporcionan
                if filtros:
                    conditions = []
                    
                    if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                        # Convertir fechas a formato comparable
                        try:
                            fecha_desde = datetime.strptime(filtros['fecha_desde'], '%Y-%m-%d').strftime('%d/%m/%Y')
                            fecha_hasta = datetime.strptime(filtros['fecha_hasta'], '%Y-%m-%d').strftime('%d/%m/%Y')
                            
                            # Para simplificar, usamos BETWEEN en SQLite aunque no sea perfecto para fechas
                            conditions.append("p.fecha_pesaje BETWEEN ? AND ?")
                            params.extend([fecha_desde, fecha_hasta])
                        except:
                            # Si hay error al parsear, no filtrar por fecha
                            pass
                        
                    if filtros.get('codigo_proveedor'):
                        conditions.append("p.codigo_proveedor LIKE ?")
                        params.append(f"%{filtros['codigo_proveedor']}%")
                        
                    if filtros.get('nombre_proveedor'):
                        conditions.append("p.nombre_proveedor LIKE ?")
                        params.append(f"%{filtros['nombre_proveedor']}%")
                        
                    if filtros.get('tipo_pesaje'):
                        conditions.append("p.tipo_pesaje = ?")
                        params.append(filtros['tipo_pesaje'])
                    
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                
                # Ejecutar la consulta sin ordenación para obtener todos los registros
                try:
                    cursor.execute(query, params)
                    
                    # Convertir filas a diccionarios
                    for row in cursor.fetchall():
                        pesaje = {key: row[key] for key in row.keys()}
                        
                        # Asegurarse de que los campos importantes tengan valores predeterminados si están vacíos
                        if not pesaje.get('fecha_registro'):
                            pesaje['fecha_registro'] = pesaje.get('fecha_pesaje', 'No disponible')
                            
                        if not pesaje.get('hora_registro'):
                            pesaje['hora_registro'] = pesaje.get('hora_pesaje', 'No disponible')
                            
                        if not pesaje.get('acarreo'):
                            pesaje['acarreo'] = 'No' 
                            
                        if not pesaje.get('cargo'):
                            pesaje['cargo'] = 'No'
                        
                        # Verificar si el nombre del proveedor es None o 'None' o está vacío
                        if pesaje.get('nombre_proveedor') is None or pesaje.get('nombre_proveedor') == 'None' or pesaje.get('nombre_proveedor') == '':
                            # Intentar obtener el nombre del proveedor del código de guía
                            if pesaje.get('codigo_guia') and '_' in pesaje.get('codigo_guia'):
                                codigo_proveedor = pesaje.get('codigo_guia').split('_')[0]
                                pesaje['codigo_proveedor'] = codigo_proveedor
                                # Buscar en entry_records el nombre asociado con este código
                                try:
                                    if entry_exists:
                                        cursor.execute("SELECT nombre_proveedor FROM entry_records WHERE codigo_proveedor = ? LIMIT 1", (codigo_proveedor,))
                                        result = cursor.fetchone()
                                        if result and result['nombre_proveedor']:
                                            pesaje['nombre_proveedor'] = result['nombre_proveedor']
                                        else:
                                            pesaje['nombre_proveedor'] = 'No disponible'
                                    else:
                                        pesaje['nombre_proveedor'] = 'No disponible'
                                except:
                                    pesaje['nombre_proveedor'] = 'No disponible'
                            else:
                                pesaje['nombre_proveedor'] = 'No disponible'
                        
                        # Verificar si el transportador es None o 'None' o está vacío
                        if pesaje.get('transportador') is None or pesaje.get('transportador') == 'None' or pesaje.get('transportador') == '':
                            # Intentar obtener el transportador del registro de entrada
                            try:
                                if entry_exists and pesaje.get('codigo_guia'):
                                    cursor.execute("SELECT transportador FROM entry_records WHERE codigo_guia = ?", (pesaje.get('codigo_guia'),))
                                    result = cursor.fetchone()
                                    if result and result['transportador'] and result['transportador'] != 'None':
                                        pesaje['transportador'] = result['transportador']
                                    else:
                                        pesaje['transportador'] = 'No disponible'
                                else:
                                    pesaje['transportador'] = 'No disponible'
                            except:
                                pesaje['transportador'] = 'No disponible'
                            
                        if not pesaje.get('codigo_guia_transporte_sap'):
                            pesaje['codigo_guia_transporte_sap'] = 'No disponible'
                        
                        # Añadir solo si no se ha procesado previamente este código_guia
                        codigo_guia = pesaje.get('codigo_guia')
                        if codigo_guia and codigo_guia not in codigos_procesados:
                            todos_pesajes.append(pesaje)
                            codigos_procesados.add(codigo_guia)
                except sqlite3.Error as e:
                    logger.error(f"Error ejecutando consulta en {db_path}: {e}")
                    logger.error(f"Query que causó el error: {query}")
                
                conn.close()
                
            except sqlite3.Error as e:
                logger.error(f"Error consultando {db_path}: {e}")
                if conn:
                    conn.close()
        
        # Si no se encontraron registros, devolver lista vacía
        if not todos_pesajes:
            return []
        
        # Función para convertir fecha y hora en un objeto datetime
        def parse_datetime_str(pesaje):
            try:
                # Parsear fecha en formato DD/MM/YYYY y hora en formato HH:MM:SS
                date_str = pesaje.get('fecha_pesaje', '01/01/1970')
                time_str = pesaje.get('hora_pesaje', '00:00:00')
                
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
                logger.error(f"Error parsing date/time for pesaje: {e}")
                return datetime(1970, 1, 1)  # Fallback to oldest date
        
        # Ordenar por fecha y hora parseadas en orden descendente (más recientes primero)
        todos_pesajes.sort(key=parse_datetime_str, reverse=True)
        
        return todos_pesajes
    except Exception as e:
        logger.error(f"Error general recuperando registros de pesajes brutos: {e}")
        return []

def get_pesaje_bruto_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de pesaje bruto específico por su código de guía.
    Consulta tanto database.db (primario) como tiquetes.db (secundario).
    
    Args:
        codigo_guia (str): El código de guía a buscar
        
    Returns:
        dict: El registro de pesaje bruto como diccionario, o None si no se encuentra
    """
    # Definir bases de datos a consultar
    dbs = ['database.db', DB_PATH]
    
    for db_path in dbs:
        if not os.path.exists(db_path):
            logger.warning(f"Base de datos {db_path} no encontrada.")
            continue
            
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Verificar si las tablas existen
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
            if not cursor.fetchone():
                logger.warning(f"La tabla pesajes_bruto no existe en {db_path}")
                conn.close()
                continue
            
            # Verificar si entry_records existe
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
            entry_exists = cursor.fetchone() is not None
            
            # Obtener información sobre la estructura de las tablas
            pesajes_columns = []
            entry_columns = []
            
            # Obtener columnas de pesajes_bruto
            try:
                cursor.execute("PRAGMA table_info(pesajes_bruto)")
                pesajes_columns = [row[1] for row in cursor.fetchall()]
            except sqlite3.Error:
                logger.warning(f"No se pudo obtener información de la tabla pesajes_bruto en {db_path}")
            
            # Obtener columnas de entry_records si existe
            if entry_exists:
                try:
                    cursor.execute("PRAGMA table_info(entry_records)")
                    entry_columns = [row[1] for row in cursor.fetchall()]
                except sqlite3.Error:
                    logger.warning(f"No se pudo obtener información de la tabla entry_records en {db_path}")
            
            # Construir consulta para pesajes_bruto
            query = f"SELECT p.*, e.image_filename FROM pesajes_bruto p LEFT JOIN entry_records e ON p.codigo_guia = e.codigo_guia WHERE p.codigo_guia = ?"
            cursor.execute(query, (codigo_guia,))
            row = cursor.fetchone()
            
            if row:
                pesaje = dict(row)
                logger.info(f"Encontrado pesaje bruto para {codigo_guia} en {db_path}")
                
                # Normalizar el campo código de guía de transporte SAP si existe
                if 'codigo_guia_transporte_sap' in pesaje and pesaje['codigo_guia_transporte_sap']:
                    logger.info(f"Guía de transporte SAP encontrada para {codigo_guia}: {pesaje['codigo_guia_transporte_sap']}")
                else:
                    pesaje['codigo_guia_transporte_sap'] = 'No registrada'
                
                # Si encontramos resultados en esta base de datos, cerramos la conexión y retornamos
                conn.close()
                return pesaje
            
            # Si no encontramos en pesajes_bruto, buscar información en entry_records si existe
            if entry_exists:
                cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
                row = cursor.fetchone()
                
                if row:
                    # Crear un pesaje básico desde entry_records
                    entry = dict(row)
                    logger.info(f"Encontrado registro de entrada para {codigo_guia} en {db_path}")
                    
                    # Mapear campos relevantes
                    peso_basico = {
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': entry.get('codigo_proveedor', ''),
                        'nombre_proveedor': entry.get('nombre_proveedor', ''),
                        'peso_bruto': 'Pendiente',
                        'tipo_pesaje': 'pendiente',
                        'fecha_pesaje': '',
                        'hora_pesaje': '',
                        'codigo_guia_transporte_sap': entry.get('codigo_guia_transporte_sap', 'No registrada'),
                        'estado': 'pendiente',
                        'image_filename': entry.get('image_filename', '')  # Incluir el nombre del archivo de imagen
                    }
                    
                    conn.close()
                    return peso_basico
            
            conn.close()
            
        except sqlite3.Error as e:
            logger.error(f"Error consultando {db_path}: {e}")
            if 'conn' in locals():
                conn.close()
    
    # Si no se encontró en ninguna base de datos, retornar None
    logger.warning(f"No se encontró pesaje bruto para {codigo_guia}")
    return None

def update_pesaje_bruto(codigo_guia, datos_pesaje):
    """
    Actualiza un registro de pesaje bruto existente con datos adicionales.
    
    Args:
        codigo_guia (str): Código de guía del registro a actualizar
        datos_pesaje (dict): Diccionario con los campos a actualizar
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar si existe el registro
        cursor.execute("SELECT id FROM pesajes_bruto WHERE codigo_guia = ?", 
                      (codigo_guia,))
        existing = cursor.fetchone()
        
        if existing:
            # Construir la consulta de actualización
            update_cols = []
            params = []
            
            for key, value in datos_pesaje.items():
                update_cols.append(f"{key} = ?")
                params.append(value)
            
            # Agregar el parámetro para WHERE
            params.append(codigo_guia)
            
            update_query = f"UPDATE pesajes_bruto SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            
            conn.commit()
            logger.info(f"Actualizado registro de pesaje bruto para guía: {codigo_guia}")
            return True
        else:
            logger.warning(f"No se encontró registro de pesaje bruto para actualizar: {codigo_guia}")
            return False
    except sqlite3.Error as e:
        logger.error(f"Error actualizando registro de pesaje bruto: {e}")
        return False
    finally:
        if conn:
            conn.close()

#-----------------------
# Operaciones para Clasificaciones
#-----------------------

def store_clasificacion(clasificacion_data, fotos=None):
    """
    Almacena un registro de clasificación y sus fotos asociadas en la base de datos.
    
    Args:
        clasificacion_data (dict): Diccionario con los datos de la clasificación
        fotos (list, optional): Lista de rutas a las fotos de la clasificación
        
    Returns:
        bool: True si se almacenó correctamente, False en caso contrario
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Preparar datos de clasificación manual y automática
        datos_a_guardar = {
            'codigo_guia': clasificacion_data.get('codigo_guia'),
            'codigo_proveedor': clasificacion_data.get('codigo_proveedor'),
            'nombre_proveedor': clasificacion_data.get('nombre_proveedor'),
            'fecha_clasificacion': clasificacion_data.get('fecha_clasificacion'),
            'hora_clasificacion': clasificacion_data.get('hora_clasificacion'),
            'observaciones': clasificacion_data.get('observaciones'),
            'estado': clasificacion_data.get('estado', 'activo')
        }
        
        # Procesar clasificación manual
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        if isinstance(clasificacion_manual, str):
            try:
                clasificacion_manual = json.loads(clasificacion_manual)
            except json.JSONDecodeError:
                clasificacion_manual = {}
        
        # También procesar campo clasificaciones por compatibilidad
        clasificaciones = clasificacion_data.get('clasificaciones', {})
        if isinstance(clasificaciones, str):
            try:
                clasificaciones = json.loads(clasificaciones)
            except json.JSONDecodeError:
                clasificaciones = {}
                
        # Si clasificacion_manual está vacío pero clasificaciones tiene datos, usarlos
        if not clasificacion_manual and clasificaciones:
            clasificacion_manual = clasificaciones
            logger.info(f"Usando datos de 'clasificaciones' como 'clasificacion_manual' para {clasificacion_data.get('codigo_guia')}")
        
        # Procesar clasificación automática
        clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
        if isinstance(clasificacion_automatica, str):
            try:
                clasificacion_automatica = json.loads(clasificacion_automatica)
            except json.JSONDecodeError:
                clasificacion_automatica = {}
        
        # Guardar las clasificaciones como JSON
        datos_a_guardar['clasificacion_manual'] = json.dumps(clasificacion_manual)
        datos_a_guardar['clasificacion_automatica'] = json.dumps(clasificacion_automatica)
        
        # Construir la consulta SQL
        campos = ', '.join(datos_a_guardar.keys())
        placeholders = ', '.join(['?' for _ in datos_a_guardar])
        valores = list(datos_a_guardar.values())
        
        # Intentar insertar primero
        try:
            cursor.execute(f"""
                INSERT INTO clasificaciones ({campos})
                VALUES ({placeholders})
            """, valores)
        except sqlite3.IntegrityError:
            # Si ya existe, actualizar
            set_clause = ', '.join([f"{k} = ?" for k in datos_a_guardar.keys()])
            cursor.execute(f"""
                UPDATE clasificaciones
                SET {set_clause}
                WHERE codigo_guia = ?
            """, valores + [datos_a_guardar['codigo_guia']])
        
        conn.commit()
        
        # Si hay fotos, guardarlas
        if fotos:
            for i, foto_path in enumerate(fotos):
                cursor.execute("""
                    INSERT INTO fotos_clasificacion (codigo_guia, ruta_foto, numero_foto)
                    VALUES (?, ?, ?)
                """, (datos_a_guardar['codigo_guia'], foto_path, i + 1))
            conn.commit()
        
        return True
    except Exception as e:
        logger.error(f"Error en store_clasificacion: {str(e)}")
        return False
    finally:
        if conn:
            conn.close()

def get_clasificaciones(filtros=None):
    """
    Recupera los registros de clasificaciones, opcionalmente filtrados.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de clasificaciones como diccionarios
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM clasificaciones"
        params = []
        
        # Aplicar filtros si se proporcionan
        if filtros:
            conditions = []
            
            if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                # Convertir fechas a formato comparable
                try:
                    fecha_desde = datetime.strptime(filtros['fecha_desde'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    fecha_hasta = datetime.strptime(filtros['fecha_hasta'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    
                    conditions.append("fecha_registro BETWEEN ? AND ?")
                    params.extend([fecha_desde, fecha_hasta])
                except:
                    # Si hay error al parsear, no filtrar por fecha
                    pass
                
            if filtros.get('codigo_proveedor'):
                conditions.append("codigo_proveedor LIKE ?")
                params.append(f"%{filtros['codigo_proveedor']}%")
                
            if filtros.get('nombre_proveedor'):
                conditions.append("nombre_proveedor LIKE ?")
                params.append(f"%{filtros['nombre_proveedor']}%")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        # Ordenar por fecha y hora más reciente
        query += " ORDER BY fecha_registro DESC, hora_registro DESC"
        
        cursor.execute(query, params)
        
        # Convertir filas a diccionarios
        clasificaciones = []
        for row in cursor.fetchall():
            clasificacion = {key: row[key] for key in row.keys()}
            
            # Obtener fotos asociadas
            cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", 
                         (clasificacion['codigo_guia'],))
            fotos = [row[0] for row in cursor.fetchall()]
            clasificacion['fotos'] = fotos
            
            clasificaciones.append(clasificacion)
        
        return clasificaciones
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registros de clasificaciones: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_clasificacion_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de clasificación por su código de guía.
    
    Args:
        codigo_guia (str): Código de guía a buscar
        
    Returns:
        dict: Datos de la clasificación o None si no se encuentra
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            clasificacion = {key: row[key] for key in row.keys()}
            
            # Obtener fotos asociadas
            cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", 
                         (codigo_guia,))
            fotos = [row[0] for row in cursor.fetchall()]
            clasificacion['fotos'] = fotos
            
            # Si clasificaciones es una cadena JSON, convertirla a lista
            if isinstance(clasificacion.get('clasificaciones'), str):
                try:
                    clasificacion['clasificaciones'] = json.loads(clasificacion['clasificaciones'])
                except json.JSONDecodeError:
                    clasificacion['clasificaciones'] = []
            
            # Si clasificacion_automatica es una cadena JSON, convertirla a diccionario
            if isinstance(clasificacion.get('clasificacion_automatica'), str):
                try:
                    clasificacion['clasificacion_automatica'] = json.loads(clasificacion['clasificacion_automatica'])
                except json.JSONDecodeError:
                    pass
                    
            return clasificacion
        return None
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registro de clasificación por código de guía: {e}")
        return None
    finally:
        if conn:
            conn.close()

#-----------------------
# Operaciones para Pesajes Neto
#-----------------------

def store_pesaje_neto(pesaje_data):
    """
    Almacena un registro de pesaje neto en la base de datos.
    
    Args:
        pesaje_data (dict): Diccionario con los datos del pesaje neto
        
    Returns:
        bool: True si se almacenó correctamente, False en caso contrario
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar si ya existe un registro con este código_guia
        cursor.execute("SELECT id FROM pesajes_neto WHERE codigo_guia = ?", 
                      (pesaje_data.get('codigo_guia'),))
        existing = cursor.fetchone()
        
        if existing:
            # Actualizar el registro existente
            update_cols = []
            params = []
            
            for key, value in pesaje_data.items():
                if key != 'codigo_guia':  # Excluir la clave primaria
                    update_cols.append(f"{key} = ?")
                    params.append(value)
            
            # Agregar el parámetro para WHERE
            params.append(pesaje_data.get('codigo_guia'))
            
            update_query = f"UPDATE pesajes_neto SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            logger.info(f"Actualizado registro de pesaje neto para guía: {pesaje_data.get('codigo_guia')}")
        else:
            # Insertar nuevo registro
            columns = ', '.join(pesaje_data.keys())
            placeholders = ', '.join(['?' for _ in pesaje_data])
            values = list(pesaje_data.values())
            
            insert_query = f"INSERT INTO pesajes_neto ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, values)
            logger.info(f"Insertado nuevo registro de pesaje neto para guía: {pesaje_data.get('codigo_guia')}")
        
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error almacenando registro de pesaje neto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_pesajes_neto(filtros=None):
    """
    Recupera los registros de pesajes netos, opcionalmente filtrados.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de pesajes netos como diccionarios
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # Permite acceso por nombre de columna
        cursor = conn.cursor()
        
        query = "SELECT * FROM pesajes_neto"
        params = []
        
        # Aplicar filtros si se proporcionan
        if filtros:
            conditions = []
            
            if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                # Convertir fechas a formato comparable
                try:
                    fecha_desde = datetime.strptime(filtros['fecha_desde'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    fecha_hasta = datetime.strptime(filtros['fecha_hasta'], '%Y-%m-%d').strftime('%d/%m/%Y')
                    
                    # Para simplificar, usamos BETWEEN en SQLite aunque no sea perfecto para fechas
                    conditions.append("fecha_pesaje BETWEEN ? AND ?")
                    params.extend([fecha_desde, fecha_hasta])
                except:
                    # Si hay error al parsear, no filtrar por fecha
                    pass
                
            if filtros.get('codigo_guia'):
                conditions.append("codigo_guia LIKE ?")
                params.append(f"%{filtros['codigo_guia']}%")
                
            if filtros.get('codigo_proveedor'):
                conditions.append("codigo_proveedor LIKE ?")
                params.append(f"%{filtros['codigo_proveedor']}%")
                
            if filtros.get('nombre_proveedor'):
                conditions.append("nombre_proveedor LIKE ?")
                params.append(f"%{filtros['nombre_proveedor']}%")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        # Ejecutar la consulta sin ordenación para obtener todos los registros
        cursor.execute(query, params)
        
        # Convertir filas a diccionarios
        pesajes = []
        for row in cursor.fetchall():
            pesaje = {key: row[key] for key in row.keys()}
            pesajes.append(pesaje)
        
        # Función para convertir fecha y hora en un objeto datetime
        def parse_datetime_str(pesaje):
            try:
                # Parsear fecha en formato DD/MM/YYYY y hora en formato HH:MM:SS
                date_str = pesaje.get('fecha_pesaje_neto', pesaje.get('fecha_pesaje', '01/01/1970'))
                time_str = pesaje.get('hora_pesaje_neto', pesaje.get('hora_pesaje', '00:00:00'))
                
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
                logger.error(f"Error parsing date/time for pesaje neto: {e}")
                return datetime(1970, 1, 1)  # Fallback to oldest date
        
        # Ordenar por fecha y hora parseadas en orden descendente (más recientes primero)
        pesajes.sort(key=parse_datetime_str, reverse=True)
        
        return pesajes
    except sqlite3.Error as e:
        logger.error(f"Recuperando registros de pesajes netos: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_pesaje_neto_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de pesaje neto específico por su código de guía.
    
    Args:
        codigo_guia (str): El código de guía a buscar
        
    Returns:
        dict: El registro de pesaje neto como diccionario, o None si no se encuentra
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            pesaje = {key: row[key] for key in row.keys()}
            return pesaje
        return None
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registro de pesaje neto por código de guía: {e}")
        return None
    finally:
        if conn:
            conn.close()

# Inicializar la base de datos
def init_db():
    """
    Inicializa la base de datos importando el esquema.
    """
    try:
        import db_schema
        db_schema.create_tables()
        return True
    except ImportError:
        logger.error("No se pudo importar el módulo db_schema")
        return False
    except Exception as e:
        logger.error(f"Error inicializando la base de datos: {e}")
        return False

def get_provider_by_code(codigo_proveedor, codigo_guia_actual=None):
    """
    Busca información de un proveedor por su código en las tablas disponibles.
    Primero busca en la tabla de proveedores si existe, luego en entry_records.
    
    Args:
        codigo_proveedor (str): Código del proveedor a buscar
        codigo_guia_actual (str, optional): Código de guía actual para evitar mezclar datos de diferentes entregas
        
    Returns:
        dict: Datos del proveedor o None si no se encuentra
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verificar si existe tabla de proveedores
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proveedores'")
        if cursor.fetchone():
            # Buscar en tabla de proveedores
            cursor.execute("SELECT * FROM proveedores WHERE codigo = ?", (codigo_proveedor,))
            row = cursor.fetchone()
            
            if row:
                proveedor = {key: row[key] for key in row.keys()}
                proveedor['es_dato_otra_entrega'] = False  # Datos de tabla maestra, no de otra entrega
                logger.info(f"Proveedor encontrado en tabla proveedores: {codigo_proveedor}")
                return proveedor
        
        # Si se proporcionó un código de guía actual, buscar primero en entry_records para este código
        if codigo_guia_actual:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
            if cursor.fetchone():
                cursor.execute(
                    "SELECT * FROM entry_records WHERE codigo_guia = ? LIMIT 1",
                    (codigo_guia_actual,)
                )
                row = cursor.fetchone()
                
                if row:
                    proveedor = {key: row[key] for key in row.keys()}
                    proveedor['codigo'] = proveedor.get('codigo_proveedor')
                    proveedor['nombre'] = proveedor.get('nombre_proveedor')
                    proveedor['es_dato_otra_entrega'] = False  # Datos del mismo registro
                    logger.info(f"Proveedor encontrado en entry_records para el mismo código de guía: {codigo_guia_actual}")
                    return proveedor
        
        # Si no se encuentra en tabla de proveedores, buscar en entry_records para otras entregas
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
        if cursor.fetchone():
            # Buscar en entry_records el registro más reciente para ese proveedor
            cursor.execute(
                "SELECT * FROM entry_records WHERE codigo_proveedor = ? ORDER BY created_at DESC LIMIT 1",
                (codigo_proveedor,)
            )
            row = cursor.fetchone()
            
            if row:
                proveedor = {key: row[key] for key in row.keys()}
                proveedor['codigo'] = proveedor.get('codigo_proveedor')
                proveedor['nombre'] = proveedor.get('nombre_proveedor')
                
                # Marcar si es de otra entrega
                if codigo_guia_actual and proveedor.get('codigo_guia') != codigo_guia_actual:
                    proveedor['es_dato_otra_entrega'] = True
                    logger.warning(f"Proveedor encontrado en otra entrada (código guía: {proveedor.get('codigo_guia')})")
                else:
                    proveedor['es_dato_otra_entrega'] = False
                
                logger.info(f"Proveedor encontrado en entry_records: {codigo_proveedor}")
                return proveedor
        
        # Si aún no se encuentra, buscar en otras tablas que puedan tener info de proveedores
        tables_to_check = ['pesajes_bruto', 'clasificaciones', 'pesajes_neto']
        for table in tables_to_check:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if cursor.fetchone():
                # Verificar si la tabla tiene las columnas necesarias
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'codigo_proveedor' in columns:
                    # Si hay un código de guía actual, buscar primero para este código específico
                    if codigo_guia_actual and 'codigo_guia' in columns:
                        query = f"SELECT * FROM {table} WHERE codigo_guia = ? LIMIT 1"
                        cursor.execute(query, (codigo_guia_actual,))
                        row = cursor.fetchone()
                        
                        if row and row['codigo_proveedor'] == codigo_proveedor:
                            proveedor = {key: row[key] for key in row.keys()}
                            proveedor['codigo'] = proveedor.get('codigo_proveedor')
                            proveedor['nombre'] = proveedor.get('nombre_proveedor')
                            proveedor['es_dato_otra_entrega'] = False  # Datos del mismo registro
                            logger.info(f"Proveedor encontrado en {table} para el mismo código de guía: {codigo_guia_actual}")
                            return proveedor
                    
                    # Luego buscar por código de proveedor si no encontramos para este código de guía
                    query = f"SELECT * FROM {table} WHERE codigo_proveedor = ? LIMIT 1"
                    cursor.execute(query, (codigo_proveedor,))
                    row = cursor.fetchone()
                    
                    if row:
                        proveedor = {key: row[key] for key in row.keys()}
                        proveedor['codigo'] = proveedor.get('codigo_proveedor')
                        proveedor['nombre'] = proveedor.get('nombre_proveedor')
                        
                        # Marcar si es de otra entrega
                        if codigo_guia_actual and 'codigo_guia' in columns and proveedor.get('codigo_guia') != codigo_guia_actual:
                            proveedor['es_dato_otra_entrega'] = True
                            logger.warning(f"Datos encontrados en {table} de otra entrada (código guía: {proveedor.get('codigo_guia')})")
                        else:
                            proveedor['es_dato_otra_entrega'] = False
                        
                        logger.info(f"Proveedor encontrado en {table}: {codigo_proveedor}")
                        return proveedor
        
        logger.warning(f"No se encontró información del proveedor: {codigo_proveedor}")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error buscando proveedor por código: {e}")
        return None
    finally:
        if conn:
            conn.close() 