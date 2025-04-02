from flask import Blueprint

bp = Blueprint('entrada', __name__)

from app.blueprints.entrada import routes
