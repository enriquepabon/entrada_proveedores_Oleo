# Proyecto: Comparación de Guías SAP y Pesos Netos desde Archivo de Texto

## Objetivo del Proyecto
Implementar una funcionalidad que permita a los usuarios subir un archivo de **texto delimitado por tabuladores (.txt, .tsv)** conteniendo códigos de guía de transporte SAP (`Doc. mat.`) y sus respectivos pesos netos (`Ctd.en UM entrada`). El sistema leerá este archivo, buscará las guías SAP en la base de datos de la aplicación, comparará los pesos netos y mostrará una tabla con los resultados, incluyendo el código de guía interno de la aplicación, la fecha de registro, los pesos de ambas fuentes y la diferencia, además de alertas por inconsistencias.

## Instrucciones Generales
- El agente (AI) ejecutará cada paso.
- El usuario (humano) probará la funcionalidad implementada en cada paso.
- El usuario proporcionará retroalimentación y aprobará el paso antes de que el agente continúe con el siguiente.
- Se utilizará la librería `pandas` para leer el archivo de texto. (`openpyxl` se mantiene en dependencias por si se requiere soporte Excel en el futuro, pero no es esencial para archivos .txt/.tsv).
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
            *   Contendrá un formulario (`<form method="POST" enctype="multipart/form-data">`) que permita al usuario seleccionar un archivo (`<input type="file" name="archivo_sap" accept=".txt, .tsv">`). (Nombre de input `archivo_sap` consistente con el código).
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

- [x] **Paso 3: Procesamiento del Archivo de Texto y Comparación (Lógica Principal)**
    -   **Agente:**
        1.  **En la ruta `POST /` en `app/blueprints/comparacion_guias/routes.py`:**
            *   Después de las validaciones del archivo:
                *   Leer el archivo de texto usando `pd.read_csv(file, sep='\t')`. Usar un bloque `try-except` para capturar errores de lectura o formato.
                *   Verificar si las columnas requeridas (`Doc. mat.` y `Ctd.en UM entrada`) existen en el DataFrame de pandas. Si no, mostrar un error flash y redirigir.
                *   Inicializar una lista `resultados_comparacion = []`.
                *   Iterar sobre las filas del DataFrame (`for index, row in df.iterrows():`).
                    *   Obtener `codigo_sap_archivo = str(row['Doc. mat.'])` y `peso_neto_archivo_str = str(row['Ctd.en UM entrada'])`. (Asegurar conversión a string).
                    *   Inicializar `codigo_guia_app = '-'`, `fecha_registro_app = '-'`, `peso_neto_app_str = '-'`, `diferencia_peso_str = '-'`, `alerta_icono = ''`.
                    *   **Validación del peso del archivo de texto:** Intentar convertir `peso_neto_archivo_str` (que podría tener comas como decimales) a float. Si falla, registrarlo para la alerta (`alerta_icono = 'peso_invalido'`) y continuar.
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
        -   Preparar un archivo de texto delimitado por tabuladores de prueba con los formatos correctos.
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
        -   Subir el archivo de texto de prueba.
        -   Verificar que la tabla de resultados se muestre correctamente con todos los datos.
        -   Verificar que las alertas aparezcan donde correspondan y sean distintivas.
        -   Verificar el formato de los números. Aprobar para finalizar. 