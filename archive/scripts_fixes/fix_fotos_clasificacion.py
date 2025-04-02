#!/usr/bin/env python
"""
Script para actualizar la columna numero_foto en la tabla fotos_clasificacion
"""

import sqlite3
import logging
import os

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ruta a la base de datos
DB_PATH = 'tiquetes.db'

def fix_fotos_clasificacion():
    """
    Actualiza la columna numero_foto en registros existentes de fotos_clasificacion,
    asignando un valor secuencial para cada código de guía.
    """
    try:
        if not os.path.exists(DB_PATH):
            logger.error(f"Base de datos no encontrada en: {DB_PATH}")
            return False
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fotos_clasificacion'")
        if not cursor.fetchone():
            logger.error("La tabla fotos_clasificacion no existe en la base de datos")
            return False
        
        # Obtener todos los códigos de guía únicos
        cursor.execute("SELECT DISTINCT codigo_guia FROM fotos_clasificacion")
        codigos_guia = [row[0] for row in cursor.fetchall()]
        
        total_actualizado = 0
        
        # Para cada código de guía, actualizar el numero_foto secuencialmente
        for codigo_guia in codigos_guia:
            # Obtener IDs de fotos para este código
            cursor.execute("SELECT id FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY id", (codigo_guia,))
            ids = [row[0] for row in cursor.fetchall()]
            
            # Actualizar cada foto con un número secuencial
            for idx, id_foto in enumerate(ids, 1):
                cursor.execute("UPDATE fotos_clasificacion SET numero_foto = ? WHERE id = ?", (idx, id_foto))
                total_actualizado += 1
        
        conn.commit()
        logger.info(f"Actualización completada: {total_actualizado} registros para {len(codigos_guia)} guías")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error actualizando la tabla: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    logger.info("Iniciando corrección de fotos_clasificacion")
    result = fix_fotos_clasificacion()
    if result:
        logger.info("Corrección completada exitosamente")
    else:
        logger.error("La corrección no se pudo completar") 