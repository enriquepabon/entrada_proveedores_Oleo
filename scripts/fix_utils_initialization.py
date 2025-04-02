#!/usr/bin/env python3
"""
Script para modificar todas las funciones en app/blueprints/misc/routes.py
para inicializar Utils dentro del contexto de la aplicación.
"""

import re

def add_utils_initialization(file_path):
    """
    Añade la inicialización de Utils al principio de cada función de ruta.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Patrón para encontrar definiciones de funciones de ruta
    route_pattern = r'(@bp\.route\([^\)]+\)\s*\n\s*def\s+([^\(]+)\([^\)]*\):\s*\n\s*"""[^"]*"""\s*\n\s*try:\s*\n)'
    
    # Reemplazar con la inicialización de Utils
    utils_init = r'\1    # Inicializar Utils dentro del contexto de la aplicación\n    utils = Utils(current_app)\n    \n    '
    
    # Aplicar el reemplazo
    modified_content = re.sub(route_pattern, utils_init, content)
    
    # Patrón para encontrar definiciones de funciones de ruta sin bloque try
    route_pattern_no_try = r'(@bp\.route\([^\)]+\)\s*\n\s*def\s+([^\(]+)\([^\)]*\):\s*\n\s*"""[^"]*"""\s*\n)'
    
    # Reemplazar con la inicialización de Utils y añadir un bloque try
    utils_init_with_try = r'\1    # Inicializar Utils dentro del contexto de la aplicación\n    utils = Utils(current_app)\n    \n    try:\n        '
    
    # Aplicar el reemplazo
    modified_content = re.sub(route_pattern_no_try, utils_init_with_try, modified_content)
    
    # Guardar el archivo modificado
    with open(file_path, 'w') as f:
        f.write(modified_content)
    
    print(f"✅ Archivo modificado: {file_path}")

if __name__ == "__main__":
    file_path = "app/blueprints/misc/routes.py"
    add_utils_initialization(file_path) 