import sqlite3
import logging
from flask import current_app
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def guardar_datos_presupuesto(datos_presupuesto):
    """
    Guarda los datos del presupuesto mensual en la base de datos.
    Reemplaza los datos existentes para el mismo mes/año si es necesario.

    Args:
        datos_presupuesto (list): Lista de diccionarios, cada uno con
                                   {'fecha_presupuesto': 'YYYY-MM-DD', 'toneladas_proyectadas': float}
    Returns:
        bool: True si la operación fue exitosa, False en caso contrario.
    """
    conn = None
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Implementación básica: Iterar y guardar/actualizar
        # (Se necesita lógica más robusta para manejar duplicados y actualizaciones)
        for dato in datos_presupuesto:
            fecha = dato.get('fecha_presupuesto')
            toneladas = dato.get('toneladas_proyectadas')
            if fecha and toneladas is not None:
                # Aquí iría la lógica para INSERT OR REPLACE o UPDATE/INSERT
                logger.info(f"Guardando presupuesto para {fecha}: {toneladas} toneladas.")
                # Ejemplo simple (necesita mejora):
                cursor.execute(
                    "INSERT OR REPLACE INTO presupuesto_mensual (fecha_presupuesto, toneladas_proyectadas, fecha_carga) VALUES (?, ?, ?)",
                    (fecha, toneladas, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                )
            else:
                logger.warning(f"Dato de presupuesto inválido omitido: {dato}")

        conn.commit()
        logger.info("Datos de presupuesto guardados exitosamente.")
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error guardando datos de presupuesto: {e}")
        if conn:
            conn.rollback() # Revertir cambios en caso de error
        return False
    except Exception as e:
         logger.error(f"Error inesperado guardando presupuesto: {e}")
         if conn:
             conn.rollback()
         return False
    finally:
        if conn:
            conn.close()

def obtener_datos_presupuesto(fecha_inicio, fecha_fin):
    """
    Obtiene los datos de presupuesto para un rango de fechas.

    Args:
        fecha_inicio (str): Fecha de inicio en formato 'YYYY-MM-DD'.
        fecha_fin (str): Fecha de fin en formato 'YYYY-MM-DD'.

    Returns:
        dict: Un diccionario donde las claves son las fechas ('YYYY-MM-DD')
              y los valores son las toneladas proyectadas.
              Retorna un diccionario vacío si hay error o no hay datos.
    """
    conn = None
    datos_presupuesto = {}
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row # Para acceder por nombre de columna
        cursor = conn.cursor()

        # Asegurar que la tabla exista antes de consultar
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='presupuesto_mensual'")
        if not cursor.fetchone():
             logger.warning("La tabla 'presupuesto_mensual' no existe. No se pueden obtener datos.")
             return {} # Retornar vacío si la tabla no existe

        query = """
            SELECT fecha_presupuesto, toneladas_proyectadas
            FROM presupuesto_mensual
            WHERE fecha_presupuesto >= ? AND fecha_presupuesto <= ?
            ORDER BY fecha_presupuesto ASC
        """
        cursor.execute(query, (fecha_inicio, fecha_fin))

        for row in cursor.fetchall():
            # La clave es la fecha, el valor es toneladas
            datos_presupuesto[row['fecha_presupuesto']] = row['toneladas_proyectadas']

        logger.info(f"Obtenidos {len(datos_presupuesto)} registros de presupuesto entre {fecha_inicio} y {fecha_fin}.")
        return datos_presupuesto
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return {}
    except sqlite3.Error as e:
        logger.error(f"Error obteniendo datos de presupuesto: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error inesperado obteniendo presupuesto: {e}")
        return {}
    finally:
        if conn:
            conn.close() 