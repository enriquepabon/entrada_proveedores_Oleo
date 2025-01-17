from flask import Flask
import os  # Agregamos esta importación

app = Flask(__name__)
app.config.update(
    UPLOAD_FOLDER=os.path.join('static', 'uploads'),
    PDF_FOLDER=os.path.join('static', 'pdfs'),
    GUIAS_FOLDER=os.path.join('static', 'guias'),
    QR_FOLDER=os.path.join('static', 'qr'),
    IMAGES_FOLDER=os.path.join('static', 'images'),
    EXCEL_FOLDER=os.path.join('static', 'excels'),
    SECRET_KEY='tu_clave_secreta'  # Cambia esto
)

# Configuración del servidor
app.config['SERVER_NAME'] = 'localhost:5002'  # O tu dominio en producción

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