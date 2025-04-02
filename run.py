import sys
import os
import logging
from logging.handlers import RotatingFileHandler

# Crear directorio de logs si no existe
os.makedirs('logs', exist_ok=True)

# Configurar logging
handler = RotatingFileHandler('logs/app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

# Asegurar que el directorio actual está en el path
sys.path.insert(0, os.getcwd())

from app import create_app

# Configurar los valores de host y puerto
CONFIG_HOST = os.environ.get('CONFIG_HOST', 'localhost')
CONFIG_PORT = os.environ.get('CONFIG_PORT', '8082')

# Roboflow configuration
# Replace with your actual API key - or set in environment variable
ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'huyFoCQs7090vfjDhfgK')  # Restored default API key
ROBOFLOW_WORKSPACE = os.environ.get('ROBOFLOW_WORKSPACE', 'enrique-p-workspace')
ROBOFLOW_PROJECT = os.environ.get('ROBOFLOW_PROJECT', 'clasificacion-racimos')
ROBOFLOW_VERSION = os.environ.get('ROBOFLOW_VERSION', '1')
ROBOFLOW_WORKFLOW_ID = os.environ.get('ROBOFLOW_WORKFLOW_ID', 'clasificacion-racimos-3')

logger = logging.getLogger(__name__)
logger.addHandler(handler)


logger.info(f"Iniciando aplicación con host={CONFIG_HOST}, port={CONFIG_PORT}")

# Crear la aplicación con la configuración
app = create_app({
    'CONFIG_HOST': CONFIG_HOST,
    'CONFIG_PORT': CONFIG_PORT,
    'PREFERRED_URL_SCHEME': 'http',
    'ROBOFLOW_API_KEY': ROBOFLOW_API_KEY,
    'ROBOFLOW_WORKSPACE': ROBOFLOW_WORKSPACE,
    'ROBOFLOW_PROJECT': ROBOFLOW_PROJECT,
    'ROBOFLOW_VERSION': ROBOFLOW_VERSION,
    'ROBOFLOW_WORKFLOW_ID': ROBOFLOW_WORKFLOW_ID
})

logger.setLevel(logging.DEBUG)
app.logger.info('Iniciando servidor Flask...')

# Registrar todas las rutas disponibles
logger.info("Rutas registradas:")
for rule in app.url_map.iter_rules():
    logger.info(f"{rule.endpoint}: {rule.rule}")

if __name__ == '__main__':
    try:
        logger.info("Iniciando servidor Flask...")
        app.run(
            host=CONFIG_HOST,
            port=int(CONFIG_PORT),
            debug=True,
            use_reloader=True,
            threaded=True
        )
    except Exception as e:
        import traceback
        logger.error(f"Error iniciando la aplicación: {str(e)}")
        logger.error(traceback.format_exc())
