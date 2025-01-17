# parser.py

# parser.py

import re
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# En parser.py

def parse_markdown_response(response_text):
    """
    Parsea una respuesta en formato markdown que incluye una tabla y nota de validación.
    """
    parsed_data = {
        'table_data': [],
        'nota': ''
    }
    
    try:
        # Separar la tabla de la nota
        parts = response_text.split('**Nota de Validación:**')
        table_text = parts[0].strip()
        
        # Procesar tabla
        rows = table_text.split('\n')
        header_found = False
        
        for row in rows:
            row = row.strip()
            if not row or '---' in row:
                continue
                
            if '|' not in row:
                continue
                
            # Procesar fila de la tabla
            columns = [col.strip() for col in row.split('|') if col.strip()]
            
            if not header_found:
                if 'Campo' in columns[0]:
                    header_found = True
                continue
            
            if len(columns) >= 3:
                # Asegurarnos de que los datos se guarden correctamente
                entry = {
                    'campo': columns[0].strip(),
                    'original': columns[1].strip(),
                    'sugerido': columns[2].strip()
                }
                logger.debug(f"Agregando entrada a table_data: {entry}")
                parsed_data['table_data'].append(entry)
        
        # Extraer nota de validación
        if len(parts) > 1:
            parsed_data['nota'] = parts[1].strip()
        
        logger.debug(f"Datos parseados completos: {parsed_data}")
        
    except Exception as e:
        logger.error(f"Error parseando respuesta: {str(e)}")
        logger.error(f"Texto recibido: {response_text}")
        
    return parsed_data