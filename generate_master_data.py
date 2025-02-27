#!/usr/bin/env python3

import os
import json
import logging
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv('API_Keys.env')

# Configuraciones
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_FILE = 'config/service-account.json'
HISTORY_FOLDER = 'data_history'
REQUIRED_FIELDS = ['tratamiento', 'acreedor', 'nombre']

def setup_google_sheets():
    """
    Configura y retorna el servicio de Google Sheets
    """
    try:
        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=scopes)
        service = build('sheets', 'v4', credentials=creds)
        return service
    except Exception as e:
        logger.error(f"Error configurando Google Sheets: {str(e)}")
        return None

def get_sheet_data(service):
    """
    Obtiene los datos de todas las hojas relevantes
    """
    if not service:
        logger.error("Servicio de Google Sheets no inicializado")
        return None
        
    try:
        sheets_to_monitor = [
            {'name': 'Asociados', 'range': 'A:Z', 'tipo': 'asociado'},
            {'name': 'Saf', 'range': 'A:Z', 'tipo': 'saf'},
            {'name': 'Pepa', 'range': 'A:Z', 'tipo': 'pepa'},
        ]
        
        all_data = []
        
        for sheet in sheets_to_monitor:
            try:
                range_name = f"'{sheet['name']}'!{sheet['range']}"
                result = service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                if not values:
                    logger.warning(f'No data found in sheet: {sheet["name"]}')
                    continue
                    
                headers = [str(col).strip().lower() for col in values[0]]
                logger.info(f"Headers in {sheet['name']}: {headers}")
                
                # Mapeo de nombres de columnas
                column_mapping = {
                    'tratamiento': ['tratamiento'],
                    'acreedor': ['acreedor'],
                    'nombre': ['nombre 1']
                }
                
                column_indices = {}
                for required_col, alternatives in column_mapping.items():
                    for alt_col in alternatives:
                        if alt_col.lower() in headers:
                            column_indices[required_col] = headers.index(alt_col.lower())
                            break
                
                for row in values[1:]:
                    if len(row) > max(column_indices.values()):
                        data_dict = {
                            'tratamiento': row[column_indices['tratamiento']] if 'tratamiento' in column_indices else '',
                            'acreedor': row[column_indices['acreedor']] if 'acreedor' in column_indices else '',
                            'nombre': row[column_indices['nombre']] if 'nombre' in column_indices else '',
                            'tipo_proveedor': sheet["tipo"]
                        }
                        
                        if any(data_dict.values()):
                            all_data.append(data_dict)
                
                logger.info(f"Procesados {len(values)-1} registros de {sheet['name']}")
                
            except Exception as e:
                logger.error(f"Error procesando hoja {sheet['name']}: {str(e)}")
                continue
                
        return all_data
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de hojas: {str(e)}")
        return None

def validate_data(data):
    """
    Valida y filtra los datos, removiendo registros inválidos
    """
    if not data:
        logger.error("No hay datos para validar")
        return None
        
    valid_data = []
    invalid_count = 0
    
    for item in data:
        missing_fields = [field for field in REQUIRED_FIELDS if not item.get(field)]
        if missing_fields:
            invalid_count += 1
            logger.warning(f"Registro inválido (campos faltantes: {missing_fields}): {item}")
            continue
        valid_data.append(item)
    
    logger.info(f"Total registros procesados: {len(data)}")
    logger.info(f"Registros válidos: {len(valid_data)}")
    logger.info(f"Registros inválidos: {invalid_count}")
    
    if not valid_data:
        logger.error("No hay registros válidos después de la validación")
        return None
        
    return valid_data

def format_master_data(data):
    """
    Formatea los datos en la estructura requerida
    """
    return {
        "proveedores": data,
        "metadata": {
            "total_records": len(data),
            "last_update": datetime.now().isoformat(),
            "records_by_type": {
                "asociado": len([r for r in data if r.get('tipo_proveedor') == 'asociado']),
                "saf": len([r for r in data if r.get('tipo_proveedor') == 'saf']),
                "pepa": len([r for r in data if r.get('tipo_proveedor') == 'pepa'])
            }
        }
    }

def save_master_data(data):
    """
    Guarda los datos en un archivo JSON con timestamp
    """
    try:
        # Crear carpeta de historial si no existe
        os.makedirs(HISTORY_FOLDER, exist_ok=True)
        
        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"Maestra_de_Datos_actualizada_al_{timestamp}.json"
        filepath = os.path.join(HISTORY_FOLDER, filename)
        
        # Guardar archivo
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Archivo guardado exitosamente: {filepath}")
        return filepath
        
    except Exception as e:
        logger.error(f"Error guardando archivo: {str(e)}")
        return None

def main():
    """
    Función principal que ejecuta todo el proceso
    """
    try:
        logger.info("Iniciando proceso de generación de datos maestros")
        
        # Configurar Google Sheets
        service = setup_google_sheets()
        if not service:
            return
        
        # Obtener datos
        raw_data = get_sheet_data(service)
        if not raw_data:
            return
            
        # Validar y filtrar datos
        valid_data = validate_data(raw_data)
        if not valid_data:
            logger.error("No se encontraron datos válidos para procesar")
            return
            
        # Formatear datos
        master_data = format_master_data(valid_data)
        
        # Guardar archivo
        saved_file = save_master_data(master_data)
        if saved_file:
            logger.info("Proceso completado exitosamente")
            logger.info(f"Total de registros válidos procesados: {len(valid_data)}")
            logger.info(f"Archivo guardado en: {saved_file}")
        
    except Exception as e:
        logger.error(f"Error en el proceso: {str(e)}")

if __name__ == "__main__":
    main() 