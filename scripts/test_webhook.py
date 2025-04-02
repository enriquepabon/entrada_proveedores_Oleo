#!/usr/bin/env python3
"""
Script para probar el webhook directamente.
"""

import os
import sys
import requests
import logging
import argparse
from pathlib import Path

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URL del webhook
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"

def test_webhook(image_path):
    """
    Prueba el webhook enviando una imagen directamente.
    
    Args:
        image_path: Ruta a la imagen a enviar
    
    Returns:
        La respuesta del webhook
    """
    if not os.path.exists(image_path):
        logger.error(f"La imagen {image_path} no existe")
        return None
    
    try:
        logger.info(f"Enviando imagen {image_path} al webhook {PROCESS_WEBHOOK_URL}")
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f, 'multipart/form-data')}
            response = requests.post(PROCESS_WEBHOOK_URL, files=files, timeout=30)
        
        logger.info(f"Respuesta del webhook: Status {response.status_code}")
        logger.info(f"Content-Type: {response.headers.get('Content-Type')}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return None
        
        logger.info(f"Respuesta del webhook: {response.text[:200]}...")
        return response.text
    
    except Exception as e:
        logger.error(f"Error al enviar la imagen al webhook: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Prueba el webhook enviando una imagen directamente')
    parser.add_argument('image_path', help='Ruta a la imagen a enviar')
    args = parser.parse_args()
    
    response = test_webhook(args.image_path)
    
    if response:
        logger.info("Webhook funcionando correctamente")
        # Guardar la respuesta en un archivo
        output_file = f"webhook_response_{Path(args.image_path).stem}.txt"
        with open(output_file, 'w') as f:
            f.write(response)
        logger.info(f"Respuesta guardada en {output_file}")
    else:
        logger.error("Error al probar el webhook")
        sys.exit(1)

if __name__ == "__main__":
    main() 