from flask import Flask, render_template
import os
import logging
from config import app as app_config
import db_schema
import secrets
from werkzeug.middleware.proxy_fix import ProxyFix
# Importar la función del filtro
from .utils.common import format_datetime_filter, format_number_es
# Importar Flask-Login
from flask_login import LoginManager

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Instanciar LoginManager globalmente o dentro de create_app
# Es común hacerlo globalmente y luego inicializarlo
login_manager = LoginManager()
# Configurar la vista a la que redirigir si el usuario no está logueado
# Usaremos 'auth.login' que crearemos más adelante en el blueprint 'auth'
login_manager.login_view = 'auth.login'
# Opcional: Mensaje flash que se mostrará al usuario redirigido
login_manager.login_message = "Por favor, inicia sesión para acceder a esta página."
login_manager.login_message_category = "info"

# Callback para recargar el objeto usuario desde el ID de usuario almacenado en la sesión
@login_manager.user_loader
def load_user(user_id):
    # Importamos la función aquí para evitar importaciones circulares si
    # auth_utils necesitara importar algo de __init__ en el futuro.
    from app.utils.auth_utils import get_user_by_id
    try:
        return get_user_by_id(int(user_id))
    except ValueError:
        # Si user_id no es un entero válido
        return None
    except Exception as e:
        # Loguear cualquier otro error inesperado durante la carga del usuario
        logger.error(f"Error cargando usuario {user_id}: {e}")
        return None

def create_app(test_config=None):
    """
    Función de fábrica para crear la aplicación Flask
    """
    # Obtener BASE_DIR de la configuración si se pasó
    base_dir = test_config.get('BASE_DIR') if test_config else None
    if not base_dir:
        # Fallback si BASE_DIR no se pasó (no debería ocurrir si run.py está bien)
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        logger.warning(f"BASE_DIR no encontrado en la configuración, usando fallback: {base_dir}")

    # Definir rutas absolutas para static y templates
    static_folder_path = os.path.join(base_dir, 'static')
    template_folder_path = os.path.join(base_dir, 'templates')

    # Crear la instancia de la aplicación Flask con rutas absolutas
    app = Flask(__name__,
                template_folder=template_folder_path,
                static_folder=static_folder_path,
                instance_relative_config=True)
    
    # --- Establecer SECRET_KEY directamente --- # <-- ELIMINAR/COMENTAR BLOQUE
    # app.secret_key = os.environ.get('FLASK_SECRET_KEY')
    # if not app.secret_key:
    #     logger.error("¡ERROR CRÍTICO! La variable de entorno FLASK_SECRET_KEY no está definida.")
    #     # Podrías lanzar una excepción aquí o usar una clave por defecto insegura para desarrollo
    #     # raise ValueError("FLASK_SECRET_KEY no definida")
    #     app.secret_key = 'clave-insegura-solo-desarrollo-definir-env' # Fallback inseguro
    #     logger.warning("Usando clave secreta insegura por defecto.")
    # else:
    #      logger.info(f"SECRET_KEY cargada directamente en app desde variable de entorno: {app.secret_key[:8]}...")
    # ------------------------------------- # <-- ELIMINAR/COMENTAR BLOQUE
    
    # Guardar BASE_DIR en la configuración de la app para usarlo después
    app.config['BASE_DIR'] = base_dir
    
    # Aplicar configuración desde parámetro test_config si existe
    if test_config is not None:
        # Excluir BASE_DIR para evitar sobreescribir la que ya establecimos
        config_to_update = {k: v for k, v in test_config.items() if k != 'BASE_DIR'}
        app.config.update(config_to_update)
        logger.info(f"Aplicada configuración externa (excluyendo BASE_DIR si estaba): {config_to_update}")
        
        # Configurar correctamente SERVER_NAME si está definido
        if 'SERVER_NAME' in test_config:
            logger.info(f"SERVER_NAME configurado: {test_config['SERVER_NAME']}")
    
    # NUEVO: Limpiar QRs problemáticos al iniciar la aplicación
    try:
        import glob
        
        # Usar static_folder_path absoluto
        qr_folder_path = os.path.join(static_folder_path, 'qr')
        
        # QRs específicamente problemáticos a eliminar de forma permanente
        specific_problem_qrs = [
            os.path.join(qr_folder_path, 'default_qr_20250311143540.png'),
            os.path.join(qr_folder_path, 'default_qr.png')
        ]
        
        # Eliminar los archivos problemáticos permanentemente
        for qr_path in specific_problem_qrs:
            if os.path.exists(qr_path):
                try:
                    os.remove(qr_path)
                    logger.info(f"QR problemático eliminado permanentemente: {qr_path}")
                except Exception as e:
                    # Si falla la eliminación, intentar renombrar
                    try:
                        backup_path = f"{qr_path}.deleted"
                        os.rename(qr_path, backup_path)
                        logger.info(f"QR problemático renombrado a {backup_path} (no se pudo eliminar)")
                    except Exception as rename_error:
                        logger.error(f"Error al eliminar/renombrar QR problemático {qr_path}: {str(rename_error)}")
        
        # Patrón para limpiar archivos similares (búsqueda con glob)
        problem_qr_patterns = [
            os.path.join(qr_folder_path, 'default_qr*.png'),
            os.path.join(qr_folder_path, 'default_qr*_*.png')
        ]
        
        for qr_pattern in problem_qr_patterns:
            matching_files = glob.glob(qr_pattern)
            for old_qr in matching_files:
                # No volver a procesar los que ya se han eliminado específicamente
                if old_qr not in specific_problem_qrs and os.path.exists(old_qr):
                    try:
                        # Renombrar en lugar de eliminar para preservar historial
                        backup_path = f"{old_qr}.old"
                        os.rename(old_qr, backup_path)
                        logger.info(f"QR problemático renombrado al iniciar: {old_qr} → {backup_path}")
                    except Exception as qr_err:
                        logger.error(f"Error renombrando QR problemático: {str(qr_err)}")
    except Exception as e:
        logger.error(f"Error limpiando QRs problemáticos: {str(e)}")
    
    # Configuración de Feature Flags para nuevos templates
    app.config['USAR_NUEVOS_TEMPLATES'] = True  # Cambiar a False para desactivar los nuevos templates
    app.config['USAR_NUEVOS_TEMPLATES_ENTRADA'] = True  # Específico para módulo de entrada
    app.config['USAR_NUEVOS_TEMPLATES_SALIDA'] = False  # Para futura implementación del módulo de salida
    app.config['USAR_NUEVOS_TEMPLATES_REPORTES'] = False  # Para futura implementación del módulo de reportes
    logger.info("Feature flags para nuevos templates configurados")
    
    # Cargar configuración desde config.py (ahora debería tener rutas absolutas)
    try:
        # Importamos la instancia 'app' de config.py para obtener su config
        from config import app as config_app_instance
        app.config.update(config_app_instance.config) # Actualiza con la configuración cargada
        logger.info("Configuración cargada desde config.py (ahora con rutas absolutas)")
    except ImportError:
        app.logger.warning("No se pudo importar la configuración desde config.py")
    
    # Configurar ProxyFix para manejar correctamente encabezados de proxy
    # app.wsgi_app = ProxyFix( # <-- Comentar
    #     app.wsgi_app, x_proto=1, x_host=1
    #     # No incluir x_port=1 para evitar problemas con el puerto
    # ) # <-- Comentar
    
    # --- Define Database Paths using BASE_DIR --- 
    app.config['TIQUETES_DB_PATH'] = os.path.join(base_dir, 'tiquetes.db')
    logger.info(f"Using Tiquetes DB Path: {app.config['TIQUETES_DB_PATH']}")
    # logger.info(f"Database DB Path: {app.config['DATABASE_DB_PATH']}")
    
    # Ensure the DB file exists, if not, log a warning (schema creation will handle actual creation)
    if not os.path.exists(app.config['TIQUETES_DB_PATH']):
        logger.warning(f"Database file not found at configured path: {app.config['TIQUETES_DB_PATH']}")
        # Consider if you need to copy a default DB or stop the app here
    # --- End Define Database Paths ---
    
    # Inicializar Flask-Login con la app
    login_manager.init_app(app)

    # --- DEBUG: Log Session Interface ---
    logger.info(f"Session Interface: {app.session_interface}")
    # --- FIN DEBUG ---

    # --- Mantenemos la creación de directorios como una salvaguarda ---
    # Ahora usará las rutas cargadas desde config.py
    folder_keys_to_ensure = ['UPLOAD_FOLDER', 'PDF_FOLDER', 'GUIAS_FOLDER', 'QR_FOLDER', 'IMAGES_FOLDER', 'FOTOS_RACIMOS_FOLDER']
    # Aseguramos static_folder principal también
    if not os.path.exists(static_folder_path):
         os.makedirs(static_folder_path, exist_ok=True)
         logger.info(f"Directorio static asegurado: {static_folder_path}")

    for folder_key in folder_keys_to_ensure:
        folder_path = app.config.get(folder_key)
        if folder_path:
            if not os.path.exists(folder_path):
                 os.makedirs(folder_path, exist_ok=True)
                 logger.info(f"Directorio {folder_key} asegurado: {folder_path}")
        else:
            logger.warning(f"La clave de configuración para la carpeta '{folder_key}' no se encontró o está vacía.")
    # --- END CHANGES ---
    
    # Registrar blueprints
    register_blueprints(app)
    
    # Registrar manejadores de errores
    register_error_handlers(app)
    
    # Registrar filtros de plantillas
    register_template_filters(app)
    
    # Inicializar utilidades
    from app.utils.common import init_utils
    utils_instance = init_utils(app)
    
    # Inicializar utilidades de PDF y procesamiento de imágenes
    from app.utils.pdf_generator import init_pdf_generator_utils
    from app.utils.image_processing import init_image_processing_utils
    pdf_generator_utils = init_pdf_generator_utils(app)
    image_processing_utils = init_image_processing_utils(app)
    
    # Guardar la instancia de utils en la configuración de la aplicación
    try:
        # Usamos la función importada de config.py
        from config import init_utils_in_app
        init_utils_in_app(app, utils_instance) # Pasamos la instancia 'app' creada aquí
    except ImportError:
         app.config['utils'] = utils_instance
         logger.warning("No se pudo importar 'init_utils_in_app' desde config.py. Utils guardados directamente.")

    # Crear tablas y verificar esquema DENTRO del contexto de la aplicación
    with app.app_context():
        try:
            db_schema.create_tables()
            logger.info("Tablas de la base de datos verificadas/creadas correctamente (db_schema.create_tables).")
            
            # --- NUEVO: Llamar a las funciones de verificación de esquema extendido ---
            try:
                from app.utils.auth_utils import ensure_users_schema_admin_column
                if ensure_users_schema_admin_column():
                    logger.info("Esquema de tabla 'users' (columna is_admin) verificado/actualizado.")
                else:
                    logger.warning("Hubo un problema al verificar/actualizar esquema de 'users' (columna is_admin).")
            except ImportError:
                logger.error("No se pudo importar ensure_users_schema_admin_column.")
            except Exception as e_user_schema:
                logger.error(f"Error inesperado al asegurar esquema de users: {e_user_schema}")

            try:
                from app.blueprints.misc.routes import ensure_entry_records_schema_is_active_column
                if ensure_entry_records_schema_is_active_column():
                    logger.info("Esquema de tabla 'entry_records' (columna is_active) verificado/actualizado.")
                else:
                    logger.warning("Hubo un problema al verificar/actualizar esquema de 'entry_records' (columna is_active).")
            except ImportError:
                logger.error("No se pudo importar ensure_entry_records_schema_is_active_column.")
            except Exception as e_entry_schema:
                logger.error(f"Error inesperado al asegurar esquema de entry_records: {e_entry_schema}")
            # --- FIN NUEVO ---

        except Exception as e:
            logger.error(f"Error creando/verificando tablas DB principales: {e}")

        try:
            from app.blueprints.misc.routes import ensure_clasificaciones_schema
            ensure_clasificaciones_schema()
            logger.info("Estructura de tabla clasificaciones verificada/actualizada correctamente.")
        except Exception as e:
            logger.error(f"Error verificando tabla clasificaciones: {str(e)}")
    
    # --- Registrar filtros Jinja2 --- 
    app.add_template_filter(format_datetime_filter, 'format_datetime')
    app.add_template_filter(format_number_es, 'format_es') # NUEVO REGISTRO
    # --- FIN Registro filtros --- 
    
    # --- Añadir logging de cookies (CORREGIDO) --- 
    # setup_logging_cookies(app)  # <-- Comentar o eliminar
    # ---------------------------------------- 

    return app

# Comentar o eliminar toda esta función
# def setup_logging_cookies(app):
#     @app.after_request
#     def log_response_cookies(response):
#         # Check if the 'session' cookie is being set
#         set_cookie_header = response.headers.get('Set-Cookie')
#         if set_cookie_header and 'session=' in set_cookie_header:
#             app.logger.info(f"<<< DEBUG: Intentando establecer cookie de sesión: {set_cookie_header}")
#         elif set_cookie_header:
#              app.logger.info(f"<<< DEBUG: Cabecera Set-Cookie presente pero sin 'session': {set_cookie_header}")
#         else:
#             app.logger.info("<<< DEBUG: No se encontró cabecera Set-Cookie en la respuesta.")
#         return response

def register_blueprints(app):
    """
    Registra todos los blueprints de la aplicación
    """
    # Importar blueprints
    from app.blueprints.entrada import bp as entrada_bp
    from app.blueprints.pesaje import bp as pesaje_bp
    from app.blueprints.clasificacion import bp as clasificacion_bp
    from app.blueprints.pesaje_neto import bp as pesaje_neto_bp
    from app.blueprints.salida import bp as salida_bp
    from app.blueprints.admin import bp as admin_bp
    from app.blueprints.api import bp as api_bp
    from app.blueprints.misc import bp as misc_bp
    # Importar el nuevo blueprint de presupuesto
    from app.blueprints.presupuesto import bp as presupuesto_bp
    # Importar el blueprint de autenticación
    from app.blueprints.auth import bp as auth_bp
    # Importar el nuevo blueprint de comparación de guías
    from app.blueprints.comparacion_guias import bp as comparacion_guias_bp
    # Importar el nuevo blueprint de graneles
    from app.blueprints.graneles import graneles_bp
    
    # Registrar blueprints con sus prefijos de URL
    app.register_blueprint(entrada_bp)
    app.register_blueprint(pesaje_bp, url_prefix='/pesaje')
    app.register_blueprint(clasificacion_bp, url_prefix='/clasificacion')
    app.register_blueprint(pesaje_neto_bp, url_prefix='/pesaje-neto')
    app.register_blueprint(salida_bp, url_prefix='/salida')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(misc_bp)
    # Registrar el blueprint de presupuesto
    app.register_blueprint(presupuesto_bp) # Ya tiene el prefijo definido en su __init__.py
    # Registrar el blueprint de autenticación
    app.register_blueprint(auth_bp, url_prefix='/auth')
    # Registrar el nuevo blueprint de comparación de guías
    app.register_blueprint(comparacion_guias_bp) # El prefijo ya está en su __init__.py
    # Registrar el nuevo blueprint de graneles
    app.register_blueprint(graneles_bp) # El prefijo ya está en su __init__.py
    
    logger.info("Todos los blueprints registrados correctamente.")

def register_error_handlers(app):
    """
    Registra manejadores de errores personalizados
    """
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('error.html', message="Página no encontrada"), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('error.html', message="Error interno del servidor"), 500

def register_template_filters(app):
    """
    Registra filtros personalizados para las plantillas
    """
    @app.template_filter('file_exists')
    def file_exists_filter(path):
        return os.path.exists(path)
