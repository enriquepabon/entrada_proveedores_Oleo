import requests
import logging
import json
from datetime import datetime

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_knowledge_update():
    """
    Prueba la actualización completa de la base de conocimiento en el asistente
    """
    url = 'http://localhost:5002/update-assistant-knowledge'
    
    try:
        logger.info("Iniciando actualización del asistente")
        response = requests.post(url)  # Cambiado a POST
        
        logger.info(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("Actualización del asistente exitosa:")
            logger.info(json.dumps(result, indent=2))
            
            # Guardar resultado en archivo de log
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_filename = f'assistant_update_log_{timestamp}.json'
            
            with open(log_filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'timestamp': timestamp,
                    'status': 'success',
                    'response': result
                }, f, indent=2)
                
            logger.info(f"Log guardado en: {log_filename}")
        else:
            logger.error(f"Error en la actualización: {response.text}")
            
    except Exception as e:
        logger.error(f"Error en la prueba: {str(e)}")
        logger.exception("Detalles del error:")

if __name__ == "__main__":
    test_knowledge_update()