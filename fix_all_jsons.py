#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import glob

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_image_urls_in_json(json_path, url_guia, static_folder):
    """
    Corrige las rutas de imágenes en un archivo JSON de clasificación para usar
    rutas relativas en lugar de absolutas.
    
    Args:
        json_path (str): Ruta al archivo JSON de clasificación
        url_guia (str): ID de la guía para usar en las rutas relativas
        static_folder (str): Ruta del directorio static
        
    Returns:
        bool: True si se realizaron cambios, False en caso contrario
    """
    try:
        # Leer archivo JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Hacer una copia para verificar cambios
        original_data = json.dumps(data)
        
        # Corregir campo 'fotos'
        if 'fotos' in data:
            fixed_fotos = []
            for foto in data['fotos']:
                if isinstance(foto, str) and os.path.isabs(foto):
                    # Extraer nombre de archivo
                    file_name = os.path.basename(foto)
                    # Construir ruta relativa
                    rel_path = f"fotos_racimos_temp/{url_guia}/{file_name}"
                    
                    # Verificar si existe el archivo
                    full_path = os.path.join(static_folder, rel_path)
                    
                    if os.path.exists(full_path):
                        logger.info(f"Ruta corregida: {foto} -> {rel_path}")
                        fixed_fotos.append(rel_path)
                    else:
                        logger.warning(f"No se encontró el archivo: {full_path}")
                        fixed_fotos.append(foto)  # Mantener la ruta original
                else:
                    fixed_fotos.append(foto)
            
            data['fotos'] = fixed_fotos
        
        # Corregir resultados_por_foto si existe
        if 'resultados_por_foto' in data:
            if isinstance(data['resultados_por_foto'], dict):
                # Si es un diccionario
                for key in data['resultados_por_foto']:
                    resultado = data['resultados_por_foto'][key]
                    fix_result_images(resultado, url_guia, static_folder)
            elif isinstance(data['resultados_por_foto'], list):
                # Si es una lista
                for resultado in data['resultados_por_foto']:
                    fix_result_images(resultado, url_guia, static_folder)
        
        # Verificar si hubo cambios
        fixed_data = json.dumps(data)
        if original_data != fixed_data:
            # Guardar cambios
            logger.info(f"Guardando cambios en: {json_path}")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        else:
            logger.info(f"No se requirieron cambios en: {json_path}")
            return False
    
    except Exception as e:
        logger.error(f"Error procesando JSON: {str(e)}")
        logger.error(f"Error detallado:", exc_info=True)
        return False

def fix_result_images(resultado, url_guia, static_folder):
    """
    Corrige las rutas de imágenes en un resultado individual.
    
    Args:
        resultado (dict): Diccionario con datos de resultado
        url_guia (str): ID de la guía
        static_folder (str): Ruta del directorio static
    """
    # Corregir imagen original
    if 'imagen_original' in resultado and isinstance(resultado['imagen_original'], str) and os.path.isabs(resultado['imagen_original']):
        # Extraer nombre de archivo
        file_name = os.path.basename(resultado['imagen_original'])
        # Construir ruta relativa
        rel_path = f"fotos_racimos_temp/{url_guia}/{file_name}"
        # Verificar si existe
        full_path = os.path.join(static_folder, rel_path)
        
        if os.path.exists(full_path):
            logger.info(f"Ruta de imagen original corregida en resultado: {resultado['imagen_original']} -> {rel_path}")
            resultado['imagen_original'] = rel_path
    
    # Corregir imagen procesada
    if 'imagen_procesada' in resultado and isinstance(resultado['imagen_procesada'], str) and os.path.isabs(resultado['imagen_procesada']):
        # Extraer nombre de archivo
        file_name = os.path.basename(resultado['imagen_procesada'])
        # Construir ruta relativa
        rel_path = f"fotos_racimos_temp/{url_guia}/{file_name}"
        # Verificar si existe
        full_path = os.path.join(static_folder, rel_path)
        
        if os.path.exists(full_path):
            logger.info(f"Ruta de imagen procesada corregida en resultado: {resultado['imagen_procesada']} -> {rel_path}")
            resultado['imagen_procesada'] = rel_path

def process_all_json_files(static_folder):
    """
    Procesa todos los archivos JSON de clasificación.
    
    Args:
        static_folder (str): Ruta del directorio static
        
    Returns:
        tuple: (int, int) - (número de archivos procesados, número de archivos modificados)
    """
    # Buscar archivos JSON de clasificación
    clasificacion_pattern = os.path.join(static_folder, 'clasificaciones', 'clasificacion_*.json')
    json_files = glob.glob(clasificacion_pattern)
    
    # Contadores
    total_processed = 0
    total_modified = 0
    
    for json_file in json_files:
        basename = os.path.basename(json_file)
        # Extraer el url_guia del nombre del archivo
        # clasificacion_CODIGO_FECHA_HORA.json -> CODIGO_FECHA_HORA
        if basename.startswith('clasificacion_'):
            url_guia = basename[len('clasificacion_'):-len('.json')]
            logger.info(f"Procesando archivo: {json_file} con ID de guía: {url_guia}")
            
            # Verificar que existan imágenes para esta guía
            images_dir = os.path.join(static_folder, 'fotos_racimos_temp', url_guia)
            if os.path.exists(images_dir) and os.path.isdir(images_dir):
                result = fix_image_urls_in_json(json_file, url_guia, static_folder)
                total_processed += 1
                if result:
                    total_modified += 1
            else:
                logger.warning(f"No se encontró directorio de imágenes para: {url_guia}")
    
    return total_processed, total_modified

if __name__ == "__main__":
    import sys
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Determinar directorio static
    static_folder = os.path.join(script_dir, 'static')
    if not os.path.exists(static_folder):
        print(f"No se encontró el directorio static en: {static_folder}")
        print("Buscando en directorios alternativos...")
        
        # Intentar otras rutas
        alt_paths = [
            os.path.join(script_dir, 'static'),
            os.path.join(os.path.dirname(script_dir), 'static'),
            './static',
            '../static',
            '/static'
        ]
        
        for path in alt_paths:
            if os.path.exists(path) and os.path.isdir(path):
                static_folder = path
                print(f"Usando directorio static: {static_folder}")
                break
    
    if len(sys.argv) > 1:
        # Si se proporciona un archivo específico
        json_path = sys.argv[1]
        url_guia = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(json_path).split('_', 1)[1].split('.')[0]
        result = fix_image_urls_in_json(json_path, url_guia, static_folder)
        sys.exit(0 if result else 1)
    else:
        # Procesar todos los archivos
        print(f"Procesando todos los archivos JSON de clasificación en: {static_folder}/clasificaciones/")
        total_processed, total_modified = process_all_json_files(static_folder)
        print(f"Procesados {total_processed} archivos. Modificados {total_modified} archivos.")
        sys.exit(0 if total_processed > 0 else 1) 