"""
Módulo para generar imágenes anotadas con bounding boxes para las detecciones.
"""
import os
import logging
from flask import url_for, current_app
import traceback
import io
import base64
import re
from PIL import Image, ImageDraw, ImageFont, ImageColor
import numpy as np

logger = logging.getLogger(__name__)

# Colores predefinidos para las categorías
COLORES = {
    'verde': '#2CD241',          # Verde brillante
    'maduro': '#FF8C00',         # Naranja brillante
    'sobremaduro': '#F5113B',    # Rojo intenso
    'podrido': '#000000',        # Negro
    'danio_corona': '#9825CF',   # Morado
    'pendunculo_largo': '#10A5E0' # Azul claro
}

# Lista de fuentes para intentar (en orden de preferencia)
FONT_LIST = [
    'arial.ttf',
    'ariblk.ttf',  # Arial Black
    'arialbd.ttf', # Arial Bold
    'DejaVuSans-Bold.ttf',
    'DejaVuSans.ttf',
    'FreeSans.ttf',
    'FreeSansBold.ttf',
    'LiberationSans-Bold.ttf',
    'LiberationSans-Regular.ttf',
    'Roboto-Bold.ttf',
    'Roboto-Regular.ttf',
    'OpenSans-Bold.ttf',
    'OpenSans-Regular.ttf',
]

def get_font(size=30):
    """
    Intenta obtener una fuente del sistema con el tamaño especificado.
    
    Args:
        size: Tamaño de la fuente
        
    Returns:
        Objeto ImageFont o None si no se encuentra ninguna fuente
    """
    # Si estamos en entorno Flask, buscar en la carpeta de estáticos
    app_fonts_path = None
    try:
        if current_app:
            app_fonts_path = os.path.join(current_app.static_folder, 'fonts')
    except:
        pass
    
    # Intentar las fuentes en la lista
    for font_name in FONT_LIST:
        try:
            # Intenta usar PIL para crear la fuente
            return ImageFont.truetype(font_name, size)
        except (OSError, IOError):
            # Intenta en la carpeta de fonts de la aplicación
            if app_fonts_path:
                try:
                    font_path = os.path.join(app_fonts_path, font_name)
                    if os.path.exists(font_path):
                        return ImageFont.truetype(font_path, size)
                except (OSError, IOError):
                    continue
    
    # Si no se encuentra una fuente TrueType, usar el default
    logger.warning("No se pudo encontrar una fuente TrueType, usando fuente predeterminada")
    try:
        return ImageFont.load_default()
    except:
        logger.error("No se pudo cargar ninguna fuente")
        return None

def draw_text_with_outline(draw, pos, text, font, text_color="#FFFFFF", outline_color="#000000", outline_width=2):
    """
    Dibuja texto con un contorno para hacerlo más visible.
    
    Args:
        draw: Objeto ImageDraw
        pos: Tupla (x, y) para la posición del texto
        text: Texto a dibujar
        font: Fuente a usar
        text_color: Color del texto
        outline_color: Color del contorno
        outline_width: Ancho del contorno en píxeles
    """
    x, y = pos
    
    # Dibujar el contorno
    for dx in range(-outline_width, outline_width + 1, 1):
        for dy in range(-outline_width, outline_width + 1, 1):
            if dx*dx + dy*dy <= outline_width*outline_width:  # Solo dibujar en círculo
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
    
    # Dibujar el texto principal
    draw.text(pos, text, font=font, fill=text_color)

def generate_annotated_image(original_image_path, detections, output_path=None):
    """
    Genera una imagen con anotaciones (bounding boxes) basadas en las detecciones
    de Roboflow y guarda la imagen procesada.
    
    Args:
        original_image_path (str): Ruta al archivo de imagen original
        detections (list): Lista de detecciones con x, y, width, height, class y confidence
        output_path (str, optional): Ruta donde guardar la imagen resultante
    
    Returns:
        str: Ruta al archivo generado o None si hay error
    """
    try:
        logger.debug(f"Generando imagen anotada para '{original_image_path}'")
        
        # Comprobar si la ruta de imagen es una URL relativa para Flask
        if original_image_path.startswith('/static/'):
            # Convertir a ruta de sistema de archivos
            if current_app:
                original_image_path = os.path.join(
                    current_app.root_path, 
                    'static', 
                    original_image_path.replace('/static/', '')
                )
        
        # Verificar si es base64
        if isinstance(original_image_path, str) and (
            original_image_path.startswith('data:image/') or 
            ';base64,' in original_image_path or
            len(original_image_path) > 100 and '/' not in original_image_path
        ):
            # Es base64, decodificar
            from app.blueprints.clasificacion.routes import decode_image_data
            image_data = decode_image_data(original_image_path)
            img = Image.open(io.BytesIO(image_data))
        elif isinstance(original_image_path, bytes):
            # Ya son bytes de imagen
            img = Image.open(io.BytesIO(original_image_path))
        else:
            # Es una ruta a un archivo
            if not os.path.exists(original_image_path):
                logger.error(f"La imagen original no existe: {original_image_path}")
                return None
            
            # Abrir la imagen desde el archivo
            img = Image.open(original_image_path)
        
        # Obtener las dimensiones de la imagen
        img_width, img_height = img.size
        
        # Si la imagen es muy grande, redimensionarla manteniendo proporciones
        max_dimension = 3000
        if img_width > max_dimension or img_height > max_dimension:
            scale = min(max_dimension / img_width, max_dimension / img_height)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            img = img.resize((new_width, new_height), Image.LANCZOS)
            img_width, img_height = img.size
            logger.info(f"Imagen redimensionada a {new_width}x{new_height}")
        
        # Convertir a RGB si es necesario
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Crear un objeto para dibujar sobre la imagen
        draw = ImageDraw.Draw(img)
        
        # Obtener fuente para las etiquetas
        font_size = max(int(img_height / 40), 30)  # Tamaño mínimo 30
        font = get_font(font_size)
        
        logger.debug(f"Procesando {len(detections)} detecciones")
        
        # Para cada detección, dibujar su bounding box
        for i, detection in enumerate(detections):
            try:
                # Extraer datos de la detección
                x_center = float(detection.get('x', 0.5))  # Normalizado 0-1
                y_center = float(detection.get('y', 0.5))  # Normalizado 0-1
                width = float(detection.get('width', 0.1))  # Normalizado 0-1
                height = float(detection.get('height', 0.1))  # Normalizado 0-1
                confidence = float(detection.get('confidence', 0.0))
                
                # Clase de la detección
                class_name = detection.get('class', 'desconocido').lower()
                
                # Convertir coordenadas normalizadas a píxeles
                x1 = int((x_center - width / 2) * img_width)
                y1 = int((y_center - height / 2) * img_height)
                x2 = int((x_center + width / 2) * img_width)
                y2 = int((y_center + height / 2) * img_height)
                
                # Ajustar para que esté dentro de la imagen
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(img_width, x2)
                y2 = min(img_height, y2)
                
                # Obtener el color para esta clase
                color = COLORES.get(class_name, '#FF0000')  # Rojo por defecto
                
                # Dibujar el rectángulo con un grosor proporcional a la imagen
                line_thickness = max(int(min(img_width, img_height) / 200), 3)
                draw.rectangle([x1, y1, x2, y2], outline=color, width=line_thickness)
                
                # Preparar el texto de la etiqueta
                if confidence > 0:
                    label = f"{class_name} {confidence:.2f}"
                else:
                    label = class_name
                
                # Calcular tamaño del texto para colocarlo correctamente
                if font:
                    text_width, text_height = font.getsize(label) if hasattr(font, 'getsize') else draw.textbbox((0, 0), label, font=font)[2:4]
                else:
                    text_width, text_height = 100, 20  # valores aproximados si no hay fuente
                
                # Determinar la posición del texto (arriba o dentro del rectángulo)
                # si hay espacio arriba, colocar encima
                if y1 > text_height + 5:
                    text_x = x1
                    text_y = y1 - text_height - 5
                # si no hay espacio arriba pero hay espacio dentro del rectángulo
                elif y2 - y1 > text_height + 10:
                    text_x = x1 + 5
                    text_y = y1 + 5
                # como último recurso, colocar dentro del rectángulo en la parte inferior
                else:
                    text_x = x1 + 5
                    text_y = y2 - text_height - 5
                
                # Dibujar un fondo para el texto para hacerlo más legible
                rect_margin = 2
                draw.rectangle(
                    [text_x - rect_margin, text_y - rect_margin, 
                     text_x + text_width + rect_margin, text_y + text_height + rect_margin],
                    fill=color
                )
                
                # Dibujar el texto con contorno para mejor legibilidad
                draw_text_with_outline(
                    draw, (text_x, text_y), 
                    label, font, 
                    text_color="#FFFFFF",  # Texto blanco
                    outline_color="#000000",  # Contorno negro
                    outline_width=2  # Grosor del contorno
                )
                
            except Exception as e:
                logger.error(f"Error procesando detección {i}: {str(e)}")
                logger.error(traceback.format_exc())
                continue
        
        # Si no se especificó una ruta para guardar, crear una basada en la original
        if not output_path:
            if isinstance(original_image_path, str) and os.path.exists(original_image_path):
                base_path = os.path.splitext(original_image_path)[0]
                output_path = f"{base_path}_annotated.jpg"
            else:
                # Generar un nombre basado en timestamp
                import time
                output_path = f"annotated_image_{int(time.time())}.jpg"
        
        # Asegurar que el directorio de salida existe
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # Guardar la imagen con alta calidad
        img.save(output_path, 'JPEG', quality=95)
        logger.info(f"Imagen anotada guardada en: {output_path}")
        
        return output_path
        
    except Exception as e:
        logger.error(f"Error al generar imagen anotada: {str(e)}")
        logger.error(traceback.format_exc())
        return None 