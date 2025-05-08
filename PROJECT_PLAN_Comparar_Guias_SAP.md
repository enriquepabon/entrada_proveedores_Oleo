# Proyecto: Comparación de Guías SAP y Pesos Netos desde Archivo de Excel

## Objetivo del Proyecto
Implementar una funcionalidad que permita a los usuarios subir un archivo de **Excel (.xlsx, .xls) o XML (.xml)** conteniendo códigos de guía de transporte SAP (columna `Guia de transporte` en Excel, o etiqueta `<Guia_de_transporte>` - pendiente de confirmación - en XML) y sus respectivos pesos netos (columna `Peso neto` en Excel, o etiqueta `<Peso_neto>` - pendiente de confirmación - en XML). El sistema leerá este archivo, buscará las guías SAP en la base de datos de la aplicación, comparará los pesos netos y mostrará una tabla con los resultados, incluyendo el código de guía interno de la aplicación, la fecha de registro, los pesos de ambas fuentes y la diferencia, además de alertas por inconsistencias.

## Instrucciones Generales
- El agente (AI) ejecutará cada paso.
- El usuario (humano) probará la funcionalidad implementada en cada paso.
- El usuario proporcionará retroalimentación y aprobará el paso antes de que el agente continúe con el siguiente.
- Se utilizará la librería `pandas` para leer archivos Excel y `xml.etree.ElementTree` para archivos XML.
- La funcionalidad residirá en un nuevo blueprint llamado `comparacion_guias` con el prefijo de URL `/comparacion-guias`.

## Pasos del Proyecto

- [x] **Paso 0: Instalación de Dependencia y Actualización de `requirements.txt`**
    -   **Agente:**
        1.  Asegurar que `pandas` esté instalado. Ejecutar `pip install pandas openpyxl` (openpyxl es opcional si solo se usarán archivos .txt/.tsv, pero bueno tenerlo).
        2.  Ejecutar `pip freeze > requirements.txt` para actualizar el archivo de dependencias.
    -   **Usuario:**
        - Confirmar que la instalación/verificación fue exitosa y `requirements.txt` se actualizó.

- [x] **Paso 1: Crear Estructura del Blueprint y Template para Carga de Archivo**
    -   **Agente:**
        1.  Crear directorio `app/blueprints/comparacion_guias/`.
        2.  Crear `app/blueprints/comparacion_guias/__init__.py` definiendo el `Blueprint('comparacion_guias', __name__, template_folder='../../../templates/comparacion_guias', url_prefix='/comparacion-guias')`.
        3.  Crear `app/blueprints/comparacion_guias/routes.py`.
        4.  Crear el archivo HTML: `app/templates/comparacion_guias/comparar_guias_sap.html`.
            *   Este template heredará de `base.html`.
            *   Incluirá un título (ej. "Comparar Guías SAP y Pesos Netos").
            *   Contendrá un formulario (`<form method="POST" enctype="multipart/form-data">`) que permita al usuario seleccionar un archivo (`<input type="file" name="archivo_sap" accept=".xlsx,.xls,.xml">`). (Nombre de input `archivo_sap` consistente con el código).
            *   Tendrá un botón de envío ("Comparar Archivo").
            *   Incluirá una sección para mostrar mensajes de error o la tabla de resultados.
    -   **Usuario:**
        - Revisar la estructura del blueprint y el template creado. Aprobar para continuar.

- [x] **Paso 2: Crear Rutas Backend (GET y POST inicial) en el Nuevo Blueprint**
    -   **Agente:**
        1.  En `app/blueprints/comparacion_guias/routes.py`:
            *   Importar `pandas` (ej. `import pandas as pd`), `current_app`.
            *   Importar el blueprint local: `from . import bp`.
            *   Crear la ruta `GET /` (relativa al prefijo del blueprint, es decir, `/comparacion-guias/`):
                *   Proteger con `@login_required`.
                *   Renderizará `comparar_guias_sap.html` (Flask buscará en la `template_folder` del blueprint).
            *   Crear la estructura inicial de la ruta `POST /`:
                *   Proteger con `@login_required`.
                *   Verificar si se subió un archivo (`'archivo_sap' in request.files`).
                *   Si no hay archivo, mostrar un error flash y redirigir de nuevo al formulario (`request.url`).
                *   Obtener el archivo: `file = request.files['archivo_sap']`.
                *   Verificar si el nombre del archivo está vacío.
        2.  En `app/__init__.py`, en la función `register_blueprints`:
            *   Importar el nuevo blueprint: `from app.blueprints.comparacion_guias import bp as comparacion_guias_bp`.
            *   Registrarlo: `app.register_blueprint(comparacion_guias_bp)`.
    -   **Usuario:**
        -   Navegar a `/comparacion-guias/`. Verificar que se muestre el formulario.
        -   Intentar enviar el formulario sin archivo y verificar el mensaje de error. Aprobar para continuar.

- [x] **Paso 3: Procesamiento del Archivo (Excel o XML) y Comparación (Lógica Principal)**
    -   **Agente:**
        1.  **En la ruta `POST /` en `app/blueprints/comparacion_guias/routes.py`:**
            *   Después de las validaciones del archivo:
                *   **Si es Excel:** Leer el archivo usando `pd.read_excel(file)`. Verificar que la primera columna sea "Guia de transporte" y la segunda "Peso neto" (o usarlas por defecto si los nombres no coinciden).
                *   **Si es XML:** Parsear el archivo usando `ET.parse(file)`. Buscar elementos `<item>` (o similar) y dentro de ellos `<Guia_de_transporte>` y `<Peso_neto>` (o los nombres de etiqueta que el usuario especifique/confirme).
                *   Usar un bloque `try-except` general para capturar errores de lectura o formato para ambos tipos.
                *   Inicializar una lista `resultados_comparacion = []`.
                *   Iterar sobre las filas del DataFrame (Excel) o los elementos correspondientes (XML).
                    *   Obtener `codigo_sap_archivo` (de la columna "Guia de transporte" o etiqueta `<Guia_de_transporte>`). Ya no se necesita procesar para quitar el "-AÑO". Obtener `peso_neto_archivo_str` (de la columna "Peso neto" o etiqueta `<Peso_neto>`).
                    *   Inicializar `codigo_guia_app = '-'`, `fecha_registro_app = '-'`, `peso_neto_app_str = '-'`, `diferencia_peso_str = '-'`, `alerta_icono = ''`.
                    *   **Validación del peso del archivo:** Intentar convertir `peso_neto_archivo_str` a float. Si falla, registrarlo para la alerta (`alerta_icono = 'peso_invalido'`) y continuar.
                    *   **Búsqueda en DB:**
                        *   Conectar a `tiquetes.db` (usar `get_db_connection()` de `app.utils.common` o `app.utils.auth_utils` si es aplicable, o conexión directa).
                        *   Buscar en `pesajes_bruto` donde `codigo_guia_transporte_sap` coincida con `codigo_sap_archivo`.
                        *   Si se encuentra, obtener el `codigo_guia` de `pesajes_bruto`.
                        *   Con ese `codigo_guia`, buscar en `entry_records` para obtener `timestamp_registro_utc` (y formatearlo usando `convertir_timestamp_a_fecha_hora` de `misc.routes` - considerar moverla a `common.py`).
                        *   Con ese `codigo_guia`, buscar en `pesajes_neto` para obtener `peso_neto`.
                        *   Si `codigo_sap_archivo` no se encuentra en `pesajes_bruto`, marcar `alerta_icono = 'no_encontrado_db'`.
                    *   Si se encontraron ambos pesos y son numéricos, calcular la diferencia.
                    *   Añadir un diccionario a `resultados_comparacion` con todos los campos definidos para la tabla de resultados.
                *   Renderizar de nuevo `comparar_guias_sap.html`, pasando `resultados_comparacion` a la plantilla.
    -   **Usuario:**
        -   Preparar un archivo de Excel o XML de prueba con los formatos correctos.
        -   Subir el archivo y verificar la lógica de procesamiento. Aprobar para continuar.

- [x] **Paso 4: Mostrar Resultados en el Template**
    -   **Agente:**
        1.  **En `app/templates/comparacion_guias/comparar_guias_sap.html`:**
            *   Debajo del formulario, añadir una sección `{% if resultados_comparacion %}`.
            *   Dentro del `if`, crear una tabla HTML para mostrar los resultados.
            *   La tabla tendrá las columnas: "Doc. mat. (SAP)", "Guía App", "Fecha App", "Peso Archivo", "Peso App", "Diferencia", "Alerta".
            *   Iterar sobre `resultados_comparacion` y mostrar cada fila.
            *   Para la columna "Alerta", mostrar un icono específico o mensaje basado en el valor de `alerta_icono` (ej. diferente para 'peso_invalido' vs 'no_encontrado_db').
            *   Formatear los números de peso usando el filtro `format_es`.
    -   **Usuario:**
        -   Subir el archivo de Excel o XML de prueba.
        -   Verificar que la tabla de resultados se muestre correctamente con todos los datos.
        -   Verificar que las alertas aparezcan donde correspondan y sean distintivas.
        -   Verificar el formato de los números. Aprobar para finalizar. 