from flask import Blueprint

bp = Blueprint('salida', __name__)

from app.blueprints.salida import routes
