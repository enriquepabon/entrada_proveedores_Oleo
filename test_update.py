import requests
import logging
import json
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_knowledge_update():
    """
    Prueba la actualización de la base de conocimiento
    """
    url = 'http://localhost:5002/test-update'
    
    try:
        logger.info("Iniciando prueba de actualización")
        response = requests.get(url)
        
        logger.info(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("Actualización exitosa:")
            logger.info(json.dumps(result, indent=2))
            
            # Guardar resultado en archivo de log
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            with open(f'update_log_{timestamp}.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
        else:
            logger.error(f"Error en la actualización: {response.text}")
            
    except Exception as e:
        logger.error(f"Error en la prueba: {str(e)}")

if __name__ == "__main__":
    test_knowledge_update()