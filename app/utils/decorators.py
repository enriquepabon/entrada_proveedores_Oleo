"""
Decoradores de utilidad para Flask

Este módulo contiene decoradores que ayudan a documentar y validar
el uso de templates en los controladores.
"""

import functools
import inspect
import logging
from flask import current_app, render_template as flask_render_template

logger = logging.getLogger(__name__)

def uses_template(template_path):
    """
    Decorador que documenta qué template es utilizado por una función.
    
    Este decorador no modifica el comportamiento de la función, solo
    añade metadatos para documentación y posible validación.
    
    Args:
        template_path (str): Ruta del template utilizado por la función
        
    Returns:
        function: La función decorada con metadatos de template
        
    Ejemplo:
        @bp.route('/mi-ruta')
        @uses_template('mi_template.html')
        def mi_funcion():
            return render_template('mi_template.html')
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Añadir el template como atributo a la función
            wrapper.template_path = template_path
            
            # No modificar el comportamiento original
            return func(*args, **kwargs)
        
        # Guardar el template como atributo de la función y del wrapper
        wrapper.template_path = template_path
        func.template_path = template_path
        
        return wrapper
    return decorator

def validate_rendered_template(func_or_method):
    """
    Decorador que valida si el template renderizado coincide con el documentado.
    
    Este decorador debe aplicarse a funciones que utilicen render_template.
    Compara el template realmente utilizado con el documentado y registra
    inconsistencias en los logs.
    
    Args:
        func_or_method: La función o método a decorar
        
    Returns:
        function: La función decorada que valida el template
        
    Ejemplo:
        @bp.route('/mi-ruta')
        @uses_template('mi_template.html')
        @validate_rendered_template
        def mi_funcion():
            return render_template('mi_template.html')
    """
    @functools.wraps(func_or_method)
    def wrapper(*args, **kwargs):
        # Guardar la implementación original de render_template
        original_render_template = flask_render_template
        
        # Obtener el template documentado (si existe)
        documented_template = getattr(func_or_method, 'template_path', None)
        
        # Templates realmente utilizados
        used_templates = []
        
        # Reemplazar render_template para capturar el template usado
        def capturing_render_template(template_name_or_list, **context):
            # Registrar el nombre del template o templates
            if isinstance(template_name_or_list, str):
                used_templates.append(template_name_or_list)
            else:
                used_templates.extend(template_name_or_list)
                
            # Llamar a la función original
            return original_render_template(template_name_or_list, **context)
        
        # Reemplazar temporalmente
        import flask
        flask.render_template = capturing_render_template
        
        try:
            # Ejecutar la función
            result = func_or_method(*args, **kwargs)
            
            # Validar si hay inconsistencias
            if documented_template and used_templates and documented_template != used_templates[0]:
                logger.warning(
                    f"Inconsistencia en templates para {func_or_method.__name__}: "
                    f"Documentado '{documented_template}', usado '{used_templates[0]}'"
                )
                
            return result
        finally:
            # Restaurar la función original
            flask.render_template = original_render_template
    
    return wrapper

def get_template_usage_stats():
    """
    Genera estadísticas sobre el uso de templates en la aplicación.
    
    Esta función debe llamarse después de que todas las rutas estén registradas.
    Analiza todas las funciones que tienen metadatos de templates y genera un informe.
    
    Returns:
        dict: Estadísticas de uso de templates
    """
    if not current_app:
        logger.error("Esta función debe llamarse dentro del contexto de aplicación Flask")
        return {}
    
    stats = {
        'template_count': 0,
        'documented_functions': 0,
        'templates_by_blueprint': {},
        'most_used_templates': {}
    }
    
    # Recorrer todos los blueprints y sus vistas
    for blueprint_name, blueprint in current_app.blueprints.items():
        stats['templates_by_blueprint'][blueprint_name] = []
        
        for rule in current_app.url_map.iter_rules():
            if rule.endpoint.startswith(f"{blueprint_name}."):
                view_func = current_app.view_functions[rule.endpoint]
                template_path = getattr(view_func, 'template_path', None)
                
                if template_path:
                    stats['documented_functions'] += 1
                    stats['templates_by_blueprint'][blueprint_name].append(template_path)
                    
                    # Contabilizar uso de templates
                    if template_path in stats['most_used_templates']:
                        stats['most_used_templates'][template_path] += 1
                    else:
                        stats['most_used_templates'][template_path] = 1
                        stats['template_count'] += 1
    
    return stats 