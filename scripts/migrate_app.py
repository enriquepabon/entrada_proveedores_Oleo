#!/usr/bin/env python3
"""
Script para facilitar la migración completa de la aplicación.
Este script coordina la migración de rutas y utilidades, y copia los archivos necesarios.
"""

import os
import sys
import shutil
import subprocess
import glob
from datetime import datetime

def create_backup(source_file, backup_dir):
    """
    Crea una copia de seguridad del archivo original.
    """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
    
    backup_file = os.path.join(backup_dir, f"{os.path.basename(source_file)}.bak")
    shutil.copy2(source_file, backup_file)
    print(f"Backup creado: {backup_file}")

def migrate_routes(app_file, output_dir):
    """
    Migra las rutas del archivo principal a blueprints.
    """
    cmd = ["python3", "scripts/migrate_routes.py", app_file]
    subprocess.run(cmd, check=True)
    
    # Buscar en el directorio raíz, no en el directorio de trabajo
    blueprint_pattern = "blueprint_migration_*"
    blueprint_dirs = glob.glob(blueprint_pattern)
    
    if not blueprint_dirs:
        print(f"Advertencia: No se encontraron directorios que coincidan con {blueprint_pattern}")
        return
        
    for blueprint_dir in blueprint_dirs:
        if os.path.isdir(blueprint_dir):
            print(f"Procesando directorio: {blueprint_dir}")
            for route_file in os.listdir(blueprint_dir):
                category = route_file.split("_")[0]
                dest_dir = os.path.join("app", "blueprints", category)
                
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                    print(f"Creado directorio: {dest_dir}")
                    
                shutil.copy2(os.path.join(blueprint_dir, route_file), os.path.join(dest_dir, "routes.py"))
                print(f"Copiado {route_file} a {dest_dir}/routes.py")

def migrate_utils(utils_file, output_dir):
    """
    Migra las funciones utilitarias a módulos específicos.
    """
    cmd = ["python3", "scripts/migrate_utils.py", utils_file]
    subprocess.run(cmd, check=True)
    
    # Buscar en el directorio raíz, no en el directorio de trabajo
    utils_pattern = "utils_migration_*"
    utils_dirs = glob.glob(utils_pattern)
    
    if not utils_dirs:
        print(f"Advertencia: No se encontraron directorios que coincidan con {utils_pattern}")
        return
        
    for utils_dir in utils_dirs:
        if os.path.isdir(utils_dir):
            print(f"Procesando directorio: {utils_dir}")
            for util_file in os.listdir(utils_dir):
                category = util_file.split(".")[0]
                dest_dir = os.path.join("app", "utils")
                
                if not os.path.exists(dest_dir):
                    os.makedirs(dest_dir, exist_ok=True)
                    print(f"Creado directorio: {dest_dir}")
                
                dest_file = os.path.join(dest_dir, f"{category}.py")
                shutil.copy2(os.path.join(utils_dir, util_file), dest_file)
                print(f"Copiado {util_file} a {dest_file}")

def main():
    """
    Función principal que coordina la migración completa.
    """
    # Crear directorio de trabajo
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    work_dir = f'migration_work_{timestamp}'
    os.makedirs(work_dir, exist_ok=True)
    
    # Crear backups
    create_backup("apptiquetes.py", work_dir)
    create_backup("utils.py", work_dir)
    
    # Migrar rutas
    print("\n=== Migrando rutas ===")
    try:
        migrate_routes("apptiquetes.py", work_dir)
    except Exception as e:
        print(f"Error al migrar rutas: {str(e)}")
    
    # Migrar utilidades
    print("\n=== Migrando utilidades ===")
    try:
        migrate_utils("utils.py", work_dir)
    except Exception as e:
        print(f"Error al migrar utilidades: {str(e)}")
    
    print("\n=== Migración completada ===")
    print(f"Archivos de trabajo guardados en: {work_dir}")
    print("Revise los archivos generados y ajuste según sea necesario.")
    print("Para ejecutar la aplicación refactorizada: python app/run.py")

if __name__ == "__main__":
    main() 