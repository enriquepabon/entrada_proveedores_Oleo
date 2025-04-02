from flask import Flask, render_template
import os
import logging
from config import app as app_config
import db_schema
import secrets
from werkzeug.middleware.proxy_fix import ProxyFix

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(test_config=None):
    """
    Función de fábrica para crear la aplicación Flask
    """
    # Crear la instancia de la aplicación Flask
    app = Flask(__name__,
                template_folder=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'templates')),
                static_folder='../static',
                instance_relative_config=True)
    
    # Aplicar configuración desde parámetro test_config si existe
    if test_config is not None:
        app.config.update(test_config)
        logger.info(f"Aplicada configuración externa: {test_config}")
        
        # Configurar correctamente SERVER_NAME si está definido
        if 'SERVER_NAME' in test_config:
            logger.info(f"SERVER_NAME configurado: {test_config['SERVER_NAME']}")
    
    # NUEVO: Limpiar QRs problemáticos al iniciar la aplicación
    try:
        import glob
        
        # QRs específicamente problemáticos a eliminar de forma permanente
        specific_problem_qrs = [
            os.path.join(app.static_folder, 'qr', 'default_qr_20250311143540.png'),
            os.path.join(app.static_folder, 'qr', 'default_qr.png')
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
            os.path.join(app.static_folder, 'qr', 'default_qr*.png'),
            os.path.join(app.static_folder, 'qr', 'default_qr*_*.png')
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
    
    # Configurar clave secreta directamente (no desde config.py)
    app.secret_key = secrets.token_hex(32)
    logger.info("Clave secreta configurada para la aplicación: %s", app.secret_key[:8] + '...')
    
    # Configuración de Feature Flags para nuevos templates
    app.config['USAR_NUEVOS_TEMPLATES'] = True  # Cambiar a False para desactivar los nuevos templates
    app.config['USAR_NUEVOS_TEMPLATES_ENTRADA'] = True  # Específico para módulo de entrada
    app.config['USAR_NUEVOS_TEMPLATES_SALIDA'] = False  # Para futura implementación del módulo de salida
    app.config['USAR_NUEVOS_TEMPLATES_REPORTES'] = False  # Para futura implementación del módulo de reportes
    logger.info("Feature flags para nuevos templates configurados")
    
    # Cargar configuración
    try:
        from config import app as config_app
        app.config.update(config_app.config)
    except ImportError:
        app.logger.warning("No se pudo importar la configuración desde config.py")
    
    # Configurar ProxyFix para manejar correctamente encabezados de proxy
    app.wsgi_app = ProxyFix(
        app.wsgi_app, x_proto=1, x_host=1
        # No incluir x_port=1 para evitar problemas con el puerto
    )
    
    # --- Define Database Paths --- 
    # Define path relative to the app root, not instance path
    # Assuming tiquetes.db is in the project root directory (TiquetesApp)
    project_root = os.path.abspath(os.path.join(app.root_path, os.pardir))
    app.config['TIQUETES_DB_PATH'] = os.path.join(project_root, 'tiquetes.db')
    # Remove the potentially confusing DATABASE_DB_PATH
    # app.config['DATABASE_DB_PATH'] = os.path.join(instance_path, 'database.db') 
    logger.info(f"Using Tiquetes DB Path: {app.config['TIQUETES_DB_PATH']}")
    # logger.info(f"Database DB Path: {app.config['DATABASE_DB_PATH']}")
    
    # Ensure the DB file exists, if not, log a warning (schema creation will handle actual creation)
    if not os.path.exists(app.config['TIQUETES_DB_PATH']):
        logger.warning(f"Database file not found at configured path: {app.config['TIQUETES_DB_PATH']}")
        # Consider if you need to copy a default DB or stop the app here
    # --- End Define Database Paths ---
    
    # Definir rutas de carpetas críticas y asegurar que existan
    app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'uploads')
    app.config['PDF_FOLDER'] = os.path.join(app.static_folder, 'pdfs')
    app.config['GUIAS_FOLDER'] = os.path.join(app.static_folder, 'guias')
    app.config['QR_FOLDER'] = os.path.join(app.static_folder, 'qr')
    app.config['IMAGES_FOLDER'] = os.path.join(app.static_folder, 'images')
    app.config['FOTOS_RACIMOS_FOLDER'] = os.path.join(app.static_folder, 'uploads', 'clasificacion')
    
    # Aseguramos que todas las carpetas existan
    for folder_key in ['UPLOAD_FOLDER', 'PDF_FOLDER', 'GUIAS_FOLDER', 'QR_FOLDER', 'IMAGES_FOLDER', 'FOTOS_RACIMOS_FOLDER']:
        folder_path = app.config.get(folder_key)
        if folder_path:
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"Directorio {folder_key} asegurado: {folder_path}")
    
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
    from config import init_utils_in_app
    init_utils_in_app(app, utils_instance)

    # Crear tablas y verificar esquema DENTRO del contexto de la aplicación
    with app.app_context():
        try:
            db_schema.create_tables()
            logger.info("Tablas de la base de datos verificadas/creadas correctamente.")
        except Exception as e:
            logger.error(f"Error creando/verificando tablas DB: {e}")
            # Podrías decidir si la app puede continuar sin DB o lanzar un error más grave

        # Asegurar que la tabla clasificaciones tenga la estructura correcta
        try:
            from app.blueprints.misc.routes import ensure_clasificaciones_schema
            ensure_clasificaciones_schema()
            logger.info("Estructura de tabla clasificaciones verificada/actualizada correctamente.")
        except Exception as e:
            logger.error(f"Error verificando tabla clasificaciones: {str(e)}")
    
    return app

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
    
    # Registrar blueprints con sus prefijos de URL
    app.register_blueprint(entrada_bp)
    app.register_blueprint(pesaje_bp, url_prefix='/pesaje')
    app.register_blueprint(clasificacion_bp, url_prefix='/clasificacion')
    app.register_blueprint(pesaje_neto_bp, url_prefix='/pesaje-neto')
    app.register_blueprint(salida_bp, url_prefix='/salida')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(misc_bp)
    
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
    Registra filtros personalizados y utilidades globales para las plantillas
    """
    @app.template_filter('file_exists')
    def file_exists_filter(path):
        return os.path.exists(path)

    # Registrar convert_to_bogota_time como una utilidad global
    from app.utils.common import convert_to_bogota_time
    app.jinja_env.globals.update(convert_to_bogota_time=convert_to_bogota_time)
    logger.info("Función 'convert_to_bogota_time' registrada como global en Jinja.")
