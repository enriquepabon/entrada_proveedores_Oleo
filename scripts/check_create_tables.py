#!/usr/bin/env python3
"""
Script para verificar y crear las tablas necesarias en la base de datos
para el funcionamiento adecuado de la aplicación TiquetesApp.
"""

import os
import sys
import sqlite3
from datetime import datetime

# Configuración
DATABASE_PATH = 'database.db'

# Definición de tablas
TABLES = {
    'entry_records': '''
    CREATE TABLE IF NOT EXISTS entry_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT,
        hora TEXT,
        codigo_guia TEXT UNIQUE,
        placa TEXT,
        tipo_vehiculo TEXT,
        procedencia TEXT,
        destino TEXT,
        conductor_nombres TEXT,
        conductor_apellidos TEXT,
        conductor_cedula TEXT,
        conductor_tel TEXT,
        producto TEXT,
        proveedor TEXT,
        referencia TEXT,
        observaciones TEXT,
        estado TEXT,
        verificacion_placa TEXT,
        fecha_creacion TEXT,
        codigo_proveedor TEXT,
        nombre_proveedor TEXT,
        fecha_registro TEXT,
        hora_registro TEXT
    )
    ''',
    'pesajes_bruto': '''
    CREATE TABLE IF NOT EXISTS pesajes_bruto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_guia TEXT UNIQUE,
        peso_bruto REAL,
        tipo_pesaje TEXT,
        fecha_pesaje TEXT,
        hora_pesaje TEXT,
        imagen_pesaje TEXT,
        estado TEXT,
        fecha_creacion TEXT
    )
    ''',
    'pesajes_neto': '''
    CREATE TABLE IF NOT EXISTS pesajes_neto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_guia TEXT UNIQUE,
        peso_tara REAL,
        peso_neto REAL,
        peso_producto REAL,
        tipo_pesaje_neto TEXT,
        fecha_pesaje_neto TEXT,
        hora_pesaje_neto TEXT,
        imagen_pesaje_neto TEXT,
        estado TEXT,
        fecha_creacion TEXT
    )
    ''',
    'salidas': '''
    CREATE TABLE IF NOT EXISTS salidas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_guia TEXT UNIQUE,
        fecha_salida TEXT,
        hora_salida TEXT,
        estado_salida TEXT,
        observaciones_salida TEXT,
        verificacion_placa_salida TEXT,
        fecha_creacion TEXT
    )
    ''',
    'clasificaciones': '''
    CREATE TABLE IF NOT EXISTS clasificaciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo_guia TEXT UNIQUE,
        fecha_clasificacion TEXT,
        hora_clasificacion TEXT,
        datos_clasificacion TEXT,  
        resultados_clasificacion TEXT,
        imagenes TEXT,
        estado TEXT,
        fecha_creacion TEXT
    )
    '''
}

def init_db():
    """Inicializar la base de datos y crear las tablas si no existen"""
    
    print(f"Verificando acceso a la base de datos: {DATABASE_PATH}")
    
    if not os.path.exists(os.path.dirname(DATABASE_PATH)) and os.path.dirname(DATABASE_PATH):
        os.makedirs(os.path.dirname(DATABASE_PATH))
        print(f"Directorio creado: {os.path.dirname(DATABASE_PATH)}")
    
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        
        # Crear tablas si no existen
        for table_name, table_sql in TABLES.items():
            print(f"Verificando tabla: {table_name}")
            c.execute(table_sql)
            conn.commit()
            
            # Verificar si la tabla se creó correctamente
            c.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            if c.fetchone():
                print(f"✓ Tabla {table_name} existe o fue creada correctamente")
            else:
                print(f"✕ Error al crear la tabla {table_name}")
        
        print("\nVerificando columnas en tablas existentes...")
        
        # Verificar columnas en la tabla pesajes_neto
        c.execute("PRAGMA table_info(pesajes_neto)")
        columns = [col[1] for col in c.fetchall()]
        
        required_columns = {
            'codigo_guia': 'TEXT UNIQUE',
            'peso_tara': 'REAL',
            'peso_neto': 'REAL',
            'peso_producto': 'REAL',
            'tipo_pesaje_neto': 'TEXT',
            'fecha_pesaje_neto': 'TEXT',
            'hora_pesaje_neto': 'TEXT',
            'imagen_pesaje_neto': 'TEXT',
            'estado': 'TEXT',
            'fecha_creacion': 'TEXT'
        }
        
        missing_columns = set(required_columns.keys()) - set(columns)
        
        if missing_columns:
            print(f"Agregando columnas faltantes a la tabla pesajes_neto: {missing_columns}")
            for column in missing_columns:
                try:
                    sql = f"ALTER TABLE pesajes_neto ADD COLUMN {column} {required_columns[column]}"
                    c.execute(sql)
                    print(f"  ✓ Columna {column} agregada")
                except sqlite3.OperationalError as e:
                    print(f"  ✕ Error al agregar columna {column}: {e}")
            
            conn.commit()
        else:
            print("✓ Todas las columnas requeridas existen en la tabla pesajes_neto")
        
        print("\nBase de datos verificada y actualizada correctamente.")
        
    except sqlite3.Error as e:
        print(f"Error de SQLite: {e}")
        return False
    finally:
        if conn:
            conn.close()
    
    return True

def main():
    """Función principal del script"""
    
    print("==============================================")
    print("VERIFICACIÓN Y CREACIÓN DE TABLAS")
    print("==============================================")
    print(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("----------------------------------------------")
    
    if init_db():
        print("\n✓ Proceso completado con éxito")
        return 0
    else:
        print("\n✕ Se encontraron errores durante el proceso")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 