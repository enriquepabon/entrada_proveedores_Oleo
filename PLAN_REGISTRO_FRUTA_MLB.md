# Plan para Implementar el Listado "Registro de Fruta MLB"

**Instrucción:** Seguiremos este plan paso a paso. Realizaré el cambio correspondiente a cada paso. Tú probarás el código en tu entorno local. Una vez que me des tu retroalimentación y aprobación, procederé con el siguiente paso.

## Checklist

*   [ ] **Paso 1:** Modificar `templates/home.html` para cambiar la tarjeta "Registros de Salida" por "Registro de Fruta MLB" y enlazarla a la nueva ruta `/registros-fruta-mlb` (Endpoint: `misc.registro_fruta_mlb`).
*   [ ] **Paso 2:** Definir la ruta básica `/registros-fruta-mlb` en `app/blueprints/misc/routes.py` y crear la función de vista asociada (`registro_fruta_mlb`).
*   [ ] **Paso 3:** Crear el archivo de plantilla básico `templates/misc/registro_fruta_mlb.html` con la estructura inicial (heredando de `base.html`).
*   [ ] **Paso 4:** Implementar la lógica en la función de vista (`registro_fruta_mlb` en `app/blueprints/misc/routes.py`) para obtener los datos necesarios de las tablas `entry_records`, `pesajes_bruto`, `clasificaciones`, `pesajes_neto` y `salidas`, combinándolos por `codigo_guia`. Se priorizará la información más reciente o relevante si hay duplicados teóricos (aunque `codigo_guia` debería ser único por tabla principal).
*   [ ] **Paso 5:** Añadir la lógica en la vista para determinar el "Estado" de cada registro basado en la existencia de datos en las tablas correspondientes:
    *   'Entrada Registrada': Existe en `entry_records`.
    *   'Pesaje Bruto Completo': Existe en `pesajes_bruto`.
    *   'Clasificación Completa': Existe en `clasificaciones`.
    *   'Pesaje Neto Completo': Existe en `pesajes_neto`.
    *   'Cerrada': Existe en `salidas`. (El estado más avanzado tiene prioridad).
*   [ ] **Paso 6:** Pasar la lista de datos combinados y con estado a la plantilla `registro_fruta_mlb.html`.
*   [ ] **Paso 7:** Actualizar `registro_fruta_mlb.html` para mostrar los datos en una tabla con las columnas:
    *   Fecha y hora de registro entrada (Desde `entry_records`).
    *   Codigo Guia (Link a detalle de entrada - `entrada.ver_detalle_entrada` o similar).
    *   Codigo Proveedor.
    *   Cantidad de Racimos (Desde `entry_records`).
    *   Pesaje Bruto (Link a `pesaje.ver_resultados_pesaje`).
    *   Clasificación (Link a `clasificacion.ver_detalle_clasificacion` o similar).
    *   Pesaje Neto (Link a `pesaje.ver_resultados_pesaje_neto` o similar).
    *   Estado (Calculado en Paso 5).
    *   Link Guía Centralizada (`misc.ver_guia_centralizada`).
*   [ ] **Paso 8:** Calcular los totales (Peso Bruto, Peso Neto, Cantidad Racimos) en la vista y mostrarlos en la plantilla.
*   [ ] **Paso 9:** Implementar la funcionalidad de filtrado (por fechas, proveedor, estado) en la vista.
*   [ ] **Paso 10:** Añadir los controles de filtrado (inputs de fecha, select de proveedor, select de estado, botón de aplicar) en la plantilla `registro_fruta_mlb.html`.
*   [ ] **Paso 11:** Añadir el botón "Imprimir Listado" en la plantilla y la funcionalidad básica de impresión usando JavaScript (`window.print()`).

## Notas Adicionales

*   Los nombres exactos de los endpoints para los links en el Paso 7 pueden necesitar ajustes según las rutas existentes o que creemos.
*   La lógica de combinación de datos (Paso 4) debe manejar casos donde falten datos en alguna tabla (ej. una guía solo tiene entrada pero no pesaje).
*   Se asumirá que `codigo_guia` es la clave principal para relacionar la información entre las tablas. 