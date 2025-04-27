from flask import Blueprint
import logging # Asegúrate que logging está importado si lo usas en el blueprint

# Configurar logger específico para este blueprint si es necesario
logger = logging.getLogger(__name__)

# Define el Blueprint aquí
bp = Blueprint('clasificacion', __name__, template_folder='templates', static_folder='static', url_prefix='/clasificacion')

# Importa los módulos de rutas DESPUÉS de definir bp para evitar importaciones circulares
# Por ahora, solo importaremos el original 'routes' para que siga funcionando.
# En pasos posteriores, cambiaremos esto para importar 'views', 'processing', etc.
from . import views      # Contendrá las rutas de vista (Paso 4)
from . import processing # Contiene las rutas de procesamiento
from . import helpers    # Contiene funciones auxiliares



