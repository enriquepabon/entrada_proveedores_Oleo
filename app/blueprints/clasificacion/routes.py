from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import glob
import logging
import traceback
import base64
from datetime import datetime
import json
import time
import threading
import re
import shutil
import random
from pathlib import Path
import requests  # Asegurarse de que requests está importado
from werkzeug.utils import secure_filename
from . import bp
from app.utils.common import CommonUtils as Utils
import fnmatch
from PIL import Image
from urllib.parse import unquote
import sqlite3
from PIL import Image, ImageDraw, ImageFont
from app.blueprints.clasificacion.utils import normalize_image_path, find_annotated_image, find_original_images
from jinja2 import TemplateNotFound
from io import BytesIO
import numpy as np
import pytz

# Configurar logging
logger = logging.getLogger(__name__)

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
        
    def run_workflow(self, workspace_name, workflow_id, images, use_cache=True):
        """
        Ejecuta un workflow de Roboflow usando solicitudes HTTP directas.
        Compatible con la interfaz del SDK oficial.
        """
        image_path = images.get("image")
        logger.info(f"Ejecutando workflow {workflow_id} con imagen {image_path}")
        
        workflow_url = f"https://detect.roboflow.com/infer/workflows/{workspace_name}/{workflow_id}"
        
        # Si la imagen es un archivo local, primero vamos a verificar su tamaño
        if os.path.exists(image_path):
            try:
                # Abrir la imagen y verificar su tamaño
                with Image.open(image_path) as img:
                    width, height = img.size
                    logger.info(f"Imagen original: {width}x{height} pixels")
                    
                    # Tamaño máximo permitido por Roboflow
                    max_width = 1152
                    max_height = 2048
                    
                    # Verificar si la imagen necesita ser redimensionada
                    if width > max_width or height > max_height:
                        logger.info(f"La imagen excede el tamaño máximo permitido por Roboflow. Redimensionando...")
                        # Calcular ratio para mantener proporciones
                        ratio = min(max_width/width, max_height/height)
                        new_size = (int(width * ratio), int(height * ratio))
                        
                        # Crear un archivo temporal para la imagen redimensionada
                        resized_image_path = image_path.replace('.jpg', '_resized.jpg')
                        if not resized_image_path.endswith('.jpg'):
                            resized_image_path += '_resized.jpg'
                        
                        # Redimensionar y guardar
                        resized_img = img.resize(new_size, Image.LANCZOS)
                        resized_img.save(resized_image_path, "JPEG", quality=95)
                        logger.info(f"Imagen redimensionada guardada en: {resized_image_path}")
                        
                        # Usar la imagen redimensionada en lugar de la original
                        image_path = resized_image_path
            except Exception as e:
                logger.error(f"Error al procesar la imagen: {str(e)}")
                logger.error(traceback.format_exc())
                # Continuar con la imagen original si hay error en el redimensionamiento
            
            # Codificar la imagen en base64 para enviar a Roboflow
            with open(image_path, "rb") as image_file:
                image_data = base64.b64encode(image_file.read()).decode("utf-8")
                
            payload = {
                "api_key": self.api_key,
                "inputs": {
                    "image": {"type": "base64", "value": image_data}
                }
            }
        else:
            # Si es una URL, usar ese formato
            payload = {
                "api_key": self.api_key,
                "inputs": {
                    "image": {"type": "url", "value": image_path}
                }
            }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Enviando solicitud HTTP a {workflow_url}")
            response = requests.post(
                workflow_url, 
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Respuesta recibida correctamente de Roboflow")
                return result
            else:
                logger.error(f"Error en la respuesta de Roboflow: {response.status_code} - {response.text}")
                # Check common error causes
                if response.status_code == 401 or response.status_code == 403:
                    logger.error("Error de autenticación - Verificar API key de Roboflow")
                    return {"error": f"Error de autenticación ({response.status_code}): {response.text}", "auth_error": True}
                elif response.status_code == 404:
                    logger.error("Workflow o workspace no encontrado - Verificar IDs")
                    return {"error": f"Workflow o workspace no encontrado: {response.text}", "not_found": True}
                elif response.status_code >= 500:
                    logger.error("Error del servidor de Roboflow - Puede ser un problema temporal")
                    return {"error": f"Error del servidor de Roboflow ({response.status_code}): {response.text}", "server_error": True}
                else:
                    return {"error": f"Error {response.status_code}: {response.text}"}
        except Exception as e:
            logger.error(f"Error en solicitud a Roboflow: {str(e)}")
            logger.error(traceback.format_exc())
            return {"error": str(e)}

# Dictionary to store processing status
processing_status = {}

# Configuration for Roboflow (you may need to adjust these based on your actual configuration)
WORKSPACE_NAME = os.environ.get('ROBOFLOW_WORKSPACE', 'enrique-p-workspace')
WORKFLOW_ID = os.environ.get('ROBOFLOW_WORKFLOW_ID', 'clasificacion-racimos-3')
ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', 'huyFoCQs7090vfjDhfgK')

# Helper function to get a utils instance
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
    Registra la clasificación manual de racimos.
    """
    try:
        # Agregar logs detallados para depuración
        logger.info("=== INICIO PROCESAMIENTO DE CLASIFICACIÓN ===")
        logger.info(f"Formulario recibido: {request.form}")
        logger.info(f"Archivos recibidos: {list(request.files.keys())}")
        logger.info(f"Headers: {request.headers}")
        logger.info(f"Content-Type: {request.content_type}")
        
        # Obtener los datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        logger.info(f"Código guía extraído del formulario: {codigo_guia}")
        
        if not codigo_guia:
            logger.error("No se proporcionó un código de guía")
            flash("Error: No se proporcionó un código de guía", "danger")
            return redirect(url_for('pesaje.lista_pesajes'))
        
        # Crear directorios para imágenes y clasificaciones si no existen
        fotos_temp_dir = os.path.join(current_app.static_folder, 'fotos_racimos_temp')
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        temp_clasificacion_dir = os.path.join(current_app.static_folder, 'uploads', 'temp_clasificacion')
        os.makedirs(fotos_temp_dir, exist_ok=True)
        os.makedirs(clasificaciones_dir, exist_ok=True)
        os.makedirs(temp_clasificacion_dir, exist_ok=True)
        logger.info(f"Directorios creados o verificados: {fotos_temp_dir}, {clasificaciones_dir}, {temp_clasificacion_dir}")
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            logger.warning(f"No se encontraron datos para la guía: {codigo_guia}")
            flash("Error: No se encontraron datos para la guía especificada", "danger")
            return redirect(url_for('pesaje.lista_pesajes'))
        
        # Capturar todos los datos de clasificación manual
        clasificacion_manual = {
            'verdes': float(request.form.get('verdes', 0) or 0),
            'maduros': float(request.form.get('maduros', 0) or 0),
            'sobremaduros': float(request.form.get('sobremaduros', 0) or 0),
            'danio_corona': float(request.form.get('dano_corona', 0) or 0),
            'pendunculo_largo': float(request.form.get('pedunculo_largo', 0) or 0),
            'podridos': float(request.form.get('podridos', 0) or 0)
        }
        
        # Log para depuración
        logger.info(f"Datos de clasificación manual: {clasificacion_manual}")
        logger.info(f"Form data recibido: {request.form}")
        
        # Procesamiento de las fotos subidas
        fotos_paths = []
        timestamp = int(time.time())
        
        # Revisar y guardar las imágenes proporcionadas
        logger.info("Revisando archivos de fotos enviados...")
        logger.info(f"Claves de archivos: {list(request.files.keys())}")
        
        for i in range(1, 4):
            key = f'foto-{i}'
            if key in request.files:
                file = request.files[key]
                logger.info(f"Encontrado archivo para {key}: {file.filename}")
                
                if file and file.filename:
                    # Asegurar que el nombre del archivo sea seguro
                    filename = secure_filename(file.filename)
                    # Agregar timestamp al nombre para evitar problemas de caché
                    base, ext = os.path.splitext(filename)
                    # Guardar en formato con nombre consistente para que pueda ser encontrado después
                    new_filename = f"temp_clasificacion_{codigo_guia}_{i}_{timestamp}{ext}"
                    filepath = os.path.join(temp_clasificacion_dir, new_filename)
                    logger.info(f"Guardando archivo {key} como: {new_filename}")
                    file.save(filepath)
                    fotos_paths.append(filepath)
                    logger.info(f"Imagen {i} guardada en: {filepath}")
                else:
                    logger.info(f"El archivo {key} no tiene nombre de archivo o está vacío")
            else:
                logger.info(f"No se encontró el archivo {key} en la solicitud")
        
        # Si no hay fotos, registrar una advertencia
        if not fotos_paths:
            logger.warning(f"No se encontraron fotos para procesar en la solicitud para la guía {codigo_guia}")
        
        # Capturar observaciones
        observaciones = request.form.get('observaciones', '')
        
        # Guardar la clasificación manual con timestamp
        now = datetime.now()
        fecha_clasificacion = now.strftime('%d/%m/%Y')
        hora_clasificacion = now.strftime('%H:%M:%S')
        
        # Preparar la estructura de datos completa
        clasificacion_data = {
            'id': f"Clasificacion_{codigo_guia}",
            'codigo_guia': codigo_guia,
            'codigo_proveedor': datos_guia.get('codigo_proveedor') or datos_guia.get('codigo'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor'),
            'fecha_registro': fecha_clasificacion,
            'hora_registro': hora_clasificacion,
            'fecha_clasificacion': fecha_clasificacion,
            'hora_clasificacion': hora_clasificacion,
            'clasificacion_manual': clasificacion_manual,
            'clasificaciones': clasificacion_manual,  # Agregar también como "clasificaciones" para compatibilidad
            'observaciones': observaciones,
            'estado': 'completado',
            'total_racimos_detectados': sum(clasificacion_manual.values()),
            'fotos': fotos_paths
        }
        
        # Si hay datos de clasificación automática, guardarlos también
        usar_clasificacion_automatica = request.form.get('usar_clasificacion_automatica') is not None
        if usar_clasificacion_automatica and 'clasificacion_automatica' in datos_guia:
            clasificacion_data['clasificacion_automatica'] = datos_guia['clasificacion_automatica']
        else:
            clasificacion_data['clasificacion_automatica'] = {}
        
        # Guardar en archivo JSON
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path = os.path.join(clasificaciones_dir, json_filename)
        
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
        
        logger.info(f"Clasificación guardada en archivo: {json_path}")
        logger.info(f"Datos guardados en JSON: {clasificacion_data}")
            
        # Guardar en la base de datos si está disponible
        try:
            from db_operations import store_clasificacion
            db_result = store_clasificacion({
                'codigo_guia': codigo_guia,
                'codigo_proveedor': clasificacion_data['codigo_proveedor'],
                'nombre_proveedor': clasificacion_data['nombre_proveedor'],
                'fecha_clasificacion': fecha_clasificacion,
                'hora_clasificacion': hora_clasificacion,
                'clasificacion_manual': json.dumps(clasificacion_manual),  # Guardar en campo correcto
                'clasificaciones': json.dumps(clasificacion_manual),  # Mantener para compatibilidad
                'observaciones': observaciones,
                'estado': 'activo'
            })
            
            if db_result:
                logger.info(f"Clasificación guardada en base de datos para código_guia: {codigo_guia}")
            else:
                logger.warning(f"No se pudo guardar la clasificación en base de datos para código_guia: {codigo_guia}")
        except Exception as db_error:
            logger.error(f"Error al guardar en base de datos: {str(db_error)}")
        
        # Actualizar el estado en la guía
        datos_guia.update({
            'clasificacion_completa': True,
            'fecha_clasificacion': fecha_clasificacion,
            'hora_clasificacion': hora_clasificacion,
            'tipo_clasificacion': 'manual',
            'clasificacion_manual': clasificacion_manual,
            'estado_actual': 'clasificacion_completada'
        })
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(current_app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Redirigir a la página de resultados
        flash("Clasificación guardada exitosamente", "success")
        logger.info(f"Redireccionando a: clasificacion.ver_resultados_clasificacion con url_guia={codigo_guia}")
        try:
            # En lugar de retornar un JSON, simplemente redirigir a la página de resultados
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))
        except Exception as redirect_error:
            logger.error(f"Error en redirección: {str(redirect_error)}")
            # Si hay error con url_for, intentar con URL directa
            return redirect(f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}")
        
    except Exception as e:
        logger.error(f"Error al procesar clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar la clasificación: {str(e)}", "danger")
        return redirect(url_for('clasificacion.clasificacion', codigo=codigo_guia))

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
            'estado': 'clasificacion_completada'
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
        datos_guia['fecha_clasificacion'] = datetime.now().strftime('%d/%m/%Y')
        datos_guia['hora_clasificacion'] = datetime.now().strftime('%H:%M:%S')
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

def process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Procesa imágenes con Roboflow para detectar racimos y clasificarlos.
    
    Args:
        codigo_guia: Código de la guía
        fotos_paths: Lista de rutas a las fotos a procesar
        guia_fotos_dir: Directorio donde se guardarán las fotos procesadas
        json_path: Ruta al archivo JSON donde se guardarán los resultados
    """
    try:
        # Definir valores por defecto para las constantes
        DEFAULT_API_KEY = ROBOFLOW_API_KEY  # Usar la constante global en lugar de hardcoded API key
        DEFAULT_WORKSPACE_NAME = WORKSPACE_NAME  # Usar la constante global  
        DEFAULT_WORKFLOW_ID = WORKFLOW_ID  # Usar la constante global
        
        # Definir valor por defecto para modelo_utilizado
        modelo_utilizado = "No especificado"
        
        logger.info(f"Iniciando procesamiento de imágenes para guía: {codigo_guia}")
        logger.info(f"Directorio de fotos: {guia_fotos_dir}")
        logger.info(f"Archivo JSON para resultados: {json_path}")
        
        # Verificar que el directorio existe
        if not os.path.exists(guia_fotos_dir):
            logger.info(f"Creando directorio para fotos: {guia_fotos_dir}")
            os.makedirs(guia_fotos_dir, exist_ok=True)
        
        # Verificar que el directorio de clasificaciones existe
        clasificaciones_dir = os.path.dirname(json_path)
        if not os.path.exists(clasificaciones_dir):
            logger.info(f"Creando directorio para clasificaciones: {clasificaciones_dir}")
            os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # MODIFICACIÓN: En lugar de eliminar el archivo JSON existente, cargar los datos manuales si existen
        existing_manual_classification = {}
        if os.path.exists(json_path):
            try:
                logger.info(f"Archivo JSON existente encontrado: {json_path}")
                # Leer el archivo JSON para extraer la clasificación manual
                with open(json_path, 'r') as f:
                    existing_data = json.load(f)
                    if 'clasificacion_manual' in existing_data and existing_data['clasificacion_manual']:
                        existing_manual_classification = existing_data['clasificacion_manual']
                        logger.info(f"Preservando clasificación manual existente: {existing_manual_classification}")
                    else:
                        logger.info("No se encontró clasificación manual en el archivo JSON existente")
                
                # Crear un respaldo del archivo existente
                backup_path = f"{json_path}.bak.{int(time.time())}"
                shutil.copy2(json_path, backup_path)
                logger.info(f"Archivo JSON respaldado como: {backup_path}")
                
                # Ahora sí podemos eliminar/sobreescribir el archivo original
                os.remove(json_path)
                logger.info("Archivo JSON eliminado correctamente para crear uno nuevo con datos actualizados.")
            except Exception as e:
                logger.error(f"Error al procesar archivo JSON existente: {str(e)}")
                logger.error(traceback.format_exc())
                # Si hay error, asegurarse de que existing_manual_classification esté inicializado
                existing_manual_classification = {}
        
        # Inicializar clasificación con estructura nueva y limpia, pero preservando clasificación manual
        clasificacion_data = {
            'id': f"Clasificacion_{codigo_guia}",
            'fecha_registro': datetime.now().strftime('%d/%m/%Y'),
            'hora_registro': datetime.now().strftime('%H:%M:%S'),
            'fotos': fotos_paths,
            'estado': 'en_proceso',
            'clasificacion_manual': existing_manual_classification,  # Usar los datos existentes
            'clasificacion_automatica': {
                'verdes': {'cantidad': 0, 'porcentaje': 0},
                'maduros': {'cantidad': 0, 'porcentaje': 0},
                'sobremaduros': {'cantidad': 0, 'porcentaje': 0},
                'podridos': {'cantidad': 0, 'porcentaje': 0},
                'danio_corona': {'cantidad': 0, 'porcentaje': 0},
                'pendunculo_largo': {'cantidad': 0, 'porcentaje': 0}
            },
            'resultados_por_foto': {}
        }
        
        # Utilizar la estructura de clasificación automática directamente
        clasificacion_automatica = clasificacion_data['clasificacion_automatica']
        resultados_por_foto = clasificacion_data['resultados_por_foto']
        
        
        # Registrar tiempo de inicio
        tiempo_inicio = time.time()
        
        # Obtener configuración de Roboflow
        roboflow_api_key = current_app.config.get('ROBOFLOW_API_KEY', DEFAULT_API_KEY)
        workspace_name = current_app.config.get('ROBOFLOW_WORKSPACE', DEFAULT_WORKSPACE_NAME)
        workflow_id = current_app.config.get('ROBOFLOW_WORKFLOW_ID', DEFAULT_WORKFLOW_ID)
        
        # Verificar que tenemos la configuración necesaria
        if not all([roboflow_api_key, workspace_name, workflow_id]):
            logger.error("Falta configuración de Roboflow.")
            logger.error(f"API Key configurada: {'Sí' if roboflow_api_key else 'No'}")
            logger.error(f"Workspace configurado: {'Sí' if workspace_name else 'No'}")
            logger.error(f"Workflow ID configurado: {'Sí' if workflow_id else 'No'}")
            logger.error("Usando simulación como alternativa.")
            # MODIFICACIÓN: Forzar el uso de API real en vez de simulación
            use_simulation = False  # Antes: use_simulation = True
        else:
            # FORZAR USO DE LLAMADAS REALES
            use_simulation = False
            # Inicializar el cliente de Roboflow
            try:
                if InferenceHTTPClient:
                    # Usar el SDK oficial si está disponible
                    client = InferenceHTTPClient(
                        api_url="https://detect.roboflow.com",
                        api_key=roboflow_api_key
                    )
                    logger.info("Cliente SDK de Roboflow inicializado correctamente.")
                else:
                    # Usar nuestro cliente directo si el SDK no está disponible
                    client = DirectRoboflowClient(
                        api_url="https://detect.roboflow.com",
                        api_key=roboflow_api_key
                    )
                    logger.info("Cliente directo HTTP de Roboflow inicializado correctamente.")
                
                logger.info(f"Workspace: {workspace_name}, Workflow ID: {workflow_id}")
            except Exception as e:
                logger.error(f"Error al inicializar el cliente de Roboflow: {str(e)}")
                # MODIFICACIÓN: No revertir a simulación en caso de error, intentar usar el cliente directo
                logger.info("Intentando usar el cliente directo como alternativa...")
                try:
                    client = DirectRoboflowClient(
                        api_url="https://detect.roboflow.com",
                        api_key=roboflow_api_key
                    )
                    logger.info("Cliente directo HTTP de Roboflow inicializado como fallback.")
                except Exception as e2:
                    logger.error(f"Error al inicializar cliente directo: {str(e2)}")
                    # Mantenemos use_simulation=False pero registramos el error
                    logger.error("Se intentará procesar con la API pero puede fallar.")
        
        # Limitar a 3 fotos en producción como indicado
        if not use_simulation and len(fotos_paths) > 3:
            logger.info(f"Limitando a 3 fotos para procesamiento con Roboflow (originalmente {len(fotos_paths)})")
            fotos_paths = fotos_paths[:3]
        
        # Procesar cada imagen
        for idx, foto_path in enumerate(fotos_paths, 1):
            logger.info(f"Procesando imagen {idx}/{len(fotos_paths)}: {foto_path}")
            
            # Actualizar estado de procesamiento
            global processing_status
            if codigo_guia in processing_status:
                processing_status[codigo_guia] = {
                    'status': 'processing',
                    'progress': int(5 + (idx-1) * 90 / len(fotos_paths)),  # Dejar espacio para el paso final
                    'step': 2,  # Paso 2: Procesando con modelo
                    'message': f'Procesando imagen {idx}/{len(fotos_paths)}...',
                    'processed_images': idx - 1,
                    'total_images': len(fotos_paths)
                }
            
            # Verificar que la imagen existe
            if not os.path.exists(foto_path):
                logger.error(f"La imagen no existe: {foto_path}")
                if codigo_guia in processing_status:
                    processing_status[codigo_guia]['message'] = f'Error: La imagen {idx} no existe'
                    processing_status[codigo_guia]['status'] = 'error'
                continue
            
            # Enviar la imagen a Roboflow para procesamiento
            try:
                if use_simulation:
                    # SIMULACIÓN: Generar datos de prueba aleatorios para imitar respuesta de Roboflow
                    logger.info(f"Simulando procesamiento para imagen {idx}: {foto_path}")
                    
                    # Simular un tiempo de procesamiento
                    time.sleep(1)
                    
                    # Generar detecciones aleatorias
                    import random
                    num_detecciones = random.randint(5, 15)
                    detecciones = []
                    
                    for _ in range(num_detecciones):
                        clase = random.choice(['verde', 'maduro', 'sobremaduro', 'podrido', 'danio_corona', 'pendunculo_largo'])
                        detecciones.append({
                            'class': clase,
                            'confidence': random.uniform(0.6, 0.95),
                            'x': random.randint(100, 500),
                            'y': random.randint(100, 500),
                            'width': random.randint(50, 150),
                            'height': random.randint(50, 150)
                        })
                    
                    # Crear un resultado simulado
                    result = {
                        'predictions': detecciones,
                        'time': random.uniform(0.5, 2.0),
                        'image': {
                            'width': 800,
                            'height': 600
                        }
                    }
                    
                    # Copiar la imagen original como "procesada" para simulación
                    processed_img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                    shutil.copy(foto_path, processed_img_path)
                    
                    logger.info(f"Simulación completa para imagen {idx}. Generadas {len(detecciones)} detecciones.")
                    modelo_utilizado = "SIMULACIÓN (versión mejorada)"
                else:
                    # CÓDIGO REAL: Enviar la imagen a Roboflow usando el SDK
                    logger.info(f"Enviando imagen {idx} a Roboflow API: {foto_path}")
                    
                    # Ejecutar el workflow con la imagen
                    result = client.run_workflow(
                        workspace_name=workspace_name,
                        workflow_id=workflow_id,
                        images={"image": foto_path},
                        use_cache=True  # cache workflow definition for 15 minutes
                    )
                    
                    logger.info(f"Respuesta de Roboflow recibida: {result}")
                    
                    # --- DEBUG --- Log the raw Roboflow result structure
                    logger.info(f"DEBUG Foto {idx}: Raw Roboflow result type: {type(result)}")
                    if isinstance(result, list):
                        logger.info(f"DEBUG Foto {idx}: Raw Roboflow result is a list with {len(result)} items.")
                        if len(result) > 0:
                            logger.info(f"DEBUG Foto {idx}: First item type: {type(result[0])}")
                            if isinstance(result[0], dict):
                                logger.info(f"DEBUG Foto {idx}: First item keys: {list(result[0].keys())}")
                    elif isinstance(result, dict):
                        logger.info(f"DEBUG Foto {idx}: Raw Roboflow result is a dict with keys: {list(result.keys())}")
                    # --- END DEBUG ---
                    
                    # Verificar si hay errores en la respuesta
                    if "error" in result:
                        error_msg = result.get("error", "Error desconocido")
                        logger.error(f"Error en la respuesta de Roboflow: {error_msg}")
                        
                        # Actualizar estado de procesamiento para mostrar el error
                        if codigo_guia in processing_status:
                            processing_status[codigo_guia]['message'] = f'Error: {error_msg}'
                            if result.get('auth_error'):
                                processing_status[codigo_guia]['message'] = 'Error de autenticación con Roboflow. Verifique su API key.'
                            elif result.get('not_found'):
                                processing_status[codigo_guia]['message'] = 'Workflow o workspace no encontrado. Verifique configuración.'
                            elif result.get('server_error'):
                                processing_status[codigo_guia]['message'] = 'Error del servidor de Roboflow. Intente nuevamente más tarde.'
                            processing_status[codigo_guia]['status'] = 'error'
                        
                        # Almacenar resultado vacío pero con error
                        detecciones = []
                        modelo_utilizado = f"Error en Roboflow: {error_msg}"
                        raw_result_to_save = result # Save the error response
                    else:
                        # Assign the full result to be saved by default
                        raw_result_to_save = result 
                        logger.info(f"DEBUG Foto {idx}: Assigning full Roboflow result to raw_result_to_save")
                        
                        # NORMALIZE THE RESPONSE for consistent processing:
                        # This ensures that label_visualization_1 is accessible in the same way
                        # regardless of whether the result is a list or dictionary
                        if isinstance(result, list) and len(result) > 0:
                            # Case 1: Response is a list (typical for photos 1 & 2)
                            logger.info(f"DEBUG Foto {idx}: Normalizing LIST result")
                            # Get the first item from the list
                            main_result = result[0] if isinstance(result[0], dict) else {}
                            # Check if this item has the expected keys
                            if 'label_visualization_1' in main_result or 'annotated_image' in main_result:
                                # If it has necessary keys, use just this dictionary
                                raw_result_to_save = main_result
                                logger.info(f"DEBUG Foto {idx}: Using first list item as raw_result (has required keys)")
                            else:
                                # If not, search all items for one with the necessary keys
                                logger.info(f"DEBUG Foto {idx}: First item lacks required keys, searching all items")
                                for item in result:
                                    if isinstance(item, dict):
                                        if 'label_visualization_1' in item or 'annotated_image' in item:
                                            raw_result_to_save = item
                                            logger.info(f"DEBUG Foto {idx}: Found list item with required keys")
                                            break
                        elif isinstance(result, dict):
                            # Case 2: Response is already a dictionary (possible for photo 3)
                            logger.info(f"DEBUG Foto {idx}: Result is already a dictionary")
                            # Keep it as is, but check if it doesn't have expected keys
                            if 'label_visualization_1' not in result and 'annotated_image' not in result:
                                logger.warning(f"DEBUG Foto {idx}: Dictionary result lacks both required keys")
                        
                        # As a final check, log what's being saved
                        if isinstance(raw_result_to_save, dict):
                            logger.info(f"DEBUG Foto {idx}: Final raw_result_to_save has keys: {list(raw_result_to_save.keys())}")
                            # Specifically check for the visualization keys
                            has_label = 'label_visualization_1' in raw_result_to_save
                            has_annotated = 'annotated_image' in raw_result_to_save
                            logger.info(f"DEBUG Foto {idx}: Has label_visualization_1: {has_label}, annotated_image: {has_annotated}")
                        elif isinstance(raw_result_to_save, list):
                            logger.info(f"DEBUG Foto {idx}: Final raw_result_to_save is still a list with {len(raw_result_to_save)} items")
                        
                        # Las detecciones podrían estar en diferentes formatos dependiendo del modelo
                        # Intentar extraer las predicciones si están disponibles
                        if isinstance(result, dict) and "predictions" in result:
                            detecciones = result["predictions"]
                            logger.info(f"Detecciones encontradas (predictions): {len(detecciones)}")
                        else:
                            # Si no hay predicciones explícitas, buscamos claves específicas como las del ejemplo
                            detecciones = []
                            
                            # Procesamiento para el formato específico de la respuesta actual
                            # Donde las categorías están en la raíz del objeto JSON
                            categorias_mapeo = {
                                "Racimos verdes": "verde",
                                "racimo verde": "verde",
                                "racimo maduro": "maduro", 
                                "racimo sobremaduro": "sobremaduro",
                                "racimo daño en corona": "danio_corona",
                                "racimo pedunculo largo": "pendunculo_largo",
                                "racimo podrido": "podrido"
                            }
                            
                            try:
                                logger.info(f"Analizando respuesta de Roboflow para buscar categorías específicas. Formato de respuesta: {type(result)}")
                                logger.info(f"Claves disponibles en la respuesta: {result.keys() if isinstance(result, dict) else 'No es un diccionario'}")
                                
                                # Log más detallado de la estructura JSON para debugging
                                if isinstance(result, dict):
                                    for key, value in result.items():
                                        logger.info(f"Key '{key}' has type {type(value)}")
                                        if key == 'outputs' and isinstance(value, list) and len(value) > 0:
                                            logger.info(f"First output has keys: {value[0].keys() if isinstance(value[0], dict) else 'Not a dict'}")
                                            
                                            # Extraer detecciones de la lista de outputs
                                            for output_idx, output in enumerate(value):
                                                if isinstance(output, dict):
                                                    logger.info(f"Procesando output[{output_idx}]")
                                                    
                                                    # Buscar categorías directamente en el output
                                                    for categoria_key, categoria_value in categorias_mapeo.items():
                                                        if categoria_key in output:
                                                            cantidad = output.get(categoria_key, 0)
                                                            logger.info(f"Encontrada categoría {categoria_key} en output[{output_idx}]: {cantidad}")
                                                            
                                                            if isinstance(cantidad, int) and cantidad > 0:
                                                                for i in range(cantidad):
                                                                    detecciones.append({
                                                                        'class': categoria_value,
                                                                        'confidence': 0.95,
                                                                        'x': 100 + (i * 10),
                                                                        'y': 100 + (i * 10),
                                                                        'width': 50,
                                                                        'height': 50
                                                                    })
                                                    
                                                    # Buscar 'Racimos verdes' específicamente
                                                    if 'Racimos verdes' in output:
                                                        cantidad = output.get('Racimos verdes', 0)
                                                        logger.info(f"Encontrada categoría 'Racimos verdes' en output[{output_idx}]: {cantidad}")
                                                        
                                                        if isinstance(cantidad, int) and cantidad > 0:
                                                            for i in range(cantidad):
                                                                detecciones.append({
                                                                    'class': 'verde',
                                                                    'confidence': 0.95,
                                                                    'x': 100 + (i * 10),
                                                                    'y': 100 + (i * 10),
                                                                    'width': 50,
                                                                    'height': 50
                                                                })
                                    
                                    # Recorrer las categorías que podemos obtener directamente de la respuesta
                                    for categoria_key, categoria_value in categorias_mapeo.items():
                                        try:
                                            if categoria_key in result:
                                                cantidad = result.get(categoria_key, 0)
                                                logger.info(f"Encontrada categoría {categoria_key}: {cantidad}")
                                                
                                                # Si es un entero, agregamos esa cantidad de detecciones
                                                if isinstance(cantidad, int) and cantidad > 0:
                                                    for i in range(cantidad):
                                                        detecciones.append({
                                                            'class': categoria_value,
                                                            'confidence': 0.95,  # Valor alto de confianza
                                                            'x': 100 + (i * 10),  # Valores placeholder variados
                                                            'y': 100 + (i * 10),
                                                            'width': 50,
                                                            'height': 50
                                                        })
                                        except Exception as e:
                                            logger.error(f"Error procesando categoría {categoria_key}: {str(e)}")
                                
                                # Buscar detecciones también en "data.raw_results" si existe
                                try:
                                    if "data" in result and isinstance(result["data"], dict) and "raw_results" in result["data"]:
                                        raw_results = result["data"]["raw_results"]
                                        logger.info(f"Encontrado campo data.raw_results: {type(raw_results)}")
                                        
                                        # Si es una lista, procesamos cada elemento
                                        if isinstance(raw_results, list):
                                            for idx, raw_result in enumerate(raw_results):
                                                # Comprobar las mismas categorías en cada resultado individual
                                                for categoria_key, categoria_value in categorias_mapeo.items():
                                                    if isinstance(raw_result, dict) and categoria_key in raw_result:
                                                        cantidad = raw_result.get(categoria_key, 0)
                                                        logger.info(f"Encontrada categoría {categoria_key} en raw_result[{idx}]: {cantidad}")
                                                        
                                                        if isinstance(cantidad, int) and cantidad > 0:
                                                            for i in range(cantidad):
                                                                detecciones.append({
                                                                    'class': categoria_value,
                                                                    'confidence': 0.95,
                                                                    'x': 100 + (i * 10),
                                                                    'y': 100 + (i * 10),
                                                                    'width': 50,
                                                                    'height': 50
                                                                })
                                except Exception as e:
                                    logger.error(f"Error procesando data.raw_results: {str(e)}")
                                
                                # Actualizamos el contador de detecciones derivadas
                                logger.info(f"Detecciones derivadas: {len(detecciones)}")
                                
                                # Si no hay detecciones, pero hay potholes_detected, creamos detecciones genéricas
                                if len(detecciones) == 0 and "potholes_detected" in result and isinstance(result["potholes_detected"], (int, float)) and result["potholes_detected"] > 0:
                                    total_potholes = result["potholes_detected"]
                                    logger.info(f"Usando potholes_detected para crear detecciones genéricas: {total_potholes}")
                                    
                                    # Crear detecciones genéricas verdes como fallback
                                    for i in range(int(total_potholes)):
                                        detecciones.append({
                                            'class': 'verde',  # Por defecto asumimos verdes
                                            'confidence': 0.90,
                                            'x': 100 + (i % 10) * 20,
                                            'y': 100 + (i // 10) * 20,
                                            'width': 50,
                                            'height': 50
                                        })
                                    
                                    logger.info(f"Creadas {len(detecciones)} detecciones genéricas")
                                    
                                # Actualizar clasificacion_automatica directamente con los datos del output
                                # Para trabajar alrededor del error NoneType
                                if len(detecciones) > 0:
                                    # Contar cuántos de cada categoría hay en las detecciones
                                    conteo_categorias = {
                                        'verdes': 0,
                                        'maduros': 0,
                                        'sobremaduros': 0,
                                        'podridos': 0,
                                        'danio_corona': 0,
                                        'pendunculo_largo': 0
                                    }
                                    
                                    for deteccion in detecciones:
                                        clase = deteccion.get('class', '').lower()
                                        if clase == 'verde':
                                            conteo_categorias['verdes'] += 1
                                        elif clase == 'maduro':
                                            conteo_categorias['maduros'] += 1
                                        elif clase == 'sobremaduro':
                                            conteo_categorias['sobremaduros'] += 1
                                        elif clase == 'podrido':
                                            conteo_categorias['podridos'] += 1
                                        elif clase == 'danio_corona':
                                            conteo_categorias['danio_corona'] += 1
                                        elif clase == 'pendunculo_largo':
                                            conteo_categorias['pendunculo_largo'] += 1
                                    
                                    # Actualizar los contadores en clasificacion_automatica
                                    for categoria, cantidad in conteo_categorias.items():
                                        if categoria in clasificacion_automatica:
                                            clasificacion_automatica[categoria]['cantidad'] = cantidad
                                    
                                    logger.info(f"Actualizado clasificacion_automatica directamente de detecciones: {conteo_categorias}")
                            except Exception as e:
                                logger.error(f"Error procesando respuesta de Roboflow: {str(e)}")
                                logger.error(traceback.format_exc())
                        
                        modelo_utilizado = f"Roboflow Workflow: {workflow_id}"
                        
                        # Intentar extraer y guardar la imagen procesada si existe
                        try:
                            # Buscar la imagen anotada si está disponible
                            annotated_image = None
                            # Comprobar varios campos donde podría estar la imagen anotada
                            for field_name in ['annotated_image', 'visualization', 'image_with_boxes', 'output_image']:
                                if field_name in result:
                                    logger.info(f"Encontrado campo {field_name} para imagen procesada")
                                    try:
                                        if isinstance(result[field_name], str):
                                            # Intentar decodificar como base64
                                            img_data = decode_image_data(result[field_name])
                                            if img_data:
                                                # Guardar la imagen procesada
                                                img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                                with open(img_path, 'wb') as f:
                                                    f.write(img_data)
                                                logger.info(f"Imagen procesada guardada desde campo '{field_name}'")
                                                break
                                    except Exception as e:
                                        logger.error(f"Error al guardar imagen procesada: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error general al procesar imagen: {str(e)}")
                        logger.error(traceback.format_exc())
                
                # Guardar resultado completo para esta foto
                str_idx = str(idx)
                resultados_por_foto[str_idx] = {
                    'detecciones': detecciones,
                    'total_detecciones': len(detecciones),
                    'raw_result': result  # Guardar el resultado completo
                }
                
                # Contar detecciones por categoría
                for deteccion in detecciones:
                    clase = deteccion.get('class', '').lower()
                    
                    # Mapear clases a categorías
                    if 'verde' in clase:
                        clasificacion_automatica['verdes']['cantidad'] += 1
                    elif 'maduro' in clase and 'sobre' not in clase:
                        clasificacion_automatica['maduros']['cantidad'] += 1
                    elif 'sobremaduro' in clase or 'sobre_maduro' in clase:
                        clasificacion_automatica['sobremaduros']['cantidad'] += 1
                    elif 'podrido' in clase:
                        clasificacion_automatica['podridos']['cantidad'] += 1
                    elif 'corona' in clase or 'danio_corona' in clase or 'daño_corona' in clase:
                        clasificacion_automatica['danio_corona']['cantidad'] += 1
                    elif 'pendunculo' in clase or 'pedunculo' in clase:
                        clasificacion_automatica['pendunculo_largo']['cantidad'] += 1
                
                # Guardar progreso parcial después de cada imagen
                clasificacion_data['clasificacion_automatica'] = clasificacion_automatica
                clasificacion_data['resultados_por_foto'] = resultados_por_foto
                clasificacion_data['estado'] = 'en_proceso'
                
                # Guardar archivo JSON con resultados parciales
                logger.info(f"Guardando resultados parciales en: {json_path}")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(clasificacion_data, f, indent=4, ensure_ascii=False)
                
            except Exception as e:
                logger.error(f"Error procesando imagen {idx}: {str(e)}")
                logger.error(traceback.format_exc())
                resultados_por_foto[str(idx)] = {'error': str(e)}
        
        # Procesar resultados finales
        logger.info("Procesamiento de imágenes completado. Preparando resultados finales.")
        
        # Calcular porcentajes
        try:
            # Filtrar solo las categorías que son diccionarios (no el total_racimos que añadimos después)
            categorias_validas = {k: v for k, v in clasificacion_automatica.items() if isinstance(v, dict) and 'cantidad' in v}
            total_racimos = sum(cat['cantidad'] for cat in categorias_validas.values())
            logger.info(f"Total de racimos detectados: {total_racimos}")
            
            if total_racimos > 0:
                for categoria, datos in clasificacion_automatica.items():
                    # Solo procesar categorías que son diccionarios con el campo cantidad
                    if isinstance(datos, dict) and 'cantidad' in datos:
                        try:
                            datos['porcentaje'] = round(
                                (datos['cantidad'] / total_racimos) * 100, 1
                            )
                        except Exception as e:
                            logger.error(f"Error calculando porcentaje para {categoria}: {str(e)}")
                            datos['porcentaje'] = 0
            
            # Guardar el total_racimos como un campo separado en los datos de clasificación
            clasificacion_data['total_racimos_detectados'] = total_racimos
            
            # También guardamos los datos procesados en clasificacion_data
            clasificacion_data['clasificacion_automatica'] = clasificacion_automatica
            clasificacion_data['resultados_por_foto'] = resultados_por_foto
            clasificacion_data['estado'] = 'completado' 
            clasificacion_data['tiempo_procesamiento'] = f"{round(time.time() - tiempo_inicio, 2)} segundos"
            clasificacion_data['modelo_utilizado'] = modelo_utilizado if 'modelo_utilizado' in locals() else "Modelo no especificado"
            
            # Guardar el JSON final
            logger.info(f"Guardando resultados finales en: {json_path}")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(clasificacion_data, f, indent=4, ensure_ascii=False)
            
            # Si hay procesamiento en curso para este código, actualizarlo
            if codigo_guia in processing_status:
                processing_status[codigo_guia]['status'] = 'completado'
                processing_status[codigo_guia]['progress'] = 100
                processing_status[codigo_guia]['message'] = f'Procesamiento completado. {total_racimos} racimos detectados.'
                
            # Log del resultado final
            logger.info(f"Procesamiento completado para guía {codigo_guia}. Tiempo: {round(time.time() - tiempo_inicio, 2)} segundos")
            
            # Si no se detectaron racimos, loguear advertencia
            if total_racimos == 0:
                logger.warning(f"Procesamiento completado pero sin detecciones para {codigo_guia}")
            
        except Exception as e:
            logger.error(f"Error calculando porcentajes: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Guardar el estado aunque haya error
            clasificacion_data['estado'] = 'error'
            clasificacion_data['error_message'] = str(e)
            
            # Guardar el JSON final aunque haya error
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(clasificacion_data, f, indent=4, ensure_ascii=False)
            
            # Actualizar estado de procesamiento
            if codigo_guia in processing_status:
                processing_status[codigo_guia]['status'] = 'error'
                processing_status[codigo_guia]['message'] = f'Error en procesamiento: {str(e)}'
        
        # Preparar datos de fotos procesadas para mostrar en la interfaz
        fotos_procesadas = []
        
        for idx, foto_path in enumerate(fotos_paths, 1):
            str_idx = str(idx)
            if str_idx in resultados_por_foto:
                resultado_foto = resultados_por_foto[str_idx]
                
                # Ruta relativa de la imagen original
                ruta_foto_original = None
                foto_original_path = os.path.join(guia_fotos_dir, f"foto_{idx}.jpg")
                if os.path.exists(foto_original_path):
                    path_parts = foto_original_path.split(os.sep)
                    try:
                        static_index = path_parts.index('static')
                        ruta_foto_original = os.sep.join(path_parts[static_index+1:])
                    except ValueError:
                        ruta_foto_original = foto_original_path
                
                # Ruta relativa de la imagen procesada
                ruta_foto_procesada = None
                foto_procesada_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                if os.path.exists(foto_procesada_path):
                    path_parts = foto_procesada_path.split(os.sep)
                    try:
                        static_index = path_parts.index('static')
                        ruta_foto_procesada = os.sep.join(path_parts[static_index+1:])
                    except ValueError:
                        ruta_foto_procesada = foto_procesada_path
                
                # Extraer imágenes anotadas de Roboflow (si existen)
                annotated_image = None
                label_visualization = None
                
                # Intentar acceder al resultado de esta foto específica
                result_for_foto = resultado_foto.get('raw_result', {})
                
                if not use_simulation and 'annotated_image' in result_for_foto:
                    try:
                        # Guardar imagen anotada
                        img_data = decode_image_data(result_for_foto.get('annotated_image'))
                        if img_data:
                            annotated_path = os.path.join(guia_fotos_dir, f"foto_{idx}_annotated.jpg")
                            with open(annotated_path, 'wb') as img_file:
                                img_file.write(img_data)
                            
                            # Determinar ruta relativa
                            path_parts = annotated_path.split(os.sep)
                            try:
                                static_index = path_parts.index('static')
                                annotated_image = os.sep.join(path_parts[static_index+1:])
                            except ValueError:
                                annotated_image = annotated_path
                    except Exception as e:
                        logger.error(f"Error guardando imagen anotada: {str(e)}")
                
                if not use_simulation and 'label_visualization_1' in result_for_foto:
                    try:
                        # Guardar visualización de etiquetas
                        img_data = decode_image_data(result_for_foto.get('label_visualization_1'))
                        if img_data:
                            label_path = os.path.join(guia_fotos_dir, f"foto_{idx}_labels.jpg")
                            with open(label_path, 'wb') as img_file:
                                img_file.write(img_data)
                            
                            # Determinar ruta relativa
                            path_parts = label_path.split(os.sep)
                            try:
                                static_index = path_parts.index('static')
                                label_visualization = os.sep.join(path_parts[static_index+1:])
                            except ValueError:
                                label_visualization = label_path
                    except Exception as e:
                        logger.error(f"Error guardando visualización de etiquetas: {str(e)}")
                
                # Obtener conteo de potholes (racimos) detectados
                total_racimos = result_for_foto.get('potholes_detected', 0)
                if not total_racimos and 'predictions' in result_for_foto:
                    total_racimos = len(result_for_foto['predictions'])
                
                # Si no hay total_racimos en el resultado específico, usar el total de categorías
                if not total_racimos:
                    total_racimos = resultado_foto.get('total_detecciones', 0)
                
                # Preparar resultados por categoría
                resultados_categorias = {}
                for deteccion in resultado_foto.get('detecciones', []):
                    clase = deteccion.get('class', '').lower()
                    if clase not in resultados_categorias:
                        resultados_categorias[clase] = 0
                    resultados_categorias[clase] += 1
                
                # Agregar a la lista de fotos procesadas
                fotos_procesadas.append({
                    'original': ruta_foto_original or foto_path,
                    'procesada': ruta_foto_procesada,
                    'annotated': annotated_image,
                    'labels': label_visualization,
                    'total_racimos': total_racimos,
                    'resultados': resultados_categorias
                })
        
        # Calcular tiempo total de procesamiento
        tiempo_fin = time.time()
        tiempo_procesamiento = round(tiempo_fin - tiempo_inicio, 2)
        
        # No duplicamos esta lógica ya que se hizo en el try/except anterior
        # Solo añadimos los datos de fotos procesadas que no se incluyeron antes
        clasificacion_data['fotos_procesadas'] = fotos_procesadas
        
        # Si no se llegó a calcular el tiempo_procesamiento en el try/except anterior
        if 'tiempo_procesamiento' not in clasificacion_data:
            clasificacion_data['tiempo_procesamiento'] = f"{tiempo_procesamiento} segundos"
        
        # Solo guardamos de nuevo si no se guardó en el try/except
        if clasificacion_data.get('estado') != 'completado' and clasificacion_data.get('estado') != 'error':
            # Guardar archivo JSON final
            logger.info(f"Guardando resultados finales (segunda fase) en: {json_path}")
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(clasificacion_data, f, indent=4, ensure_ascii=False)
        
        logger.info(f"Procesamiento completado para guía {codigo_guia}. Tiempo: {tiempo_procesamiento} segundos")
        return clasificacion_data
        
    except Exception as e:
        logger.error(f"Error en process_images_with_roboflow: {str(e)}")
        logger.error(traceback.format_exc())
        raise




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



@bp.route('/ver_resultados_clasificacion/<path:url_guia>')
def ver_resultados_clasificacion(url_guia):
    """
    Muestra los resultados de clasificación de una guía
    """
    logger.info(f"Iniciando ver_resultados_clasificacion para {url_guia}")
    inicio = time.time()
    mostrar_automatica = request.args.get('mostrar_automatica', False) == 'True'
    
    # Inicializar variables importantes
    template_data = {}
    clasificacion_automatica_consolidada = {}
    total_racimos_detectados = 0  # Inicializar aquí para que siempre exista
    
    try:
        # Decodificar la URL para obtener el código de guía
        codigo_guia_partes = unquote(url_guia)
        logger.info(f"Código de guía a buscar: {codigo_guia_partes}")
        
        # Verificar formato del código de guía
        if len(codigo_guia_partes.split('_')) < 3:
            logger.warning(f"Formato de código de guía incorrecto: {codigo_guia_partes}")
            flash("Formato de código de guía incorrecto. Debe tener el formato PROVEEDOR_FECHA_HORA.", "danger")
            return redirect(url_for('misc.index'))
        
        # Extraer el código de proveedor del código de guía
        codigo_proveedor = codigo_guia_partes.split('_')[0] if '_' in codigo_guia_partes else codigo_guia_partes
        # Asegurarse de que termina con 'A' correctamente
        if re.match(r'\d+[aA]?$', codigo_proveedor):
            if codigo_proveedor.endswith('a'):
                codigo_proveedor = codigo_proveedor[:-1] + 'A'
            elif not codigo_proveedor.endswith('A'):
                codigo_proveedor = codigo_proveedor + 'A'
        
        # Obtener datos de clasificación desde la base de datos
        from db_operations import get_clasificacion_by_codigo_guia
        
        clasificacion_data = get_clasificacion_by_codigo_guia(url_guia)
        if not clasificacion_data:
            logger.warning(f"No se encontraron datos de clasificación para {url_guia}")
            clasificacion_data = {}  # Inicializar diccionario vacío
            
            # Intentar obtener desde el utils_instance (ya que podría no estar en la BD aún)
            utils_instance = get_utils_instance()
            datos_guia = utils_instance.get_datos_guia(url_guia)
            if datos_guia and 'clasificacion_manual' in datos_guia:
                clasificacion_data['clasificacion_manual'] = datos_guia['clasificacion_manual']
                logger.info(f"Datos de clasificación manual encontrados en utils_instance: {clasificacion_data['clasificacion_manual']}")
        else:
            # Verificar clasificación manual en los datos de la base de datos
            if clasificacion_data.get('clasificacion_manual_json'):
                try:
                    manual_json = clasificacion_data.get('clasificacion_manual_json')
                    if manual_json and isinstance(manual_json, str):
                        clasificacion_data['clasificacion_manual'] = json.loads(manual_json)
                        logger.info(f"Clasificación manual extraída de clasificacion_manual_json: {clasificacion_data['clasificacion_manual']}")
                except Exception as json_error:
                    logger.error(f"Error decodificando clasificacion_manual_json: {str(json_error)}")
            
            # Si no tenemos clasificación manual en clasificacion_manual_json, revisar los valores individuales
            if not clasificacion_data.get('clasificacion_manual') and (
                clasificacion_data.get('verde_manual') is not None or 
                clasificacion_data.get('sobremaduro_manual') is not None or
                clasificacion_data.get('danio_corona_manual') is not None or
                clasificacion_data.get('pendunculo_largo_manual') is not None or
                clasificacion_data.get('podrido_manual') is not None):
                
                # Construir clasificación manual desde campos individuales
                clasificacion_data['clasificacion_manual'] = {
                    'verdes': clasificacion_data.get('verde_manual', 0),
                    'sobremaduros': clasificacion_data.get('sobremaduro_manual', 0),
                    'danio_corona': clasificacion_data.get('danio_corona_manual', 0),
                    'pendunculo_largo': clasificacion_data.get('pendunculo_largo_manual', 0),
                    'podridos': clasificacion_data.get('podrido_manual', 0)
                }
                logger.info(f"Clasificación manual construida desde campos individuales: {clasificacion_data['clasificacion_manual']}")
        
        # Verificar si hay datos de clasificación manual en datos_guia
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
        
        logger.info(f"Fotos procesadas: {fotos_procesadas}")
        
        # Determinar el tamaño de la muestra basado en la cantidad de racimos
        try:
            cantidad_racimos_int = int(cantidad_racimos_final) if cantidad_racimos_final and cantidad_racimos_final != 'N/A' else 0
            tamaño_muestra = 100 if cantidad_racimos_int > 1000 else 28
        except (ValueError, TypeError):
            tamaño_muestra = 28  # Valor por defecto si hay algún error
            
        # Calcular porcentajes para la clasificación manual
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        if not clasificacion_manual:
            # Si no hay datos, crear estructura vacía completa
            clasificacion_manual = {
                'verdes': 0,
                'maduros': 0,
                'sobremaduros': 0,
                'danio_corona': 0,
                'pendunculo_largo': 0,
                'podridos': 0
            }
            # Asignar de vuelta para asegurar que se use
            clasificacion_data['clasificacion_manual'] = clasificacion_manual
        
        logger.info(f"Clasificación manual final para porcentajes: {clasificacion_manual}")
        
        clasificacion_manual_con_porcentajes = {}
        
        for categoria, valor in clasificacion_manual.items():
            try:
                valor_num = float(valor) if valor is not None else 0
                porcentaje = (valor_num / tamaño_muestra) * 100 if tamaño_muestra > 0 else 0
                clasificacion_manual_con_porcentajes[categoria] = {
                    'cantidad': valor_num,
                    'porcentaje': porcentaje
                }
            except (ValueError, TypeError, ZeroDivisionError):
                clasificacion_manual_con_porcentajes[categoria] = {
                    'cantidad': valor if valor is not None else 0,
                    'porcentaje': 0
                }
                
        logger.info(f"Clasificación manual con porcentajes: {clasificacion_manual_con_porcentajes}")
            
        # Preparar datos para la plantilla de resultados
        template_data = {
            'codigo_guia': url_guia,
            'codigo_proveedor': codigo_proveedor,  # Agregar código de proveedor extraído
            'id': clasificacion_data.get('id', ''),  # Añadir el ID para las rutas de imágenes
            'fecha_registro': datos_guia.get('fecha_registro'),
            'hora_registro': datos_guia.get('hora_registro'),
            'fecha_clasificacion': clasificacion_data.get('fecha_clasificacion'),
            'hora_clasificacion': clasificacion_data.get('hora_clasificacion'),
            'nombre': nombre_proveedor_final,
            'nombre_proveedor': nombre_proveedor_final,
            'cantidad_racimos': cantidad_racimos_final,
            'tamaño_muestra': tamaño_muestra,  # Añadir el tamaño de la muestra
            'clasificacion_manual': clasificacion_manual,  # Mantener estructura original
            'clasificacion_manual_con_porcentajes': clasificacion_manual_con_porcentajes,  # Añadir estructura con porcentajes
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'total_racimos_detectados': clasificacion_data.get('total_racimos_detectados', 0),
            'resultados_por_foto': clasificacion_data.get('resultados_por_foto', {}),  # Añadir resultados por foto
            'clasificaciones': clasificaciones,
            'fotos': fotos_procesadas,
            'modelo_utilizado': clasificacion_data.get('modelo_utilizado', 'No especificado'),
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap') or clasificacion_data.get('codigo_guia_transporte_sap'),
            'peso_bruto': datos_guia.get('peso_bruto'),
            'observaciones': clasificacion_data.get('observaciones', ''),
            'automatica_completado': 'clasificacion_automatica' in clasificacion_data and any(
                (isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), dict) and 
                clasificacion_data['clasificacion_automatica'][categoria].get('cantidad', 0) > 0) or
                (isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), (int, float)) and 
                clasificacion_data['clasificacion_automatica'][categoria] > 0)
                for categoria in ['verdes', 'maduros', 'sobremaduros', 'podridos', 'danio_corona', 'pendunculo_largo']
            ),
            'tiene_pesaje_neto': False,  # Por defecto asumimos que no tiene pesaje neto
            'datos_guia': datos_guia  # Incluir datos_guia completo para la plantilla
        }
        
        # Registrar lo que estamos enviando a la plantilla
        logger.info(f"Enviando a template - código_proveedor: {template_data['codigo_proveedor']}")
        logger.info(f"Enviando a template - nombre_proveedor: {template_data['nombre_proveedor']}")
        logger.info(f"Enviando a template - cantidad_racimos: {template_data['cantidad_racimos']}")
        logger.info(f"Enviando a template - clasificacion_manual: {json.dumps(template_data.get('clasificacion_manual', {}))}")
        logger.info(f"Enviando a template - clasificacion_automatica: {json.dumps(template_data.get('clasificacion_automatica', {}))}")
        logger.info(f"Enviando a template - fotos: {len(template_data.get('fotos', []))}")
        logger.info(f"Enviando a template - total_racimos_detectados: {template_data.get('total_racimos_detectados', 0)}")
        logger.info(f"Enviando a template - codigo_guia_transporte_sap: {template_data.get('codigo_guia_transporte_sap')}")
        logger.info(f"Mostrando resultados de clasificación para: {url_guia}")
        
        # Intentar cargar la clasificación automática si existe
        json_folder = os.path.join(current_app.static_folder, 'clasificaciones')
        clasificacion_file = os.path.join(json_folder, f'clasificacion_{codigo_guia_partes}.json')
        
        if os.path.exists(clasificacion_file):
            logger.info(f"Cargando clasificación automática desde: {clasificacion_file}")
            try:
                with open(clasificacion_file, 'r') as f:
                    json_data = json.load(f)
                    
                # Extraer el total de racimos detectados
                total_racimos_detectados = json_data.get('total_racimos_detectados', 0)
                logger.info(f"Total de racimos detectados extraído del JSON: {total_racimos_detectados}")
                
                # IMPORTANTE: Actualizar clasificación manual si existe en el JSON
                if 'clasificacion_manual' in json_data and json_data['clasificacion_manual']:
                    logger.info(f"Actualizando clasificación manual desde JSON: {json_data['clasificacion_manual']}")
                    # Actualizar datos de template
                    clasificacion_manual = json_data['clasificacion_manual']
                    template_data['clasificacion_manual'] = clasificacion_manual
                    
                    # Recalcular porcentajes con los nuevos datos manuales
                    clasificacion_manual_con_porcentajes = {}
                    for categoria, valor in clasificacion_manual.items():
                        try:
                            valor_num = float(valor) if valor is not None else 0
                            porcentaje = (valor_num / tamaño_muestra) * 100 if tamaño_muestra > 0 else 0
                            clasificacion_manual_con_porcentajes[categoria] = {
                                'cantidad': valor_num,
                                'porcentaje': porcentaje
                            }
                        except (ValueError, TypeError, ZeroDivisionError):
                            clasificacion_manual_con_porcentajes[categoria] = {
                                'cantidad': valor if valor is not None else 0,
                                'porcentaje': 0
                            }
                    
                    template_data['clasificacion_manual_con_porcentajes'] = clasificacion_manual_con_porcentajes
                    logger.info(f"Clasificación manual actualizada con porcentajes: {clasificacion_manual_con_porcentajes}")
                    
                # Verificar si se ha realizado una clasificación automática
                if 'clasificacion_automatica' in json_data:
                    # Actualizar clasificación automática en template_data
                    template_data['clasificacion_automatica'] = json_data['clasificacion_automatica']
                    logger.info(f"Clasificación automática encontrada en el archivo JSON y actualizada en template_data")

                # Asegurarse de pasar total_racimos_detectados al template
                template_data['total_racimos_detectados'] = total_racimos_detectados
            except Exception as e:
                logger.error(f"Error al cargar el archivo de clasificación: {str(e)}")
                logger.error(traceback.format_exc())
                # Asegurar que total_racimos_detectados sigue existiendo aunque falle la carga
                total_racimos_detectados = template_data.get('total_racimos_detectados', 0)
        
        # ... existing code ...
        
        # Consolidar los resultados de la clasificación automática para mostrarlos en la sección de resumen
        clasificacion_automatica_consolidada = {}
        
        # Si tenemos clasificación automática, procesarla
        if clasificacion_data.get('clasificacion_automatica'):
            auto_data = clasificacion_data.get('clasificacion_automatica', {})
            
            # Verificar el formato de los datos de clasificación automática
            logger.info(f"Formato de clasificacion_automatica: {type(auto_data)}")
            logger.info(f"Contenido de clasificacion_automatica: {auto_data}")
            
            # Obtener las categorías y su mapeo singular/plural
            categorias = ['verdes', 'maduros', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']
            categorias_singular = ['verde', 'maduro', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido']
            mapeo_plural_singular = dict(zip(categorias, categorias_singular))
            mapeo_singular_plural = dict(zip(categorias_singular, categorias))
            total_racimos_auto = 0
            
            # Consolidar los resultados de todas las categorías
            for i, categoria in enumerate(categorias):
                categoria_singular = categorias_singular[i]
                
                # Intentar obtener datos tanto en formato plural como singular
                datos_categoria = auto_data.get(categoria, auto_data.get(categoria_singular, {}))
                
                logger.info(f"Procesando categoría '{categoria}' (singular: '{categoria_singular}'): {datos_categoria}")
                
                if isinstance(datos_categoria, dict) and 'cantidad' in datos_categoria:
                    cantidad = datos_categoria.get('cantidad', 0)
                    logger.info(f"Cantidad encontrada en diccionario: {cantidad}")
                else:
                    # Si es un valor directo en lugar de un diccionario
                    cantidad = datos_categoria if isinstance(datos_categoria, (int, float)) else 0
                    logger.info(f"Cantidad como valor directo: {cantidad}")
                
                # Siempre incrementamos el total, independientemente del formato
                total_racimos_auto += cantidad
                
                # Asegurarnos de guardar los datos en un formato consistente (diccionario)
                # Y guardar tanto en formato plural como singular para compatibilidad
                if not isinstance(datos_categoria, dict):
                    datos_formateados = {
                        'cantidad': cantidad,
                        'porcentaje': 0  # Lo calcularemos después
                    }
                else:
                    datos_formateados = {
                        'cantidad': cantidad,
                        'porcentaje': datos_categoria.get('porcentaje', 0)
                    }
                
                # Guardar en ambos formatos (singular y plural) para compatibilidad
                clasificacion_automatica_consolidada[categoria] = datos_formateados
                clasificacion_automatica_consolidada[categoria_singular] = datos_formateados
            
            # Calcular porcentajes
            if total_racimos_auto > 0:
                for categoria in clasificacion_automatica_consolidada:
                    cantidad = clasificacion_automatica_consolidada[categoria]['cantidad']
                    porcentaje = (cantidad / total_racimos_auto) * 100
                    clasificacion_automatica_consolidada[categoria]['porcentaje'] = porcentaje
                    logger.info(f"Categoría {categoria}: {cantidad} racimos, {porcentaje:.2f}%")
            
            logger.info(f"Clasificación automática consolidada: {clasificacion_automatica_consolidada}")
            
            # Asegurar que total_racimos_detectados esté definido
            if 'total_racimos_detectados' not in locals() or total_racimos_detectados is None:
                total_racimos_detectados = template_data.get('total_racimos_detectados', 0)
                logger.info(f"total_racimos_detectados no estaba definido, usando valor de template_data: {total_racimos_detectados}")
            
            # Añadir el total de racimos en la clasificación automática
            clasificacion_automatica_consolidada['total_racimos'] = total_racimos_auto if total_racimos_auto > 0 else total_racimos_detectados
            
            # Log del valor final de total_racimos
            logger.info(f"Valor final de clasificacion_automatica_consolidada['total_racimos']: {clasificacion_automatica_consolidada['total_racimos']}")
            
            # Si venimos desde la clasificación automática, mostrar un mensaje
            if mostrar_automatica:
                total_detectados = clasificacion_automatica_consolidada['total_racimos']
                if total_detectados > 0:
                    flash(f"Procesamiento de imágenes exitoso. Se detectaron {total_detectados} racimos en total.", "success")
                else:
                    flash("El procesamiento de imágenes finalizó pero no se detectaron racimos. Revise las imágenes.", "warning")
        
        # Actualizar template_data con la clasificación automática consolidada
        template_data['clasificacion_automatica_consolidada'] = clasificacion_automatica_consolidada
        template_data['mostrar_automatica'] = mostrar_automatica  # Indicar si se debe destacar la clasificación automática
        
        # Log detallado para debugging
        logger.info(f"DETALLE clasificacion_automatica_consolidada: {json.dumps(clasificacion_automatica_consolidada, default=str)}")
        logger.info(f"DETALLE clasificacion_automatica_consolidada.total_racimos: {clasificacion_automatica_consolidada.get('total_racimos', 0)}")
        logger.info(f"DETALLE template_data['total_racimos_detectados']: {template_data.get('total_racimos_detectados', 0)}")
        
        for categoria, datos in clasificacion_automatica_consolidada.items():
            if categoria != 'total_racimos':
                logger.info(f"DETALLE categoria {categoria}: {json.dumps(datos, default=str)}")
        
        # Verificación final de datos de clasificación manual
        logger.info("=== VERIFICACIÓN FINAL DE DATOS DE CLASIFICACIÓN MANUAL ===")
        logger.info(f"Clasificación manual en template_data: {json.dumps(template_data.get('clasificacion_manual', {}))}")
        logger.info(f"Clasificación manual con porcentajes: {json.dumps(template_data.get('clasificacion_manual_con_porcentajes', {}))}")
        
        # Validación adicional y corrección final de datos
        if not template_data.get('clasificacion_manual') or all(value == 0 for value in template_data.get('clasificacion_manual', {}).values()):
            logger.warning("Clasificación manual está vacía o todos los valores son cero. Intentando recuperar de datos_guia nuevamente.")
            
            # Verificar una última vez si hay datos en datos_guia
            if isinstance(datos_guia, dict) and 'clasificacion_manual' in datos_guia and datos_guia['clasificacion_manual']:
                logger.info(f"Recuperando clasificación manual de datos_guia: {datos_guia['clasificacion_manual']}")
                template_data['clasificacion_manual'] = datos_guia['clasificacion_manual']
                
                # Recalcular porcentajes con los datos recuperados
                clasificacion_manual_con_porcentajes = {}
                for categoria, valor in datos_guia['clasificacion_manual'].items():
                    try:
                        valor_num = float(valor) if valor is not None else 0
                        porcentaje = (valor_num / tamaño_muestra) * 100 if tamaño_muestra > 0 else 0
                        clasificacion_manual_con_porcentajes[categoria] = {
                            'cantidad': valor_num,
                            'porcentaje': porcentaje
                        }
                    except (ValueError, TypeError, ZeroDivisionError):
                        clasificacion_manual_con_porcentajes[categoria] = {
                            'cantidad': valor if valor is not None else 0,
                            'porcentaje': 0
                        }
                template_data['clasificacion_manual_con_porcentajes'] = clasificacion_manual_con_porcentajes
        
        logger.info("=== FIN DE VERIFICACIÓN ===")
        
        logger.info("Renderizando plantilla clasificacion_resultados.html")
        return render_template('clasificacion/clasificacion_resultados.html', **template_data)
    except Exception as e:
        logger.error(f"Error en ver_resultados_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error mostrando resultados de clasificación: {str(e)}")


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
    """Inicia el procesamiento de imágenes con IA para una guía específica."""
    logger.info(f"Iniciando procesamiento manual con Roboflow para guía: {url_guia}")
    
    try:
        # Cargar los datos de clasificación si existen
        clasificacion_data = {}
        clasificacion_file = os.path.join(current_app.static_folder, 'clasificaciones', f"clasificacion_{url_guia}.json")
        if os.path.exists(clasificacion_file):
            try:
                logger.info(f"Datos de clasificación cargados: {clasificacion_file}")
                with open(clasificacion_file, 'r', encoding='utf-8') as f:
                    clasificacion_data = json.load(f)
                    # Extraer información relevante si está disponible
                    fotos = clasificacion_data.get('fotos', [])
                    logger.info(f"Contenido relevante del archivo JSON: fotos={fotos}")
            except Exception as e:
                logger.error(f"Error al cargar el archivo de clasificación: {str(e)}")
                
        # Crear directorios si no existen
        guia_fotos_base_dir = os.path.join(current_app.static_folder, 'fotos_racimos_temp')
        os.makedirs(guia_fotos_base_dir, exist_ok=True)
        
        # Buscar las imágenes en diferentes ubicaciones
        guia_fotos_dir = os.path.join(guia_fotos_base_dir, url_guia)
        
        # Verificar si existe el directorio de fotos
        if not os.path.exists(guia_fotos_dir):
            logger.info(f"El directorio {guia_fotos_dir} no existe")
            
            # Intentar buscar en directorio alternativo
            guia_fotos_dir_alt = os.path.join(current_app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
            if os.path.exists(guia_fotos_dir_alt):
                guia_fotos_dir = guia_fotos_dir_alt
                logger.info(f"Usando directorio alternativo para fotos: {guia_fotos_dir}")
            else:
                logger.info(f"El directorio {guia_fotos_dir_alt} no existe")
        
        # Buscar en el directorio de clasificación temporal
        temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'temp_clasificacion')
        logger.info(f"Buscando fotos en directorio temp_clasificacion: {temp_dir}")
        
        # Listar todos los archivos en el directorio temporal
        if os.path.exists(temp_dir):
            all_temp_files = os.listdir(temp_dir)
            logger.info(f"Archivos encontrados en {temp_dir}: {all_temp_files}")
            
            # Filtrar para encontrar archivos relacionados con esta guía
            pattern = f"*{url_guia}*"
            matching_files = [f for f in all_temp_files if fnmatch.fnmatch(f, pattern)]
            
            if matching_files:
                logger.info(f"Fotos encontradas que coinciden con {url_guia}: {matching_files}")
                # Crear directorio para esta guía si no existe
                os.makedirs(guia_fotos_dir, exist_ok=True)
                
                # Mover las imágenes al directorio de la guía
                for file in matching_files:
                    src = os.path.join(temp_dir, file)
                    dst = os.path.join(guia_fotos_dir, file)
                    shutil.copy2(src, dst)
                    logger.info(f"Copiada imagen de {src} a {dst}")
            else:
                warning_msg = f"No se encontraron fotos que coincidan con el patrón {pattern} en {temp_dir}"
                logger.warning(warning_msg)
                flash(warning_msg, "warning")
        
        # Buscar fotos en el directorio de la guía
        fotos_paths = []
        if os.path.exists(guia_fotos_dir):
            for ext in ['*.jpg', '*.jpeg', '*.png']:
                fotos_paths.extend(glob.glob(os.path.join(guia_fotos_dir, ext)))
        
        if not fotos_paths:
            error_msg = f"No se encontraron imágenes para procesar en {url_guia}"
            logger.error(error_msg)
            flash(error_msg, "error")
            flash("Para usar la clasificación automática, primero debe subir imágenes utilizando el botón 'Clasificar' y cargar fotos de racimos.", "warning")
            return jsonify({
                'success': False,
                'message': error_msg,
                'error_code': 'NO_IMAGES_FOUND'
            }), 404
        
        # Preparar ruta para guardar resultados
        json_path = os.path.join(current_app.static_folder, 'clasificaciones', f"clasificacion_{url_guia}.json")
        
        # Iniciar procesamiento en segundo plano
        thread = threading.Thread(
            target=process_thread,
            args=(current_app._get_current_object(), url_guia, fotos_paths, guia_fotos_dir, json_path)
        )
        thread.daemon = True
        thread.start()
        
        logger.info(f"Procesamiento iniciado para {url_guia} con {len(fotos_paths)} imágenes en segundo plano")
        
        return jsonify({
            'success': True,
            'status': 'started',
            'message': f'Procesamiento iniciado con {len(fotos_paths)} imágenes',
            'num_images': len(fotos_paths),
            'check_status_url': url_for('clasificacion.check_procesamiento_status', url_guia=url_guia),
            'results_url': url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia)
        })
        
    except Exception as e:
        error_msg = f"Error al iniciar procesamiento: {str(e)}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        flash(error_msg, "error")
        return jsonify({
            'success': False,
            'message': error_msg,
            'error_code': 'PROCESSING_ERROR'
        }), 500



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
        
        logger.info(f"Fotos procesadas: {fotos_procesadas}")
        
        # Determinar el tamaño de la muestra basado en la cantidad de racimos
        try:
            cantidad_racimos_int = int(cantidad_racimos_final) if cantidad_racimos_final and cantidad_racimos_final != 'N/A' else 0
            tamaño_muestra = 100 if cantidad_racimos_int > 1000 else 28
        except (ValueError, TypeError):
            tamaño_muestra = 28  # Valor por defecto si hay algún error
            
        # Calcular porcentajes para la clasificación manual
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        if not clasificacion_manual:
            # Si no hay datos, crear estructura vacía completa
            clasificacion_manual = {
                'verdes': 0,
                'maduros': 0,
                'sobremaduros': 0,
                'danio_corona': 0,
                'pendunculo_largo': 0,
                'podridos': 0
            }
            # Asignar de vuelta para asegurar que se use
            clasificacion_data['clasificacion_manual'] = clasificacion_manual
        
        logger.info(f"Clasificación manual final para porcentajes: {clasificacion_manual}")
        
        clasificacion_manual_con_porcentajes = {}
        
        for categoria, valor in clasificacion_manual.items():
            try:
                valor_num = float(valor) if valor is not None else 0
                porcentaje = (valor_num / tamaño_muestra) * 100 if tamaño_muestra > 0 else 0
                clasificacion_manual_con_porcentajes[categoria] = {
                    'cantidad': valor_num,
                    'porcentaje': porcentaje
                }
            except (ValueError, TypeError, ZeroDivisionError):
                clasificacion_manual_con_porcentajes[categoria] = {
                    'cantidad': valor if valor is not None else 0,
                    'porcentaje': 0
                }
                
        logger.info(f"Clasificación manual con porcentajes: {clasificacion_manual_con_porcentajes}")
            
        # Preparar datos para la plantilla de resultados
        template_data = {
            'codigo_guia': url_guia,
            'codigo_proveedor': codigo_proveedor,  # Agregar código de proveedor extraído
            'id': clasificacion_data.get('id', ''),  # Añadir el ID para las rutas de imágenes
            'fecha_registro': datos_guia.get('fecha_registro'),
            'hora_registro': datos_guia.get('hora_registro'),
            'fecha_clasificacion': clasificacion_data.get('fecha_clasificacion'),
            'hora_clasificacion': clasificacion_data.get('hora_clasificacion'),
            'nombre': nombre_proveedor_final,
            'nombre_proveedor': nombre_proveedor_final,
            'cantidad_racimos': cantidad_racimos_final,
            'tamaño_muestra': tamaño_muestra,  # Añadir el tamaño de la muestra
            'clasificacion_manual': clasificacion_manual,  # Mantener estructura original
            'clasificacion_manual_con_porcentajes': clasificacion_manual_con_porcentajes,  # Añadir estructura con porcentajes
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'total_racimos_detectados': clasificacion_data.get('total_racimos_detectados', 0),
            'resultados_por_foto': clasificacion_data.get('resultados_por_foto', {}),  # Añadir resultados por foto
            'clasificaciones': clasificaciones,
            'fotos': fotos_procesadas,
            'modelo_utilizado': clasificacion_data.get('modelo_utilizado', 'No especificado'),
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap') or clasificacion_data.get('codigo_guia_transporte_sap'),
            'peso_bruto': datos_guia.get('peso_bruto'),
            'observaciones': clasificacion_data.get('observaciones', ''),
            'automatica_completado': 'clasificacion_automatica' in clasificacion_data and any(
                (isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), dict) and 
                clasificacion_data['clasificacion_automatica'][categoria].get('cantidad', 0) > 0) or
                (isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), (int, float)) and 
                clasificacion_data['clasificacion_automatica'][categoria] > 0)
                for categoria in ['verdes', 'maduros', 'sobremaduros', 'podridos', 'danio_corona', 'pendunculo_largo']
            ),
            'tiene_pesaje_neto': False,  # Por defecto asumimos que no tiene pesaje neto
            'datos_guia': datos_guia  # Incluir datos_guia completo para la plantilla
        }
        
        # Registrar lo que estamos enviando a la plantilla
        logger.info(f"Enviando a template - código_proveedor: {template_data['codigo_proveedor']}")
        logger.info(f"Enviando a template - nombre_proveedor: {template_data['nombre_proveedor']}")
        logger.info(f"Enviando a template - cantidad_racimos: {template_data['cantidad_racimos']}")
        logger.info(f"Enviando a template - clasificacion_manual: {json.dumps(template_data.get('clasificacion_manual', {}))}")
        logger.info(f"Enviando a template - clasificacion_automatica: {json.dumps(template_data.get('clasificacion_automatica', {}))}")
        logger.info(f"Enviando a template - fotos: {len(template_data.get('fotos', []))}")
        logger.info(f"Enviando a template - total_racimos_detectados: {template_data.get('total_racimos_detectados', 0)}")
        logger.info(f"Enviando a template - codigo_guia_transporte_sap: {template_data.get('codigo_guia_transporte_sap')}")
        logger.info(f"Mostrando resultados de clasificación para: {url_guia}")
        
        # Consolidar los resultados de la clasificación automática para mostrarlos en la sección de resumen
        clasificacion_automatica_consolidada = {}
        
        # Si tenemos clasificación automática, procesarla
        if clasificacion_data.get('clasificacion_automatica'):
            auto_data = clasificacion_data.get('clasificacion_automatica', {})
            
            # Verificar el formato de los datos de clasificación automática
            logger.info(f"Formato de clasificacion_automatica: {type(auto_data)}")
            logger.info(f"Contenido de clasificacion_automatica: {auto_data}")
            
            # Obtener las categorías y su mapeo singular/plural
            categorias = ['verdes', 'maduros', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']
            categorias_singular = ['verde', 'maduro', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido']
            mapeo_plural_singular = dict(zip(categorias, categorias_singular))
            mapeo_singular_plural = dict(zip(categorias_singular, categorias))
            total_racimos_auto = 0
            
            # Consolidar los resultados de todas las categorías
            for i, categoria in enumerate(categorias):
                categoria_singular = categorias_singular[i]
                
                # Intentar obtener datos tanto en formato plural como singular
                datos_categoria = auto_data.get(categoria, auto_data.get(categoria_singular, {}))
                
                logger.info(f"Procesando categoría '{categoria}' (singular: '{categoria_singular}'): {datos_categoria}")
                
                if isinstance(datos_categoria, dict) and 'cantidad' in datos_categoria:
                    cantidad = datos_categoria.get('cantidad', 0)
                    logger.info(f"Cantidad encontrada en diccionario: {cantidad}")
                else:
                    # Si es un valor directo en lugar de un diccionario
                    cantidad = datos_categoria if isinstance(datos_categoria, (int, float)) else 0
                    logger.info(f"Cantidad como valor directo: {cantidad}")
                
                # Siempre incrementamos el total, independientemente del formato
                total_racimos_auto += cantidad
                
                # Asegurarnos de guardar los datos en un formato consistente (diccionario)
                if not isinstance(datos_categoria, dict):
                    datos_formateados = {
                        'cantidad': cantidad,
                        'porcentaje': 0  # Lo calcularemos después
                    }
                else:
                    datos_formateados = {
                        'cantidad': cantidad,
                        'porcentaje': datos_categoria.get('porcentaje', 0)
                    }
                
                # Guardar en ambos formatos (singular y plural) para compatibilidad
                clasificacion_automatica_consolidada[categoria] = datos_formateados
                clasificacion_automatica_consolidada[categoria_singular] = datos_formateados
            
            # Calcular porcentajes
            if total_racimos_auto > 0:
                for categoria in clasificacion_automatica_consolidada:
                    cantidad = clasificacion_automatica_consolidada[categoria]['cantidad']
                    porcentaje = (cantidad / total_racimos_auto) * 100
                    clasificacion_automatica_consolidada[categoria]['porcentaje'] = porcentaje
                    logger.info(f"Categoría {categoria}: {cantidad} racimos, {porcentaje:.2f}%")
            
            logger.info(f"Clasificación automática consolidada: {clasificacion_automatica_consolidada}")
            
            # Asegurar que total_racimos_detectados esté definido
            if 'total_racimos_detectados' not in locals() or total_racimos_detectados is None:
                total_racimos_detectados = template_data.get('total_racimos_detectados', 0)
                logger.info(f"total_racimos_detectados no estaba definido, usando valor de template_data: {total_racimos_detectados}")
            
            # Añadir el total de racimos en la clasificación automática
            clasificacion_automatica_consolidada['total_racimos'] = total_racimos_auto if total_racimos_auto > 0 else total_racimos_detectados
            
            # Log del valor final de total_racimos
            logger.info(f"Valor final de clasificacion_automatica_consolidada['total_racimos']: {clasificacion_automatica_consolidada['total_racimos']}")
            
            # Si venimos desde la clasificación automática, mostrar un mensaje
            if mostrar_automatica:
                total_detectados = clasificacion_automatica_consolidada['total_racimos']
                if total_detectados > 0:
                    flash(f"Procesamiento de imágenes exitoso. Se detectaron {total_detectados} racimos en total.", "success")
                else:
                    flash("El procesamiento de imágenes finalizó pero no se detectaron racimos. Revise las imágenes.", "warning")
        
        # Actualizar template_data con la clasificación automática consolidada
        template_data['clasificacion_automatica_consolidada'] = clasificacion_automatica_consolidada
        template_data['mostrar_automatica'] = mostrar_automatica  # Indicar si se debe destacar la clasificación automática
        
        # Log detallado para debugging
        logger.info(f"DETALLE clasificacion_automatica_consolidada: {json.dumps(clasificacion_automatica_consolidada, default=str)}")
        logger.info(f"DETALLE clasificacion_automatica_consolidada.total_racimos: {clasificacion_automatica_consolidada.get('total_racimos', 0)}")
        logger.info(f"DETALLE template_data['total_racimos_detectados']: {template_data.get('total_racimos_detectados', 0)}")
        
        for categoria, datos in clasificacion_automatica_consolidada.items():
            if categoria != 'total_racimos':
                logger.info(f"DETALLE categoria {categoria}: {json.dumps(datos, default=str)}")
        
        logger.info("Renderizando plantilla clasificacion_resultados.html")
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

def process_thread(app, url_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Función para procesar imágenes en un hilo separado
    """
    # Inicializar mostrar_automatica para evitar errores
    mostrar_automatica = True
    
    with app.app_context():
        logger.info(f"Iniciando procesamiento en hilo para guía: {url_guia}")
        
        # Inicializar variables de resultado
        result = None
        error_occurred = False
        error_message = ""
        
        try:
            # Decodificar la URL para obtener el código de guía
            codigo_guia = url_guia.replace('_', '/')
            
            # Actualizar estado de procesamiento
            if url_guia in processing_status:
                processing_status[url_guia]['message'] = 'Iniciando procesamiento de imágenes.'
                processing_status[url_guia]['status'] = 'processing'
                processing_status[url_guia]['progress'] = 0
                processing_status[url_guia]['step'] = 1
            
            # Procesar las imágenes con Roboflow
            result = process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path)
            
            logger.info(f"Procesamiento completado para guía {url_guia}. Tiempo: {result.get('tiempo', '?')} segundos")
            
            # Actualizar estado de procesamiento al completar
            if url_guia in processing_status:
                processing_status[url_guia]['message'] = 'Procesamiento completado.'
                processing_status[url_guia]['status'] = 'completed'
                processing_status[url_guia]['progress'] = 100
                processing_status[url_guia]['step'] = 5
                processing_status[url_guia]['redirect_url'] = f'/mostrar_resultados_automaticos/{url_guia}'
                processing_status[url_guia]['total_detecciones'] = result.get('total_detecciones', 0)
                processing_status[url_guia]['tiempo'] = result.get('tiempo', '?')
            
        except Exception as e:
            error_occurred = True
            error_message = str(e)
            logger.error(f"Excepción durante el procesamiento: {error_message}")
            logger.error(traceback.format_exc())
            
            # Actualizar estado de procesamiento con el error
            if url_guia in processing_status:
                processing_status[url_guia]['message'] = f'Error en procesamiento: {error_message}'
                processing_status[url_guia]['status'] = 'error'
                processing_status[url_guia]['progress'] = 100
                processing_status[url_guia]['step'] = 5
                processing_status[url_guia]['total_detecciones'] = 0
                processing_status[url_guia]['tiempo'] = '?'
        
        # Siempre actualizar el timestamp
        if url_guia in processing_status:
            processing_status[url_guia]['timestamp'] = datetime.now().isoformat()
        
        # Guardar un mensaje flash en la sesión para mostrarlo después de la redirección
        with app.test_request_context():
            if error_occurred:
                flash(f"Error en el procesamiento: {error_message}", "danger")
            elif result and url_guia in processing_status:
                total_detecciones = processing_status[url_guia].get('total_detecciones', 0)
                mensaje = f"Procesamiento completado con éxito. Se detectaron {total_detecciones} racimos."
                if total_detecciones > 0:
                    flash(mensaje, "success")
                else:
                    flash("Procesamiento completado pero no se detectaron racimos. Revise las imágenes.", "warning")

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
                datos_clasificacion = {
                    'codigo_guia': codigo_guia,
                    'codigo_proveedor': datos_guia.get('codigo_proveedor'),
                    'nombre_proveedor': datos_guia.get('nombre_proveedor'),
                    'fecha_clasificacion': datetime.utcnow().strftime('%d/%m/%Y'), # Use UTC now
                    'hora_clasificacion': datetime.utcnow().strftime('%H:%M:%S'), # Use UTC now
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
                    
                    # También crear un diccionario para actualizar datos_guia
                    clasificacion_manual_dict = {
                        'verdes': valores_manual.get('verde_manual', 0),
                        'sobremaduros': valores_manual.get('sobremaduro_manual', 0),
                        'danio_corona': valores_manual.get('danio_corona_manual', 0),
                        'pendunculo_largo': valores_manual.get('pendunculo_largo_manual', 0),
                        'podridos': valores_manual.get('podrido_manual', 0)
                    }
                    
                    # Actualizar los datos de la guía
                    datos_guia['clasificacion_manual'] = clasificacion_manual_dict
                    utils_instance.update_datos_guia(codigo_guia, datos_guia)
                    logger.info(f"Actualizada clasificación manual en datos_guia: {clasificacion_manual_dict}")
                    
                    # Siempre guardar el JSON completo para facilitar recuperación
                    # Esto es crucial para asegurar que la clasificación manual se mantenga entre vistas
                    datos_clasificacion['clasificacion_manual_json'] = json.dumps(manual)
                    logger.info(f"JSON de clasificación manual: {datos_clasificacion['clasificacion_manual_json']}")
                    
                    # Actualizar también el archivo JSON original de clasificación
                    clasificacion_data['clasificacion_manual'] = clasificacion_manual_dict
                    with open(clasificacion_file, 'w', encoding='utf-8') as f:
                        json.dump(clasificacion_data, f, indent=4)
                    logger.info(f"Archivo de clasificación actualizado en: {clasificacion_file}")
                
                # Agregar datos de clasificación automática si existen
                if 'clasificacion_automatica' in clasificacion_data:
                    auto = clasificacion_data['clasificacion_automatica']
                    # Guardar el JSON completo para facilitar recuperación
                    datos_clasificacion['clasificacion_automatica_json'] = json.dumps(auto)
                    
                    # Obtener porcentajes o cantidades según lo que esté disponible
                    try:
                        # Verificar si es un diccionario con estructura completa
                        datos_clasificacion.update({
                            'verde_automatico': auto.get('verdes', {}).get('porcentaje', 0) if isinstance(auto.get('verdes'), dict) else auto.get('verdes', 0),
                            'sobremaduro_automatico': auto.get('sobremaduros', {}).get('porcentaje', 0) if isinstance(auto.get('sobremaduros'), dict) else auto.get('sobremaduros', 0),
                            'danio_corona_automatico': auto.get('danio_corona', {}).get('porcentaje', 0) if isinstance(auto.get('danio_corona'), dict) else auto.get('danio_corona', 0),
                            'pendunculo_largo_automatico': auto.get('pendunculo_largo', {}).get('porcentaje', 0) if isinstance(auto.get('pendunculo_largo'), dict) else auto.get('pendunculo_largo', 0),
                            'podrido_automatico': auto.get('podridos', {}).get('porcentaje', 0) if isinstance(auto.get('podridos'), dict) else auto.get('podridos', 0)
                        })
                    except Exception as e:
                        logger.error(f"Error procesando clasificación automática: {str(e)}")
                
                # Guardar datos en la base de datos usando store_clasificacion
                from db_operations import store_clasificacion
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

def generate_annotated_image(original_image_path, detections, output_path=None):
    """
    Genera una imagen con anotaciones (bounding boxes) basadas en las detecciones
    de Roboflow y guarda la imagen procesada.
    
    Args:
        original_image_path (str): Ruta al archivo de imagen original
        detections (list): Lista de detecciones con x, y, width, height y class
        output_path (str, optional): Ruta donde guardar la imagen procesada
        
    Returns:
        str: Ruta a la imagen procesada generada
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import os
        
        # Verificar que la imagen original existe
        if not os.path.exists(original_image_path):
            logger.error(f"Imagen original no encontrada: {original_image_path}")
            return None
        
        # Determinar ruta de salida si no se proporciona
        if not output_path:
            base_dir = os.path.dirname(original_image_path)
            base_name = os.path.basename(original_image_path)
            name, ext = os.path.splitext(base_name)
            output_path = os.path.join(base_dir, f"{name}_annotated{ext}")
        
        # Crear directorio si no existe
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # Abrir imagen original
        img = Image.open(original_image_path)
        draw = ImageDraw.Draw(img)
        
        # Colores para diferentes clases (formato RGB)
        class_colors = {
            'verde': (0, 128, 0),  # Verde
            'maduro': (255, 165, 0), # Naranja
            'sobremaduro': (255, 0, 0), # Rojo
            'podrido': (75, 0, 130), # Índigo
            'danio_corona': (255, 192, 203), # Rosa
            'pendunculo_largo': (0, 0, 255), # Azul
            'racimo': (128, 128, 128), # Gris para la detección general
            'conteo-de-racimos-de-palma': (128, 128, 128), # Gris para la detección general (Alias)
        }
        
        # Intentar cargar una fuente
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            try:
                # Alternativas de fuente
                font = ImageFont.truetype("DejaVuSans.ttf", 20)
            except:
                font = ImageFont.load_default()
        
        # Dibujar cada detección
        for detection in detections:
            detection_class = detection['class']
            confidence = detection['confidence']
            color = class_colors.get(detection_class.lower(), "white") # Default a blanco si la clase no está mapeada

            # --- Calcular coordenadas de esquina desde el centro ---
            x_center = detection['x']
            y_center = detection['y']
            width = detection['width']
            height = detection['height']

            # --- ¡NUEVO! Verificar y escalar coordenadas si están normalizadas (0-1) ---
            img_width, img_height = img.size
            if 0 <= x_center <= 1 and 0 <= y_center <= 1 and width < 1 and height < 1:
                logger.debug(f"Coordenadas parecen normalizadas. Escalando con: {img.size}")
                x_center *= img_width
                y_center *= img_height
                width *= img_width
                height *= img_height
            # --- Fin verificación de escala ---

            # --- Calcular coordenadas de esquina desde el centro (ahora en píxeles) ---
            x1 = x_center - (width / 2)
            y1 = y_center - (height / 2)
            x2 = x_center + (width / 2)
            y2 = y_center + (height / 2)
            # --- Fin del cálculo ---

            logger.debug(f"  Calculadas esquinas: ({x1:.1f}, {y1:.1f}) -> ({x2:.1f}, {y2:.1f})") # LOG ESQUINAS

            # Dibujar rectángulo usando las coordenadas de esquina calculadas (convertidas a int)
            draw.rectangle([int(x1), int(y1), int(x2), int(y2)], outline=color, width=3)

            # Preparar texto y fondo para la etiqueta
            label_text = f"{detection_class}: {confidence:.0%}"
            try:
                # Usar textbbox para obtener el tamaño exacto del texto
                text_bbox = draw.textbbox((0, 0), label_text, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
            except AttributeError:
                # Fallback para versiones antiguas de Pillow
                text_size = draw.textsize(label_text, font=font)
                text_width = text_size[0]
                text_height = text_size[1]

            logger.debug(f"  Calculado tamaño texto: W={text_width}, H={text_height}") # LOG TAMAÑO TEXTO

            # Posición de la etiqueta (usando x1, y1 calculados) - REVERTIDO A ORIGINAL
            # Asegurarse de que la etiqueta no se salga por arriba
            text_y_base = y1 + 2
            if text_y_base < 0: # Si la caja está muy arriba
                text_y_base = y2 - text_height - 2 # Ponerla dentro por abajo
            text_x = x1 + 2

            logger.debug(f"  Calculada posición texto: X={text_x:.1f}, Y={text_y_base:.1f}") # LOG POSICIÓN TEXTO

            # Dibujar fondo de etiqueta (convertido a int)
            draw.rectangle([int(text_x), int(text_y_base), int(text_x + text_width + 4), int(text_y_base + text_height + 4)], fill=color)
            # Dibujar texto de etiqueta (convertido a int)
            draw.text((int(text_x + 2), int(text_y_base + 2)), label_text, fill="white", font=font)
        
        # Guardar imagen procesada
        img.save(output_path)
        logger.info(f"Imagen procesada generada y guardada en: {output_path}")
        
        # Convertir ruta absoluta a relativa para la URL
        static_folder = current_app.static_folder
        if output_path.startswith(static_folder):
            rel_path = output_path[len(static_folder):].lstrip(os.sep)
            url_path = url_for('static', filename=rel_path)
            return url_path
        else:
            return output_path
        
    except Exception as e:
        logger.error(f"Error generando imagen anotada: {str(e)}")
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
        from app.blueprints.clasificacion.generate_annotated_image import generate_annotated_image
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
    conn = None
    try:
        json_filename = f"clasificacion_{codigo_guia}.json"
        json_path = os.path.join(current_app.static_folder, 'clasificaciones', json_filename)

        if not os.path.exists(json_path):
            return jsonify({'success': False, 'message': 'Archivo JSON no encontrado'}), 404

        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)

        conn = sqlite3.connect(current_app.config['TIQUETES_DB_PATH'])
        cursor = conn.cursor()

        # Preparar los datos para la actualización
        datos = {
            'codigo_guia': codigo_guia,
            'fecha_clasificacion': clasificacion_data.get('fecha_registro'),
            'hora_clasificacion': clasificacion_data.get('hora_registro'),
            'clasificacion_manual': json.dumps(clasificacion_data.get('clasificacion_manual', {})),
            'clasificacion_automatica': json.dumps(clasificacion_data.get('clasificacion_automatica', {})),
            'estado': clasificacion_data.get('estado', 'activo')
        }

        # Intentar actualizar primero
        cursor.execute("""
            UPDATE clasificaciones 
            SET fecha_clasificacion = :fecha_clasificacion,
                hora_clasificacion = :hora_clasificacion,
                clasificacion_manual = :clasificacion_manual,
                clasificacion_automatica = :clasificacion_automatica,
                estado = :estado
            WHERE codigo_guia = :codigo_guia
        """, datos)

        # Si no se actualizó ningún registro, insertar uno nuevo
        if cursor.rowcount == 0:
            cursor.execute("""
                INSERT INTO clasificaciones (
                    codigo_guia, fecha_clasificacion, hora_clasificacion,
                    clasificacion_manual, clasificacion_automatica, estado
                ) VALUES (
                    :codigo_guia, :fecha_clasificacion, :hora_clasificacion,
                    :clasificacion_manual, :clasificacion_automatica, :estado
                )
            """, datos)

        conn.commit()
        conn.close()

        current_app.logger.info(f"Datos de clasificación sincronizados para guía {codigo_guia}")
        return jsonify({
            'success': True,
            'message': 'Datos de clasificación sincronizados correctamente'
        })

    except Exception as e:
        current_app.logger.error(f"Error sincronizando datos de clasificación: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error sincronizando datos de clasificación: {str(e)}'
        })
    finally:
        if conn:
            conn.close()

def get_clasificacion_by_codigo_guia(codigo_guia):
    """
    Recupera un registro de clasificación por su código de guía.
    
    Args:
        codigo_guia (str): Código de guía a buscar
        
    Returns:
        dict: Datos de la clasificación o None si no se encuentra
    """
    conn = None # Initialize conn to None before the try block
    try:
        db_path = current_app.config['TIQUETES_DB_PATH'] # Get DB path from app config
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM clasificaciones WHERE codigo_guia = ?", (codigo_guia,))
        row = cursor.fetchone()
        
        if row:
            clasificacion = {key: row[key] for key in row.keys()}
            
            # Obtener fotos asociadas
            cursor.execute("SELECT ruta_foto FROM fotos_clasificacion WHERE codigo_guia = ? ORDER BY numero_foto", 
                         (codigo_guia,))
            fotos = [row[0] for row in cursor.fetchall()]
            clasificacion['fotos'] = fotos
            
            # Si clasificaciones es una cadena JSON, convertirla a lista
            if isinstance(clasificacion.get('clasificaciones'), str):
                try:
                    clasificacion['clasificaciones'] = json.loads(clasificacion['clasificaciones'])
                except json.JSONDecodeError:
                    clasificacion['clasificaciones'] = []
            
            # Si clasificacion_automatica es una cadena JSON, convertirla a diccionario
            if isinstance(clasificacion.get('clasificacion_automatica'), str):
                try:
                    clasificacion['clasificacion_automatica'] = json.loads(clasificacion['clasificacion_automatica'])
                except json.JSONDecodeError:
                    clasificacion['clasificacion_automatica'] = {}
                # # Limpiar Nones después de cargar desde JSON  <- COMMENTED OUT BLOCK
                # if isinstance(clasificacion.get('clasificacion_automatica'), dict):
                #     clasificacion['clasificacion_automatica'] = clean_classification_dict(clasificacion['clasificacion_automatica'])
                #     logger.info(f"Limpiado clasificacion_automatica tras carga DB: {clasificacion['clasificacion_automatica']}")
                    
            # Si clasificacion_manual_json existe, convertirlo y asignarlo a clasificacion_manual
            if 'clasificacion_manual_json' in clasificacion and clasificacion['clasificacion_manual_json']:
                try:
                    clasificacion['clasificacion_manual'] = json.loads(clasificacion['clasificacion_manual_json'])
                    logger.info(f"Convertido clasificacion_manual_json a clasificacion_manual: {clasificacion['clasificacion_manual']}")
                except json.JSONDecodeError:
                    logger.error(f"Error decodificando clasificacion_manual_json: {clasificacion['clasificacion_manual_json']}")
                    clasificacion['clasificacion_manual'] = {}
                # # Limpiar Nones después de cargar desde JSON  <- COMMENTED OUT BLOCK
                # if isinstance(clasificacion.get('clasificacion_manual'), dict):
                #      clasificacion['clasificacion_manual'] = clean_classification_dict(clasificacion['clasificacion_manual'])
                #      logger.info(f"Limpiado clasificacion_manual tras carga DB: {clasificacion['clasificacion_manual']}")
            
            return clasificacion
        return None
    except sqlite3.Error as e:
        logger.error(f"Error recuperando registro de clasificación por código de guía: {e}")
        return None
    finally:
        if conn:
            conn.close()

@bp.route('/ver_detalles_clasificacion/<url_guia>')
def ver_detalles_clasificacion(url_guia):
    """
    Muestra los detalles de clasificación por foto para una guía específica
    """
    import time
    from flask import current_app, make_response
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
        'datos_guia': {} # Initialize datos_guia
    }

    try:
        logger.info(f"Código de guía a buscar: {url_guia}")

        # Buscar el archivo de clasificación
        clasificacion_path = os.path.join(current_app.static_folder, 'clasificaciones', f"clasificacion_{url_guia}.json")
        template_data['json_path'] = clasificacion_path

        # Add logic to search alternative paths as in the archive if needed
        if not os.path.exists(clasificacion_path):
             # Intentar buscar en subdirectorios (Adaptado del archivo archivado)
            alt_paths_to_check = [
                os.path.join(current_app.static_folder, 'fotos_racimos_temp', url_guia, f"clasificacion_{url_guia}.json"),
                os.path.join(current_app.static_folder, current_app.config.get('FOTOS_RACIMOS_FOLDER', 'fotos_racimos_temp'), url_guia, f"clasificacion_{url_guia}.json")
            ]
            for alt_path in alt_paths_to_check:
                 if os.path.exists(alt_path):
                     clasificacion_path = alt_path
                     template_data['json_path'] = alt_path
                     logger.info(f"Archivo de clasificación encontrado en ruta alternativa: {alt_path}")
                     break

        if not os.path.exists(clasificacion_path):
            logger.error(f"No se encontró el archivo de clasificación para: {url_guia} en {template_data['json_path']} ni en rutas alternativas.")
            flash("No se encontró información de clasificación para esta guía", "error")
            # Render the correct template even on error
            return render_template('detalles_clasificacion.html', **template_data)

        # Leer el archivo de clasificación
        with open(clasificacion_path, 'r', encoding='utf-8') as f:
            clasificacion_data = json.load(f)
            logger.info(f"Clasificación leída del archivo: {clasificacion_path}")
            template_data['raw_data'] = clasificacion_data
            if 'tiempo_procesamiento' in clasificacion_data:
                template_data['tiempo_procesamiento'] = clasificacion_data['tiempo_procesamiento']

        # Obtener datos de la guía (Asumiendo que Utils está disponible)
        try:
            utils = Utils(current_app)
            datos_guia = utils.get_datos_guia(url_guia)
            template_data['datos_guia'] = datos_guia
            logger.info(f"Datos de guía obtenidos: {datos_guia}")
        except Exception as e:
            logger.error(f"Error al obtener datos de la guía: {str(e)}")
            logger.error(traceback.format_exc())
            template_data['datos_guia'] = {}

        # Procesar fotos originales (Adaptado del archivo archivado)
        fotos_originales_urls = []
        if 'fotos' in clasificacion_data:
            fotos_paths_json = clasificacion_data['fotos']
            fotos_filtradas = []
            for foto_path in fotos_paths_json:
                 if len(fotos_filtradas) >= 3: break
                 if isinstance(foto_path, str) and 'resized' not in foto_path and 'annotated' not in foto_path:
                      fotos_filtradas.append(foto_path)

            for i, foto_path in enumerate(fotos_filtradas):
                 url = None
                 if os.path.isabs(foto_path):
                      static_folder = current_app.static_folder
                      if foto_path.startswith(static_folder):
                           rel_path = foto_path.replace(static_folder, '').lstrip('/')
                           url = url_for('static', filename=rel_path)
                      else: # Try finding by basename in standard locations
                           file_name = os.path.basename(foto_path)
                           possible_rels = [
                               f"uploads/fotos/{url_guia}/{file_name}",
                               f"fotos_racimos_temp/{url_guia}/{file_name}"
                               # Add other likely locations if necessary
                           ]
                           for rel_path in possible_rels:
                                if os.path.exists(os.path.join(static_folder, rel_path)):
                                     url = url_for('static', filename=rel_path)
                                     break
                 else: # Assume relative path is correct
                      url = url_for('static', filename=foto_path)

                 if url: fotos_originales_urls.append(url)
                 else: logger.warning(f"No se pudo generar URL para foto original: {foto_path}")

            template_data['fotos_originales'] = fotos_originales_urls
            logger.info(f"Fotos originales procesadas para URL: {fotos_originales_urls}")

        # Extraer resultados por foto (Adaptado y simplificado del archivo archivado)
        resultados_por_foto_procesados = []
        if 'resultados_por_foto' in clasificacion_data:
            logger.info("Procesando 'resultados_por_foto' del JSON")
            resultados_data = clasificacion_data['resultados_por_foto']

            # Handle dict structure (e.g., {'1': {...}, '2': {...}})
            if isinstance(resultados_data, dict):
                keys = sorted([int(k) for k in resultados_data.keys() if k.isdigit()], key=int)
                for key in keys:
                    if len(resultados_por_foto_procesados) >= 3: break
                    str_key = str(key)
                    if str_key in resultados_data:
                        resultado = resultados_data[str_key]
                        detecciones = resultado.get('detecciones', [])
                        raw_result = resultado.get('raw_result', {})
                        
                        # --- INICIO: Corregir asignación de imagen original ---
                        # Usar el índice (key - 1 porque los keys son 1-based) para obtener la URL de la lista original
                        imagen_original_url = None # Default to None
                        original_image_index = key - 1
                        if 0 <= original_image_index < len(fotos_originales_urls):
                            imagen_original_url = fotos_originales_urls[original_image_index]
                            logger.info(f"Asignada URL de imagen original para foto {key}: {imagen_original_url}")
                        else:
                            logger.warning(f"No se pudo encontrar URL original correspondiente para foto {key} (índice {original_image_index})")
                        # --- FIN: Corregir asignación de imagen original ---
                        
                        # --- DEBUG: Print the raw_result being processed ---
                        logger.info(f"DEBUG Foto {key}: Processing raw_result: {json.dumps(raw_result, indent=2)}")
                        # --- END DEBUG ---
                        
                        # --- INICIO: Lógica Robusta de extracción de imágenes (EXISTING CODE) ---
                        imagen_annotated_url = None
                        imagen_clasificada_url = None

                        # Función auxiliar para decodificar y guardar
                        def decode_and_save(base64_str, filename_suffix):
                            try:
                                import base64
                                # Add padding if necessary for base64 decoding
                                missing_padding = len(base64_str) % 4
                                if missing_padding:
                                    base64_str += '=' * (4 - missing_padding)
                                    logger.info(f"Added padding to base64 string for {filename_suffix.upper()} foto {key}")
                                
                                img_data = base64.b64decode(base64_str)
                                output_filename = f"{url_guia}_foto{key}_roboflow_{filename_suffix}.jpg"
                                output_dir = os.path.join(current_app.static_folder, 'fotos_racimos_temp', url_guia)
                                output_path = os.path.join(output_dir, output_filename)
                                
                                # Ensure directory exists
                                os.makedirs(output_dir, exist_ok=True)
                                logger.info(f"Ensured directory exists: {output_dir}")
                                
                                with open(output_path, 'wb') as f:
                                    f.write(img_data)
                                logger.info(f"Successfully wrote image file to: {output_path}")
                                    
                                # Generate URL relative to static folder
                                image_url = f"/static/fotos_racimos_temp/{url_guia}/{output_filename}"
                                logger.info(f"Imagen {filename_suffix.upper()} guardada y URL generada para foto {key}: {image_url}")
                                return image_url
                            except base64.binascii.Error as b64_error:
                                logger.error(f"Error decoding base64 for {filename_suffix.upper()} foto {key}: {str(b64_error)}")
                                # Optionally log part of the string: logger.error(f"Base64 start: {base64_str[:50]}...")
                                return None
                            except OSError as os_error:
                                logger.error(f"Error saving file {output_path} for {filename_suffix.upper()} foto {key}: {str(os_error)}")
                                return None
                            except Exception as e:
                                logger.error(f"Unexpected error processing image {filename_suffix.upper()} para foto {key}: {str(e)}")
                                logger.error(traceback.format_exc())
                                return None

                        # Caso 1: raw_result es un Diccionario
                        if isinstance(raw_result, dict):
                            logger.info(f"Procesando raw_result como diccionario para foto {key}")
                            # 1. Buscar imagen ANNOTATED dentro de la lista 'outputs'
                            outputs_list = raw_result.get('outputs', [])
                            if isinstance(outputs_list, list):
                                for output_item in outputs_list:
                                    if isinstance(output_item, dict):
                                        img_annotated_dict = output_item.get('annotated_image', {})
                                        img_annotated_base64 = img_annotated_dict.get('value')
                                        if img_annotated_base64:
                                            imagen_annotated_url = decode_and_save(img_annotated_base64, "annotated")
                                            break # Encontramos la primera, salimos del bucle interno
                            if not imagen_annotated_url:
                                logger.warning(f"No se encontró 'annotated_image' -> 'value' dentro de la lista 'outputs' en raw_result (dict) para foto {key}")

                            # 2. Buscar imagen CLASIFICADA/LABELED directamente bajo raw_result
                            # CORRECTED: Check for the value within the nested dict
                            img_labeled_dict = raw_result.get('label_visualization_1', None) # Get dict or None
                            logger.info(f"DEBUG Foto {key}: img_labeled_dict = {img_labeled_dict is not None}") # Log if dict was found
                            
                            img_labeled_base64 = None
                            if img_labeled_dict and isinstance(img_labeled_dict, dict):
                                img_labeled_base64 = img_labeled_dict.get('value')
                                logger.info(f"DEBUG Foto {key}: img_labeled_base64 found = {img_labeled_base64 is not None}") # Log if base64 string was found
                                
                            # FALLBACK: If label_visualization_1 wasn't found, try annotated_image as a fallback
                            if not img_labeled_base64:
                                logger.warning(f"label_visualization_1 not found or missing 'value' for foto {key}, trying annotated_image as fallback")
                                img_annotated_fallback = raw_result.get('annotated_image', None)
                                if img_annotated_fallback and isinstance(img_annotated_fallback, dict):
                                    img_labeled_base64 = img_annotated_fallback.get('value')
                                    logger.info(f"Using annotated_image as fallback for label_visualization_1 for foto {key}")

                            # FALLBACK: Try to find any key with "visualiz" in the name
                            if not img_labeled_base64:
                                for key_name, value in raw_result.items():
                                    if 'visualiz' in key_name.lower() and isinstance(value, dict) and 'value' in value:
                                        img_labeled_base64 = value.get('value')
                                        logger.info(f"Found alternative visualization key: {key_name} for foto {key}")
                                        break
                            
                            # NEW FALLBACK: Check inside outputs[0] which is where it might be for photo 3
                            if not img_labeled_base64 and 'outputs' in raw_result and isinstance(raw_result['outputs'], list) and len(raw_result['outputs']) > 0:
                                outputs_item = raw_result['outputs'][0]
                                if isinstance(outputs_item, dict) and 'label_visualization_1' in outputs_item:
                                    logger.info(f"Found label_visualization_1 inside outputs[0] for foto {key}")
                                    img_labeled_outputs = outputs_item.get('label_visualization_1')
                                    if isinstance(img_labeled_outputs, dict) and 'value' in img_labeled_outputs:
                                        img_labeled_base64 = img_labeled_outputs.get('value')
                                        logger.info(f"Successfully extracted base64 value from outputs[0].label_visualization_1 for foto {key}")
                                        
                            if img_labeled_base64:
                                logger.info(f"DEBUG Foto {key}: Attempting decode_and_save for LABELED image.") # Log before calling
                                imagen_clasificada_url = decode_and_save(img_labeled_base64, "labeled")
                            elif img_labeled_dict is not None: # Log only if the base dict existed but value didn't
                                logger.warning(f"Found 'label_visualization_1' dict but missing 'value' key in raw_result (dict) for foto {key}")
                            else: # Log if the base dict itself wasn't found
                                logger.warning(f"Did not find 'label_visualization_1' key in raw_result (dict) for foto {key}")
                                # Additional debug info on raw_result structure
                                logger.info(f"DEBUG Foto {key}: raw_result keys: {list(raw_result.keys())}")
                                for r_key in raw_result.keys():
                                    if isinstance(raw_result[r_key], dict):
                                        logger.info(f"DEBUG Foto {key}: raw_result[{r_key}] is a dict with keys: {list(raw_result[r_key].keys())}")
                                    elif isinstance(raw_result[r_key], list) and len(raw_result[r_key]) > 0:
                                        logger.info(f"DEBUG Foto {key}: raw_result[{r_key}] is a list with {len(raw_result[r_key])} items")
                                        if isinstance(raw_result[r_key][0], dict):
                                            logger.info(f"DEBUG Foto {key}: raw_result[{r_key}][0] keys: {list(raw_result[r_key][0].keys())}")

                        # Caso 2: raw_result es una Lista
                        elif isinstance(raw_result, list):
                            logger.warning(f"raw_result para foto {key} es una lista. Buscando imágenes en los elementos.")
                            for item in raw_result:
                                if isinstance(item, dict):
                                    # Intentar encontrar imagen ANNOTATED en el item
                                    if not imagen_annotated_url:
                                        # CORRECTED: Access outputs as a list
                                        outputs_list_item = item.get('outputs', [])
                                        if outputs_list_item and isinstance(outputs_list_item, list) and len(outputs_list_item) > 0:
                                            img_annotated_dict = outputs_list_item[0].get('annotated_image', {})
                                            img_annotated_base64 = img_annotated_dict.get('value')
                                            if img_annotated_base64:
                                                imagen_annotated_url = decode_and_save(img_annotated_base64, "annotated")
                                        else:
                                            logger.warning(f"Could not find 'outputs' list or 'annotated_image' within item for Foto {key}")
                                            
                                    # Intentar encontrar imagen LABELED en el item
                                    if not imagen_clasificada_url:
                                        # CORRECTED: Check for the value within the nested dict
                                        img_labeled_dict_item = item.get('label_visualization_1', None)
                                        logger.info(f"DEBUG Foto {key} (list item): img_labeled_dict_item = {img_labeled_dict_item is not None}")
                                        
                                        img_labeled_base64_item = None
                                        if img_labeled_dict_item and isinstance(img_labeled_dict_item, dict):
                                            img_labeled_base64_item = img_labeled_dict_item.get('value')
                                            logger.info(f"DEBUG Foto {key} (list item): img_labeled_base64_item found = {img_labeled_base64_item is not None}")
                                            
                                        # FALLBACK: If label_visualization_1 wasn't found, try annotated_image as a fallback
                                        if not img_labeled_base64_item:
                                            logger.warning(f"label_visualization_1 not found or missing 'value' for foto {key} (list item), trying annotated_image as fallback")
                                            img_annotated_fallback = item.get('annotated_image', None)
                                            if img_annotated_fallback and isinstance(img_annotated_fallback, dict):
                                                img_labeled_base64_item = img_annotated_fallback.get('value')
                                                logger.info(f"Using annotated_image as fallback for label_visualization_1 for foto {key} (list item)")

                                        # FALLBACK: Try to find any key with "visualiz" in the name
                                        if not img_labeled_base64_item:
                                            for key_name, value in item.items():
                                                if 'visualiz' in key_name.lower() and isinstance(value, dict) and 'value' in value:
                                                    img_labeled_base64_item = value.get('value')
                                                    logger.info(f"Found alternative visualization key: {key_name} for foto {key} (list item)")
                                                    break
                                                
                                        if img_labeled_base64_item:
                                            logger.info(f"DEBUG Foto {key} (list item): Attempting decode_and_save for LABELED image.")
                                            imagen_clasificada_url = decode_and_save(img_labeled_base64_item, "labeled")
                                        elif img_labeled_dict_item is not None:
                                            logger.warning(f"Found 'label_visualization_1' dict but missing 'value' key in raw_result (list item) for foto {key}")
                                        # Log all keys in the item for debugging
                                        elif isinstance(item, dict):
                                            logger.warning(f"Did not find 'label_visualization_1' key in list item for foto {key}")
                                            logger.info(f"DEBUG Foto {key} (list item): item keys: {list(item.keys())}")
                                        # No need for final else here, outer loop will log if nothing found

                                # Salir si ya encontramos ambas
                                if imagen_annotated_url and imagen_clasificada_url:
                                    break
                            if not imagen_annotated_url: logger.warning(f"No se encontró imagen ANNOTATED en la lista raw_result para foto {key}")
                            if not imagen_clasificada_url: logger.warning(f"No se encontró imagen LABELED en la lista raw_result para foto {key}")
                            
                        # Caso 3: Tipo inesperado
                        else:
                             logger.warning(f"Tipo inesperado para raw_result en foto {key}: {type(raw_result)}. No se buscarán imágenes de Roboflow.")

                        # --- FIN: Lógica Robusta de extracción de imágenes ---

                        # --- INICIO: Extraer total de racimos (potholes_detected) ---
                        # Obtener el total de racimos detectados de potholes_detected
                        total_racimos_detectados = 0
                        
                        # Buscar potholes_detected en el raw_result
                        if isinstance(raw_result, dict):
                            # Buscar directamente en raw_result
                            if 'potholes_detected' in raw_result:
                                try:
                                    total_racimos_detectados = int(raw_result.get('potholes_detected', 0))
                                    logger.info(f"Foto {key}: Encontrado potholes_detected directamente en raw_result: {total_racimos_detectados}")
                                except (ValueError, TypeError):
                                    total_racimos_detectados = 0
                                    logger.warning(f"Foto {key}: potholes_detected en raw_result no es un número válido")
                            # Buscar en outputs[0] si existe
                            elif 'outputs' in raw_result and isinstance(raw_result['outputs'], list) and len(raw_result['outputs']) > 0:
                                outputs_item = raw_result['outputs'][0]
                                if isinstance(outputs_item, dict) and 'potholes_detected' in outputs_item:
                                    try:
                                        total_racimos_detectados = int(outputs_item.get('potholes_detected', 0))
                                        logger.info(f"Foto {key}: Encontrado potholes_detected en outputs[0]: {total_racimos_detectados}")
                                    except (ValueError, TypeError):
                                        total_racimos_detectados = 0
                                        logger.warning(f"Foto {key}: potholes_detected en outputs[0] no es un número válido")
                        
                        # Si no se encontró, usar el número de detecciones como fallback
                        if total_racimos_detectados <= 0:
                            total_racimos_detectados = len(detecciones)
                            logger.info(f"Foto {key}: No se encontró potholes_detected válido, usando longitud de detecciones: {total_racimos_detectados}")
                        
                        # Asegurar siempre un valor mínimo de 1 racimo si hay detecciones
                        if total_racimos_detectados <= 0 and len(detecciones) > 0:
                            total_racimos_detectados = len(detecciones)
                            logger.warning(f"Foto {key}: potholes_detected era 0 o negativo con {len(detecciones)} detecciones, estableciendo a: {total_racimos_detectados}")
                        
                        # Log final del valor utilizado
                        logger.info(f"Foto {key}: Valor final de racimos detectados: {total_racimos_detectados} (tipo: {type(total_racimos_detectados).__name__})")
                        # --- FIN: Extraer total de racimos ---

                        # --- INICIO: Calcular conteo de categorías desde detecciones ---
                        categorias = { 
                            cat: {'cantidad': 0, 'porcentaje': 0.0} 
                            for cat in ['verde', 'maduro', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido']
                        }
                        # Normalizar nombres de clases esperados (minúsculas, sin tildes, nombres alternativos)
                        mapping_clases = {
                            'verde': 'verde',
                            'verdes': 'verde',
                            'maduro': 'maduro',
                            'maduros': 'maduro',
                            'sobremaduro': 'sobremaduro',
                            'sobremaduros': 'sobremaduro',
                            'sobre maduro': 'sobremaduro',
                            'danio_corona': 'danio_corona',
                            'danio corona': 'danio_corona',
                            'daño_corona': 'danio_corona',
                            'daño corona': 'danio_corona',
                            'pendunculo_largo': 'pendunculo_largo',
                            'pendunculo largo': 'pendunculo_largo',
                            'pedunculo_largo': 'pendunculo_largo',
                            'pedunculo largo': 'pendunculo_largo',
                            'podrido': 'podrido',
                            'podridos': 'podrido'
                        }
                        
                        total_detecciones_calculado = len(detecciones)
                        if total_detecciones_calculado > 0:
                            for det in detecciones:
                                clase_original = det.get('class', '').lower().strip()
                                clase_normalizada = mapping_clases.get(clase_original)
                                if clase_normalizada and clase_normalizada in categorias:
                                    categorias[clase_normalizada]['cantidad'] += 1
                                elif clase_original: # Log if class not mapped
                                    logger.warning(f"Clase detectada '{clase_original}' no mapeada en foto {key}")
                                    
                            # Calcular porcentajes
                            for cat in categorias:
                                if categorias[cat]['cantidad'] > 0:
                                    categorias[cat]['porcentaje'] = round((categorias[cat]['cantidad'] / total_racimos_detectados) * 100, 1)
                        # --- FIN: Calcular conteo de categorías desde detecciones ---

                        # Preparar el diccionario para el template
                        foto_procesada = {
                            'numero': key,
                            'imagen_original': imagen_original_url, # Usar la URL obtenida
                            'imagen_annotated': imagen_annotated_url, 
                            'imagen_clasificada': imagen_clasificada_url, 
                            'detecciones': detecciones,
                            # Usar las categorías calculadas
                            'conteo_categorias': categorias, 
                            'total_detecciones': total_detecciones_calculado, # Mantener para compatibilidad
                            'total_racimos': total_racimos_detectados # Asegurarnos de que este valor sea correcto
                        }
                        
                        # Logging para verificar que los datos se están asignando correctamente
                        logger.info(f"Foto {key}: Agregando a resultados_por_foto_procesados con total_racimos={total_racimos_detectados}")
                        resultados_por_foto_procesados.append(foto_procesada)

            elif isinstance(resultados_data, list):
                logger.warning("Procesamiento de 'resultados_por_foto' como lista no completamente implementado en esta restauración.")
                # Implementar lógica similar a la del 'dict' si este formato es posible

        else:
             logger.warning("'resultados_por_foto' no encontrado en el JSON.")

        # Si no hay resultados procesados pero sí fotos originales, crear entradas básicas
        if not resultados_por_foto_procesados and template_data['fotos_originales']:
             logger.info("Creando entradas básicas para fotos procesadas ya que 'resultados_por_foto' estaba vacío/ausente.")
             for i, foto_orig_url in enumerate(template_data['fotos_originales'][:3]):
                  resultados_por_foto_procesados.append({
                       'numero': i + 1,
                       'imagen_original': foto_orig_url,
                       'imagen_annotated': None, # Añadir campo por defecto
                       'imagen_clasificada': None,
                       'detecciones': [],
                       'conteo_categorias': { cat: {'cantidad': 0, 'porcentaje': 0.0} for cat in ['verdes', 'maduros', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']},
                       'total_detecciones': 0
                  })

        template_data['fotos_procesadas'] = resultados_por_foto_procesados

        # Extraer clasificación consolidada (si existe)
        if 'clasificacion_automatica' in clasificacion_data:
            template_data['clasificacion_automatica_consolidada'] = clasificacion_data['clasificacion_automatica']

        # Calcular total de racimos acumulados de todas las fotos
        total_racimos_acumulados = 0
        for foto in resultados_por_foto_procesados:
            if 'total_racimos' in foto and foto['total_racimos'] is not None:
                try:
                    total_racimos_acumulados += int(foto['total_racimos'])
                    logger.info(f"Sumando {foto['total_racimos']} racimos de foto {foto.get('numero', '?')} al total acumulado")
                except (ValueError, TypeError):
                    logger.warning(f"No se pudo convertir a entero: {foto['total_racimos']}")
        
        # Pasar explícitamente el total a la plantilla
        template_data['total_racimos_acumulados'] = total_racimos_acumulados
        logger.info(f"Total de racimos acumulados para enviar a la plantilla: {total_racimos_acumulados}")

        end_time = time.time()
        template_data['tiempo_procesamiento'] = round(end_time - start_time, 2)

        # Guardar los totales consolidados en la base de datos
        try:
            import sqlite3
            conn = sqlite3.connect('tiquetes.db')
            cursor = conn.cursor()
            
            # Verificar si ya existe un registro para esta guía
            cursor.execute("SELECT id FROM clasificaciones WHERE codigo_guia = ?", (url_guia,))
            existing = cursor.fetchone()
            
            # Crear diccionario con los totales por categoría
            categorias_consolidadas = {}
            for foto in resultados_por_foto_procesados:
                for cat, datos in foto.get('conteo_categorias', {}).items():
                    if cat not in categorias_consolidadas:
                        categorias_consolidadas[cat] = {'cantidad': 0, 'porcentaje': 0.0}
                    categorias_consolidadas[cat]['cantidad'] += datos.get('cantidad', 0)
            
            # Calcular porcentajes
            if total_racimos_acumulados > 0:
                for cat in categorias_consolidadas:
                    categorias_consolidadas[cat]['porcentaje'] = round((categorias_consolidadas[cat]['cantidad'] / total_racimos_acumulados) * 100, 1)
            
            # Convertir a JSON para almacenar
            categorias_json = json.dumps(categorias_consolidadas)
            
            # Fecha y hora actual
            fecha_actual = datetime.now().strftime('%Y-%m-%d')
            hora_actual = datetime.now().strftime('%H:%M:%S')
            
            if existing:
                # Actualizar registro existente
                cursor.execute("""
                    UPDATE clasificaciones 
                    SET total_racimos_detectados = ?, 
                        clasificacion_consolidada = ?,
                        fecha_actualizacion = ?,
                        hora_actualizacion = ?
                    WHERE codigo_guia = ?
                """, (total_racimos_acumulados, categorias_json, fecha_actual, hora_actual, url_guia))
                logger.info(f"Actualizado registro de clasificación para guía {url_guia}")
            else:
                # Insertar nuevo registro 
                cursor.execute("""
                    INSERT INTO clasificaciones 
                    (codigo_guia, total_racimos_detectados, clasificacion_consolidada, 
                    fecha_actualizacion, hora_actualizacion)
                    VALUES (?, ?, ?, ?, ?)
                """, (url_guia, total_racimos_acumulados, categorias_json, fecha_actual, hora_actual))
                logger.info(f"Insertado nuevo registro de clasificación para guía {url_guia}")
            
            # Confirmar la transacción
            conn.commit()
            logger.info(f"Datos consolidados guardados en BD: guía={url_guia}, total_racimos={total_racimos_acumulados}")
        except Exception as e:
            logger.error(f"Error guardando datos consolidados en BD: {str(e)}")
            logger.error(traceback.format_exc())
        finally:
            if 'conn' in locals():
                conn.close()

        # Renderizar la plantilla correcta
        logger.info(f"Renderizando plantilla: detalles_clasificacion.html")
        return render_template('detalles_clasificacion.html', **template_data)

    except Exception as e:
        logger.error(f"Error general en ver_detalles_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar detalles de clasificación: {str(e)}", "error")
        template_data['error'] = str(e)
        # Renderizar la plantilla correcta incluso en caso de error general
        return render_template('detalles_clasificacion.html', **template_data)
