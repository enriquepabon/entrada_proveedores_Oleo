"""
Utilidades para el módulo de clasificación, incluyendo funciones para manejo de imágenes,
estandarización de rutas y manejo de archivos.
"""
import os
import logging
from flask import url_for, current_app

logger = logging.getLogger(__name__)

# Rutas estándar donde se guardan las imágenes de clasificación
IMAGE_PATHS = [
    'fotos_racimos_temp/{url_guia}/',
    'uploads/fotos/{url_guia}/',
    'uploads/clasificacion/{url_guia}/',
    'clasificaciones/fotos/{url_guia}/'
]

def normalize_image_path(image_path, url_guia, static_folder=None):
    """
    Normaliza una ruta de imagen para uso en plantillas web.
    Convierte rutas absolutas a URLs relativas para el navegador.
    
    Args:
        image_path (str): Ruta original de la imagen (puede ser absoluta o relativa)
        url_guia (str): ID de la guía para buscar en directorios alternativos
        static_folder (str, opcional): Directorio static de la aplicación
        
    Returns:
        str: URL relativa normalizada para uso en plantillas
    """
    logger.info(f"Normalizando ruta de imagen: {image_path}")
    
    if not image_path:
        logger.warning("La ruta de imagen está vacía")
        return ""
    
    if static_folder is None:
        static_folder = current_app.static_folder
        logger.info(f"Usando static_folder: {static_folder}")
    
    # Si es una ruta absoluta
    if os.path.isabs(image_path):
        logger.info(f"La ruta es absoluta: {image_path}")
        
        # 1. Verificar si la ruta comienza con el directorio static
        if image_path.startswith(static_folder):
            rel_path = image_path.replace(static_folder, '').lstrip('/')
            url = url_for('static', filename=rel_path)
            logger.info(f"Convertida a URL relativa: {url}")
            return url
        
        # 2. Verificar si el archivo existe en la ruta absoluta
        if os.path.exists(image_path):
            logger.info(f"El archivo existe en la ruta absoluta: {image_path}")
        else:
            logger.warning(f"El archivo NO existe en la ruta absoluta: {image_path}")
        
        # 3. Si no, extraer el nombre del archivo
        file_name = os.path.basename(image_path)
        logger.info(f"Nombre del archivo extraído: {file_name}")
        
        # 4. Buscar en todas las rutas posibles
        for path_template in IMAGE_PATHS:
            rel_path = path_template.format(url_guia=url_guia) + file_name
            full_path = os.path.join(static_folder, rel_path)
            logger.info(f"Buscando en ruta alternativa: {full_path}")
            
            if os.path.exists(full_path):
                url = url_for('static', filename=rel_path)
                logger.info(f"Encontrada imagen en ruta alternativa: {url}")
                return url
    else:
        logger.info(f"La ruta NO es absoluta: {image_path}")
    
    # Si es una ruta relativa o no se encontró el archivo en rutas absolutas
    # Verificar si podría ser una URL ya válida (comienza con static)
    if isinstance(image_path, str) and 'static/' in image_path:
        logger.info(f"Ya parece ser una URL válida: {image_path}")
        return image_path
    
    # Intentar como ruta relativa dentro de static
    try:
        url = url_for('static', filename=image_path)
        logger.info(f"Generada URL como ruta relativa: {url}")
        
        # Verificar si el archivo existe
        full_path = os.path.join(static_folder, image_path)
        if os.path.exists(full_path):
            logger.info(f"El archivo existe en: {full_path}")
        else:
            logger.warning(f"El archivo NO existe en: {full_path}")
            
        return url
    except Exception as e:
        logger.error(f"Error generando URL: {str(e)}")
        return ""

def find_annotated_image(original_image_url, url_guia, static_folder=None):
    """
    Busca la versión anotada de una imagen original en diferentes directorios.
    
    Args:
        original_image_url (str): URL o ruta de la imagen original
        url_guia (str): ID de la guía para buscar en directorios estándar
        static_folder (str, opcional): Directorio static de la aplicación
        
    Returns:
        str: URL de la imagen anotada o cadena vacía si no se encuentra
    """
    if not original_image_url:
        return ""
    
    if static_folder is None:
        static_folder = current_app.static_folder
    
    # Extraer nombre de archivo de la URL original
    if '/' in original_image_url:
        base_name = original_image_url.split('/')[-1]
    else:
        base_name = original_image_url
    
    # Generar nombre de archivo para versión anotada
    name, ext = os.path.splitext(base_name)
    annotated_name = f"{name}_annotated{ext}"
    
    # Buscar en todas las rutas estándar
    for path_template in IMAGE_PATHS:
        rel_path = path_template.format(url_guia=url_guia) + annotated_name
        full_path = os.path.join(static_folder, rel_path)
        
        if os.path.exists(full_path):
            logger.info(f"Encontrada imagen anotada en: {rel_path}")
            return url_for('static', filename=rel_path)
    
    return ""

def find_original_images(url_guia, limit=3, static_folder=None):
    """
    Busca imágenes originales para una guía en las rutas estándar.
    
    Args:
        url_guia (str): ID de la guía
        limit (int): Número máximo de imágenes a devolver
        static_folder (str, opcional): Directorio static de la aplicación
        
    Returns:
        list: Lista de URLs de imágenes originales encontradas
    """
    if static_folder is None:
        static_folder = current_app.static_folder
    
    found_images = []
    
    # Buscar en todas las rutas estándar
    for path_template in IMAGE_PATHS:
        if len(found_images) >= limit:
            break
            
        dir_path = os.path.join(static_folder, path_template.format(url_guia=url_guia))
        
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            # Listar archivos y filtrar solo imágenes originales
            files = sorted(os.listdir(dir_path))
            for file in files:
                if len(found_images) >= limit:
                    break
                    
                # Filtrar solo archivos JPG/JPEG/PNG que no sean resized ni annotated
                if file.lower().endswith(('.jpg', '.jpeg', '.png')) and 'resized' not in file and 'annotated' not in file:
                    rel_path = path_template.format(url_guia=url_guia) + file
                    found_images.append(url_for('static', filename=rel_path))
    
    return found_images 