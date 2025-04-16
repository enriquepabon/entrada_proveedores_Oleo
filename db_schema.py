"""
Definición del esquema de la base de datos SQLite para la aplicación de tiquetes.
Este archivo contiene las sentencias SQL para crear las tablas necesarias.
"""

import sqlite3
import logging
import os
from flask import current_app
import traceback

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

# --- NUEVO: Esquema para la tabla de Presupuesto Mensual --- 
CREATE_PRESUPUESTO_MENSUAL_TABLE = """
CREATE TABLE IF NOT EXISTS presupuesto_mensual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_presupuesto TEXT UNIQUE NOT NULL, -- Fecha del día del presupuesto (YYYY-MM-DD)
    toneladas_proyectadas REAL,          -- Cantidad proyectada en toneladas
    fecha_carga TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Cuándo se cargó/actualizó este dato
);
"""
# --- FIN NUEVO --- 

def create_tables():
    """
    Crea las tablas necesarias en la base de datos si no existen.
    Utiliza la ruta definida en la configuración de la aplicación.
    """
    conn = None # Initialize conn
    db_path = None # Initialize db_path
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

        # --- Paso 1: Crear todas las tablas ---
        logger.info(f"Ejecutando CREATE TABLE IF NOT EXISTS para todas las tablas en {db_path}...")
        cursor.execute(CREATE_ENTRY_RECORDS_TABLE)
        cursor.execute(CREATE_PESAJES_BRUTO_TABLE)
        cursor.execute(CREATE_CLASIFICACIONES_TABLE)
        cursor.execute(CREATE_PESAJES_NETO_TABLE)
        cursor.execute(CREATE_FOTOS_CLASIFICACION_TABLE)
        # -- Bloque específico para la tabla salidas --
        try:
            logger.info("Intentando ejecutar CREATE TABLE IF NOT EXISTS salidas...")
            cursor.execute(CREATE_SALIDAS_TABLE)
            logger.info("CREATE TABLE IF NOT EXISTS salidas ejecutado.")
            # Verificar si la tabla existe inmediatamente después
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='salidas'")
            if cursor.fetchone():
                logger.info("Tabla 'salidas' verificada y existe después de CREATE.")
            else:
                logger.error("¡ERROR! La tabla 'salidas' NO existe inmediatamente después de ejecutar CREATE TABLE.")
        except sqlite3.Error as e_create:
            logger.error(f"¡ERROR SQLite específico al ejecutar CREATE TABLE IF NOT EXISTS salidas: {e_create}")
            logger.error(traceback.format_exc())
            # Considerar si relanzar el error: raise e_create
        # -- Fin bloque específico --
        cursor.execute(CREATE_PRESUPUESTO_MENSUAL_TABLE)
        conn.commit() # Commit after creating tables
        logger.info("CREATE TABLE statements ejecutados.")

        # --- Paso 2: Verificar y añadir columnas faltantes ---
        logger.info(f"Verificando/Añadiendo columnas faltantes en {db_path}...")

        # --- Helper function to add column if not exists ---
        def add_column_if_not_exists(table_name, column_name, column_definition):
            try:
                # Check if the column exists using PRAGMA
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [column[1] for column in cursor.fetchall()]
                if column_name not in columns:
                    logger.info(f"Intentando añadir columna faltante '{column_name}' a la tabla {table_name}...")
                    try:
                        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")
                        logger.info(f"Columna '{column_name}' añadida exitosamente a {table_name}.")
                        conn.commit() # Commit after successful addition
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" in str(e).lower():
                             logger.warning(f"La columna '{column_name}' parece ya existir en {table_name} (error ALTER: {e})")
                        else:
                            logger.error(f"Error operacional SQLite añadiendo '{column_name}' a {table_name}: {e}")
                            raise e # Re-raise other operational errors
                # else:
                    # logger.debug(f"Columna '{column_name}' ya existe en {table_name}.") # Optional debug log

            except sqlite3.Error as e:
                 logger.error(f"Error SQLite verificando/añadiendo columna '{column_name}' a {table_name}: {e}")
                 # Consider re-raising depending on severity: raise e

        # --- Aplicar verificaciones/adiciones para cada tabla ---

        # entry_records
        add_column_if_not_exists('entry_records', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('entry_records', 'timestamp_registro_utc', 'TEXT')
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

        # pesajes_bruto
        add_column_if_not_exists('pesajes_bruto', 'timestamp_pesaje_utc', 'TEXT')
        add_column_if_not_exists('pesajes_bruto', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('pesajes_bruto', 'codigo_guia_transporte_sap', 'TEXT')

        # clasificaciones
        add_column_if_not_exists('clasificaciones', 'timestamp_clasificacion_utc', 'TEXT')
        add_column_if_not_exists('clasificaciones', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('clasificaciones', 'total_racimos_detectados', 'INTEGER')
        add_column_if_not_exists('clasificaciones', 'clasificacion_consolidada', 'TEXT')

        # pesajes_neto
        add_column_if_not_exists('pesajes_neto', 'timestamp_pesaje_neto_utc', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('pesajes_neto', 'peso_producto', 'REAL')
        add_column_if_not_exists('pesajes_neto', 'comentarios', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'tipo_pesaje_neto', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'respuesta_sap', 'TEXT')
        add_column_if_not_exists('pesajes_neto', 'peso_bruto', 'REAL')

        # salidas
        add_column_if_not_exists('salidas', 'timestamp_salida_utc', 'TEXT')
        add_column_if_not_exists('salidas', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists('salidas', 'comentarios_salida', 'TEXT')
        add_column_if_not_exists('salidas', 'firma_salida', 'TEXT')

        # fotos_clasificacion
        add_column_if_not_exists('fotos_clasificacion', 'fecha_creacion', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')

        # presupuesto_mensual (ejemplo)
        # add_column_if_not_exists('presupuesto_mensual', 'nueva_columna', 'TEXT')

        logger.info(f"Verificación/Adición de columnas completada para: {db_path}")
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        # Log específico del error durante la creación o verificación
        logger.error(f"Error durante la creación/verificación del esquema de la BD ({db_path}): {e}")
        logger.error(traceback.format_exc()) # Log completo del traceback
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