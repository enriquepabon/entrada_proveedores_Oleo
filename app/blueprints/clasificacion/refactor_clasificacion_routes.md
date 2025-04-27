# Plan de Refactorización: Dividir clasificacion/routes.py

**IMPORTANTE:** Sigue estos pasos estrictamente en orden. **Realiza solo UN paso a la vez**, prueba tu aplicación localmente después de cada cambio y **confirma que todo funciona** antes de proceder al siguiente paso. Si algo falla, deshaz el cambio de ese paso y avísame.

**Objetivo:** Dividir `app/blueprints/clasificacion/routes.py` en archivos más pequeños y manejables (`views.py`, `processing.py`, `helpers.py`) sin alterar la funcionalidad.

---

**Paso 0: Preparación (Backup y Creación de Archivos)**

1.  **Backup:** Haz una copia de seguridad completa de tu archivo `app/blueprints/clasificacion/routes.py` actual. Guárdala en un lugar seguro fuera del proyecto por si necesitas revertir todo.
2.  **Crear Archivos:** Dentro del directorio `app/blueprints/clasificacion/`, crea los siguientes archivos **vacíos**:
    *   `__init__.py`
    *   `views.py`
    *   `processing.py`
    *   `helpers.py`

3.  **Confirmación:** Confírmame cuando hayas hecho el backup y creado los archivos vacíos para pasar al siguiente paso.

---

**Paso 1: Mover Definición del Blueprint a `__init__.py`**

1.  **Acción:** Mueve la línea donde defines el Blueprint (`bp = Blueprint(...)`) desde `routes.py` al archivo `__init__.py`.
2.  **Archivos Involucrados:**
    *   **Cortar** de `app/blueprints/clasificacion/routes.py`
    *   **Pegar** en `app/blueprints/clasificacion/__init__.py`
3.  **Código en `app/blueprints/clasificacion/__init__.py`:**
    ```python
    # app/blueprints/clasificacion/__init__.py
    from flask import Blueprint
    import logging # Asegúrate que logging está importado si lo usas en el blueprint

    # Configurar logger específico para este blueprint si es necesario
    logger = logging.getLogger(__name__)

    # Define el Blueprint aquí
    # Asegúrate que los argumentos ('clasificacion', __name__, etc.) sean los mismos que tenías
    bp = Blueprint('clasificacion', __name__, template_folder='templates', static_folder='static', url_prefix='/clasificacion')

    # Importa los módulos de rutas DESPUÉS de definir bp para evitar importaciones circulares
    # Por ahora, solo importaremos el original 'routes' para que siga funcionando.
    # En pasos posteriores, cambiaremos esto para importar 'views', 'processing', etc.
    from . import routes
    ```
4.  **Código en `app/blueprints/clasificacion/routes.py`:**
    *   **Elimina** la línea `bp = Blueprint(...)`.
    *   **Añade** la siguiente importación al principio del archivo (junto con los otros imports):
        ```python
        from . import bp
        ```
5.  **Prueba:**
    *   Reinicia tu aplicación Flask.
    *   Verifica que la aplicación arranque sin errores de importación relacionados con el blueprint `clasificacion`.
    *   Navega a un par de rutas del blueprint de clasificación (ej. `/clasificacion/clasificaciones/lista`, `/clasificacion/ver_resultados_clasificacion/...`). ¿Se cargan correctamente?
6.  **Confirmación:** Confírmame si la aplicación arranca y las rutas de clasificación siguen funcionando después de mover la definición del `bp`.

---

**Paso 2: Mover Funciones Auxiliares (Helpers) a `helpers.py`**

1.  **Identificación:** Busca funciones dentro de `routes.py` que **NO** sean rutas (es decir, que no tengan el decorador `@bp.route(...)`). Ejemplos probables:
    *   `process_images_with_roboflow`
    *   `generate_annotated_image`
    *   `DirectRoboflowClient` (la clase completa)
    *   `get_utc_timestamp_str` (si solo se usa aquí)
    *   `es_archivo_imagen` (si solo se usa aquí)
    *   `decode_image_data` (si solo se usa aquí)
    *   `get_utils_instance` (si solo se usa aquí)
    *   `get_clasificacion_by_codigo_guia` (si solo se usa aquí)
    *   Cualquier otra función sin `@bp.route`.
2.  **Acción:** Mueve **SOLO las definiciones de estas funciones auxiliares y la clase `DirectRoboflowClient`** desde `routes.py` al archivo `helpers.py`.
3.  **Archivos Involucrados:**
    *   **Cortar** de `app/blueprints/clasificacion/routes.py`
    *   **Pegar** en `app/blueprints/clasificacion/helpers.py`
4.  **Importaciones en `helpers.py`:**
    *   Asegúrate de que `helpers.py` tenga **TODAS las importaciones** necesarias para que *esas funciones específicas* se ejecuten (ej. `os`, `json`, `logging`, `time`, `base64`, `requests`, `Image`, `current_app`, `traceback`, `re`, `sqlite3`, etc.). Copia las importaciones relevantes desde el inicio de `routes.py`.
    *   Añade al principio de `helpers.py`:
        ```python
        import logging
        logger = logging.getLogger(__name__)
        # ... otros imports necesarios para las funciones movidas ...
        from flask import current_app # Si usan current_app
        # Importa otras utils si son necesarias
        # from app.utils.common import CommonUtils
        # from db_operations import ... (si usan funciones de db)
        ```
5.  **Importaciones en `routes.py`:**
    *   Donde antes se llamaba directamente a estas funciones (ej. `result = process_images_with_roboflow(...)`), ahora necesitas importarlas desde `helpers`. Añade al principio de `routes.py`:
        ```python
        from .helpers import (
            process_images_with_roboflow,
            generate_annotated_image,
            DirectRoboflowClient,
            get_utc_timestamp_str, # Añade todas las funciones que moviste
            es_archivo_imagen,
            decode_image_data,
            get_utils_instance,
            get_clasificacion_by_codigo_guia
            # ... etc
        )
        ```
    *   Puedes eliminar las importaciones de `routes.py` que *solo* eran usadas por las funciones que moviste a `helpers.py`.
6.  **Prueba:**
    *   Reinicia tu aplicación Flask.
    *   Prueba funcionalidades que dependan específicamente de las funciones movidas:
        *   Inicia un procesamiento automático (esto llamará a `process_images_with_roboflow`).
        *   Verifica los resultados (esto podría usar `generate_annotated_image` o `get_clasificacion_by_codigo_guia`).
    *   Revisa los logs buscando errores.
7.  **Confirmación:** Confírmame si las funcionalidades que usan los helpers movidos siguen operando correctamente.

---

**Paso 3: Mover Rutas de Procesamiento a `processing.py`**

1.  **Identificación:** Busca rutas en `routes.py` que se encarguen principalmente de **recibir datos (POST), iniciar tareas, verificar estados o realizar acciones en segundo plano**. Ejemplos probables:
    *   `/registrar_clasificacion` (POST)
    *   `/registrar_clasificacion_api` (POST)
    *   `/procesar_clasificacion` (POST)
    *   `/iniciar_procesamiento` (POST)
    *   `/check_procesamiento_status` (GET, pero relacionado con procesamiento)
    *   `/procesar_automatico` (POST)
    *   `/guardar_clasificacion_final` (POST)
    *   `/regenerar_imagenes` (GET/POST, acción de procesamiento)
    *   `/sync_clasificacion` (GET, acción de procesamiento)
2.  **Acción:** Mueve **SOLO las definiciones de estas rutas (con sus decoradores `@bp.route(...)`)** desde `routes.py` a `processing.py`.
3.  **Archivos Involucrados:**
    *   **Cortar** de `app/blueprints/clasificacion/routes.py`
    *   **Pegar** en `app/blueprints/clasificacion/processing.py`
4.  **Importaciones en `processing.py`:**
    *   Añade al principio:
        ```python
        from flask import request, jsonify, redirect, url_for, flash, current_app, render_template # etc.
        from . import bp # Importar el blueprint
        import logging
        logger = logging.getLogger(__name__)
        # Importar helpers necesarios
        from .helpers import process_images_with_roboflow, DirectRoboflowClient # etc.
        # Importar utils generales o db_operations si se usan
        from app.utils.common import CommonUtils, get_utc_timestamp_str # Ejemplo
        import db_operations # Ejemplo
        import db_utils # Ejemplo
        # ... CUALQUIER OTRA importación que usen ESTAS rutas ...
        ```
5.  **Importaciones en `__init__.py`:**
    *   Modifica la última línea para que también importe `processing`:
        ```python
        # app/blueprints/clasificacion/__init__.py
        # ... (definición de bp) ...

        # Importa los módulos que contienen las rutas
        from . import routes # Mantén este por ahora
        from . import processing # Añade esta línea
        ```
6.  **Prueba:**
    *   Reinicia la aplicación.
    *   Intenta realizar las acciones correspondientes a las rutas movidas:
        *   Registra una clasificación manual.
        *   Inicia un procesamiento automático.
        *   Verifica el estado.
        *   Guarda una clasificación final.
    *   Revisa que funcionen y que los `redirect` o respuestas JSON sean correctos. Revisa los logs.
7.  **Confirmación:** Confírmame si las rutas de procesamiento funcionan correctamente desde `processing.py`.

---

**Paso 4: Mover Rutas de Vistas a `views.py`**

1.  **Identificación:** Busca las rutas restantes en `routes.py`. Estas suelen ser las que **muestran páginas HTML al usuario (GET)**. Ejemplos:
    *   `/` (si existe dentro del blueprint)
    *   `/<codigo>` (la principal de clasificación)
    *   `/prueba-clasificacion/<codigo>`
    *   `/clasificaciones`
    *   `/clasificaciones/lista`
    *   `/ver_resultados_clasificacion/<path:url_guia>`
    *   `/procesar_clasificacion_manual/<path:url_guia>` (GET)
    *   `/procesar_imagenes/<path:url_guia>` (¡Ojo! Esta parece más de vista que de procesamiento)
    *   `/generar_pdf_clasificacion/<codigo_guia>`
    *   `/print_view_clasificacion/<codigo_guia>`
    *   `/success/<path:codigo_guia>`
    *   `/forzar_ver_clasificacion/<path:url_guia>`
    *   `/forzar_ver_clasificacion_v2/<path:url_guia>`
    *   `/test_annotated_image/<path:url_guia>`
    *   `/ver_detalles_clasificacion/<path:url_guia>`
2.  **Acción:** Mueve **SOLO las definiciones de estas rutas de vista (con sus decoradores `@bp.route(...)`)** desde `routes.py` a `views.py`.
3.  **Archivos Involucrados:**
    *   **Cortar** de `app/blueprints/clasificacion/routes.py`
    *   **Pegar** en `app/blueprints/clasificacion/views.py`
4.  **Importaciones en `views.py`:**
    *   Añade al principio:
        ```python
        from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response # etc.
        from . import bp # Importar el blueprint
        import logging
        logger = logging.getLogger(__name__)
        # Importar helpers necesarios
        from .helpers import get_clasificacion_by_codigo_guia, generate_annotated_image # etc.
        # Importar utils generales o db_operations/db_utils si se usan
        from app.utils.common import CommonUtils, format_datetime_filter # Ejemplo
        import db_operations # Ejemplo
        import db_utils # Ejemplo
        import json # Ejemplo
        import os # Ejemplo
        # ... CUALQUIER OTRA importación que usen ESTAS rutas ...
        ```
5.  **Importaciones en `__init__.py`:**
    *   Modifica la última parte para importar `views` en lugar de `routes`:
        ```python
        # app/blueprints/clasificacion/__init__.py
        # ... (definición de bp) ...

        # Importa los módulos que contienen las rutas
        # from . import routes # Comenta o elimina esta línea
        from . import views # Añade esta
        from . import processing
        from . import helpers # Aunque no tenga rutas, puede ser útil importarlo aquí si otros módulos del blueprint lo necesitan
        ```
6.  **Archivo `routes.py`:** Este archivo ahora debería estar **vacío** o contener solo importaciones y quizás alguna configuración muy específica que no encaje en otro lugar (idealmente debería estar vacío). Puedes renombrarlo a `routes_old.py` o eliminarlo si estás seguro.
7.  **Prueba:**
    *   Reinicia la aplicación.
    *   Navega a todas las páginas de clasificación que moviste a `views.py`.
    *   Verifica que carguen los datos, se muestren las plantillas correctamente, y los formularios (si los hay) funcionen.
    *   Prueba la generación de PDFs si moviste esas rutas.
    *   Revisa los logs.
8.  **Confirmación:** Confírmame si todas las vistas de clasificación funcionan correctamente desde `views.py`.

---

**Paso 5: Limpieza Final (Opcional pero Recomendado)**

1.  **Revisar Importaciones:** Revisa los archivos `__init__.py`, `views.py`, `processing.py`, y `helpers.py`. Elimina cualquier importación que ya no se esté utilizando en ese archivo específico.
2.  **Consistencia:** Asegúrate de que la forma de importar (ej. `from . import bp`, `from .helpers import ...`) sea consistente.
3.  **Eliminar `routes.py`:** Si estás seguro de que todo funciona y el archivo `routes.py` original está vacío o solo contiene comentarios, puedes eliminarlo.
4.  **Prueba Final:** Realiza una prueba completa de todo el flujo de clasificación, desde el inicio hasta el final, incluyendo la visualización en el dashboard.
5.  **Confirmación:** Confírmame que has realizado la limpieza y la prueba final ha sido exitosa.

---