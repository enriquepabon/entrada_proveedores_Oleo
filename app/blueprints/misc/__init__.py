from flask import Blueprint

bp = Blueprint('misc', __name__)

from app.blueprints.misc import routes 