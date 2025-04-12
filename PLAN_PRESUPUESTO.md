# Plan de Desarrollo: Funcionalidad de Carga de Presupuesto Mensual

Este documento detalla los pasos para implementar la carga y visualización del presupuesto de fruta en el dashboard.

## Fases y Pasos

**Fase 1: Estructura y Carga Básica**

-   [x] **1.1. Crear Nuevo Blueprint:**
    -   [x] Crear la estructura de carpetas: `app/blueprints/presupuesto/`
    -   [x] Crear archivos iniciales: `app/blueprints/presupuesto/__init__.py` y `app/blueprints/presupuesto/routes.py`.
    -   [x] Registrar el nuevo blueprint en la aplicación principal (`app/__init__.py`).
-   [ ] **1.2. Interfaz de Carga:**
    -   [ ] Añadir sección/botón de carga de archivo en `templates/dashboard.html`.
    -   [ ] Incluir `<input type="file">` y botón "Subir".
-   [x] **1.3. Ruta Backend para Carga:**
    -   [x] Crear la ruta `/presupuesto/upload` (o similar) en `app/blueprints/presupuesto/routes.py` que acepte `POST`.
    -   [x] Implementar la recepción básica del archivo (`request.files`).
    -   [x] Implementar validación inicial del tipo de archivo (ej. `.xlsx`, `.csv`).
    -   [x] Guardar el archivo temporalmente en `static/uploads/presupuestos/` (crear carpeta si no existe).
    -   [x] Devolver una respuesta JSON simple (éxito/error) al frontend.

**Fase 2: Procesamiento y Almacenamiento del Presupuesto**

-   [x] **2.1. Parsing del Archivo:**
    -   [x] Añadir librería de lectura (`pandas`) a `requirements.txt`.
    -   [x] En la ruta `/presupuesto/upload`, implementar la lógica básica para leer el archivo (`pandas`).
    -   [x] Extraer las columnas 'Fecha' y 'ToneladasProyectadas' (o nombres configurables).
    -   [x] Validar los datos (fechas válidas, números para toneladas).
    -   [ ] Determinar mes/año del presupuesto.
-   [x] **2.2. Estructura Base de Datos:**
    -   [x] Definir la nueva tabla `presupuesto_mensual` en `db_schema.py` (columnas: `id`, `fecha_presupuesto`, `toneladas_proyectadas`, `fecha_carga`).
    -   [x] Asegurarse de que la función `create_tables` en `db_schema.py` cree la nueva tabla.
-   [x] **2.3. Operaciones de Base de Datos:**
    -   [x] Crear archivo `app/utils/db_budget_operations.py`.
    -   [x] Crear función `guardar_datos_presupuesto(datos)`.
    -   [x] Crear función `obtener_datos_presupuesto(fecha_inicio, fecha_fin)`.
-   [x] **2.4. Integración Backend:**
    -   [x] Llamar a `guardar_datos_presupuesto` desde la ruta `/presupuesto/upload` después del parsing.

**Fase 3: Visualización en el Dashboard**

-   [x] **3.1. Modificar API del Dashboard:**
    -   [x] En la función `dashboard_stats` (`app/blueprints/misc/routes.py`), llamar a `obtener_datos_presupuesto` usando el rango de fechas del filtro.
    -   [x] Añadir los datos del presupuesto recuperados a la respuesta JSON.
    -   [ ] Asegurarse de que los datos del presupuesto estén formateados para coincidir con las etiquetas del gráfico diario.
-   [x] **3.2. Actualizar Gráfico Frontend:**
    -   [x] En el JavaScript de `templates/dashboard.html`, leer los datos del presupuesto de la respuesta de la API.
    -   [x] Añadir/actualizar una nueva serie de datos ("Toneladas Presupuestadas") en el gráfico de "Peso Neto Diario".
    -   [x] Ajustar leyendas y tooltips del gráfico.

**Fase 4: Mejoras y Refinamientos (Opcional)**

-   [ ] Mejorar feedback al usuario durante/después de la carga.
-   [ ] Añadir opción para ver/eliminar presupuestos cargados.
-   [ ] Calcular y mostrar KPI de desviación (Real vs. Presupuesto).
-   [ ] Añadir manejo de errores más robusto. 