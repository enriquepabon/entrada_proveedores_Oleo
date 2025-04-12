# app/utils/db_budget_operations.py
"""
Módulo para operaciones CRUD relacionadas con la tabla de presupuesto mensual.
"""

import sqlite3
import os
import logging
from flask import current_app
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def guardar_datos_presupuesto(datos_presupuesto):
    """
    Guarda o actualiza múltiples registros de presupuesto en la base de datos.
    Utiliza INSERT OR REPLACE para manejar duplicados por fecha.

    Args:
        datos_presupuesto (list): Una lista de diccionarios, donde cada diccionario 
                                 contiene 'fecha_presupuesto' (YYYY-MM-DD) y 
                                 'toneladas_proyectadas' (float o convertible a float).

    Returns:
        tuple: (bool, int) - Indica si la operación fue exitosa y el número de filas afectadas.
    """
    conn = None
    rows_affected = 0
    success = False
    
    if not datos_presupuesto:
        logger.warning("No se proporcionaron datos de presupuesto para guardar.")
        return False, 0

    # Preparar y validar los datos para la inserción masiva
    data_tuples = []
    for item in datos_presupuesto:
        fecha = item.get('fecha_presupuesto')
        toneladas = item.get('toneladas_proyectadas')
        
        if fecha and toneladas is not None:
            try:
                toneladas_float = float(toneladas)
                datetime.strptime(fecha, '%Y-%m-%d') 
                data_tuples.append((fecha, toneladas_float))
            except (ValueError, TypeError):
                 logger.warning(f"Registro de presupuesto inválido omitido: {item}")
        else:
             logger.warning(f"Registro de presupuesto incompleto omitido: {item}")

    if not data_tuples:
         logger.error("No hay datos de presupuesto válidos para guardar después de la validación.")
         return False, 0

    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        sql = """INSERT OR REPLACE INTO presupuesto_mensual 
                 (fecha_presupuesto, toneladas_proyectadas) 
                 VALUES (?, ?)"""
        
        cursor.executemany(sql, data_tuples)
        conn.commit()
        
        rows_affected = cursor.rowcount 
        if rows_affected == -1: 
             rows_affected = len(data_tuples) 
             
        success = True
        logger.info(f"Se guardaron/actualizaron {rows_affected} registros de presupuesto.")

    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        success = False
    except sqlite3.Error as e:
        logger.error(f"Error DB al guardar datos de presupuesto: {e}", exc_info=True)
        if conn: 
            try: conn.rollback()
            except sqlite3.Error as rb_err: logger.error(f"Error durante el rollback: {rb_err}")
        success = False
    except Exception as e:
         logger.error(f"Error inesperado al guardar presupuesto: {e}", exc_info=True)
         success = False
    finally:
        if conn:
            conn.close()
            
    return success, rows_affected

def obtener_datos_presupuesto(fecha_inicio, fecha_fin):
    """
    Obtiene los datos de presupuesto para un rango de fechas específico.

    Args:
        fecha_inicio (str): Fecha de inicio del rango (YYYY-MM-DD).
        fecha_fin (str): Fecha de fin del rango (YYYY-MM-DD).

    Returns:
        dict: Un diccionario mapeando fecha (str YYYY-MM-DD) a toneladas_proyectadas (float).
              Devuelve un diccionario vacío si no hay datos o en caso de error.
    """
    conn = None
    presupuesto_dict = {}

    try:
        datetime.strptime(fecha_inicio, '%Y-%m-%d')
        datetime.strptime(fecha_fin, '%Y-%m-%d')

        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row 
        cursor = conn.cursor()

        sql = """SELECT fecha_presupuesto, toneladas_proyectadas 
                 FROM presupuesto_mensual 
                 WHERE fecha_presupuesto BETWEEN ? AND ?
                 ORDER BY fecha_presupuesto"""
        
        cursor.execute(sql, (fecha_inicio, fecha_fin))
        
        for row in cursor.fetchall():
            presupuesto_dict[row['fecha_presupuesto']] = row['toneladas_proyectadas']
            
        logger.info(f"Se obtuvieron {len(presupuesto_dict)} registros de presupuesto para el rango {fecha_inicio} - {fecha_fin}.")

    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
    except (ValueError, TypeError):
        logger.error(f"Fechas inválidas proporcionadas: inicio='{fecha_inicio}', fin='{fecha_fin}'")
    except sqlite3.Error as e:
        logger.error(f"Error DB obteniendo presupuesto: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Error inesperado obteniendo presupuesto: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            
    return presupuesto_dict