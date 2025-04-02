#!/usr/bin/env python3
"""
Script para limpiar archivos redundantes del proyecto.
Este script identifica y elimina (opcionalmente) archivos que ya no son necesarios
después de la refactorización, como copias de seguridad, archivos originales migrados, etc.
"""
import os
import glob
import argparse
import shutil
from datetime import datetime

def find_backup_files(directory="."):
    """
    Encuentra archivos de copia de seguridad (.bak*) en el directorio especificado.
    """
    return glob.glob(os.path.join(directory, "**/*.bak*"), recursive=True)

def find_redundant_files(directory="."):
    """
    Encuentra archivos redundantes que ya han sido migrados a blueprints.
    """
    # Lista de archivos que se sabe que ya han sido migrados
    redundant_files = [
        "apptiquetes.py",
        "implementacion_clasificacion.py",
        "utils_clasificacion.py",
        "app_bp.py",
        "debug_bp.py",
    ]
    
    return [os.path.join(directory, f) for f in redundant_files if os.path.exists(os.path.join(directory, f))]

def find_temporary_files(directory="."):
    """
    Encuentra archivos temporales y de caché.
    """
    patterns = [
        "**/__pycache__/**",
        "**/*.pyc",
        "**/*.pyo",
        "**/.DS_Store",
        "**/*.swp",
    ]
    
    temp_files = []
    for pattern in patterns:
        temp_files.extend(glob.glob(os.path.join(directory, pattern), recursive=True))
    
    return temp_files

def create_backup_directory(directory="."):
    """
    Crea un directorio de respaldo con la fecha actual.
    """
    backup_dir = os.path.join(directory, f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir

def move_to_backup(files, backup_dir):
    """
    Mueve archivos al directorio de respaldo en lugar de eliminarlos.
    """
    moved_files = []
    for file_path in files:
        if os.path.exists(file_path):
            # Crear estructura de directorios en el backup
            relative_path = os.path.relpath(file_path, ".")
            backup_path = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(backup_path), exist_ok=True)
            
            # Mover archivo
            shutil.move(file_path, backup_path)
            moved_files.append(file_path)
    
    return moved_files

def delete_files(files):
    """
    Elimina archivos de la lista proporcionada.
    """
    deleted_files = []
    for file_path in files:
        if os.path.exists(file_path):
            if os.path.isdir(file_path):
                shutil.rmtree(file_path)
            else:
                os.remove(file_path)
            deleted_files.append(file_path)
    
    return deleted_files

def main():
    parser = argparse.ArgumentParser(description='Limpia archivos redundantes del proyecto')
    parser.add_argument('--delete', action='store_true', help='Eliminar archivos en lugar de moverlos a respaldo')
    parser.add_argument('--backup-dir', help='Directorio donde se moverán los archivos')
    parser.add_argument('--temp-only', action='store_true', help='Eliminar solo archivos temporales')
    parser.add_argument('--redundant-only', action='store_true', help='Eliminar solo archivos redundantes (migrados)')
    parser.add_argument('--backup-only', action='store_true', help='Eliminar solo archivos de respaldo (.bak)')
    parser.add_argument('--list-only', action='store_true', help='Solo listar archivos sin eliminarlos')
    args = parser.parse_args()
    
    # Determinar qué tipos de archivos buscar
    find_temp = not (args.redundant_only or args.backup_only)
    find_redundant = not (args.temp_only or args.backup_only)
    find_backup = not (args.temp_only or args.redundant_only)
    
    # Recopilar archivos
    files_to_clean = []
    
    if find_temp:
        temp_files = find_temporary_files()
        print(f"\nArchivos temporales encontrados: {len(temp_files)}")
        for file in temp_files:
            print(f"  - {file}")
        files_to_clean.extend(temp_files)
    
    if find_redundant:
        redundant_files = find_redundant_files()
        print(f"\nArchivos redundantes encontrados: {len(redundant_files)}")
        for file in redundant_files:
            print(f"  - {file}")
        files_to_clean.extend(redundant_files)
    
    if find_backup:
        backup_files = find_backup_files()
        print(f"\nArchivos de respaldo encontrados: {len(backup_files)}")
        for file in backup_files:
            print(f"  - {file}")
        files_to_clean.extend(backup_files)
    
    # Salir si solo queremos listar
    if args.list_only:
        print(f"\nTotal de archivos a limpiar: {len(files_to_clean)}")
        print("Se ejecutó en modo 'solo listar'. No se ha eliminado ningún archivo.")
        return
    
    # Salir si no hay nada que limpiar
    if not files_to_clean:
        print("No se encontraron archivos para limpiar.")
        return
    
    if args.delete:
        # Eliminar archivos directamente
        deleted = delete_files(files_to_clean)
        print(f"\nSe eliminaron {len(deleted)} archivos.")
    else:
        # Mover a directorio de respaldo
        backup_dir = args.backup_dir if args.backup_dir else create_backup_directory()
        print(f"\nMoviendo archivos a: {backup_dir}")
        moved = move_to_backup(files_to_clean, backup_dir)
        print(f"Se movieron {len(moved)} archivos al directorio de respaldo.")

if __name__ == "__main__":
    main() 