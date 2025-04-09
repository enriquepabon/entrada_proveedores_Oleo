"""
Definición del esquema de la base de datos SQLite para la aplicación de tiquetes.
Este archivo contiene las sentencias SQL para crear las tablas necesarias.
"""

import sqlite3
import logging
import os
from flask import current_app

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Eliminar la variable global DB_PATH
# DB_PATH = 'tiquetes.db' 

# Esquema de la tabla de registros de entrada
CREATE_ENTRY_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS entry_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    nombre_proveedor TEXT,
    codigo_proveedor TEXT,
    timestamp_registro_utc TEXT,
    num_cedula TEXT,
    num_placa TEXT, -- Kept for potential legacy use
    placa TEXT, -- Added for consistency with code usage
    conductor TEXT,
    transportador TEXT, -- Added
    codigo_transportador TEXT, -- Added
    tipo_fruta TEXT,
    cantidad_racimos INTEGER, -- Added
    acarreo TEXT, -- Added
    cargo TEXT, -- Added
    nota TEXT, -- Added
    lote TEXT,
    image_filename TEXT, -- Added
    modified_fields TEXT, -- Added (store as JSON string)
    fecha_tiquete TEXT, -- Added
    pdf_filename TEXT, -- Added
    qr_filename TEXT, -- Added
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Esquema de la tabla de pesajes brutos
CREATE_PESAJES_BRUTO_TABLE = """
CREATE TABLE IF NOT EXISTS pesajes_bruto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    peso_bruto REAL,
    tipo_pesaje TEXT,
    timestamp_pesaje_utc TEXT,
    imagen_pesaje TEXT,
    codigo_guia_transporte_sap TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Esquema de la tabla de clasificaciones
CREATE_CLASIFICACIONES_TABLE = """
CREATE TABLE IF NOT EXISTS clasificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    timestamp_clasificacion_utc TEXT,
    -- Clasificación Manual
    verde_manual REAL,
    sobremaduro_manual REAL,
    danio_corona_manual REAL,
    pendunculo_largo_manual REAL,
    podrido_manual REAL,
    -- Clasificación Automática
    verde_automatico REAL,
    sobremaduro_automatico REAL,
    danio_corona_automatico REAL,
    pendunculo_largo_automatico REAL,
    podrido_automatico REAL,
    -- Campos JSON completos
    clasificacion_manual_json TEXT,
    clasificacion_automatica_json TEXT,
    clasificacion_manual TEXT,
    clasificacion_automatica TEXT,
    observaciones TEXT,
    estado TEXT DEFAULT 'activo',
    -- Nuevas columnas para datos consolidados
    total_racimos_detectados INTEGER, 
    clasificacion_consolidada TEXT, -- JSON con {categoria: {cantidad: X, porcentaje: Y}}
    fecha_actualizacion TEXT,
    hora_actualizacion TEXT,
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Esquema de la tabla de pesajes netos
CREATE_PESAJES_NETO_TABLE = """
CREATE TABLE IF NOT EXISTS pesajes_neto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    peso_bruto REAL,
    peso_tara REAL,
    peso_neto REAL,
    peso_producto REAL,
    tipo_pesaje_neto TEXT,
    timestamp_pesaje_neto_utc TEXT,
    comentarios TEXT,
    respuesta_sap TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Esquema para la tabla de registro de salidas
CREATE_SALIDAS_TABLE = """
CREATE TABLE IF NOT EXISTS salidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    timestamp_salida_utc TEXT,
    comentarios_salida TEXT,
    firma_salida TEXT,
    estado TEXT DEFAULT 'completado',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Esquema para la tabla de fotos de clasificación
CREATE_FOTOS_CLASIFICACION_TABLE = """
CREATE TABLE IF NOT EXISTS fotos_clasificacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT NOT NULL,
    ruta_foto TEXT NOT NULL,
    numero_foto INTEGER,
    tipo_foto TEXT,
    fecha_subida TEXT,
    hora_subida TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (codigo_guia) REFERENCES clasificaciones(codigo_guia)
);
"""

def create_tables():
    """
    Crea las tablas necesarias en la base de datos si no existen.
    Utiliza la ruta definida en la configuración de la aplicación.
    """
    conn = None # Initialize conn
    try:
        # Obtener la ruta de la base de datos desde la configuración de la app
        db_path = current_app.config['TIQUETES_DB_PATH']
        
        # Asegurar que el directorio de la base de datos exista
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Directorio de base de datos creado: {db_dir}")
            
        # Conectar a la base de datos usando la ruta configurada
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Crear tablas
        cursor.execute(CREATE_ENTRY_RECORDS_TABLE)
        cursor.execute(CREATE_PESAJES_BRUTO_TABLE)
        cursor.execute(CREATE_CLASIFICACIONES_TABLE)
        cursor.execute(CREATE_PESAJES_NETO_TABLE)
        cursor.execute(CREATE_FOTOS_CLASIFICACION_TABLE)
        cursor.execute(CREATE_SALIDAS_TABLE)
        
        # --- Helper function to add column if not exists ---
        def add_column_if_not_exists(table_name, column_name, column_definition):
            try:
                # First, check if the column exists using PRAGMA
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [column[1] for column in cursor.fetchall()]
                if column_name not in columns:
                    logger.info(f"Attempting to add missing '{column_name}' column to {table_name}...")
                    try:
                        # Try to add the column
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")
                        logger.info(f"Column '{column_name}' added successfully to {table_name}.")
                        conn.commit() # Commit after successful addition
                    except sqlite3.OperationalError as e:
                        # Check if the error is specifically about a duplicate column
                        if "duplicate column name" in str(e).lower():
                             # This case might happen if PRAGMA check failed or in a race condition (unlikely here)
                             logger.warning(f"Column '{column_name}' appears to already exist in {table_name} despite initial check (or ALTER failed with duplicate error). Error: {e}")
                        else:
                            # Re-raise other operational errors
                            logger.error(f"Unexpected SQLite OperationalError adding '{column_name}' to {table_name}: {e}")
                            raise e # Re-raise the original error if it's not a duplicate column issue
                # else:
                     # Column already exists based on PRAGMA check, no action needed.
                     # logger.info(f"Column '{column_name}' already exists in {table_name}.")
                     
            except sqlite3.Error as e:
                 # Catch other potential SQLite errors during the process
                 logger.error(f"General SQLite Error checking/adding '{column_name}' to {table_name}: {e}")
                 # Depending on severity, you might want to raise e here as well
        # --------------------------------------------------

        # Check and add columns for entry_records
        add_column_if_not_exists('entry_records', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('entry_records', 'timestamp_registro_utc', 'TEXT') # Ensure this one is also checked
        # --- BEGIN ADDED CHECKS for entry_records ---
        add_column_if_not_exists('entry_records', 'placa', 'TEXT')
        add_column_if_not_exists('entry_records', 'transportador', 'TEXT')
        add_column_if_not_exists('entry_records', 'codigo_transportador', 'TEXT')
        add_column_if_not_exists('entry_records', 'cantidad_racimos', 'INTEGER')
        add_column_if_not_exists('entry_records', 'acarreo', 'TEXT')
        add_column_if_not_exists('entry_records', 'cargo', 'TEXT')
        add_column_if_not_exists('entry_records', 'nota', 'TEXT')
        add_column_if_not_exists('entry_records', 'image_filename', 'TEXT')
        add_column_if_not_exists('entry_records', 'modified_fields', 'TEXT')
        add_column_if_not_exists('entry_records', 'fecha_tiquete', 'TEXT')
        add_column_if_not_exists('entry_records', 'pdf_filename', 'TEXT')
        add_column_if_not_exists('entry_records', 'qr_filename', 'TEXT')
        # --- END ADDED CHECKS for entry_records ---

        # Check and add columns for pesajes_bruto
        add_column_if_not_exists('pesajes_bruto', 'timestamp_pesaje_utc', 'TEXT')
        add_column_if_not_exists('pesajes_bruto', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('pesajes_bruto', 'codigo_guia_transporte_sap', 'TEXT')

        # Check and add columns for clasificaciones
        add_column_if_not_exists('clasificaciones', 'timestamp_clasificacion_utc', 'TEXT')
        add_column_if_not_exists('clasificaciones', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('clasificaciones', 'total_racimos_detectados', 'INTEGER')
        add_column_if_not_exists('clasificaciones', 'clasificacion_consolidada', 'TEXT')

        # Check and add columns for pesajes_neto
        add_column_if_not_exists('pesajes_neto', 'timestamp_pesaje_neto_utc', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('pesajes_neto', 'peso_producto', 'REAL')
        add_column_if_not_exists('pesajes_neto', 'comentarios', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'tipo_pesaje_neto', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'respuesta_sap', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'peso_bruto', 'REAL') # Ensure peso_bruto is here too
        
        # Check and add columns for salidas
        add_column_if_not_exists('salidas', 'timestamp_salida_utc', 'TEXT')
        add_column_if_not_exists('salidas', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('salidas', 'comentarios_salida', 'TEXT')
        add_column_if_not_exists('salidas', 'firma_salida', 'TEXT')

        # Check and add columns for fotos_clasificacion
        add_column_if_not_exists('fotos_clasificacion', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        # Add other checks for fotos_clasificacion if needed

        logger.info(f"Table schema verification completed for: {db_path}")
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error creando tablas en la base de datos ({db_path}): {e}")
        return False
    finally:
        if conn:
            conn.close()

# El bloque if __name__ == "__main__": ya no puede funcionar directamente
# porque necesita el contexto de la aplicación Flask para acceder a current_app.config
# Se podría adaptar para usarlo desde un script que cree la app primero, o eliminarlo
# si la creación de tablas solo se hace desde app/__init__.py.
# Por ahora, lo comentamos para evitar errores si se ejecuta directamente.
# if __name__ == "__main__":
#    # Necesitarías crear una instancia de app aquí o pasarla para que esto funcione
#    # create_tables() 