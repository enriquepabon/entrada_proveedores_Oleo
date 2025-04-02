#!/usr/bin/env python
"""
Script para limpiar códigos QR problemáticos en la aplicación TiquetesApp.

Este script busca y elimina QR problemáticos, especialmente:
- default_qr_20250311143540.png
- default_qr.png
- Cualquier otro QR con prefijo 'default_qr'

Uso:
    python clean_qr.py
"""

import os
import glob
import shutil
from datetime import datetime

def clean_problematic_qrs():
    """Busca y elimina QRs problemáticos del directorio static/qr"""
    # Directorio donde se almacenan los QRs
    base_dir = os.path.dirname(os.path.abspath(__file__))
    qr_dir = os.path.join(base_dir, 'static', 'qr')
    
    # Crear directorio de respaldo para los QRs eliminados
    backup_dir = os.path.join(base_dir, 'static', 'qr_backup', datetime.now().strftime('%Y%m%d_%H%M%S'))
    os.makedirs(backup_dir, exist_ok=True)
    
    print(f"Buscando QRs problemáticos en: {qr_dir}")
    
    if not os.path.exists(qr_dir):
        print(f"El directorio {qr_dir} no existe. Creándolo...")
        os.makedirs(qr_dir, exist_ok=True)
        return
    
    # Lista específica de QRs extremadamente problemáticos
    specific_qrs = [
        os.path.join(qr_dir, 'default_qr_20250311143540.png'),
        os.path.join(qr_dir, 'default_qr.png')
    ]
    
    for qr_path in specific_qrs:
        if os.path.exists(qr_path):
            print(f"Encontrado QR específicamente problemático: {os.path.basename(qr_path)}")
            try:
                # Hacer copia de seguridad antes de eliminar
                backup_path = os.path.join(backup_dir, os.path.basename(qr_path))
                shutil.copy2(qr_path, backup_path)
                
                # Eliminar el archivo
                os.remove(qr_path)
                print(f"  ✓ Eliminado: {os.path.basename(qr_path)}")
            except Exception as e:
                print(f"  ✗ Error al eliminar {os.path.basename(qr_path)}: {str(e)}")
    
    # Buscar y eliminar todos los QRs con patrón default_qr*
    default_qr_pattern = os.path.join(qr_dir, 'default_qr*.png')
    qr_files = glob.glob(default_qr_pattern)
    
    if not qr_files:
        print("No se encontraron QRs con patrón 'default_qr*.png'")
    else:
        print(f"Encontrados {len(qr_files)} QRs con patrón 'default_qr*.png':")
        
        for qr_path in qr_files:
            try:
                # Hacer copia de seguridad antes de eliminar
                backup_path = os.path.join(backup_dir, os.path.basename(qr_path))
                shutil.copy2(qr_path, backup_path)
                
                # Eliminar el archivo
                os.remove(qr_path)
                print(f"  ✓ Eliminado: {os.path.basename(qr_path)}")
            except Exception as e:
                print(f"  ✗ Error al eliminar {os.path.basename(qr_path)}: {str(e)}")
    
    # Buscar archivos de QR que hayan sido renombrados con backup o old
    backup_pattern = os.path.join(qr_dir, 'default_qr*.old')
    old_files = glob.glob(backup_pattern)
    
    backup_pattern2 = os.path.join(qr_dir, 'default_qr*.backup')
    old_files.extend(glob.glob(backup_pattern2))
    
    if old_files:
        print(f"\nEncontrados {len(old_files)} QRs de respaldo que pueden eliminarse:")
        for old_file in old_files:
            print(f"  - {os.path.basename(old_file)}")
        
        response = input("\n¿Desea eliminar también estos archivos de respaldo? (s/n): ")
        if response.lower() == 's':
            for old_file in old_files:
                try:
                    # Hacer copia de seguridad antes de eliminar
                    backup_path = os.path.join(backup_dir, os.path.basename(old_file))
                    shutil.copy2(old_file, backup_path)
                    
                    # Eliminar el archivo
                    os.remove(old_file)
                    print(f"  ✓ Eliminado: {os.path.basename(old_file)}")
                except Exception as e:
                    print(f"  ✗ Error al eliminar {os.path.basename(old_file)}: {str(e)}")
    
    print("\nLimpieza de QRs completada.")
    print(f"Se ha creado una copia de seguridad de todos los archivos eliminados en: {backup_dir}")

if __name__ == "__main__":
    clean_problematic_qrs() 