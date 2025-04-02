#!/usr/bin/env python3
"""
Script para sincronizar los datos de los archivos JSON con las bases de datos
y asegurar que todas las tablas tengan la estructura correcta.
"""

import os
import json
import sqlite3
import glob
import logging
import traceback
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Definiciones de bases de datos
DB_PATHS = ['database.db', 'tiquetes.db']
GUIAS_DIR = 'guias'

def sync_database_structure():
    """Sincroniza la estructura de las bases de datos"""
    for db_path in DB_PATHS:
        try:
            logger.info(f"Sincronizando estructura de {db_path}...")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Crear tabla entry_records si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS entry_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_guia TEXT UNIQUE NOT NULL,
                codigo_proveedor TEXT,
                nombre_proveedor TEXT,
                fecha_registro TEXT,
                hora_registro TEXT,
                num_cedula TEXT,
                num_placa TEXT,
                conductor TEXT,
                tipo_fruta TEXT,
                lote TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                codigo_guia_transporte_sap TEXT,
                racimos TEXT,
                placa TEXT,
                transportador TEXT,
                acarreo TEXT,
                cargo TEXT
            )
            """)

            # Crear tabla pesajes_bruto si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pesajes_bruto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_guia TEXT UNIQUE NOT NULL,
                codigo_proveedor TEXT,
                nombre_proveedor TEXT,
                peso_bruto REAL,
                tipo_pesaje TEXT,
                fecha_pesaje TEXT,
                hora_pesaje TEXT,
                imagen_pesaje TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                codigo_guia_transporte_sap TEXT
            )
            """)

            # Crear tabla clasificaciones si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS clasificaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_guia TEXT UNIQUE NOT NULL,
                codigo_proveedor TEXT,
                nombre_proveedor TEXT,
                fecha_clasificacion TEXT,
                hora_clasificacion TEXT,
                clasificaciones TEXT,
                clasificacion_manual TEXT,
                clasificacion_automatica TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                racimos TEXT
            )
            """)

            # Crear tabla pesajes_neto si no existe
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS pesajes_neto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_guia TEXT UNIQUE NOT NULL,
                codigo_proveedor TEXT,
                nombre_proveedor TEXT,
                peso_tara REAL,
                peso_neto REAL,
                peso_producto REAL,
                tipo_pesaje TEXT,
                fecha_pesaje_neto TEXT,
                hora_pesaje_neto TEXT,
                imagen_pesaje TEXT,
                estado TEXT DEFAULT 'activo',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                racimos TEXT,
                placa TEXT,
                transportador TEXT,
                codigo_guia_transporte_sap TEXT
            )
            """)

            # Verificar columnas en tablas existentes y añadir las que falten
            tables = {
                "entry_records": [
                    "codigo_guia_transporte_sap", "racimos", "placa", "transportador", 
                    "acarreo", "cargo", "fecha_registro", "hora_registro"
                ],
                "pesajes_bruto": [
                    "codigo_guia_transporte_sap", "codigo_proveedor", "nombre_proveedor"
                ],
                "clasificaciones": [
                    "clasificacion_manual", "clasificacion_automatica", "racimos", 
                    "codigo_proveedor", "nombre_proveedor"
                ],
                "pesajes_neto": [
                    "codigo_guia_transporte_sap", "racimos", "placa", "transportador",
                    "codigo_proveedor", "nombre_proveedor"
                ]
            }

            for table, columns in tables.items():
                # Verificar que la tabla exista
                cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
                if not cursor.fetchone():
                    logger.warning(f"La tabla {table} no existe en {db_path}. Se ha intentado crearla.")
                    continue
                
                # Obtener columnas actuales
                cursor.execute(f"PRAGMA table_info({table})")
                current_columns = [row[1] for row in cursor.fetchall()]
                
                # Añadir columnas faltantes
                for column in columns:
                    if column not in current_columns:
                        try:
                            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
                            logger.info(f"Añadida columna {column} a la tabla {table} en {db_path}")
                        except sqlite3.Error as e:
                            logger.error(f"Error al añadir columna {column} a {table} en {db_path}: {e}")

            conn.commit()
            logger.info(f"Estructura de {db_path} sincronizada correctamente")
            
        except sqlite3.Error as e:
            logger.error(f"Error sincronizando estructura de {db_path}: {e}")
            logger.error(traceback.format_exc())
        finally:
            if conn:
                conn.close()

def sync_json_to_database():
    """Sincroniza los datos de los archivos JSON con las bases de datos"""
    if not os.path.exists(GUIAS_DIR):
        logger.error(f"El directorio {GUIAS_DIR} no existe")
        return
    
    # Obtener todos los archivos JSON en el directorio guias
    json_pattern = os.path.join(GUIAS_DIR, "guia_*.json")
    json_files = glob.glob(json_pattern)
    
    logger.info(f"Encontrados {len(json_files)} archivos JSON para sincronizar")
    
    for json_file in json_files:
        try:
            # Cargar datos del archivo JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                datos = json.load(f)
            
            codigo_guia = datos.get('codigo_guia')
            if not codigo_guia:
                logger.warning(f"Archivo JSON sin código de guía: {json_file}")
                continue
            
            logger.info(f"Sincronizando datos para guía {codigo_guia} desde {json_file}")
            
            # Sincronizar en cada base de datos
            for db_path in DB_PATHS:
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # 1. Actualizar entry_records
                    codigo_proveedor = datos.get('codigo_proveedor') or datos.get('codigo')
                    nombre_proveedor = datos.get('nombre_proveedor') or datos.get('nombre_agricultor') or datos.get('nombre')
                    
                    # Verificar si existe el registro
                    cursor.execute("SELECT codigo_guia FROM entry_records WHERE codigo_guia = ?", (codigo_guia,))
                    if cursor.fetchone():
                        # Actualizar registro existente
                        cursor.execute("""
                        UPDATE entry_records SET 
                            codigo_proveedor = ?,
                            nombre_proveedor = ?,
                            placa = ?,
                            transportador = ?,
                            racimos = ?,
                            acarreo = ?,
                            cargo = ?,
                            codigo_guia_transporte_sap = ?
                        WHERE codigo_guia = ?
                        """, (
                            codigo_proveedor,
                            nombre_proveedor,
                            datos.get('placa', 'No disponible'),
                            datos.get('transportador', 'No disponible'),
                            datos.get('racimos', 'No disponible'),
                            datos.get('acarreo', 'No'),
                            datos.get('cargo', 'No'),
                            datos.get('codigo_guia_transporte_sap', ''),
                            codigo_guia
                        ))
                        logger.info(f"Actualizado registro en entry_records para {codigo_guia} en {db_path}")
                    else:
                        # Insertar nuevo registro
                        fecha_registro = datos.get('fecha_registro', datetime.now().strftime('%d/%m/%Y'))
                        hora_registro = datos.get('hora_registro', datetime.now().strftime('%H:%M:%S'))
                        
                        cursor.execute("""
                        INSERT OR IGNORE INTO entry_records (
                            codigo_guia, codigo_proveedor, nombre_proveedor, fecha_registro, hora_registro,
                            placa, transportador, racimos, acarreo, cargo, codigo_guia_transporte_sap, estado
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            codigo_guia,
                            codigo_proveedor,
                            nombre_proveedor,
                            fecha_registro,
                            hora_registro,
                            datos.get('placa', 'No disponible'),
                            datos.get('transportador', 'No disponible'),
                            datos.get('racimos', 'No disponible'),
                            datos.get('acarreo', 'No'),
                            datos.get('cargo', 'No'),
                            datos.get('codigo_guia_transporte_sap', ''),
                            'entrada_completada'
                        ))
                        logger.info(f"Insertado registro en entry_records para {codigo_guia} en {db_path}")
                    
                    # 2. Actualizar pesajes_bruto si hay datos de pesaje
                    if 'peso_bruto' in datos:
                        # Verificar si existe el registro
                        cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia = ?", (codigo_guia,))
                        if cursor.fetchone():
                            # Actualizar registro existente
                            cursor.execute("""
                            UPDATE pesajes_bruto SET 
                                codigo_proveedor = ?,
                                nombre_proveedor = ?,
                                peso_bruto = ?,
                                tipo_pesaje = ?,
                                fecha_pesaje = ?,
                                hora_pesaje = ?,
                                imagen_pesaje = ?,
                                codigo_guia_transporte_sap = ?
                            WHERE codigo_guia = ?
                            """, (
                                codigo_proveedor,
                                nombre_proveedor,
                                datos.get('peso_bruto'),
                                datos.get('tipo_pesaje', 'directo'),
                                datos.get('fecha_pesaje', datetime.now().strftime('%d/%m/%Y')),
                                datos.get('hora_pesaje', datetime.now().strftime('%H:%M:%S')),
                                datos.get('imagen_pesaje', ''),
                                datos.get('codigo_guia_transporte_sap', ''),
                                codigo_guia
                            ))
                            logger.info(f"Actualizado registro en pesajes_bruto para {codigo_guia} en {db_path}")
                        else:
                            # Insertar nuevo registro
                            cursor.execute("""
                            INSERT INTO pesajes_bruto (
                                codigo_guia, codigo_proveedor, nombre_proveedor, peso_bruto, tipo_pesaje,
                                fecha_pesaje, hora_pesaje, imagen_pesaje, estado, codigo_guia_transporte_sap
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                codigo_guia,
                                codigo_proveedor,
                                nombre_proveedor,
                                datos.get('peso_bruto'),
                                datos.get('tipo_pesaje', 'directo'),
                                datos.get('fecha_pesaje', datetime.now().strftime('%d/%m/%Y')),
                                datos.get('hora_pesaje', datetime.now().strftime('%H:%M:%S')),
                                datos.get('imagen_pesaje', ''),
                                'pesaje_bruto_completado',
                                datos.get('codigo_guia_transporte_sap', '')
                            ))
                            logger.info(f"Insertado registro en pesajes_bruto para {codigo_guia} en {db_path}")
                    
                    conn.commit()
                    
                except sqlite3.Error as e:
                    logger.error(f"Error sincronizando datos para {codigo_guia} en {db_path}: {e}")
                    logger.error(traceback.format_exc())
                finally:
                    if conn:
                        conn.close()
        
        except Exception as e:
            logger.error(f"Error procesando archivo {json_file}: {e}")
            logger.error(traceback.format_exc())

def main():
    """Función principal"""
    logger.info("Iniciando sincronización de base de datos...")
    
    # Primero sincronizar la estructura
    sync_database_structure()
    
    # Luego sincronizar los datos
    sync_json_to_database()
    
    logger.info("Sincronización completada")

if __name__ == "__main__":
    main() 