import os
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from flask import current_app

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
    # Construir la ruta al archivo de credenciales usando BASE_DIR desde la configuración de la app
    if not current_app:
        logger.error("No se puede acceder a current_app. ¿Está la función fuera de un contexto de aplicación?")
        # Como fallback, intentar la ruta original si no hay contexto de app (ej. al correr el script directamente)
        # Esto puede no ser ideal para producción si el script se ejecuta fuera de Flask.
        base_dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        logger.warning(f"Usando fallback para BASE_DIR: {base_dir_path}")
    else:
        base_dir_path = current_app.config.get('BASE_DIR')
        if not base_dir_path:
            logger.error("BASE_DIR no está configurado en current_app.config.")
            # Fallback a la ruta original si BASE_DIR no está en la config
            base_dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            logger.warning(f"Usando fallback para BASE_DIR (no encontrado en config): {base_dir_path}")

    credentials_path = os.path.join(base_dir_path, CREDENTIALS_FILENAME)
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

def find_granel_record_by_placa(placa_to_find, fecha_a_buscar=None):
    """
    Busca un registro en la hoja 'Graneles' por la columna 'Placa' y opcionalmente por 'Fecha'.

    Args:
        placa_to_find (str): La placa a buscar.
        fecha_a_buscar (str, optional): La fecha a buscar en formato 'dd/mm/aaaa'. Defaults to None.

    Returns:
        dict: El registro encontrado (como diccionario) o None si no se encuentra.
    """
    if not placa_to_find:
        logger.warning("Se intentó buscar una placa vacía.")
        return None
        
    placa_to_find = placa_to_find.strip().upper() # Normalizar la placa buscada
    if fecha_a_buscar:
        logger.info(f"Buscando placa en Google Sheets: {placa_to_find} para la fecha: {fecha_a_buscar}")
    else:
        logger.info(f"Buscando placa en Google Sheets: {placa_to_find} (sin fecha específica)")

    try:
        all_records = get_all_granel_records()
        if not all_records:
            return None

        for record in all_records:
            placa_in_sheet = record.get('Placa')
            if placa_in_sheet and placa_in_sheet.strip().upper() == placa_to_find:
                # Si se encontró la placa, verificar la fecha si fue proporcionada
                if fecha_a_buscar:
                    fecha_in_sheet = record.get('Fecha') # Asumiendo que la columna se llama 'Fecha'
                    if fecha_in_sheet and fecha_in_sheet == fecha_a_buscar:
                        logger.info(f"Registro encontrado para la placa '{placa_to_find}' y fecha '{fecha_a_buscar}': {record}")
                        return record
                    # Si la fecha fue proporcionada pero no coincide, continuar buscando (podría haber otra entrada con la misma placa en otra fecha)
                else:
                    # Si no se proporcionó fecha, devolver el primer match de placa
                    logger.info(f"Registro encontrado para la placa '{placa_to_find}' (sin filtro de fecha): {record}")
                    return record
        
        if fecha_a_buscar:
            logger.info(f"No se encontró ningún registro para la placa '{placa_to_find}' en la fecha '{fecha_a_buscar}'.")
        else:
            logger.info(f"No se encontró ningún registro para la placa '{placa_to_find}'.")
        return None
    except Exception as e:
        if fecha_a_buscar:
            logger.error(f"Error al buscar registro por placa '{placa_to_find}' y fecha '{fecha_a_buscar}': {e}")
        else:
            logger.error(f"Error al buscar registro por placa '{placa_to_find}': {e}")
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