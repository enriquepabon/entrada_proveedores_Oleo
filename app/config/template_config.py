"""
Configuración centralizada de templates

Este archivo proporciona un mapeo centralizado entre funciones de controlador y sus templates correspondientes.
Este mapeo sirve como documentación oficial y puede usarse para validación.
"""

# Mapeo completo de templates organizados por blueprint y función
# Formato: 'blueprint.function_name': 'template_path.html'
TEMPLATE_MAPPING = {
    # Blueprint de Pesaje
    'pesaje.pesaje': 'pesaje/pesaje.html',
    'pesaje.pesaje_neto': 'pesaje/pesaje_neto.html',
    'pesaje.lista_pesajes': 'pesaje/pesajes_lista.html',
    'pesaje.lista_pesajes_neto': 'pesaje/pesajes_neto_lista.html',
    'pesaje.ver_resultados_pesaje': 'pesaje/resultados_pesaje.html',
    
    # Blueprint de Pesaje Neto
    'pesaje_neto.ver_resultados_pesaje_neto': 'resultados_pesaje_neto.html',
    
    # Blueprint de Clasificación
    'clasificacion.clasificacion': 'clasificacion/clasificacion.html',
    'clasificacion.ver_resultados_clasificacion': 'clasificacion/resultados_clasificacion.html',
    
    # Blueprint de Entrada
    'entrada.nueva_entrada': 'entrada/nueva_entrada.html',
    'entrada.lista_entradas': 'entrada/lista_entradas.html',
    
    # Blueprint de Salida
    'salida.registro_salida': 'salida/registro_salida.html',
    'salida.ver_resultados_salida': 'salida/resultados_salida.html',
    
    # Blueprint Misc
    'misc.upload_file': 'index.html',
    'misc.ver_guia': 'guia.html',
    'misc.ver_guia_centralizada': 'guia_centralizada.html',
}

def get_template_for_function(blueprint_name, function_name):
    """
    Obtener el nombre del template para una función de blueprint específica
    
    Args:
        blueprint_name (str): Nombre del blueprint
        function_name (str): Nombre de la función
        
    Returns:
        str|None: Ruta del template o None si no se encuentra
    """
    key = f"{blueprint_name}.{function_name}"
    return TEMPLATE_MAPPING.get(key)

def validate_template(blueprint_name, function_name, template_path):
    """
    Validar si el template usado coincide con el definido en la configuración
    
    Args:
        blueprint_name (str): Nombre del blueprint
        function_name (str): Nombre de la función
        template_path (str): Ruta del template a validar
        
    Returns:
        bool: True si coincide, False si no
    """
    expected_template = get_template_for_function(blueprint_name, function_name)
    if not expected_template:
        return False
    return expected_template == template_path 