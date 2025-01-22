# TiquetesApp - Sistema de Gestión de Tiquetes de Fruta

## Descripción
Sistema web para la gestión y procesamiento de tiquetes de fruta, que incluye:
- Registro y validación de tiquetes
- Pesaje (directo y virtual)
- Clasificación automática de racimos usando IA
- Clasificación manual
- Generación de reportes y documentos PDF
- Seguimiento del proceso completo

## Características
- Procesamiento de imágenes con OCR para extracción de datos
- Integración con Roboflow para clasificación automática de racimos
- Sistema de autorización para pesaje virtual
- Generación automática de códigos QR
- Generación de PDFs para cada etapa del proceso
- Interfaz web responsive y amigable

## Tecnologías
- Python 3.x
- Flask
- HTML/CSS/JavaScript
- Bootstrap 5
- WeasyPrint (generación de PDFs)
- Pillow (procesamiento de imágenes)
- Roboflow API (clasificación de imágenes)

## Instalación

1. Clonar el repositorio:
```bash
git clone [URL_DEL_REPOSITORIO]
cd TiquetesApp
```

2. Crear y activar entorno virtual:
```bash
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
pip install -r requirements.txt
```

4. Configurar variables de entorno:
Crear archivo `.env` con las siguientes variables:
```
ROBOFLOW_API_KEY=tu_api_key
PROCESS_WEBHOOK_URL=url_webhook
REGISTER_WEBHOOK_URL=url_webhook
REVALIDATION_WEBHOOK_URL=url_webhook
ADMIN_NOTIFICATION_WEBHOOK_URL=url_webhook
PESAJE_WEBHOOK_URL=url_webhook
AUTORIZACION_WEBHOOK_URL=url_webhook
REGISTRO_PESO_WEBHOOK_URL=url_webhook
CLASIFICACION_WEBHOOK_URL=url_webhook
REGISTRO_CLASIFICACION_WEBHOOK_URL=url_webhook
```

5. Crear directorios necesarios:
```bash
mkdir -p static/{uploads,pdfs,guias,excels,qr}
```

## Uso

1. Iniciar el servidor:
```bash
python apptiquetes.py
```

2. Acceder a la aplicación en:
```
http://localhost:5002
```

## Estructura del Proyecto
```
TiquetesApp/
├── apptiquetes.py         # Aplicación principal
├── config.py             # Configuración
├── utils.py             # Utilidades
├── knowledge_updater.py  # Actualizador de conocimiento
├── parser.py            # Parser de respuestas
├── static/              # Archivos estáticos
│   ├── uploads/        # Imágenes subidas
│   ├── pdfs/          # PDFs generados
│   ├── guias/         # HTMLs de guías
│   ├── excels/        # Archivos Excel
│   └── qr/            # Códigos QR generados
├── templates/          # Plantillas HTML
└── requirements.txt    # Dependencias
```

## Flujo del Proceso
1. Registro inicial del tiquete
2. Validación de datos
3. Pesaje (directo o virtual)
4. Clasificación de racimos (automática y/o manual)
5. Registro de peso tara
6. Registro de salida

## Contribución
1. Fork el repositorio
2. Crear rama para feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir Pull Request

## Licencia
Distribuido bajo la Licencia MIT. Ver `LICENSE` para más información.

## Contacto
Enrique Pabon - epabon@oleoflores.com