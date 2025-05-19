"""
Módulo para las operaciones CRUD de la base de datos.
Contiene funciones para guardar y recuperar datos de todas las tablas.
"""

import sqlite3
import os
import logging
import json
from datetime import datetime, time
from flask import current_app
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define timezones
UTC = pytz.utc
BOGOTA_TZ = pytz.timezone('America/Bogota')

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
    pesajes = []
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
                    query = "SELECT *, timestamp_pesaje_utc FROM pesajes_bruto ORDER BY timestamp_pesaje_utc DESC"
                    params = []
                    # TODO: Re-implementar filtros si son necesarios
                    # ... 
                    cursor.execute(query, params)
                    for row in cursor.fetchall():
                        pesaje = {key: row[key] for key in row.keys()}
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
        logger.info(f"[DEBUG-ESTADO] Valor de 'estado' a guardar: {datos_finales.get('estado')}")

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
                logger.info(f"STORE_CLASIF: Preparando UPDATE para {codigo_guia}.")
                logger.info(f"[DEBUG-ESTADO] Valor de 'estado' en UPDATE: {update_fields.get('estado')}")
                # --- INICIO: Logs detallados de UPDATE ---
                logger.info(f"STORE_CLASIF [UPDATE SQL]: {update_query}")
                # Loguear parámetros con cuidado, especialmente si pueden ser muy largos
                try:
                    # Intentar loguear como JSON para valores largos
                    params_log = json.dumps(valores, indent=2, ensure_ascii=False, default=str)
                    logger.info(f"STORE_CLASIF [UPDATE PARAMS]:\n{params_log}")
                except Exception as log_err:
                    logger.error(f"STORE_CLASIF [UPDATE PARAMS] Error al dumpear params para log: {log_err}")
                    logger.info(f"STORE_CLASIF [UPDATE PARAMS] (raw - puede estar truncado): {valores}")
                # --- FIN: Logs detallados de UPDATE ---
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
            logger.info(f"[DEBUG-ESTADO] Valor de 'estado' en INSERT: {datos_finales.get('estado')}")
            logger.debug(f"STORE_CLASIF: Valores para INSERT: {valores}")
            cursor.execute(insert_query, valores)
            logger.info(f"STORE_CLASIF: INSERT ejecutado para {codigo_guia}.")

        # Commit después de INSERT/UPDATE de clasificación
        conn.commit()
        logger.info(f"[DEBUG-ESTADO] Commit realizado para {codigo_guia}. Valor de 'estado' guardado: {datos_finales.get('estado')}")
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
            
            if filtros.get('fecha_desde'):
                try:
                    fecha_desde_str = filtros['fecha_desde'] # YYYY-MM-DD
                    # Convertir a UTC desde Bogotá
                    naive_dt_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                    naive_dt_desde = datetime.combine(naive_dt_desde.date(), time.min)
                    bogota_dt_desde = BOGOTA_TZ.localize(naive_dt_desde)
                    utc_dt_desde = bogota_dt_desde.astimezone(UTC)
                    utc_timestamp_desde = utc_dt_desde.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_clasificacion_utc >= ?")
                    params.append(utc_timestamp_desde)
                    logger.info(f"[Clasificaciones] Filtro fecha_desde (Bogotá: {fecha_desde_str} 00:00:00) -> UTC: {utc_timestamp_desde}")
                except (ValueError, TypeError) as e:
                     logger.warning(f"[Clasificaciones] Error procesando fecha_desde '{filtros.get('fecha_desde', 'N/A')}': {e}. Saltando filtro.")
                
            if filtros.get('fecha_hasta'):
                try:
                    fecha_hasta_str = filtros['fecha_hasta'] # YYYY-MM-DD
                    # Convertir a UTC desde Bogotá
                    naive_dt_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                    naive_dt_hasta = datetime.combine(naive_dt_hasta.date(), time.max.replace(microsecond=0))
                    bogota_dt_hasta = BOGOTA_TZ.localize(naive_dt_hasta)
                    utc_dt_hasta = bogota_dt_hasta.astimezone(UTC)
                    utc_timestamp_hasta = utc_dt_hasta.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_clasificacion_utc <= ?")
                    params.append(utc_timestamp_hasta)
                    logger.info(f"[Clasificaciones] Filtro fecha_hasta (Bogotá: {fecha_hasta_str} 23:59:59) -> UTC: {utc_timestamp_hasta}")
                except (ValueError, TypeError) as e:
                     logger.warning(f"[Clasificaciones] Error procesando fecha_hasta '{filtros.get('fecha_hasta', 'N/A')}': {e}. Saltando filtro.")
            
            # Mantener los otros filtros como estaban
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
            
            # Convertir fechas de filtro de Bogotá a UTC
            if filtros.get('fecha_desde'):
                try:
                    fecha_desde_str = filtros['fecha_desde'] # YYYY-MM-DD
                    naive_dt_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                    naive_dt_desde = datetime.combine(naive_dt_desde.date(), time.min)
                    bogota_dt_desde = BOGOTA_TZ.localize(naive_dt_desde)
                    utc_dt_desde = bogota_dt_desde.astimezone(UTC)
                    utc_timestamp_desde = utc_dt_desde.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_pesaje_neto_utc >= ?")
                    params.append(utc_timestamp_desde)
                    logger.info(f"[Pesajes Neto] Filtro fecha_desde (Bogotá: {fecha_desde_str} 00:00:00) -> UTC: {utc_timestamp_desde}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Pesajes Neto] Error procesando fecha_desde '{filtros.get('fecha_desde', 'N/A')}': {e}. Saltando filtro.")

            if filtros.get('fecha_hasta'):
                try:
                    fecha_hasta_str = filtros['fecha_hasta'] # YYYY-MM-DD
                    naive_dt_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                    naive_dt_hasta = datetime.combine(naive_dt_hasta.date(), time.max.replace(microsecond=0))
                    bogota_dt_hasta = BOGOTA_TZ.localize(naive_dt_hasta)
                    utc_dt_hasta = bogota_dt_hasta.astimezone(UTC)
                    utc_timestamp_hasta = utc_dt_hasta.strftime('%Y-%m-%d %H:%M:%S')
                    
                    conditions.append("timestamp_pesaje_neto_utc <= ?")
                    params.append(utc_timestamp_hasta)
                    logger.info(f"[Pesajes Neto] Filtro fecha_hasta (Bogotá: {fecha_hasta_str} 23:59:59) -> UTC: {utc_timestamp_hasta}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Pesajes Neto] Error procesando fecha_hasta '{filtros.get('fecha_hasta', 'N/A')}': {e}. Saltando filtro.")

            # Otros filtros
            proveedor_term_filter = filtros.get('proveedor_term')
            if proveedor_term_filter:
                # Asumiendo que las columnas codigo_proveedor y nombre_proveedor existen en la tabla pesajes_neto
                # o que se hace un JOIN apropiado si vienen de otra tabla.
                # Si no existen directamente, esta condición no funcionará como se espera.
                # Esta lógica asume que la tabla pesajes_neto tiene estas columnas o se unen adecuadamente.
                # Si 'nombre_proveedor' no está en 'pesajes_neto', necesitarás un JOIN con 'entry_records' o similar.
                # Por ahora, se asume que existen o se unen.
                # Si 'nombre_proveedor' no está directamente en la tabla 'pesajes_neto',
                # esta parte del filtro necesitará un JOIN en la consulta principal.
                # Por simplicidad, se añade la condición, pero puede requerir ajustar el SELECT y FROM.
                # Ejemplo simplificado asumiendo que existen en la tabla:
                conditions.append("(codigo_proveedor LIKE ? OR nombre_proveedor LIKE ?)")
                params.extend([f"%{proveedor_term_filter}%", f"%{proveedor_term_filter}%"])
                logger.info(f"[Pesajes Neto] Filtro por proveedor_term: '{proveedor_term_filter}'")
            
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
            # Cerrar conexión si se abrió
            if conn:
                conn.close()
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
            # Ensure the timestamp field is included
            record['timestamp_registro_utc'] = record.get('timestamp_registro_utc', '') 
            records.append(record)
        
        # Cerrar conexión antes de retornar
        if conn:
             conn.close()
        logger.info(f"Encontrados {len(records)} registros para el proveedor {codigo_proveedor}")
        return records
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        if conn: # Asegurar cierre en caso de error
            conn.close()
        return []
    except Exception as e:
        logger.error(f"Error al obtener registros para el proveedor {codigo_proveedor}: {str(e)}")
        # logger.error(traceback.format_exc()) # Comentado para reducir verbosidad, descomentar si es necesario
        if conn:
             conn.close()
        return []
    finally:
        # Asegurar cierre final si aún está abierta (por si acaso)
        if conn:
            conn.close()

#-----------------------
# Operaciones para Salidas
#-----------------------

def store_salida(salida_data):
    """
    Almacena un registro de salida en la base de datos.
    Uses TIQUETES_DB_PATH.
    
    Args:
        salida_data (dict): Diccionario con los datos de la salida
        
    Returns:
        bool: True si se almacenó correctamente, False en caso contrario
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Verificar si ya existe un registro con este código_guia
        cursor.execute("SELECT id FROM salidas WHERE codigo_guia = ?", 
                      (salida_data.get('codigo_guia'),))
        existing = cursor.fetchone()
        
        # Preparar datos excluyendo claves None y la clave primaria para INSERT/UPDATE
        datos_filtrados = {k: v for k, v in salida_data.items() if v is not None and k != 'id'}
        datos_finales = datos_filtrados # En este caso no hay timestamps complejos que manejar

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
            
            update_query = f"UPDATE salidas SET {', '.join(update_cols)} WHERE codigo_guia = ?"
            cursor.execute(update_query, params)
            logger.info(f"Actualizado registro de salida para guía: {datos_finales.get('codigo_guia')}")
        else:
            # Insertar nuevo registro
            columns = ', '.join(datos_finales.keys())
            placeholders = ', '.join(['?' for _ in datos_finales])
            values = list(datos_finales.values())
            
            insert_query = f"INSERT INTO salidas ({columns}) VALUES ({placeholders})"
            cursor.execute(insert_query, values)
            logger.info(f"Insertado nuevo registro de salida para guía: {datos_finales.get('codigo_guia')}")
        
        conn.commit()
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error almacenando registro de salida: {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_salidas(filtros=None):
    """
    Recupera los registros de salidas, opcionalmente filtrados.
    Uses TIQUETES_DB_PATH.
    
    Args:
        filtros (dict, optional): Diccionario con condiciones de filtro
        
    Returns:
        list: Lista de registros de salidas como diccionarios
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verificar que la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='salidas'")
        if not cursor.fetchone():
            logger.warning("La tabla 'salidas' no existe en la base de datos.")
            return []
        
        query = "SELECT * FROM salidas"
        params = []
        
        # Aplicar filtros si se proporcionan
        if filtros:
            conditions = []
            
            # Filtro por fecha (usando timestamp_salida_utc)
            if filtros.get('fecha_desde'):
                try:
                    fecha_desde_str = filtros['fecha_desde'] # YYYY-MM-DD
                    naive_dt_desde = datetime.strptime(fecha_desde_str, '%Y-%m-%d')
                    naive_dt_desde = datetime.combine(naive_dt_desde.date(), time.min)
                    bogota_dt_desde = BOGOTA_TZ.localize(naive_dt_desde)
                    utc_dt_desde = bogota_dt_desde.astimezone(UTC)
                    utc_timestamp_desde = utc_dt_desde.strftime('%Y-%m-%d %H:%M:%S')
                    conditions.append("timestamp_salida_utc >= ?")
                    params.append(utc_timestamp_desde)
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Salidas] Error procesando fecha_desde '{filtros.get('fecha_desde', 'N/A')}': {e}.")

            if filtros.get('fecha_hasta'):
                try:
                    fecha_hasta_str = filtros['fecha_hasta'] # YYYY-MM-DD
                    naive_dt_hasta = datetime.strptime(fecha_hasta_str, '%Y-%m-%d')
                    naive_dt_hasta = datetime.combine(naive_dt_hasta.date(), time.max.replace(microsecond=0))
                    bogota_dt_hasta = BOGOTA_TZ.localize(naive_dt_hasta)
                    utc_dt_hasta = bogota_dt_hasta.astimezone(UTC)
                    utc_timestamp_hasta = utc_dt_hasta.strftime('%Y-%m-%d %H:%M:%S')
                    conditions.append("timestamp_salida_utc <= ?")
                    params.append(utc_timestamp_hasta)
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Salidas] Error procesando fecha_hasta '{filtros.get('fecha_hasta', 'N/A')}': {e}.")

            # Otros filtros
            if filtros.get('codigo_guia'):
                conditions.append("codigo_guia LIKE ?")
                params.append(f"%{filtros['codigo_guia']}%")
            if filtros.get('codigo_proveedor'):
                conditions.append("codigo_proveedor LIKE ?")
                params.append(f"%{filtros['codigo_proveedor']}%")
            if filtros.get('nombre_proveedor'):
                conditions.append("nombre_proveedor LIKE ?")
                params.append(f"%{filtros['nombre_proveedor']}%")
            if filtros.get('estado'):
                 conditions.append("estado LIKE ?")
                 params.append(f"%{filtros['estado']}%")
            
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
                
        # Ordenar por timestamp UTC más reciente
        query += " ORDER BY timestamp_salida_utc DESC"
                
        cursor.execute(query, params)
        
        salidas = []
        for row in cursor.fetchall():
            salida = {key: row[key] for key in row.keys()}
            salidas.append(salida)
        
        return salidas
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return []
    except sqlite3.Error as e:
        logger.error(f"Recuperando registros de salidas: {e}")
        return []
    finally:
        if conn:
            conn.close()


def get_salida_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de salida específico por su código de guía.
    Uses TIQUETES_DB_PATH.
    
    Args:
        codigo_guia (str): El código de guía a buscar
        
    Returns:
        dict: El registro de salida como diccionario, o None si no se encuentra
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verificar que la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='salidas'")
        if not cursor.fetchone():
            logger.warning("La tabla 'salidas' no existe al buscar por código de guía.")
            return None
        
        cursor.execute("SELECT * FROM salidas WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            salida = {key: row[key] for key in row.keys()}
            return salida
        return None
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registro de salida por código de guía: {e}")
        return None
    finally:
        if conn:
            conn.close()

#-----------------------
# Operaciones Genéricas / Proveedor
#-----------------------

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
            # Cerrar conexión si se abrió
            if conn:
                conn.close()
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
            # Ensure the timestamp field is included
            record['timestamp_registro_utc'] = record.get('timestamp_registro_utc', '') 
            records.append(record)
        
        # Cerrar conexión antes de retornar
        if conn:
             conn.close()
        logger.info(f"Encontrados {len(records)} registros para el proveedor {codigo_proveedor}")
        return records
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        if conn: # Asegurar cierre en caso de error
            conn.close()
        return []
    except Exception as e:
        logger.error(f"Error al obtener registros para el proveedor {codigo_proveedor}: {str(e)}")
        # logger.error(traceback.format_exc()) # Comentado para reducir verbosidad, descomentar si es necesario
        if conn:
             conn.close()
        return []
    finally:
        # Asegurar cierre final si aún está abierta (por si acaso)
        if conn:
            conn.close()