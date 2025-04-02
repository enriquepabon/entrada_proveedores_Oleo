"""
Definición del esquema de la base de datos SQLite para la aplicación de tiquetes.
Este archivo contiene las sentencias SQL para crear las tablas necesarias.
"""

import sqlite3
import logging
import os

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ruta a la base de datos
DB_PATH = 'tiquetes.db'

# Esquema de la tabla de registros de entrada
CREATE_ENTRY_RECORDS_TABLE = """
CREATE TABLE IF NOT EXISTS entry_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    nombre_proveedor TEXT,
    codigo_proveedor TEXT,
    fecha_registro TEXT,
    hora_registro TEXT,
    num_cedula TEXT,
    num_placa TEXT,
    conductor TEXT,
    tipo_fruta TEXT,
    lote TEXT,
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
    fecha_pesaje TEXT,
    hora_pesaje TEXT,
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
    fecha_clasificacion TEXT,
    hora_clasificacion TEXT,
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
    # Nuevas columnas para datos consolidados
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
    tipo_pesaje TEXT,
    tipo_pesaje_neto TEXT,
    fecha_pesaje TEXT,
    hora_pesaje TEXT,
    imagen_pesaje TEXT,
    comentarios TEXT,
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
    fecha_salida TEXT,
    hora_salida TEXT,
    comentarios_salida TEXT,
    nota_salida TEXT,
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
    """
    try:
        # Verificar si el directorio existe, crearlo si no
        db_dir = os.path.dirname(DB_PATH)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Crear tablas
        cursor.execute(CREATE_ENTRY_RECORDS_TABLE)
        cursor.execute(CREATE_PESAJES_BRUTO_TABLE)
        cursor.execute(CREATE_CLASIFICACIONES_TABLE)
        cursor.execute(CREATE_PESAJES_NETO_TABLE)
        cursor.execute(CREATE_FOTOS_CLASIFICACION_TABLE)
        cursor.execute(CREATE_SALIDAS_TABLE)
        
        conn.commit()
        logger.info("Tablas creadas correctamente en la base de datos.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error creando tablas en la base de datos: {e}")
        return False
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_tables() 