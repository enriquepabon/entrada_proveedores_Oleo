import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuración del logger
logger = logging.getLogger(__name__)

# Nombre del archivo de credenciales (asumiendo que está en la raíz del proyecto)
# Se podría pasar como variable de entorno o configuración de la app para mayor flexibilidad.
CREDENTIALS_FILENAME = 'google_sheets_credentials_09052025.json'
# ID del Spreadsheet (se puede extraer de la URL: https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit)
SPREADSHEET_ID = '14uoRvBmmgQ3F_bM9mhToMpHUG9oMYEtcwbG6ejCgUfA' 
# Nombre de la hoja específica
SHEET_NAME = 'Graneles'

# Alcances necesarios para la API de Google Sheets (solo lectura en este caso)
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

def get_sheets_service():
    """Autentica y devuelve un objeto de servicio para interactuar con Google Sheets API."""
    creds = None
    credentials_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), CREDENTIALS_FILENAME)
    logger.info(f"Intentando cargar credenciales desde: {credentials_path}")

    if not os.path.exists(credentials_path):
        logger.error(f"Archivo de credenciales no encontrado en: {credentials_path}")
        raise FileNotFoundError(f"Archivo de credenciales no encontrado: {credentials_path}")

    try:
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=creds)
        logger.info("Servicio de Google Sheets autenticado y construido exitosamente.")
        return service
    except Exception as e:
        logger.error(f"Error al autenticar o construir el servicio de Google Sheets: {e}")
        raise

def get_all_granel_records():
    """Obtiene todos los registros de la hoja 'Graneles'."""
    try:
        service = get_sheets_service()
        sheet = service.spreadsheets()
        # Se asume que la primera fila contiene los encabezados
        result = sheet.values().get(spreadsheetId=SPREADSHEET_ID,
                                    range=f"{SHEET_NAME}!A:H").execute() # Leer hasta la columna H (Destino)
        values = result.get('values', [])
        
        if not values:
            logger.info(f"No se encontraron datos en la hoja {SHEET_NAME}.")
            return []
        else:
            # La primera fila son los encabezados, el resto son datos.
            # Convertimos cada fila de datos en un diccionario para facilitar el acceso.
            headers = values[0]
            data_rows = values[1:]
            records = [dict(zip(headers, row)) for row in data_rows]
            logger.info(f"Se recuperaron {len(records)} registros de la hoja {SHEET_NAME}.")
            return records
    except HttpError as err:
        logger.error(f"Error HTTP al obtener datos de Google Sheets: {err}")
        raise
    except Exception as e:
        logger.error(f"Error inesperado al obtener todos los registros de granel: {e}")
        raise

def find_granel_record_by_placa(placa_to_find):
    """
    Busca un registro en la hoja 'Graneles' por la columna 'Placa'.

    Args:
        placa_to_find (str): La placa a buscar.

    Returns:
        dict: El registro encontrado (como diccionario) o None si no se encuentra.
    """
    if not placa_to_find:
        logger.warning("Se intentó buscar una placa vacía.")
        return None
        
    placa_to_find = placa_to_find.strip().upper() # Normalizar la placa buscada

    try:
        all_records = get_all_granel_records()
        if not all_records:
            return None

        for record in all_records:
            # Asegurarse de que la columna 'Placa' exista en el registro y no esté vacía
            placa_in_sheet = record.get('Placa')
            if placa_in_sheet:
                if placa_in_sheet.strip().upper() == placa_to_find:
                    logger.info(f"Registro encontrado para la placa '{placa_to_find}': {record}")
                    return record
        
        logger.info(f"No se encontró ningún registro para la placa '{placa_to_find}'.")
        return None
    except Exception as e:
        logger.error(f"Error al buscar registro por placa '{placa_to_find}': {e}")
        # No relanzar la excepción aquí directamente si queremos que la app continúe (ej. para ingreso manual)
        # pero sí es bueno loguearla. Dependerá de cómo se maneje en la ruta.
        return None

# Ejemplo de uso (se puede comentar o eliminar para producción)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    # Prueba de autenticación
    try:
        get_sheets_service()
    except Exception as e:
        logger.error(f"Fallo en prueba de autenticación: {e}")

    # Prueba de obtener todos los registros
    # try:
    #     todos_los_registros = get_all_granel_records()
    #     if todos_los_registros:
    #         logger.info(f"Primer registro obtenido: {todos_los_registros[0]}")
    # except Exception as e:
    #     logger.error(f"Fallo al obtener todos los registros: {e}")

    # Prueba de buscar una placa (reemplaza 'LUM356' con una placa existente o no existente para probar)
    # placa_ejemplo_existente = 'LUM356'
    # placa_ejemplo_no_existente = 'XYZ123'
    
    # try:
    #     registro = find_granel_record_by_placa(placa_ejemplo_existente)
    #     if registro:
    #         logger.info(f"Encontrado para {placa_ejemplo_existente}: {registro}")
    #     else:
    #         logger.info(f"NO encontrado para {placa_ejemplo_existente}")
            
    #     registro_no = find_granel_record_by_placa(placa_ejemplo_no_existente)
    #     if registro_no:
    #         logger.info(f"Encontrado para {placa_ejemplo_no_existente}: {registro_no}")
    #     else:
    #         logger.info(f"NO encontrado para {placa_ejemplo_no_existente}")
            
    # except Exception as e:
    #     logger.error(f"Fallo en la búsqueda por placa: {e}") 