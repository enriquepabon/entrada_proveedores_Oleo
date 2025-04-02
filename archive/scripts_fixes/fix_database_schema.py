#!/usr/bin/env python3
"""
Script para corregir el esquema de la base de datos añadiendo las columnas faltantes
que están causando errores en la aplicación TiquetesApp.
"""

import sqlite3
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_and_add_columns():
    """Verifica y añade columnas faltantes en las bases de datos"""
    logger.info("Iniciando la corrección del esquema de la base de datos...")
    
    databases = ['tiquetes.db', 'database.db']
    
    for db_name in databases:
        if not os.path.exists(db_name):
            logger.warning(f"Base de datos {db_name} no encontrada. Omitiendo.")
            continue
            
        logger.info(f"Verificando esquema de {db_name}...")
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # Verificar y añadir columna codigo_guia_transporte_sap a entry_records
        cursor.execute("PRAGMA table_info(entry_records)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "codigo_guia_transporte_sap" not in columns:
            try:
                logger.info(f"Añadiendo columna codigo_guia_transporte_sap a entry_records en {db_name}")
                cursor.execute("ALTER TABLE entry_records ADD COLUMN codigo_guia_transporte_sap TEXT")
                conn.commit()
            except Exception as e:
                logger.error(f"Error al añadir columna a entry_records: {str(e)}")
        else:
            logger.info(f"La columna codigo_guia_transporte_sap ya existe en entry_records en {db_name}")
        
        # Verificar y añadir columna codigo_guia_transporte_sap a pesajes_bruto
        cursor.execute("PRAGMA table_info(pesajes_bruto)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if "codigo_guia_transporte_sap" not in columns:
            try:
                logger.info(f"Añadiendo columna codigo_guia_transporte_sap a pesajes_bruto en {db_name}")
                cursor.execute("ALTER TABLE pesajes_bruto ADD COLUMN codigo_guia_transporte_sap TEXT")
                conn.commit()
            except Exception as e:
                logger.error(f"Error al añadir columna a pesajes_bruto: {str(e)}")
        else:
            logger.info(f"La columna codigo_guia_transporte_sap ya existe en pesajes_bruto en {db_name}")

        # Cerrar conexión
        conn.close()
    
    logger.info("Proceso de actualización de esquema completado.")


if __name__ == "__main__":
    check_and_add_columns() 