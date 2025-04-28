import os
import logging
from flask import Flask, session, request

# Configurar logging básico
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Crear instancia de Flask
app = Flask(__name__)

# --- Establecer SECRET_KEY directamente ---
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
if not app.secret_key:
    logger.error("¡ERROR CRÍTICO! La variable de entorno FLASK_SECRET_KEY no está definida.")
    app.secret_key = 'clave-insegura-fallback-para-test'
    logger.warning("Usando clave secreta insegura por defecto para test_session.py.")
else:
    logger.info(f"test_session.py: SECRET_KEY cargada desde variable de entorno: {app.secret_key[:8]}...")
# -------------------------------------

@app.route('/set')
def set_session():
    session['test_value'] = 'hello world'
    logger.info(f"Ruta /set: session['test_value'] establecida como 'hello world'")
    return "Valor 'hello world' establecido en la sesión. Ahora ve a /get"

@app.route('/get')
def get_session():
    value = session.get('test_value', '¡¡¡VALOR NO ENCONTRADO!!!')
    logger.info(f"Ruta /get: Valor obtenido de session.get('test_value'): {value}")
    return f"Valor obtenido de la sesión: {value}"

if __name__ == '__main__':
    # Correr en un puerto diferente para evitar conflictos
    logger.info("Iniciando servidor de prueba de sesión en http://localhost:5001")
    app.run(debug=True, port=5001) 