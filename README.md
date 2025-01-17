# TiquetesApp - Sistema de Registro MLB

Sistema de registro y validación de tiquetes para la Extractora Maria la Baja.

## Descripción

TiquetesApp es una aplicación web desarrollada en Flask que permite:
- Escanear y procesar tiquetes de entrada
- Validar información contra una base de datos
- Generar códigos QR para seguimiento
- Gestionar el proceso de pesaje y clasificación

## Requisitos

- Python 3.8+
- Flask
- OpenCV
- Otras dependencias (ver requirements.txt)

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
```bash
cp .env.example .env
# Editar .env con las configuraciones necesarias
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
├── apptiquetes.py      # Aplicación principal
├── utils.py            # Utilidades y funciones auxiliares
├── templates/          # Plantillas HTML
├── static/            # Archivos estáticos
│   ├── images/       # Imágenes
│   ├── uploads/      # Archivos subidos
│   ├── pdfs/         # PDFs generados
│   └── qr/           # Códigos QR generados
└── requirements.txt   # Dependencias
```

## Contribuir

1. Fork el repositorio
2. Crear una rama para tu feature (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

## Licencia

Este proyecto es propiedad de Oleoflores S.A.S. Todos los derechos reservados.