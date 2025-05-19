from flask import Blueprint

# Define el Blueprint para el módulo de graneles
graneles_bp = Blueprint(
    'graneles',
    __name__,
    template_folder='../../templates/graneles',  # Ruta desde app/blueprints/graneles/ a app/templates/graneles/
    url_prefix='/graneles'
)

# Importa las rutas DESPUÉS de definir graneles_bp para evitar importaciones circulares
from . import routes 