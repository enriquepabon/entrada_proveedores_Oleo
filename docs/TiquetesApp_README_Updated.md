# TiquetesApp

Sistema de gestión de tiquetes para el registro, pesaje, clasificación y salida de entradas de proveedores a Oleoflores - Extractora MLB.

**Fecha de actualización:** 18 de marzo de 2024

## Descripción

TiquetesApp es una aplicación web desarrollada con Flask que gestiona el proceso completo de entrada, procesamiento y salida de proveedores en la planta Extractora MLB de Oleoflores. El sistema captura imágenes, procesa datos de vehículos, realiza pesajes (bruto y neto), clasifica racimos, y registra la salida de vehículos, generando la documentación necesaria en cada etapa del proceso.

## Características principales

- **Registro de entrada**: Captura de datos de proveedores, conductores y vehículos mediante procesamiento de imágenes
- **Pesaje inicial (bruto)**: Registro del peso bruto de los vehículos con carga
- **Clasificación de racimos**: Sistema integrado con IA para clasificación automática
- **Pesaje neto**: Registro del peso tara y cálculo del peso neto
- **Registro de salida**: Documentación del proceso de salida
- **Generación de guías PDF**: Documentos para cada etapa del proceso
- **Base de datos SQLite**: Almacenamiento persistente con compatibilidad con JSON
- **Panel administrativo**: Gestión de registros y operaciones del sistema
- **API REST**: Endpoints para integración con otros sistemas

## Estructura del flujo de trabajo

El sistema sigue un flujo de trabajo lineal con las siguientes etapas:

1. **Entrada**: Registro del ingreso del proveedor con datos del tiquete y placa
2. **Pesaje bruto**: Registro del peso inicial del vehículo con carga
3. **Clasificación**: Análisis y clasificación de racimos mediante sistema de IA
4. **Pesaje neto**: Registro del peso final (tara) y cálculo de peso neto
5. **Salida**: Registro de la salida del vehículo de la planta

## Arquitectura técnica

La aplicación ha sido reestructurada utilizando Flask Blueprints para mejorar la organización, mantenibilidad y escalabilidad del código:

- **entrada**: Gestión de registros de entrada
- **pesaje**: Proceso de pesaje bruto de vehículos
- **clasificacion**: Sistema de clasificación automática de racimos
- **pesaje_neto**: Registro de peso tara y cálculo de peso neto
- **salida**: Registro de salida de vehículos
- **misc**: Funcionalidades misceláneas y común
- **admin**: Funciones administrativas
- **api**: Endpoints para integración con otros sistemas

## Instalación

1. **Clonar el repositorio**:
```bash
git clone [url-del-repositorio]
cd TiquetesApp
```

2. **Crear y activar entorno virtual**:
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. **Instalar dependencias**:
```bash
pip install -r requirements.txt
```

4. **Configurar la aplicación**:
- Copiar `.env.example` a `.env`
- Editar `.env` con los valores adecuados para su entorno
- Configurar las claves de API de Roboflow (para clasificación) en `config.py`

5. **Iniciar la aplicación**:
```bash
python run.py
```

## Requisitos del sistema

- **Python**: 3.8+
- **Sistema operativo**: Windows, macOS, Linux
- **Memoria**: Mínimo 2GB RAM (4GB recomendado)
- **Almacenamiento**: Mínimo 500MB de espacio libre
- **Conexión a internet**: Requerida para la clasificación mediante IA

## Dependencias principales

- **Flask**: 3.0.0 - Framework web
- **Werkzeug**: 3.0.1 - Utilidades WSGI para Flask
- **Pillow**: 10.1.0 - Procesamiento de imágenes
- **WeasyPrint**: 60.1 - Generación de PDF
- **SQLite**: Base de datos incorporada
- **OpenCV**: 4.8.1.78 - Procesamiento de imágenes para detección de placas
- **QRCode**: 7.4.2 - Generación de códigos QR

Para una lista completa de dependencias, consulte el archivo `requirements.txt`.

## Estructura de archivos y directorios

```
TiquetesApp/
├── app/                      # Directorio principal de la aplicación
│   ├── __init__.py           # Configuración e inicialización de la app Flask
│   ├── models/               # Modelos de datos 
│   ├── utils/                # Utilidades generales
│   ├── blueprints/           # Módulos funcionales (blueprints)
│       ├── entrada/          # Funcionalidad de registro de entrada
│       ├── pesaje/           # Funcionalidad de pesaje bruto
│       ├── clasificacion/    # Funcionalidad de clasificación
│       ├── pesaje_neto/      # Funcionalidad de pesaje neto
│       ├── salida/           # Funcionalidad de registro de salida
│       ├── misc/             # Funcionalidades misceláneas
│       ├── admin/            # Funcionalidades de administración
│       └── api/              # Endpoints de API
├── static/                   # Archivos estáticos (CSS, JS, imágenes)
│   ├── uploads/              # Imágenes subidas por usuarios
│   ├── pdfs/                 # PDFs generados
│   ├── guias/                # Archivos de guías HTML
│   ├── qr/                   # Códigos QR generados
│   └── images/               # Imágenes del sistema
├── templates/                # Plantillas HTML
│   ├── entrada/              # Plantillas para módulo de entrada
│   ├── pesaje/               # Plantillas para módulo de pesaje
│   ├── clasificacion/        # Plantillas para módulo de clasificación
│   ├── pesaje_neto/          # Plantillas para módulo de pesaje neto
│   ├── salida/               # Plantillas para módulo de salida
│   ├── admin/                # Plantillas para administración
│   └── components/           # Componentes reutilizables
├── docs/                     # Documentación
├── scripts/                  # Scripts de utilidades y migración
├── data/                     # Datos persistentes (JSONs)
├── tiquetes.db               # Base de datos SQLite principal
├── database.db               # Base de datos SQLite secundaria/legado
├── requirements.txt          # Dependencias del proyecto
└── run.py                    # Punto de entrada de la aplicación
```

## Base de datos

El sistema utiliza SQLite como motor de base de datos principal, manteniendo compatibilidad con el formato JSON para datos históricos. Las tablas principales son:

- **entry_records**: Datos de entrada de vehículos
- **pesajes_bruto**: Registros de pesaje bruto
- **clasificaciones**: Resultados de clasificación de racimos
- **pesajes_neto**: Registros de pesaje neto
- **fotos_clasificacion**: Referencias a imágenes de clasificación
- **salidas**: Registros de salida de vehículos

Para más detalles sobre la estructura de la base de datos, consulte `db_schema.py`.

## Almacenamiento de archivos

Los archivos generados por la aplicación se almacenan en las siguientes ubicaciones:

- **Fotos de tiquetes**: `/static/uploads/`
- **Fotos de clasificación**: `/static/uploads/clasificacion/`
- **Imágenes de básculas**: `/static/uploads/bascula/`
- **PDFs generados**: `/static/pdfs/`
- **Guías HTML**: `/static/guias/`
- **Códigos QR**: `/static/qr/`

## Rutas principales

### Entrada
- `/`: Página principal para subir imágenes de tiquetes
- `/home`: Dashboard principal
- `/processing`: Procesamiento de imágenes
- `/review`: Revisión de datos extraídos
- `/register`: Registro final de datos de entrada

### Pesaje
- `/pesaje/<codigo>`: Página principal de pesaje
- `/pesaje-inicial/<codigo>`: Registro de pesaje bruto
- `/pesajes`: Listado de pesajes realizados

### Clasificación
- `/clasificacion/<codigo>`: Página de clasificación 
- `/clasificaciones/lista`: Listado de clasificaciones

### Pesaje Neto
- `/pesaje-neto/<codigo>`: Página de pesaje neto
- `/pesaje-neto/ver_resultados_pesaje_neto/<codigo>`: Resultados de pesaje neto

### Salida
- `/salida/registro_salida/<codigo>`: Registro de salida
- `/salida/ver_resultados_salida/<codigo>`: Resultados de salida

### Centralizado
- `/guia-centralizada/<codigo>`: Vista centralizada con todas las etapas

## Contacto

Para soporte, consultas o reporte de errores:
- Email: [correo del desarrollador]
- Teléfono: [número de contacto] 