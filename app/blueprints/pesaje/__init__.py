from flask import Blueprint

bp = Blueprint('pesaje', __name__)

from app.blueprints.pesaje import routes
