from flask import Flask
import os  # Agregamos esta importación
import secrets  # Para generar una clave secreta segura

# Calcular BASE_DIR basado en la ubicación de este archivo (config.py)
# Asumimos que config.py está en el directorio raíz del proyecto.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_FOLDER_PATH = os.path.join(BASE_DIR, 'static')

# Mantenemos la instancia app aquí por si es necesaria en otras partes
# aunque idealmente la configuración no debería depender de una instancia de app.
app = Flask(__name__)

# Actualizar configuración usando rutas absolutas
app.config.update(
    # Usar rutas absolutas calculadas
    UPLOAD_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'uploads'),
    PDF_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'pdfs'),
    GUIAS_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'guias'),
    QR_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'qr'),
    IMAGES_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'images'),
    EXCEL_FOLDER=os.path.join(STATIC_FOLDER_PATH, 'excels'),
    # Mantener otras configuraciones
    SECRET_KEY=secrets.token_hex(32),
    USAR_VISTA_DINAMICA=True,
    USAR_NUEVOS_TEMPLATES_ENTRADA=True,
    # Guardamos BASE_DIR aquí también para consistencia
    BASE_DIR=BASE_DIR,
    STATIC_FOLDER=STATIC_FOLDER_PATH # Añadimos STATIC_FOLDER explícitamente
)

# Eliminamos la configuración de SERVER_NAME para permitir que Flask determine automáticamente
# el host y puerto en entorno de producción
# app.config['SERVER_NAME'] = 'localhost:8081'  # Comentamos o eliminamos esta línea

# Configuración opcional para forzar HTTPS en producción (descomenta si necesario)
# app.config['PREFERRED_URL_SCHEME'] = 'https'

# Crear directorios usando rutas absolutas si no existen
# Es buena práctica tener esto, aunque app/__init__.py también lo hace.
# Asegúrate que las claves coincidan con las definidas arriba.
required_folders_keys = [
    'UPLOAD_FOLDER', 'PDF_FOLDER', 'GUIAS_FOLDER',
    'QR_FOLDER', 'IMAGES_FOLDER', 'EXCEL_FOLDER'
]
# Añadir la carpeta static principal también
os.makedirs(STATIC_FOLDER_PATH, exist_ok=True)

for folder_key in required_folders_keys:
    folder_path = app.config.get(folder_key)
    if folder_path:
        os.makedirs(folder_path, exist_ok=True)

# Asegurarse de guardar la instancia de utils en la aplicación para facilitar su acceso
def init_utils_in_app(app_instance, utils_instance): # Cambiado a app_instance para claridad
    """
    Guarda la instancia de Utils en la configuración de la aplicación
    para facilitar su acceso desde cualquier parte de la misma.
    """
    app_instance.config['utils'] = utils_instance
    return app_instance