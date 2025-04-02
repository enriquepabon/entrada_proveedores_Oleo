#!/usr/bin/env python3
"""
Script para ayudar a migrar las funciones utilitarias a módulos específicos.
Este script analiza el archivo utils.py y clasifica las funciones por categoría.
"""

import re
import os
import sys
from datetime import datetime

# Categorías de funciones utilitarias
CATEGORIES = {
    'common': [
        r'ensure_directories',
        r'get_datos_guia',
        r'update_datos_guia',
        r'get_datos_registro',
        r'generar_codigo_guia',
        r'generate_unique_id',
        r'_verificar_y_corregir_campos',
    ],
    'pdf_generator': [
        r'generate_pdf',
        r'generar_pdf_completo',
        r'generar_pdf_proceso_completo',
        r'generar_pdf_clasificacion',
        r'generar_pdf_pesaje',
        r'generar_pdf_pesaje_neto',
        r'generar_pdf_registro',
    ],
    'image_processing': [
        r'generate_qr',
        r'generar_qr',
        r'process_tiquete_image',
        r'process_plate_image',
        r'process_images_with_roboflow',
    ],
}

def find_method_blocks(file_path):
    """
    Encuentra bloques de código que contienen métodos en la clase Utils.
    """
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Patrón para encontrar métodos en la clase Utils
    pattern = r'    def ([a-zA-Z0-9_]+)\(self(?:, [^)]+)?\):\s*(?:"""(?:.+?)""")?\s*(.+?)(?=    def|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    
    method_blocks = {}
    for method_name, method_body in matches:
        method_blocks[method_name] = f"def {method_name}(self{', ' if method_body.strip() else ''}...):\n{method_body}"
    
    return method_blocks

def categorize_method(method_name):
    """
    Categoriza un método según las categorías definidas.
    """
    for category, patterns in CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, method_name):
                return category
    
    return 'misc'  # Categoría por defecto para métodos no categorizados

def create_util_files(methods_by_category):
    """
    Crea archivos para cada categoría de utilidades con los métodos correspondientes.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_dir = f'utils_migration_{timestamp}'
    os.makedirs(output_dir, exist_ok=True)
    
    for category, methods in methods_by_category.items():
        if not methods:
            continue
        
        output_file = os.path.join(output_dir, f'{category}.py')
        
        with open(output_file, 'w') as f:
            f.write(f"""import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template

# Configurar logging
logger = logging.getLogger(__name__)

class {category.capitalize()}Utils:
    def __init__(self, app):
        self.app = app
        
""")
            
            for method_name, method_body in methods.items():
                f.write(f"    {method_body}\n\n")
    
    print(f"Archivos de utilidades creados en el directorio: {output_dir}")

def main():
    if len(sys.argv) != 2:
        print("Uso: python migrate_utils.py <ruta_al_archivo_utils.py>")
        sys.exit(1)
    
    file_path = sys.argv[1]
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe.")
        sys.exit(1)
    
    method_blocks = find_method_blocks(file_path)
    print(f"Se encontraron {len(method_blocks)} métodos en la clase Utils.")
    
    methods_by_category = {category: {} for category in CATEGORIES.keys()}
    methods_by_category['misc'] = {}  # Para métodos no categorizados
    
    for method_name, method_body in method_blocks.items():
        category = categorize_method(method_name)
        methods_by_category[category][method_name] = method_body
    
    # Imprimir estadísticas
    print("\nEstadísticas de métodos por categoría:")
    for category, methods in methods_by_category.items():
        print(f"{category}: {len(methods)} métodos")
    
    create_util_files(methods_by_category)

if __name__ == "__main__":
    main() 