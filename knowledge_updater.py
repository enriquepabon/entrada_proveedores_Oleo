# knowledge_updater.py

from flask import Blueprint, jsonify
import os
import json
import logging
from datetime import datetime
from openai import OpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.oauth2 import service_account
from dotenv import load_dotenv

# Configurar logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv('API_Keys.env')

# Crear Blueprint
knowledge_bp = Blueprint('knowledge', __name__)

# Configuraciones
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ASSISTANT_ID = os.getenv('ASSISTANT_ID')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
SERVICE_ACCOUNT_FILE = 'config/service-account.json'

# Inicializar clientes
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Configurar Google Sheets
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
try:
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    sheets_service = build('sheets', 'v4', credentials=creds)
except Exception as e:
    logger.error(f"Error inicializando Google Sheets: {str(e)}")
    sheets_service = None

def cleanup_old_files():
    """
    Limpia archivos antiguos del asistente
    """
    try:
        # Listar archivos actuales
        files = openai_client.files.list()
        
        # Ordenar por fecha de creación (el más reciente primero)
        files_sorted = sorted(files.data, key=lambda x: x.created_at, reverse=True)
        
        # Mantener solo el archivo más reciente
        if len(files_sorted) > 1:
            for file in files_sorted[1:]:
                try:
                    openai_client.files.delete(file.id)
                    logger.info(f"Archivo eliminado: {file.id}")
                except Exception as e:
                    logger.error(f"Error eliminando archivo {file.id}: {str(e)}")
                    
    except Exception as e:
        logger.error(f"Error en limpieza de archivos: {str(e)}")

def get_sheet_data():
    """
    Obtiene los datos actualizados de todas las hojas relevantes
    """
    if not sheets_service:
        logger.error("Servicio de Google Sheets no inicializado")
        return None
        
    try:
        # Lista de hojas específicas a monitorear
        SHEETS_TO_MONITOR = [
            {'name': 'Asociados', 'range': 'A:Z', 'tipo': 'asociado'},
            {'name': 'Saf', 'range': 'A:Z', 'tipo': 'saf'},
            {'name': 'Pepa', 'range': 'A:Z', 'tipo': 'pepa'},
        ]
        
        all_data = []
        
        for sheet in SHEETS_TO_MONITOR:
            try:
                # Construir el rango usando el método correcto
                range_name = f"'{sheet['name']}'!{sheet['range']}"
                
                result = sheets_service.spreadsheets().values().get(
                    spreadsheetId=SPREADSHEET_ID,
                    range=range_name
                ).execute()
                
                values = result.get('values', [])
                if not values:
                    logger.warning(f'No data found in sheet: {sheet["name"]}')
                    continue
                    
                headers = [str(col).strip().lower() for col in values[0]]
                
                # Log de headers para debugging
                logger.info(f"Headers in {sheet['name']}: {headers}")
                
                # Mapeo de nombres de columnas
                column_mapping = {
                    'código': ['código', 'id', 'identificacion'],
                    'nombre': ['nombres', 'nombre 1', 'razon social'],
                    'placa': ['vehículo', 'matrícula']
                }
                
                # Obtener indices de columnas requeridas
                column_indices = {}
                for required_col, alternatives in column_mapping.items():
                    for alt_col in alternatives:
                        if alt_col.lower() in headers:
                            column_indices[required_col] = headers.index(alt_col.lower())
                            break
                            
                # Procesar datos
                for row in values[1:]:
                    if len(row) > max(column_indices.values()):
                        data_dict = {
                            'codigo': row[column_indices['código']] if 'código' in column_indices else '',
                            'nombre': row[column_indices['nombre']] if 'nombre' in column_indices else '',
                            'placa': row[column_indices['placa']] if 'placa' in column_indices else '',
                            'tipo_proveedor': sheet["tipo"]
                        }
                        
                        # Solo agregar si al menos uno de los campos tiene valor
                        if any(data_dict.values()):
                            all_data.append(data_dict)
                
                logger.info(f"Procesados {len(values)-1} registros de {sheet['name']}")
                
            except Exception as e:
                logger.error(f"Error procesando hoja {sheet['name']}: {str(e)}")
                continue
                
        if not all_data:
            logger.error("No se encontraron datos válidos en ninguna hoja")
            return None
            
        logger.info(f"Total de registros procesados: {len(all_data)}")
        return all_data
        
    except Exception as e:
        logger.error(f"Error obteniendo datos de hoja: {str(e)}")
        return None

def format_assistant_data(data):
    """
    Formatea los datos para el asistente
    """
    if not data:
        return None
        
    formatted_data = {
        "proveedores": [
            {
                "codigo": row.get('codigo', ''),
                "nombre": row.get('nombre', ''),
                "placa": row.get('placa', ''),
                "tipo_proveedor": row.get('tipo_proveedor', '')
            }
            for row in data
        ],
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
    
    return formatted_data

@knowledge_bp.route('/update-assistant-knowledge', methods=['POST'])
def update_assistant_knowledge():
    """
    Actualiza la base de conocimiento del asistente
    """
    try:
        # Limpiar archivos antiguos
        cleanup_old_files()
        
        # Obtener datos actualizados de Google Sheets
        sheet_data = get_sheet_data()
        
        if not sheet_data:
            return jsonify({
                'success': False,
                'message': 'No se pudieron obtener los datos de Google Sheets'
            }), 500

        # Formatear datos para el asistente
        formatted_data = format_assistant_data(sheet_data)
        
        # Crear archivo temporal
        temp_dir = 'temp'
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, 'temp_base_maestra.json')
        
        with open(temp_file_path, 'w', encoding='utf-8') as f:
            json.dump(formatted_data, f, ensure_ascii=False, indent=2)

        # Crear archivo en OpenAI
        with open(temp_file_path, 'rb') as f:
            file = openai_client.files.create(
                file=f,
                purpose='assistants'
            )

        # Actualizar el asistente
        assistant = openai_client.beta.assistants.update(
            assistant_id=ASSISTANT_ID,
            file_ids=[file.id]
        )

        # Registro de actualización
        update_log = {
            'timestamp': datetime.now().isoformat(),
            'records_count': len(sheet_data),
            'file_id': file.id,
            'assistant_id': assistant.id
        }
        
        log_dir = 'logs'
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, 'updates_log.json'), 'a') as f:
            f.write(json.dumps(update_log) + '\n')

        logger.info(f"Base de conocimiento actualizada: {len(sheet_data)} registros")
        
        # Limpiar archivo temporal
        os.remove(temp_file_path)
        
        return jsonify({
            'success': True,
            'message': 'Base de conocimiento actualizada correctamente',
            'records': len(sheet_data),
            'assistant_id': assistant.id,
            'file_id': file.id
        })
        
    except Exception as e:
        logger.error(f"Error actualizando base de conocimiento: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

# Ruta de prueba opcional
@knowledge_bp.route('/test-update', methods=['GET'])
def test_update():
    """
    Ruta de prueba para actualizar la base de conocimiento
    """
    try:
        logger.info("Iniciando prueba de actualización")
        
        # Obtener datos de hojas
        sheet_data = get_sheet_data()
        
        if not sheet_data:
            return jsonify({
                'success': False,
                'message': 'No se pudieron obtener datos de Google Sheets'
            }), 500
        
        # Formatear datos
        formatted_data = format_assistant_data(sheet_data)
        
        return jsonify({
            'success': True,
            'message': 'Prueba de actualización completada',
            'total_records': formatted_data['metadata']['total_records'],
            'records_by_type': formatted_data['metadata']['records_by_type']
        })
    
    except Exception as e:
        logger.error(f"Error en prueba de actualización: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500