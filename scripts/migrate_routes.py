#!/usr/bin/env python3
"""
Script para ayudar a migrar las rutas del archivo apptiquetes.py a los nuevos blueprints.
Este script analiza el archivo original, identifica las rutas y las clasifica por categoría.
"""

import re
import os
import sys
from datetime import datetime

# Categorías de rutas
CATEGORIES = {
    'entrada': [
        r'^@app\.route\(\'/?$', 
        r'^@app\.route\(\'/index', 
        r'^@app\.route\(\'/home',
        r'^@app\.route\(\'/processing',
        r'^@app\.route\(\'/process_image',
        r'^@app\.route\(\'/review',
        r'^@app\.route\(\'/register',
        r'^@app\.route\(\'/update_data',
        r'^@app\.route\(\'/registros-entrada',
        r'^@app\.route\(\'/registro-entrada',
    ],
    'pesaje': [
        r'^@app\.route\(\'/pesaje',
        r'^@app\.route\(\'/procesar_pesaje',
        r'^@app\.route\(\'/verificar_placa_pesaje',
        r'^@app\.route\(\'/solicitar_autorizacion_pesaje',
        r'^@app\.route\(\'/validar_codigo_autorizacion',
        r'^@app\.route\(\'/registrar_peso',
    ],
    'clasificacion': [
        r'^@app\.route\(\'/clasificacion',
        r'^@app\.route\(\'/registrar_clasificacion',
        r'^@app\.route\(\'/ver_resultados_clasificacion',
        r'^@app\.route\(\'/clasificaciones',
        r'^@app\.route\(\'/procesar_clasificacion',
        r'^@app\.route\(\'/iniciar_procesamiento',
        r'^@app\.route\(\'/check_procesamiento_status',
        r'^@app\.route\(\'/procesar_imagenes',
        r'^@app\.route\(\'/mostrar_resultados_automaticos',
    ],
    'pesaje_neto': [
        r'^@app\.route\(\'/pesaje-neto',
        r'^@app\.route\(\'/pesaje_neto',
        r'^@app\.route\(\'/registrar_peso_neto',
        r'^@app\.route\(\'/ver_resultados_pesaje_neto',
        r'^@app\.route\(\'/pesajes-neto',
    ],
    'salida': [
        r'^@app\.route\(\'/registro-salida',
        r'^@app\.route\(\'/completar_registro_salida',
        r'^@app\.route\(\'/ver_resultados_salida',
    ],
    'admin': [
        r'^@app\.route\(\'/admin',
        r'^@app\.route\(\'/migrar-registros',
    ],
    'api': [
        r'^@app\.route\(\'/api',
        r'^@app\.route\(\'/debug',
        r'^@app\.route\(\'/test',
        r'^@app\.route\(\'/verificar_placa',
    ],
}

def find_route_blocks(file_path):
    """
    Encuentra bloques de código que contienen rutas en el archivo.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Patrón para encontrar bloques de rutas
    pattern = r'(@app\.route\([^\)]+\)[^\n]*\n)([^@]*)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    route_blocks = []
    for route_def, route_body in matches:
        route_blocks.append(route_def + route_body)
    
    return route_blocks

def categorize_route(route_block):
    """
    Categoriza un bloque de ruta según las categorías definidas.
    """
    first_line = route_block.split('\n')[0]
    
    for category, patterns in CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, first_line):
                return category
    
    return 'misc'  # Categoría por defecto para rutas no categorizadas

def extract_function_name(route_block):
    """
    Extrae el nombre de la función de un bloque de ruta.
    """
    # Patrón para encontrar la definición de la función
    pattern = r'def\s+([a-zA-Z0-9_]+)\s*\('
    match = re.search(pattern, route_block)
    
    if match:
        return match.group(1)
    
    return None

def create_blueprint_files(routes_by_category):
    """
    Crea archivos para cada blueprint con las rutas correspondientes.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = f'blueprint_migration_{timestamp}'
    os.makedirs(output_dir, exist_ok=True)
    
    for category, routes in routes_by_category.items():
        if not routes:
            continue
        
        output_file = os.path.join(output_dir, f'{category}_routes.py')
        
        with open(output_file, 'w') as f:
            f.write(f"""from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.{category} import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

""")
            
            for route in routes:
                # Reemplazar @app.route por @bp.route
                modified_route = route.replace('@app.route', '@bp.route')
                
                # Reemplazar url_for sin prefijo de blueprint
                function_name = extract_function_name(route)
                if function_name:
                    modified_route = re.sub(
                        r'url_for\([\'"](' + function_name + r')[\'"]', 
                        f'url_for(\'{category}.\\1\'', 
                        modified_route
                    )
                
                f.write(modified_route)
                f.write('\n\n')
    
    print(f"Archivos de blueprint creados en el directorio: {output_dir}")

def main():
    if len(sys.argv) != 2:
        print("Uso: python migrate_routes.py <ruta_al_archivo_apptiquetes.py>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        sys.exit(1)
    
    route_blocks = find_route_blocks(file_path)
    print(f"Se encontraron {len(route_blocks)} bloques de rutas.")
    
    routes_by_category = {category: [] for category in CATEGORIES.keys()}
    routes_by_category['misc'] = []  # Para rutas no categorizadas
    
    for route_block in route_blocks:
        category = categorize_route(route_block)
        routes_by_category[category].append(route_block)
    
    # Imprimir estadísticas
    print("\nEstadísticas de rutas por categoría:")
    for category, routes in routes_by_category.items():
        print(f"{category}: {len(routes)} rutas")
    
    create_blueprint_files(routes_by_category)

if __name__ == "__main__":
    main() 