#!/usr/bin/env python
"""
Script para probar la función de generación de imágenes anotadas directamente.
"""
import os
import sys
import random
import base64
from PIL import Image

# Añadir el directorio raíz del proyecto al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar la función que queremos probar y la aplicación Flask
from app.blueprints.clasificacion.generate_annotated_image import generate_annotated_image
from app import create_app

def test_generate_annotated_image():
    """Probar la función de generación de imágenes anotadas"""
    
    # Crear una aplicación Flask y un contexto de aplicación
    app = create_app()
    with app.app_context():
        # Directorio donde se encuentran las imágenes a anotar
        photos_dir = "static/uploads/fotos/0150076A_20250312_155241"
        
        # Buscar archivos de imagen en el directorio
        image_files = [
            os.path.join(photos_dir, f) for f in os.listdir(photos_dir) 
            if f.endswith('.jpg') and not f.endswith('_annotated.jpg')
        ]
        
        if not image_files:
            print("No se encontraron imágenes para anotar.")
            return
        
        # Seleccionar una imagen aleatoria para la prueba
        image_path = random.choice(image_files)
        print(f"Usando imagen: {image_path}")
        
        # Crear detecciones de prueba simuladas
        detections = [
            {
                'x': 0.3, 'y': 0.3, 'width': 0.2, 'height': 0.2,
                'class': 'verde', 'confidence': 0.95
            },
            {
                'x': 0.7, 'y': 0.4, 'width': 0.15, 'height': 0.15,
                'class': 'maduro', 'confidence': 0.87
            },
            {
                'x': 0.5, 'y': 0.6, 'width': 0.25, 'height': 0.2,
                'class': 'sobremaduro', 'confidence': 0.82
            },
            {
                'x': 0.2, 'y': 0.7, 'width': 0.18, 'height': 0.18,
                'class': 'danio_corona', 'confidence': 0.78
            },
            {
                'x': 0.8, 'y': 0.2, 'width': 0.1, 'height': 0.3,
                'class': 'pendunculo_largo', 'confidence': 0.91
            }
        ]
        
        # Ruta para la imagen anotada
        output_path = "test_images/test_annotated_image.jpg"
        
        # Generar la imagen anotada
        result_path = generate_annotated_image(image_path, detections, output_path)
        
        if result_path:
            print(f"Imagen anotada generada exitosamente: {result_path}")
            
            # Mostrar información sobre la imagen generada
            with Image.open(output_path) as img:
                width, height = img.size
                print(f"Tamaño de la imagen anotada: {width}x{height}")
                
            # Mostrar tamaño del archivo
            file_size = os.path.getsize(output_path) / (1024 * 1024)  # Convertir a MB
            print(f"Tamaño del archivo: {file_size:.2f} MB")
            
            print("\nPrueba completada con éxito.")
        else:
            print("Error al generar la imagen anotada.")

if __name__ == "__main__":
    test_generate_annotated_image() 