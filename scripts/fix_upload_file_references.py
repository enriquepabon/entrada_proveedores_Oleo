#!/usr/bin/env python3
"""
Script para corregir las referencias a url_for('entrada.upload_file') en las plantillas,
cambiándolas a url_for('misc.upload_file').
"""

import os
import re
import glob

def update_template(filepath):
    """
    Actualiza las referencias a url_for('entrada.upload_file') en la plantilla especificada.
    """
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Buscar referencias a url_for('entrada.upload_file')
    old_pattern = "url_for('entrada.upload_file')"
    new_pattern = "url_for('misc.upload_file')"
    
    if old_pattern in content:
        content = content.replace(old_pattern, new_pattern)
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