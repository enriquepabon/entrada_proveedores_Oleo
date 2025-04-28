from flask import Blueprint

# Definir el Blueprint para autenticación
# Usamos 'templates' como template_folder para que busque en app/templates/auth/
bp = Blueprint('auth', __name__, template_folder='templates')

# Importar las rutas al final para evitar importaciones circulares
from . import routes 