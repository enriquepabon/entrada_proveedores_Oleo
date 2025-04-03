# Plan de Refactorización de Timestamps

## Objetivo

Estandarizar el manejo de fechas y horas en toda la aplicación para mejorar la confiabilidad, mantenibilidad y consistencia.

## Lógica Ideal Propuesta

1.  **Almacenar Todo en UTC:** Guardar siempre las fechas y horas en la base de datos en UTC. Esto elimina la ambigüedad de la zona horaria. Es la práctica estándar recomendada.
2.  **Usar Formato Estándar:** Almacenar las fechas/horas en la base de datos como `TEXT` en formato ISO 8601 (`YYYY-MM-DD HH:MM:SS`).
3.  **Generar en UTC:** Utilizar `datetime.utcnow()` o equivalentes (`pytz.UTC.localize(datetime.now())`) para generar todos los timestamps al momento de la acción (registro, pesaje, etc.).
4.  **Convertir Solo para Mostrar:** Realizar la conversión a la zona horaria local del usuario (America/Bogota en este caso) **únicamente** en el momento de mostrar la fecha/hora al usuario final. Esto debe hacerse lo más tarde posible en el flujo:
    *   En las funciones de las rutas (views) justo antes de pasar los datos al template.
    *   O preferiblemente, usando filtros personalizados en las plantillas Jinja2.

## Estado Actual y Checklist

-   [x] **Schema `entry_records`:** Modificado para usar `timestamp_registro_utc TEXT` en lugar de `fecha_registro` y `hora_registro`.
-   [x] **Generación (`registrar_entrada`):** Modificado para generar `timestamp_registro_utc` usando `utcnow()` y guardarlo en formato `YYYY-MM-DD HH:MM:SS` UTC.
-   [x] **Lectura (`db_utils.py`):** Funciones `get_entry_records` y `get_entry_record_by_guide_code` actualizadas para leer el nuevo campo `timestamp_registro_utc`.
-   [x] **Lectura (`db_operations.py`):** Funciones como `get_pesaje_bruto_by_codigo_guia` y `get_provider_by_code` actualizadas para leer el nuevo campo `timestamp_registro_utc` de `entry_records`.
-   [ ] **Conversión TZ en `get_datos_guia` (`app/utils/common.py`):**
    -   [x] Conversión añadida para `timestamp_registro_utc` (y otros) como paso de compatibilidad.
    -   [ ] **TODO:** Mover esta conversión a la capa de vista/plantilla.
-   [ ] **Conversión TZ en `get_entry_record_by_guide_code` (`db_utils.py`):**
    -   [x] Conversión añadida para `timestamp_registro_utc` como paso de compatibilidad.
    -   [ ] **TODO:** Mover esta conversión a la capa de vista/plantilla.
-   [ ] **Revisar Otros Módulos (Generación):** Verificar que los módulos de `pesaje_bruto`, `clasificacion`, `pesaje_neto`, `salida` generen y almacenen sus respectivos timestamps en UTC y formato estándar.
-   [ ] **Revisar Otros Módulos (Lectura):** Verificar que todas las funciones que leen datos con timestamps los manejen correctamente (esperando UTC).
-   [ ] **Actualizar Plantillas:** Modificar todas las plantillas que muestran fechas/horas para que:
    -   Reciban el timestamp UTC (ej. `datos_guia.timestamp_registro_utc`).
    -   Utilicen un filtro Jinja2 (ej. `| format_datetime_bogota`) o reciban datos pre-formateados desde la ruta para mostrar la hora local.

## Pasos Futuros

1.  Continuar revisando y actualizando los demás módulos (`pesaje_bruto`, `clasificacion`, `pesaje_neto`, `salida`) para que generen y almacenen timestamps en UTC.
2.  Refactorizar las funciones de lectura (`get_datos_guia`, `get_entry_record_by_guide_code`, etc.) para que *no* hagan la conversión de zona horaria, devolviendo los timestamps en UTC.
3.  Actualizar todas las plantillas y rutas correspondientes para realizar la conversión a hora local justo antes de la visualización. 