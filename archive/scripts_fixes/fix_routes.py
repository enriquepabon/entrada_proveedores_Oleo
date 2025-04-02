#!/usr/bin/env python3
import os
import re
import shutil

def fix_routes_file():
    # Ruta al archivo original
    file_path = 'app/blueprints/clasificacion/routes.py'
    
    # Crear una copia de seguridad
    backup_path = f"{file_path}.backup"
    shutil.copy2(file_path, backup_path)
    print(f"Copia de seguridad creada en: {backup_path}")
    
    # Leer el contenido del archivo
    with open(file_path, 'r') as f:
        content = f.read()
    
    # El patrón a buscar es la línea problemática y algún código antes/después
    pattern = r'(# Si hay actualizaciones para hacer\.\.\.\s+if updates:.+?params\.append\(codigo_guia\).+?)# Redirigir a la guía centralizada'
    
    # Reemplazar con el try-except completo
    replacement = r'\1            try:\n                # Redirigir a la guía centralizada'
    
    # Realizar la sustitución
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Verificar que se hizo el cambio
    if new_content == content:
        print("No se pudo encontrar el patrón para reemplazar. Operación abortada.")
        return False
    
    # Escribir el contenido modificado
    with open(file_path, 'w') as f:
        f.write(new_content)
        
    print(f"Archivo {file_path} modificado con éxito.")
    return True

if __name__ == "__main__":
    fix_routes_file() 