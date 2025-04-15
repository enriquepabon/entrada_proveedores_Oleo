# Standard Library Imports
import base64
import fnmatch  # Para comparación de patrones de archivos
import glob
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import threading
import time
import traceback
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
import copy
# Al principio de app/blueprints/clasificacion/routes.py
from app.utils.common import get_db_connection, get_utc_timestamp_str

# Third-party Library Imports
from flask import (
    Blueprint, current_app, flash, jsonify, make_response, redirect,
    render_template, request, send_file, session, url_for
)
from jinja2 import TemplateNotFound
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytz
import requests
from werkzeug.utils import secure_filename

# Local Application Imports
# Asegúrate que la ruta a db_operations sea correcta desde este archivo
# Si db_operations.py está en el directorio raíz del proyecto:
import db_operations
# O si está dentro de app/utils/ por ejemplo:
# from app.utils import db_operations
# O si está al mismo nivel que la carpeta blueprints:
# import db_operations

# Si necesitas funciones específicas directamente:
from db_operations import store_clasificacion, get_clasificacion_by_codigo_guia
from app.utils.common import CommonUtils as Utils, format_datetime_filter, UTC, BOGOTA_TZ
from . import bp  # Importa el Blueprint local
# Asumiendo que 'utils.py' existe dentro del blueprint 'clasificacion'
from .utils import normalize_image_path, find_annotated_image, find_original_images

# Local helper functions (assuming they are defined later in this file)
# from .helpers import es_archivo_imagen, get_utils_instance # Example if they were in helpers.py
# If defined in *this* file, no import needed here. Check definitions below.

# Configurar logger (Asegúrate que esto se haga una sola vez, preferiblemente en __init__.py)
# logger = logging.getLogger(__name__) # Ya deberías tener esto configurado

# Configuración de logging (asegúrate que esté configurado)
logger = logging.getLogger(__name__)

# Definir zona horaria si se usa consistentemente
BOGOTA_TZ = pytz.timezone('America/Bogota')

# Configurar logging
logger = logging.getLogger(__name__)

# Define timezones
BOGOTA_TZ = pytz.timezone('America/Bogota')
UTC = pytz.utc

# Define helper to get UTC timestamp
def get_utc_timestamp_str():
    """Generates the current UTC timestamp as a string."""
    return datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')

# Intentar importar el SDK de Roboflow, pero proporcionar una interfaz alternativa si no está disponible
try:
    # noqa: F401 - Se importa pero puede que no se use directamente si hay error
    from inference_sdk import InferenceHTTPClient  # type: ignore # pylint: disable=import-error
except ImportError:
    logger.warning("Inference SDK not installed or not compatible with this Python version. Will use HTTP direct requests for Roboflow.")
    InferenceHTTPClient = None
    
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

@bp.route('/<codigo>')
def clasificacion(codigo):
    """
    Vista principal para la clasificación de racimos
    """
    try:
        logger.info(f"Inicio función clasificacion para: {codigo}")
        
        # Verificar si hay datos en la sesión para peso bruto
        peso_bruto_session = session.get('peso_bruto')
        logger.info(f"Peso bruto en sesión: {peso_bruto_session}")
        
        # Obtener información completa de la guía mediante el código original
        codigo_guia = codigo
        codigo_guia_json = codigo
        
        # Si hay un error o se verifica que hay otro formato de código
        if '_' not in codigo and len(codigo) <= 8:  # Posiblemente solo código de proveedor
            logger.warning(f"Formato de código posiblemente incompleto: {codigo}")
            # Obtener el código guía completo del archivo más reciente
            guias_folder = current_app.config['GUIAS_FOLDER']
            guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo}_*.html'))
            
            if guias_files:
                # Ordenar por fecha de modificación, más reciente primero
                guias_files.sort(key=os.path.getmtime, reverse=True)
                # Extraer el codigo_guia del nombre del archivo más reciente
                latest_guia = os.path.basename(guias_files[0])
                codigo_guia_json = latest_guia[5:-5]  # Remover 'guia_' y '.html'
                logger.info(f"Código guía completo obtenido del archivo HTML: {codigo_guia_json}")
            else:
                # Si no encontramos archivos HTML, buscar en los archivos JSON de guía
                json_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo}_*.json'))
                
                if json_files:
                    json_files.sort(key=os.path.getmtime, reverse=True)
                    latest_json = os.path.basename(json_files[0])
                    codigo_guia_json = latest_json[5:-5]  # Remover 'guia_' y '.json'
                    logger.info(f"Código guía completo obtenido del archivo JSON: {codigo_guia_json}")
        
        # Verificar si se ha proporcionado el parámetro reclasificar
        reclasificar = request.args.get('reclasificar', 'false').lower() == 'true'
        logger.info(f"Parámetro reclasificar: {reclasificar}")
        
        # Verificar si ya existe un archivo de clasificación para esta guía específica
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        codigo_guia_completo = codigo_guia_json
        archivo_clasificacion_exacto = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_completo}.json")
        
        # También verificar en el directorio fotos_racimos_temp
        fotos_racimos_dir = os.path.join(current_app.static_folder, 'fotos_racimos_temp')
        os.makedirs(fotos_racimos_dir, exist_ok=True)
        archivo_clasificacion_alt = os.path.join(fotos_racimos_dir, f"clasificacion_{codigo_guia_completo}.json")
        
        clasificacion_existe = os.path.exists(archivo_clasificacion_exacto) or os.path.exists(archivo_clasificacion_alt)
        logger.info(f"Verificación de clasificación: existe = {clasificacion_existe}, reclasificar = {reclasificar}")
        
        # Verificar si la petición viene del botón en guia_centralizada.html
        # Si es así, forzamos la clasificación independientemente de si existe o no
        referrer = request.referrer or ""
        desde_guia_centralizada = 'guia-centralizada' in referrer
        
        if clasificacion_existe and not reclasificar and not desde_guia_centralizada:
            logger.info(f"Se encontró un archivo de clasificación para la guía actual: {codigo_guia_completo}")
            # Redirigir a la página de resultados de clasificación
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia_completo))
        elif clasificacion_existe and (reclasificar or desde_guia_centralizada):
            logger.info(f"Se encontró un archivo de clasificación, pero se procederá con la reclasificación: {codigo_guia_completo}")

        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia_completo)
        logger.info(f"Datos de guía obtenidos: {json.dumps(datos_guia)}")
        
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia_completo}")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá de la clasificación
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado'] and not reclasificar:
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia_completo))
        
        # Verificar si hay datos en la sesión para peso
        tiene_peso_en_sesion = peso_bruto_session is not None
        tiene_peso_en_guia = datos_guia.get('peso_bruto') is not None
        
        # Logging para diagnóstico
        logger.info(f"Verificación de pesaje completado: {tiene_peso_en_sesion or tiene_peso_en_guia} (peso en guía: {tiene_peso_en_guia}, peso en sesión: {tiene_peso_en_sesion})")
        
        # Verificar si el pesaje ha sido completado
        if not (tiene_peso_en_sesion or tiene_peso_en_guia):
            flash("Necesitas completar el pesaje antes de clasificar los racimos.", "warning")
            return redirect(url_for('pesaje.pesaje', codigo=codigo_guia_completo))
        
        # Obtener el código de proveedor directamente del código guía
        # El formato típico es 0123456A_YYYYMMDD_HHMMSS
        codigo_proveedor = None
        nombre_proveedor = None
        cantidad_racimos = None
        
        # Extraer el código de proveedor del código de guía
        if '_' in codigo_guia_completo:
            codigo_proveedor = codigo_guia_completo.split('_')[0]
            # Asegurarse de que termina con 'A' correctamente
            if re.match(r'\d+[aA]?$', codigo_proveedor):
                if codigo_proveedor.endswith('a'):
                    codigo_proveedor = codigo_proveedor[:-1] + 'A'
                elif not codigo_proveedor.endswith('A'):
                    codigo_proveedor = codigo_proveedor + 'A'
        else:
            codigo_proveedor = codigo_guia_completo
        
        logger.info(f"Código de proveedor extraído: {codigo_proveedor}")
        
        # Intentar obtener datos del proveedor desde la base de datos de entrada
        try:
            from db_utils import get_entry_record_by_guide_code
            
            # Primero intentar buscar por código guía completo
            registro_entrada = get_entry_record_by_guide_code(codigo_guia_completo)
            
            if registro_entrada:
                logger.info(f"Encontrado registro de entrada para guía {codigo_guia_completo}")
                nombre_proveedor = registro_entrada.get('nombre_proveedor')
                cantidad_racimos = registro_entrada.get('cantidad_racimos') or registro_entrada.get('racimos')
            else:
                # Si no encontramos el registro por código completo, usar datos de sesión o valores predeterminados
                logger.warning(f"No se encontró registro de entrada para guía {codigo_guia_completo}")
                
                # Intentar obtener datos del proveedor usando el código de proveedor
                from db_operations import get_provider_by_code
                datos_proveedor = get_provider_by_code(codigo_proveedor)
                
                if datos_proveedor:
                    logger.info(f"Encontrado proveedor por código: {codigo_proveedor}")
                    nombre_proveedor = datos_proveedor.get('nombre')
                    # La cantidad de racimos podría no estar aquí
                
        except Exception as e:
            logger.error(f"Error buscando información del proveedor: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Usar valores de datos_guia si están disponibles, sino usar los que acabamos de obtener
        codigo_proveedor_final = datos_guia.get('codigo_proveedor') or codigo_proveedor
        
        # CORREGIDO: Priorizar el nombre del proveedor del registro de entrada
        nombre_proveedor_final = (
            nombre_proveedor or
            datos_guia.get('nombre_proveedor') or 
            datos_guia.get('nombre_agricultor') or 
            datos_guia.get('nombre') or 
            'Proveedor no identificado'
        )
        
        # CORREGIDO: Priorizar la cantidad de racimos del registro de entrada
        cantidad_racimos_final = (
            cantidad_racimos or
            datos_guia.get('cantidad_racimos') or 
            datos_guia.get('racimos') or 
            'N/A'
        )
        
        logger.info(f"Información final para template - Nombre: {nombre_proveedor_final}, Racimos: {cantidad_racimos_final}")
        
        # Preparar los datos para la plantilla
        template_data = {
            'codigo_guia': codigo_guia_completo,
            'codigo_proveedor': codigo_proveedor_final,
            'nombre_proveedor': nombre_proveedor_final,
            'peso_bruto': datos_guia.get('peso_bruto') or peso_bruto_session,
            'cantidad_racimos': cantidad_racimos_final,
            'en_reclasificacion': reclasificar,
            'tipo_pesaje': datos_guia.get('tipo_pesaje', 'No especificado'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'N/A'),
            'hora_pesaje': datos_guia.get('hora_pesaje', ''),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', 'No disponible')
        }
        
        logger.info(f"Renderizando plantilla de clasificación con datos: {template_data}")
        
        # Renderizar la plantilla de clasificación
        return render_template('clasificacion/clasificacion_form.html', **template_data)
        
    except Exception as e:
        logger.error(f"Error al mostrar vista de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al cargar la vista de clasificación: {str(e)}", "danger")
        return render_template('error.html', message=f"Error al cargar la vista de clasificación: {str(e)}"), 500


@bp.route('/prueba-clasificacion/<codigo>')
def prueba_clasificacion(codigo):
    """
    Endpoint de prueba para verificar datos disponibles para clasificación
    """
    try:
        logger.info(f"Prueba de clasificación para código: {codigo}")
        
        # Obtener el código base (sin timestamp ni versión)
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = current_app.config['GUIAS_FOLDER']
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            logger.info(f"Código guía completo obtenido del archivo HTML: {codigo_guia_completo}")
        else:
            codigo_guia_completo = codigo
            logger.info(f"No se encontró archivo HTML, usando código original: {codigo_guia_completo}")
        
        # Obtener datos completos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return jsonify({"error": "Guía no encontrada"}), 404
            
        # Mostrar los datos disponibles en la guía
        return jsonify({
            "datos_guia_completos": datos_guia,
            "nombre_variables_disponibles": list(datos_guia.keys()),
            "nombre_proveedor": datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible'),
            "codigo_proveedor": datos_guia.get('codigo_proveedor') or datos_guia.get('codigo', 'No disponible'),
            "cantidad_racimos": datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
            "peso_bruto": datos_guia.get('peso_bruto'),
            "estado_actual": datos_guia.get('estado_actual'),
        })
    
    except Exception as e:
        logger.error(f"Error en prueba de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@bp.route('/registrar_clasificacion', methods=['POST'])
def registrar_clasificacion():
    """
    Registra la clasificación manual y las fotos subidas.
    Redirige a la vista centralizada después de guardar.
    """
    utils = get_utils_instance()
    codigo_guia = request.form.get('codigo_guia')
    logger.info(f"Iniciando registro de clasificación manual/fotos para guía: {codigo_guia}")

    if not codigo_guia:
        flash('No se proporcionó código de guía.', 'danger')
        # Redirigir a una página de error o lista, ya que no hay guía para volver
        return redirect(url_for('misc.listar_guias'))

    # Directorio para guardar fotos de esta guía
    guia_fotos_dir_rel = os.path.join('uploads', codigo_guia)
    guia_fotos_dir_abs = os.path.join(current_app.static_folder, guia_fotos_dir_rel)
    try:
        os.makedirs(guia_fotos_dir_abs, exist_ok=True)
        logger.info(f"Directorio asegurado/creado para fotos: {guia_fotos_dir_abs}")
    except OSError as e:
        logger.error(f"Error creando directorio {guia_fotos_dir_abs}: {e}")
        flash(f'Error creando directorio para fotos: {e}', 'danger')
        return redirect(url_for('.clasificacion', codigo=codigo_guia, respetar_codigo=True)) # Volver al form

    rutas_fotos_guardadas = []
    # Procesar hasta 3 fotos
    for i in range(1, 4):
        file_key = f'foto-{i}'
        if file_key in request.files:
            file = request.files[file_key]
            if file and file.filename and es_archivo_imagen(file.filename):
                try:
                    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{file.filename}")
                    save_path_abs = os.path.join(guia_fotos_dir_abs, filename)
                    file.save(save_path_abs)
                    # Guardar ruta relativa a 'static' para usar en la BD y templates
                    save_path_rel = os.path.join(guia_fotos_dir_rel, filename).replace('\\', '/')
                    rutas_fotos_guardadas.append(save_path_rel)
                    logger.info(f"Foto '{filename}' guardada en '{save_path_abs}' (rel: {save_path_rel})")
                except Exception as e:
                    logger.error(f"Error guardando archivo {file.filename}: {e}")
                    flash(f'Error guardando la foto {i}: {e}', 'warning')
            elif file and file.filename:
                 logger.warning(f"Archivo '{file.filename}' omitido (no es imagen).")
        else:
            logger.info(f"Campo de archivo '{file_key}' no encontrado en la solicitud.")


    # Recopilar datos de clasificación manual del formulario
    clasificacion_manual = {
        'verdes': float(request.form.get('verdes', 0) or 0),
        'sobremaduros': float(request.form.get('sobremaduros', 0) or 0),
        # CORRECCIÓN: tomar el valor de 'dano_corona' y asignarlo a 'danio_corona'
        'danio_corona': float(request.form.get('dano_corona', 0) or 0),
        'pedunculo_largo': float(request.form.get('pedunculo_largo', 0) or 0),
        'podridos': float(request.form.get('podridos', 0) or 0)
    }

    logger.info(f"Clasificación manual recibida para {codigo_guia}: {clasificacion_manual}")
    # Validar que el total no sea excesivo (opcional)
    # if total_manual > 100:
    #    flash('La suma de porcentajes manuales no puede exceder 100.', 'warning')
    #    # Considerar si redirigir o continuar

    # Preparar datos para guardar en la BD
    datos_para_guardar = {
        'codigo_guia': codigo_guia,
        'clasificacion_manual_json': json.dumps(clasificacion_manual),
        'verde_manual': clasificacion_manual.get('verdes'),
        'sobremaduro_manual': clasificacion_manual.get('sobremaduros'),
        'danio_corona_manual': clasificacion_manual.get('danio_corona'),
        'pendunculo_largo_manual': clasificacion_manual.get('pedunculo_largo'),
        'podrido_manual': clasificacion_manual.get('podridos'),
        'timestamp_clasificacion_utc': datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S'),
        'estado': 'completado'  # <-- Unificado
    }

    # *** LLAMADA EXPLÍCITA PARA GUARDAR CLASIFICACIÓN ***
    # Usar db_operations.store_clasificacion en lugar de depender de update_datos_guia
    # Pasar también las rutas de las fotos guardadas
    exito_guardado = store_clasificacion(datos_para_guardar, fotos=rutas_fotos_guardadas)

    if exito_guardado:
        logger.info(f"Clasificación manual y rutas de fotos guardadas exitosamente para guía {codigo_guia}.")
        flash('Clasificación manual y fotos guardadas correctamente.', 'success')
        # *** CORRECCIÓN DE REDIRECCIÓN ***
        # Redirigir a la vista centralizada según el plan
        return redirect(url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia))
    else:
        logger.error(f"Error al guardar la clasificación manual/fotos para guía {codigo_guia} en la base de datos.")
        flash('Error al guardar la clasificación en la base de datos.', 'danger')
        # Volver al formulario de clasificación en caso de error de guardado
        return redirect(url_for('.clasificacion', codigo=codigo_guia, respetar_codigo=True))

# ... (resto de funciones del blueprint) ...





@bp.route('/registrar_clasificacion_api', methods=['POST'])
def registrar_clasificacion_api():
    """
    Registra los resultados de la clasificación
    """
    try:
        logger.info("Iniciando registro de clasificación")
        
        if 'codigo_guia' not in request.form:
            logger.error("No se proporcionó el código de guía")
            return jsonify({'success': False, 'message': 'No se proporcionó el código de guía'}), 400
        
        codigo_guia = request.form['codigo_guia']
        logger.info(f"Registrando clasificación para guía: {codigo_guia}")
        
        # Obtener datos de clasificación
        verdes = request.form.get('verdes', '0')
        sobremaduros = request.form.get('sobremaduros', '0')
        dano_corona = request.form.get('dano_corona', '0')
        pedunculo_largo = request.form.get('pedunculo_largo', '0')
        podridos = request.form.get('podridos', '0')  # Nuevo campo para racimos podridos
        
        # Crear directorios para imágenes de clasificación si no existen
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        imagenes_dir = os.path.join(current_app.static_folder, 'uploads', 'clasificacion')
        os.makedirs(clasificaciones_dir, exist_ok=True)
        os.makedirs(imagenes_dir, exist_ok=True)
        
        # Guardar las imágenes permanentemente si se proporcionaron
        imagenes = []
        for i in range(1, 4):
            key = f'foto-{i}'
            if key in request.files and request.files[key].filename:
                file = request.files[key]
                filename = f"clasificacion_{codigo_guia}_{i}.jpg"
                filepath = os.path.join(imagenes_dir, filename)
                file.save(filepath)
                imagenes.append(filepath)
                logger.info(f"Imagen {i} guardada permanentemente: {filepath}")
        
        # Crear objeto con los datos de clasificación
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        
        if not datos_guia:
            logger.error(f"No se encontraron datos de guía para clasificación: {codigo_guia}")
            return jsonify({'success': False, 'message': 'No se encontraron datos de la guía'}), 404
        
        # Estructurar datos de clasificación para guardar
        clasificacion_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': datos_guia.get('codigo_proveedor') or datos_guia.get('codigo'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor') or datos_guia.get('nombre'),
            'cantidad_racimos': datos_guia.get('cantidad_racimos') or datos_guia.get('racimos'),
            'peso_bruto': datos_guia.get('peso_bruto'),
            'timestamp_clasificacion_utc': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'), # Usar timestamp UTC
            'verdes': float(verdes),
            'sobremaduros': float(sobremaduros),
            'dano_corona': float(dano_corona),
            'pedunculo_largo': float(pedunculo_largo),
            'podridos': float(podridos),  # Agregar el campo de racimos podridos
            'imagenes': [os.path.basename(img) for img in imagenes],
            'estado': 'completado'  # <-- Unificado
        }
        
        # Guardar datos en archivo JSON
        clasificacion_file = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
        with open(clasificacion_file, 'w', encoding='utf-8') as f:
            json.dump(clasificacion_data, f, indent=4, ensure_ascii=False)
        
        logger.info(f"Datos de clasificación guardados en: {clasificacion_file}")
        
        # Actualizar el estado en los datos de la guía
        datos_guia['estado_actual'] = 'clasificacion_completada'
        datos_guia['clasificacion_manual'] = {
            'verdes': float(verdes),
            'sobremaduros': float(sobremaduros),
            'dano_corona': float(dano_corona),
            'pedunculo_largo': float(pedunculo_largo),
            'podridos': float(podridos)
        }
        #datos_guia['fecha_clasificacion'] = datetime.now().strftime('%d/%m/%Y')
        #datos_guia['hora_clasificacion'] = datetime.now().strftime('%H:%M:%S')
        datos_guia['imagenes_clasificacion'] = [os.path.join('uploads', 'clasificacion', os.path.basename(img)) for img in imagenes]
        utils_instance.update_datos_guia(codigo_guia, datos_guia)
        
        # Actualizar el archivo HTML con el nuevo estado
        try:
            # Intentar renderizar el template
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            html_filename = f'guia_{codigo_guia}.html'
            html_path = os.path.join(current_app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Archivo HTML de guía actualizado correctamente: {html_path}")
        except Exception as template_error:
            # Si hay error en el template, registrarlo pero seguir adelante
            logger.error(f"Error al renderizar el template: {str(template_error)}")
            logger.error(traceback.format_exc())
            # No dejar que este error detenga el proceso
            
        logger.info(f"Clasificación registrada exitosamente para guía: {codigo_guia}")
        
        # Responder con éxito y múltiples opciones de redirección
        try:
            redirect_url = url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia)
        except Exception as url_error:
            logger.error(f"Error generando URL con url_for: {str(url_error)}")
            redirect_url = f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}"
            
        # Incluir URLs directas como respaldo
        direct_url = f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}"
        
        return jsonify({
            'success': True,
            'message': 'Clasificación registrada exitosamente',
            'redirect_url': redirect_url,
            'direct_url': direct_url,
            'codigo_guia': codigo_guia
        })
    
    except Exception as e:
        logger.error(f"Error al registrar clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

# Definición de la función completa modificada
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
            # Asumiendo que DirectRoboflowClient está definido o importado correctamente
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
        'imagenes_procesadas': [], # Lista para detalles por imagen
        'errores': [], # Lista para errores generales o por imagen
        'tiempo_total_procesamiento_seg': 0.0
        # 'clasificacion_automatica' se añadirá después del bucle
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

    # Definir class_mapping una vez fuera del bucle para la agregación
    # ESTE MAPEADO ES CRÍTICO - debe coincidir con las clases de TU MODELO y la respuesta API
    class_mapping = {
       'verde': 'verde',
       'racimos verdes': 'verde', # Clave exacta de tu log
       'sobremaduro': 'sobremaduro',
       'racimo sobremaduro': 'sobremaduro', # Clave exacta de tu log
       'danio_en_corona': 'danio_corona', # Nombre común Roboflow
       'racimo daño en corona': 'danio_corona', # Clave exacta de tu log (con ñ) -> Ojo con encoding si usas 'ñ'
       'racimo dano en corona': 'danio_corona', # Variante sin 'ñ'
       'pendunculo_largo': 'pendunculo_largo', # Nombre común Roboflow
       'racimo pedunculo largo': 'pendunculo_largo', # Clave exacta de tu log
       'fruta_podrida': 'podrido', # Nombre común Roboflow
       'racimo podrido': 'podrido', # Clave exacta de tu log
       'maduro': 'maduro', # Añadir 'maduro' si es una clase posible
       # Añade más alias o nombres exactos si es necesario
    }
    logger.info(f"[DIAG RESPONSE PROC] Diccionario class_mapping definido globalmente para la función: {class_mapping}")

    # --- BUCLE DE PROCESAMIENTO DE IMÁGENES ---
    for idx, img_path in enumerate(fotos_paths):
        start_time_img = time.time()
        img_filename = os.path.basename(img_path)
        logger.info(f"[DIAG Param] Procesando imagen {idx+1}/{len(fotos_paths)}: {img_filename}")

        image_result = {
            'indice': idx + 1, 'numero': idx + 1,
            'nombre_original': img_filename, 'ruta_original': img_path,
            'imagen_original': None, # Se calcula abajo
            'timestamp_inicio': get_utc_timestamp_str(), 'estado': 'pendiente',
            'mensaje_error': None, 'traceback': None,
            'tiempo_procesamiento_seg': 0,
            'detecciones': [], 'conteo_por_clase': {}, 'conteo_categorias': {},
            'total_racimos_imagen': 0, 'total_racimos': 0, 'num_racimos_detectados': 0, # Inicializar todos
            'ruta_anotada': None, 'imagen_annotated': None,
            'ruta_clasificada_rf': None # Para la imagen de Roboflow
        }

        try:
            # Calcular ruta relativa imagen original
            try:
                static_folder_path = current_app.static_folder
                rel_original_path = os.path.relpath(img_path, static_folder_path)
                image_result['imagen_original'] = rel_original_path.replace(os.sep, '/')
            except Exception as rel_orig_err:
                logger.error(f"Error calculando ruta relativa para imagen original {img_filename}: {rel_orig_err}")
                image_result['imagen_original'] = img_path # Fallback

            # Validación y apertura de imagen
            if not os.path.exists(img_path): raise FileNotFoundError(f"Archivo no encontrado: {img_path}")
            if not es_archivo_imagen(img_filename): raise ValueError("Archivo no es imagen válida.")
            try:
                with Image.open(img_path) as img_pil: img_pil.verify()
                with Image.open(img_path) as img_pil:
                    img_pil.load()
                    if img_pil.mode != 'RGB': img_pil = img_pil.convert('RGB')
                    img_width, img_height = img_pil.size
            except Exception as img_err: raise ValueError(f"Error abriendo imagen: {img_err}")

            # Llamada a Roboflow
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

            # --- PROCESAMIENTO RESPUESTA ROBOFLOW ---
            logger.info(f"[DIAG RESPONSE PROC] Procesando respuesta API para img {idx+1}...")
            try: logger.info(f"[DIAG RESPONSE PROC] Respuesta API Completa: {json.dumps(api_response, indent=2)}")
            except: logger.info(f"[DIAG RESPONSE PROC] Respuesta API Completa (raw): {api_response}")

            # (class_mapping ya está definido fuera del bucle)
            claves_internas_unicas = set(class_mapping.values())
            conteo_clases_directo = {clave: 0 for clave in claves_internas_unicas}
            num_racimos_detectados_en_imagen = 0
            detections_processed = [] # Para BBOX

            # Extraer CONTEOS DIRECTOS
            primary_output = {}
            if isinstance(api_response, dict) and 'outputs' in api_response and isinstance(api_response['outputs'], list) and api_response['outputs']:
                primary_output = api_response['outputs'][0]
                if not isinstance(primary_output, dict):
                     logger.warning(f"[DIAG RESPONSE PROC] outputs[0] no es dict. Buscando en raíz.")
                     primary_output = api_response
            elif isinstance(api_response, dict):
                 logger.info("[DIAG RESPONSE PROC] No se encontró 'outputs'. Buscando en raíz.")
                 primary_output = api_response
            else:
                 logger.warning(f"[DIAG RESPONSE PROC] Formato respuesta API inesperado ({type(api_response)}).")

            if isinstance(primary_output, dict):
                 logger.info(f"[DIAG RESPONSE PROC] Buscando conteos directos en keys: {list(primary_output.keys())}")
                 for key_rf, value_rf in primary_output.items():
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

            # Extraer PREDICCIONES BBOX (si existen)
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

            # Asignación Final a image_result
            image_result['detections'] = detections_processed
            image_result['conteo_por_clase'] = conteo_clases_directo
            image_result['num_racimos_detectados'] = num_racimos_detectados_en_imagen # Clave principal
            image_result['total_racimos_imagen'] = num_racimos_detectados_en_imagen # Alias
            image_result['total_racimos'] = num_racimos_detectados_en_imagen # Alias

            logger.info(f"Asignación final img {idx+1} - num_racimos_detectados: {image_result['num_racimos_detectados']}")

            # Calcular porcentajes POR IMAGEN para template detalles
            total_img_correcto = num_racimos_detectados_en_imagen
            conteo_categorias_template = {}
            for clase_int, cantidad in conteo_clases_directo.items():
                 porcentaje = round((cantidad / total_img_correcto) * 100, 1) if total_img_correcto > 0 else 0.0
                 conteo_categorias_template[clase_int] = {'cantidad': cantidad, 'porcentaje': porcentaje}
            image_result['conteo_categorias'] = conteo_categorias_template

            # Generar imagen anotada localmente (usa BBOX de detections_processed)
            try:
                annotated_img_filename = f"{os.path.splitext(img_filename)[0]}_annotated.jpg"
                annotated_img_path_abs = os.path.join(guia_fotos_dir, annotated_img_filename)
                generate_annotated_image(img_path, detections_processed, output_path=annotated_img_path_abs)
                try:
                    static_folder_path = current_app.static_folder
                    rel_annotated_path = os.path.relpath(annotated_img_path_abs, static_folder_path)
                    rel_annotated_path_web = rel_annotated_path.replace(os.sep, '/')
                    image_result['ruta_anotada'] = rel_annotated_path_web
                    image_result['imagen_annotated'] = rel_annotated_path_web
                    logger.info(f"Imagen anotada local generada, ruta relativa: {rel_annotated_path_web}")
                except Exception as rel_path_err:
                     logger.error(f"Error calculando ruta relativa anotada: {rel_path_err}")
                     image_result['ruta_anotada'] = annotated_img_path_abs # Fallback
                     image_result['imagen_annotated'] = annotated_img_path_abs
            except Exception as annotate_err:
                logger.error(f"Error generando imagen anotada local {img_filename}: {annotate_err}")
                image_result['mensaje_error'] = (image_result['mensaje_error'] or "") + f"; Error anotación local: {annotate_err}"

            # Guardar Imagen Etiquetada de Roboflow (label_visualization_1)
            imagen_clasificada_rf_rel_path = None
            try:
                img_labeled_base64 = None
                if isinstance(primary_output, dict):
                    vis_data = primary_output.get('label_visualization_1')
                    if isinstance(vis_data, dict): img_labeled_base64 = vis_data.get('value')
                    elif not img_labeled_base64 and 'outputs' in primary_output: # Check outputs again if needed
                         # ... (logic to check outputs[0]['label_visualization_1'] if needed) ...
                         pass

                if img_labeled_base64:
                    logger.info(f"[DIAG SAVE RF IMG] Base64 'label_visualization_1' encontrado img {idx+1}.")
                    img_data = base64.b64decode(img_labeled_base64)
                    labeled_rf_filename = f"{os.path.splitext(img_filename)[0]}_labeled_rf.jpg"
                    labeled_rf_path_abs = os.path.join(guia_fotos_dir, labeled_rf_filename)
                    with open(labeled_rf_path_abs, 'wb') as f_label: f_label.write(img_data)
                    logger.info(f"Imagen Roboflow etiquetada guardada: {labeled_rf_path_abs}")
                    try:
                        static_folder_path = current_app.static_folder
                        rel_labeled_rf_path = os.path.relpath(labeled_rf_path_abs, static_folder_path)
                        imagen_clasificada_rf_rel_path = rel_labeled_rf_path.replace(os.sep, '/')
                        logger.info(f"Ruta relativa imagen Roboflow etiquetada: {imagen_clasificada_rf_rel_path}")
                    except Exception as rel_rf_err: logger.error(f"Error ruta relativa img RF: {rel_rf_err}")
                else: logger.warning(f"No se encontró base64 para 'label_visualization_1' img {idx+1}.")

            except Exception as save_rf_err:
                logger.error(f"Error guardando img etiquetada RF {idx+1}: {save_rf_err}")
                logger.error(traceback.format_exc())

            image_result['ruta_clasificada_rf'] = imagen_clasificada_rf_rel_path
            image_result['estado'] = 'procesada_ok'

        # --- Manejo de Errores por Imagen ---
        except Exception as e:
            logger.error(f"Error procesando imagen {idx+1} ({img_filename}): {str(e)}")
            tb_str = traceback.format_exc(); logger.error(tb_str)
            image_result['estado'] = 'error_procesamiento'
            image_result['mensaje_error'] = str(e)
            image_result['traceback'] = tb_str
            results_data['errores'].append({'indice': idx + 1, 'nombre_original': img_filename,
                                           'mensaje_error': str(e), 'traceback': tb_str})
        finally:
            end_time_img = time.time()
            image_result['tiempo_procesamiento_seg'] = round(end_time_img - start_time_img, 2)
            # --- MODIFICACIÓN: Usar deepcopy ---
            results_data['imagenes_procesadas'].append(copy.deepcopy(image_result))
            # ------------------------------------

    # --- Fin del Bucle de Imágenes ---

    # --- INICIO: Calcular Resumen Agregado para 'clasificacion_automatica' ---
    logger.info("[AGREGACIÓN] Calculando resumen agregado de clasificación automática...")
    summary_clasificacion_automatica = {}
    claves_internas_unicas = set(class_mapping.values()) # Usa el mapping definido antes
    total_counts = {key: 0 for key in claves_internas_unicas}
    grand_total_racimos = 0

    for img_res in results_data.get('imagenes_procesadas', []):
        grand_total_racimos += img_res.get('num_racimos_detectados', 0)
        conteo_imagen = img_res.get('conteo_por_clase', {})
        for clase_interna, cantidad in conteo_imagen.items():
            if clase_interna in total_counts:
                total_counts[clase_interna] += cantidad
            else:
                 logger.warning(f"[AGREGACIÓN] Clase interna inesperada: {clase_interna}. Ignorando.")

    logger.info(f"[AGREGACIÓN] Total racimos (todas imgs): {grand_total_racimos}")
    logger.info(f"[AGREGACIÓN] Conteos totales por clase: {total_counts}")

    # Mapeo inverso clave interna -> clave JSON para el resumen final
    db_key_to_json_key = {
        'verde': 'verdes',
        'sobremaduro': 'sobremaduros',
        'danio_corona': 'danio_corona', # Clave JSON consistente
        'pendunculo_largo': 'pendunculo_largo', # Clave JSON consistente
        'podrido': 'podridos',
        'maduro': 'maduros' # Si existe
    }

    for clase_interna, total_cantidad in total_counts.items():
        porcentaje_final = round((total_cantidad / grand_total_racimos) * 100, 1) if grand_total_racimos > 0 else 0.0
        json_key = db_key_to_json_key.get(clase_interna)
        if json_key:
            # Estructura que espera guardar_clasificacion_final
            summary_clasificacion_automatica[json_key] = {'porcentaje': porcentaje_final}
            # summary_clasificacion_automatica[json_key]['cantidad_total'] = total_cantidad # Opcional
        else:
            logger.warning(f"[AGREGACIÓN] No se encontró mapeo JSON para clase interna: {clase_interna}.")

    # Añadir el resumen al diccionario principal
    if summary_clasificacion_automatica:
        results_data['clasificacion_automatica'] = summary_clasificacion_automatica
        logger.info(f"[AGREGACIÓN] Resumen 'clasificacion_automatica' añadido a results_data: {summary_clasificacion_automatica}")
    else:
         logger.warning("[AGREGACIÓN] No se generó resumen 'clasificacion_automatica'.")
    # --- FIN: Calcular Resumen Agregado ---

    # Calcular tiempo total final
    end_time_total = time.time()
    results_data['tiempo_total_procesamiento_seg'] = round(end_time_total - start_time_total, 2)

    # Log antes de guardar JSON
    logger.info(f"[DIAG DUMP PRE-SAVE] Contenido final results_data ANTES de json.dump:")
    try:
        # Usar default=str para manejar objetos no serializables si los hubiera
        logger.info(json.dumps(results_data, indent=2, ensure_ascii=False, default=str))
    except Exception as log_dump_err:
        logger.error(f"Error al hacer log dump de results_data: {log_dump_err}")
        logger.info(f"Intentando log dump parcial: { {k: v for k, v in results_data.items() if k != 'imagenes_procesadas'} }")


    try:
        # Guardar JSON
        json_dir = os.path.dirname(json_path)
        os.makedirs(json_dir, exist_ok=True)
        logger.info(f"Asegurando directorio para JSON: {json_dir}")
        logger.info(f"Intentando escribir JSON en: {json_path}")
        with open(json_path, 'w', encoding='utf-8') as f:
            # Usar default=str aquí también por seguridad
            json.dump(results_data, f, ensure_ascii=False, indent=4, default=str)
            f.flush()
            if hasattr(os, 'fsync'):
                try: os.fsync(f.fileno()); logger.info("[DIAG WRITE] os.fsync() ejecutado.")
                except OSError as fsync_err: logger.warning(f"Error en os.fsync(): {fsync_err}") # Cambiado a warning
            else: logger.info("[DIAG WRITE] os.fsync() no disponible.")
        logger.info("[DIAG WRITE] Escritura JSON completada.")

        # Verificar existencia y tamaño
        time.sleep(0.5)
        if os.path.exists(json_path):
            file_size = os.path.getsize(json_path)
            logger.info(f"[DIAG WRITE] Verificación post-escritura: OK (Tamaño: {file_size} bytes)")
            if file_size == 0: logger.warning("[DIAG WRITE] Advertencia! Archivo JSON con tamaño 0.")
        else:
            logger.error(f"[DIAG WRITE] ¡ERROR CRÍTICO! Archivo JSON NO existe después de escribir: {json_path}")

    except Exception as e:
        logger.error(f"Error crítico escribiendo JSON en {json_path}: {str(e)}")
        logger.error(traceback.format_exc())
        # Considerar devolver error aquí si la escritura falla

    # Actualizar la base de datos si es necesario (ej. timestamp, estado)
    # Esta parte puede necesitar lógica adicional o hacerse en otro lugar

    success = len(results_data['errores']) == 0
    message = "Procesamiento completado." if success else "Procesamiento completado con errores."

    return success, message, results_data



@bp.route('/clasificaciones')
def listar_clasificaciones():
    # Redirigir a la nueva ruta
    return redirect('/clasificaciones/lista')



@bp.route('/clasificaciones/lista')
def listar_clasificaciones_filtradas():
    try:
        # Obtener parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        estado = request.args.get('estado', '')
        
        clasificaciones = []
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        
        # Asegurar que el directorio existe
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Importar función para obtener registros de la base de datos
        from db_utils import get_entry_record_by_guide_code
        
        # Crear un diccionario para rastrear códigos de guía base ya procesados
        # Esto evitará procesar múltiples versiones del mismo código base
        codigos_base_procesados = {}
        
        # Leer todos los archivos JSON de clasificaciones
        for filename in os.listdir(clasificaciones_dir):
            if filename.startswith('clasificacion_') and filename.endswith('.json'):
                try:
                    with open(os.path.join(clasificaciones_dir, filename), 'r') as f:
                        clasificacion_data = json.load(f)
                    
                    # Extraer el código de guía del nombre del archivo
                    codigo_guia = filename.replace('clasificacion_', '').replace('.json', '')
                    
                    # Extraer el código base (sin timestamp ni versión)
                    codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                    
                    # Si ya procesamos este código base y tiene un timestamp más reciente, omitir este archivo
                    if codigo_base in codigos_base_procesados:
                        # Comparar timestamps si existen
                        if '_' in codigo_guia and '_' in codigos_base_procesados[codigo_base]:
                            timestamp_actual = codigo_guia.split('_')[1] if len(codigo_guia.split('_')) > 1 else ''
                            timestamp_previo = codigos_base_procesados[codigo_base].split('_')[1] if len(codigos_base_procesados[codigo_base].split('_')) > 1 else ''
                            
                            # Si el timestamp actual es menor que el previo, omitir este archivo
                            if timestamp_actual < timestamp_previo:
                                logger.info(f"Omitiendo clasificación duplicada anterior: {codigo_guia}, ya existe una más reciente: {codigos_base_procesados[codigo_base]}")
                                continue
                    
                    # Registrar este código base con su versión completa
                    codigos_base_procesados[codigo_base] = codigo_guia
                    
                    # Inicializar valores por defecto
                    nombre_proveedor_actual = 'No disponible'
                    codigo_proveedor_actual = ''
                    cantidad_racimos = 'No disponible'
                    
                    # 1. Primero intentar obtener de la base de datos - PRIORIDAD MÁXIMA
                    entry_record = get_entry_record_by_guide_code(codigo_guia)
                    
                    if entry_record:
                        # Obtener datos directamente con las claves específicas
                        nombre_proveedor_actual = entry_record.get('nombre_proveedor', 'No disponible')
                        codigo_proveedor_actual = entry_record.get('codigo_proveedor', '')
                        cantidad_racimos = entry_record.get('cantidad_racimos', 'No disponible')
                        
                        # Log para debug
                        logger.info(f"Datos de DB para {codigo_guia}: Proveedor={nombre_proveedor_actual}, Racimos={cantidad_racimos}")
                    else:
                        # 2. Si no hay en DB, extraer código de proveedor del código de guía
                        if '_' in codigo_guia:
                            codigo_base = codigo_guia.split('_')[0]
                            # Asegurarse de que termine con A mayúscula si corresponde
                            if re.match(r'\d+[aA]?$', codigo_base):
                                if codigo_base.endswith('a'):
                                    codigo_proveedor_actual = codigo_base[:-1] + 'A'
                                elif not codigo_base.endswith('A'):
                                    codigo_proveedor_actual = codigo_base + 'A'
                                else:
                                    codigo_proveedor_actual = codigo_base
                        else:
                            codigo_proveedor_actual = codigo_base
                        codigo_proveedor_actual = codigo_guia
                    
                    # 3. Buscar datos usando get_utils_instance
                    try:
                        utils_instance = get_utils_instance()
                        datos_registro = utils_instance.get_datos_registro(codigo_guia)
                        if datos_registro:
                            nombre_proveedor_actual = datos_registro.get("nombre_proveedor", "No disponible")
                            if not codigo_proveedor_actual:
                                codigo_proveedor_actual = datos_registro.get("codigo_proveedor", "")
                            cantidad_racimos = datos_registro.get("cantidad_racimos", "No disponible")

                        # Log para debug
                        logger.info(f"Datos de archivo para {codigo_guia}: Proveedor={nombre_proveedor_actual}, Racimos={cantidad_racimos}")
                    except Exception as e:
                        logger.warning(f"Error obteniendo datos de registro desde archivo: {str(e)}")
                    
                    # 4. Buscar datos en el propio archivo de clasificación como último recurso
                    if nombre_proveedor_actual == 'No disponible' and 'nombre_proveedor' in clasificacion_data:
                            nombre_proveedor_actual = clasificacion_data.get('nombre_proveedor', 'No disponible')
                    
                    if not codigo_proveedor_actual and 'codigo_proveedor' in clasificacion_data:
                            codigo_proveedor_actual = clasificacion_data.get('codigo_proveedor', '')
                    
                    if cantidad_racimos == 'No disponible' and 'cantidad_racimos' in clasificacion_data:
                            cantidad_racimos = clasificacion_data.get('cantidad_racimos', 'No disponible')
                    
                    # Limpiar nombres inadecuados
                    if nombre_proveedor_actual in ['No disponible', 'del Agricultor', '', None]:
                        # Como último recurso, usar una descripción basada en el código
                        if codigo_proveedor_actual:
                            nombre_proveedor_actual = f"Proveedor {codigo_proveedor_actual}"
                        else:
                            nombre_proveedor_actual = "Proveedor sin nombre"
                    
                    # Preparar los datos para la plantilla
                    item = {
                        'codigo_guia': codigo_guia,
                        'nombre_proveedor': nombre_proveedor_actual,
                        'codigo_proveedor': codigo_proveedor_actual,
                        'fecha_clasificacion': clasificacion_data.get('fecha_registro', 'No disponible'),
                        'hora_clasificacion': clasificacion_data.get('hora_registro', 'No disponible'),
                        'cantidad_racimos': cantidad_racimos if cantidad_racimos else 'No disponible',
                        'estado': clasificacion_data.get('estado', 'en_proceso'),
                        'manual_completado': 'clasificacion_manual' in clasificacion_data and clasificacion_data['clasificacion_manual'] is not None,
                        'automatica_completado': 'clasificacion_automatica' in clasificacion_data and clasificacion_data['clasificacion_automatica'] is not None,
                        'automatica_en_proceso': clasificacion_data.get('estado') == 'en_proceso'
                    }
                    
                    # Aplicar filtros
                    if fecha_desde and item['fecha_clasificacion'] < fecha_desde:
                        continue
                    if fecha_hasta and item['fecha_clasificacion'] > fecha_hasta:
                        continue
                    if codigo_proveedor and codigo_proveedor.lower() not in item['codigo_proveedor'].lower():
                        continue
                    if nombre_proveedor and nombre_proveedor.lower() not in item['nombre_proveedor'].lower():
                        continue
                    if estado and estado != item['estado']:
                        continue
                        
                    clasificaciones.append(item)
                except Exception as e:
                    logger.error(f"Error procesando archivo {filename}: {str(e)}")
                    continue
        
        # Ordenar por fecha y hora convertidas a objetos datetime
        from datetime import datetime
        
        def parse_datetime_str(clasificacion):
            try:
                # Parsear fecha en formato DD/MM/YYYY y hora en formato HH:MM:SS
                fecha_str = clasificacion.get('fecha_clasificacion', '01/01/1970')
                hora_str = clasificacion.get('hora_clasificacion', '00:00:00')
                
                if '/' in fecha_str:  # Formato DD/MM/YYYY
                    dia, mes, anio = map(int, fecha_str.split('/'))
                    fecha_obj = datetime(anio, mes, dia)
                else:  # Alternativa formato YYYY-MM-DD
                    fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d')
                
                # Asegurar que hora_str tiene el formato esperado
                if not hora_str or hora_str == 'No disponible':
                    hora_str = '00:00:00'
                
                # Dividir la hora, asegurando que tiene suficientes partes
                hora_parts = hora_str.split(':')
                horas = int(hora_parts[0]) if len(hora_parts) > 0 else 0
                minutos = int(hora_parts[1]) if len(hora_parts) > 1 else 0
                segundos = int(hora_parts[2]) if len(hora_parts) > 2 else 0
                
                # Combinar fecha y hora
                return datetime(
                    fecha_obj.year, fecha_obj.month, fecha_obj.day,
                    horas, minutos, segundos
                )
            except Exception as e:
                logger.error(f"Error al parsear fecha/hora para clasificación: {str(e)}")
                return datetime(1970, 1, 1)  # Fecha más antigua como fallback
        
        # Ordenar por fecha y hora parseadas en orden descendente (más recientes primero)
        clasificaciones.sort(key=parse_datetime_str, reverse=True)
        
        return render_template('clasificaciones_lista.html', 
                               clasificaciones=clasificaciones,
                               filtros={
                                   'fecha_desde': fecha_desde,
                                   'fecha_hasta': fecha_hasta,
                                   'codigo_proveedor': codigo_proveedor,
                                   'nombre_proveedor': nombre_proveedor,
                                   'estado': estado
                               })
    except Exception as e:
        logger.error(f"Error listando clasificaciones: {str(e)}")
        return render_template('error.html', mensaje=f"Error al listar clasificaciones: {str(e)}")



# ... (importaciones y código anterior) ...

@bp.route('/ver_resultados_clasificacion/<path:url_guia>')
def ver_resultados_clasificacion(url_guia):
    """Muestra los resultados consolidados de la clasificación."""
    logger.info(f"Accediendo a resultados de clasificación para: {url_guia}")
    start_time = time.time()

    utils = get_utils_instance()
    datos_guia = utils.get_datos_guia(url_guia)

    if not datos_guia:
        flash(f"No se encontraron datos para la guía {url_guia}", 'error')
        return redirect(url_for('clasificacion.listar_clasificaciones_filtradas'))

    codigo_guia = datos_guia.get('codigo_guia', url_guia)
    codigo_proveedor = datos_guia.get('codigo_proveedor', 'N/A')
    nombre_proveedor = datos_guia.get('nombre_proveedor', 'N/A')
    peso_bruto = datos_guia.get('peso_bruto', 'N/A')
    cantidad_racimos = datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'N/A')

    # Convertir timestamps UTC a local Bogota para mostrar
    timestamp_clasificacion_utc_str = datos_guia.get('timestamp_clasificacion_utc')
    fecha_clasificacion = format_datetime_filter(timestamp_clasificacion_utc_str, '%d/%m/%Y') if timestamp_clasificacion_utc_str else 'N/A'
    hora_clasificacion = format_datetime_filter(timestamp_clasificacion_utc_str, '%H:%M:%S') if timestamp_clasificacion_utc_str else 'N/A'

    clasificacion_manual = datos_guia.get('clasificacion_manual', {})

    # --- Inicio: Lógica Mejorada para Detalles Automáticos ---
    clasificacion_automatica = {} # Datos leídos de la DB (si existen)
    total_racimos_detectados_json = 0 # Total acumulado desde el JSON
    hay_detalles_por_foto_json = False # Flag específico del JSON

    # Construir ruta esperada del archivo JSON de clasificación automática
    json_path_abs = None
    try:
        # Directorio base relativo (ajustar si es necesario)
        base_dir_relativo = os.path.join('uploads', codigo_guia)
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path_abs = os.path.join(current_app.static_folder, base_dir_relativo, json_filename)
        logger.info(f"[DIAG] Buscando archivo JSON de detalles en: {json_path_abs}")

        # --- Espera corta antes de leer (para descartar problemas de timing/caché del SO) ---
        logger.info("[DIAG READ] Iniciando pausa de 0.5s antes de intentar leer JSON...")
        time.sleep(0.5) # Esperar medio segundo
        logger.info("[DIAG READ] Pausa completada.")
        # ----------------------------------------------------------------------------

        hay_detalles_por_foto_json = False # Inicializar fuera del bloque try
        imagenes_procesadas = []          # Inicializar fuera del bloque try
        total_racimos_detectados_json = 0 # Inicializar fuera del bloque try

        if os.path.exists(json_path_abs):
             logger.info(f"[DIAG READ] Archivo JSON encontrado. Intentando leer...")
             try:
                 with open(json_path_abs, 'r', encoding='utf-8') as f:
                     # --- Log del tamaño del archivo ---
                     file_size = os.path.getsize(json_path_abs)
                     logger.info(f"[DIAG READ] Tamaño del archivo JSON antes de json.load: {file_size} bytes")
                     if file_size == 0:
                         logger.warning("[DIAG READ] ¡Advertencia! El archivo JSON tiene tamaño 0 antes de intentar leerlo.")
                     # ---------------------------------
                     json_data = json.load(f)
                     logger.info(f"[DIAG READ] Contenido JSON cargado exitosamente vía json.load().")

                 # --- Log del contenido completo justo después de cargar ---
                 # Usar json.dumps para formatear la salida del log
                 try:
                     json_data_str = json.dumps(json_data, indent=2)
                     logger.info(f"[DIAG READ RAW CONTENT DUMP] Contenido completo leído y parseado del JSON:\n{json_data_str}")
                 except Exception as dump_err:
                     logger.error(f"[DIAG READ RAW CONTENT DUMP] Error al dumpear el json_data leído para logging: {dump_err}")
                     logger.info(f"[DIAG READ RAW CONTENT DUMP] json_data (tipo {type(json_data)}): {json_data}")
                 # ---------------------------------------------------------

                 # Verificar si hay imágenes procesadas y si alguna tiene detecciones
                 imagenes_procesadas = json_data.get('imagenes_procesadas', []) # Obtener la lista
                 if isinstance(imagenes_procesadas, list) and len(imagenes_procesadas) > 0:
                      logger.info(f"[DIAG READ] Verificación JSON: Encontradas {len(imagenes_procesadas)} imágenes procesadas en la estructura cargada. Iniciando bucle de verificación...")
                      # Reiniciar contadores y flags aquí DENTRO del 'if' para asegurar que solo se usan si hay datos
                      total_racimos_detectados_json = 0
                      hay_detalles_por_foto_json = False

                      for i, img in enumerate(imagenes_procesadas):
                          # --- LOG DE DIAGNÓSTICO ADICIONAL ---
                          logger.info(f"[DIAG READ DETAIL] Imagen {i}: Contenido completo del diccionario 'img' iterado: {img}")
                          # --- FIN LOG ADICIONAL ---

                          # --- LOG DE DIAGNÓSTICO ---
                          valor_raw = img.get('num_racimos_detectados', 'NO_ENCONTRADO')
                          logger.info(f"[DIAG READ] Imagen {i}: Verificando clave 'num_racimos_detectados'. Valor RAW obtenido: '{valor_raw}' (Tipo: {type(valor_raw).__name__})")
                          # --- FIN LOG DE DIAGNÓSTICO ---

                          # Intentar convertir a entero para la comparación
                          try:
                              racimos_img = int(valor_raw) if valor_raw != 'NO_ENCONTRADO' else 0
                              logger.info(f"[DIAG READ] Imagen {i}: Valor convertido a int: {racimos_img}")
                          except (ValueError, TypeError) as conv_err:
                               logger.warning(f"[DIAG READ] Imagen {i}: No se pudo convertir '{valor_raw}' a int. Error: {conv_err}. Usando 0.")
                               racimos_img = 0

                          # Comparación
                          if racimos_img > 0:
                              hay_detalles_por_foto_json = True
                              total_racimos_detectados_json += racimos_img # Acumular el total del JSON aquí
                              logger.info(f"[DIAG READ] Imagen {i}: Condición (racimos_img > 0) es VERDADERA. Estableciendo hay_detalles_por_foto_json = True. Total JSON acumulado: {total_racimos_detectados_json}")
                          else:
                               logger.info(f"[DIAG READ] Imagen {i}: Condición (racimos_img > 0) es FALSA.")

                      # Log después del bucle
                      if hay_detalles_por_foto_json:
                          logger.info(f"[DIAG READ] Verificación JSON (Post-Bucle): Se encontraron imágenes con num_racimos_detectados > 0. Flag final: {hay_detalles_por_foto_json}. Total Racimos JSON: {total_racimos_detectados_json}")
                      else:
                          logger.info(f"[DIAG READ] Verificación JSON (Post-Bucle): Se recorrieron las imágenes procesadas, pero NINGUNA tiene num_racimos_detectados > 0. Flag final: {hay_detalles_por_foto_json}")

                 else:
                      logger.warning(f"[DIAG READ] La clave 'imagenes_procesadas' no es una lista válida o está vacía en el JSON leído.")
                      imagenes_procesadas = [] # Asegurar que sea una lista vacía
                      hay_detalles_por_foto_json = False

             except json.JSONDecodeError as json_err:
                 logger.error(f"[DIAG READ] ¡ERROR al decodificar JSON desde {json_path_abs}! Error: {json_err}")
                 # Intentar leer el contenido crudo si falla la decodificación
                 try:
                     with open(json_path_abs, 'r', encoding='utf-8') as f_raw:
                         raw_content = f_raw.read()
                         logger.error(f"[DIAG READ RAW ON ERROR] Contenido crudo del archivo JSON con error:\n{raw_content[:1000]}...") # Mostrar primeros 1000 caracteres
                 except Exception as read_raw_err:
                     logger.error(f"[DIAG READ RAW ON ERROR] No se pudo leer el contenido crudo del archivo: {read_raw_err}")
                 # Asegurar valores por defecto si hay error
                 imagenes_procesadas = []
                 hay_detalles_por_foto_json = False
                 total_racimos_detectados_json = 0

             except Exception as read_err:
                 logger.error(f"[DIAG READ] ¡Error inesperado al leer o procesar el archivo JSON {json_path_abs}! Error: {read_err}")
                 logger.error(traceback.format_exc())
                 # Asegurar valores por defecto si hay error
                 imagenes_procesadas = []
                 hay_detalles_por_foto_json = False
                 total_racimos_detectados_json = 0

        else:
            logger.warning(f"[DIAG READ] Archivo JSON NO encontrado en {json_path_abs}. No se puede verificar detalles desde JSON.")
            # Asegurar valores por defecto si el archivo no existe
            imagenes_procesadas = []
            hay_detalles_por_foto_json = False
            total_racimos_detectados_json = 0

        # --- Determinación Final ---
        # ... (resto del código para comparar con la DB y renderizar) ...

    except Exception as e:
        logger.error(f"Error en ver_resultados_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar resultados de clasificación: {str(e)}", "error")
        return render_template('error.html', error=str(e))

    # --- Fin: Lógica Mejorada para Detalles Automáticos ---


    # --- Lógica Original (Datos de la Base de Datos) ---
    clasificacion_automatica_raw = datos_guia.get('clasificacion_automatica_json')
    db_total_racimos = datos_guia.get('total_racimos_detectados') # Obtener valor, puede ser None

    if clasificacion_automatica_raw:
        try:
            clasificacion_automatica = json.loads(clasificacion_automatica_raw)
            # logger.info(f"Clasificación automática cargada desde DB (JSON): {clasificacion_automatica}") # Log menos verboso
        except Exception as e:
            logger.error(f"Error cargando clasificacion_automatica_json de DB: {e}")
            clasificacion_automatica = {} # Dejar vacío en caso de error

    # Log del total de racimos de la DB
    logger.info(f"Total de racimos detectados leído desde la DB: {db_total_racimos} (Tipo: {type(db_total_racimos).__name__})")


    # --- Decisión Final para habilitar el botón "Ver Detalles" ---
    # Habilitar si la verificación del JSON fue exitosa O si los datos de la DB indican detecciones
    db_check_passed = (db_total_racimos is not None and db_total_racimos > 0)
    hay_detalles_por_foto = hay_detalles_por_foto_json or db_check_passed

    logger.info(f"Determinación final 'hay_detalles_por_foto': {hay_detalles_por_foto} (JSON Check: {hay_detalles_por_foto_json}, DB Check: {db_check_passed})")

    # Decidir qué total de racimos mostrar (priorizar JSON si tiene detalles, sino DB)
    total_racimos_a_mostrar = total_racimos_detectados_json if hay_detalles_por_foto_json else (db_total_racimos if db_total_racimos is not None else 0)
    logger.info(f"Total de racimos que se mostrará en la vista: {total_racimos_a_mostrar}")

    # Calcular porcentajes para la clasificación manual si existe
    clasificacion_manual_con_porcentajes = {}
    total_manual = sum(v for v in clasificacion_manual.values() if v is not None) # Asegura suma correcta con None
    if total_manual > 0:
        for cat, cant in clasificacion_manual.items():
            if cant is not None: # Solo calcular si la cantidad no es None
                porcentaje = round((cant / total_manual) * 100, 1)
                clasificacion_manual_con_porcentajes[cat] = {'cantidad': cant, 'porcentaje': porcentaje}
            else: # Incluir la categoría con 0 si era None
                clasificacion_manual_con_porcentajes[cat] = {'cantidad': 0, 'porcentaje': 0.0}

    end_time = time.time()
    # logger.info(f"Tiempo para cargar resultados de {url_guia}: {end_time - start_time:.2f} segundos") # Log menos verboso

    # Log final antes de renderizar
    logger.info(f"Datos finales para renderizar (incluye hay_detalles_por_foto={hay_detalles_por_foto}): { { 'codigo_guia': codigo_guia, 'hay_detalles': hay_detalles_por_foto, 'total_a_mostrar': total_racimos_a_mostrar, 'total_db': db_total_racimos, 'total_json': total_racimos_detectados_json } }")

    return render_template('clasificacion/clasificacion_resultados.html',
                           codigo_guia=codigo_guia,
                           codigo_proveedor=codigo_proveedor,
                           nombre_proveedor=nombre_proveedor,
                           peso_bruto=peso_bruto,
                           cantidad_racimos=cantidad_racimos,
                           fecha_clasificacion=fecha_clasificacion,
                           hora_clasificacion=hora_clasificacion,
                           clasificacion_manual=clasificacion_manual,
                           clasificacion_manual_con_porcentajes=clasificacion_manual_con_porcentajes,
                           # Pasar los datos automáticos leídos de la DB (si los hay)
                           clasificacion_automatica_consolidada=clasificacion_automatica,
                           # Pasar el total de racimos decidido (prioridad JSON)
                           total_racimos_detectados=total_racimos_a_mostrar,
                           hay_detalles_por_foto=hay_detalles_por_foto, # Variable clave para el botón
                           tiene_pesaje_neto=bool(datos_guia.get('peso_neto')) # Para botón de pesaje neto
                           )


@bp.route('/procesar_clasificacion', methods=['POST'])
def procesar_clasificacion():
    try:
        # Obtener datos del formulario - soportar tanto JSON como form data
        codigo_guia = None
        clasificacion_manual = {}
        
        if request.is_json:
            data = request.get_json()
            codigo_guia = data.get('codigo_guia')
            clasificacion_manual = data.get('clasificacion_manual', {})
        else:
            codigo_guia = request.form.get('codigo_guia')
            # Intentar recuperar clasificación manual de formulario normal
            for key in request.form:
                if key.startswith('cantidad_') or key in ['verdes', 'maduros', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']:
                    try:
                        categoria = key.replace('cantidad_', '')
                        clasificacion_manual[categoria] = int(float(request.form[key]))
                    except (ValueError, TypeError):
                        clasificacion_manual[categoria] = 0
        
        if not codigo_guia:
            logger.error("Falta código guía en la solicitud de clasificación")
            return jsonify({"success": False, "message": "Falta código guía"}), 400
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía ya clasificada: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya ha sido clasificada y no se puede modificar'
            }), 403
            
        # Verificar que el pesaje esté completado
        if not datos_guia or datos_guia.get('estado_actual') != 'pesaje_completado':
            logger.error(f"Intento de clasificar una guía sin pesaje completado: {codigo_guia}")
            return jsonify({
                'success': False,
                'message': 'Debe completar el proceso de pesaje antes de realizar la clasificación'
            }), 400
        
        # Crear directorio para clasificaciones si no existe
        clasificaciones_dir = os.path.join(current_app.config['CLASIFICACIONES_FOLDER'])
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Guardar la clasificación manual
        now = datetime.now()
        fecha_registro = now.strftime('%d/%m/%Y')
        hora_registro = now.strftime('%H:%M:%S')
        
        clasificacion_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': datos_guia.get('codigo_proveedor') or datos_guia.get('codigo'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor') or datos_guia.get('nombre'),
            'clasificacion_manual': clasificacion_manual,
            'observaciones': request.form.get('observaciones', ''),
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro
        }
        
        # Guardar en archivo JSON
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path = os.path.join(clasificaciones_dir, json_filename)
        
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
            
        # Actualizar el estado en la guía
        datos_guia.update({
            'clasificacion_completa': True,
            'fecha_clasificacion': fecha_registro,
            'hora_clasificacion': hora_registro,
            'tipo_clasificacion': 'manual',
            'clasificacion_manual': clasificacion_manual,
            'estado_actual': 'clasificacion_completada'
        })
        
        # Intentar generar URLs correctas con múltiples niveles de fallback
        try:
            # Intentar generar URL para ver resultados de clasificación
            results_url = url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia, _external=True)
        except Exception as e:
            logger.error(f"Error al generar URL para resultados (1): {str(e)}")
            try:
                # Segundo intento: usar la ruta directa
                results_url = f"{request.host_url.rstrip('/')}/clasificacion/ver_resultados_clasificacion/{codigo_guia}"
            except Exception as e2:
                logger.error(f"Error al generar URL para resultados (2): {str(e2)}")
                # Fallback final: URL relativa simple
                results_url = f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}"
        
        try:
            # Intentar generar URL para guía centralizada
            centralizada_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        except Exception as e:
            logger.error(f"Error al generar URL para guía centralizada (1): {str(e)}")
            try:
                # Segundo intento con ruta directa
                centralizada_url = f"{request.host_url.rstrip('/')}/guia-centralizada/{codigo_guia}"
            except Exception as e2:
                logger.error(f"Error al generar URL para guía centralizada (2): {str(e2)}")
                # Fallback final
                centralizada_url = f"/guia-centralizada/{codigo_guia}"
        
        # Generar HTML actualizado con manejo de errores
        try:
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            # Actualizar el archivo de la guía
            guia_path = os.path.join(current_app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
            with open(guia_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
        except Exception as e:
            logger.error(f"Error al actualizar template de guía: {str(e)}")
            logger.error(traceback.format_exc())
        
        # Determinar el tipo de respuesta basado en el content-type de solicitud
        if request.is_json:
            return jsonify({
                'success': True,
                'message': 'Clasificación guardada exitosamente',
                'redirect_url': results_url,
                'centralizada_url': centralizada_url,
                'success_url': url_for('clasificacion.success_page', codigo_guia=codigo_guia, _external=True)
            })
        else:
            # Renderizar la plantilla de éxito para solicitudes de formulario
            return render_template(
                'clasificacion/clasificacion_success.html',
                codigo_guia=codigo_guia,
                datos_guia=datos_guia,
                resultados_url=results_url,
                guia_url=centralizada_url
            )
            
    except Exception as e:
        logger.error(f"Error al procesar clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar redirigir a página de éxito incluso en caso de error
        try:
            if codigo_guia:
                return redirect(url_for('clasificacion.success_page', codigo_guia=codigo_guia))
        except Exception:
            pass
            
        # Si todo lo demás falla, mostrar una respuesta de error genérica
        if request.is_json:
            return jsonify({
                'success': False,
                'message': f'Error al procesar la clasificación: {str(e)}'
            }), 500
        else:
            flash(f"Error al procesar la clasificación: {str(e)}", "danger")
            return redirect(url_for('pesaje.lista_pesajes'))

@bp.route('/procesar_clasificacion_manual/<path:url_guia>', methods=['GET', 'POST'])
def procesar_clasificacion_manual(url_guia):
    """
    Muestra la pantalla de procesamiento para clasificación automática manual
    """
    try:
        logger.info(f"Iniciando pantalla de procesamiento para clasificación manual de: {url_guia}")
        
        # Obtener datos de clasificación desde el archivo JSON
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
        
        # Variables por defecto
        nombre = "No disponible"
        codigo_proveedor = ""
        fotos = []
        
        # Cargar el archivo JSON si existe
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                    
                # Obtener las fotos del archivo de clasificación
                fotos = clasificacion_data.get('fotos', [])
                
                # Intentar obtener los datos del proveedor
                utils_instance = get_utils_instance()
                datos_registro = utils_instance.get_datos_registro(url_guia)
                if datos_registro:
                    nombre = datos_registro.get('nombre_proveedor', 'No disponible')
                    codigo_proveedor = datos_registro.get('codigo_proveedor', '')
            except Exception as e:
                logger.error(f"Error al cargar el archivo JSON: {str(e)}")
        else:
            logger.warning(f"No se encontró el archivo de clasificación para: {url_guia}")
        
        return render_template('archive/old_templates/procesando_clasificacion.html', 
                              codigo_guia=url_guia, 
                              nombre=nombre,
                              codigo_proveedor=codigo_proveedor,
                              cantidad_fotos=len(fotos))
    except Exception as e:
        logger.error(f"Error al mostrar la pantalla de procesamiento: {str(e)}")
        return render_template('error.html', 
                              mensaje=f"Error al preparar el procesamiento de clasificación: {str(e)}",
                              volver_url=url_for('clasificacion.ver_resultados_automaticos', url_guia=url_guia))

# Dictionary to track the progress of image processing
processing_status = {}



@bp.route('/iniciar_procesamiento/<path:url_guia>', methods=['POST'])
def iniciar_procesamiento(url_guia):
    """
    Inicia el procesamiento de clasificación automática para una guía específica.
    Recupera las rutas de las fotos guardadas y lanza un hilo para procesarlas.
    """
    utils = get_utils_instance() # Asegúrate que get_utils_instance() esté definida o importa CommonUtils
    codigo_guia = url_guia.replace('/', '_') # Asegurar formato correcto
    logger.info(f"Solicitud para iniciar procesamiento automático para guía: {codigo_guia}")

    try:
        # --- CORRECCIÓN: Usar get_clasificacion_by_codigo_guia para obtener las fotos ---
        datos_clasificacion = get_clasificacion_by_codigo_guia(codigo_guia)

        if not datos_clasificacion:
            logger.error(f"No se encontraron datos de clasificación para la guía: {codigo_guia}")
            # Podrías intentar obtener datos generales como fallback si es necesario
            # datos_guia_general = utils.get_datos_guia(codigo_guia)
            # if not datos_guia_general:
            #     return jsonify({'success': False, 'message': 'Guía no encontrada'}), 404
            # else: # Si hay datos generales pero no de clasificación
            return jsonify({'success': False, 'message': 'Datos de clasificación no encontrados para esta guía.'}), 404

        # Obtener las rutas de las fotos de la clasificación
        # La función get_clasificacion_by_codigo_guia devuelve las rutas en la clave 'fotos'
        rutas_fotos_guardadas = datos_clasificacion.get('fotos', [])

        if not rutas_fotos_guardadas:
             logger.error(f"No se encontraron rutas de fotos en los datos de clasificación de la guía {codigo_guia}")
             # Este log ahora indica que get_clasificacion_by_codigo_guia no las devolvió
             return jsonify({'success': False, 'message': 'No se encontraron fotos asociadas a esta clasificación.'}), 400
        # ---------------------------------------------------------------------------------

        # Convertir rutas (que podrían ser relativas desde static) a absolutas
        static_folder = current_app.static_folder
        upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(static_folder, 'uploads')) # Define upload_folder
        fotos_paths_absolutas = []

        for ruta_relativa_o_url in rutas_fotos_guardadas:
            abs_path = None
            # Quitar '/static/' si es una URL generada por url_for
            if ruta_relativa_o_url.startswith('/static/'):
                ruta_limpia = ruta_relativa_o_url[len('/static/'):]
                abs_path = os.path.join(static_folder, ruta_limpia)
            # Si es una ruta relativa simple (ej: 'uploads/codigo_guia/foto.jpg')
            elif not os.path.isabs(ruta_relativa_o_url):
                 # Asumimos que es relativa a static_folder
                 abs_path = os.path.join(static_folder, ruta_relativa_o_url)
            # Si ya es una ruta absoluta
            elif os.path.isabs(ruta_relativa_o_url):
                 abs_path = ruta_relativa_o_url

            # Verificar si el archivo existe antes de añadirlo
            if abs_path and os.path.exists(abs_path):
                fotos_paths_absolutas.append(abs_path)
                logger.debug(f"Ruta absoluta encontrada y verificada: {abs_path}")
            elif abs_path:
                logger.warning(f"Archivo de foto no encontrado en la ruta absoluta calculada: {abs_path} (Original: {ruta_relativa_o_url}) para guía {codigo_guia}")
            else:
                 logger.warning(f"No se pudo determinar la ruta absoluta para: {ruta_relativa_o_url}")


        if not fotos_paths_absolutas:
             logger.error(f"Ninguna de las fotos guardadas para la guía {codigo_guia} fue encontrada en el sistema de archivos como ruta absoluta.")
             return jsonify({'success': False, 'message': 'Archivos de fotos no encontrados.'}), 400

        logger.info(f"Rutas absolutas encontradas para procesar para guía {codigo_guia}: {fotos_paths_absolutas}")

        # Definir directorios y archivos de salida (usando upload_folder como base)
        # El directorio de la guía debería estar dentro de uploads
        guia_dir_relativo = os.path.join(codigo_guia) # ej: 0150076A_20250411_100000
        guia_dir_absoluto = os.path.join(upload_folder, guia_dir_relativo)
        os.makedirs(guia_dir_absoluto, exist_ok=True) # Asegurar que el directorio exista

        # El archivo JSON también debería ir aquí para mantener todo junto
        json_filename = f'clasificacion_{codigo_guia}.json'
        json_path = os.path.join(guia_dir_absoluto, json_filename)
        logger.info(f"Directorio de salida para guía {codigo_guia}: {guia_dir_absoluto}")
        logger.info(f"Ruta de salida JSON para guía {codigo_guia}: {json_path}")


        # Actualizar estado de la guía para indicar inicio de procesamiento (Opcional, podrías hacerlo en process_thread)
        # Considera si 'utils.update_datos_guia' es la forma correcta o si deberías actualizar la tabla 'clasificaciones' directamente
        # try:
        #     update_data = {
        #         'estado_clasificacion_auto': 'procesando',
        #         'timestamp_inicio_auto': get_utc_timestamp_str() # Asegúrate que esta función exista
        #     }
        #     # utils.update_datos_guia(codigo_guia, update_data) # Comentado temporalmente - Revisar si es necesario/correcto
        #     logger.info(f"Estado de guía {codigo_guia} actualizado a 'procesando' (si la función está descomentada).")
        # except Exception as update_err:
        #     logger.warning(f"No se pudo actualizar el estado de la guía {codigo_guia} a 'procesando': {update_err}")


        logger.info(f"Iniciando hilo de procesamiento para guía: {codigo_guia}")
        # Iniciar el procesamiento en un hilo separado
        thread = threading.Thread(target=process_thread, args=(
            current_app._get_current_object(),
            codigo_guia,
            fotos_paths_absolutas, # Pasar la lista de rutas absolutas encontradas
            guia_dir_absoluto, # Pasar el directorio absoluto de la guía
            json_path # Pasar la ruta absoluta del JSON
        ))
        thread.start()

        logger.info(f"Hilo de procesamiento iniciado para guía: {codigo_guia}")

        # Devolver respuesta indicando que el proceso inició
        return jsonify({
            'success': True,
            'message': 'Procesamiento automático iniciado en segundo plano.',
            'check_status_url': url_for('clasificacion.check_procesamiento_status', url_guia=url_guia)
        })

    except Exception as e:
        logger.error(f"Error GRANDE al iniciar procesamiento automático para guía {codigo_guia}: {str(e)}")
        logger.error(traceback.format_exc())
   
        return jsonify({'success': False, 'message': f'Error interno del servidor: {str(e)}'}), 500




@bp.route('/check_procesamiento_status/<path:url_guia>', methods=['GET'])
def check_procesamiento_status(url_guia):
    """
    Endpoint para verificar el estado del procesamiento de imágenes
    """
    logger.info(f"Verificando estado de procesamiento para: {url_guia}")
    
    # Verificar si hay información de estado para esta guía
    if url_guia in processing_status:
        status_data = processing_status[url_guia].copy()
        
        # Verificar si el procesamiento está completo
        is_completed = status_data.get('status') == 'completed'
        
        # Incluir flag de clasificación completa en la respuesta
        status_data['clasificacion_completa'] = is_completed
        
        # Si está completo, incluir total_racimos_detectados
        if is_completed:
            try:
                # Buscar el archivo de clasificación para obtener el total de racimos detectados
                clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
                json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
                
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        clasificacion_data = json.load(f)
                        # Extraer total_racimos_detectados
                        total_racimos = clasificacion_data.get('total_racimos_detectados', 0)
                        status_data['total_racimos_detectados'] = total_racimos
                        logger.info(f"Total racimos detectados para {url_guia}: {total_racimos}")
            except Exception as e:
                logger.error(f"Error al obtener total_racimos_detectados: {str(e)}")
                # Si hay un error, asumimos que hay al menos un racimo detectado para habilitar el botón
                status_data['total_racimos_detectados'] = 1
        
        return jsonify(status_data)
    else:
        # No hay información de procesamiento para esta guía
        return jsonify({
            'status': 'not_found',
            'message': 'No se encontró información de procesamiento para esta guía',
            'clasificacion_completa': False,
            'total_racimos_detectados': 0
        })



@bp.route('/procesar_imagenes/<path:url_guia>')
def procesar_imagenes(url_guia):
    """
    Procesa las imágenes de una guía para clasificación automática
    """
    # Inicializar mostrar_automatica para evitar errores
    mostrar_automatica = True  
    
    try:
        # Obtener datos de clasificación desde la base de datos
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(url_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {url_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
            
            logger.info(f"Buscando archivo de clasificación en: {json_path}")
            logger.info(f"El archivo existe: {os.path.exists(json_path)}")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                # Buscar en el directorio fotos_racimos_temp también
                alt_path = os.path.join(current_app.static_folder, 'fotos_racimos_temp', f"clasificacion_{url_guia}.json")
                logger.info(f"Buscando archivo alternativo en: {alt_path}")
                logger.info(f"El archivo alternativo existe: {os.path.exists(alt_path)}")
                
                if os.path.exists(alt_path):
                    with open(alt_path, 'r') as f:
                        clasificacion_data = json.load(f)
                    logger.info(f"Clasificación leída del archivo alternativo: {alt_path}")
                else:
                    # Intentar una tercera ubicación (uploads/clasificacion)
                    fotos_folder = current_app.config.get('FOTOS_RACIMOS_FOLDER', 
                                                  os.path.join(current_app.config['UPLOAD_FOLDER'], 'clasificacion'))
                    third_path = os.path.join(fotos_folder, f'clasificacion_{url_guia}.json')
                    logger.info(f"Buscando en tercera ubicación: {third_path}")
                    
                    if os.path.exists(third_path):
                        with open(third_path, 'r') as f:
                            clasificacion_data = json.load(f)
                        logger.info(f"Clasificación leída de la tercera ubicación: {third_path}")
                    else:
                        return render_template('error.html', message="Clasificación no encontrada")
        
        # Extraer el código de proveedor del código de guía
        codigo_proveedor = url_guia.split('_')[0] if '_' in url_guia else url_guia
        # Asegurarse de que termina con 'A' correctamente
        if re.match(r'\d+[aA]?$', codigo_proveedor):
            if codigo_proveedor.endswith('a'):
                codigo_proveedor = codigo_proveedor[:-1] + 'A'
            elif not codigo_proveedor.endswith('A'):
                codigo_proveedor = codigo_proveedor + 'A'
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(url_guia)
        logger.info(f"Datos de guía encontrados: {datos_guia is not None}")
        logger.info(f"Datos de guía obtenidos: {json.dumps(datos_guia) if datos_guia else None}")
        
        # Intentar obtener datos adicionales si no están completos
        nombre_proveedor = None
        cantidad_racimos = None
        
        try:
            # Intentar obtener datos desde la tabla de entrada
            from db_utils import get_entry_record_by_guide_code
            registro_entrada = get_entry_record_by_guide_code(url_guia)
            
            if registro_entrada:
                logger.info(f"Encontrado registro de entrada para {url_guia}")
                nombre_proveedor = registro_entrada.get('nombre_proveedor')
                cantidad_racimos = registro_entrada.get('cantidad_racimos') or registro_entrada.get('racimos')
            else:
                # Intentar obtener datos del proveedor
                from db_operations import get_provider_by_code
                datos_proveedor = get_provider_by_code(codigo_proveedor)
                
                if datos_proveedor:
                    logger.info(f"Encontrado proveedor por código: {codigo_proveedor}")
                    nombre_proveedor = datos_proveedor.get('nombre')
                    
                # También podemos buscar en pesajes
                from db_operations import get_pesaje_bruto_by_codigo_guia
                datos_pesaje = get_pesaje_bruto_by_codigo_guia(url_guia)
                
                if datos_pesaje:
                    logger.info(f"Encontrado pesaje para {url_guia}")
                    if not nombre_proveedor:
                        nombre_proveedor = datos_pesaje.get('nombre_proveedor')
                    if not cantidad_racimos:
                        cantidad_racimos = datos_pesaje.get('cantidad_racimos') or datos_pesaje.get('racimos')
                    
        except Exception as e:
            logger.error(f"Error buscando información adicional: {str(e)}")
            logger.error(traceback.format_exc())
        
        if not datos_guia:
            logger.warning("No se encontraron datos de guía, intentando crear datos mínimos")
            datos_guia = {
                'codigo_guia': url_guia,
                'codigo_proveedor': codigo_proveedor,
                'nombre_proveedor': clasificacion_data.get('nombre_proveedor', nombre_proveedor or 'No disponible'),
                'cantidad_racimos': clasificacion_data.get('cantidad_racimos', cantidad_racimos or 'N/A'),
                'peso_bruto': clasificacion_data.get('peso_bruto', 'N/A')
            }
            
        # Asegurar que clasificacion_manual no sea None
        if clasificacion_data.get('clasificacion_manual') is None:
            clasificacion_data['clasificacion_manual'] = {}
            
        # Asegurar que clasificacion_automatica no sea None
        if clasificacion_data.get('clasificacion_automatica') is None:
            clasificacion_data['clasificacion_automatica'] = {}
            
        # Log para diagnóstico
        logger.info(f"Clasificación manual: {clasificacion_data.get('clasificacion_manual')}")
        logger.info(f"Clasificación automática: {clasificacion_data.get('clasificacion_automatica')}")
        
        # Procesar clasificaciones si están en formato JSON
        clasificaciones = []
        if isinstance(clasificacion_data.get('clasificaciones'), str):
            try:
                clasificaciones = json.loads(clasificacion_data['clasificaciones'])
                # También asignar a clasificacion_manual si está vacío
                if not clasificacion_data.get('clasificacion_manual'):
                    clasificacion_data['clasificacion_manual'] = clasificaciones
            except json.JSONDecodeError:
                clasificaciones = []
        else:
            clasificaciones = clasificacion_data.get('clasificaciones', [])
            
        # Convertir los datos de clasificación de texto a objetos Python, si es necesario
        if clasificacion_data and isinstance(clasificacion_data.get('clasificacion_manual'), str):
            try:
                clasificacion_data['clasificacion_manual'] = json.loads(clasificacion_data['clasificacion_manual'])
            except json.JSONDecodeError:
                clasificacion_data['clasificacion_manual'] = {}
                
        # Si aún no tenemos clasificacion_manual, intentar buscar en clasificaciones
        if not clasificacion_data.get('clasificacion_manual') and clasificaciones:
            clasificacion_data['clasificacion_manual'] = clasificaciones
                
        # Usar la información más completa que tengamos
        nombre_proveedor_final = (
            datos_guia.get('nombre_proveedor') or 
            datos_guia.get('nombre') or 
            clasificacion_data.get('nombre_proveedor') or 
            nombre_proveedor or 
            'No disponible'
        )
        
        cantidad_racimos_final = (
            datos_guia.get('cantidad_racimos') or 
            datos_guia.get('racimos') or 
            clasificacion_data.get('cantidad_racimos') or
            clasificacion_data.get('racimos') or
            cantidad_racimos or 
            'N/A'
        )
                
        # Procesar fotos para asegurar rutas relativas correctas
        fotos_originales = clasificacion_data.get('fotos', [])
        fotos_procesadas = []
        
        if fotos_originales:
            logger.info(f"Procesando {len(fotos_originales)} fotos para la clasificación")
            for foto in fotos_originales:
                # Si la ruta es absoluta, convertirla a relativa
                if isinstance(foto, str):
                    if os.path.isabs(foto):
                        try:
                            # Obtener la parte relativa después de /static/
                            static_index = foto.find('/static/')
                            if static_index != -1:
                                rel_path = foto[static_index + 8:]  # +8 para saltar '/static/'
                                fotos_procesadas.append(rel_path)
                            else:
                                # Si contiene fotos_racimos_temp, crear ruta relativa
                                if 'fotos_racimos_temp' in foto:
                                    foto_filename = os.path.basename(foto)
                                    fotos_procesadas.append(f'fotos_racimos_temp/{foto_filename}')
                                else:
                                    logger.warning(f"No se pudo determinar ruta relativa para: {foto}")
                        except Exception as e:
                            logger.error(f"Error procesando ruta de foto: {str(e)}")
                    else:
                        # Ya es relativa, usarla directamente
                        fotos_procesadas.append(foto)
        else:
            logger.warning("No se encontraron fotos en los datos de clasificación")
            # Buscar fotos en la tabla fotos_clasificacion
            try:
                with sqlite3.connect(current_app.config['TIQUETES_DB_PATH']) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", (url_guia,))
                    db_fotos = [row['ruta_foto'] for row in cursor.fetchall()]
                    if db_fotos:
                        logger.info(f"Fotos encontradas en fotos_clasificacion: {len(db_fotos)}")
                        fotos_originales = db_fotos # Usar estas fotos
                        # Procesar rutas de nuevo
                        for foto in fotos_originales:
                            if isinstance(foto, str):
                                if os.path.isabs(foto):
                                    static_index = foto.find('/static/')
                                    if static_index != -1:
                                        rel_path = foto[static_index + 8:]
                                        fotos_procesadas.append(rel_path)
                                else:
                                    fotos_procesadas.append(foto)
            except Exception as db_foto_err:
                logger.error(f"Error buscando fotos en la DB: {db_foto_err}")

        # Calcular total_racimos_detectados si hay datos automáticos
        # Asegurarse que clasificacion_automatica_consolidada es un dict
        if isinstance(clasificacion_data.get('clasificacion_consolidada'), str):
            try:
                clasificacion_automatica_consolidada = json.loads(clasificacion_data['clasificacion_consolidada'])
            except json.JSONDecodeError:
                clasificacion_automatica_consolidada = {}
        elif isinstance(clasificacion_data.get('clasificacion_consolidada'), dict):
            clasificacion_automatica_consolidada = clasificacion_data['clasificacion_consolidada']
        else:
            clasificacion_automatica_consolidada = {}
            
        # Obtener total_racimos_detectados de la consolidación
        if clasificacion_automatica_consolidada and 'total_racimos' in clasificacion_automatica_consolidada:
            total_racimos_detectados = clasificacion_automatica_consolidada['total_racimos']
        elif isinstance(clasificacion_data.get('clasificacion_automatica'), dict) and 'total_racimos' in clasificacion_data['clasificacion_automatica']:
             total_racimos_detectados = clasificacion_data['clasificacion_automatica']['total_racimos']
        # Fallback si no se encuentra en ningún lado
        if not isinstance(total_racimos_detectados, int) or total_racimos_detectados < 0:
            total_racimos_detectados = clasificacion_data.get('total_racimos_detectados', 0)
            if not isinstance(total_racimos_detectados, int) or total_racimos_detectados < 0:
                 total_racimos_detectados = 0 # Asegurar que sea un entero no negativo
        
        logger.info(f"Total de racimos detectados: {total_racimos_detectados}")
        
        # Después de cargar clasificacion_data (sea de la BD o del JSON)
        # ... (código existente para cargar datos_guia, nombre_proveedor, fotos, etc.) ...

        # --- INICIO: NUEVA VERIFICACIÓN ---
        hay_detalles_por_foto = False
        # Verificar si la clave que contiene los detalles por foto existe y no está vacía
        # Usamos 'resultados_por_foto' como la clave más probable basada en ver_detalles_clasificacion
        if clasificacion_data and 'resultados_por_foto' in clasificacion_data:
            detalles = clasificacion_data['resultados_por_foto']
            # Asegurarse que no sea None y que tenga contenido (sea dict o list)
            if detalles and (isinstance(detalles, dict) or isinstance(detalles, list)) and len(detalles) > 0:
                 hay_detalles_por_foto = True
                 logger.info(f"Se encontraron detalles por foto ('resultados_por_foto') para {url_guia}")
            else:
                 logger.info(f"'resultados_por_foto' encontrado pero vacío o None para {url_guia}")
        else:
            logger.info(f"No se encontró la clave 'resultados_por_foto' en clasificacion_data para {url_guia}")
        # --- FIN: NUEVA VERIFICACIÓN ---

        # Preparar datos para la plantilla
        template_data = {
            'codigo_guia': url_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor_final,
            'cantidad_racimos': cantidad_racimos_final,
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {}),
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'total_racimos_detectados': total_racimos_detectados,
            'fotos_procesadas': fotos_procesadas, # Asegúrate que esta variable se sigue pasando
            'hay_fotos': len(fotos_procesadas) > 0,
            # Reemplaza la dependencia de 'hay_resultados_automaticos' si es necesario
            # 'hay_resultados_automaticos': bool(clasificacion_automatica_consolidada) or bool(clasificacion_data.get('clasificacion_automatica')), # Comentado/Revisar
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'N/A'),
            'error_procesamiento': clasificacion_data.get('error_message', None),
            'estado_procesamiento': clasificacion_data.get('estado', 'pendiente'),
            'mostrar_automatica': mostrar_automatica,
            # *** AÑADIR LA NUEVA VARIABLE ***
            'hay_detalles_por_foto': hay_detalles_por_foto,
             # Pasar también clasificacion_automatica_consolidada si se sigue usando en otro lugar
            'clasificacion_automatica_consolidada': clasificacion_automatica_consolidada
        }

        # Log final antes de renderizar
        logger.info(f"Datos finales para renderizar (incluye hay_detalles_por_foto={hay_detalles_por_foto}): {json.dumps({k: v for k, v in template_data.items() if k != 'raw_data'})}") # Log sin el raw_data si es muy grande
        fin = time.time()
        logger.info(f"Tiempo total en ver_resultados_clasificacion: {fin - inicio:.4f} segundos")

        return render_template('clasificacion/clasificacion_resultados.html', **template_data)

    except Exception as e:
        logger.error(f"Error en procesar_imagenes: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar las imágenes: {str(e)}", "error")
        return redirect(url_for('clasificacion.ver_resultados_automaticos', url_guia=url_guia))

@bp.route('/generar_pdf_clasificacion/<codigo_guia>')
def generar_pdf_clasificacion(codigo_guia):
    """
    Genera un PDF con los resultados de la clasificación.
    """
    try:
        logger.info(f"Generando PDF de clasificación para guía: {codigo_guia}")
            
        # Obtener datos de clasificación
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(codigo_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {codigo_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                flash("No se encontró la clasificación para la guía especificada.", "error")
                return redirect(url_for('misc.index'))
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('misc.index'))
        
        # Procesar clasificaciones si están en formato JSON
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
        
        # Preparar datos para la plantilla
        codigo_proveedor = clasificacion_data.get('codigo_proveedor', datos_guia.get('codigo_proveedor', ''))
        nombre_proveedor = clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre_agricultor', ''))
        
        # Generar QR
        qr_filename = f"qr_clasificacion_{codigo_guia}.png"
        qr_path = os.path.join(current_app.config['QR_FOLDER'], qr_filename)
        qr_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
        
        utils_instance.generar_qr(qr_url, qr_path)
        
        # Obtener fotos de clasificación
        fotos = []
        if isinstance(clasificacion_data.get('fotos'), list):
            for foto_path in clasificacion_data['fotos']:
                # Convertir a ruta relativa si es una ruta absoluta
                if os.path.isabs(foto_path):
                    rel_path = os.path.relpath(foto_path, current_app.static_folder)
                    fotos.append(rel_path)
                else:
                    fotos.append(foto_path)
                    
        # Preparar la plantilla PDF
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'fecha_clasificacion': clasificacion_data.get('fecha_registro', datos_guia.get('fecha_registro', '')),
            'hora_clasificacion': clasificacion_data.get('hora_registro', datos_guia.get('hora_registro', '')),
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': clasificacion_automatica,
            'qr_code': url_for('static', filename=f'qr/{qr_filename}'),
            'fotos': fotos,
            'peso_bruto': datos_guia.get('peso_bruto', ''),
            'cantidad_racimos': datos_guia.get('racimos', ''),
            'transportador': datos_guia.get('transportador', ''),
            'placa': datos_guia.get('placa', ''),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', ''),
            'for_pdf': True
        }
        
        # Generar HTML renderizado
        html = render_template('clasificacion/clasificacion_documento.html', **template_data)
        
        # Crear PDF a partir del HTML
        pdf_filename = f"clasificacion_{codigo_guia}.pdf"
        pdf_path = os.path.join(current_app.config['PDF_FOLDER'], pdf_filename)
        
        # Importar CSS para el PDF
        css_paths = [
            os.path.join(current_app.static_folder, 'css/bootstrap.min.css'),
            os.path.join(current_app.static_folder, 'css/documento_styles.css')
        ]
        
        # Generar PDF usando utils
        utils_instance.generar_pdf_desde_html(html, pdf_path, css_paths)
        
        # Devolver el PDF como descarga
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)
        
    except Exception as e:
        logger.error(f"Error generando PDF de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))

@bp.route('/print_view_clasificacion/<codigo_guia>')
def print_view_clasificacion(codigo_guia):
    """
    Muestra una vista para impresión de los resultados de clasificación.
    """
    try:
        logger.info(f"Mostrando vista de impresión para clasificación: {codigo_guia}")
        
        # Obtener datos de clasificación
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(codigo_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {codigo_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                flash("No se encontró la clasificación para la guía especificada.", "error")
                return redirect(url_for('misc.index'))
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('misc.index'))
        
        # Procesar clasificaciones si están en formato JSON
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
        
        # Preparar datos para la plantilla
        codigo_proveedor = clasificacion_data.get('codigo_proveedor', datos_guia.get('codigo_proveedor', ''))
        nombre_proveedor = clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre_agricultor', ''))
        
        # Obtener fotos de clasificación
        fotos = []
        if isinstance(clasificacion_data.get('fotos'), list):
            for foto_path in clasificacion_data['fotos']:
                # Convertir a ruta relativa si es una ruta absoluta
                if os.path.isabs(foto_path):
                    rel_path = os.path.relpath(foto_path, current_app.static_folder)
                    fotos.append(rel_path)
                else:
                    fotos.append(foto_path)
                    
        # Preparar la plantilla
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'fecha_clasificacion': clasificacion_data.get('fecha_registro', datos_guia.get('fecha_registro', '')),
            'hora_clasificacion': clasificacion_data.get('hora_registro', datos_guia.get('hora_registro', '')),
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': clasificacion_automatica,
            'fotos': fotos,
            'peso_bruto': datos_guia.get('peso_bruto', ''),
            'cantidad_racimos': datos_guia.get('racimos', ''),
            'transportador': datos_guia.get('transportador', ''),
            'placa': datos_guia.get('placa', ''),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', ''),
            'for_print': True
        }
        
        return render_template('clasificacion/clasificacion_documento.html', **template_data)
        
    except Exception as e:
        logger.error(f"Error mostrando vista de impresión: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error mostrando vista de impresión: {str(e)}", "error")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))

@bp.route('/procesar_automatico', methods=['POST'])
def procesar_clasificacion_automatica():
    """
    Procesa las imágenes subidas para realizar una clasificación automática
    """
    try:
        logger.info("Iniciando procesamiento de clasificación automática")
        
        if 'codigo_guia' not in request.form:
            logger.error("No se proporcionó el código de guía")
            return jsonify({'success': False, 'message': 'No se proporcionó el código de guía'}), 400
        
        codigo_guia = request.form['codigo_guia']
        logger.info(f"Procesando clasificación automática para guía: {codigo_guia}")
        
        # Crear directorio temporal para las imágenes si no existe
        temp_dir = os.path.join(current_app.config.get('UPLOAD_FOLDER', 'uploads'), 'temp_clasificacion')
        os.makedirs(temp_dir, exist_ok=True)
        
        # Guardar las imágenes subidas
        imagenes = []
        for i in range(1, 4):
            key = f'foto-{i}'
            if key in request.files and request.files[key].filename:
                file = request.files[key]
                filename = f"temp_clasificacion_{codigo_guia}_{i}_{int(time.time())}.jpg"
                filepath = os.path.join(temp_dir, filename)
                file.save(filepath)
                imagenes.append(filepath)
                logger.info(f"Imagen {i} guardada: {filepath}")
        
        if not imagenes:
            logger.error("No se proporcionaron imágenes para la clasificación")
            return jsonify({'success': False, 'message': 'No se proporcionaron imágenes para la clasificación'}), 400
        
        # Aquí se procesarían las imágenes con la IA (Roboflow u otro servicio)
        # Como es un ejemplo, generamos resultados aleatorios para demostración
        # En una implementación real, aquí se llamaría a la API o modelo de ML
        
        import random
        # Simulamos un procesamiento con valores aleatorios
        resultados = {
            'verdes': round(random.uniform(0, 100), 2),
            'sobremaduros': round(random.uniform(0, 20), 2),
            'dano_corona': round(random.uniform(0, 10), 2),
            'pedunculo_largo': round(random.uniform(0, 15), 2)
        }
        
        logger.info(f"Resultados de clasificación automática: {resultados}")
        
        # Responder con los resultados y indicador de clasificación completa
        return jsonify({
            'success': True,
            'resultados': resultados,
            'mensaje': 'Clasificación automática completada exitosamente',
            'clasificacion_completa': True,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    
    except Exception as e:
        logger.error(f"Error en procesamiento automático: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}', 'clasificacion_completa': False}), 500


@bp.route('/debug_redirect/<path:url_guia>')
def debug_redirect(url_guia):
    """
    Debug route for testing redirects to classification results
    """
    logger.info(f"Debug redirect for guía: {url_guia}")
    redirect_url = url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia)
    logger.info(f"Redirect URL generated: {redirect_url}")
    return jsonify({
        'success': True,
        'message': 'Debug info for redirection',
        'redirect_url': redirect_url,
        'direct_url': f"/clasificacion/ver_resultados_clasificacion/{url_guia}"
    })



@bp.route("/success/<path:codigo_guia>")
def success_page(codigo_guia):
    """Página de éxito cuando otras redirecciones fallan"""
    logger.info(f"Mostrando página de éxito para: {codigo_guia}")
    
    # Inicializar mostrar_automatica para evitar errores
    mostrar_automatica = True
    
    # Obtener datos básicos de la guía
    utils_instance = get_utils_instance()
    datos_guia = utils_instance.get_datos_guia(codigo_guia)
    
    if not datos_guia:
        datos_guia = {
            "codigo_guia": codigo_guia,
            "codigo_proveedor": codigo_guia.split("_")[0] if "_" in codigo_guia else codigo_guia
        }
    
    # Intentar generar la URL correcta de resultados
    try:
        resultados_url = url_for("clasificacion.ver_resultados_clasificacion", url_guia=codigo_guia)
    except Exception:
        resultados_url = f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}"
    
    # Intentar también la URL de la guía centralizada
    try:
        guia_url = url_for("misc.ver_guia_centralizada", codigo_guia=codigo_guia)
    except Exception:
        guia_url = f"/guia-centralizada/{codigo_guia}"
    
    return render_template(
        "clasificacion/clasificacion_success.html",
        codigo_guia=codigo_guia,
        datos_guia=datos_guia,
        resultados_url=resultados_url,
        guia_url=guia_url
    )

# Asegúrate que las importaciones necesarias estén presentes al inicio del archivo:
# import time, logging, traceback, threading
# from . import bp # O la referencia correcta a tu blueprint
# from flask import current_app # Necesario para obtener app.config dentro del contexto
# from app.utils.common import CommonUtils as Utils # O la ruta correcta a Utils
# from .routes import get_utils_instance, get_utc_timestamp_str, process_images_with_roboflow # Y otras necesarias



def process_thread(app, codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Función ejecutada en un hilo separado para procesar imágenes con Roboflow.
    Establece contexto, lee config y la pasa explícitamente a la función de procesamiento.
    """
    with app.app_context(): # Establecer contexto de aplicación
        start_time = time.time()
        utils = get_utils_instance()
        logger.info(f"[Hilo Param] Iniciando procesamiento para guía: {codigo_guia}")

        # --- LEER CONFIGURACIÓN AQUÍ DENTRO DEL CONTEXTO ---
        try:
            roboflow_config = {
                'api_key': current_app.config.get('ROBOFLOW_API_KEY'),
                'workspace': current_app.config.get('ROBOFLOW_WORKSPACE'),
                'project': current_app.config.get('ROBOFLOW_PROJECT'),
                'workflow_id': current_app.config.get('ROBOFLOW_WORKFLOW_ID'),
                'api_url': current_app.config.get('ROBOFLOW_API_URL', "https://classify.roboflow.com") # O la URL específica si la tienes
            }
            # Verificar que todos los valores necesarios se leyeron
            # Ajustar esta lista si alguna clave es opcional
            required_keys = ['api_key', 'workspace', 'project', 'workflow_id', 'api_url']
            if not all(roboflow_config.get(key) for key in required_keys):
                 # Loguear qué claves faltan específicamente
                 missing_keys = [key for key in required_keys if not roboflow_config.get(key)]
                 logger.error(f"[Hilo Param] Faltan valores en la configuración de Roboflow leída desde app.config. Claves faltantes: {missing_keys}")
                 raise ValueError("Configuración de Roboflow incompleta.")
            logger.info("[Hilo Param] Configuración Roboflow leída exitosamente desde app.config.")
        except Exception as config_err:
            logger.error(f"[Hilo Param] Error crítico leyendo configuración de Roboflow desde app.config: {config_err}")
            # Marcar estado como error y salir del hilo
            try:
                update_data = {'estado_clasificacion_auto': 'error_config'}
                utils.update_datos_guia(codigo_guia, update_data)
                logger.info(f"[Hilo Param] Estado 'error_config' guardado para guía {codigo_guia}.")
            except Exception as update_e:
                logger.error(f"[Hilo Param] Error adicional al guardar estado 'error_config' para {codigo_guia}: {update_e}")
            return # Terminar el hilo si no se puede leer la config

        # --- LLAMAR A PROCESAMIENTO PASANDO LA CONFIG ---
        try:
            # Asegúrate que la función 'process_images_with_roboflow' está definida ANTES que 'process_thread'
            success, message, results = process_images_with_roboflow(
                codigo_guia,
                fotos_paths,
                guia_fotos_dir,
                json_path,
                roboflow_config # <--- Pasar config como argumento
            )

            end_time = time.time()
            processing_time = end_time - start_time

            # Determinar estado final
            final_status = 'completado' if success else 'error_procesamiento'
            if success and results and 'summary' in results and results['summary'].get('total_racimos_detectados', 0) == 0:
                final_status = 'completado_sin_deteccion'

            # Actualizar estado final
            update_data = {
                'estado_clasificacion_auto': final_status,
                'timestamp_fin_auto': get_utc_timestamp_str(),
                'tiempo_procesamiento_auto': round(processing_time, 2),
                'resultados_auto_resumen': results.get('summary') if results else None
            }
            if utils.update_datos_guia(codigo_guia, update_data):
                logger.info(f"[Hilo Param] Estado final '{final_status}' guardado para guía {codigo_guia}.")
            else:
                logger.error(f"[Hilo Param] Error al guardar estado final para guía {codigo_guia}.")

            logger.info(f"[Hilo Param] Procesamiento completado para guía {codigo_guia}. Tiempo: {processing_time:.2f} segundos. Estado final: {final_status}. Mensaje: {message}")

        except NameError as ne:
             # Error específico si process_images_with_roboflow no está definida antes
             logger.error(f"[Hilo Param] Error de definición: {ne}. Asegúrate que 'process_images_with_roboflow' esté definida ANTES que 'process_thread'.")
             logger.error(traceback.format_exc())
             # Intentar marcar error
             try:
                 update_data = {'estado_clasificacion_auto': 'error_definicion'}
                 utils.update_datos_guia(codigo_guia, update_data)
             except Exception as update_e: logger.error(f"[Hilo Param] Error adicional guardando estado error_definicion: {update_e}")

        except Exception as e:
            # --- Manejo de otros errores durante el procesamiento ---
            end_time = time.time()
            logger.error(f"[Hilo Param] Error GRABE en el hilo de procesamiento para guía {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            try:
                update_data = {
                   'estado_clasificacion_auto': 'error_hilo',
                   'timestamp_fin_auto': get_utc_timestamp_str(),
                   'tiempo_procesamiento_auto': round(end_time - start_time, 2)
                }
                if utils.update_datos_guia(codigo_guia, update_data):
                    logger.info(f"[Hilo Param] Estado 'error_hilo' guardado para guía {codigo_guia} debido a excepción.")
                else:
                    logger.error(f"[Hilo Param] Error al intentar guardar estado 'error_hilo' para guía {codigo_guia}.")
            except Exception as update_e:
                logger.error(f"[Hilo Param] Error adicional al intentar actualizar estado a error_hilo para {codigo_guia}: {update_e}")

@bp.route('/forzar_ver_clasificacion/<path:url_guia>')
def forzar_ver_clasificacion(url_guia):
    logger = logging.getLogger(__name__)
    logger.info(f"Iniciando forzar_ver_clasificacion para guía {url_guia}")
    
    # Inicializar mostrar_automatica para evitar errores
    mostrar_automatica = True
    
    try:
        # Decodificar URL y extraer código guía
        codigo_guia = url_guia.replace('_', '/')
        
        # Extraer partes del código de guía para buscar archivos
        codigo_guia_partes = codigo_guia.replace('/', '_')
        
        # Ruta fija al archivo JSON (usamos la primera opción)
        json_path = os.path.join(current_app.static_folder, 'clasificaciones', f'clasificacion_{codigo_guia_partes}.json')
        
        logger.info(f"Buscando archivo JSON en: {json_path}")
        
        # Verificar existencia del archivo
        if not os.path.exists(json_path):
            flash(f"No se encontró el archivo JSON de clasificación", "danger")
            return redirect(url_for('clasificacion.clasificaciones'))
        
        # Cargar datos del JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            clasificacion_data = json.load(f)
        
        logger.info(f"Archivo JSON cargado correctamente: {json_path}")
        
        # Preparar diccionario para enviar a la plantilla
        template_data = {}
        
        # Extraer código de proveedor
        codigo_proveedor = codigo_guia.split('_')[0]
        
        # Obtener datos del proveedor usando una instancia de Utils
        utils_instance = get_utils_instance()
        try:
            proveedor_data = utils_instance.get_provider_by_code(codigo_proveedor)
            if proveedor_data:
                template_data['codigo_proveedor'] = proveedor_data.get('codigo')
                template_data['nombre_proveedor'] = proveedor_data.get('nombre')
        except Exception as e:
            logger.error(f"Error obteniendo datos del proveedor: {str(e)}")
        
        # Preparar datos para la plantilla
        template_data['codigo_guia'] = codigo_guia
        template_data['fecha_registro'] = clasificacion_data.get('fecha_registro')
        template_data['hora_registro'] = clasificacion_data.get('hora_registro')
        template_data['observaciones'] = clasificacion_data.get('observaciones', '')
        
        # Total de racimos detectados - ESTE ES EL PUNTO CLAVE
        total_racimos_detectados = clasificacion_data.get('total_racimos_detectados', 0)
        logger.info(f"Total racimos detectados en el JSON: {total_racimos_detectados}")
        template_data['total_racimos_detectados'] = total_racimos_detectados
        
        # Fotos (si existen)
        if 'fotos' in clasificacion_data and clasificacion_data['fotos']:
            template_data['fotos'] = clasificacion_data['fotos']
        
        # Datos de clasificación manual
        if 'clasificacion_manual' in clasificacion_data:
            template_data['clasificacion_manual'] = clasificacion_data['clasificacion_manual']
            
            # Calcular porcentajes
            if 'total_racimos' in clasificacion_data['clasificacion_manual']:
                template_data['cantidad_racimos'] = clasificacion_data['clasificacion_manual']['total_racimos']
                
                clasificacion_manual_con_porcentajes = {}
                for categoria, cantidad in clasificacion_data['clasificacion_manual'].items():
                    if categoria != 'total_racimos':
                        porcentaje = (cantidad / clasificacion_data['clasificacion_manual']['total_racimos']) * 100
                        clasificacion_manual_con_porcentajes[categoria] = {
                            'cantidad': cantidad,
                            'porcentaje': porcentaje
                        }
                
                template_data['clasificacion_manual_con_porcentajes'] = clasificacion_manual_con_porcentajes
        
        # ---- PARTE CRÍTICA: DATOS DE CLASIFICACIÓN AUTOMÁTICA ----
        clasificacion_automatica_consolidada = {}
        
        # Verificar si hay datos de clasificación automática
        if 'clasificacion_automatica' in clasificacion_data and clasificacion_data['clasificacion_automatica']:
            clasificacion_automatica = clasificacion_data['clasificacion_automatica']
            
            # Log detallado
            logger.info(f"Datos de clasificación automática encontrados. Tipo: {type(clasificacion_automatica)}")
            logger.info(f"Claves en clasificacion_automatica: {list(clasificacion_automatica.keys())}")
            
            # Procesar cada categoría
            for categoria, datos in clasificacion_automatica.items():
                # Saltar total_racimos, lo procesaremos por separado
                if categoria == 'total_racimos':
                    continue
                
                # Verificar si la estructura es un diccionario o valor directo
                if isinstance(datos, dict) and 'cantidad' in datos:
                    cantidad = datos.get('cantidad', 0)
                    logger.info(f"Categoría {categoria}: cantidad={cantidad} (formato diccionario)")
                    clasificacion_automatica_consolidada[categoria] = {
                        'cantidad': cantidad,
                        'porcentaje': datos.get('porcentaje', 0)
                    }
                else:
                    # Si es un valor directo en lugar de un diccionario
                    cantidad = datos if isinstance(datos, (int, float)) else 0
                    logger.info(f"Categoría {categoria}: cantidad={cantidad} (formato valor directo)")
                    clasificacion_automatica_consolidada[categoria] = {
                        'cantidad': cantidad,
                        'porcentaje': 0  # Se calculará después
                    }
            
            # Calcular total de racimos para porcentajes si no existe
            total_racimos_auto = sum(datos['cantidad'] for categoria, datos in clasificacion_automatica_consolidada.items())
            logger.info(f"Total racimos calculado: {total_racimos_auto}")
            
            # Si no hay racimos calculados, usar el de total_racimos_detectados
            if total_racimos_auto == 0 and total_racimos_detectados > 0:
                total_racimos_auto = total_racimos_detectados
                logger.info(f"Usando total_racimos_detectados como total: {total_racimos_auto}")
            
            # Actualizar porcentajes
            if total_racimos_auto > 0:
                for categoria in clasificacion_automatica_consolidada:
                    cantidad = clasificacion_automatica_consolidada[categoria]['cantidad']
                    porcentaje = (cantidad / total_racimos_auto) * 100
                    clasificacion_automatica_consolidada[categoria]['porcentaje'] = porcentaje
                    logger.info(f"Actualizado porcentaje para {categoria}: {porcentaje:.2f}%")
            
            # Añadir total_racimos a clasificacion_automatica_consolidada
            clasificacion_automatica_consolidada['total_racimos'] = total_racimos_auto
            logger.info(f"Añadido total_racimos a clasificacion_automatica_consolidada: {total_racimos_auto}")
        
        # Agregamos la clasificación automática consolidada al template
        template_data['clasificacion_automatica_consolidada'] = clasificacion_automatica_consolidada
        template_data['mostrar_automatica'] = True  # Siempre mostrar en este endpoint
        
        # Log detallado antes de renderizar
        logger.info(f"DETALLE classificacion_automatica_consolidada: {clasificacion_automatica_consolidada}")
        logger.info(f"DETALLE total_racimos_detectados: {total_racimos_detectados}")
        
        # Renderizar template con los datos preparados
        return render_template('clasificacion/clasificacion_resultados.html', **template_data)
    
    except Exception as e:
        logger.error(f"Error en forzar_ver_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar resultados de clasificación: {str(e)}", "danger")
        return render_template('error.html', error=str(e))

@bp.route('/forzar_ver_clasificacion_v2/<path:url_guia>')
def forzar_ver_clasificacion_v2(url_guia):
    """
    Una función mejorada que carga directamente el archivo JSON de clasificación
    y lo procesa correctamente para mostrar en el template
    """
    logger.info(f"Iniciando forzar_ver_clasificacion_v2 para {url_guia}")
    inicio = time.time()
    
    # Inicializar variables importantes
    mostrar_automatica = True  # Siempre mostrar en este endpoint
    
    try:
        # Decodificar la URL para obtener el código de guía
        codigo_guia_partes = unquote(url_guia)
        logger.info(f"Código de guía a buscar: {codigo_guia_partes}")
        
        # Buscar el archivo JSON directamente
        json_folder = os.path.join(current_app.static_folder, 'clasificaciones')
        json_file = os.path.join(json_folder, f'clasificacion_{codigo_guia_partes}.json')
        
        if not os.path.exists(json_file):
            logger.error(f"No se encontró el archivo JSON: {json_file}")
            flash("No se encontró el archivo de clasificación.", "danger")
            return redirect(url_for('clasificacion.listar_clasificaciones_filtradas'))
        
        # Cargar el archivo JSON
        with open(json_file, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Preparar datos para el template
        template_data = {
            'codigo_guia': codigo_guia_partes,
            'codigo_proveedor': clasificacion_data.get('codigo_proveedor', 'N/A'),
            'nombre_proveedor': clasificacion_data.get('nombre_proveedor', 'N/A'),
            'fecha_registro': clasificacion_data.get('fecha_registro', 'N/A'),
            'hora_registro': clasificacion_data.get('hora_registro', 'N/A'),
            'observaciones': clasificacion_data.get('observaciones', ''),
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {}),
            'peso_bruto': clasificacion_data.get('peso_bruto', 'N/A'),
            'cantidad_racimos': clasificacion_data.get('cantidad_racimos', 'N/A')
        }
        
        # Obtener racimos detectados - garantizamos que exista
        total_racimos_detectados = clasificacion_data.get('total_racimos_detectados', 0)
        template_data['total_racimos_detectados'] = total_racimos_detectados
        
        # Procesar la clasificación automática
        clasificacion_automatica_consolidada = {}
        
        if 'clasificacion_automatica' in clasificacion_data:
            auto_data = clasificacion_data['clasificacion_automatica']
            
            # Categorías estándar
            categorias = ['verdes', 'maduros', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']
            
            # Calcular el total de racimos automáticos
            total_racimos_auto = 0
            
            # Consolidar datos
            for categoria in categorias:
                datos = auto_data.get(categoria, {})
                
                # Manejar tanto diccionarios como valores directos
                if isinstance(datos, dict) and 'cantidad' in datos:
                    cantidad = datos.get('cantidad', 0)
                else:
                    cantidad = datos if isinstance(datos, (int, float)) else 0
                
                # Añadir al total
                total_racimos_auto += cantidad
                
                # Guardar en formato consistente
                clasificacion_automatica_consolidada[categoria] = {
                    'cantidad': cantidad,
                    'porcentaje': 0  # Calcularemos después
                }
            
            # Calcular porcentajes
            if total_racimos_auto > 0:
                for categoria in clasificacion_automatica_consolidada:
                    cantidad = clasificacion_automatica_consolidada[categoria]['cantidad']
                    porcentaje = (cantidad / total_racimos_auto) * 100
                    clasificacion_automatica_consolidada[categoria]['porcentaje'] = porcentaje
                    logger.info(f"Categoría {categoria}: {cantidad} racimos, {porcentaje:.2f}%")
            
            # Importante: Siempre establecer total_racimos, usando detectados si auto es 0
            clasificacion_automatica_consolidada['total_racimos'] = total_racimos_auto if total_racimos_auto > 0 else total_racimos_detectados
            
            logger.info(f"TOTAL RACIMOS AUTO: {total_racimos_auto}")
            logger.info(f"TOTAL RACIMOS DETECTADOS: {total_racimos_detectados}")
            logger.info(f"TOTAL RACIMOS FINAL: {clasificacion_automatica_consolidada['total_racimos']}")
        
        # Guardar la clasificación automática consolidada
        template_data['clasificacion_automatica_consolidada'] = clasificacion_automatica_consolidada
        
        # Renderizar el template
        return render_template('clasificacion/clasificacion_resultados.html',
                               **template_data,
                               time_taken=round(time.time() - inicio, 2),
                               show_debug=True)
    
    except Exception as e:
        logger.error(f"Error en forzar_ver_clasificacion_v2: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al cargar la clasificación: {str(e)}", "danger")
        return redirect(url_for('clasificacion.listar_clasificaciones_filtradas'))

@bp.route('/guardar_clasificacion_final/<path:codigo_guia>', methods=['POST'])
def guardar_clasificacion_final(codigo_guia):
    """
    Guarda la clasificación final en la base de datos y actualiza el estado de la guía.
    """
    try:
        # Obtener la instancia de utils
        utils_instance = get_utils_instance()
        
        # Importar módulos necesarios
        import os
        from datetime import datetime
        import json
        import traceback
        from flask import current_app, redirect, url_for, flash
        
        # Obtener datos de la guía
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontró la guía especificada", "danger")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))
        
        # Cargar datos de clasificación del archivo JSON
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        clasificacion_file = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
        if os.path.exists(clasificacion_file):
            with open(clasificacion_file, 'r', encoding='utf-8') as f:
                clasificacion_data = json.load(f)
                
                # Preparar datos para guardar en la base de datos
                timestamp_utc_str = get_utc_timestamp_str() # Generate UTC timestamp
                datos_clasificacion = {
                    'codigo_guia': codigo_guia,
                    'codigo_proveedor': datos_guia.get('codigo_proveedor'),
                    'nombre_proveedor': datos_guia.get('nombre_proveedor'),
                    # 'fecha_clasificacion': datetime.utcnow().strftime('%d/%m/%Y'), # REMOVE LOCAL
                    # 'hora_clasificacion': datetime.utcnow().strftime('%H:%M:%S'), # REMOVE LOCAL
                    'timestamp_clasificacion_utc': timestamp_utc_str, # Use UTC timestamp
                    'estado': 'completado'
                }
                
                # Agregar datos de clasificación manual
                if 'clasificacion_manual' in clasificacion_data:
                    manual = clasificacion_data['clasificacion_manual']
                    logger.info(f"Clasificación manual encontrada: {manual}")
                    
                    # Mapear las diferentes variantes de nombres de categorías posibles
                    categoria_mapping = {
                        'verde': ['verdes', 'verde'],
                        'sobremaduro': ['sobremaduros', 'sobremaduro'],
                        'danio_corona': ['danio_corona', 'dano_corona'],
                        'pendunculo_largo': ['pendunculo_largo', 'pedunculo_largo'],
                        'podrido': ['podridos', 'podrido']
                    }
                    
                    # Inicializar con valores por defecto
                    valores_manual = {
                        'verde_manual': 0,
                        'sobremaduro_manual': 0,
                        'danio_corona_manual': 0,
                        'pendunculo_largo_manual': 0,
                        'podrido_manual': 0
                    }
                    
                    # Buscar las categorías utilizando las posibles variantes
                    for db_campo, posibles_nombres in categoria_mapping.items():
                        for nombre in posibles_nombres:
                            if nombre in manual:
                                # Convertir a int para asegurar que se guarde correctamente
                                try:
                                    valor = int(float(manual[nombre])) if manual[nombre] is not None else 0
                                except (ValueError, TypeError):
                                    valor = 0
                                valores_manual[f"{db_campo}_manual"] = valor
                                logger.info(f"Asignado {db_campo}_manual = {valor} (encontrado como '{nombre}')")
                                break
                    
                    # Actualizar datos_clasificacion con valores manual
                    datos_clasificacion.update(valores_manual)
                    
                    # Asegurar que los campos individuales estén presentes y sean float
                    datos_clasificacion['verde_manual'] = float(valores_manual.get('verde_manual', 0))
                    datos_clasificacion['sobremaduro_manual'] = float(valores_manual.get('sobremaduro_manual', 0))
                    datos_clasificacion['danio_corona_manual'] = float(valores_manual.get('danio_corona_manual', 0))
                    datos_clasificacion['pendunculo_largo_manual'] = float(valores_manual.get('pendunculo_largo_manual', 0))
                    datos_clasificacion['podrido_manual'] = float(valores_manual.get('podrido_manual', 0))
                    # Forzar el estado a 'completado' siempre
                    datos_clasificacion['estado'] = 'completado'
                    # También crear un diccionario para actualizar datos_guia
                    clasificacion_manual_dict = {
                        'verdes': datos_clasificacion['verde_manual'],
                        'sobremaduros': datos_clasificacion['sobremaduro_manual'],
                        'danio_corona': datos_clasificacion['danio_corona_manual'],
                        'pendunculo_largo': datos_clasificacion['pendunculo_largo_manual'],
                        'podridos': datos_clasificacion['podrido_manual']
                    }
                    
                    # Actualizar los datos de la guía
                    datos_guia['clasificacion_manual'] = clasificacion_manual_dict
                    datos_guia['timestamp_clasificacion_utc'] = timestamp_utc_str  # Add UTC timestamp to datos_guia as well
                    datos_guia['fecha_clasificacion'] = datetime.now(BOGOTA_TZ).strftime('%d/%m/%Y')  # Keep local for display if needed
                    datos_guia['hora_clasificacion'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')  # Keep local for display if needed
                    datos_guia['clasificacion_completada'] = True  # Ensure this flag is set
                    datos_guia['estado_actual'] = 'clasificacion_completada'  # Set state
                    datos_guia['estado_clasificacion'] = 'completado'  # Set state
                    utils_instance.update_datos_guia(codigo_guia, datos_guia)
                    logger.info(f"Actualizada clasificación manual en datos_guia: {clasificacion_manual_dict}")
                    
                    # Siempre guardar el JSON completo para facilitar recuperación
                    # Esto es crucial para asegurar que la clasificación manual se mantenga entre vistas
                    datos_clasificacion['clasificacion_manual_json'] = json.dumps(manual)
                    logger.info(f"JSON de clasificación manual: {datos_clasificacion['clasificacion_manual_json']}")
                    
                    # Actualizar también el archivo JSON original de clasificación
                    clasificacion_data['clasificacion_manual'] = clasificacion_manual_dict
                    # Add timestamp to JSON file as well for consistency
                    clasificacion_data['timestamp_clasificacion_utc'] = timestamp_utc_str
                    clasificacion_data['fecha_clasificacion'] = datos_guia['fecha_clasificacion']  # Keep local in JSON too
                    clasificacion_data['hora_clasificacion'] = datos_guia['hora_clasificacion']  # Keep local in JSON too
                    clasificacion_data['estado_clasificacion'] = 'completado'  # Add status to JSON
                    with open(clasificacion_file, 'w', encoding='utf-8') as f:
                        json.dump(clasificacion_data, f, indent=4)
                    logger.info(f"Archivo de clasificación actualizado en: {clasificacion_file}")
                
                # Agregar datos de clasificación automática si existen
                if 'clasificacion_automatica' in clasificacion_data:
                    auto = clasificacion_data['clasificacion_automatica']
                    logger.info(f"Clasificación automática encontrada en JSON: {auto}") # Log para ver qué se leyó

                    # Guardar el JSON crudo original como respaldo/diagnóstico
                    datos_clasificacion['clasificacion_automatica_json'] = json.dumps(auto)

                    # --- INICIO: Generar datos para clasificacion_consolidada ---
                    consolidada_data = {}
                    # Mapeo de clave interna (usada en dashboard) a clave posible en JSON 'auto'
                    key_mapping_auto = {
                        'verde': 'verdes',
                        'sobremaduro': 'sobremaduros',
                        'danio_corona': 'danio_corona', # Ajustar si nombre en JSON es diferente
                        'pendunculo_largo': 'pendunculo_largo', # Ajustar si nombre en JSON es diferente
                        'podrido': 'podridos'
                    }

                    for db_key, json_key in key_mapping_auto.items():
                        valor_obj = auto.get(json_key) # Obtener valor del JSON leído
                        porcentaje = 0.0 # Usar float por defecto

                        if isinstance(valor_obj, dict) and 'porcentaje' in valor_obj:
                            # Caso 1: Estructura {'porcentaje': P}
                            porcentaje_raw = valor_obj['porcentaje']
                            try:
                                if isinstance(porcentaje_raw, (int, float)):
                                    porcentaje = float(porcentaje_raw)
                                elif isinstance(porcentaje_raw, str):
                                     porcentaje = float(porcentaje_raw.replace('%','').strip())
                                else:
                                     logger.warning(f"Tipo inesperado para 'porcentaje' en {json_key}: {type(porcentaje_raw)}. Usando 0.")
                            except (ValueError, TypeError):
                                 logger.warning(f"No se pudo convertir el porcentaje '{porcentaje_raw}' para {json_key}. Usando 0.")

                        elif isinstance(valor_obj, (int, float)):
                            # Caso 2: Valor numérico directo P
                            porcentaje = float(valor_obj)
                        elif isinstance(valor_obj, str):
                            # Caso 3: Valor string "P" o "P%"
                            try:
                                porcentaje = float(valor_obj.replace('%','').strip())
                            except (ValueError, TypeError):
                                logger.warning(f"No se pudo convertir el valor string '{valor_obj}' para {json_key}. Usando 0.")
                        elif valor_obj is not None:
                             logger.warning(f"Tipo inesperado para el valor de {json_key}: {type(valor_obj)}. Usando 0.")

                        # Crear la estructura {'porcentaje': valor_numerico}
                        # El dashboard espera leer esta estructura desde clasificacion_consolidada
                        consolidada_data[db_key] = {'porcentaje': porcentaje}
                        logger.debug(f"  -> Consolidada[{db_key}] = {consolidada_data[db_key]}")

                    # Convertir el diccionario consolidado a JSON y añadirlo
                    if consolidada_data:
                        datos_clasificacion['clasificacion_consolidada'] = json.dumps(consolidada_data)
                        logger.info(f"JSON de clasificación consolidada generado: {datos_clasificacion['clasificacion_consolidada']}")
                    else:
                        logger.warning("No se generaron datos para clasificación consolidada (posiblemente JSON 'auto' vacío o con claves inesperadas).")
                    # --- FIN: Generar datos para clasificacion_consolidada ---


                    # Obtener porcentajes o cantidades según lo que esté disponible (Código anterior para columnas individuales, se puede mantener o eliminar si clasificacion_consolidada es suficiente)
                    # Mantener por ahora como respaldo o si se usan estas columnas individuales en otro lugar.
                    try:
                        # Extraer el valor numérico del diccionario consolidado recién creado
                        datos_clasificacion.update({
                            'verde_automatico': consolidada_data.get('verde', {}).get('porcentaje', 0.0),
                            'sobremaduro_automatico': consolidada_data.get('sobremaduro', {}).get('porcentaje', 0.0),
                            'danio_corona_automatico': consolidada_data.get('danio_corona', {}).get('porcentaje', 0.0),
                            'pendunculo_largo_automatico': consolidada_data.get('pendunculo_largo', {}).get('porcentaje', 0.0),
                            'podrido_automatico': consolidada_data.get('podrido', {}).get('porcentaje', 0.0)
                        })
                        logger.info("Columnas _automatico individuales actualizadas desde datos consolidados.")
                    except Exception as e:
                        logger.error(f"Error actualizando columnas _automatico individuales: {str(e)}")

                else:
                     logger.warning("No se encontró la clave 'clasificacion_automatica' en el archivo JSON leído.") # Log si falta la clave

                # Guardar datos en la base de datos usando store_clasificacion
                from db_operations import store_clasificacion
                logger.info(f"Calling store_clasificacion from guardar_clasificacion_final with: {datos_clasificacion}")
                # --- INICIO: Log detallado ANTES de guardar ---
                try:
                    # Intentar loguear como JSON para mejor legibilidad
                    datos_log = json.dumps(datos_clasificacion, indent=2, ensure_ascii=False, default=str)
                    logger.info(f"[GUARDAR_FINAL PRE-SAVE] Datos a enviar a store_clasificacion:\n{datos_log}")
                except Exception as log_err:
                    # Fallback si json.dumps falla
                    logger.error(f"[GUARDAR_FINAL PRE-SAVE] Error al dumpear datos_clasificacion para log: {log_err}")
                    logger.info(f"[GUARDAR_FINAL PRE-SAVE] Datos a enviar (raw): {datos_clasificacion}")
                # --- FIN: Log detallado ANTES de guardar ---
                success = store_clasificacion(datos_clasificacion, clasificacion_data.get('fotos', []))
                logger.info(f"Datos de clasificación guardados en la base de datos para {codigo_guia}: {'Éxito' if success else 'Falló'}")
        
        # Actualizar el estado de clasificación en ambas bases de datos
        dbs = ['database.db', 'tiquetes.db']
        actualizado = False
        
        for db_path in dbs:
            try:
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Verificar si la tabla pesajes_bruto existe
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'")
                if not cursor.fetchone():
                    logger.warning(f"Tabla pesajes_bruto no encontrada en {db_path}")
                    continue
                
                # Verificar si existe el registro
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia = ?", (codigo_guia,))
                if not cursor.fetchone():
                    logger.warning(f"No se encontró registro para {codigo_guia} en {db_path}")
                    continue
                
                # Actualizar estado de clasificación
                update_query = """
                UPDATE pesajes_bruto 
                SET estado_clasificacion = 'completado', 
                    clasificacion_completada = 1,
                    estado_actual = 'clasificacion_completada'
                WHERE codigo_guia = ?
                """
                cursor.execute(update_query, (codigo_guia,))
                conn.commit()
                
                logger.info(f"Estado de clasificación actualizado para {codigo_guia} en {db_path}")
                actualizado = True
                
                conn.close()
            except Exception as e:
                logger.error(f"Error actualizando en {db_path}: {str(e)}")
                if 'conn' in locals():
                    conn.close()
        
        # Actualizar directamente usando la función existente
        try:
            import db_utils
            datos_update = {
                'estado_clasificacion': 'completado',
                'clasificacion_completada': True,
                'estado_actual': 'clasificacion_completada'
            }
            db_utils.update_pesaje_bruto(codigo_guia, datos_update)
            logger.info(f"Pesaje bruto actualizado con db_utils para {codigo_guia}")
        except Exception as e:
            logger.error(f"Error actualizando con db_utils: {str(e)}")
        
        # También intentar actualizar usando utils del app
        try:
            from app.utils.db_operations import update_pesaje_bruto
            datos_update = {
                'estado_clasificacion': 'completado',
                'clasificacion_completada': True,
                'estado_actual': 'clasificacion_completada'
            }
            update_pesaje_bruto(codigo_guia, datos_update)
            logger.info(f"Pesaje bruto actualizado con app.utils.db_operations para {codigo_guia}")
        except Exception as e:
            logger.error(f"Error actualizando con app.utils.db_operations: {str(e)}")
        
        # Actualizar archivo JSON si existe
        try:
            import json
            import os
            from flask import current_app
            
            # Directorio donde se almacenan los archivos JSON de las guías
            guias_folder = current_app.config.get('GUIAS_FOLDER')
            json_path = os.path.join(guias_folder, f'guia_{codigo_guia}.json')
            
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    datos_json = json.load(f)
                
                # Actualizar datos JSON con la información de clasificación
                datos_json['clasificacion_completada'] = True
                datos_json['estado_actual'] = 'clasificacion_completada'
                datos_json['fecha_clasificacion'] = datos_guia.get('fecha_clasificacion')
                datos_json['hora_clasificacion'] = datos_guia.get('hora_clasificacion')
                datos_json['estado_clasificacion'] = 'completado'
                
                if 'pasos_completados' not in datos_json:
                    datos_json['pasos_completados'] = ['entrada', 'pesaje', 'clasificacion']
                elif 'clasificacion' not in datos_json['pasos_completados']:
                    datos_json['pasos_completados'].append('clasificacion')
                
                # Guardar los cambios en el archivo JSON
                with open(json_path, 'w') as f:
                    json.dump(datos_json, f, indent=4)
                
                logger.info(f"Archivo JSON actualizado para {codigo_guia}")
        except Exception as e:
            logger.error(f"Error actualizando archivo JSON: {str(e)}")
        
        flash("Clasificación guardada correctamente", "success")
        logger.info(f"Redirigiendo a guía centralizada para {codigo_guia}")
        
        # Redirigir a la vista centralizada usando redirect en lugar de JavaScript
        return redirect(url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia))
    
    except Exception as e:
        logger.error(f"Error en guardar_clasificacion_final: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al guardar la clasificación: {str(e)}", "danger")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))

# Reemplaza la función generate_annotated_image completa con esta:
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
        # Asegúrate que PIL esté importado
        # from PIL import Image, ImageDraw, ImageFont
        # import os (ya deberían estar importados al inicio del archivo)

        if not os.path.exists(original_image_path):
            logger.error(f"Imagen original no encontrada: {original_image_path}")
            return None

        if not output_path:
            base_dir = os.path.dirname(original_image_path)
            base_name = os.path.basename(original_image_path)
            name, ext = os.path.splitext(base_name)
            # Asegurar extensión .jpg para consistencia
            output_path = os.path.join(base_dir, f"{name}_annotated.jpg")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with Image.open(original_image_path) as img:
            # Convertir a RGB si es necesario para dibujar con color
            if img.mode != 'RGB':
                img = img.convert('RGB')
            draw = ImageDraw.Draw(img)
            img_width, img_height = img.size # Obtener dimensiones

            # Colores (puedes ajustar estos)
            class_colors = {
                'verde': (0, 128, 0), 'sobremaduro': (255, 0, 0),
                'danio_corona': (255, 192, 203), 'pendunculo_largo': (0, 0, 255),
                'podrido': (75, 0, 130), 'maduro': (255, 165, 0), # Añadido maduro
                # Añade otros mapeos si son necesarios
            }
            default_color = (128, 128, 128) # Gris por defecto

            # Fuente
            try:
                font = ImageFont.truetype("arial.ttf", 20)
            except IOError:
                try:
                     font = ImageFont.truetype("DejaVuSans.ttf", 20)
                except IOError:
                     font = ImageFont.load_default()

            # Dibujar detecciones
            for detection in detections:
                clase = detection.get('clase', 'desconocido')
                confianza = detection.get('confianza', 0.0)
                bbox = detection.get('bbox') # Debería ser [x1, y1, x2, y2] en píxeles

                if not bbox or len(bbox) != 4:
                    logger.warning(f"Bounding box inválido o ausente para detección: {detection}")
                    continue

                # Usar color mapeado o el por defecto
                color = class_colors.get(clase.lower(), default_color)

                # Dibujar rectángulo (bbox ya debería estar en píxeles absolutos)
                try:
                    # Asegurarse que las coordenadas son enteros
                    coords = [int(c) for c in bbox]
                    draw.rectangle(coords, outline=color, width=3)
                except (ValueError, TypeError) as e:
                    logger.error(f"Error al dibujar rectángulo con bbox {bbox}: {e}")
                    continue

                # Preparar y dibujar etiqueta
                label_text = f"{clase}: {confianza:.0%}"
                try:
                    # Pillow >= 9.3.0
                    text_bbox = draw.textbbox((coords[0], coords[1]), label_text, font=font)
                    text_width = text_bbox[2] - text_bbox[0]
                    text_height = text_bbox[3] - text_bbox[1]
                except AttributeError:
                    # Fallback para versiones antiguas
                    text_size = draw.textsize(label_text, font=font)
                    text_width = text_size[0]
                    text_height = text_size[1]

                # Posición de la etiqueta (arriba a la izquierda de la caja)
                text_x = coords[0] + 2
                text_y = coords[1] + 2
                 # Ajustar si se sale por arriba
                if text_y < 0:
                      text_y = coords[3] - text_height - 2 # Abajo dentro de la caja

                # Dibujar fondo y texto
                draw.rectangle([text_x, text_y, text_x + text_width + 4, text_y + text_height + 4], fill=color)
                draw.text((text_x + 2, text_y + 2), label_text, fill="white", font=font)

            # Guardar la imagen anotada
            img.save(output_path, "JPEG", quality=95) # Guardar como JPEG
            logger.info(f"Imagen procesada generada y guardada en: {output_path}")

            # --- CAMBIO PRINCIPAL: Devolver ruta relativa ---
            try:
                # Calcular ruta relativa desde la carpeta 'static'
                static_folder = current_app.static_folder
                rel_path = os.path.relpath(output_path, static_folder)
                # Normalizar separadores para URLs
                rel_path_url_format = rel_path.replace(os.sep, '/')
                logger.info(f"Devolviendo ruta relativa para imagen anotada: {rel_path_url_format}")
                return rel_path_url_format
            except ValueError:
                 # Si output_path no está dentro de static_folder (ej. discos diferentes)
                 logger.warning(f"No se pudo calcular la ruta relativa para {output_path} desde {static_folder}. Devolviendo ruta absoluta.")
                 return output_path # Devolver absoluta como fallback
            except Exception as rel_path_err:
                 logger.error(f"Error inesperado calculando ruta relativa: {rel_path_err}")
                 return output_path # Devolver absoluta como fallback

    except FileNotFoundError:
         logger.error(f"Error: Imagen original no encontrada en {original_image_path}")
         return None
    except ImportError:
         logger.error("Error: Biblioteca Pillow (PIL) no encontrada. Instálala: pip install Pillow")
         return None
    except Exception as e:
        # Captura cualquier otra excepción de PIL o del sistema de archivos
        logger.error(f"Error generando imagen anotada ({original_image_path}): {str(e)}")
        logger.error(traceback.format_exc())
        return None

@bp.route('/test_annotated_image/<path:url_guia>')
def test_annotated_image(url_guia):
    """
    Ruta para probar la generación de imágenes anotadas con detecciones simuladas
    """
    try:
        import random
        
        # Obtener lista de imágenes disponibles para la guía
        photos_dir = os.path.join(current_app.static_folder, 'uploads', 'fotos', url_guia)
        
        if not os.path.exists(photos_dir):
            flash("No se encontraron imágenes para esta guía", "warning")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))
        
        # Buscar archivos de imagen en el directorio
        image_files = [
            os.path.join(photos_dir, f) for f in os.listdir(photos_dir) 
            if f.endswith('.jpg') and not f.endswith('_annotated.jpg') and not f.endswith('_resized.jpg')
        ]
        
        if not image_files:
            flash("No se encontraron imágenes elegibles para esta guía", "warning")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))
        
        # Seleccionar una imagen aleatoria para la prueba
        image_path = random.choice(image_files)
        
        # Crear detecciones de prueba simuladas
        detections = []
        num_detections = random.randint(5, 15)  # Entre 5 y 15 detecciones aleatorias
        
        for _ in range(num_detections):
            class_type = random.choice(['verde', 'maduro', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido'])
            
            detection = {
                'x': random.uniform(0.1, 0.9),        # Posición X normalizada
                'y': random.uniform(0.1, 0.9),        # Posición Y normalizada
                'width': random.uniform(0.05, 0.3),   # Ancho normalizado
                'height': random.uniform(0.05, 0.3),  # Alto normalizado
                'class': class_type,                  # Clase de detección
                'confidence': random.uniform(0.7, 0.99)  # Confianza entre 70% y 99%
            }
            
            detections.append(detection)
        
        # Preparar ruta para la imagen anotada
        output_name = f"test_annotated_{os.path.basename(image_path)}"
        output_path = os.path.join(photos_dir, output_name)
        
        # Generar la imagen anotada utilizando la función mejorada
        # REMOVED: from app.blueprints.clasificacion.generate_annotated_image import generate_annotated_image
        result_path = generate_annotated_image(image_path, detections, output_path)
        
        if result_path:
            # Convertir ruta absoluta a relativa para mostrarla en el navegador
            if os.path.isabs(result_path):
                rel_path = result_path.replace(current_app.static_folder, '').lstrip('/')
                result_url = url_for('static', filename=rel_path)
            else:
                result_url = result_path
                
            # Convertir ruta de imagen original para mostrarse en navegador
            if os.path.isabs(image_path):
                orig_rel_path = image_path.replace(current_app.static_folder, '').lstrip('/')
                orig_url = url_for('static', filename=orig_rel_path)
            else:
                orig_url = image_path
            
            return render_template(
                'clasificacion/test_annotated_image.html',
                original_image=orig_url,
                annotated_image=result_url,
                detections=detections,
                num_detections=len(detections),
                guia=url_guia
            )
        else:
            flash("Error al generar la imagen anotada. Verifique los logs para más detalles.", "error")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))
            
    except Exception as e:
        logger.error(f"Error en test_annotated_image: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar imagen anotada: {str(e)}", "error")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))


@bp.route('/regenerar_imagenes/<path:url_guia>')
def regenerar_imagenes(url_guia):
    utils = get_utils_instance()
    try:
        codigo_guia = url_guia.replace('/', '_') # Reemplazar slash por guión bajo
        logger.info(f"Regenerando imágenes anotadas para: {codigo_guia}")

        # Ruta del archivo JSON
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")

        if not os.path.exists(json_path):
            logger.warning(f"No se encontró JSON de clasificación: {json_path}")
            flash(f'No se encontró el archivo de clasificación JSON para {codigo_guia}', 'warning')
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))

        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)

        annotated_images = []
        guia_fotos_dir = os.path.join(current_app.static_folder, 'uploads', 'clasificacion_fotos', codigo_guia)

        if 'clasificacion_automatica' in clasificacion_data and 'detalles_por_imagen' in clasificacion_data['clasificacion_automatica']:
            for imagen_info in clasificacion_data['clasificacion_automatica']['detalles_por_imagen']:
                original_filename = imagen_info.get('nombre_original')
                detections = imagen_info.get('detecciones', [])

                if not original_filename:
                    logger.warning(f"Falta nombre original en detalles_por_imagen: {imagen_info}")
                    continue

                original_image_path = os.path.join(guia_fotos_dir, original_filename)
                annotated_output_filename = f"annotated_{original_filename}"
                annotated_output_path = os.path.join(guia_fotos_dir, annotated_output_filename)

                if not os.path.exists(original_image_path):
                    logger.warning(f"Imagen original no encontrada para anotar: {original_image_path}")
                    continue

                logger.info(f"Generando imagen anotada para: {original_filename} -> {annotated_output_filename}")
                # Usar la función local o importada correctamente
                generated_path = generate_annotated_image(original_image_path, detections, annotated_output_path)
                if generated_path:
                    # Construir URL relativa para el template
                    relative_path = os.path.join('uploads', 'clasificacion_fotos', codigo_guia, annotated_output_filename)
                    annotated_images.append(url_for('static', filename=relative_path))
                    logger.info(f"Imagen anotada generada: {generated_path}")
                else:
                    logger.error(f"Error generando imagen anotada para {original_filename}")

            flash('Imágenes anotadas regeneradas correctamente.', 'success')
        else:
            flash('No se encontraron detalles de detección para regenerar imágenes.', 'warning')

        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))

    except Exception as e:
        logger.error(f"Error regenerando imágenes: {str(e)}", exc_info=True)
        flash(f'Error al regenerar las imágenes: {str(e)}', 'danger')
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))

@bp.route('/sync_clasificacion/<codigo_guia>')
def sync_clasificacion(codigo_guia):
    """
    Sincroniza los datos de clasificación desde el archivo JSON a la base de datos.
    Utiliza la conexión centralizada. (Versión API/directa)
    """
    conn = None # Inicializar conexión
    try:
        # Construir ruta al archivo JSON
        json_filename = f"clasificacion_{codigo_guia}.json"
        clasificaciones_dir = current_app.config.get('CLASIFICACIONES_DIR', os.path.join(current_app.static_folder, 'clasificaciones'))
        json_path = os.path.join(clasificaciones_dir, json_filename)

        if not os.path.exists(json_path):
            current_app.logger.warning(f"Archivo JSON no encontrado para sync: {json_path}")
            return jsonify({'success': False, 'message': 'Archivo JSON no encontrado'}), 404

        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)

        # >>> CAMBIO PRINCIPAL: Usar la función de utilidad <<<
        conn = get_db_connection()
        cursor = conn.cursor()

        # Preparar los datos para la actualización/inserción
        timestamp_clasificacion = clasificacion_data.get('timestamp_clasificacion_utc', get_utc_timestamp_str())
        manual_json = json.dumps(clasificacion_data.get('clasificacion_manual', {}))
        auto_json = json.dumps(clasificacion_data.get('clasificacion_automatica', {}))
        estado_clasificacion = clasificacion_data.get('estado_clasificacion', clasificacion_data.get('estado', 'completado'))

        # Intentar actualizar primero
        update_sql = """
            UPDATE clasificaciones
            SET timestamp_clasificacion_utc = ?,
                clasificacion_manual_json = ?,
                clasificacion_automatica_json = ?,
                estado_clasificacion = ?
            WHERE codigo_guia = ?
        """
        cursor.execute(update_sql, (
            timestamp_clasificacion,
            manual_json,
            auto_json,
            estado_clasificacion,
            codigo_guia
        ))

        # Si no se actualizó ningún registro, insertar uno nuevo
        if cursor.rowcount == 0:
            insert_sql = """
                INSERT INTO clasificaciones (
                    codigo_guia, timestamp_clasificacion_utc,
                    clasificacion_manual_json, clasificacion_automatica_json,
                    estado_clasificacion
                ) VALUES (?, ?, ?, ?, ?)
            """
            cursor.execute(insert_sql, (
                codigo_guia,
                timestamp_clasificacion,
                manual_json,
                auto_json,
                estado_clasificacion
            ))

        conn.commit()
        current_app.logger.info(f"Datos de clasificación sincronizados (vía API) para guía {codigo_guia}")
        return jsonify({
            'success': True,
            'message': 'Datos de clasificación sincronizados correctamente'
        })

    except Exception as e:
        current_app.logger.error(f"Error en sync_clasificacion (API) para {codigo_guia}: {str(e)}")
        current_app.logger.error(traceback.format_exc())
        if conn: # Intentar rollback si la conexión se estableció
            try:
                conn.rollback()
                current_app.logger.info(f"Rollback realizado en sync_clasificacion (API) para {codigo_guia} debido a error.")
            except Exception as rb_err:
                current_app.logger.error(f"Error durante el rollback en sync_clasificacion (API) para {codigo_guia}: {rb_err}")
        # Devolver error como JSON
        return jsonify({
            'success': False,
            'message': f'Error interno al sincronizar datos de clasificación: {str(e)}'
        }), 500
    finally:
        # Asegurarse de cerrar la conexión
        if conn:
            conn.close()
            current_app.logger.debug(f"Conexión a BD cerrada para {codigo_guia} en sync_clasificacion (API).")

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
        conn = get_db_connection()
        # conn.row_factory ya está establecido en get_db_connection()
        cursor = conn.cursor()

        # Obtener datos principales de clasificación
        cursor.execute("SELECT * FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()

        if row:
            # Convertir Row a diccionario mutable
            clasificacion = dict(row)

            # Procesar JSON si existen
            if 'clasificacion_manual_json' in clasificacion and clasificacion['clasificacion_manual_json']:
                try:
                    clasificacion['clasificacion_manual'] = json.loads(clasificacion['clasificacion_manual_json'])
                except json.JSONDecodeError:
                    logger.error(f"Error decodificando clasificacion_manual_json para {codigo_guia}: {clasificacion['clasificacion_manual_json']}")
                    clasificacion['clasificacion_manual'] = {} # Default a dict vacío

            if 'clasificacion_automatica_json' in clasificacion and clasificacion['clasificacion_automatica_json']:
                try:
                    clasificacion['clasificacion_automatica'] = json.loads(clasificacion['clasificacion_automatica_json'])
                except json.JSONDecodeError:
                    logger.error(f"Error decodificando clasificacion_automatica_json para {codigo_guia}: {clasificacion['clasificacion_automatica_json']}")
                    clasificacion['clasificacion_automatica'] = {} # Default a dict vacío

            # Obtener fotos asociadas (si la tabla existe y es relevante)
            # Considerar mover esto a una función separada si la lógica crece
            try:
                cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto",
                             (codigo_guia,))
                fotos = [foto_row[0] for foto_row in cursor.fetchall()]
                clasificacion['fotos'] = fotos
            except sqlite3.OperationalError as table_err:
                # Manejar caso donde la tabla fotos_clasificacion podría no existir aún
                if "no such table" in str(table_err):
                    logger.warning(f"Tabla fotos_clasificacion no encontrada para {codigo_guia}. Omitiendo fotos.")
                    clasificacion['fotos'] = []
                else:
                    raise # Relanzar otros errores de SQL

            logger.debug(f"Clasificación encontrada para {codigo_guia}")
            return clasificacion
        else:
            logger.warning(f"No se encontró registro de clasificación para {codigo_guia}")
            return None

    except sqlite3.Error as e:
        logger.error(f"Error de base de datos recuperando clasificación para {codigo_guia}: {e}")
        logger.error(traceback.format_exc())
        return None # Devolver None en caso de error de BD
    except Exception as e:
        logger.error(f"Error inesperado recuperando clasificación para {codigo_guia}: {e}")
        logger.error(traceback.format_exc())
        return None # Devolver None en caso de error general
    finally:
        # Asegurarse de cerrar la conexión
        if conn:
            conn.close()
            logger.debug(f"Conexión a BD cerrada para {codigo_guia} en get_clasificacion_by_codigo_guia.")

@bp.route('/ver_detalles_clasificacion/<url_guia>')
def ver_detalles_clasificacion(url_guia):
    """
    Muestra los detalles de clasificación por foto para una guía específica
    """
    import time
    from flask import current_app, make_response, flash, render_template, url_for # Asegurar imports
    start_time = time.time()

    logger.info(f"Iniciando ver_detalles_clasificacion para {url_guia}")

    template_data = {
        'url_guia': url_guia,
        'resultados_por_foto': [],
        'fotos_originales': [],
        'fotos_procesadas': [],  # Variable para el template
        'clasificacion_automatica_consolidada': {},
        'raw_data': {},
        'debug_info': {},
        'json_path': '',
        'tiempo_procesamiento': '',
        'datos_guia': {}, # Initialize datos_guia
        'error': None # Añadir para manejar errores en template
    }

    try:
        codigo_guia = url_guia # Usar url_guia directamente aquí
        logger.info(f"Código de guía a buscar: {codigo_guia}")

        # --- RUTA CORREGIDA PARA BUSCAR EL JSON ---
        # Buscar primero en la ubicación estándar donde se guarda
        base_dir_relativo = os.path.join('uploads', codigo_guia)
        json_filename = f"clasificacion_{codigo_guia}.json"
        clasificacion_path = os.path.join(current_app.static_folder, base_dir_relativo, json_filename)
        template_data['json_path'] = clasificacion_path # Guardar la ruta intentada
        logger.info(f"Intentando buscar archivo JSON en la ruta estándar: {clasificacion_path}")
        # -------------------------------------------

        # Comprobar si existe en la ruta estándar
        if not os.path.exists(clasificacion_path):
            logger.warning(f"Archivo JSON no encontrado en ruta estándar: {clasificacion_path}. Intentando rutas alternativas...")
            # Intentar buscar en rutas alternativas (si aún las necesitas como fallback)
            alt_paths_to_check = [
                os.path.join(current_app.static_folder, 'clasificaciones', json_filename), # La ruta original incorrecta
                os.path.join(current_app.static_folder, 'fotos_racimos_temp', codigo_guia, json_filename),
                os.path.join(current_app.static_folder, current_app.config.get('FOTOS_RACIMOS_FOLDER', 'fotos_racimos_temp'), codigo_guia, json_filename)
            ]
            found_alt = False
            for alt_path in alt_paths_to_check:
                 if os.path.exists(alt_path):
                     clasificacion_path = alt_path
                     template_data['json_path'] = alt_path # Actualizar la ruta encontrada
                     logger.info(f"Archivo de clasificación encontrado en ruta alternativa: {alt_path}")
                     found_alt = True
                     break
            if not found_alt:
                logger.error(f"No se encontró el archivo de clasificación para: {codigo_guia} en NINGUNA ruta verificada.")
                flash("No se encontró información de clasificación detallada para esta guía", "error")
                # Asegurarse de renderizar el template correcto incluso en error
                template_data['error'] = "Archivo JSON de detalles no encontrado."
                return render_template('detalles_clasificacion.html', **template_data)


        # Leer el archivo de clasificación (ahora con la ruta correcta)
        with open(clasificacion_path, 'r', encoding='utf-8') as f:
            clasificacion_data = json.load(f)
            logger.info(f"Clasificación detallada leída del archivo: {clasificacion_path}")
            template_data['raw_data'] = clasificacion_data
            # Asegurar que tiempo_procesamiento exista, usar 'N/A' si no
            template_data['tiempo_procesamiento'] = clasificacion_data.get('tiempo_total_procesamiento_seg', 'N/A')


        # --- OBTENER DATOS DE GUÍA (Código existente) ---
        try:
            utils = Utils(current_app) # Asumiendo que Utils está definido o importado
            datos_guia = utils.get_datos_guia(url_guia)
            template_data['datos_guia'] = datos_guia if datos_guia else {} # Asignar dict vacío si es None
            logger.info(f"Datos de guía obtenidos: {template_data['datos_guia']}")
        except NameError: # Capturar si Utils no está definido
            logger.error("La clase Utils no está definida o importada.")
            template_data['datos_guia'] = {}
        except Exception as e:
            logger.error(f"Error al obtener datos de la guía: {str(e)}")
            logger.error(traceback.format_exc())
            template_data['datos_guia'] = {}
        # --------------------------------------------------

        # --- PROCESAR fotos_procesadas DEL JSON (Lógica principal) ---
        resultados_por_foto_procesados = []
        fotos_originales_urls = [] # Lista para guardar URLs originales

        # Extraer la lista 'imagenes_procesadas' del JSON leído
        imagenes_procesadas_json = clasificacion_data.get('imagenes_procesadas', [])

        if isinstance(imagenes_procesadas_json, list):
             logger.info(f"Procesando {len(imagenes_procesadas_json)} entradas de 'imagenes_procesadas' del JSON.")
             for img_data in imagenes_procesadas_json:
                 if not isinstance(img_data, dict):
                     logger.warning(f"Elemento no esperado en 'imagenes_procesadas': {img_data}")
                     continue

                 foto_numero = img_data.get('numero', img_data.get('indice', '?')) # Usar numero o indice

                 # --- URL Imagen Original ---
                 # Usar la ruta relativa guardada en el JSON directamente si existe
                 imagen_original_rel_path = img_data.get('imagen_original')
                 imagen_original_url = None
                 if imagen_original_rel_path:
                     try:
                          imagen_original_url = url_for('static', filename=imagen_original_rel_path)
                          fotos_originales_urls.append(imagen_original_url) # Guardar para resumen
                          logger.debug(f"Foto {foto_numero}: URL original generada desde JSON: {imagen_original_url}")
                     except Exception as url_err:
                          logger.error(f"Foto {foto_numero}: Error generando URL para imagen original relativa '{imagen_original_rel_path}': {url_err}")
                          imagen_original_url = "#error" # Indicar error
                 else:
                     logger.warning(f"Foto {foto_numero}: No se encontró 'imagen_original' (ruta relativa) en los datos JSON.")
                     imagen_original_url = "#no_encontrada"

                 # --- URL Imagen Anotada ---
                 # Usar la ruta relativa guardada 'ruta_anotada' o 'imagen_annotated'
                 imagen_annotated_rel_path = img_data.get('ruta_anotada', img_data.get('imagen_annotated'))
                 imagen_annotated_url = None
                 if imagen_annotated_rel_path:
                     try:
                         imagen_annotated_url = url_for('static', filename=imagen_annotated_rel_path)
                         logger.debug(f"Foto {foto_numero}: URL anotada generada desde JSON: {imagen_annotated_url}")
                     except Exception as url_err:
                         logger.error(f"Foto {foto_numero}: Error generando URL para imagen anotada relativa '{imagen_annotated_rel_path}': {url_err}")
                         imagen_annotated_url = "#error_annotated"
                 else:
                     logger.warning(f"Foto {foto_numero}: No se encontró ruta relativa ('ruta_anotada' o 'imagen_annotated') en los datos JSON.")
                     imagen_annotated_url = "#no_annotated"

                 # --- URL Imagen Clasificada (Priorizar la de Roboflow) ---
                 imagen_clasificada_rel_path = img_data.get('ruta_clasificada_rf') # Buscar la clave nueva
                 imagen_clasificada_url = None
                 if imagen_clasificada_rel_path:
                     try:
                         imagen_clasificada_url = url_for('static', filename=imagen_clasificada_rel_path)
                         logger.debug(f"Foto {foto_numero}: URL clasificada (RF) generada desde JSON: {imagen_clasificada_url}")
                     except Exception as url_err:
                         logger.error(f"Foto {foto_numero}: Error generando URL para imagen clasificada RF relativa '{imagen_clasificada_rel_path}': {url_err}")
                         imagen_clasificada_url = "#error_clasificada_rf"
                 else:
                     # Fallback a la imagen anotada local si no se guardó la de Roboflow
                     logger.warning(f"Foto {foto_numero}: No se encontró 'ruta_clasificada_rf'. Usando imagen anotada local como fallback para clasificada.")
                     imagen_clasificada_url = imagen_annotated_url # Fallback

                 # --- Detecciones y Conteos ---
                 detecciones = img_data.get('detections', []) # BBOX (puede estar vacía)
                 conteo_categorias = img_data.get('conteo_categorias', {}) # Categorías calculadas
                 total_racimos = img_data.get('num_racimos_detectados', img_data.get('total_racimos', 0)) # Usar num_racimos...

                 # Preparar el diccionario final para esta foto para el template
                 foto_procesada = {
                    'numero': foto_numero,
                    'imagen_original': imagen_original_url,
                    'imagen_annotated': imagen_annotated_url, # La local con bboxes
                    'imagen_clasificada': imagen_clasificada_url, # La de Roboflow (o fallback)
                    'detecciones': detecciones,
                    'conteo_categorias': conteo_categorias,
                    'total_racimos': total_racimos
                 }
                 resultados_por_foto_procesados.append(foto_procesada)
                 logger.info(f"Foto {foto_numero}: Procesada para template. Total Racimos: {total_racimos}")

        else:
             logger.error("'imagenes_procesadas' no es una lista o no existe en el JSON leído.")
             flash("El formato del archivo de detalles es incorrecto.", "error")
             template_data['error'] = "Formato de archivo de detalles incorrecto."
             # Continuar para renderizar el template con el error

        # Asignar listas procesadas al diccionario del template
        template_data['fotos_procesadas'] = resultados_por_foto_procesados
        template_data['fotos_originales'] = fotos_originales_urls # Para el resumen si lo usa

        # --- Calcular total acumulado (código existente) ---
        total_racimos_acumulados = 0
        for foto in resultados_por_foto_procesados:
            racimos_foto = foto.get('total_racimos', 0)
            if racimos_foto is not None:
                try:
                    total_racimos_acumulados += int(racimos_foto)
                except (ValueError, TypeError):
                    logger.warning(f"Valor no numérico para total_racimos en foto {foto.get('numero', '?')}: {racimos_foto}")
        template_data['total_racimos_acumulados'] = total_racimos_acumulados
        logger.info(f"Total de racimos acumulados calculado para la plantilla: {total_racimos_acumulados}")

        end_time = time.time()
        # Sobrescribir tiempo si no estaba en el JSON
        if template_data['tiempo_procesamiento'] == 'N/A':
            template_data['tiempo_procesamiento'] = round(end_time - start_time, 2)

        # --- Guardar totales consolidados (código existente, verificar si es necesario aquí) ---
        # Considera si esto debe hacerse aquí o en otro lugar. Si el JSON ya existe,
        # probablemente estos datos ya se guardaron. Quizás solo si se *regenera* el JSON.
        # try:
        #     # ... (código para guardar en BD) ...
        # except Exception as db_err:
        #     logger.error(f"Error guardando datos consolidados (desde detalles): {db_err}")
        # --------------------------------------------------------------------------

        logger.info(f"Renderizando plantilla detalles_clasificacion.html con {len(template_data['fotos_procesadas'])} fotos.")
        return render_template('detalles_clasificacion.html', **template_data)

    except json.JSONDecodeError as json_err:
         logger.error(f"Error fatal decodificando JSON en ver_detalles_clasificacion ({clasificacion_path}): {json_err}")
         flash(f"Error al leer el archivo de detalles: {json_err}", "error")
         template_data['error'] = f"Error al leer archivo de detalles: {json_err}"
         return render_template('detalles_clasificacion.html', **template_data)
    except Exception as e:
        logger.error(f"Error general en ver_detalles_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar detalles de clasificación: {str(e)}", "error")
        template_data['error'] = str(e)
        return render_template('detalles_clasificacion.html', **template_data)

def tu_funcion_que_prepara_contexto(datos_guia):
    # ... otros cálculos previos ...

    # Obtener la fecha de pesaje a partir del timestamp
    if datos_guia.get('timestamp_pesaje_utc'):
        fecha_pesaje, _ = convertir_timestamp_a_fecha_hora(datos_guia['timestamp_pesaje_utc'])
    else:
        fecha_pesaje = "Pendiente"

    contexto = {
        # ... otros campos ...
        'fecha_pesaje': fecha_pesaje,
        # ... otros campos ...
    }
    # ... resto de la función ...
    return contexto
