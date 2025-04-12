from flask import Blueprint

# Crear una instancia del Blueprint
bp = Blueprint('presupuesto', __name__, url_prefix='/presupuesto')

# Importar las rutas después de crear el blueprint para evitar importación circular
from . import routes 