# Uso de la Estructura de Templates

## Introducción

Este documento proporciona instrucciones detalladas sobre cómo utilizar las nuevas herramientas para mantener y documentar la estructura de templates en TiquetesApp.

## Herramientas Disponibles

Se han implementado tres herramientas principales:

1. **Documentación de Estructura**: Archivo `template_structure.md` en la raíz del proyecto
2. **Configuración Centralizada**: Archivo `app/config/template_config.py`
3. **Decoradores de Template**: Archivo `app/utils/decorators.py`

## Cómo Documentar Nuevos Templates

Cuando crees un nuevo controlador o vista que renderice un template, debes:

1. Añadir el mapeo al archivo `app/config/template_config.py`
2. Usar el decorador `@uses_template` para documentar la función
3. Actualizar el archivo `template_structure.md` si es necesario

### Ejemplo de Código

```python
# En un archivo de rutas (app/blueprints/mi_modulo/routes.py)
from flask import Blueprint, render_template
from app.utils.decorators import uses_template

bp = Blueprint('mi_modulo', __name__)

@bp.route('/mi-vista')
@uses_template('mi_modulo/mi_vista.html')  # Documenta el template usado
def mi_vista():
    # Template en: app/templates/mi_modulo/mi_vista.html
    return render_template('mi_modulo/mi_vista.html', datos={'clave': 'valor'})
```

Luego, añade la entrada en `app/config/template_config.py`:

```python
TEMPLATE_MAPPING = {
    # Entradas existentes...
    
    # Nuevo mapeo
    'mi_modulo.mi_vista': 'mi_modulo/mi_vista.html',
}
```

## Validación de Templates

Para validar si los templates usados coinciden con los documentados puedes usar:

```python
from app.config.template_config import validate_template

# Verifica si el template usado coincide con el configurado
is_valid = validate_template('mi_modulo', 'mi_vista', 'mi_modulo/mi_vista.html')
```

También puedes usar el decorador avanzado:

```python
from app.utils.decorators import uses_template, validate_rendered_template

@bp.route('/mi-vista')
@uses_template('mi_modulo/mi_vista.html')
@validate_rendered_template  # Valida automáticamente
def mi_vista():
    return render_template('mi_modulo/mi_vista.html')
```

## Estadísticas de Uso de Templates

Para obtener estadísticas de uso de templates en toda la aplicación:

```python
from app.utils.decorators import get_template_usage_stats

# Dentro del contexto de aplicación Flask
with app.app_context():
    stats = get_template_usage_stats()
    print(f"Total de templates documentados: {stats['template_count']}")
    print(f"Funciones con templates documentados: {stats['documented_functions']}")
```

## Ejemplos para el Caso Específico de Pesaje Neto

### Decorar la función existente (sin modificar comportamiento)

```python
# En app/blueprints/pesaje_neto/routes.py (solo para referencia, no modificar el archivo)

# Importar el decorador
from app.utils.decorators import uses_template

@bp.route('/ver_resultados_pesaje_neto/<codigo_guia>')
@uses_template('resultados_pesaje_neto.html')
def ver_resultados_pesaje_neto(codigo_guia):
    # Template en: templates/resultados_pesaje_neto.html
    return render_template('resultados_pesaje_neto.html', **context)
```

## Buenas Prácticas

1. **Comentarios**: Añadir siempre un comentario indicando la ubicación exacta del template
2. **Consistencia**: Mantener consistencia entre decoradores, configuración y comentarios
3. **Documentación**: Actualizar la documentación cuando se añadan nuevos templates
4. **Validación**: Usar los decoradores de validación para detectar inconsistencias
5. **Mantenimiento**: Mantener limpia la estructura y documentación de templates 