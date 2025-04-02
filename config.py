from flask import Flask
import os  # Agregamos esta importación
import secrets  # Para generar una clave secreta segura

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=os.path.join('static', 'uploads'),
    PDF_FOLDER=os.path.join('static', 'pdfs'),
    GUIAS_FOLDER=os.path.join('static', 'guias'),
    QR_FOLDER=os.path.join('static', 'qr'),
    IMAGES_FOLDER=os.path.join('static', 'images'),
    EXCEL_FOLDER=os.path.join('static', 'excels'),
    SECRET_KEY=secrets.token_hex(32),  # Clave secreta generada aleatoriamente
    
    # Nuevas configuraciones para vistas dinámicas
    USAR_VISTA_DINAMICA=True,  # Habilitar la vista dinámica centralizada
    USAR_NUEVOS_TEMPLATES_ENTRADA=True  # Usar los nuevos templates de entrada
)

# Eliminamos la configuración de SERVER_NAME para permitir que Flask determine automáticamente
# el host y puerto en entorno de producción
# app.config['SERVER_NAME'] = 'localhost:8081'  # Comentamos o eliminamos esta línea

# Configuración opcional para forzar HTTPS en producción (descomenta si necesario)
# app.config['PREFERRED_URL_SCHEME'] = 'https'

# Crear directorios si no existen
for folder in [
    app.config['UPLOAD_FOLDER'], 
    app.config['PDF_FOLDER'],
    app.config['GUIAS_FOLDER'],
    app.config['QR_FOLDER'],
    app.config['IMAGES_FOLDER'],
    app.config['EXCEL_FOLDER']
]:
    os.makedirs(folder, exist_ok=True)

# Asegurarse de guardar la instancia de utils en la aplicación para facilitar su acceso
def init_utils_in_app(app, utils_instance):
    """
    Guarda la instancia de Utils en la configuración de la aplicación
    para facilitar su acceso desde cualquier parte de la misma.
    """
    app.config['utils'] = utils_instance
    return app