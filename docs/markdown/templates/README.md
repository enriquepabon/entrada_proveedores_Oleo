# Componentes y Layouts del Sistema de Gestión de Tiquetes MLB

Este directorio contiene los templates y componentes utilizados en la aplicación de gestión de tiquetes, organizados siguiendo una arquitectura modular para maximizar la reutilización y mantener la consistencia visual.

## Estructura de Directorios

```
templates/
├── base.html                     # Template base con estructura común
├── components/                   # Componentes reutilizables
│   ├── forms/                    # Macros para formularios
│   ├── tables/                   # Macros para tablas
│   ├── cards/                    # Macros para tarjetas y elementos visuales
│   ├── pesaje_datos.html         # Componentes específicos para pesaje
│   ├── pesaje_styles.html        # Estilos para templates de pesaje
│   ├── clasificacion_datos.html  # Componentes específicos para clasificación
│   └── clasificacion_styles.html # Estilos para templates de clasificación
├── layouts/                      # Layouts específicos que extienden base.html
│   ├── documento_layout.html     # Layout para documentos (PDF/impresión)
│   ├── form_layout.html          # Layout para formularios
│   ├── list_layout.html          # Layout para listas y tablas
│   └── results_layout.html       # Layout para pantallas de resultados
├── entrada/                      # Templates para registro de entrada
│   ├── entrada_form.html         # Formulario de registro de nueva entrada
│   ├── entradas_lista.html       # Lista de entradas registradas
│   └── entrada_resultados.html   # Resultados de procesamiento OCR
├── pesaje/                       # Templates para pesajes (bruto y neto)
├── clasificacion/                # Templates para clasificación 
├── salida/                       # Templates para registro de salida
└── README.md                     # Esta documentación
```

## Layouts Disponibles

### 1. `layouts/documento_layout.html`

Layout para documentos (PDF e impresión) que proporciona una estructura común para los comprobantes.

**Uso:**
```html
{% extends "layouts/documento_layout.html" %}

{% block title %}Título del documento{% endblock %}
{% block header_title %}Encabezado Principal{% endblock %}
{% block header_subtitle %}Subtítulo{% endblock %}

{% block content %}
<!-- Contenido del documento -->
{% endblock %}
```

**Parámetros importantes:**
- `for_print`: Booleano que indica si es para vista de impresión (muestra botones de impresión)
- `for_pdf`: Booleano que indica si es para generación de PDF (URLs absolutas)
- `volver_url`: URL para el botón de volver en la vista de impresión
- `fecha_generacion` y `hora_generacion`: Para mostrar en el pie de página

### 2. `layouts/list_layout.html`

Layout para pantallas de listas con filtros y tablas de datos.

**Uso:**
```html
{% extends "layouts/list_layout.html" %}
{% import "components/tables/tabla_datos.html" as tablas %}

{% block lista_titulo %}Título de la Lista{% endblock %}
{% block lista_descripcion %}Descripción de la lista{% endblock %}

{% block filtros %}
<!-- Definir filtros con tablas.filtros_form() -->
{% endblock %}

{% block lista %}
<!-- Definir columnas y tabla con tablas.tabla_filtrable() -->
{% endblock %}
```

**Parámetros importantes:**
- `volver_url`: URL para el botón de volver
- `volver_texto`: Texto para el botón de volver

### 3. `layouts/form_layout.html`

Layout para pantallas de formularios.

**Uso:**
```html
{% extends "layouts/form_layout.html" %}
{% import "components/forms/form_elements.html" as forms %}

{% block form_titulo %}Título del Formulario{% endblock %}
{% block form_descripcion %}Descripción del formulario{% endblock %}

{% block form_body %}
<!-- Elementos del formulario usando forms.input_text(), etc. -->
{% endblock %}

{% block form_buttons %}
<!-- Botones personalizados o usar los por defecto -->
{% endblock %}
```

**Parámetros importantes:**
- `volver_url`: URL para el botón de cancelar/volver
- `volver_texto`: Texto para el enlace de volver
- `method`: Método HTTP del formulario (default: POST)
- `action`: URL de acción del formulario
- `enctype`: Tipo de codificación del formulario (necesario para subida de archivos)

### 4. `layouts/results_layout.html`

Layout para pantallas de resultados con estadísticas y acciones.

**Uso:**
```html
{% extends "layouts/results_layout.html" %}
{% import "components/cards/stat_cards.html" as cards %}

{% block results_titulo %}Título de Resultados{% endblock %}
{% block results_descripcion %}Descripción de los resultados{% endblock %}

{% block header_actions %}
<!-- Acciones en el encabezado (botones) -->
{% endblock %}

{% block results_stats %}
<!-- Tarjetas de estadísticas usando cards.simple_stat_card() -->
{% endblock %}

{% block results_content %}
<!-- Contenido principal de los resultados -->
{% endblock %}

{% block action_buttons %}
<!-- Botones de acción en el pie de página -->
{% endblock %}
```

## Componentes Reutilizables

### 1. Componentes de Formularios (`components/forms/form_elements.html`)

Macros para elementos de formulario:

- `input_text(id, etiqueta, valor, placeholder, required, readonly, clase, help_text)`
- `input_number(id, etiqueta, valor, min, max, step, required, readonly, clase, help_text)`
- `input_date(id, etiqueta, valor, min, max, required, readonly, clase, help_text)`
- `select(id, etiqueta, opciones, valor_seleccionado, required, readonly, clase, help_text, empty_option, empty_text)`
- `textarea(id, etiqueta, valor, rows, required, readonly, clase, help_text)`
- `checkbox(id, etiqueta, checked, value, readonly, clase, help_text)`
- `file_input(id, etiqueta, accept, multiple, required, clase, help_text)`
- `submit_button(texto, clase, extra_clase, icon)`
- `cancel_button(texto, url, clase, extra_clase, icon)`
- `button_group(buttons)`

**Ejemplo:**
```html
{% import "components/forms/form_elements.html" as forms %}

{{ forms.input_text(
    id="nombre",
    etiqueta="Nombre",
    valor=usuario.nombre,
    required=true,
    placeholder="Ingrese su nombre"
) }}

{{ forms.submit_button(
    texto="Guardar Usuario",
    icon="save"
) }}
```

### 2. Componentes de Tablas (`components/tables/tabla_datos.html`)

Macros para tablas y filtros:

- `tabla_filtrable(titulo, columnas, datos, url_filtros, filtros_actuales, sin_resultados_mensaje)`
- `filtros_form(filtros, url_form, limpiar_url, titulo)`
- `acciones_botones(acciones)`

**Ejemplo:**
```html
{% import "components/tables/tabla_datos.html" as tablas %}

{% set columnas = [
    {'titulo': 'ID', 'campo': 'id'},
    {'titulo': 'Nombre', 'campo': 'nombre'},
    {'titulo': 'Estado', 'render': lambda item: '<span class="badge bg-success">Activo</span>' if item.activo else '<span class="badge bg-danger">Inactivo</span>'},
    {'titulo': 'Acciones', 'render': lambda item: tablas.acciones_botones([
        {'url': url_for('ver', id=item.id), 'texto': 'Ver', 'tipo': 'primary', 'icono': 'eye'},
        {'url': url_for('editar', id=item.id), 'texto': 'Editar', 'tipo': 'warning', 'icono': 'edit'}
    ])}
] %}

{{ tablas.tabla_filtrable(
    'Resultados',
    columnas,
    datos,
    url_for('lista')
) }}
```

### 3. Componentes de Tarjetas (`components/cards/stat_cards.html`)

Macros para tarjetas de estadísticas y datos:

- `simple_stat_card(titulo, valor, icono, color, footer_texto, footer_link)`
- `progress_stat_card(titulo, valor, maximo, porcentaje, icono, color, footer_texto, footer_link)`
- `detail_stat_card(titulo, valor_principal, subtitulo, valor_secundario, porcentaje, icono, color, tendencia)`
- `image_card(imagen_url, titulo, descripcion, footer, link, clase_extra)`

**Ejemplo:**
```html
{% import "components/cards/stat_cards.html" as cards %}

<div class="row">
    <div class="col-md-3">
        {{ cards.simple_stat_card(
            "Total Usuarios",
            total_usuarios|string,
            "users",
            "primary",
            "Actualizado hoy"
        ) }}
    </div>
    <div class="col-md-3">
        {{ cards.progress_stat_card(
            "Progreso",
            completados|string,
            total|string,
            porcentaje,
            "tasks",
            "success"
        ) }}
    </div>
</div>
```

### 4. Componentes Específicos de Pesaje

- `pesaje_datos.html`: Macros para mostrar datos de proveedor, pesaje, etc.
- `pesaje_styles.html`: Estilos específicos para documentos de pesaje

### 5. Componentes Específicos de Clasificación

- `clasificacion_datos.html`: Macros para mostrar datos de clasificación manual/automática
- `clasificacion_styles.html`: Estilos específicos para documentos de clasificación

### 6. Componentes Específicos de Entrada

- `entrada_datos.html`: Macros para mostrar datos de guías, procesamiento OCR, y estados
  - `datos_guia(codigo_guia, fecha_registro, hora_registro, estado)`: Muestra información general de la guía
  - `imagen_tiquete(imagen_url, for_pdf)`: Muestra la imagen del tiquete
  - `datos_extraccion(datos_extraidos)`: Muestra los datos extraídos del OCR
  - `estado_procesamiento(estado, mensaje, progreso)`: Muestra el estado del procesamiento (éxito, error, en proceso)

- `entrada_styles.html`: Estilos específicos para componentes de entrada
  - Estilo para la visualización de imágenes de tiquetes
  - Estilo para los estados de procesamiento (success, error, processing)
  - Estilo para el componente de carga de archivos (drag & drop)

## Guía de Uso Rápido

### Crear un Nuevo Template de Lista

1. Extiende `layouts/list_layout.html`
2. Importa `components/tables/tabla_datos.html`
3. Define filtros y columnas
4. Usa los macros `filtros_form()` y `tabla_filtrable()`

### Crear un Nuevo Template de Formulario

1. Extiende `layouts/form_layout.html`
2. Importa `components/forms/form_elements.html`
3. Define el contenido del formulario en `form_body`
4. Personaliza los botones si es necesario en `form_buttons`

### Crear un Nuevo Template de Documento (PDF/Impresión)

1. Extiende `layouts/documento_layout.html`
2. Importa los componentes específicos que necesites
3. Define los bloques `title`, `header_title`, `header_subtitle` y `content`
4. Asegúrate de pasar los parámetros correctos (`for_pdf`, `for_print`, etc.)

### Crear un Nuevo Template de Resultados

1. Extiende `layouts/results_layout.html`
2. Importa `components/cards/stat_cards.html` y otros componentes necesarios
3. Define los bloques `results_stats`, `results_content` y `action_buttons`

## Mejores Prácticas

1. **Reutiliza componentes**: Siempre busca usar los componentes existentes antes de crear estilos o estructuras nuevas.
2. **Mantén la consistencia**: Usa los layouts y componentes como se documentan para mantener una experiencia de usuario coherente.
3. **Responsabilidad única**: Cada componente debe tener una sola responsabilidad y hacer una cosa bien.
4. **Parametriza adecuadamente**: Usa parámetros para personalizar componentes en lugar de duplicar código.
5. **Respeta la jerarquía**: Mantén la estructura de directorios organizada según la funcionalidad.

## Contribuciones

Al añadir nuevos componentes:
1. Documenta sus parámetros y uso
2. Actualiza este README
3. Mantén la estructura de directorios

## Ejemplos Completos

Para ver ejemplos completos de implementación, revisa:
- `pesaje/pesaje_documento.html`: Documento de pesaje
- `pesaje/pesajes_lista.html`: Lista de pesajes
- `clasificacion/clasificacion_form.html`: Formulario de clasificación
- `clasificacion/clasificacion_resultados.html`: Resultados de clasificación
- `entrada/entrada_form.html`: Formulario de registro de entrada
- `entrada/entrada_resultados.html`: Resultados de procesamiento OCR 