# Guía de Instalación y Configuración - TiquetesApp

Este documento proporciona instrucciones detalladas para la instalación, configuración y despliegue de la aplicación TiquetesApp.

**Fecha de actualización:** 18 de marzo de 2024

## 1. Requisitos del Sistema

### 1.1 Requisitos de Hardware
- **Procesador**: 2 GHz o superior (Intel Core i3/i5 o equivalente)
- **Memoria RAM**: Mínimo 2 GB (4 GB recomendado)
- **Almacenamiento**: 500 MB mínimo para la aplicación base
- **Conexión a Internet**: Requerida para clasificación con IA (Roboflow)

### 1.2 Requisitos de Software
- **Sistema Operativo**: Windows 10+, macOS 10.14+, o Linux (Ubuntu 18.04+, Debian 10+)
- **Python**: Versión 3.8 o superior
- **Navegador Web**: Chrome, Firefox, Edge (últimas versiones)
- **Git**: Para clonar el repositorio (opcional)

## 2. Instalación

### 2.1 Instalación desde Cero

1. **Clonar el repositorio** (o descargar como ZIP si no tiene Git):
   ```bash
   git clone [url-del-repositorio]
   cd TiquetesApp
   ```

2. **Crear y activar un entorno virtual**:
   
   En Windows:
   ```bash
   python -m venv venv
   venv\Scripts\activate
   ```
   
   En macOS/Linux:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Crear directorios necesarios** (si no existen):
   ```bash
   mkdir -p static/uploads static/pdfs static/guias static/qr static/images
   mkdir -p static/uploads/clasificacion static/uploads/bascula
   ```

5. **Inicializar la base de datos**:
   ```bash
   python db_schema.py
   ```

### 2.2 Actualización de una Instalación Existente

1. **Detener la aplicación si está en ejecución**

2. **Respaldar datos importantes**:
   ```bash
   cp tiquetes.db tiquetes.db.backup
   cp database.db database.db.backup
   cp -r data data_backup
   cp -r static/uploads uploads_backup
   ```

3. **Actualizar el código fuente**:
   ```bash
   git pull
   # O si no usa Git, reemplace los archivos con la nueva versión
   ```

4. **Actualizar dependencias**:
   ```bash
   pip install -r requirements.txt --upgrade
   ```

5. **Actualizar esquema de la base de datos**:
   ```bash
   python db_schema.py
   ```

## 3. Configuración

### 3.1 Configuración Básica

1. **Configuración de variables de entorno**:
   - Copie el archivo `.env.example` a `.env`
   - Edite `.env` según su entorno

   ```
   CONFIG_HOST=localhost
   CONFIG_PORT=8082
   
   # Roboflow API (para clasificación)
   ROBOFLOW_API_KEY=your_api_key_here
   ROBOFLOW_WORKSPACE=your_workspace
   ROBOFLOW_PROJECT=your_project
   ROBOFLOW_VERSION=1
   ROBOFLOW_WORKFLOW_ID=your_workflow_id
   
   # Carpetas (opcional, use rutas absolutas para cambiar ubicaciones)
   #UPLOAD_FOLDER=/path/to/uploads
   #PDF_FOLDER=/path/to/pdfs
   #GUIAS_FOLDER=/path/to/guias
   ```

2. **Configuración de API de Roboflow** (para clasificación automática):
   - Cree una cuenta en [Roboflow](https://roboflow.com)
   - Obtenga una clave API de Roboflow
   - Configure su espacio de trabajo y proyecto
   - Actualice los valores en `.env` o directamente en `run.py`

### 3.2 Configuración Avanzada

1. **Configuración del servidor Flask**:
   
   Edite `run.py` para cambiar la configuración del servidor:
   ```python
   app.run(
       host='0.0.0.0',  # Cambie a '0.0.0.0' para permitir acceso externo
       port=8082,       # Puerto personalizado
       debug=False,     # Desactive debug en producción
       use_reloader=False,
       threaded=True
   )
   ```

2. **Configuración de la base de datos**:
   
   Para usar una base de datos en una ubicación personalizada, edite `db_schema.py`:
   ```python
   # Ruta a la base de datos
   DB_PATH = '/path/to/your/tiquetes.db'
   ```

3. **Configuración de logging**:
   
   Para personalizar el logging, modifique la configuración en `app/__init__.py`:
   ```python
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       filename='app.log'
   )
   ```

## 4. Ejecución y Despliegue

### 4.1 Entorno de Desarrollo

Para ejecutar la aplicación en modo desarrollo:

```bash
python run.py
```

La aplicación estará disponible en http://localhost:8082

### 4.2 Entorno de Producción

Para despliegue en producción, se recomienda utilizar un servidor WSGI como Gunicorn:

1. **Instalar Gunicorn**:
   ```bash
   pip install gunicorn
   ```

2. **Ejecutar con Gunicorn**:
   ```bash
   gunicorn -w 4 -b 0.0.0.0:8082 "run:app"
   ```

3. **Uso con Nginx** (recomendado para producción):
   
   Ejemplo de configuración de Nginx:
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location / {
           proxy_pass http://127.0.0.1:8082;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static {
           alias /path/to/TiquetesApp/static;
           expires 30d;
       }
   }
   ```

4. **Configuración de systemd** (para autoarranque en Linux):
   
   Cree un archivo `/etc/systemd/system/tiquetesapp.service`:
   ```
   [Unit]
   Description=TiquetesApp Gunicorn Service
   After=network.target

   [Service]
   User=yourusername
   Group=yourgroup
   WorkingDirectory=/path/to/TiquetesApp
   Environment="PATH=/path/to/TiquetesApp/venv/bin"
   ExecStart=/path/to/TiquetesApp/venv/bin/gunicorn -w 4 -b 127.0.0.1:8082 "run:app"
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   
   Habilite y inicie el servicio:
   ```bash
   sudo systemctl enable tiquetesapp
   sudo systemctl start tiquetesapp
   ```

### 4.3 Despliegue en Contenedor Docker

1. **Crear un Dockerfile**:
   ```Dockerfile
   FROM python:3.9-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   EXPOSE 8082
   
   CMD ["python", "run.py"]
   ```

2. **Construir y ejecutar el contenedor**:
   ```bash
   docker build -t tiquetesapp .
   docker run -d -p 8082:8082 --name tiquetes-container tiquetesapp
   ```

## 5. Solución de Problemas

### 5.1 Problemas Comunes

1. **Error al iniciar la aplicación**:
   - Verificar que el puerto no esté en uso
   - Verificar permisos de escritura en directorios
   - Revisar logs en `flask_app.log`

2. **Problemas de base de datos**:
   - Si hay errores de SQLite, verificar permisos del archivo
   - Ejecutar `python db_schema.py` para reconstruir tablas

3. **Errores en clasificación**:
   - Verificar la conexión a Internet
   - Comprobar la validez de la API key de Roboflow
   - Verificar que el proyecto y workflow estén correctamente configurados

### 5.2 Logs y Monitoreo

Los logs principales están en:
- `flask_app.log`: Logs generales de la aplicación
- Logs del sistema: `/var/log/nginx/error.log` (si usa Nginx)

Para depuración extendida, active el nivel DEBUG en `app/__init__.py`:
```python
logging.basicConfig(level=logging.DEBUG, ...)
```

## 6. Actualización y Mantenimiento

### 6.1 Respaldo de Datos

Se recomienda realizar respaldos periódicos de:
- Archivos de base de datos (`tiquetes.db`, `database.db`)
- Directorio de uploads (`static/uploads/`)
- Archivos de guías generadas (`static/guias/`)

Ejemplo de script de respaldo:
```bash
#!/bin/bash
BACKUP_DIR="/path/to/backups/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR
cp tiquetes.db database.db $BACKUP_DIR/
tar -czf $BACKUP_DIR/uploads.tar.gz static/uploads/
tar -czf $BACKUP_DIR/guias.tar.gz static/guias/
```

### 6.2 Actualización de Dependencias

Para actualizar las dependencias manteniendo compatibilidad:
```bash
pip install -r requirements.txt --upgrade
```

## 7. Contacto y Soporte

Para soporte técnico o consultas:
- Email: [correo del desarrollador]
- Teléfono: [número de contacto]

---

Documento preparado por [nombre del autor]
Última actualización: 18 de marzo de 2024 