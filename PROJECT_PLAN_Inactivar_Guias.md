# Proyecto: Funcionalidad para Inactivar Guías (Admin)

## Objetivo del Proyecto
Implementar la funcionalidad que permita a un usuario administrador marcar una guía específica como "Inactiva" directamente desde la tabla de registros en la página `registro_fruta_mlb.html`. Este estado "Inactiva" será persistente en la base de datos, se reflejará visualmente con un badge distintivo (rojo), y solo el administrador podrá realizar esta acción. Se añadirá también la opción de filtrar por este nuevo estado. La columna `is_active` que controlará esto no será visible directamente en el frontend.

## Instrucciones Generales
- El agente (AI) ejecutará cada paso.
- El usuario (humano) probará la funcionalidad implementada en cada paso.
- El usuario proporcionará retroalimentación y aprobará el paso antes de que el agente continúe con el siguiente.
- Se asumirá que existe un sistema de autenticación con Flask-Login y un objeto `current_user` disponible.
- Se asumirá que la tabla principal de guías es `entry_records`.
- Se añadirá una columna `is_admin` a la tabla `users` y al modelo `User`. Se usará `current_user.is_admin` para verificar si el usuario es administrador.

## Pasos del Proyecto

- [x] **Paso 1: Modificar Modelos/Base de Datos**
    -   **Agente:**
        1.  **Tabla `entry_records`:**
            *   Definir una función (ej. `ensure_entry_records_schema_extended` en `app/blueprints/misc/routes.py` o un archivo `db_schema.py` si se prefiere) que verifique la existencia de la tabla `entry_records`.
            *   Dentro de esa función, añadir lógica para verificar si existe la columna `is_active`.
            *   Si la columna `is_active` no existe, añadirla a la tabla `entry_records` con el tipo `INTEGER` y un valor por defecto de `1`. (SQL: `ALTER TABLE entry_records ADD COLUMN is_active INTEGER DEFAULT 1;`)
        2.  **Tabla `users` y Modelo `User`:**
            *   Definir una función (ej. `ensure_users_schema_extended` en `app/utils/auth_utils.py` o `db_schema.py`) que verifique la existencia de la tabla `users`.
            *   Dentro de esa función, añadir lógica para verificar si existe la columna `is_admin`.
            *   Si la columna `is_admin` no existe, añadirla a la tabla `users` con el tipo `INTEGER` y un valor por defecto de `0`. (SQL: `ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0;`)
            *   Modificar la clase `User` en `app/models/user_model.py` para incluir el atributo `is_admin` en su constructor y como propiedad.
            *   Actualizar las funciones `get_user_by_id` y `get_user_by_username` en `app/utils/auth_utils.py` para que recuperen el campo `is_admin` de la base de datos y lo pasen al constructor del objeto `User`.
        3.  **Llamada a las funciones de esquema:**
            *   Asegurar que ambas funciones de verificación de esquema (para `entry_records` y `users`) se llamen al iniciar la aplicación (probablemente en `app/__init__.py` después de `create_tables()` o dentro de un `db_schema.py` que se ejecute al inicio).
    -   **Usuario:**
        -   Verificar que la aplicación se inicie sin errores.
        -   Verificar que la columna `is_active` se haya añadido a la tabla `entry_records` (con default 1).
        -   Verificar que la columna `is_admin` se haya añadido a la tabla `users` (con default 0).
        -   Manualmente, actualizar la base de datos para que el usuario 'epabon' (o el administrador designado) tenga `is_admin = 1`.
        -   Aprobar para continuar.

- [x] **Paso 2: Crear Ruta Backend para Inactivar/Reactivar**
    -   **Agente:**
        1.  En `app/blueprints/misc/routes.py`, crear una nueva ruta: `@bp.route('/guias/<codigo_guia>/toggle_active', methods=['POST'])`.
        2.  Añadir el decorador `@login_required`.
        3.  Dentro de la ruta:
            *   Verificar si `current_user.is_admin` es `True`. Si no, devolver un error JSON (ej: `{'success': False, 'message': 'Permiso denegado'}`), status 403.
            *   Obtener el `codigo_guia` de la URL.
            *   Conectarse a la base de datos (`tiquetes.db`).
            *   Obtener el valor actual de `is_active` para esa `codigo_guia` en la tabla `entry_records`.
            *   Calcular el nuevo estado: `new_status = 0 if current_status == 1 else 1`.
            *   Actualizar la tabla `entry_records` estableciendo `is_active = new_status` donde `codigo_guia` coincida.
            *   Hacer `commit` de los cambios.
            *   Cerrar la conexión.
            *   Devolver una respuesta JSON indicando éxito y el nuevo estado (ej: `{'success': True, 'new_status': new_status}`).
    -   **Usuario:**
        -   Probar manualmente la ruta (usando `curl` o una herramienta similar) enviando un POST a `/guias/UN_CODIGO_VALIDO/toggle_active` (asegurándose de estar logueado como admin). Verificar que la respuesta JSON sea correcta y que el valor en la base de datos cambie. Aprobar para continuar.

- [x] **Paso 3: Modificar Template `registro_fruta_mlb.html` (Visualización y Botón)**
    -   **Agente:**
        1.  **Modificar la ruta `registro_fruta_mlb` en `app/blueprints/misc/routes.py`:**
            *   Al obtener los datos de cada registro (`lista_filtrada_final`), asegurarse de incluir el valor de `is_active` de la base de datos. El diccionario `registro_preparado` debería tener una clave `is_active` (ej: `registro_preparado['is_active'] = entrada_data.get('is_active', 1)`).
        2.  **En `templates/misc/registro_fruta_mlb.html`:**
            *   **Columna Estado:**
                *   Encontrar el `<td>` que muestra el estado (`<span class="badge ...">`).
                *   Envolver la lógica actual del badge con `{% if registro.is_active == 1 %}` ... `{% else %}` ... `{% endif %}`.
                *   En la sección `{% else %}` (cuando `is_active` es 0), mostrar: `<span class="badge bg-danger">Inactiva</span>`.
            *   **Columna Acciones:**
                *   Dentro del `<div class="btn-group ...">` donde están los otros botones.
                *   Añadir: `{% if current_user.is_authenticated and current_user.is_admin %}`.
                *   Dentro de este `if`, añadir otro `if`: `{% if registro.is_active == 1 %}`.
                *   Mostrar el botón "Inactivar": `<button type="button" class="btn btn-outline-warning btn-sm btn-toggle-active" data-codigo-guia="{{ registro.codigo_guia }}" title="Inactivar Guía"><i class="fas fa-lock"></i></button>`.
                *   *Opcional:* En un `{% else %}` del `if` interno, podrías añadir un botón "Activar": `<button type="button" class="btn btn-outline-success btn-sm btn-toggle-active" data-codigo-guia="{{ registro.codigo_guia }}" title="Activar Guía"><i class="fas fa-lock-open"></i></button>`.
                *   Cerrar los `{% endif %}`.
        3.  **Añadir JavaScript:**
            *   En el bloque `{% block extra_js %}`.
            *   Añadir un event listener para los botones con la clase `btn-toggle-active`.
            *   Al hacer clic:
                *   Obtener el `codigo_guia` del atributo `data-codigo-guia`.
                *   Hacer una petición `fetch` de tipo `POST` a la URL `/guias/<codigo_guia>/toggle_active`.
                *   Incluir headers necesarios (ej., para CSRF si lo usas).
                *   Al recibir la respuesta:
                    *   Si es exitosa (`response.ok` y `data.success`), actualizar el badge de estado y el icono/tooltip del botón en la fila correspondiente sin recargar la página.
                    *   Si hay error, mostrar un mensaje (ej., con `alert()` o una librería de notificaciones).
    -   **Usuario:**
        -   Verificar que la tabla cargue correctamente.
        -   Verificar que, si estás logueado como admin, aparezca el botón "Inactivar" (o "Activar") para las guías.
        -   Verificar que al hacer clic en el botón, el estado cambie visualmente y el botón se actualice.
        -   Verificar que el cambio persista al recargar la página.
        -   Verificar que si no estás logueado como admin, el botón no aparezca. Aprobar para continuar.

- [x] **Paso 4: Actualizar Filtros (Opción "Inactiva" y Lógica Backend)**
    -   **Agente:**
        1.  **En `templates/misc/registro_fruta_mlb.html`:**
            *   En el `<select>` con `id="estado"` para los filtros, añadir la opción: `<option value="Inactiva" {% if filtros.estado == 'Inactiva' %}selected{% endif %}>Inactiva</option>`.
        2.  **En la ruta `registro_fruta_mlb` en `app/blueprints/misc/routes.py`:**
            *   Modificar la lógica de filtrado por estado para manejar el filtro `estado_filtro == 'Inactiva'` (mostrando solo `is_active == 0`) y para que otros estados solo muestren guías con `is_active == 1`.
    -   **Usuario:**
        -   Verificar que la opción "Inactiva" aparezca en el dropdown de filtros.
        -   Seleccionar "Inactiva" y aplicar filtros. Verificar que solo se muestren las guías marcadas como inactivas.
        -   Seleccionar otros estados y verificar que solo se muestren las guías activas que coincidan con ese estado. Aprobar para finalizar la funcionalidad de inactivación básica.

- [ ] **Paso 5: Implementar Filtro de Estado Múltiple con Select2**
    -   **Agente:**
        1.  **Modificar `templates/misc/registro_fruta_mlb.html` (Frontend):**
            *   Añadir el atributo `multiple` al tag `<select>` del filtro de estado.
            *   Incluir los assets de Select2 (CSS y JS) en el template `base.html` o directamente en `registro_fruta_mlb.html` (preferiblemente desde un CDN).
            *   En el bloque `{% block extra_js %}` de `registro_fruta_mlb.html`, inicializar Select2 para el campo de selección de estado.
            *   Ajustar la lógica en el template para marcar las opciones como `selected` si `filtros.estado` (que ahora será una lista) contiene el valor de la opción: `{% if option_value in filtros.estado %}selected{% endif %}`.
        2.  **Modificar la ruta `registro_fruta_mlb` en `app/blueprints/misc/routes.py` (Backend):**
            *   Cambiar la forma de obtener el filtro de estado: de `request.args.get('estado', '')` a `lista_estados_filtro = request.args.getlist('estado')`.
            *   Actualizar `filtros_activos['estado']` para que almacene esta `lista_estados_filtro`.
            *   Adaptar la lógica de filtrado de `lista_consolidada_preparada` para que itere sobre `lista_estados_filtro` y aplique las condiciones correspondientes (si se selecciona "Inactiva", mostrar solo `is_active == 0`; para otros estados, mostrar solo `is_active == 1` Y que `r['estado']` esté en `otros_estados_seleccionados`). Considerar cómo manejar la combinación y evitar duplicados si es necesario.
    -   **Usuario:**
        -   Verificar que el dropdown de "Estado Proceso" ahora permita selección múltiple y tenga el estilo de Select2.
        -   Probar seleccionar múltiples estados (ej. "Cerrada" y "Pesaje Neto Completo") y verificar que se muestren las guías activas que cumplan cualquiera de esas condiciones.
        -   Probar seleccionar "Inactiva" junto con otros estados. El comportamiento esperado es que se muestren las inactivas Y las activas que coincidan con los otros estados seleccionados.
        -   Probar no seleccionar ningún estado (si Select2 lo permite) o seleccionar la opción "-- Todos --" (si se mantiene) para ver todas las guías.
        -   Verificar que los filtros seleccionados persistan correctamente al recargar la página. 