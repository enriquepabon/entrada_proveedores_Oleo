import base64
import json
import logging
import os
import re
import sqlite3
import threading
import time
import traceback
from datetime import datetime
import copy # Necesario por generate_annotated_image si usa deepcopy
from pathlib import Path # Importar Path

import pytz
import requests
from flask import current_app
from PIL import Image, ImageDraw, ImageFont

# Importaciones locales relativas (asumiendo que utils está en el mismo nivel que el blueprint)
# Ajusta si tu estructura es diferente
# from app.utils.common import CommonUtils as Utils, UTC, BOGOTA_TZ, get_db_connection # Si necesitas Utils
# from db_operations import store_clasificacion # Si se usa directamente aquí (poco probable)
import db_operations # Asegurar que db_operations está importado

# Configuración de logging (básico)
logger = logging.getLogger(__name__)

# Definir zonas horarias si se usan
try:
    BOGOTA_TZ = pytz.timezone('America/Bogota')
    UTC = pytz.utc
except pytz.UnknownTimeZoneError:
    logger.error("Zonas horarias no encontradas. Usando UTC como fallback.")
    UTC = pytz.utc
    BOGOTA_TZ = UTC


# Define helper to get UTC timestamp
def get_utc_timestamp_str():
    """Generates the current UTC timestamp as a string."""
    return datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')

# Definir una clase para reemplazar el SDK de Roboflow cuando no está disponible
class DirectRoboflowClient:
    """Cliente alternativo que usa requests directamente para hablar con la API de Roboflow"""

    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key
        self.session = requests.Session()
        logger.info(f"Inicializado cliente directo de Roboflow para {api_url}")

   # Reemplaza la función run_workflow existente (aprox. línea 90-198) con esta:
    def run_workflow(self, workspace_name, workflow_id, image_path_or_url, image_data_dict, use_cache=True):
        """
        Ejecuta un workflow de Roboflow usando solicitudes HTTP directas.
        Compatible con la interfaz del SDK oficial.

        Args:
            workspace_name (str): Nombre del workspace en Roboflow.
            workflow_id (str): ID del workflow en Roboflow.
            image_path_or_url (str): Ruta al archivo local o URL de la imagen.
            image_data_dict (dict): Diccionario con el tipo y valor de la imagen
                                   (ej: {"type": "base64", "value": "..."} o {"type": "url", "value": "..."}).
            use_cache (bool): Argumento no utilizado en esta implementación directa.
        """
        logger.info(f"Ejecutando workflow {workflow_id} con imagen desde: {image_path_or_url}")

        workflow_url = f"https://detect.roboflow.com/infer/workflows/{workspace_name}/{workflow_id}"
        current_image_path = image_path_or_url # Usar la ruta original para chequeos locales

        # Variable para guardar el base64 final (original o redimensionado)
        final_image_base64 = image_data_dict.get("value")

        # --- Lógica de redimensionamiento (igual que antes, pero actualiza final_image_base64) ---
        if image_data_dict.get("type") == "base64" and os.path.exists(current_image_path):
            try:
                with Image.open(current_image_path) as img:
                    width, height = img.size
                    logger.info(f"Imagen original: {width}x{height} pixels")

                    max_width = 1152
                    max_height = 2048

                    if width > max_width or height > max_height:
                        logger.info(f"La imagen excede el tamaño máximo permitido por Roboflow. Redimensionando...")
                        ratio = min(max_width/width, max_height/height)
                        new_size = (int(width * ratio), int(height * ratio))

                        resized_image_path = current_image_path.replace('.jpg', '_resized.jpg')
                        if not resized_image_path.endswith('_resized.jpg'):
                            base, ext = os.path.splitext(current_image_path)
                            resized_image_path = f"{base}_resized{ext}"

                        resized_img = img.resize(new_size, Image.LANCZOS)
                        resized_img.save(resized_image_path, img.format or "JPEG", quality=95)
                        logger.info(f"Imagen redimensionada guardada en: {resized_image_path}")

                        # Actualizar el base64 que se usará en el payload
                        with open(resized_image_path, "rb") as image_file:
                            final_image_base64 = base64.b64encode(image_file.read()).decode("utf-8")
                        logger.info("Base64 actualizado con imagen redimensionada.")

            except Exception as e:
                logger.error(f"Error al procesar la imagen localmente ({current_image_path}): {str(e)}")
                logger.error(traceback.format_exc())
                # Continuar con el base64 original si hay error en redimensionamiento

        elif image_data_dict.get("type") == "url":
            logger.info("Procesando imagen desde URL, no se aplica redimensionamiento previo.")
            # Aquí final_image_base64 seguirá siendo None si type es URL, lo cual es correcto
            # ya que el payload para URL es diferente.
        elif image_data_dict.get("type") == "base64":
             logger.warning(f"Imagen en base64 pero la ruta original no existe o no se proporcionó: {current_image_path}")

        # --- Fin lógica de redimensionamiento ---\

        # --- INICIO CORRECCIÓN PAYLOAD ---
        # Construir payload dentro de la clave 'inputs'
        payload = {
            "api_key": self.api_key  # API Key va fuera de 'inputs' según documentación
        }
        if image_data_dict.get("type") == "base64" and final_image_base64:
             payload["inputs"] = {
                 "image": {"type": "base64", "value": final_image_base64}
                 # Añadir otros campos requeridos por el workflow aquí si es necesario
             }
        elif image_data_dict.get("type") == "url":
             payload["inputs"] = {
                 "image": {"type": "url", "value": image_path_or_url}
                 # Añadir otros campos requeridos por el workflow aquí si es necesario
             }
        else:
             logger.error(f"Tipo de imagen no soportado o base64 vacío: {image_data_dict.get('type')}")
             return {"error": "Tipo de imagen no soportado o datos inválidos"}

        # --- FIN CORRECCIÓN PAYLOAD ---

        headers = {
            "Content-Type": "application/json"
        }

        try:
            # Loguear payload de forma segura (truncando valores largos)
            loggable_payload = {}
            for key, value in payload.items():
                if key == "inputs" and isinstance(value, dict):
                    loggable_payload["inputs"] = {}
                    for k, v in value.items():
                         if k == "image" and isinstance(v, dict) and "value" in v:
                             img_val = v["value"]
                             loggable_payload["inputs"]["image"] = {"type": v.get("type"), "value": img_val[:50] + "..." if isinstance(img_val, str) and len(img_val) > 50 else img_val}
                         else:
                             loggable_payload["inputs"][k] = v[:50] + "..." if isinstance(v, str) and len(v) > 50 else v
                else:
                    loggable_payload[key] = value[:50] + "..." if isinstance(value, str) and len(value) > 50 else value

            logger.info(f"Enviando solicitud HTTP a {workflow_url} con payload: {loggable_payload}")

            response = requests.post(
                workflow_url,
                headers=headers,
                json=payload  # Usar el payload corregido
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Respuesta recibida correctamente de Roboflow")
                try:
                    logger.info(f"[DIAG RAW RESPONSE] Respuesta JSON cruda de Roboflow: {json.dumps(result, indent=2)}")
                except Exception as json_log_err:
                    logger.error(f"[DIAG RAW RESPONSE] Error al loguear respuesta JSON: {json_log_err}. Respuesta como string: {response.text}")
                return result
            else:
                logger.error(f"Error en la respuesta de Roboflow: {response.status_code} - {response.text}")
                if response.status_code == 401 or response.status_code == 403:
                    logger.error("Error de autenticación - Verificar API key de Roboflow")
                    return {"error": f"Error de autenticación ({response.status_code}): {response.text}", "auth_error": True}
                elif response.status_code == 404:
                    logger.error("Workflow o workspace no encontrado - Verificar IDs")
                    return {"error": f"Workflow o workspace no encontrado ({response.status_code}): {response.text}", "not_found": True}
                elif response.status_code == 422: # Manejo específico para el error 422
                    logger.error(f"Error de entidad no procesable (422). Revisar estructura 'inputs'. Respuesta: {response.text}")
                    return {"error": f"Entidad no procesable ({response.status_code}): {response.text}", "unprocessable_entity": True}
                elif response.status_code >= 500:
                    logger.error("Error del servidor de Roboflow - Puede ser un problema temporal")
                    return {"error": f"Error del servidor de Roboflow ({response.status_code}): {response.text}", "server_error": True}
                else:
                    return {"error": f"Error {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"Error en solicitud a Roboflow: {str(e)}")
            logger.error(traceback.format_exc())
            return {"error": str(e)}

def get_utils_instance():
    # Necesitamos Utils aquí
    from app.utils.common import CommonUtils as Utils
    return Utils(current_app)

# Helper function to check if a file is an image
def es_archivo_imagen(filename):
    """Check if a filename has an image extension"""
    return re.search(r'\.(jpg|jpeg|png|gif|bmp)$', filename.lower()) is not None

def decode_image_data(data):
    """
    Decodifica datos de imágenes en formato base64.

    Args:
        data: Datos de imagen en base64 u otro formato soportado

    Returns:
        bytes: Datos binarios de la imagen decodificada
    """
    try:
        if not data:
            return None

        # Si es un diccionario, intentar extraer el valor correcto
        if isinstance(data, dict):
            if 'value' in data:
                data = data['value']
            elif 'image' in data:
                data = data['image']
            elif 'base64' in data:
                data = data['base64']

        # Si es una string, intentar decodificar
        if isinstance(data, str):
            # Limpiar espacios y caracteres de nueva línea que pueden causar problemas
            data = data.strip()

            # Remover prefijo de data-url si existe (manejar varios formatos)
            if data.startswith('data:image'):
                # Formato típico: data:image/jpeg;base64,/9j/4AAQ...
                try:
                    data = data.split(',', 1)[1]
                except IndexError:
                    logger.warning(f"Error separando data-url, usando string completa")

            # A veces hay caracteres no válidos en base64 - eliminarlos
            valid_chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
            if any(c not in valid_chars for c in data):
                filtered_data = ''.join(c for c in data if c in valid_chars)
                logger.warning(f"Filtrados caracteres no válidos de base64: {len(data) - len(filtered_data)} caracteres eliminados")
                data = filtered_data

            # Asegurar que la longitud de la cadena es múltiplo de 4 (requisito de base64)
            missing_padding = len(data) % 4
            if missing_padding:
                data += '=' * (4 - missing_padding)
                logger.debug(f"Añadido padding a la cadena base64: {4 - missing_padding} caracteres '='")

            # Decodificar base64
            try:
                return base64.b64decode(data)
            except Exception as e:
                logger.error(f"Error en decodificación base64: {str(e)}")
                # Intentar recuperación eliminando caracteres especiales
                try:
                    cleaned_data = ''.join(c for c in data if c in valid_chars)
                    return base64.b64decode(cleaned_data)
                except:
                    logger.error("Error en intento de recuperación de base64")
                    return None

        # Si llegamos aquí, el formato no es compatible
        logger.warning(f"Formato de datos no compatible para decodificación: {type(data)}")
        return None
    except Exception as e:
        logger.error(f"Error decodificando imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return None

# --- process_images_with_roboflow ---
def process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path, roboflow_config):
    """
    Procesa imágenes usando Roboflow, enfocándose en guardar los detalles por imagen
    y calculando un resumen agregado. Recibe la configuración como argumento.

    Args:
        codigo_guia (str): Código de la guía.
        fotos_paths (list): Rutas absolutas a las imágenes.
        guia_fotos_dir (str): Directorio de salida para imágenes anotadas.
        json_path (str): Ruta al archivo JSON donde se guardarán los resultados detallados y el resumen.
        roboflow_config (dict): Diccionario con la configuración de Roboflow
                                ('api_key', 'workspace', 'project', 'workflow_id', 'api_url').

    Returns:
        tuple: (success (bool), message (str), results (dict))
               results contiene 'imagenes_procesadas' con detalles por foto y 'clasificacion_automatica' con el resumen.
    """
    logger.info(f"[DIAG Param] Iniciando process_images_with_roboflow para guía {codigo_guia} (Modo Detalle + Agregación)")
    start_time_total = time.time()
    use_roboflow_api = False
    roboflow_client = None
    workspace = roboflow_config.get('workspace')
    project = roboflow_config.get('project')
    workflow_id = roboflow_config.get('workflow_id')
    api_url = roboflow_config.get('api_url')
    api_key = roboflow_config.get('api_key')

    # --- Inicialización del cliente Roboflow ---
    try:
        required_keys = ['api_key', 'workspace', 'project', 'workflow_id', 'api_url']
        if not all(roboflow_config.get(key) for key in required_keys):
            missing_keys = [key for key in required_keys if not roboflow_config.get(key)]
            logger.warning(f"[DIAG Param] Faltan valores en la config de Roboflow: {missing_keys}. No se usará la API.")
            return False, f"Configuración de Roboflow incompleta: faltan {missing_keys}", {}
        else:
            roboflow_client = DirectRoboflowClient(api_url=api_url, api_key=api_key)
            logger.info(f"[DIAG Param] Cliente Roboflow inicializado para {project}/{workflow_id}")
            use_roboflow_api = True
    except NameError as ne:
        logger.error(f"[DIAG Param] Error: La clase DirectRoboflowClient no está definida o importada.")
        logger.error(traceback.format_exc())
        return False, "Error interno: Falta definición de DirectRoboflowClient", {}
    except Exception as client_init_err:
        logger.error(f"[DIAG Param] Error inicializando cliente Roboflow: {client_init_err}")
        return False, f"Error inicializando cliente Roboflow: {client_init_err}", {}

    # --- Estructura de Resultados (incluirá 'clasificacion_automatica' al final) ---
    results_data = {
        'codigo_guia': codigo_guia,
        'timestamp_procesamiento_utc': get_utc_timestamp_str(),
        'configuracion_usada': {
            'usando_api': use_roboflow_api,
            'workspace': workspace,
            'project': project,
            'workflow_id': workflow_id
        },
        'imagenes_procesadas': [],
        'errores': [],
        'tiempo_total_procesamiento_seg': 0
    }

    try:
        os.makedirs(guia_fotos_dir, exist_ok=True)
    except OSError as e:
        logger.error(f"No se pudo crear el directorio de salida {guia_fotos_dir}: {e}")
        results_data['errores'].append({
             'indice': None, 'nombre_original': 'Setup Directorio',
             'mensaje_error': f"Error creando directorio {guia_fotos_dir}: {e}",
             'traceback': traceback.format_exc()
        })
        return False, f"Error creando directorio de salida: {e}", results_data

    class_mapping = {
       'verde': 'verde',
       'racimos verdes': 'verde',
       'sobremaduro': 'sobremaduro',
       'racimo sobremaduro': 'sobremaduro',
       'danio_en_corona': 'danio_corona',
       'racimo daño en corona': 'danio_corona',
       'racimo dano en corona': 'danio_corona',
       'pendunculo_largo': 'pendunculo_largo',
       'racimo pedunculo largo': 'pendunculo_largo',
       'fruta_podrida': 'podrido',
       'racimo podrido': 'podrido',
       'maduro': 'maduro',
    }
    logger.info(f"[DIAG RESPONSE PROC] Diccionario class_mapping definido globalmente para la función: {class_mapping}")

    # --- Validación CRUCIAL de guia_fotos_dir ---
    try:
        static_folder_path = Path(current_app.static_folder).resolve()
        guia_fotos_dir_path = Path(guia_fotos_dir).resolve()
        logger.info(f"Verificando rutas: static_folder='{static_folder_path}', guia_fotos_dir='{guia_fotos_dir_path}'")
        if not guia_fotos_dir_path.is_relative_to(static_folder_path):
            logger.error(f"¡CRÍTICO! El directorio de salida de fotos {guia_fotos_dir_path} NO ESTÁ dentro de la carpeta static {static_folder_path}. Las URLs serán inválidas.")
            # Considerar lanzar un error aquí o asignar un path base inválido claramente
            base_rel_path_for_guide = None
        else:
             # Ejemplo: 'uploads/0150076A_20250424_185407' (Debe ser así)
             base_rel_path_for_guide = guia_fotos_dir_path.relative_to(static_folder_path).as_posix()
             logger.info(f"Ruta relativa base para URLs calculada: {base_rel_path_for_guide}")
    except Exception as path_err:
        logger.error(f"Error crítico determinando la ruta relativa base para {guia_fotos_dir}: {path_err}")
        base_rel_path_for_guide = None
    # --- Fin Validación ---

    for idx, img_path in enumerate(fotos_paths):
        start_time_img = time.time()
        img_filename = os.path.basename(img_path)
        logger.info(f"[DIAG Param] Procesando imagen {idx+1}/{len(fotos_paths)}: {img_filename}")

        # --- Inicializar image_result ---
        image_result = {
            'indice': idx + 1, 'numero': idx + 1,
            'nombre_original': img_filename, 'ruta_original': img_path, # Mantener ruta absoluta original si se necesita
            'imagen_original': None, # Se calculará abajo
            'timestamp_inicio': get_utc_timestamp_str(),
            'estado': 'pendiente',
            'mensaje_error': None, 'traceback': None,
            'tiempo_procesamiento_seg': 0,
            'detecciones': [], 'conteo_por_clase': {}, 'conteo_categorias': {},
            'total_racimos_imagen': 0, 'total_racimos': 0, 'num_racimos_detectados': 0,
            'ruta_anotada': None, # Se calculará abajo
            'imagen_annotated': None,
            'ruta_clasificada_rf': None, # Se calculará abajo
            'roboflow_potholes_count': None,
            'raw_roboflow_response': None
        }

        try:
            # --- Cálculo Directo de ruta relativa para imagen_original --- 
            image_result['imagen_original'] = None # Reiniciar por si acaso
            try:
                static_folder_path = Path(current_app.static_folder).resolve()
                img_path_abs = Path(img_path).resolve()
                if img_path_abs.is_relative_to(static_folder_path):
                    rel_original_path = img_path_abs.relative_to(static_folder_path)
                    image_result['imagen_original'] = rel_original_path.as_posix()
                    logger.info(f"Ruta URL para imagen original ({img_filename}) calculada desde origen: {image_result['imagen_original']}")
                else:
                    logger.warning(f"Imagen original '{img_path}' está fuera de static '{static_folder_path}'. No se puede generar URL.")
            except Exception as rel_orig_err:
                logger.error(f"Error calculando ruta relativa para imagen original {img_filename}: {rel_orig_err}")
            # --- Fin Cálculo imagen_original ---

            # --- Validaciones de imagen y API Roboflow ---
            if not os.path.exists(img_path): raise FileNotFoundError(f"Archivo no encontrado: {img_path}")
            if not es_archivo_imagen(img_filename): raise ValueError("Archivo no es imagen válida.")
            try:
                with Image.open(img_path) as img_pil: img_pil.verify()
                with Image.open(img_path) as img_pil:
                    img_pil.load()
                    if img_pil.mode != 'RGB': img_pil = img_pil.convert('RGB')
                    img_width, img_height = img_pil.size
            except Exception as img_err: raise ValueError(f"Error abriendo imagen: {img_err}")

            if not use_roboflow_api or not roboflow_client: raise ConnectionError("Cliente Roboflow no inicializado.")
            logger.info(f"[DIAG Param] Enviando imagen {idx+1} a Roboflow API...")
            image_data_dict = {}
            try:
                with open(img_path, "rb") as image_file:
                    img_str = base64.b64encode(image_file.read()).decode('utf-8')
                    image_data_dict = {"type": "base64", "value": img_str}
            except Exception as read_err: raise IOError(f"Error leyendo/codificando imagen: {read_err}")

            start_api_time = time.time()
            api_response = roboflow_client.run_workflow(workspace, workflow_id, img_path, image_data_dict)
            end_api_time = time.time()
            logger.info(f"[DIAG Param] Respuesta Roboflow img {idx+1}. Tiempo API: {end_api_time - start_api_time:.2f}s")

            if isinstance(api_response, dict) and api_response.get("error"):
                error_msg = api_response.get("error", "Error desconocido Roboflow")
                logger.error(f"[DIAG Param] Roboflow error img {idx+1}: {error_msg}")
                raise ConnectionError(f"Error Roboflow: {error_msg}")

            logger.info(f"[DIAG RESPONSE PROC] Procesando respuesta API para img {idx+1}...")
            try:
                logger.info(f"[DIAG RESPONSE PROC] Respuesta API Completa: {json.dumps(api_response, indent=2)}")
            except: logger.info(f"[DIAG RESPONSE PROC] Respuesta API Completa (raw): {api_response}")

            potholes_count_final = None
            primary_output = None
            image_result['raw_roboflow_response'] = api_response
            logger.info(f"[DIAG POTHOLES] Respuesta cruda guardada para foto {idx+1}")

            if isinstance(api_response, dict) and 'outputs' in api_response and isinstance(api_response['outputs'], list) and api_response['outputs']:
                primary_output = api_response['outputs'][0]
                if isinstance(primary_output, dict):
                    potholes_value_raw = primary_output.get('potholes_detected', None)
                    if potholes_value_raw is not None:
                        logger.info(f"[DIAG POTHOLES] Valor 'potholes_detected' RAW encontrado en outputs[0]: '{potholes_value_raw}' (Tipo: {type(potholes_value_raw)})")
                        try:
                            potholes_str = str(potholes_value_raw).strip()
                            potholes_count_final = int(potholes_str)
                            logger.info(f"[DIAG POTHOLES] Convertido a entero exitosamente: {potholes_count_final}")
                        except (ValueError, TypeError) as convert_err:
                            logger.warning(f"[DIAG POTHOLES] FALLO al convertir '{potholes_value_raw}' a entero: {convert_err}. Se guarda None.")
                            potholes_count_final = None
                    else:
                        logger.warning(f"[DIAG POTHOLES] Clave 'potholes_detected' NO encontrada dentro de outputs[0]. Claves presentes: {list(primary_output.keys())}")
                else:
                    logger.warning(f"[DIAG POTHOLES] El primer elemento de 'outputs' no es un diccionario (Tipo: {type(primary_output)}). No se puede buscar 'potholes_detected'.")
            elif isinstance(api_response, dict):
                 logger.warning(f"[DIAG POTHOLES] No se encontró la lista 'outputs' válida en api_response. Verificando claves raíz: {list(api_response.keys())}")
            else:
                logger.warning(f"[DIAG POTHOLES] La respuesta de Roboflow no es un diccionario (Tipo: {type(api_response)}). No se puede buscar 'potholes_detected'.")

            image_result['roboflow_potholes_count'] = potholes_count_final
            logger.info(f"[DIAG POTHOLES] Valor final asignado a image_result['roboflow_potholes_count']: {potholes_count_final}")

            claves_internas_unicas = set(class_mapping.values())
            conteo_clases_directo = {clave: 0 for clave in claves_internas_unicas}
            num_racimos_detectados_en_imagen = 0
            detections_processed = []

            if primary_output is None:
                if isinstance(api_response, dict):
                     logger.info("[DIAG RESPONSE PROC] No se encontró 'outputs'. Buscando conteos en raíz.")
                     primary_output = api_response
                else:
                     logger.warning(f"[DIAG RESPONSE PROC] Formato respuesta API inesperado ({type(api_response)}), no se buscarán conteos.")
                     primary_output = {}

            if isinstance(primary_output, dict):
                 logger.info(f"[DIAG RESPONSE PROC] Buscando conteos directos en keys: {list(primary_output.keys())}")
                 for key_rf, value_rf in primary_output.items():
                     if key_rf == 'potholes_detected': continue
                     key_rf_normalized = key_rf.lower().strip()
                     clase_interna = class_mapping.get(key_rf_normalized)
                     if clase_interna and isinstance(value_rf, (int, float)):
                         try:
                             cantidad = int(value_rf)
                             if cantidad > 0:
                                 conteo_clases_directo[clase_interna] += cantidad
                                 num_racimos_detectados_en_imagen += cantidad
                                 logger.info(f"[DIAG RESPONSE PROC] Conteo directo: RF='{key_rf}'->Int='{clase_interna}', Cant={cantidad}. Total img: {num_racimos_detectados_en_imagen}")
                         except (ValueError, TypeError):
                              logger.warning(f"No se pudo convertir valor '{value_rf}' para '{key_rf}'.")
                     elif clase_interna:
                           logger.warning(f"Valor para clave mapeada '{key_rf}'->'{clase_interna}' no numérico: {value_rf}")

            logger.info(f"[DIAG RESPONSE PROC] Conteos directos img {idx+1}. Total: {num_racimos_detectados_en_imagen}. Detalle: {conteo_clases_directo}")

            raw_predictions = []
            if isinstance(primary_output, dict) and 'predictions' in primary_output:
                raw_predictions = primary_output.get('predictions', [])
                if isinstance(raw_predictions, list): logger.info(f"Encontradas {len(raw_predictions)} predicciones BBOX.")
                else: logger.warning(f"'predictions' no es lista. Ignorando BBOX."); raw_predictions = []
            else: logger.info("No se encontró 'predictions' para BBOX.")

            if raw_predictions and img_width > 0 and img_height > 0:
                for pred in raw_predictions:
                    if not isinstance(pred, dict): continue
                    class_name_rf = pred.get('class')
                    confidence = pred.get('confidence')
                    class_name_rf_normalized = class_name_rf.lower().strip() if class_name_rf else None
                    class_name_internal = class_mapping.get(class_name_rf_normalized)
                    if not class_name_internal or confidence is None: continue
                    x_c, y_c, w, h = pred.get('x'), pred.get('y'), pred.get('width'), pred.get('height')
                    if None in [x_c, y_c, w, h]: continue
                    try:
                        x1, y1 = int((x_c-w/2)*img_width), int((y_c-h/2)*img_height)
                        x2, y2 = int((x_c+w/2)*img_width), int((y_c+h/2)*img_height)
                        detections_processed.append({'clase': class_name_internal, 'class': class_name_internal,
                                                     'confianza': round(float(confidence), 3), 'confidence': round(float(confidence), 3),
                                                     'bbox': [x1, y1, x2, y2], 'x': x_c, 'y': y_c, 'width': w, 'height': h})
                    except TypeError: continue
                logger.info(f"Procesadas {len(detections_processed)} detecciones BBOX.")
            elif raw_predictions:
                logger.warning("No se pudieron obtener dimensiones img, BBOX no procesados.")

            image_result['detecciones'] = detections_processed
            image_result['conteo_por_clase'] = conteo_clases_directo

            categorias_final = {clave: {'cantidad': 0, 'porcentaje': 0.0} for clave in claves_internas_unicas}
            total_general_categorias = 0

            for clase, cantidad in conteo_clases_directo.items():
                if clase in categorias_final:
                    categorias_final[clase]['cantidad'] += cantidad
                    total_general_categorias += cantidad

            if detections_processed and num_racimos_detectados_en_imagen == 0:
                logger.info("Usando conteos de BBOX ya que no hubo conteos directos.")
                for det in detections_processed:
                    clase = det['clase']
                    if clase in categorias_final:
                        categorias_final[clase]['cantidad'] += 1
                        total_general_categorias += 1
            elif detections_processed:
                 logger.info("Conteos directos encontrados, ignorando BBOX para conteo total.")

            if total_general_categorias > 0:
                for clase in categorias_final:
                    categorias_final[clase]['porcentaje'] = round((categorias_final[clase]['cantidad'] / total_general_categorias) * 100, 2)

            image_result['conteo_categorias'] = categorias_final
            # --- CORRECCIÓN: Usar potholes_count si existe para el total --- 
            if image_result['roboflow_potholes_count'] is not None:
                 try:
                     # Asegurar que sea un entero válido
                     total_para_usar = int(image_result['roboflow_potholes_count'])
                     logger.info(f"Usando roboflow_potholes_count ({total_para_usar}) como total para img {idx+1}")
                 except (ValueError, TypeError):
                     logger.warning(f"roboflow_potholes_count no es entero válido ({image_result['roboflow_potholes_count']}). Usando total_general_categorias ({total_general_categorias}).")
                     total_para_usar = total_general_categorias
            else:
                 logger.info(f"roboflow_potholes_count es None. Usando total_general_categorias ({total_general_categorias}) como total para img {idx+1}")
                 total_para_usar = total_general_categorias

            image_result['num_racimos_detectados'] = total_para_usar
            image_result['total_racimos_imagen'] = total_para_usar
            image_result['total_racimos'] = total_para_usar
            # --- FIN CORRECCIÓN ---

            logger.info(f"Asignación final img {idx+1} - num_racimos_detectados: {image_result['num_racimos_detectados']}")

            # --- Guardado y Cálculo de URL para "Imagen Clasificada (Etiquetas)" (annotated_image) --- 
            image_result['ruta_clasificada_rf'] = None
            annotated_image_data = primary_output.get('annotated_image') if isinstance(primary_output, dict) else None
            if annotated_image_data and isinstance(annotated_image_data, dict) and annotated_image_data.get('type') == 'base64':
                labeled_filename_rf = f"{os.path.splitext(img_filename)[0]}_labeled_rf.jpg"
                labeled_path_rf_abs = Path(guia_fotos_dir) / labeled_filename_rf
                try:
                    img_bytes = base64.b64decode(annotated_image_data['value'])
                    with open(labeled_path_rf_abs, 'wb') as f_out:
                        f_out.write(img_bytes)
                    logger.info(f"Guardada imagen 'annotated_image' de Roboflow en: {labeled_path_rf_abs}")
                    guide_folder_name = Path(guia_fotos_dir).name
                    relative_url_path = f"uploads/{guide_folder_name}/{labeled_filename_rf}"
                    image_result['ruta_clasificada_rf'] = relative_url_path
                    logger.info(f"Ruta URL para 'annotated_image' ({labeled_filename_rf}) construida: {relative_url_path}")
                except Exception as save_rf_err:
                    logger.error(f"Error guardando o construyendo URL para 'annotated_image': {save_rf_err}")
            else:
                logger.warning(f"No se encontró 'annotated_image' válida en la respuesta para foto {idx+1}")
            # --- Fin annotated_image ---

            # --- NUEVO: Guardado y URL para "Imagen Procesada (Conteos)" (label_visualization_1) --- 
            image_result['ruta_anotada'] = None
            image_result['imagen_annotated'] = None
            label_viz_data = primary_output.get('label_visualization_1') if isinstance(primary_output, dict) else None
            if label_viz_data and isinstance(label_viz_data, dict) and label_viz_data.get('type') == 'base64':
                label_viz_filename = f"{os.path.splitext(img_filename)[0]}_label_viz.jpg"
                label_viz_path_abs = Path(guia_fotos_dir) / label_viz_filename
                try:
                    img_bytes_viz = base64.b64decode(label_viz_data['value'])
                    with open(label_viz_path_abs, 'wb') as f_out:
                        f_out.write(img_bytes_viz)
                    logger.info(f"Guardada imagen 'label_visualization_1' de Roboflow en: {label_viz_path_abs}")
                    guide_folder_name = Path(guia_fotos_dir).name
                    relative_url_path_viz = f"uploads/{guide_folder_name}/{label_viz_filename}"
                    image_result['ruta_anotada'] = relative_url_path_viz
                    image_result['imagen_annotated'] = relative_url_path_viz # Asignar a ambas claves
                    logger.info(f"Ruta URL para 'label_visualization_1' ({label_viz_filename}) construida: {relative_url_path_viz}")
                except Exception as save_viz_err:
                     logger.error(f"Error guardando o construyendo URL para 'label_visualization_1': {save_viz_err}")
            else:
                logger.warning(f"No se encontró 'label_visualization_1' válida en la respuesta para foto {idx+1}")
            # --- Fin label_visualization_1 ---

            # --- Guardado y Cálculo (posiblemente fallido) para imagen anotada localmente --- 
            # Se mantiene esta lógica por si acaso, aunque probablemente no se ejecute si no hay detections_processed
            if detections_processed:
                 annotated_filename = f"{os.path.splitext(img_filename)[0]}_annotated.jpg"
                 annotated_path_abs = Path(guia_fotos_dir) / annotated_filename
                 try:
                    generate_annotated_image(img_path, detections_processed, str(annotated_path_abs))
                    logger.info(f"Imagen anotada local generada en: {annotated_path_abs}")
                    # NO SOBREESCRIBIR las rutas si label_visualization_1 ya las llenó
                    if image_result['ruta_anotada'] is None:
                        guide_folder_name = Path(guia_fotos_dir).name
                        relative_url_path = f"uploads/{guide_folder_name}/{annotated_filename}"
                        image_result['ruta_anotada'] = relative_url_path
                        image_result['imagen_annotated'] = relative_url_path
                        logger.info(f"Ruta URL para imagen anotada LOCAL ({annotated_filename}) construida: {relative_url_path}")
                    else:
                        logger.info("Se omite la asignación de URL para imagen anotada local porque ya se usó la de label_visualization_1.")

                 except Exception as gen_ann_err:
                     logger.error(f"Error generando imagen anotada local: {gen_ann_err}")
            # --- Fin imagen anotada localmente ---

            image_result['estado'] = 'procesada_ok'

        except FileNotFoundError as e:
            logger.error(f"Error procesando imagen {img_filename}: {e}")
            image_result['estado'] = 'error_archivo'
            image_result['mensaje_error'] = str(e)
            image_result['traceback'] = traceback.format_exc()
            results_data['errores'].append(image_result)
        except ValueError as e:
            logger.error(f"Error procesando imagen {img_filename}: {e}")
            image_result['estado'] = 'error_formato'
            image_result['mensaje_error'] = str(e)
            image_result['traceback'] = traceback.format_exc()
            results_data['errores'].append(image_result)
        except ConnectionError as e:
             logger.error(f"Error de conexión con Roboflow para {img_filename}: {e}")
             image_result['estado'] = 'error_api'
             image_result['mensaje_error'] = str(e)
             image_result['traceback'] = traceback.format_exc()
             results_data['errores'].append(image_result)
        except Exception as e:
            logger.error(f"Error inesperado procesando imagen {img_filename}: {e}")
            image_result['estado'] = 'error_inesperado'
            image_result['mensaje_error'] = str(e)
            image_result['traceback'] = traceback.format_exc()
            results_data['errores'].append(image_result)
        finally:
            end_time_img = time.time()
            image_result['tiempo_procesamiento_seg'] = round(end_time_img - start_time_img, 2)
            # Solo añadir al resultado si tiene datos útiles o si hubo un error específico de la imagen
            if image_result['estado'] != 'pendiente' or image_result['mensaje_error']:
                 results_data['imagenes_procesadas'].append(image_result)
            logger.info(f"Imagen {idx+1} finalizada. Estado: {image_result['estado']}. Tiempo: {image_result['tiempo_procesamiento_seg']:.2f}s")

    logger.info("[DIAG AGGREGATION] Iniciando cálculo de resultados agregados...")
    clasificacion_automatica = {
        'codigo_guia': codigo_guia,
        'timestamp_finalizacion_utc': get_utc_timestamp_str(),
        'conteo_total_racimos': 0,
        'conteo_imagenes_ok': 0,
        'conteo_imagenes_error': 0,
        'categorias': {},
        'detalle_errores': results_data['errores']
    }

    categorias_base = list(class_mapping.values())
    for cat_base in set(categorias_base):
        clasificacion_automatica['categorias'][cat_base] = {'cantidad': 0, 'porcentaje': 0.0}

    total_racimos_agregado = 0

    for img_res in results_data['imagenes_procesadas']:
        if img_res['estado'] == 'procesada_ok':
            clasificacion_automatica['conteo_imagenes_ok'] += 1
            num_racimos_img = img_res.get('num_racimos_detectados', 0)
            total_racimos_agregado += num_racimos_img

            conteo_categorias_img = img_res.get('conteo_categorias', {})
            for cat_interna, datos_cat in conteo_categorias_img.items():
                if cat_interna in clasificacion_automatica['categorias']:
                    clasificacion_automatica['categorias'][cat_interna]['cantidad'] += datos_cat.get('cantidad', 0)
        else:
            clasificacion_automatica['conteo_imagenes_error'] += 1

    clasificacion_automatica['conteo_total_racimos'] = total_racimos_agregado

    if total_racimos_agregado > 0:
        for cat_interna in clasificacion_automatica['categorias']:
            cantidad_cat = clasificacion_automatica['categorias'][cat_interna]['cantidad']
            clasificacion_automatica['categorias'][cat_interna]['porcentaje'] = round((cantidad_cat / total_racimos_agregado) * 100, 2)

    results_data['clasificacion_automatica'] = clasificacion_automatica
    end_time_total = time.time()
    results_data['tiempo_total_procesamiento_seg'] = round(end_time_total - start_time_total, 2)

    logger.info(f"[DIAG AGGREGATION] Resultados agregados calculados. Total racimos: {total_racimos_agregado}")
    logger.info(f"[DIAG AGGREGATION] Detalle agregado: {clasificacion_automatica['categorias']}")
    logger.info(f"[DIAG Param] Finalizando process_images_with_roboflow. Tiempo total: {results_data['tiempo_total_procesamiento_seg']:.2f}s")

    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(results_data, f, ensure_ascii=False, indent=4)
        logger.info(f"[DIAG WRITE] Resultados guardados exitosamente en: {json_path}")

        try:
            file_size = os.path.getsize(json_path)
            logger.info(f"[DIAG WRITE] Verificación post-escritura: OK (Tamaño: {file_size} bytes)")
        except Exception as check_err:
             logger.warning(f"[DIAG WRITE] No se pudo verificar el archivo después de escribir: {check_err}")

        success = clasificacion_automatica['conteo_imagenes_ok'] > 0
        message = f"Procesamiento completado. {clasificacion_automatica['conteo_imagenes_ok']} imágenes OK, {clasificacion_automatica['conteo_imagenes_error']} con error."
        return success, message, results_data

    except Exception as e:
        logger.error(f"[DIAG WRITE] Error guardando resultados en JSON {json_path}: {e}")
        logger.error(traceback.format_exc())
        return False, f"Error guardando resultados JSON: {e}", results_data
# --- FIN DE LA FUNCIÓN PARA COPIAR ---


# --- process_thread ---
def process_thread(app, codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Función ejecutada en un hilo separado para procesar imágenes con Roboflow.
    Establece contexto, lee config y la pasa explícitamente a la función de procesamiento.
    """
    with app.app_context(): # Establecer contexto de aplicación
        start_time = time.time()
        utils = get_utils_instance() # Necesita Utils y current_app
        logger.info(f"[Hilo Param] Iniciando procesamiento para guía: {codigo_guia}")

        try:
            roboflow_config = {
                'api_key': current_app.config.get('ROBOFLOW_API_KEY'),
                'workspace': current_app.config.get('ROBOFLOW_WORKSPACE'),
                'project': current_app.config.get('ROBOFLOW_PROJECT'),
                'workflow_id': current_app.config.get('ROBOFLOW_WORKFLOW_ID'),
                'api_url': current_app.config.get('ROBOFLOW_API_URL', "https://classify.roboflow.com")
            }
            required_keys = ['api_key', 'workspace', 'project', 'workflow_id', 'api_url']
            if not all(roboflow_config.get(key) for key in required_keys):
                 missing_keys = [key for key in required_keys if not roboflow_config.get(key)]
                 logger.error(f"[Hilo Param] Faltan valores en la configuración de Roboflow leída desde app.config. Claves faltantes: {missing_keys}")
                 raise ValueError("Configuración de Roboflow incompleta.")
            logger.info("[Hilo Param] Configuración Roboflow leída exitosamente desde app.config.")
        except Exception as config_err:
            logger.error(f"[Hilo Param] Error crítico leyendo configuración de Roboflow desde app.config: {config_err}")
            try:
                update_data = {'codigo_guia': codigo_guia, 'estado': 'error_config'} # Añadir codigo_guia
                # Necesitaríamos una función de actualización de BD aquí si se usa
                # db_operations.store_clasificacion(update_data) # Llamar aquí también si es necesario
                logger.info(f"[Hilo Param] Estado 'error_config' guardado para guía {codigo_guia} (si update funcionó).")
            except Exception as update_e:
                logger.error(f"[Hilo Param] Error adicional al guardar estado 'error_config' para {codigo_guia}: {update_e}")
            return

        try:
            success, message, results = process_images_with_roboflow(
                codigo_guia,
                fotos_paths,
                guia_fotos_dir,
                json_path,
                roboflow_config
            )
            end_time = time.time()
            processing_time = end_time - start_time

            final_status = 'completado' if success else 'error_procesamiento'
            if success and results and 'clasificacion_automatica' in results and results['clasificacion_automatica'].get('conteo_total_racimos', 0) == 0:
                final_status = 'completado_sin_deteccion'

            # --- Preparar datos para guardar en DB --- 
            update_data = {
                'codigo_guia': codigo_guia, # Incluir la clave primaria
                'estado': final_status, # Guardar el estado calculado
                'timestamp_fin_auto': get_utc_timestamp_str(),
                'tiempo_procesamiento_auto': round(processing_time, 2),
                # Obtener el total de racimos detectados del resumen
                'total_racimos_detectados': results.get('clasificacion_automatica', {}).get('conteo_total_racimos') if results else None,
                # Guardar el resumen de categorías como JSON en clasificacion_consolidada
                'clasificacion_consolidada': json.dumps(results.get('clasificacion_automatica', {}).get('categorias', {}), ensure_ascii=False) if results else None,
                # --- NUEVO: Guardar también el JSON completo en clasificacion_automatica_json ---
                'clasificacion_automatica_json': json.dumps(results.get('clasificacion_automatica', {}), ensure_ascii=False, default=str) if results else None 
                # --- FIN NUEVO ---
            }
            # --- Fin preparación datos DB ---

            # --- Bloque para llamar a la función de actualización de DB --- 
            try:
                # Filtrar claves None antes de guardar
                datos_para_guardar = {k: v for k, v in update_data.items() if v is not None}
                if len(datos_para_guardar) > 1: # Asegurar que hay algo más que codigo_guia
                    # Llamar a la función de actualización de DB con los datos preparados
                    exito_update = db_operations.store_clasificacion(datos_para_guardar)
                    if exito_update:
                        logger.info(f"[Hilo Param] Estado final '{final_status}' y consolidado guardado en DB para guía {codigo_guia}.")
                    else:
                        logger.error(f"[Hilo Param] Error al guardar estado final/consolidado en DB para guía {codigo_guia}.")
                else:
                    logger.info(f"[Hilo Param] No había datos nuevos para guardar en DB para guía {codigo_guia} (después de filtrar None). ")
            except Exception as db_update_err:
                logger.error(f"[Hilo Param] Error actualizando DB en hilo: {db_update_err}")
            # --- Fin bloque actualización DB ---

            logger.info(f"[Hilo Param] Procesamiento completado para guía {codigo_guia}. Tiempo: {processing_time:.2f} segundos. Estado final: {final_status}. Mensaje: {message}")

        except NameError as ne:
             logger.error(f"[Hilo Param] Error de definición: {ne}. Asegúrate que 'process_images_with_roboflow' esté definida ANTES que 'process_thread'.")
             logger.error(traceback.format_exc())
             # Intentar marcar error en DB
        except Exception as e:
            end_time = time.time()
            logger.error(f"[Hilo Param] Error GRABE en el hilo de procesamiento para guía {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            # Intentar marcar error en DB

# --- generate_annotated_image ---
def generate_annotated_image(original_image_path, detections, output_path=None):
    """
    Genera una imagen con anotaciones (bounding boxes) basadas en las detecciones
    y guarda la imagen procesada. Devuelve la ruta relativa al directorio static.

    Args:
        original_image_path (str): Ruta al archivo de imagen original.
        detections (list): Lista de diccionarios de detección. Cada dict debe tener
                           'clase', 'confianza', y 'bbox' (lista [x1, y1, x2, y2]).
                           Las coordenadas bbox deben ser absolutas (en píxeles).
        output_path (str, optional): Ruta absoluta donde guardar la imagen procesada.

    Returns:
        str or None: Ruta relativa al directorio 'static' de la imagen anotada guardada,
                     o None si ocurre un error.
    """
    try:
        if not os.path.exists(original_image_path):
            logger.error(f"Imagen original no encontrada: {original_image_path}")
            return None

        if not output_path:
            base_dir = os.path.dirname(original_image_path)
            base_name = os.path.basename(original_image_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(base_dir, f"{name}_annotated.jpg")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with Image.open(original_image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            draw = ImageDraw.Draw(img)
            img_width, img_height = img.size

            class_colors = {
                'verde': (0, 128, 0), 'sobremaduro': (255, 0, 0),
                'danio_corona': (255, 192, 203), 'pendunculo_largo': (0, 0, 255),
                'podrido': (75, 0, 130), 'maduro': (255, 165, 0),
            }
            default_color = (128, 128, 128)

            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except IOError:
                try:
                     font = ImageFont.truetype("DejaVuSans.ttf", 20)
                except IOError:
                     font = ImageFont.load_default()

            for detection in detections:
                clase = detection.get('clase', 'desconocido')
                confianza = detection.get('confianza', 0.0)
                bbox = detection.get('bbox')

                if not bbox or len(bbox) != 4:
                    logger.warning(f"Bounding box inválido o ausente para detección: {detection}")
                    continue

                color = class_colors.get(clase.lower(), default_color)

                try:
                    coords = [int(c) for c in bbox]
                    draw.rectangle(coords, outline=color, width=3)
                except (ValueError, TypeError) as e:
                    logger.error(f"Error al dibujar rectángulo con bbox {bbox}: {e}")
                    continue

                label_text = f"{clase}: {confianza:.0%}"
                try:
                    text_bbox = draw.textbbox((coords[0], coords[1]), label_text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                except AttributeError:
                    text_size = draw.textsize(label_text, font=font)
                    text_width = text_size[0]
                    text_height = text_size[1]

                text_x = coords[0] + 2
                text_y = coords[1] + 2
                if text_y < 0:
                      text_y = coords[3] - text_height - 2

                draw.rectangle([text_x, text_y, text_x + text_width + 4, text_y + text_height + 4], fill=color)
                draw.text((text_x + 2, text_y + 2), label_text, fill="white", font=font)

            img.save(output_path, "JPEG", quality=95)
            logger.info(f"Imagen procesada generada y guardada en: {output_path}")

            try:
                static_folder = current_app.static_folder
                rel_path = os.path.relpath(output_path, static_folder)
                rel_path_url_format = rel_path.replace(os.sep, '/')
                logger.info(f"Devolviendo ruta relativa para imagen anotada: {rel_path_url_format}")
                return rel_path_url_format
            except ValueError:
                 logger.warning(f"No se pudo calcular la ruta relativa para {output_path} desde {static_folder}. Devolviendo ruta absoluta.")
                 return output_path
            except Exception as rel_path_err:
                 logger.error(f"Error inesperado calculando ruta relativa: {rel_path_err}")
                 return output_path

    except FileNotFoundError:
         logger.error(f"Error: Imagen original no encontrada en {original_image_path}")
         return None
    except ImportError:
         logger.error("Error: Biblioteca Pillow (PIL) no encontrada. Instálala: pip install Pillow")
         return None
    except Exception as e:
        logger.error(f"Error generando imagen anotada ({original_image_path}): {str(e)}")
        logger.error(traceback.format_exc())
        return None


# --- get_clasificacion_by_codigo_guia ---
def get_clasificacion_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de clasificación por su código de guía.
    Utiliza la conexión centralizada.

    Args:
        codigo_guia (str): Código de guía a buscar

    Returns:
        dict: Datos de la clasificación o None si no se encuentra
    """
    conn = None # Inicializar conexión
    try:
        # >>> CAMBIO PRINCIPAL: Usar la función de utilidad <<<
        # Necesitamos get_db_connection aquí
        from app.utils.common import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()

        if row:
            clasificacion = dict(row)

            if 'clasificacion_manual_json' in clasificacion and clasificacion['clasificacion_manual_json']:
                try:
                    clasificacion['clasificacion_manual'] = json.loads(clasificacion['clasificacion_manual_json'])
                except json.JSONDecodeError:
                    logger.error(f"Error decodificando clasificacion_manual_json para {codigo_guia}: {clasificacion['clasificacion_manual_json']}")
                    clasificacion['clasificacion_manual'] = {}

            if 'clasificacion_automatica_json' in clasificacion and clasificacion['clasificacion_automatica_json']:
                try:
                    clasificacion['clasificacion_automatica'] = json.loads(clasificacion['clasificacion_automatica_json'])
                except json.JSONDecodeError:
                    logger.error(f"Error decodificando clasificacion_automatica_json para {codigo_guia}: {clasificacion['clasificacion_automatica_json']}")
                    clasificacion['clasificacion_automatica'] = {}

            try:
                cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto",
                             (codigo_guia,))
                fotos = [foto_row[0] for foto_row in cursor.fetchall()]
                clasificacion['fotos'] = fotos
            except sqlite3.OperationalError as table_err:
                if "no such table" in str(table_err):
                    logger.warning(f"Tabla fotos_clasificacion no encontrada para {codigo_guia}. Omitiendo fotos.")
                    clasificacion['fotos'] = []
                else:
                    raise

            logger.debug(f"Clasificación encontrada para {codigo_guia}")
            return clasificacion
        else:
            logger.warning(f"No se encontró registro de clasificación para {codigo_guia}")
            return None

    except sqlite3.Error as e:
        logger.error(f"Error de base de datos recuperando clasificación para {codigo_guia}: {e}")
        logger.error(traceback.format_exc())
        return None
    except Exception as e:
        logger.error(f"Error inesperado recuperando clasificación para {codigo_guia}: {e}")
        logger.error(traceback.format_exc())
        return None
    finally:
        if conn:
            conn.close()
            logger.debug(f"Conexión a BD cerrada para {codigo_guia} en get_clasificacion_by_codigo_guia.")


# --- tu_funcion_que_prepara_contexto ---
def tu_funcion_que_prepara_contexto(datos_guia):
    # ... otros cálculos previos ...
    # Necesita convertir_timestamp_a_fecha_hora - Esta función no está definida aquí ni en routes.py original
    # Se debe definir o importar de donde exista (posiblemente misc/routes.py?)
    # def convertir_timestamp_a_fecha_hora(timestamp_utc_str): ...

    # Obtener la fecha de pesaje a partir del timestamp
    if datos_guia.get('timestamp_pesaje_utc'):
         # fecha_pesaje, _ = convertir_timestamp_a_fecha_hora(datos_guia['timestamp_pesaje_utc']) # Comentado por dependencia faltante
         fecha_pesaje = "FUNC_FALTANTE"
    else:
        fecha_pesaje = "Pendiente"

    contexto = {
        # ... otros campos ...
        'fecha_pesaje': fecha_pesaje,
        # ... otros campos ...
    }
    # ... resto de la función ...
    return contexto 

