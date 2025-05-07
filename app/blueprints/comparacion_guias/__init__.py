from flask import Blueprint

bp = Blueprint('comparacion_guias', __name__, template_folder='../../../templates/comparacion_guias', url_prefix='/comparacion-guias')

from . import routes 