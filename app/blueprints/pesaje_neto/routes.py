from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import logging
import traceback
from datetime import datetime
import json
import glob
import sqlite3
import pytz
from app.blueprints.pesaje_neto import bp
from app.utils.common import CommonUtils as Utils
from flask_login import login_required
from werkzeug.utils import secure_filename

# Configurar logging
logger = logging.getLogger(__name__)

# Definir zona horaria de Bogotá
BOGOTA_TZ = pytz.timezone('America/Bogota')
UTC = pytz.utc

def get_utc_timestamp_str():
    """Generates the current UTC timestamp as a string."""
    return datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

def get_bogota_datetime():
    """
    Obtiene la fecha y hora actual en la zona horaria de Bogotá.
    Returns:
        tuple: (fecha_str, hora_str) en formato DD/MM/YYYY y HH:MM:SS
    """
    now_utc = datetime.now(pytz.UTC)
    now_bogota = now_utc.astimezone(BOGOTA_TZ)
    return now_bogota.strftime('%d/%m/%Y'), now_bogota.strftime('%H:%M:%S')

def ensure_pesajes_neto_schema():
    """
    Asegura que la tabla pesajes_neto tenga todas las columnas necesarias.
    """
    conn = None # Initialize conn
    try:
        # Use the configured DB path
        db_path = current_app.config['TIQUETES_DB_PATH'] 
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # --- INICIO MODIFICACIÓN: Crear tabla si no existe ---
        # Definición de la tabla obtenida de db_schema.py
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
        cursor.execute(CREATE_PESAJES_NETO_TABLE)
        conn.commit()
        # --- FIN MODIFICACIÓN ---

        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(pesajes_neto)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Añadir columnas faltantes
        columns_to_add = []
        
        if 'peso_producto' not in columns:
            columns_to_add.append("peso_producto REAL")
            
        if 'comentarios' not in columns:
            columns_to_add.append("comentarios TEXT")
            
        if 'tipo_pesaje_neto' not in columns:
            columns_to_add.append("tipo_pesaje_neto TEXT")
            
        if 'respuesta_sap' not in columns:
            columns_to_add.append("respuesta_sap TEXT")
            
        # Add new column for SAP support image
        if 'imagen_soporte_sap' not in columns:
            columns_to_add.append("imagen_soporte_sap TEXT")
            
        # Add new date/time columns if missing
        if 'fecha_pesaje_neto' not in columns:
            columns_to_add.append("fecha_pesaje_neto TEXT")
            
        if 'hora_pesaje_neto' not in columns:
            columns_to_add.append("hora_pesaje_neto TEXT")
            
        # Ejecutar alters para añadir columnas faltantes
        for column_def in columns_to_add:
            column_name = column_def.split()[0]
            logger.info(f"Añadiendo columna {column_name} a la tabla pesajes_neto")
            try:
                cursor.execute(f"ALTER TABLE pesajes_neto ADD COLUMN {column_def}")
                conn.commit()
                logger.info(f"Columna {column_name} añadida exitosamente")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.warning(f"La columna {column_name} ya existe en la tabla")
                else:
                    raise
                    
        # --- REMOVE OLD/INCORRECT COLUMNS --- 
        # Check if old columns exist and drop them if they do
        old_columns_to_drop = ['fecha_pesaje', 'hora_pesaje', 'imagen_pesaje']
        current_columns_info = {col[1]: col for col in cursor.execute("PRAGMA table_info(pesajes_neto)").fetchall()}
        
        for old_col in old_columns_to_drop:
            if old_col in current_columns_info:
                logger.warning(f"Encontrada columna obsoleta '{old_col}' en pesajes_neto. Se eliminará.")
                try:
                    # SQLite doesn't directly support DROP COLUMN in older versions easily.
                    # A common workaround is to recreate the table, but for simplicity, 
                    # we will log a warning and the code saving data should ignore these columns.
                    # cursor.execute(f"ALTER TABLE pesajes_neto DROP COLUMN {old_col}") # This might fail
                    # conn.commit()
                    # logger.info(f"Columna obsoleta '{old_col}' eliminada.")
                    logger.warning(f"Por favor, considera eliminar manualmente la columna '{old_col}' de la tabla pesajes_neto si causa problemas.")
                except sqlite3.OperationalError as drop_err:
                    logger.error(f"Error al intentar eliminar columna obsoleta '{old_col}': {drop_err}. Se continuará, pero considera limpieza manual.")
        # --- END REMOVE OLD COLUMNS ---
                    
        conn.commit()
        logger.info("Esquema de la tabla pesajes_neto verificado/actualizado")
        conn.close()
        return True
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada en la aplicación Flask.")
        if 'conn' in locals() and conn:
            conn.close()
        return False
    except Exception as e:
        logger.error(f"Error verificando/actualizando esquema de pesajes_neto: {str(e)}")
        if 'conn' in locals() and conn:
            conn.close()
        return False

@bp.route('/ver_resultados_pesaje_neto/<codigo_guia>')
@login_required
def ver_resultados_pesaje_neto(codigo_guia):
    """
    Muestra los resultados del pesaje neto para una guía específica.
    """
    try:
        # --- NUEVO: Asegurar que la tabla exista antes de consultar ---
        ensure_pesajes_neto_schema()
        # --- FIN NUEVO ---
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Obtener los datos más recientes de la base de datos
        conn = None # Initialize conn outside try
        try:
            # --- CORREGIDO: Usar la ruta configurada ---
            db_path = current_app.config['TIQUETES_DB_PATH']
            logger.info(f"[ver_resultados_pesaje_neto] Conectando a DB: {db_path}") # Log añadido
            conn = sqlite3.connect(db_path)
            # --- FIN CORRECCIÓN ---
            cursor = conn.cursor()
            # --- CORREGIDO: Seleccionar todos los campos relevantes de la tabla ---
            # Asegúrate que los nombres aquí coincidan EXACTAMENTE con la definición de la tabla
            cursor.execute(
                """
                SELECT peso_bruto, peso_tara, peso_neto, peso_producto,
                       timestamp_pesaje_neto_utc, comentarios, respuesta_sap, tipo_pesaje_neto,
                       imagen_soporte_sap
                FROM pesajes_neto
                WHERE codigo_guia = ?
                """, (codigo_guia,)
            )
            result = cursor.fetchone()

            if result:
                # --- CORREGIDO: Desempaquetar todos los campos recuperados ---
                (peso_bruto_db, peso_tara_db, peso_neto_db, peso_producto_db,
                 timestamp_pesaje_neto_utc, comentarios_db, respuesta_sap_db, tipo_pesaje_neto_db,
                 imagen_soporte_sap_db) = result
                 
                # Convertir timestamp a fecha y hora local
                fecha_pesaje_neto, hora_pesaje_neto = convertir_timestamp_a_fecha_hora(timestamp_pesaje_neto_utc)
                
                # Actualizar los datos con los valores más recientes de la DB
                datos_guia.update({
                    'peso_bruto': peso_bruto_db, # Añadir peso bruto recuperado
                    'peso_tara': peso_tara_db,
                    'peso_neto': peso_neto_db,
                    'peso_producto': peso_producto_db, # Añadir peso producto recuperado
                    'fecha_pesaje_neto': fecha_pesaje_neto,
                    'hora_pesaje_neto': hora_pesaje_neto,
                    'timestamp_pesaje_neto_utc': timestamp_pesaje_neto_utc, # Guardar también el UTC
                    'comentarios_neto': comentarios_db,
                    'respuesta_sap': respuesta_sap_db,
                    'tipo_pesaje_neto': tipo_pesaje_neto_db, # Añadir tipo pesaje neto
                    'imagen_soporte_sap': imagen_soporte_sap_db, # Añadir ruta de imagen de soporte SAP
                    'pesaje_neto_completado': True # Marcar como completado si se encontraron datos
                })
                logger.info(f"Datos actualizados desde la base de datos: bruto={peso_bruto_db}, tara={peso_tara_db}, neto={peso_neto_db}, producto={peso_producto_db}, imagen_sap={imagen_soporte_sap_db}")
            else:
                 # --- NUEVO: Log si no se encuentran datos en pesajes_neto ---
                 logger.warning(f"No se encontraron datos en la tabla pesajes_neto para la guía {codigo_guia}. Se mostrarán los datos de get_datos_guia.")
                 # Asegurar que el estado refleje que no se completó el pesaje neto si no hay datos
                 datos_guia['pesaje_neto_completado'] = False
                 # Puedes poner valores por defecto si es necesario
                 datos_guia.setdefault('peso_bruto', 'N/A') # Mantener el bruto si viene de la guía
                 datos_guia.setdefault('peso_tara', 'N/A')
                 datos_guia.setdefault('peso_neto', 'N/A')
                 datos_guia.setdefault('peso_producto', 'N/A')
                 datos_guia.setdefault('fecha_pesaje_neto', 'N/A')
                 datos_guia.setdefault('hora_pesaje_neto', 'N/A')
                 datos_guia.setdefault('tipo_pesaje_neto', 'N/A')
                 datos_guia.setdefault('imagen_soporte_sap', None) # Asegurar que exista la clave
        except sqlite3.Error as db_error: # Capturar específicamente errores de DB
            logger.error(f"Error SQLite recuperando datos de la base de datos: {str(db_error)}")
            logger.error(traceback.format_exc()) # Log completo
            # Establecer valores por defecto o marcar error en datos_guia si falla la DB
            datos_guia['pesaje_neto_completado'] = False
            datos_guia.setdefault('peso_neto', 'Error DB')
            # ... otros defaults si es necesario ...
        except Exception as e:
            logger.error(f"Error general recuperando datos de la base de datos: {str(e)}")
            logger.error(traceback.format_exc()) # Log completo
            datos_guia['pesaje_neto_completado'] = False
            datos_guia.setdefault('peso_neto', 'Error General')
        finally:
            # --- CORREGIDO: Usar la variable 'conn' definida fuera del try ---
            if conn:
                conn.close()
            # --- FIN CORRECCIÓN ---

        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia
        }
        
        return render_template('resultados_pesaje_neto.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

@bp.route('/registrar_peso_neto_directo', methods=['POST'])
@login_required
def registrar_peso_neto_directo():
    """Registra el peso neto para una guía específica usando el método directo."""
    
    # Asegurar que la tabla pesajes_neto tenga todas las columnas necesarias
    ensure_pesajes_neto_schema()
    
    # Inicializar variables
    error_message = None
    data_received = {}
    conn = None # Initialize conn
    
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        db_path = current_app.config['TIQUETES_DB_PATH'] # Get DB path
        
        logger.info("Procesando solicitud de registro de peso neto directo")
        
        # Obtener fecha y hora en zona horaria de Bogotá - REMOVED
        # fecha_actual, hora_actual = get_bogota_datetime()
        timestamp_utc = get_utc_timestamp_str() # USAR UTC
        
        # Obtener datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        peso_tara = request.form.get('peso_tara')
        peso_neto = request.form.get('peso_neto')
        comentarios = request.form.get('comentarios', '')
        respuesta_sap = request.form.get('respuesta_sap')
        
        # --- INICIO: Gestión de la imagen de soporte SAP ---
        imagen_soporte_sap_path = None
        if 'imagen' in request.files:
            imagen_file = request.files['imagen']
            if imagen_file and imagen_file.filename != '':
                original_filename = secure_filename(imagen_file.filename)
                
                # --- INICIO: Generar nombre de archivo único ---
                # El timestamp_utc ya se obtiene antes con get_utc_timestamp_str()
                # El codigo_guia ya se obtiene antes con request.form.get('codigo_guia')
                timestamp_sanitized = timestamp_utc.replace(":", "-").replace(" ", "_") # ej: 2023-10-27_15-30-00
                
                name_part, ext_part = os.path.splitext(original_filename)
                if not ext_part: # Asegurar que haya una extensión
                    # Default a .png si no hay extensión (ej. captura de pantalla sin extensión explícita)
                    ext_part = '.png' 
                
                # Construir el nuevo nombre de archivo único
                # Asegurarse de que codigo_guia es válido para un nombre de archivo
                safe_codigo_guia = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in str(codigo_guia))
                unique_filename = f"{safe_codigo_guia}_{timestamp_sanitized}{ext_part}"
                # --- FIN: Generar nombre de archivo único ---

                upload_folder = os.path.join(current_app.config['BASE_DIR'], 'static', 'fotos_pesaje_neto')
                
                logger.info(f"Intentando crear directorio: {upload_folder}")
                os.makedirs(upload_folder, exist_ok=True) # Asegurar que el directorio exista
                
                # Usar unique_filename para guardar
                save_path = os.path.join(upload_folder, unique_filename)
                logger.info(f"Ruta de guardado completa para la imagen: {save_path}")
                
                try:
                    imagen_file.save(save_path)
                    logger.info(f"ÉXITO: Imagen de soporte SAP guardada en: {save_path}")
                    
                    # --- INICIO: Verificar existencia del archivo --- 
                    if os.path.exists(save_path):
                        logger.info(f"VERIFICADO: El archivo {save_path} existe en el disco después de guardar.")
                        # Usar unique_filename para la ruta en DB
                        imagen_soporte_sap_path = os.path.join('fotos_pesaje_neto', unique_filename).replace("\\\\", "/")
                    else:
                        logger.error(f"ERROR DE VERIFICACIÓN: El archivo {save_path} NO se encontró en el disco después de guardar.")
                        imagen_soporte_sap_path = None # No guardar ruta si el archivo no está realmente allí
                    # --- FIN: Verificar existencia del archivo --- 

                except Exception as e:
                    logger.error(f"ERROR AL GUARDAR IMAGEN DE SOPORTE SAP en {save_path}: {str(e)}")
                    logger.error(traceback.format_exc())
                    imagen_soporte_sap_path = None # No guardar la ruta en DB si el archivo no se pudo guardar
            else:
                logger.info("No se proporcionó un archivo de imagen válido o el nombre del archivo está vacío.")
        else:
            logger.info("No se encontró 'imagen' en request.files.")
        # --- FIN: Gestión de la imagen de soporte SAP ---
                
        data_received = {k: v for k, v in request.form.items()}
        logger.info(f"Datos recibidos para pesaje neto directo: {data_received}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara or not peso_neto:
            error_message = "El peso tara y peso neto son obligatorios"
            raise ValueError(error_message)
        
        # Convertir pesos a float para asegurar precisión
        try:
            peso_tara = float(peso_tara)
            peso_neto = float(peso_neto)
        except ValueError:
            error_message = "Los valores de peso deben ser numéricos"
            raise ValueError(error_message)
            
        # Obtener datos originales de la guía (incluyendo peso bruto)
        datos_originales = utils.get_datos_guia(codigo_guia)
        if not datos_originales:
            error_message = "No se encontraron los datos originales de la guía"
            raise ValueError(error_message)
            
        # Calcular peso_producto (Tara - Bruto) -> REVERTIDO: Calcular como Bruto - Tara 
        # -> AJUSTE FINAL: Asignar peso_neto como peso_producto
        peso_producto = peso_neto # Asignar peso_neto directamente
        
        logger.info(f"Pesos validados: tara={peso_tara}, neto={peso_neto}, producto={peso_producto}")
        
        # Modificar el JSON de respuesta_sap antes de guardarlo
        if respuesta_sap:
            try:
                respuesta_sap_dict = json.loads(respuesta_sap)
                # Asegurar que peso_neto (string) exista antes de usarlo
                peso_neto_str = str(peso_neto) if peso_neto is not None else '0.0'
                respuesta_sap_dict['peso_producto_valor'] = peso_neto_str
                respuesta_sap_dict['peso_producto'] = f"{peso_neto_str} kg"
                respuesta_sap = json.dumps(respuesta_sap_dict) # Convertir de nuevo a JSON string
                logger.info(f"respuesta_sap JSON modificado para igualar peso_neto: {respuesta_sap}")
            except json.JSONDecodeError as json_err:
                logger.error(f"Error procesando respuesta_sap JSON: {json_err}. Se guardará el original.")
            except Exception as e:
                logger.error(f"Error inesperado modificando respuesta_sap: {e}")
        # --- FIN MODIFICACIÓN ---
        
        # Actualizar directamente en la base de datos
        try:
            # --- AUMENTAR TIMEOUT ---
            conn = sqlite3.connect(db_path, timeout=10) # Timeout de 10 segundos
            # --- FIN AUMENTAR TIMEOUT ---
            cursor = conn.cursor()
            
            # Primero verificar si existe el registro
            cursor.execute("SELECT 1 FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # Actualizar registro existente
                cursor.execute("""
                    UPDATE pesajes_neto 
                    SET peso_tara = ?, peso_neto = ?, peso_producto = ?, 
                        timestamp_pesaje_neto_utc = ?,
                        tipo_pesaje_neto = ?, comentarios = ?, respuesta_sap = ?, 
                        peso_bruto = ?, imagen_soporte_sap = ?
                    WHERE codigo_guia = ?
                """, (
                    peso_tara,
                    peso_neto,
                    peso_producto,
                    timestamp_utc,
                    'directo',
                    comentarios,
                    respuesta_sap,
                    datos_originales.get('peso_bruto'),
                    imagen_soporte_sap_path, # Añadir ruta de imagen
                    codigo_guia
                ))
            else:
                # Insertar nuevo registro
                cursor.execute("""
                    INSERT INTO pesajes_neto (
                        codigo_guia, peso_tara, peso_neto, peso_producto, 
                        timestamp_pesaje_neto_utc, tipo_pesaje_neto,
                        comentarios, respuesta_sap, codigo_proveedor, nombre_proveedor, peso_bruto,
                        imagen_soporte_sap
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    codigo_guia,
                    peso_tara,
                    peso_neto,
                    peso_producto,
                    timestamp_utc,
                    'directo',
                    comentarios,
                    respuesta_sap,
                    datos_originales.get('codigo_proveedor'),
                    datos_originales.get('nombre_proveedor'),
                    datos_originales.get('peso_bruto'),
                    imagen_soporte_sap_path # Añadir ruta de imagen
                ))
            
            conn.commit()
            logger.info(f"Datos actualizados en la base de datos para guía {codigo_guia}")
            
        except sqlite3.Error as db_e:
            logger.error(f"Error actualizando la base de datos: {str(db_e)}")
            if "no column named" in str(db_e):
                error_message = f"Error de base de datos: {db_e}. Por favor, verifica la estructura de la tabla."
            else:
                error_message = f"Error de base de datos al guardar pesaje neto: {db_e}"
            raise sqlite3.Error(error_message)
        except Exception as e:
            logger.error(f"Error inesperado durante la operación de base de datos: {str(e)}")
            error_message = f"Error inesperado: {str(e)}"
            raise
        finally:
            if conn:
                conn.close()
        
        # Actualizar solo los datos del pesaje en la UI, manteniendo los datos originales del proveedor
        datos_ui = {
            'peso_tara': peso_tara,
            'peso_neto': peso_neto,
            'peso_producto': peso_producto,
            'tipo_pesaje_neto': 'directo',
            'timestamp_pesaje_neto_utc': timestamp_utc,
            'comentarios_neto': comentarios,
            'respuesta_sap': respuesta_sap,
            'imagen_soporte_sap': imagen_soporte_sap_path, # Añadir al diccionario de datos UI
            'pesaje_neto_completado': True
        }
        
        # Combine with original data fetched earlier, ensuring peso_bruto is present
        datos_originales.update(datos_ui)
        
        # Guardar los datos actualizados (using the combined dict)
        if utils.update_datos_guia(codigo_guia, datos_originales): # Save combined data
            logger.info(f"Pesaje neto directo guardado correctamente para guía {codigo_guia}")
            
            return jsonify({
                'success': True,
                'message': 'Pesaje neto registrado correctamente',
                'redirect_url': url_for('pesaje_neto.ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
            })
        else:
            logger.error(f"Error al guardar pesaje neto directo para {codigo_guia} (en utils.update_datos_guia)")
            error_message = "No se pudo guardar el pesaje neto (error post-DB)"
            # Even if DB save was ok, if update_datos_guia fails, report error
            return jsonify({
                'success': False,
                'message': error_message
            }), 500 # Internal server error
            
    except (ValueError, sqlite3.Error) as ve:
        # Catch validation errors and DB errors raised earlier
        logger.error(f"Error (Validation/DB) al registrar peso neto directo: {str(ve)}")
        logger.error(f"Datos recibidos: {data_received}")
        # Use the error message set in the specific exception block if available
        final_error_message = error_message or str(ve) 
        return jsonify({
            'success': False,
            'message': final_error_message
        }), 400 # Bad request for validation, potentially 500 for DB
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Error general al registrar peso neto directo: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        final_error_message = error_message or f"Error inesperado al registrar peso neto: {str(e)}"
        
        return jsonify({
            'success': False,
            'message': final_error_message
        }), 500 # Internal Server Error

@bp.route('/registrar_peso_neto', methods=['POST'])
@login_required
def registrar_peso_neto():
    """Registra el peso neto para una guía específica."""
    
    # Asegurar que la tabla pesajes_neto tenga el esquema correcto
    ensure_pesajes_neto_schema()
    
    error_message = None
    data_received = {}
    conn = None
    
    try:
        # Inicializar Utils y obtener la ruta de la DB
        utils = current_app.config.get('utils', Utils(current_app))
        db_path = current_app.config['TIQUETES_DB_PATH']
        
        # Obtener datos de la solicitud (JSON o Formulario)
        if request.is_json:
            data = request.get_json()
            data_received = data
        else:
            data = request.form
            data_received = {k: v for k, v in data.items()}

        codigo_guia = data.get('codigo_guia')
        peso_tara_str = data.get('peso_tara')
        
        logger.info(f"Registrando pesaje neto para guía {codigo_guia}. Datos recibidos: {data_received}")
        
        # Validar datos requeridos
        if not codigo_guia:
            raise ValueError("El código de guía es obligatorio")
        if not peso_tara_str:
            raise ValueError("El peso tara es obligatorio")
            
        # Convertir peso tara a float
        try:
            peso_tara = float(peso_tara_str)
        except ValueError:
            raise ValueError("El peso tara debe ser un valor numérico")

        # Obtener datos originales de la guía (incluyendo peso bruto)
        datos_originales = utils.get_datos_guia(codigo_guia)
        if not datos_originales:
            raise ValueError(f"No se encontraron datos originales para la guía {codigo_guia}")
        
        peso_bruto_str = datos_originales.get('peso_bruto')
        
        # Calcular peso neto y peso producto
        peso_neto = None
        peso_producto = None
        if peso_bruto_str and peso_bruto_str != 'Pendiente' and peso_bruto_str != 'N/A':
             try:
                 peso_bruto = float(peso_bruto_str)
                 peso_neto = round(peso_bruto - peso_tara, 3)
                 # Asumimos que peso_producto es igual a peso_neto en este contexto
                 peso_producto = peso_neto 
             except (ValueError, TypeError):
                 logger.warning(f"No se pudo calcular peso neto/producto para {codigo_guia}. Peso bruto: {peso_bruto_str}")
                 raise ValueError("No se pudo calcular el peso neto debido a un valor de peso bruto inválido.")
        else:
             raise ValueError("El peso bruto no está disponible para calcular el peso neto.")

        # Obtener fecha y hora en zona horaria de Bogotá - REMOVED
        # fecha_actual, hora_actual = get_bogota_datetime()
        timestamp_utc = get_utc_timestamp_str() # USAR UTC

        # Preparar datos para la base de datos
        datos_db = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara,
            'peso_neto': peso_neto,
            'peso_producto': peso_producto,
            # 'fecha_pesaje_neto': fecha_actual, # REMOVED local date/time
            # 'hora_pesaje_neto': hora_actual,  # REMOVED local date/time
            'timestamp_pesaje_neto_utc': timestamp_utc, # USAR UTC
            'tipo_pesaje_neto': data.get('tipo_pesaje_neto', 'formulario'), # Indicar origen
            'comentarios': data.get('comentarios', ''),
            'respuesta_sap': data.get('respuesta_sap', ''), # Si viene de SAP
            'codigo_proveedor': datos_originales.get('codigo_proveedor'),
            'nombre_proveedor': datos_originales.get('nombre_proveedor'),
            'peso_bruto': peso_bruto # Guardar el peso bruto usado para el cálculo
        }
        
        # Guardar en la base de datos
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Usar INSERT OR REPLACE para simplificar (o verificar y luego INSERT/UPDATE como en directo)
        column_names = ', '.join(datos_db.keys())
        placeholders = ', '.join(['?'] * len(datos_db))
        values = list(datos_db.values())
        
        try:
            # Intenta insertar primero
            cursor.execute(f"INSERT INTO pesajes_neto ({column_names}) VALUES ({placeholders})", values)
            logger.info(f"Insertado nuevo registro de pesaje neto para {codigo_guia}")
        except sqlite3.IntegrityError:
            # Si ya existe (por codigo_guia UNIQUE), actualiza
            update_set = ', '.join([f"{key} = ?" for key in datos_db if key != 'codigo_guia'])
            update_values = [v for k, v in datos_db.items() if k != 'codigo_guia'] + [codigo_guia]
            cursor.execute(f"UPDATE pesajes_neto SET {update_set} WHERE codigo_guia = ?", update_values)
            logger.info(f"Actualizado registro existente de pesaje neto para {codigo_guia}")
            
        conn.commit()
        logger.info(f"Pesaje neto registrado/actualizado en DB para {codigo_guia}")

        # Actualizar datos en sesión si es necesario (o si la lógica lo requiere)
        session['codigo_guia'] = codigo_guia
        session['peso_tara'] = peso_tara
        session['peso_neto'] = peso_neto

        # Determinar redirección o respuesta JSON
        redirect_url = url_for('pesaje_neto.ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
        if request.is_json:
            return jsonify({
                'status': 'success',
                'message': 'Pesaje neto registrado correctamente',
                'redirect_url': redirect_url
            })
        else:
            flash('Pesaje neto registrado correctamente.', 'success')
            return redirect(redirect_url)

    except (ValueError, sqlite3.Error) as ve:
        error_msg = str(ve)
        logger.error(f"Error (Validation/DB) al registrar peso neto: {error_msg}")
        logger.error(f"Datos recibidos: {data_received}")
        if request.is_json:
             return jsonify({'status': 'error', 'message': error_msg}), 400
        else:
             flash(error_msg, 'danger')
             # Redirigir a alguna vista relevante, tal vez la vista centralizada o el formulario
             # Si codigo_guia está disponible, redirige al formulario de pesaje neto
             if 'codigo_guia' in data_received and data_received['codigo_guia']:
                 return redirect(url_for('.pesaje_neto', codigo_guia=data_received['codigo_guia']))
             else: # Si no hay código guía, redirige a la página principal o de búsqueda
                 return redirect(url_for('misc.upload_file')) 
                 
    except Exception as e:
        error_msg = f"Error inesperado al registrar pesaje neto: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if request.is_json:
            return jsonify({'status': 'error', 'message': error_msg}), 500
        else:
            flash(error_msg, 'danger')
            # Redirigir de forma segura
            if 'codigo_guia' in data_received and data_received['codigo_guia']:
                 return redirect(url_for('.pesaje_neto', codigo_guia=data_received['codigo_guia']))
            else: 
                 return redirect(url_for('misc.upload_file'))
                 
    finally:
        if conn:
            conn.close()

@bp.route('/pesaje/<codigo_guia>')
@login_required
def pesaje_neto(codigo_guia):
    """Muestra el formulario de pesaje neto."""
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener datos originales de la guía
        datos = utils.get_datos_guia(codigo_guia)
        if not datos:
            flash("No se encontró la guía especificada", "error")
            return redirect(url_for('misc.upload_file'))
            
        logger.info(f"Datos recuperados para pesaje neto: {datos}")
        
        # --- NUEVO: Asegurar que fecha_registro y hora_registro se calculen --- 
        if datos.get('timestamp_registro_utc'):
            try:
                fecha_local, hora_local = convertir_timestamp_a_fecha_hora(datos['timestamp_registro_utc'])
                datos['fecha_registro'] = fecha_local
                datos['hora_registro'] = hora_local
            except Exception as e:
                 logger.warning(f"Error al convertir timestamp para {codigo_guia} en pesaje_neto: {e}")
                 datos['fecha_registro'] = datos.get('fecha_registro', 'Error Conv')
                 datos['hora_registro'] = datos.get('hora_registro', '')
        # --- FIN NUEVO ---
        
        return render_template('pesaje/pesaje_neto.html', datos=datos)
        
    except Exception as e:
        logger.error(f"Error al mostrar formulario de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar formulario: {str(e)}", "error")
        return redirect(url_for('misc.upload_file'))

def convertir_timestamp_a_fecha_hora(timestamp_utc):
    if not timestamp_utc or timestamp_utc in [None, '', 'N/A']:
        return None, None
    utc_dt = datetime.strptime(timestamp_utc, '%Y-%m-%d %H:%M:%S')
    utc_dt = pytz.utc.localize(utc_dt)
    bogota_dt = utc_dt.astimezone(pytz.timezone('America/Bogota'))
    return bogota_dt.strftime('%d/%m/%Y'), bogota_dt.strftime('%H:%M:%S')



