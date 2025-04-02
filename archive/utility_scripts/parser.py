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
    También maneja respuestas en formato de texto plano.
    """
    parsed_data = {
        'table_data': [],
        'nota': '',
        'acarreo': '',
        'cargo': '',
        'descripcion': ''
    }
    
    if not response_text or not isinstance(response_text, str):
        logger.error(f"Respuesta inválida: {response_text}")
        return parsed_data
    
    try:
        # Registrar la respuesta completa para debugging
        logger.debug(f"Parseando respuesta: {response_text[:200]}...")
        
        # Verificar si la respuesta contiene una tabla (formato markdown)
        if '|' in response_text and ('Campo' in response_text or 'Información Original' in response_text):
            # Es una respuesta con formato de tabla
            
            # Extraer valores para Se Acarreó y Se Cargó
            acarreo_match = re.search(r"Se Acarreó:\s*([^\n|]*)", response_text, re.IGNORECASE)
            if acarreo_match:
                parsed_data['acarreo'] = acarreo_match.group(1).strip()
            
            cargo_match = re.search(r"Se Cargó:\s*([^\n|]*)", response_text, re.IGNORECASE)
            if cargo_match:
                parsed_data['cargo'] = cargo_match.group(1).strip()
            
            # Separar la tabla de la nota - busca tanto "Nota de Validación:" como "Nota:"
            parts = None
            if "Nota de Validación:" in response_text:
                parts = response_text.split("Nota de Validación:")
            elif "**Nota de Validación:**" in response_text:
                parts = response_text.split("**Nota de Validación:**")
            elif "Nota:" in response_text:
                parts = response_text.split("Nota:")
            else:
                parts = [response_text, ""]
                logger.warning("No se encontró sección de nota en la respuesta")
            
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
                # Limpiar la nota de cualquier formato markdown adicional
                nota = parts[1].strip()
                # Eliminar "Status: 200" o líneas similares al final si existen
                if "Status:" in nota:
                    nota = nota.split("Status:")[0].strip()
                parsed_data['nota'] = nota
            
            # Verificar si se encontraron datos en la tabla
            if not parsed_data['table_data']:
                logger.warning("No se encontraron datos en la tabla de la respuesta")
        else:
            # Es una respuesta en formato de texto plano (descripción)
            logger.info("Respuesta en formato de texto plano (descripción)")
            parsed_data['descripcion'] = response_text.strip()
            parsed_data['nota'] = "La imagen no contiene un tiquete válido. Se muestra una descripción general."
        
        logger.debug(f"Datos parseados completos: {parsed_data}")
        
    except Exception as e:
        logger.error(f"Error parseando respuesta: {str(e)}")
        logger.error(f"Texto recibido: {response_text}")
        
    return parsed_data