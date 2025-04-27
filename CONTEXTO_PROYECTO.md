# Contexto del Proyecto: TiquetesApp

**Objetivo:** Documentar la estructura, recursos principales y templates de la aplicación Flask para facilitar la integración de nuevas funcionalidades como la autenticación.

**Fecha:** {datetime.now().strftime('%Y-%m-%d')}

---

## 1. Estructura del Proyecto

La aplicación sigue una estructura basada en Blueprints de Flask:

```
/
├── run.py                  # Punto de entrada de la aplicación, configuración inicial.
├── config.py               # Configuración específica (puede que parte esté en run.py).
├── requirements.txt        # Dependencias de Python.
├── tiquetes.db             # Base de datos SQLite principal.
├── db_schema.py            # Define el esquema SQL para las tablas.
├── db_utils.py             # Funciones de utilidad para interactuar con la BD (especialmente entry_records).
├── db_operations.py        # Funciones de utilidad para operaciones CRUD en otras tablas (pesaje, clasificación, etc.).
├── app/                    # Directorio principal de la aplicación Flask.
│   ├── __init__.py         # Fábrica de la aplicación (create_app), inicialización de extensiones.
│   ├── blueprints/         # Módulos de la aplicación (agrupados por funcionalidad).
│   │   ├── __init__.py
│   │   ├── admin/          # Rutas y lógica para tareas administrativas.
│   │   ├── api/            # Rutas para endpoints API (ej. verificación placa).
│   │   ├── clasificacion/  # Rutas y lógica para el proceso de clasificación.
│   │   ├── entrada/        # Rutas y lógica para el registro de entrada.
│   │   ├── misc/           # Rutas diversas, utilidades generales (upload, pdf, etc.).
│   │   ├── pesaje/         # Rutas y lógica para el pesaje bruto.
│   │   ├── pesaje_neto/    # Rutas y lógica para el pesaje neto.
│   │   ├── presupuesto/    # Rutas y lógica para la gestión de presupuestos.
│   │   └── salida/         # Rutas y lógica para el registro de salida.
│   ├── static/             # Archivos estáticos (CSS, JS, imágenes, uploads).
│   │   ├── css/
│   │   ├── js/
│   │   ├── images/
│   │   └── uploads/        # Directorio para archivos subidos (tiquetes, placas, presupuestos).
│   │       ├── clasificacion/
│   │       └── presupuestos/
│   ├── templates/          # Plantillas HTML (Jinja2).
│   │   ├── base.html       # Plantilla base principal.
│   │   ├── index.html      # Página inicial para subir imágenes (tiquete/placa).
│   │   ├── home.html       # Panel principal con accesos a módulos.
│   │   ├── error.html      # Página genérica de error.
│   │   ├── guia_base.html  # Posible plantilla base para vistas de guía.
│   │   ├── guia_template.html # Template específico para mostrar datos de una guía (usado por misc/serve_guia).
│   │   ├── guia_centralizada.html # Vista consolidada de una guía específica.
│   │   ├── dashboard.html  # Panel de control/dashboard principal.
│   │   ├── registro_salida.html # Formulario para completar el registro de salida.
│   │   ├── resultados_salida.html # Muestra resultados después de registrar salida.
│   │   ├── (directorios por blueprint...) # ej. entrada/, pesaje/, etc.
│   │   └── components/     # Macros y componentes reutilizables (tablas, formularios).
│   │       ├── tables/
│   │       │   └── tabla_datos.html
│   │       └── clasificacion_datos.html
│   └── utils/              # Módulos de utilidad general.
│       ├── common.py       # Clases o funciones de utilidad comunes.
│       ├── image_processing.py # Lógica para procesar imágenes (placas, etc.).
│       └── db_budget_operations.py # Operaciones específicas para la tabla de presupuesto.
├── logs/                   # Directorio para archivos de log.
├── venv/                   # Entorno virtual (si se usa).
└── ...                     # Otros archivos de configuración, scripts, etc.
```

## 2. Recursos Principales

*   **Framework:** Flask
*   **Base de Datos:** SQLite (`tiquetes.db`). La interacción se realiza mayormente con el módulo `sqlite3` directamente a través de funciones en `db_utils.py` y `db_operations.py`.
*   **Gestión de Esquema:** Definido en `db_schema.py`.
*   **Librerías Clave (según run.py y uso general):**
    *   `Flask`: Núcleo de la aplicación web.
    *   `requests`: Para realizar llamadas a webhooks externos (ej. Roboflow, Make).
    *   `logging`: Para registrar eventos y errores.
    *   `Werkzeug`: Dependencia de Flask, usada directamente para `secure_filename` y potencialmente para hashing de contraseñas en la autenticación.
    *   `pandas`: Usado en el blueprint de presupuesto para leer archivos Excel/CSV.
*   **Templates:** Jinja2 (integrado en Flask).
*   **Frontend:** Bootstrap 5, Font Awesome para estilos e iconos. JavaScript para interactividad (ej. manejo de cámara, AJAX).

## 3. Descripción de Templates Principales (`templates/`)

*   `base.html`: Plantilla principal que define la estructura común (navegación, footer, bloques para contenido específico, CSS/JS base). El resto de templates suelen heredar de esta.
*   `index.html`: Página de inicio donde el usuario sube la imagen del tiquete y opcionalmente la placa para iniciar el proceso de registro de entrada. Incluye la funcionalidad de cámara.
*   `home.html`: Panel de control principal que ofrece accesos directos a las diferentes secciones y funcionalidades de la aplicación (Iniciar Registro, Listas, Búsqueda).
*   `error.html`: Plantilla genérica para mostrar mensajes de error al usuario.
*   `guia_base.html`: Parece ser una plantilla base alternativa o específica para las vistas relacionadas con una guía individual.
*   `guia_template.html`: Utilizada para generar y servir las páginas HTML estáticas de cada guía (accesibles vía `/guias/<filename>`). Muestra toda la información y el progreso de una guía específica.
*   `guia_centralizada.html`: Vista dinámica que muestra el estado y detalles consolidados de una guía específica, similar a `guia_template.html` pero generada al vuelo.
*   `dashboard.html`: Presenta un dashboard con estadísticas, gráficos y posiblemente KPIs relacionados con los registros.
*   `components/`: Contiene fragmentos de plantillas reutilizables (macros):
    *   `tables/tabla_datos.html`: Macros para generar tablas HTML filtrables y formularios de filtros.
    *   `clasificacion_datos.html`: Macros para mostrar los resultados de la clasificación (manual/automática).
    *   Otros componentes para estilos y datos específicos (`pesaje_datos.html`, `entrada_datos.html`, etc.).
*   `misc/registro_fruta_mlb.html`: Vista que muestra una tabla consolidada de todos los registros con filtros, mostrando el estado general de cada guía.
*   `registro_salida.html`: Formulario final del proceso donde se registran comentarios y se marca la salida del vehículo.
*   `resultados_salida.html`: Página que muestra la confirmación y los detalles finales después de completar el registro de salida.
*   Directorios específicos por blueprint (ej. `templates/entrada/`, `templates/pesaje/`): Contienen las plantillas específicas para las rutas definidas en esos blueprints (listas, formularios de edición, vistas de detalles, etc.).

---

Este documento servirá como referencia durante el desarrollo. ¿Estás listo para proceder con el **Paso 1** del `PLAN_AUTENTICACION.md` (Instalación y Configuración Inicial)? 