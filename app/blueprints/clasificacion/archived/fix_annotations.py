"""
Script para corregir anotaciones de imágenes y generar las imágenes etiquetadas.
"""
import os
import json
import logging
import traceback
import glob
from flask import current_app
import sys
import time

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_roboflow_detections(raw_result):
    """
    Extrae las detecciones de la respuesta de Roboflow en varios formatos posibles.
    
    Args:
        raw_result (dict): Respuesta JSON de Roboflow
        
    Returns:
        list: Lista de detecciones en formato estandarizado
    """
    detecciones = []
    
    try:
        logger.info(f"Extrayendo detecciones de respuesta Roboflow: {raw_result.keys() if isinstance(raw_result, dict) else 'no es un diccionario'}")
        
        # Caso 1: Formato estándar de Roboflow con 'predictions' en la raíz
        if isinstance(raw_result, dict) and 'predictions' in raw_result:
            pred_list = raw_result['predictions']
            logger.info(f"Formato estándar encontrado con {len(pred_list)} predicciones")
            
            for pred in pred_list:
                if isinstance(pred, dict):
                    deteccion = {
                        'x': float(pred.get('x', 0)),
                        'y': float(pred.get('y', 0)),
                        'width': float(pred.get('width', 0)),
                        'height': float(pred.get('height', 0)),
                        'class': pred.get('class', 'unknown'),
                        'confidence': float(pred.get('confidence', 0))
                    }
                    detecciones.append(deteccion)
            
        # Caso 2: Formato alternativo con 'outputs' que contiene 'predictions'
        elif isinstance(raw_result, dict) and 'outputs' in raw_result and isinstance(raw_result['outputs'], list):
            logger.info(f"Formato con 'outputs' encontrado")
            for output in raw_result['outputs']:
                if isinstance(output, dict) and 'predictions' in output:
                    pred_list = output['predictions']
                    logger.info(f"Encontradas {len(pred_list)} predicciones en output")
                    
                    for pred in pred_list:
                        if isinstance(pred, dict):
                            deteccion = {
                                'x': float(pred.get('x', 0)),
                                'y': float(pred.get('y', 0)),
                                'width': float(pred.get('width', 0)),
                                'height': float(pred.get('height', 0)),
                                'class': pred.get('class', 'unknown'),
                                'confidence': float(pred.get('confidence', 0))
                            }
                            detecciones.append(deteccion)
        
        # Caso 3: Formato con 'output' (singular) que contiene 'predictions'
        elif isinstance(raw_result, dict) and 'output' in raw_result:
            output = raw_result['output']
            logger.info(f"Formato con 'output' singular encontrado")
            
            if isinstance(output, dict) and 'predictions' in output:
                pred_list = output['predictions']
                logger.info(f"Encontradas {len(pred_list)} predicciones en output")
                
                for pred in pred_list:
                    if isinstance(pred, dict):
                        deteccion = {
                            'x': float(pred.get('x', 0)),
                            'y': float(pred.get('y', 0)),
                            'width': float(pred.get('width', 0)),
                            'height': float(pred.get('height', 0)),
                            'class': pred.get('class', 'unknown'),
                            'confidence': float(pred.get('confidence', 0))
                        }
                        detecciones.append(deteccion)
        
        # Caso 4: La respuesta en sí es una lista de predicciones
        elif isinstance(raw_result, list):
            logger.info(f"La respuesta es una lista con {len(raw_result)} elementos")
            for pred in raw_result:
                if isinstance(pred, dict) and 'class' in pred:
                    deteccion = {
                        'x': float(pred.get('x', 0)),
                        'y': float(pred.get('y', 0)),
                        'width': float(pred.get('width', 0)),
                        'height': float(pred.get('height', 0)),
                        'class': pred.get('class', 'unknown'),
                        'confidence': float(pred.get('confidence', 0))
                    }
                    detecciones.append(deteccion)
        
        logger.info(f"Total de detecciones extraídas: {len(detecciones)}")
        return detecciones
        
    except Exception as e:
        logger.error(f"Error extrayendo detecciones: {str(e)}")
        logger.error(traceback.format_exc())
        return []

def generate_annotated_image(original_image_path, detections, output_path=None):
    """
    Genera una imagen con anotaciones (bounding boxes) basadas en las detecciones.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import os
        import time
        
        # Verificar que la imagen original existe
        if not os.path.exists(original_image_path):
            logger.error(f"Imagen original no encontrada: {original_image_path}")
            return None
        
        # Determinar ruta de salida si no se proporciona
        if not output_path:
            base_dir = os.path.dirname(original_image_path)
            base_name = os.path.basename(original_image_path)
            name, ext = os.path.splitext(base_name)
            timestamp = int(time.time())
            output_path = os.path.join(base_dir, f"{name}_annotated_{timestamp}{ext}")
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Abrir imagen original y obtener dimensiones
        img = Image.open(original_image_path)
        img_width, img_height = img.size
        logger.info(f"Dimensiones de imagen original: {img_width}x{img_height}")
        
        # Crear una copia de la imagen para dibujar
        draw = ImageDraw.Draw(img)
        
        # Ajustar factores de escala basados en el tamaño de la imagen
        base_size = max(img_width, img_height)
        scale_factor = base_size / 800.0  # Usar 800px como base para escalar
        scale_factor = max(0.8, min(scale_factor, 3.0))  # Limitar entre 0.8 y 3.0
        
        # Configurar tamaños para las etiquetas y líneas
        line_width = max(3, int(5 * scale_factor))  # Líneas más gruesas
        font_size = max(24, int(36 * scale_factor))  # Fuente más grande
        padding = max(4, int(6 * scale_factor))  # Padding más grande
        
        logger.info(f"Factores de escala - scale_factor: {scale_factor}, line_width: {line_width}, font_size: {font_size}")
        
        # Colores para las etiquetas (más brillantes para mejor contraste)
        colors = {
            'verde': (0, 255, 0),
            'maduro': (255, 165, 0),
            'sobremaduro': (255, 0, 0),
            'danio_corona': (255, 0, 255),
            'pendunculo_largo': (0, 255, 255),
            'podrido': (128, 128, 128)
        }
        
        # Intentar cargar una fuente
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            try:
                font = ImageFont.truetype("DejaVuSans.ttf", font_size)
            except:
                font = ImageFont.load_default()
        
        def draw_text_with_outline(draw, pos, text, font, text_color, outline_color, width=2):
            x, y = pos
            # Dibujar contorno
            for dx, dy in [(-width, -width), (-width, 0), (-width, width), 
                           (0, -width), (0, width), 
                           (width, -width), (width, 0), (width, width)]:
                draw.text((x+dx, y+dy), text, font=font, fill=outline_color)
            # Dibujar texto principal
            draw.text(pos, text, font=font, fill=text_color)
        
        # Dibujar cada detección
        for detection in detections:
            try:
                # Registrar la detección para depuración
                logger.info(f"Procesando detección: {detection}")
                
                # Obtener coordenadas y dimensiones
                try:
                    x = float(detection.get('x', 0))
                    y = float(detection.get('y', 0))
                    width = float(detection.get('width', 0))
                    height = float(detection.get('height', 0))
                except (ValueError, TypeError) as e:
                    logger.error(f"Error en conversión de coordenadas: {e}")
                    continue
                
                # Las coordenadas de Roboflow son absolutas y (x,y) es el centro del rectángulo
                x1 = max(0, x - width/2)
                y1 = max(0, y - height/2)
                x2 = min(img_width, x + width/2)
                y2 = min(img_height, y + height/2)
                
                logger.info(f"Bounding box: centro=({x},{y}), dimensiones=({width},{height})")
                logger.info(f"Bounding box: esquinas=({x1},{y1}), ({x2},{y2})")
                
                # Asegurar que el bounding box tenga un tamaño mínimo visible
                if (x2 - x1 < 5) or (y2 - y1 < 5):
                    logger.warning(f"Bounding box demasiado pequeño: ({x1},{y1}), ({x2},{y2}) - se expandirá")
                    # Expandir box si es muy pequeño para ser visible
                    if (x2 - x1 < 5):
                        padding_x = (5 - (x2 - x1)) / 2
                        x1 = max(0, x1 - padding_x)
                        x2 = min(img_width, x2 + padding_x)
                    if (y2 - y1 < 5):
                        padding_y = (5 - (y2 - y1)) / 2
                        y1 = max(0, y1 - padding_y)
                        y2 = min(img_height, y2 + padding_y)
                
                # Obtener clase y confianza
                detection_class = detection.get('class', '').lower()
                confidence = detection.get('confidence', 0)
                
                # Determinar color basado en la clase
                color = colors.get(detection_class, (255, 0, 0))  # Rojo por defecto
                
                # Dibujar bounding box con borde negro grueso para contraste
                outline_width = 2
                draw.rectangle([x1-outline_width, y1-outline_width, x2+outline_width, y2+outline_width], 
                               outline=(0, 0, 0), width=outline_width)
                draw.rectangle([x1, y1, x2, y2], outline=color, width=line_width)
                
                # Preparar texto para la etiqueta
                text = f"{detection_class} {confidence:.2f}"
                
                # Calcular tamaño del texto para el fondo
                text_bbox = draw.textbbox((0, 0), text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # Posicionar etiqueta arriba del bounding box si hay espacio
                label_x = x1 + ((x2 - x1) / 2) - (text_width / 2)
                label_y = y1 - text_height - padding
                
                # Si no hay espacio arriba, intentar otras posiciones
                if label_y < 0:
                    if (y2 - y1) > text_height + 2 * padding:  # Espacio dentro del bounding box
                        label_y = y1 + padding
                    else:  # Ponerla debajo
                        label_y = y2 + padding
                
                # Asegurar que la etiqueta no se salga de la imagen
                label_x = max(0, min(label_x, img_width - text_width - padding))
                label_y = max(0, min(label_y, img_height - text_height - padding))
                
                # Dibujar fondo de la etiqueta con borde negro para contraste
                draw.rectangle([label_x-5, label_y-5, 
                                label_x + text_width + padding + 5, 
                                label_y + text_height + padding + 5], 
                                fill=(0, 0, 0))
                draw.rectangle([label_x-2, label_y-2, 
                                label_x + text_width + padding + 2, 
                                label_y + text_height + padding + 2], 
                                fill=color)
                
                # Dibujar texto con borde negro para contraste
                draw_text_with_outline(draw, 
                                       (label_x + padding/2, label_y + padding/2), 
                                       text, 
                                       font=font, 
                                       text_color=(255, 255, 255), 
                                       outline_color=(0, 0, 0), 
                                       width=2)
                
            except Exception as e:
                logger.error(f"Error procesando detección: {str(e)}")
                logger.error(traceback.format_exc())
                continue
        
        # Guardar imagen procesada
        img.save(output_path, quality=95)
        logger.info(f"Imagen procesada guardada en: {output_path}")
        
        return output_path
    
    except Exception as e:
        logger.error(f"Error generando imagen anotada: {str(e)}")
        logger.error(traceback.format_exc())
        return None

def process_guia(guia_id, static_folder):
    """
    Procesa todas las imágenes de una guía y genera las imágenes etiquetadas.
    
    Args:
        guia_id (str): ID de la guía
        static_folder (str): Ruta al directorio static de la aplicación
        
    Returns:
        dict: Estadísticas de procesamiento
    """
    try:
        logger.info(f"Procesando guía: {guia_id}")
        
        # Buscar el archivo JSON de la clasificación
        json_path = os.path.join(static_folder, 'clasificaciones', f'clasificacion_{guia_id}.json')
        
        if not os.path.exists(json_path):
            logger.error(f"No se encontró el archivo de clasificación: {json_path}")
            return {"error": "Archivo de clasificación no encontrado"}
        
        # Leer el archivo JSON
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        logger.info(f"Datos del JSON: {clasificacion_data.keys()}")
        
        # Obtener las fotos
        fotos = clasificacion_data.get('fotos', [])
        
        if not fotos:
            logger.error(f"No hay fotos en la clasificación")
            return {"error": "No hay fotos en la clasificación"}
        
        # Obtener los resultados por foto
        resultados_por_foto = clasificacion_data.get('resultados_por_foto', {})
        
        if not resultados_por_foto:
            logger.error(f"No hay resultados por foto en la clasificación")
            return {"error": "No hay resultados por foto"}
        
        # Estadísticas
        stats = {
            'total_fotos': len(fotos),
            'fotos_procesadas': 0,
            'total_detecciones': 0,
            'imagenes_generadas': 0,
            'errores': 0
        }
        
        # Procesar cada foto
        for idx, foto_path in enumerate(fotos, 1):
            if '_resized.' in foto_path or '_annotated' in foto_path:
                continue  # Saltar versiones redimensionadas o ya anotadas
                
            str_idx = str(idx)
            if str_idx not in resultados_por_foto:
                logger.warning(f"No hay resultados para la foto {idx}")
                continue
            
            resultado_foto = resultados_por_foto[str_idx]
            
            # Obtener detecciones directamente o desde raw_result
            detecciones = resultado_foto.get('detecciones', [])
            
            if not detecciones and 'raw_result' in resultado_foto:
                raw_result = resultado_foto['raw_result']
                detecciones = extract_roboflow_detections(raw_result)
                logger.info(f"Extraídas {len(detecciones)} detecciones del raw_result para foto {idx}")
                
                if detecciones:
                    resultado_foto['detecciones'] = detecciones
            
            if not detecciones:
                logger.warning(f"No hay detecciones para la foto {idx}")
                continue
            
            # Generar imagen etiquetada
            try:
                logger.info(f"Generando imagen etiquetada para foto {idx}")
                output_path = generate_annotated_image(foto_path, detecciones)
                
                if output_path:
                    logger.info(f"Imagen etiquetada generada: {output_path}")
                    
                    # Actualizar el resultado con la referencia a la imagen
                    if 'imagenes_procesadas' not in resultado_foto:
                        resultado_foto['imagenes_procesadas'] = []
                    resultado_foto['imagenes_procesadas'].append(output_path)
                    
                    # Actualizar estadísticas
                    stats['fotos_procesadas'] += 1
                    stats['total_detecciones'] += len(detecciones)
                    stats['imagenes_generadas'] += 1
                else:
                    logger.error(f"Error generando imagen etiquetada para foto {idx}")
                    stats['errores'] += 1
            except Exception as e:
                logger.error(f"Error procesando foto {idx}: {str(e)}")
                logger.error(traceback.format_exc())
                stats['errores'] += 1
        
        # Guardar los cambios
        try:
            clasificacion_data['resultados_por_foto'] = resultados_por_foto
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
            logger.info(f"Archivo de clasificación actualizado: {json_path}")
        except Exception as e:
            logger.error(f"Error guardando cambios en el archivo JSON: {str(e)}")
            logger.error(traceback.format_exc())
            stats['errores'] += 1
        
        return stats
    
    except Exception as e:
        logger.error(f"Error procesando guía {guia_id}: {str(e)}")
        logger.error(traceback.format_exc())
        return {"error": str(e)}

def main():
    """
    Función principal para ejecutar el script desde línea de comandos.
    """
    if len(sys.argv) < 3:
        print("Uso: python fix_annotations.py <guia_id> <static_folder>")
        return
    
    guia_id = sys.argv[1]
    static_folder = sys.argv[2]
    
    logger.info(f"Iniciando procesamiento para guía {guia_id}")
    stats = process_guia(guia_id, static_folder)
    logger.info(f"Procesamiento completado: {stats}")

if __name__ == "__main__":
    main() 