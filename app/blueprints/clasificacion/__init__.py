from flask import Blueprint

bp = Blueprint('clasificacion', __name__)

from app.blueprints.clasificacion import routes
