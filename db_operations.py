"""
Módulo para las operaciones CRUD de la base de datos.
Contiene funciones para guardar y recuperar datos de todas las tablas.
"""

import sqlite3
import os
import logging
import json
from datetime import datetime
from flask import current_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
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
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
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
    conn_tq = None
    try:
        # Get DB paths from config
        db_path_secondary = current_app.config['TIQUETES_DB_PATH']
        
        # Process the single configured DB (tiquetes.db)
        if os.path.exists(db_path_secondary):
            try:
                conn_tq = sqlite3.connect(db_path_secondary)
                conn_tq.row_factory = sqlite3.Row
                cursor = conn_tq.cursor()
                
                # Similar query structure as above
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
                pesajes_exists = cursor.fetchone() is not None
                if pesajes_exists:
                    # Build and execute query for tiquetes.db
                    # Fetch results
                    query = "SELECT p.*, p.timestamp_pesaje_utc "
                    params = []
                    # Add JOINs and filters as needed (similar to original code)
                    # ... 
                    cursor.execute(query, params)
                    pesajes = []
                    for row in cursor.fetchall():
                        pesaje = {key: row[key] for key in row.keys()}
                        # Add default values, check providers, etc.
                        # ... (data cleaning/enrichment logic from original code) ...
                        codigo_guia = pesaje.get('codigo_guia')
                        if codigo_guia:
                            pesajes.append(pesaje)

            except sqlite3.Error as e:
                 logger.error(f"Error consultando {db_path_secondary}: {e}")
            finally:
                if conn_tq:
                    conn_tq.close()
        else:
            logger.warning(f"Base de datos {db_path_secondary} no encontrada.")
            
        # If no records found, return empty list
        if not pesajes:
            return []
        
        # Sort results directly by the timestamp string
        pesajes.sort(key=lambda p: p.get('timestamp_pesaje_utc', '1970-01-01 00:00:00'), reverse=True)
        
        return pesajes
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
    conn = None
    try:
        # Get DB paths from config
        db_path_secondary = current_app.config['TIQUETES_DB_PATH']
        
        # Process the single configured DB (tiquetes.db)
        if os.path.exists(db_path_secondary):
            try:
                conn = sqlite3.connect(db_path_secondary)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Verificar si las tablas existen
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
                pesajes_exists = cursor.fetchone() is not None
                
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
                entry_exists = cursor.fetchone() is not None
                
                # Query pesajes_bruto first
                if pesajes_exists:
                    query = "SELECT p.*, p.timestamp_pesaje_utc "
                    
                    # Conditionally add image_filename if entry_records exists
                    if entry_exists:
                         # Check if image_filename column exists in entry_records
                         cursor.execute("PRAGMA table_info(entry_records)")
                         entry_cols = {row[1] for row in cursor.fetchall()}
                         if 'image_filename' in entry_cols:
                             query += ", e.image_filename "
                         else: 
                             query += ", NULL as image_filename " # Add placeholder if column missing
                         query += "FROM pesajes_bruto p LEFT JOIN entry_records e ON p.codigo_guia = e.codigo_guia WHERE p.codigo_guia = ?"
                    else:
                         query += ", NULL as image_filename FROM pesajes_bruto p WHERE p.codigo_guia = ?" 
                         
                    cursor.execute(query, (codigo_guia,))
                    row = cursor.fetchone()
                    
                    if row:
                        pesaje = dict(row)
                        logger.info(f"Encontrado pesaje bruto para {codigo_guia} en {db_path_secondary}")
                        # Normalize SAP code
                        if 'codigo_guia_transporte_sap' not in pesaje or not pesaje['codigo_guia_transporte_sap']:
                             pesaje['codigo_guia_transporte_sap'] = 'No registrada'
                        conn.close()
                        return pesaje
                
                # If not found in pesajes_bruto, check entry_records if it exists
                if entry_exists:
                    cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
                    row = cursor.fetchone()
                    
                    if row:
                        entry = dict(row)
                        logger.info(f"Encontrado registro de entrada para {codigo_guia} en {db_path_secondary}")
                        peso_basico = {
                           # ... (mapping logic remains the same) ...
                            'codigo_guia': codigo_guia,
                            'codigo_proveedor': entry.get('codigo_proveedor', ''),
                            'nombre_proveedor': entry.get('nombre_proveedor', ''),
                            'peso_bruto': 'Pendiente',
                            'tipo_pesaje': 'pendiente',
                            'timestamp_registro_utc': entry.get('timestamp_registro_utc', ''),
                            'codigo_guia_transporte_sap': entry.get('codigo_guia_transporte_sap', 'No registrada'),
                            'estado': 'pendiente',
                            'image_filename': entry.get('image_filename', '')
                        }
                        conn.close()
                        return peso_basico
                
                # If not found in this DB, close connection and continue to next DB
                conn.close()
                conn = None # Reset conn for the next iteration or finally block
                
            except sqlite3.Error as e:
                logger.error(f"Error consultando {db_path_secondary}: {e}")
                if conn:
                    conn.close()
                    conn = None # Reset conn
        
        # If not found in any database
        logger.warning(f"No se encontró pesaje bruto para {codigo_guia}")
        return None

    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except Exception as e:
        logger.error(f"Error general en get_pesaje_bruto_by_codigo_guia: {e}")
        if conn: # Close connection if open due to general error
             conn.close()
        return None

def update_pesaje_bruto(codigo_guia, datos_pesaje):
    """
    Actualiza un registro de pesaje bruto existente con datos adicionales.
    Uses TIQUETES_DB_PATH for update.
    
    Args:
        codigo_guia (str): Código de guía del registro a actualizar
        datos_pesaje (dict): Diccionario con los campos a actualizar
        
    Returns:
        bool: True si se actualizó correctamente, False en caso contrario
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
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
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
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
# db_operations.py



def store_clasificacion(clasificacion_data, fotos=None):
    """
    Almacena un registro de clasificación y sus fotos asociadas en la base de datos.
    Uses TIQUETES_DB_PATH. CON LOGGING DETALLADO.
    """
    conn = None
    codigo_guia_logging = clasificacion_data.get('codigo_guia', 'UNKNOWN') # Para logs
    try:
        logger.info(f"--- store_clasificacion v2 INICIO para {codigo_guia_logging} ---")
        logger.debug(f"Datos recibidos: {clasificacion_data}")
        logger.debug(f"Fotos recibidas: {fotos}")

        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        # Asegurar que las claves foráneas estén habilitadas si usas relaciones
        # conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        datos_para_sql = clasificacion_data.copy()
        codigo_guia = datos_para_sql.get('codigo_guia')

        if not codigo_guia:
            logger.error("STORE_CLASIF: No se puede guardar sin 'codigo_guia'. Abortando.")
            return False

        # Quitar valores None ANTES de construir el SQL
        datos_finales = {k: v for k, v in datos_para_sql.items() if v is not None}
        logger.debug(f"STORE_CLASIF: Datos finales para SQL (sin None): {datos_finales}")

        # Check if record exists
        cursor.execute("SELECT id FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        existing = cursor.fetchone()
        logger.debug(f"STORE_CLASIF: Registro existente para {codigo_guia}? {'Sí' if existing else 'No'}")

        if existing:
            # UPDATE logic
            update_fields = {k: v for k, v in datos_finales.items() if k != 'codigo_guia'}
            if not update_fields:
                logger.warning(f"STORE_CLASIF: No hay campos para actualizar en clasificación existente {codigo_guia}.")
            else:
                set_clause = ', '.join([f"{k} = ?" for k in update_fields.keys()])
                valores = list(update_fields.values()) + [codigo_guia]
                update_query = f"UPDATE clasificaciones SET {set_clause} WHERE codigo_guia = ?"
                logger.info(f"STORE_CLASIF: Ejecutando UPDATE: {update_query}")
                logger.debug(f"STORE_CLASIF: Valores para UPDATE: {valores}")
                cursor.execute(update_query, valores)
                logger.info(f"STORE_CLASIF: UPDATE ejecutado para {codigo_guia}.")
        else:
            # INSERT logic
            if not datos_finales:
                 logger.error("STORE_CLASIF: No hay datos disponibles para insertar. Abortando.")
                 return False

            campos = ', '.join(datos_finales.keys())
            placeholders = ', '.join(['?' for _ in datos_finales])
            valores = list(datos_finales.values())
            insert_query = f"INSERT INTO clasificaciones ({campos}) VALUES ({placeholders})"
            logger.info(f"STORE_CLASIF: Ejecutando INSERT: {insert_query}")
            logger.debug(f"STORE_CLASIF: Valores para INSERT: {valores}")
            cursor.execute(insert_query, valores)
            logger.info(f"STORE_CLASIF: INSERT ejecutado para {codigo_guia}.")

        # Commit después de INSERT/UPDATE de clasificación
        conn.commit()
        logger.info(f"STORE_CLASIF: Commit realizado para tabla clasificaciones ({codigo_guia}).")


        # --- Guardar fotos si existen ---
        if fotos:
            logger.info(f"STORE_CLASIF: Procesando {len(fotos)} fotos para {codigo_guia}.")
            # Borrar fotos existentes
            logger.info(f"STORE_CLASIF: Borrando fotos existentes para {codigo_guia}...")
            try:
                cursor.execute("DELETE FROM fotos_clasificacion WHERE codigo_guia = ?", (codigo_guia,))
                logger.info(f"STORE_CLASIF: Fotos antiguas borradas ok para {codigo_guia}.")
            except sqlite3.Error as del_err:
                 # Loguear pero continuar, podría ser que la tabla no exista o esté vacía
                 logger.warning(f"STORE_CLASIF: Error (o tabla vacía?) borrando fotos antiguas para {codigo_guia}: {del_err}")

            # Insertar fotos nuevas
            fotos_insertadas_count = 0
            for i, foto_path in enumerate(fotos):
                if foto_path:
                    logger.debug(f"STORE_CLASIF: Insertando foto {i+1}: {foto_path}")
                    try:
                        cursor.execute("""
                            INSERT INTO fotos_clasificacion (codigo_guia, ruta_foto, numero_foto)
                            VALUES (?, ?, ?)
                        """, (codigo_guia, foto_path, i + 1))
                        fotos_insertadas_count += 1
                    except sqlite3.Error as insert_err:
                         # Loguear el error específico de la foto
                         logger.error(f"STORE_CLASIF: Error insertando foto {i+1} ({foto_path}) para {codigo_guia}: {insert_err}")
                         # Considerar si se debe devolver False aquí si una foto falla
                         # return False # Descomentar si el fallo al guardar UNA foto debe detener todo
                else:
                    logger.warning(f"STORE_CLASIF: Se omitió la foto {i+1} para {codigo_guia} (ruta vacía).")

            # Commit después de insertar todas las fotos
            conn.commit()
            logger.info(f"STORE_CLASIF: Commit realizado para tabla fotos_clasificacion ({codigo_guia}). {fotos_insertadas_count} fotos insertadas.")
        else:
             logger.info(f"STORE_CLASIF: No se proporcionaron fotos para guardar ({codigo_guia}).")

        logger.info(f"--- store_clasificacion v2 FIN ÉXITO para {codigo_guia_logging} ---")
        return True

    except KeyError as ke:
        logger.error(f"STORE_CLASIF: Error de configuración (KeyError) para {codigo_guia_logging}: {ke}", exc_info=True)
        return False
    except sqlite3.Error as db_err:
        # *** LOG DETALLADO DEL ERROR SQL ***
        logger.error(f"STORE_CLASIF: Error de Base de Datos (sqlite3.Error) para {codigo_guia_logging}: {db_err}", exc_info=True)
        # Loguear los datos que se intentaban guardar puede ser útil
        logger.error(f"STORE_CLASIF: Datos que se intentaban guardar: {datos_finales if 'datos_finales' in locals() else 'No disponibles'}")
        return False
    except Exception as e:
        logger.error(f"STORE_CLASIF: Error General (Exception) para {codigo_guia_logging}: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()
            logger.debug(f"STORE_CLASIF: Conexión a BD cerrada para {codigo_guia_logging}.")
        else:
            logger.debug(f"STORE_CLASIF: Conexión a BD no estaba abierta al finalizar ({codigo_guia_logging}).")

# ... (resto de funciones en db_operations.py) ...

def get_clasificaciones(filtros=None):
    """
    Recupera los registros de clasificaciones, opcionalmente filtrados.
    Uses TIQUETES_DB_PATH.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de clasificaciones como diccionarios
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM clasificaciones"
        params = []
        
        # Aplicar filtros si se proporcionan
        if filtros:
            conditions = []
            
            if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                try:
                    # No reformatear, usar YYYY-MM-DD directamente
                    fecha_desde = filtros['fecha_desde'] + ' 00:00:00'
                    fecha_hasta = filtros['fecha_hasta'] + ' 23:59:59'
                    
                    # Usar timestamp_clasificacion_utc para el rango
                    conditions.append("timestamp_clasificacion_utc BETWEEN ? AND ?")
                    params.extend([fecha_desde, fecha_hasta])
                except Exception as e: 
                    logger.warning(f"Error processing date filter values: {e}. Skipping date filter.")
                
            if filtros.get('codigo_proveedor'):
                conditions.append("codigo_proveedor LIKE ?")
                params.append(f"%{filtros['codigo_proveedor']}%")
                
            if filtros.get('nombre_proveedor'):
                conditions.append("nombre_proveedor LIKE ?")
                params.append(f"%{filtros['nombre_proveedor']}%")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
        
        # Ordenar por timestamp UTC más reciente
        query += " ORDER BY timestamp_clasificacion_utc DESC"
        
        cursor.execute(query, params)
        
        # Convertir filas a diccionarios
        clasificaciones = []
        for row in cursor.fetchall():
            clasificacion = {key: row[key] for key in row.keys()}
            
            # Obtener fotos asociadas
            # Use a separate cursor or fetch all data first to avoid issues
            with sqlite3.connect(db_path) as foto_conn:
                foto_cursor = foto_conn.cursor()
                foto_cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", 
                             (clasificacion['codigo_guia'],))
                fotos = [foto_row[0] for foto_row in foto_cursor.fetchall()]
                clasificacion['fotos'] = fotos
            
            clasificaciones.append(clasificacion)
        
        return clasificaciones
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return []
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registros de clasificaciones: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_clasificacion_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de clasificación por su código de guía.
    Uses TIQUETES_DB_PATH.
    
    Args:
        codigo_guia (str): Código de guía a buscar
        
    Returns:
        dict: Datos de la clasificación o None si no se encuentra
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            clasificacion = {key: row[key] for key in row.keys()}
            
            # Obtener fotos asociadas (using main connection cursor is fine here)
            logger.info(f"[DIAG][get_clasificacion] Buscando fotos para guía: {codigo_guia}")
            try:
                cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", 
                             (codigo_guia,))
                fotos_raw = cursor.fetchall() # Obtener todas las filas crudas
                logger.info(f"[DIAG][get_clasificacion] Consulta de fotos ejecutada para {codigo_guia}. Resultado crudo: {fotos_raw}")
                fotos = [foto_row[0] for foto_row in fotos_raw] # Extraer la ruta
                clasificacion['fotos'] = fotos
                logger.info(f"[DIAG][get_clasificacion] Rutas de fotos encontradas y asignadas para {codigo_guia}: {fotos}")
            except sqlite3.Error as фото_err:
                 logger.error(f"[DIAG][get_clasificacion] Error al consultar fotos para {codigo_guia}: {фото_err}")
                 clasificacion['fotos'] = [] # Asignar lista vacía en caso de error
            
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
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
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
    Uses TIQUETES_DB_PATH.
    
    Args:
        pesaje_data (dict): Diccionario con los datos del pesaje neto
        
    Returns:
        bool: True si se almacenó correctamente, False en caso contrario
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar si ya existe un registro con este código_guia
        cursor.execute("SELECT id FROM pesajes_neto WHERE codigo_guia = ?", 
                      (pesaje_data.get('codigo_guia'),))
        existing = cursor.fetchone()
        
        # Preparar datos excluyendo claves None y la clave primaria para INSERT/UPDATE
        datos_filtrados = {k: v for k, v in pesaje_data.items() if v is not None and k != 'id'}
        # Asegurarse de incluir el timestamp UTC y excluir los viejos
        datos_filtrados['timestamp_pesaje_neto_utc'] = datos_filtrados.pop('timestamp_pesaje_neto_utc', None) # Ensure it exists
        datos_filtrados.pop('fecha_pesaje_neto', None) # Remove old field
        datos_filtrados.pop('hora_pesaje_neto', None)  # Remove old field
        
        # Filtrar nuevamente por si el timestamp UTC era None
        datos_finales = {k: v for k, v in datos_filtrados.items() if v is not None}

        if existing:
            # Actualizar el registro existente
            update_cols = []
            params = []
            
            for key, value in datos_finales.items():
                if key != 'codigo_guia':  # Excluir la clave primaria
                    update_cols.append(f"{key} = ?")
                    params.append(value)
            
            # Agregar el parámetro para WHERE
            params.append(datos_finales.get('codigo_guia'))
            
            update_query = f"UPDATE pesajes_neto SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            logger.info(f"Actualizado registro de pesaje neto para guía: {datos_finales.get('codigo_guia')}")
        else:
            # Insertar nuevo registro
            columns = ', '.join(datos_finales.keys())
            placeholders = ', '.join(['?' for _ in datos_finales])
            values = list(datos_finales.values())
            
            insert_query = f"INSERT INTO pesajes_neto ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, values)
            logger.info(f"Insertado nuevo registro de pesaje neto para guía: {datos_finales.get('codigo_guia')}")
        
        conn.commit()
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error almacenando registro de pesaje neto: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_pesajes_neto(filtros=None):
    """
    Recupera los registros de pesajes netos, opcionalmente filtrados.
    Uses TIQUETES_DB_PATH.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de pesajes netos como diccionarios
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = "SELECT * FROM pesajes_neto"
        params = []
        
        # Aplicar filtros si se proporcionan
        if filtros:
            conditions = []
            
            if filtros.get('fecha_desde') and filtros.get('fecha_hasta'):
                try:
                    # No reformatear, usar YYYY-MM-DD directamente
                    fecha_desde = filtros['fecha_desde'] + ' 00:00:00'
                    fecha_hasta = filtros['fecha_hasta'] + ' 23:59:59'
                    
                    # Usar timestamp_pesaje_neto_utc para el rango
                    conditions.append("timestamp_pesaje_neto_utc BETWEEN ? AND ?")
                    params.extend([fecha_desde, fecha_hasta])
                except Exception as e: 
                    logger.warning(f"Error processing date filter values: {e}. Skipping date filter.")
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
                
        # Ordenar por timestamp UTC más reciente en SQL
        query += " ORDER BY timestamp_pesaje_neto_utc DESC"
                
        cursor.execute(query, params)
        
        pesajes = []
        for row in cursor.fetchall():
            pesaje = {key: row[key] for key in row.keys()}
            pesajes.append(pesaje)
        
        return pesajes
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return []
    except sqlite3.Error as e:
        logger.error(f"Recuperando registros de pesajes netos: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_pesaje_neto_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de pesaje neto específico por su código de guía.
    Uses TIQUETES_DB_PATH.
    
    Args:
        codigo_guia (str): El código de guía a buscar
        
    Returns:
        dict: El registro de pesaje neto como diccionario, o None si no se encuentra
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            pesaje = {key: row[key] for key in row.keys()}
            return pesaje
        return None
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registro de pesaje neto por código de guía: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_provider_by_code(codigo_proveedor, codigo_guia_actual=None):
    """
    Busca información de un proveedor por su código en las tablas disponibles.
    Uses TIQUETES_DB_PATH.
    
    Args:
        codigo_proveedor (str): Código del proveedor a buscar
        codigo_guia_actual (str, optional): Código de guía actual para evitar mezclar datos de diferentes entregas
        
    Returns:
        dict: Datos del proveedor o None si no se encuentra
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verificar si existe tabla de proveedores
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='proveedores'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM proveedores WHERE codigo = ?", (codigo_proveedor,))
            row = cursor.fetchone()
            if row: 
                proveedor = {key: row[key] for key in row.keys()}
                proveedor['es_dato_otra_entrega'] = False
                logger.info(f"Proveedor encontrado en tabla proveedores: {codigo_proveedor}")
                return proveedor
        
        if codigo_guia_actual:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM entry_records WHERE codigo_guia = ? LIMIT 1", (codigo_guia_actual,))
                row = cursor.fetchone()
                if row:
                    proveedor = {key: row[key] for key in row.keys()}
                    proveedor['codigo'] = proveedor.get('codigo_proveedor')
                    proveedor['nombre'] = proveedor.get('nombre_proveedor')
                    proveedor['es_dato_otra_entrega'] = False
                    logger.info(f"Proveedor encontrado en entry_records para el mismo código de guía: {codigo_guia_actual}")
                    return proveedor
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entry_records'")
        if cursor.fetchone():
            cursor.execute("SELECT * FROM entry_records WHERE codigo_proveedor = ? ORDER BY fecha_creacion DESC LIMIT 1", (codigo_proveedor,))
            row = cursor.fetchone()
            if row:
                proveedor = {key: row[key] for key in row.keys()}
                proveedor['codigo'] = proveedor.get('codigo_proveedor')
                proveedor['nombre'] = proveedor.get('nombre_proveedor')
                proveedor['timestamp_registro_utc'] = proveedor.get('timestamp_registro_utc', '')
                proveedor['es_dato_otra_entrega'] = bool(codigo_guia_actual and proveedor.get('codigo_guia') != codigo_guia_actual)
                if proveedor['es_dato_otra_entrega']:
                    logger.warning(f"Proveedor encontrado en otra entrada (código guía: {proveedor.get('codigo_guia')})")
                logger.info(f"Proveedor encontrado en entry_records: {codigo_proveedor}")
                return proveedor
            
        tables_to_check = ['pesajes_bruto', 'clasificaciones', 'pesajes_neto']
        for table in tables_to_check:
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
            if cursor.fetchone():
                cursor.execute(f"PRAGMA table_info({table})")
                columns = [row[1] for row in cursor.fetchall()]
                if 'codigo_proveedor' in columns:
                    if codigo_guia_actual and 'codigo_guia' in columns:
                        query = f"SELECT * FROM {table} WHERE codigo_guia = ? LIMIT 1"
                        cursor.execute(query, (codigo_guia_actual,))
                        row = cursor.fetchone()
                        if row and row['codigo_proveedor'] == codigo_proveedor:
                            proveedor = {key: row[key] for key in row.keys()}
                            proveedor['codigo'] = proveedor.get('codigo_proveedor')
                            proveedor['nombre'] = proveedor.get('nombre_proveedor')
                            proveedor['es_dato_otra_entrega'] = False
                            logger.info(f"Proveedor encontrado en {table} para el mismo código de guía: {codigo_guia_actual}")
                            return proveedor
                    query = f"SELECT * FROM {table} WHERE codigo_proveedor = ? LIMIT 1"
                    cursor.execute(query, (codigo_proveedor,))
                    row = cursor.fetchone()
                    if row:
                        proveedor = {key: row[key] for key in row.keys()}
                        proveedor['codigo'] = proveedor.get('codigo_proveedor')
                        proveedor['nombre'] = proveedor.get('nombre_proveedor')
                        proveedor['es_dato_otra_entrega'] = bool(codigo_guia_actual and 'codigo_guia' in columns and proveedor.get('codigo_guia') != codigo_guia_actual)
                        if proveedor['es_dato_otra_entrega']:
                            logger.warning(f"Datos encontrados en {table} de otra entrada (código guía: {proveedor.get('codigo_guia')})")
                        logger.info(f"Proveedor encontrado en {table}: {codigo_proveedor}")
                        return proveedor
        
        logger.warning(f"No se encontró información del proveedor: {codigo_proveedor}")
        return None
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error buscando proveedor por código: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_entry_records_by_provider_code(codigo_proveedor):
    # ... existing code ...
        records = []
        for row in c.fetchall():
            record = {}
            for key in row.keys():
                record[key] = row[key]
            # Ensure the timestamp field is included
            record['timestamp_registro_utc'] = record.get('timestamp_registro_utc', '') 
            records.append(record)
        
        conn.close()
        logger.info(f"Encontrados {len(records)} registros para el proveedor {codigo_proveedor}")
        return records
    # ... existing code ... 