# TiquetesApp

Sistema de gestión de tiquetes para el registro, pesaje y clasificación de entradas a planta.

## Descripción

TiquetesApp es una aplicación web desarrollada con Flask que permite gestionar el proceso completo de registro, pesaje y clasificación de vehículos que ingresan a la planta. El sistema captura imágenes, datos del vehículo, información de pesaje y utiliza técnicas de análisis de imágenes para clasificar automáticamente los ingresos.

## Características principales

- Registro de vehículos y conductores
- Captura y procesamiento de imágenes
- Pesaje de vehículos
- Clasificación automática de ingresos
- Generación de tiquetes PDF
- Panel de administración
- API para integración con otros sistemas

## Reestructuración del proyecto

La aplicación ha sido completamente reestructurada utilizando Flask Blueprints para mejorar la organización, mantenibilidad y escalabilidad del código. Los módulos principales ahora están organizados como blueprints independientes:

- **Entrada**: Gestión de registros de entrada
- **Pesaje**: Proceso de pesaje de vehículos
- **Clasificación**: Sistema de clasificación automática
- **Misc**: Funcionalidades misceláneas y webhooks
- **Admin**: Administración del sistema
- **API**: Endpoints para integración con otros sistemas

## Instalación

1. Clonar el repositorio:
```bash
git clone [url-del-repositorio]
cd TiquetesApp
```

2. Crear y activar entorno virtual:
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

3. Instalar dependencias:
```bash
make install-deps
# Alternativa: pip install -r requirements.txt
```

4. Configurar la aplicación:
- Copiar `config.py.example` a `config.py`
- Editar `config.py` con los valores adecuados para su entorno

5. Iniciar la aplicación:
```bash
make run
# Alternativa: python3 run.py
```

## Comandos útiles

Se ha incluido un Makefile para facilitar tareas comunes:

```bash
# Ver comandos disponibles
make help

# Ejecutar la aplicación
make run

# Limpiar archivos temporales
make clean-temp

# Limpiar archivos redundantes
make clean-redundant

# Corregir URLs en las plantillas
make fix-templates

# Verificar la base de datos
make check-db

# Instalar dependencias
make install-deps
```

## Estructura del proyecto

Para comprender mejor la estructura y organización del proyecto, consulte la [documentación de estructura del proyecto](docs/project_structure.md).

## Webhooks y APIs

La aplicación proporciona varios webhooks y APIs para integración con sistemas externos:

- **Webhooks**: 
  - `/webhook/tiquete`: Notificaciones sobre tiquetes
  - `/webhook/clasificacion`: Resultados de clasificación
  - `/webhook/procesamiento`: Eventos de procesamiento
  - `/webhook/pesaje`: Notificaciones de pesaje

- **APIs**:
  - `/api/tiquetes`: CRUD para tiquetes
  - `/api/clasificacion`: API para resultados de clasificación
  - `/api/stats`: Estadísticas generales

## Requisitos

- Python 3.8+
- Flask
- SQLAlchemy
- Pillow (para procesamiento de imágenes)
- Otras dependencias listadas en requirements.txt

## Documentación

- [Estructura del proyecto](docs/project_structure.md)
- [Manual de usuario](docs/user_manual.md) (pendiente)
- [API Reference](docs/api_reference.md) (pendiente)

## Contacto

Para soporte o consultas:
- Email: [email-de-contacto]
- Teléfono: [número-de-contacto]