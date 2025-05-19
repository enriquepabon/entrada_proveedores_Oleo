# Plan de Desarrollo: Módulo de Graneles

## Objetivo General
Desarrollar e integrar un nuevo módulo de "Registro de Graneles" en la aplicación existente. Este módulo permitirá el registro de entrada de vehículos de transporte de graneles mediante la captura o digitación de la placa, la consulta de información de autorización desde un archivo de Google Sheets y el guardado de los datos validados o ingresados manualmente en una base de datos específica.

## Proceso de Desarrollo
1.  El agente (IA) generará el código o las modificaciones necesarias para cada paso del plan.
2.  El usuario (tú) probará la implementación del paso actual.
3.  El usuario proporcionará retroalimentación detallada al agente.
4.  Si el paso es aprobado por el usuario, el agente lo marcará como completado (ej., tachándolo: ~~Paso X~~) y procederá con el siguiente.
5.  Si se identifican problemas o se requieren cambios, el agente realizará las correcciones necesarias y se repetirá el proceso de prueba y retroalimentación para ese paso hasta su aprobación.

## Pasos para el Desarrollo del Módulo de Graneles

*   **~~Paso 0: Configuración Inicial y Preguntas (Este paso)~~**
    *   ~~Crear este archivo `PLAN_GRANELES.md`.~~
    *   ~~Formular y resolver preguntas aclaratorias con el usuario para asegurar todos los requerimientos.~~
        *   ~~**Google Sheets:**~~
            *   ~~Nombre del Archivo: `Registro Vehiculos Granel`~~
            *   ~~Nombre de la Hoja: `Graneles`~~
            *   ~~URL: [https://docs.google.com/spreadsheets/d/14uoRvBmmgQ3F_bM9mhToMpHUG9oMYEtcwbG6ejCgUfA/edit?gid=0#gid=0](https://docs.google.com/spreadsheets/d/14uoRvBmmgQ3F_bM9mhToMpHUG9oMYEtcwbG6ejCgUfA/edit?gid=0#gid=0)~~
            *   ~~Columnas: "Producto", "Fecha", "Placa", "Trailer", "Cédula del Conductor", "Nombre del Conductor", "Origen", "Destino".~~
            *   ~~Columna Clave para Búsqueda: "Placa".~~
            *   ~~Acceso: Se configurará el acceso (requiere acción en Paso 3).~~
            *   ~~Formato de Fecha: `dd/mm/aaaa`.~~
        *   ~~**Base de Datos:**~~
            *   ~~Tipo: SQLite.~~
            *   ~~Archivo Existente: `tiquetes.db`.~~
            *   ~~Nombre de la Nueva Tabla: `RegistroEntradaGraneles`.~~
            *   ~~Campos Adicionales: `timestamp_registro` (DATETIME, default now), `tipo_registro` (VARCHAR, ej: 'gsheet', 'manual'), `observaciones` (TEXT).~~
        *   ~~**Reconocimiento de Placa (OCR):**~~
            *   ~~Se utilizará webhook existente: `https://hook.us2.make.com/a2yotw5cls6qxom2iacvyaoh2b9uk9ip`. La aplicación enviará la imagen a este webhook.~~
        *   ~~**Interfaz y Estructura del Proyecto:**~~
            *   ~~Botón de fruta rebautizado: "Registro de Fruta".~~
            *   ~~Nuevo botón para graneles: "Registro de Graneles".~~
            *   ~~Estructura de Archivos: `app/graneles/` para rutas/modelos. Templates en `app/templates/graneles/`.~~
    *   Definir la estructura de archivos y nombres para el nuevo módulo.

*   **~~Paso 1: Actualización de la Interfaz Principal (`templates/home.html`)~~**
    *   ~~Identificar el archivo `home.html` (o el template principal equivalente) donde se encuentra la sección "iniciar proceso".~~
    *   ~~Rebautizar el botón existente para el módulo de fruta a "Registro de Fruta".~~
    *   ~~Añadir un nuevo botón (ej. "Registro de Graneles") al lado del de "Registro de Fruta".~~
    *   ~~Este nuevo botón deberá redirigir a la nueva ruta para el registro de entrada de graneles (temporalmente `#`).~~

*   **Paso 2: Creación de Rutas y Template Base para el Registro de Entrada de Graneles**
    *   Crear los archivos necesarios para las rutas del módulo de graneles (`app/blueprints/graneles/__init__.py` y `app/blueprints/graneles/routes.py`, registrando un nuevo Blueprint llamado `graneles`).
    *   Definir la ruta principal para el registro de entrada de graneles (`/graneles/registro_entrada`).
    *   Crear un nuevo archivo HTML (`app/templates/graneles/registro_entrada_graneles.html`) con el diseño básico del formulario.
    *   Registrar el `graneles_bp` en `app/__init__.py`.
    *   Actualizar el `href` del botón "Registro de Graneles" en `templates/home.html` a `url_for('graneles.registro_entrada')`.

*   **~~Paso 3: Lógica de Backend para Consulta en Google Sheets~~**
    *   ~~Configurar el acceso a la API de Google Sheets (archivo de credenciales `google_sheets_credentials_09052025.json` en la raíz y permisos en el Sheet).~~
    *   ~~Crear `app/utils/google_sheets_api.py` con funciones para autenticar, obtener todos los registros y `find_granel_record_by_placa`.~~
    *   ~~Probar la conexión y lectura de datos directamente desde el script (opcional).~~
    *   ~~Crear ruta en Flask (`/graneles/buscar_placa_granel`) en `app/blueprints/graneles/routes.py` que utiliza `find_granel_record_by_placa` y devuelve JSON.~~

*   **~~Paso 4: Interacción Frontend - Backend para Búsqueda de Placa~~**
    *   ~~Implementar lógica JavaScript en `app/templates/graneles/registro_entrada_graneles.html` para:~~
        *   ~~Al hacer clic en "Buscar/Validar Placa", enviar la placa al backend (`/graneles/buscar_placa_granel`) vía `fetch` POST.~~
        *   ~~Recibir la respuesta JSON.~~
        *   ~~Si la placa se encuentra (`success: true`), poblar los campos del formulario con los datos y permitir edición.~~
        *   ~~Si la placa no se encuentra (`success: false`), habilitar campos para ingreso manual y anotar "Registro manual".~~
        *   ~~Mostrar mensajes al usuario (éxito, error, placa no encontrada).~~
        *   ~~Habilitar el botón "Registrar Entrada" si se cargan datos o se procede con registro manual.~~
        *   ~~Implementar botón "Limpiar / Nueva Búsqueda".~~

*   **~~Paso 5: Definición del Modelo de Base de Datos y Creación de Tabla~~**
    *   ~~Definir el modelo para la tabla `RegistroEntradaGraneles` en `tiquetes.db` (SQLAlchemy)~~ -> Corregido a SQL directo en `db_schema.py`.
    *   ~~Campos mínimos: `id` (PK), `producto` (TEXT), `fecha_autorizacion` (TEXT), `placa` (TEXT), `trailer` (TEXT), `cedula_conductor` (TEXT), `nombre_conductor` (TEXT), `origen` (TEXT), `destino` (TEXT).~~
    *   ~~Campos adicionales confirmados: `timestamp_registro` (TIMESTAMP, default current_timestamp), `tipo_registro` (TEXT), `observaciones` (TEXT).~~
    *   ~~Añadir `CREATE_REGISTRO_ENTRADA_GRANELES_TABLE` a `db_schema.py` y ejecutarla en `create_tables()`.~~
    *   ~~Verificar la creación de la tabla en `tiquetes.db`.~~

*   **~~Paso 6: Lógica de Backend para Guardar el Registro de Entrada~~**
    *   ~~Crear la ruta y función en el backend (`@graneles_bp.route('/guardar_registro_granel', methods=['POST'])`) en `app/blueprints/graneles/routes.py` para recibir los datos del formulario.~~
    *   ~~Procesar los datos recibidos (extraer de `request.form`).~~
    *   ~~Insertar los datos en la tabla `RegistroEntradaGraneles` de `tiquetes.db`.~~
    *   ~~Devolver una respuesta JSON al frontend indicando éxito o error.~~
    *   ~~Actualizar el JavaScript en `registro_entrada_graneles.html` para que el botón "Registrar Entrada" envíe los datos a la nueva ruta y maneje la respuesta (mostrar mensaje, limpiar formulario).~~

*   **~~Paso 7: Implementación de Captura de Foto de Placa y Envío a Webhook~~**

*   **~~Paso 8: Pruebas Exhaustivas y Refinamiento (Fase 1)~~**
    *   ~~Probar todo el flujo del módulo:~~
        *   ~~Búsqueda de placa existente en Google Sheets.~~
        *   ~~Búsqueda de placa NO existente en Google Sheets y registro manual.~~
        *   ~~Validaciones de campos.~~
        *   ~~Correcto guardado en la base de datos.~~
    *   ~~Realizar ajustes de UI/UX según sea necesario.~~
    *   ~~Corregir cualquier error encontrado.~~

*   **~~Paso 9: Planificación de Nuevas Funcionalidades (Detalle, QR, PDF)~~**
    *   ~~Definir con el usuario los requerimientos para la visualización detallada de registros de graneles, generación de QR y PDF, similar al módulo de fruta.~~
    *   ~~Aclarar preferencias de diseño (colores: marrones/azules para graneles), datos a mostrar (todos, incluyendo usuario_registro), acceso QR (internet, con login), acciones (imprimir, PDF, volver, editar), ubicación de archivos (subcarpetas para graneles), formato de fecha (local Bogotá para timestamp_registro).~~

*   **Paso 10: Actualización de BD y Creación del Template de Detalle de Registro de Graneles**
    *   Modificar `db_schema.py`: Añadir campo `usuario_registro TEXT` a la tabla `RegistroEntradaGraneles`.
    *   Actualizar `app/blueprints/graneles/routes.py`: En la función de guardar registro, obtener `current_user.username` (o `current_user.id`) y guardarlo en el nuevo campo `usuario_registro`.
    *   Crear un nuevo template HTML (ej: `app/templates/graneles/detalle_registro_granel.html`) que muestre:
        *   Todos los datos registrados del vehículo de graneles (producto, fecha_autorizacion, placa, trailer, cedula_conductor, nombre_conductor, origen, destino, observaciones, timestamp_registro, tipo_registro, usuario_registro).
        *   La hora y fecha de `timestamp_registro` en formato local (Bogotá), sin el texto "formato Bogotá" en el título del campo.
        *   Un diseño visual diferenciado del módulo de fruta (ej. usando tonos marrones o azules).
        *   Incluir botones para acciones como: Imprimir, Descargar PDF, Volver a la lista, Editar (estos últimos inicialmente pueden ser placeholders).

*   **Paso 11: Generación de Código QR y URL de la Guía de Graneles**
    *   Implementar la lógica para generar un código QR único para cada registro de graneles.
    *   El QR debe apuntar a una URL única donde se pueda consultar el detalle del registro (ej: `/graneles/guia/<id_registro_granel>`), accesible desde internet (producción) y que requiera login.
    *   Guardar el archivo QR en la carpeta `static/qr/graneles/`.
    *   Mostrar el QR en el template `detalle_registro_granel.html` y permitir su descarga o impresión.

*   **Paso 12: Ruta y Lógica Backend para la Vista de la Guía de Graneles** (COMPLETADO)
    *   Crear una nueva ruta Flask (ej: `@graneles_bp.route('/guia/<int:id_registro_granel>')`) en `app/blueprints/graneles/routes.py` que:
        *   Requiera login (`@login_required`). (HECHO)
        *   Reciba el ID del registro de granel. (HECHO)
        *   Obtenga los datos del registro correspondiente desde la tabla `RegistroEntradaGraneles`. (HECHO)
        *   Renderice el template `detalle_registro_granel.html` con los datos recuperados y la información del QR. (HECHO)

*   **Paso 13: Generación de PDF del Registro de Graneles** (HECHO, con template PDF simplificado)
    *   Implementar la función para generar un PDF del registro de granel, utilizando un diseño similar al del template HTML de detalle. (HECHO)
    *   Guardar los PDFs generados en la carpeta `static/pdfs/graneles/`. (HECHO)
    *   Asegurar que el botón "Descargar PDF" en la vista de detalle sea funcional y permita la descarga del archivo. (HECHO)

*   **Paso 14: Pruebas Finales, Validaciones y Ajustes de UI/UX**
    *   Probar el flujo completo: registro de entrada de granel, visualización del detalle, generación y funcionamiento del QR, generación y descarga del PDF.
    *   Verificar que el acceso a la guía de granel (vía URL directa o QR) requiera autenticación.
    *   Validar que las URLs generadas para el QR funcionen correctamente en un entorno de producción simulado (accesibles desde internet).
    *   Realizar ajustes finales de UI/UX en el template de detalle para asegurar claridad, consistencia y una buena experiencia de usuario, diferenciándolo del módulo de fruta.
    *   Confirmar que todas las acciones (Imprimir, Editar -si se implementa-, Volver) funcionen como se espera.

*   **Paso 15: Implementación de la Vista de Guía Centralizada de Graneles**
    *   Crear el template HTML `app/templates/graneles/guia_centralizada_graneles.html` basado en la guía de fruta pero adaptado al flujo de 5 pasos de graneles (Registro, Pesaje Vacío, Control Calidad, Pesaje Lleno, Salida).
    *   Añadir la ruta `@graneles_bp.route('/guia-centralizada/<int:id_registro_granel>')` en `app/blueprints/graneles/routes.py`.
    *   Implementar la función `vista_guia_centralizada_granel` que:
        *   Obtenga el registro de entrada de granel por su ID.
        *   Formatee el timestamp de registro.
        *   Genere las URLs para el código QR (apuntando a la guía centralizada).
        *   Renderice `guia_centralizada_graneles.html` con los datos, mostrando el primer paso como completado y los demás como pendientes.
    *   Añadir un enlace a esta nueva vista desde `detalle_registro_granel.html` y, opcionalmente, desde una nueva lista de registros de graneles.
    *   Asegurar que el QR se muestre correctamente en la guía centralizada y que la URL del QR apunte a la guía centralizada.
    *   Verificar que la fecha y hora del registro de entrada se muestren correctamente en la guía centralizada.

*   **Paso 16: Definición de Esquemas de BD y Lógica para Etapas del Proceso de Graneles**
    *   **Sub-paso 16.1: Primer Pesaje Granel**
        *   Definir y crear la tabla `PrimerPesajeGranel` en `db_schema.py` (campos: `id`, `id_registro_granel` (FK), `peso_primer_kg`, `timestamp_primer_pesaje`, `usuario_pesaje`, `foto_soporte_path`).
        *   Crear la interfaz y la lógica de backend para registrar el primer pesaje, asociándolo al `id_registro_granel`.
        *   Actualizar `vista_guia_centralizada_granel` para mostrar esta información.
    *   **Sub-paso 16.2: Control de Calidad del Producto Granel**
        *   Definir y crear la tabla `ControlCalidadGranel` en `db_schema.py` (campos: `id`, `id_registro_granel` (FK), `parametros_calidad` (JSON/TEXT), `resultado_calidad` (TEXT), `observaciones_calidad`, `timestamp_calidad`, `usuario_calidad`).
        *   Crear la interfaz y la lógica para registrar el control de calidad.
        *   Actualizar `vista_guia_centralizada_granel`.
    *   **Sub-paso 16.3: Segundo Pesaje Granel**
        *   Definir y crear la tabla `SegundoPesajeGranel` en `db_schema.py` (campos: `id`, `id_registro_granel` (FK), `peso_segundo_kg`, `peso_neto_granel_kg`, `timestamp_segundo_pesaje`, `usuario_pesaje`, `foto_soporte_path`).
        *   Crear la interfaz y la lógica para registrar el segundo pesaje y calcular el neto.
        *   Actualizar `vista_guia_centralizada_granel`.
    *   **Sub-paso 16.4: Salida del Vehículo de Granel**
        *   Definir y crear la tabla `SalidasGranel` en `db_schema.py` (campos: `id`, `id_registro_granel` (FK), `timestamp_salida`, `usuario_salida`, `observaciones_salida`).
        *   Crear la interfaz y la lógica para registrar la salida.
        *   Actualizar `vista_guia_centralizada_granel` y marcar la guía como completada.

*   **Paso 17: Integración y Pruebas del Flujo Completo de Graneles**
    *   Probar todo el flujo desde el registro inicial hasta la salida del vehículo.
    *   Verificar que la `guia_centralizada_graneles.html` refleje correctamente el progreso.
    *   Realizar validaciones y ajustes de UI/UX necesarios.

*   **Paso 18: Documentación y Entrega Final del Módulo de Graneles**
    *   Asegurar que el código esté comentado donde sea necesario.
    *   Actualizar cualquier documentación relevante del proyecto. 