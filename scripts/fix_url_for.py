#!/usr/bin/env python3
"""
Script para actualizar todas las referencias a url_for en las plantillas
para adaptarlas a la nueva estructura de blueprints.
"""

import os
import re
import glob

# Mapeo de funciones a blueprints
FUNCTION_TO_BLUEPRINT = {
    # Blueprint de entrada
    'upload_file': 'entrada',
    'processing': 'entrada',
    'review': 'entrada',
    'index': 'entrada',
    'home': 'entrada',
    'register': 'entrada',
    'update_data': 'entrada',
    'review_pdf': 'entrada',
    'revalidation_results': 'entrada',
    'revalidation_success': 'entrada',
    
    # Blueprint de pesaje
    'pesaje': 'pesaje',
    'pesaje_inicial': 'pesaje',
    'procesar_pesaje_directo': 'pesaje',
    'solicitar_autorizacion_pesaje': 'pesaje',
    'validar_codigo_autorizacion': 'pesaje',
    'registrar_peso_directo': 'pesaje',
    'registrar_peso_virtual': 'pesaje',
    'ver_resultados_pesaje': 'pesaje',
    'lista_pesajes': 'pesaje',
    'lista_pesajes_neto': 'pesaje',
    
    # Blueprint de clasificación
    'clasificacion': 'clasificacion',
    'registrar_clasificacion': 'clasificacion',
    'ver_resultados_clasificacion': 'clasificacion',
    'listar_clasificaciones': 'clasificacion',
    'listar_clasificaciones_filtradas': 'clasificacion',
    'procesar_clasificacion': 'clasificacion',
    'procesar_clasificacion_manual': 'clasificacion',
    'iniciar_procesamiento': 'clasificacion',
    'mostrar_resultados_automaticos': 'clasificacion',
    
    # Blueprint de pesaje neto
    'pesaje_neto': 'pesaje_neto',
    'pesaje_tara': 'pesaje_neto',
    'registrar_peso_neto': 'pesaje_neto',
    'registrar_peso_neto_directo': 'pesaje_neto',
    'registrar_peso_neto_virtual': 'pesaje_neto',
    'ver_resultados_pesaje_neto': 'pesaje_neto',
    
    # Blueprint de salida
    'registro_salida': 'salida',
    'completar_registro_salida': 'salida',
    'ver_resultados_salida': 'salida',
    
    # Blueprint de admin
    'admin': 'admin',
    'migrar_registros': 'admin',
}

def update_template(filepath):
    """
    Actualiza las referencias a url_for en la plantilla especificada.
    """
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Buscar referencias a url_for
    url_for_pattern = r"url_for\(\s*['\"]([\w_]+)['\"]"
    matches = re.findall(url_for_pattern, content)
    
    modified = False
    for function_name in matches:
        if function_name in FUNCTION_TO_BLUEPRINT:
            blueprint = FUNCTION_TO_BLUEPRINT[function_name]
            old = f"url_for('{function_name}'"
            new = f"url_for('{blueprint}.{function_name}'"
            
            if old in content:
                content = content.replace(old, new)
                modified = True
                print(f"  - Reemplazado: {old} -> {new}")
    
    if modified:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Actualizado: {filepath}")
        return True
    else:
        print(f"⏭️ Sin cambios: {filepath}")
        return False

def main():
    """
    Función principal que recorre todas las plantillas y actualiza las referencias.
    """
    # Obtener todas las plantillas
    templates = glob.glob('templates/**/*.html', recursive=True)
    
    count_modified = 0
    for template in templates:
        print(f"\nProcesando: {template}")
        if update_template(template):
            count_modified += 1
    
    print(f"\nResumen: {count_modified} de {len(templates)} plantillas actualizadas.")

if __name__ == "__main__":
    main() 