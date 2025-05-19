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
    is_madre INTEGER DEFAULT 0, -- 0 = Normal, 1 = Madre
    hijas_str TEXT, -- Códigos de guías hijas separados por comas o saltos de línea
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
    -- Columnas que faltaban para el proceso automático
    timestamp_fin_auto TEXT,
    tiempo_procesamiento_auto REAL,
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

# --- NUEVO: Esquema para la tabla de Usuarios --- 
CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER DEFAULT 0,  -- 0 para False, 1 para True
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# --- NUEVO: Esquema para la tabla de Registro de Entrada de Graneles ---
CREATE_REGISTRO_ENTRADA_GRANELES_TABLE = """
CREATE TABLE IF NOT EXISTS RegistroEntradaGraneles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    producto TEXT,
    fecha_autorizacion TEXT,
    placa TEXT,
    trailer TEXT,
    cedula_conductor TEXT,
    nombre_conductor TEXT,
    origen TEXT,
    destino TEXT,
    timestamp_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_registro TEXT, -- ej: 'gsheet', 'manual'
    observaciones TEXT,
    usuario_registro TEXT -- NUEVO CAMPO PARA GUARDAR EL USUARIO QUE REGISTRA
);
"""

# --- NUEVO: Esquema para la tabla de Primer Pesaje de Graneles ---
CREATE_PRIMER_PESAJE_GRANEL_TABLE = """
CREATE TABLE IF NOT EXISTS PrimerPesajeGranel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_registro_granel INTEGER,
    peso_primer_kg REAL,
    codigo_sap_granel TEXT,
    timestamp_primer_pesaje TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_pesaje TEXT,
    foto_soporte_path TEXT,
    FOREIGN KEY (id_registro_granel) REFERENCES RegistroEntradaGraneles(id)
);
"""

# --- NUEVO: Esquema para la tabla de Control de Calidad de Graneles ---
CREATE_CONTROL_CALIDAD_GRANEL_TABLE = """
CREATE TABLE IF NOT EXISTS ControlCalidadGranel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    id_registro_granel INTEGER,
    parametros_calidad TEXT, -- Almacenar como JSON string
    resultado_calidad TEXT, -- ej: 'Aprobado', 'Rechazado', 'Con Observaciones'
    observaciones_calidad TEXT,
    timestamp_calidad TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    usuario_calidad TEXT,
    foto_soporte_calidad_path TEXT, -- Para la foto del control de calidad
    FOREIGN KEY (id_registro_granel) REFERENCES RegistroEntradaGraneles(id)
);
"""

def create_tables():
    """
    Crea las tablas necesarias en la base de datos si no existen.
    Utiliza la ruta definida en la configuración de la aplicación.
    """
    conn = None 
    db_path = None 
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        logger.info(f"[create_tables] DEBUG: Intentando usar DB path: {db_path}")

        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logger.info(f"Directorio de base de datos creado: {db_dir}")

        conn = sqlite3.connect(db_path)
        # No establecer row_factory aquí para add_column_if_not_exists, PRAGMA table_info devuelve tuplas
        # conn.row_factory = sqlite3.Row 

        cursor = conn.cursor() # Cursor principal para CREATE TABLE

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
        cursor.execute(CREATE_USERS_TABLE)
        cursor.execute(CREATE_REGISTRO_ENTRADA_GRANELES_TABLE)
        cursor.execute(CREATE_PRIMER_PESAJE_GRANEL_TABLE)
        cursor.execute(CREATE_CONTROL_CALIDAD_GRANEL_TABLE)
        conn.commit() # Commit después de todos los CREATE TABLE
        logger.info("CREATE TABLE statements ejecutados y commit realizado.")

        # --- Helper function to add column if not exists --- (Modificada)
        def add_column_if_not_exists(conn_local, table_name, column_name, column_definition):
            cursor_local = None # Inicializar cursor_local
            try:
                # Usar un cursor dedicado para PRAGMA y ALTER dentro de esta función
                cursor_local = conn_local.cursor()
                cursor_local.execute(f"PRAGMA table_info({table_name})")
                columns = [column_info[1] for column_info in cursor_local.fetchall()] # PRAGMA devuelve tuplas
                
                if column_name not in columns:
                    logger.info(f"Intentando añadir columna faltante '{column_name}' ({column_definition}) a la tabla {table_name}...")
                    try:
                        alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
                        cursor_local.execute(alter_sql)
                        conn_local.commit() # Commit inmediato después de ALTER exitoso
                        logger.info(f"Columna '{column_name}' añadida y commit realizado para {table_name}.")
                    except sqlite3.OperationalError as e_alter:
                        if "duplicate column name" in str(e_alter).lower():
                             logger.warning(f"Intento de ALTER fallido: La columna '{column_name}' ya parece existir en {table_name} (SQLite dice: {e_alter})")
                        else:
                            logger.error(f"Error operacional SQLite añadiendo '{column_name}' a {table_name}: {e_alter}")
                            # No hacer rollback aquí, podría interferir con otras operaciones de create_tables
                            # Dejar que el bloque principal de create_tables maneje el rollback general si es necesario.
                # else:
                    # logger.debug(f"Columna '{column_name}' ya existe en {table_name}.")
            except sqlite3.Error as e_pragma:
                 logger.error(f"Error SQLite general verificando/añadiendo columna '{column_name}' a {table_name} (PRAGMA o chequeo): {e_pragma}")
            finally:
                if cursor_local:
                    cursor_local.close()

        logger.info(f"Verificando/Añadiendo columnas faltantes en {db_path}...")

        # --- Aplicar verificaciones/adiciones para cada tabla y columna --- 
        # (Ejemplo para entry_records)
        # add_column_if_not_exists(conn, 'entry_records', 'nueva_col_test', 'TEXT')

        # --- Verificaciones para RegistroEntradaGraneles --- 
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'producto', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'fecha_autorizacion', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'placa', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'trailer', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'cedula_conductor', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'nombre_conductor', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'origen', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'destino', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'timestamp_registro', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP') # El default puede que no se aplique con ALTER
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'tipo_registro', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'observaciones', 'TEXT')
        add_column_if_not_exists(conn, 'RegistroEntradaGraneles', 'usuario_registro', 'TEXT') # Clave aquí

        # --- Verificaciones para PrimerPesajeGranel ---
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'id_registro_granel', 'INTEGER')
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'peso_primer_kg', 'REAL')
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'codigo_sap_granel', 'TEXT')
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'timestamp_primer_pesaje', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'usuario_pesaje', 'TEXT')
        add_column_if_not_exists(conn, 'PrimerPesajeGranel', 'foto_soporte_path', 'TEXT')

        # --- Verificaciones para ControlCalidadGranel ---
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'id_registro_granel', 'INTEGER')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'parametros_calidad', 'TEXT')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'resultado_calidad', 'TEXT')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'observaciones_calidad', 'TEXT')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'timestamp_calidad', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'usuario_calidad', 'TEXT')
        add_column_if_not_exists(conn, 'ControlCalidadGranel', 'foto_soporte_calidad_path', 'TEXT')
        
        # Commit final si hubo otras modificaciones por add_column_if_not_exists que no hicieron commit individual
        # Aunque la versión modificada de add_column_if_not_exists hace commit individual para ALTERs.
        # Este commit es más para asegurar cualquier otra operación pendiente antes de cerrar.
        # conn.commit() # Comentado si add_column_if_not_exists ya hace commits individuales para ALTERs.

        logger.info(f"Verificación/Adición de columnas completada para: {db_path}")
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error durante la creación/verificación del esquema de la BD ({db_path}): {e}")
        logger.error(traceback.format_exc())
        if conn: 
            conn.rollback() # Rollback general si hay un error mayor en create_tables
        return False
    finally:
        if cursor: # Cerrar cursor principal
            cursor.close()
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