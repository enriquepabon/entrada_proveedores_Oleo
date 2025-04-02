from flask import Blueprint

bp = Blueprint('pesaje_neto', __name__)

from app.blueprints.pesaje_neto import routes
