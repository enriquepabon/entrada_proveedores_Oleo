# app/blueprints/clasificacion/views.py
# Standard Library Imports
import base64
import fnmatch
import glob
import json
import logging
import os
import random
import re
import shutil
import sqlite3
import time
import traceback
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
import copy

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
from . import bp  # Importar el Blueprint local
from .helpers import ( # Importar funciones auxiliares necesarias
    get_utils_instance, es_archivo_imagen, get_clasificacion_by_codigo_guia,
    generate_annotated_image # Ajustar según necesidad
)
# Importar desde app.utils y raíz
from app.utils.common import CommonUtils as Utils, format_datetime_filter, UTC, BOGOTA_TZ, get_db_connection, get_utc_timestamp_str
import db_operations
import db_utils
# Importar login_required
from flask_login import login_required

# Configurar logger
logger = logging.getLogger(__name__)

# --- Rutas de Vistas Movidas ---

@bp.route('/<codigo>')
@login_required # Añadir protección
def clasificacion(codigo):
    """
    Vista principal para la clasificación de racimos
    """
    try:
        logger.info(f"Inicio función clasificacion para: {codigo}")

        peso_bruto_session = session.get('peso_bruto') # Puede ser None
        logger.info(f"Peso bruto en sesión: {peso_bruto_session}")

        codigo_guia = codigo
        codigo_guia_json = codigo # Mantener ambos por ahora

        # Lógica para encontrar código completo si se pasa solo base
        if '_' not in codigo and len(codigo) <= 8:
            logger.warning(f"Formato de código posiblemente incompleto: {codigo}")
            guias_folder = current_app.config.get('GUIAS_FOLDER', os.path.join(current_app.static_folder, 'guias'))
            guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo}_*.html'))
            if not guias_files:
                json_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo}_*.json'))
                if json_files: guias_files = json_files # Usar JSON si no hay HTML

            if guias_files:
                guias_files.sort(key=os.path.getmtime, reverse=True)
                latest_guia_file = os.path.basename(guias_files[0])
                # Extraer código guía del nombre, manejando .html o .json
                codigo_guia_completo = Path(latest_guia_file).stem.replace('guia_', '', 1)
                logger.info(f"Código guía completo encontrado: {codigo_guia_completo}")
                codigo_guia = codigo_guia_completo # Actualizar código a usar
            else:
                 logger.warning(f"No se encontraron archivos para completar el código base: {codigo}")
                 # Considerar devolver error si el código es crucial
                 # return render_template('error.html', message="Formato de guía inválido"), 400

        codigo_guia_completo = codigo_guia # Usar código guía (completo o no)

        reclasificar = request.args.get('reclasificar', 'false').lower() == 'true'
        logger.info(f"Parámetro reclasificar: {reclasificar}")

        # --- Verificar si ya existe clasificación (DB primero) ---
        clasificacion_db = get_clasificacion_by_codigo_guia(codigo_guia_completo)
        clasificacion_existe = bool(clasificacion_db)
        logger.info(f"Verificación de clasificación en DB: existe = {clasificacion_existe}, reclasificar = {reclasificar}")

        # Lógica de redirección si ya existe y no se fuerza reclasificación
        referrer = request.referrer or ""
        desde_guia_centralizada = 'guia-centralizada' in referrer

        if clasificacion_existe and not reclasificar and not desde_guia_centralizada:
            logger.info(f"Clasificación ya existe en DB para {codigo_guia_completo}. Redirigiendo a resultados.")
            return redirect(url_for('.ver_resultados_clasificacion', url_guia=codigo_guia_completo))
        elif clasificacion_existe:
             logger.info(f"Clasificación existe, pero se procederá (reclasificar={reclasificar}, desde_central={desde_guia_centralizada})")

        # Obtener datos generales de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia_completo)

        if not datos_guia:
             logger.error(f"No se encontraron datos generales (Utils) para la guía: {codigo_guia_completo}")
             # Intentar cargar desde DB entry como fallback
             try:
                 datos_guia = db_utils.get_entry_record_by_guide_code(codigo_guia_completo)
                 if datos_guia: logger.info("Datos de guía recuperados desde entry_records.")
                 else: raise ValueError("No encontrado en entry_records tampoco")
             except Exception as e:
                 logger.error(f"Fallo al obtener datos de guía incluso desde entry_records: {e}")
                 flash(f"No se pudieron cargar los datos para la guía {codigo_guia_completo}", "danger")
                 return redirect(url_for('misc.dashboard')) # O a una página de error

        logger.info(f"Datos de guía para plantilla: {json.dumps(datos_guia)}")

        # Verificar si el pesaje está completado (requerido para clasificar)
        # Usar get_estado_guia podría ser más robusto aquí
        tiene_peso_bruto = datos_guia.get('peso_bruto') is not None and datos_guia.get('peso_bruto') != 'Pendiente'
        if not tiene_peso_bruto:
            flash("Necesitas completar el pesaje bruto antes de clasificar.", "warning")
            try:
                 return redirect(url_for('pesaje.pesaje_inicial', codigo=codigo_guia_completo))
            except:
                 flash("Error encontrando ruta de pesaje.", "error")
                 return redirect(url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia_completo))


        # Preparar datos finales para la plantilla
        template_data = {
            'codigo_guia': codigo_guia_completo,
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'N/A'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto'),
            'cantidad_racimos': datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'N/A'),
            'en_reclasificacion': reclasificar,
            'tipo_pesaje': datos_guia.get('tipo_pesaje', 'N/A'),
            'fecha_pesaje': format_datetime_filter(datos_guia.get('timestamp_pesaje_utc'), '%d/%m/%Y'), # Usar formateador
            'hora_pesaje': format_datetime_filter(datos_guia.get('timestamp_pesaje_utc'), '%H:%M:%S'), # Usar formateador
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', 'N/A')
        }

        logger.info(f"Renderizando plantilla clasificacion_form.html con datos: {template_data}")
        return render_template('clasificacion/clasificacion_form.html', **template_data)

    except Exception as e:
        logger.error(f"Error GRANDE al mostrar vista de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error inesperado al cargar la página de clasificación: {str(e)}", "danger")
        # Redirigir a una página segura
        return redirect(url_for('misc.dashboard'))


@bp.route('/prueba-clasificacion/<codigo>')
@login_required # Añadir protección
def prueba_clasificacion(codigo):
    """
    Endpoint de prueba para verificar datos disponibles para clasificación.
    """
    try:
        logger.info(f"Prueba de clasificación para código: {codigo}")
        # Usar get_utils_instance y get_datos_guia para obtener datos
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo) # Probar con código original o completo

        if not datos_guia:
            # Intentar con DB si falla utils
            try:
                 datos_guia = db_utils.get_entry_record_by_guide_code(codigo)
            except: pass # Ignorar error de DB aquí

        if not datos_guia:
            return jsonify({"error": f"Guía {codigo} no encontrada"}), 404

        # Devolver datos relevantes
        return jsonify({
            "datos_guia_completos": datos_guia,
            "nombre_proveedor": datos_guia.get('nombre_proveedor', 'N/A'),
            "codigo_proveedor": datos_guia.get('codigo_proveedor', 'N/A'),
            "cantidad_racimos": datos_guia.get('cantidad_racimos', 'N/A'),
            "peso_bruto": datos_guia.get('peso_bruto'),
            "estado_actual": datos_guia.get('estado_actual'),
        })

    except Exception as e:
        logger.error(f"Error en prueba de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

@bp.route('/clasificaciones')
@login_required # Añadir protección
def listar_clasificaciones():
    # Redirigir a la nueva ruta filtrada
    return redirect(url_for('.listar_clasificaciones_filtradas'))

@bp.route('/clasificaciones/lista')
@login_required # Añadir protección
def listar_clasificaciones_filtradas():
    """Muestra la lista de clasificaciones, leyendo desde la base de datos."""
    try:
        # Obtener parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        estado = request.args.get('estado', '') # Puede ser 'pendiente', 'en_proceso', 'completado'

        # Preparar filtros para la consulta DB
        filtros_db = {}
        if fecha_desde: filtros_db['fecha_desde'] = fecha_desde
        if fecha_hasta: filtros_db['fecha_hasta'] = fecha_hasta
        if codigo_proveedor: filtros_db['codigo_proveedor'] = codigo_proveedor
        if nombre_proveedor: filtros_db['nombre_proveedor'] = nombre_proveedor
        # El filtro de 'estado' se aplica después, ya que puede depender de la lógica

        logger.info(f"Obteniendo clasificaciones de DB con filtros: {filtros_db}")
        # Usar db_operations.get_clasificaciones que ya maneja filtros y orden
        clasificaciones_db = db_operations.get_clasificaciones(filtros=filtros_db)

        # Procesar resultados para la plantilla
        clasificaciones_procesadas = []
        for record in clasificaciones_db:
            item = {
                'codigo_guia': record.get('codigo_guia'),
                'nombre_proveedor': record.get('nombre_proveedor', 'N/A'),
                'codigo_proveedor': record.get('codigo_proveedor', 'N/A'),
                'fecha_clasificacion': format_datetime_filter(record.get('timestamp_clasificacion_utc'), '%d/%m/%Y'),
                'hora_clasificacion': format_datetime_filter(record.get('timestamp_clasificacion_utc'), '%H:%M:%S'),
                'cantidad_racimos': record.get('total_racimos_detectados', 'N/A'),
                'estado_db': record.get('estado', 'pendiente'), # Estado crudo de DB
                'manual_completado': bool(record.get('clasificacion_manual_json') and record.get('clasificacion_manual_json') != '{}'),
                'automatica_completado': bool(record.get('clasificacion_automatica_json') and record.get('clasificacion_automatica_json') != '{}'),
            }
            # Normalizar estado para UI (similar a como se hacía antes)
            if item['estado_db'] in ['completado', 'completado_sin_deteccion', 'error_procesamiento', 'error_config', 'error_hilo']:
                 item['estado'] = 'completado'
            elif item['estado_db'] == 'procesando':
                 item['estado'] = 'en_proceso'
            else: # Pendiente, inicial, etc.
                 item['estado'] = 'pendiente'

            # Aplicar filtro de estado si se especificó
            if estado and item['estado'] != estado:
                continue

            clasificaciones_procesadas.append(item)

        logger.info(f"Total de {len(clasificaciones_procesadas)} clasificaciones para mostrar.")

        return render_template('clasificacion/clasificaciones_lista.html',
                               clasificaciones=clasificaciones_procesadas,
                               filtros={ # Pasar filtros activos a la plantilla
                                   'fecha_desde': fecha_desde,
                                   'fecha_hasta': fecha_hasta,
                                   'codigo_proveedor': codigo_proveedor,
                                   'nombre_proveedor': nombre_proveedor,
                                   'estado': estado
                               })
    except Exception as e:
        logger.error(f"Error listando clasificaciones: {str(e)}")
        logger.error(traceback.format_exc())
        # Considerar mostrar un mensaje de error más específico en la plantilla
        return render_template('error.html', mensaje=f"Error al listar clasificaciones: {str(e)}")


@bp.route('/ver_resultados_clasificacion/<path:url_guia>')
@login_required # Añadir protección
def ver_resultados_clasificacion(url_guia):
    """Muestra los resultados consolidados de la clasificación."""
    logger.info(f"Accediendo a resultados de clasificación para: {url_guia}")
    start_time = time.time()

    # Usar helper para obtener la instancia de Utils
    utils = get_utils_instance() # Usar helper
    datos_guia = utils.get_datos_guia(url_guia) # Obtener datos generales

    # Obtener datos específicos de clasificación de la DB usando el helper
    datos_clasificacion_db = get_clasificacion_by_codigo_guia(url_guia) # Usar helper

    if not datos_guia and not datos_clasificacion_db:
        flash(f"No se encontraron datos generales ni de clasificación para la guía {url_guia}", 'error')
        return redirect(url_for('.listar_clasificaciones_filtradas'))

    # Combinar datos (priorizando DB de clasificación si existe)
    datos_combinados = datos_guia if datos_guia else {}
    if datos_clasificacion_db:
        # Guardar una copia del estado original antes de actualizar
        estado_original_guia = datos_combinados.get('estado')
        datos_combinados.update(datos_clasificacion_db) # Sobrescribe si hay claves iguales
        # Restaurar estado original si no vino de la DB de clasificación
        if 'estado' not in datos_clasificacion_db and estado_original_guia:
            datos_combinados['estado'] = estado_original_guia

        # Asegurar que clasificacion_manual/automatica sean dicts si están en DB
        if 'clasificacion_manual' not in datos_combinados or not isinstance(datos_combinados['clasificacion_manual'], dict):
            datos_combinados['clasificacion_manual'] = {}
        if 'clasificacion_automatica' not in datos_combinados or not isinstance(datos_combinados['clasificacion_automatica'], dict):
             datos_combinados['clasificacion_automatica'] = {}


    codigo_guia = datos_combinados.get('codigo_guia', url_guia)
    codigo_proveedor = datos_combinados.get('codigo_proveedor', 'N/A')
    nombre_proveedor = datos_combinados.get('nombre_proveedor', 'N/A')
    peso_bruto = datos_combinados.get('peso_bruto', 'N/A')
    cantidad_racimos = datos_combinados.get('cantidad_racimos') or datos_combinados.get('racimos', 'N/A')

    # Timestamp de clasificación (prioridad: DB > Guía general)
    timestamp_clasificacion_utc_str = datos_combinados.get('timestamp_clasificacion_utc')
    fecha_clasificacion = format_datetime_filter(timestamp_clasificacion_utc_str, '%d/%m/%Y') if timestamp_clasificacion_utc_str else 'N/A'
    hora_clasificacion = format_datetime_filter(timestamp_clasificacion_utc_str, '%H:%M:%S') if timestamp_clasificacion_utc_str else 'N/A'

    # Clasificación Manual (Prioridad: DB > Guía general)
    clasificacion_manual = datos_combinados.get('clasificacion_manual', {}) # Ya debería ser dict

    # Clasificación Automática (Consolidada) (Solo de DB)
    # Usar 'clasificacion_automatica' como fuente principal ahora
    clasificacion_automatica_consolidada = datos_combinados.get('clasificacion_automatica', {}) # Ya debería ser dict
    total_racimos_detectados_db = datos_combinados.get('total_racimos_detectados') # Puede ser None

    # Verificar si hay detalles por foto disponibles (se buscará en el JSON)
    hay_detalles_por_foto_json = False
    total_racimos_detectados_json = 0
    json_path_abs = None

    try:
        # Buscar el JSON de detalles
        guia_fotos_dir_rel = os.path.join('uploads', 'fotos', codigo_guia)
        guia_fotos_dir_abs = os.path.join(current_app.static_folder, guia_fotos_dir_rel)
        json_filename_detalles = f'clasificacion_auto_detalles_{codigo_guia}.json'
        json_path_detalles_abs = os.path.join(guia_fotos_dir_abs, json_filename_detalles)

        json_filename_simple = f'clasificacion_{codigo_guia}.json'
        # Ruta simple dentro de la carpeta 'fotos'
        json_path_simple_fotos_abs = os.path.join(guia_fotos_dir_abs, json_filename_simple)
        # Ruta simple dentro de la carpeta 'uploads' (donde se está guardando)
        guia_uploads_dir_rel = os.path.join('uploads', codigo_guia)
        guia_uploads_dir_abs = os.path.join(current_app.static_folder, guia_uploads_dir_rel)
        json_path_simple_uploads_abs = os.path.join(guia_uploads_dir_abs, json_filename_simple)
        # Ruta simple en la carpeta general 'clasificaciones'
        json_path_simple_general_abs = os.path.join(current_app.config.get('CLASIFICACIONES_FOLDER', os.path.join(current_app.static_folder, 'clasificaciones')), json_filename_simple)

        json_path_abs = None # Inicializar
        if os.path.exists(json_path_detalles_abs):
            json_path_abs = json_path_detalles_abs
            logger.info(f"Archivo JSON de DETALLES encontrado en: {json_path_abs}")
        elif os.path.exists(json_path_simple_fotos_abs):
            json_path_abs = json_path_simple_fotos_abs
            logger.info(f"Archivo JSON simple encontrado en carpeta FOTOS: {json_path_abs}. Verificando...")
        elif os.path.exists(json_path_simple_uploads_abs):
            json_path_abs = json_path_simple_uploads_abs
            logger.info(f"Archivo JSON simple encontrado en carpeta UPLOADS: {json_path_abs}. Verificando...")
        elif os.path.exists(json_path_simple_general_abs):
            json_path_abs = json_path_simple_general_abs
            logger.info(f"Archivo JSON simple encontrado en carpeta general CLASIFICACIONES: {json_path_abs}. Verificando...")
        else:
            logger.warning(f"No se encontró archivo JSON de clasificación en rutas esperadas para {codigo_guia}.")

        if json_path_abs:
             with open(json_path_abs, 'r', encoding='utf-8') as f:
                 json_data = json.load(f)

             imagenes_procesadas = json_data.get('imagenes_procesadas', [])
             if isinstance(imagenes_procesadas, list) and len(imagenes_procesadas) > 0:
                  logger.info(f"Verificando {len(imagenes_procesadas)} imágenes procesadas del JSON...")
                  for img in imagenes_procesadas:
                       racimos_img_val = img.get('num_racimos_detectados', img.get('total_racimos_imagen'))
                       try:
                            racimos_img = int(racimos_img_val) if racimos_img_val is not None else 0
                            if racimos_img > 0:
                                hay_detalles_por_foto_json = True
                                total_racimos_detectados_json += racimos_img
                       except (ValueError, TypeError):
                            continue # Ignorar si no es número
                  logger.info(f"Verificación JSON: hay_detalles={hay_detalles_por_foto_json}, total_json={total_racimos_detectados_json}")
             else:
                  logger.info("JSON no contiene 'imagenes_procesadas' o está vacío.")

    except Exception as json_err:
        logger.error(f"Error leyendo o procesando JSON para detalles: {json_err}")

    # Decisión final sobre el botón "Ver Detalles"
    db_check_passed = total_racimos_detectados_db is not None and total_racimos_detectados_db > 0
    db_estado_indica_proceso = datos_combinados.get('estado') in ['completado', 'completado_sin_deteccion', 'error_procesamiento']
    hay_detalles_por_foto = hay_detalles_por_foto_json or (db_check_passed and db_estado_indica_proceso)
    logger.info(f"Determinación final 'hay_detalles_por_foto': {hay_detalles_por_foto} (JSON: {hay_detalles_por_foto_json}, DB Check: {db_check_passed}, DB Estado OK: {db_estado_indica_proceso})")

    # Decidir total a mostrar (Prioridad: DB si existe, sino JSON si tiene detalles, sino 0)
    total_racimos_a_mostrar = total_racimos_detectados_db if total_racimos_detectados_db is not None else (total_racimos_detectados_json if hay_detalles_por_foto_json else 0)
    logger.info(f"Total de racimos que se mostrará: {total_racimos_a_mostrar}")


    # Calcular porcentajes para la clasificación manual
    clasificacion_manual_con_porcentajes = {}
    total_manual = sum(v for v in clasificacion_manual.values() if isinstance(v, (int, float)))
    if total_manual > 0:
        for cat, cant in clasificacion_manual.items():
            if isinstance(cant, (int, float)):
                porcentaje = round((cant / total_manual) * 100, 1) if total_manual > 0 else 0.0
                clasificacion_manual_con_porcentajes[cat] = {'cantidad': cant, 'porcentaje': porcentaje}
            else: # Mantener la clave pero con 0 si el valor no era numérico
                 clasificacion_manual_con_porcentajes[cat] = {'cantidad': 0, 'porcentaje': 0.0}


    end_time = time.time()
    logger.info(f"Tiempo para cargar resultados de {url_guia}: {end_time - start_time:.2f} segundos")

    # Renderizar la plantilla con los datos combinados
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
                           clasificacion_automatica_consolidada=clasificacion_automatica_consolidada,
                           total_racimos_detectados=total_racimos_a_mostrar,
                           hay_detalles_por_foto=hay_detalles_por_foto,
                           tiene_pesaje_neto=bool(datos_combinados.get('peso_neto'))
                           )

@bp.route('/procesar_clasificacion_manual/<path:url_guia>', methods=['GET', 'POST'])
@login_required # Añadir protección
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

@bp.route('/generar_pdf_clasificacion/<codigo_guia>')
@login_required # Añadir protección
def generar_pdf_clasificacion(codigo_guia):
    """
    Genera un PDF con los resultados de la clasificación.
    """
    try:
        logger.info(f"Generando PDF de clasificación para guía: {codigo_guia}")
            
        # Obtener datos de clasificación
        # from db_operations import get_clasificacion_by_codigo_guia # Comentado, usar el import de processing
        
        clasificacion_data = get_clasificacion_by_codigo_guia(codigo_guia)
        
        if not clasificacion_data:
            logger.warning(f"Clasificación no encontrada en la base de datos para código: {codigo_guia}")
            
            # Intentar como fallback buscar en el sistema de archivos (legado)
            # NOTA: Considerar si este fallback aún es necesario o si db_operations es la única fuente
            clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones') # Asegurarse que 'clasificaciones' es el dir correcto
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                flash("No se encontró la clasificación para la guía especificada.", "error")
                # Redirigir a una ruta válida, ¿quizás la lista de clasificaciones?
                return redirect(url_for('clasificacion.listar_clasificaciones_filtradas')) 
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('clasificacion.listar_clasificaciones_filtradas')) # O a donde sea apropiado
        
        # Procesar clasificaciones si están en formato JSON
        # Asegurarse que las claves 'clasificacion_manual' y 'clasificacion_automatica' existen o usar .get()
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
        
        # Preparar datos para la plantilla
        codigo_proveedor = clasificacion_data.get('codigo_proveedor', datos_guia.get('codigo_proveedor', 'N/A'))
        nombre_proveedor = clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre_proveedor', 'N/A')) # Corregido acceso a nombre_proveedor
        
        # Generar QR
        # Asegurarse que QR_FOLDER está configurado en app.config
        qr_folder = current_app.config.get('QR_FOLDER', os.path.join(current_app.static_folder, 'qr')) 
        qr_filename = f"qr_clasificacion_{codigo_guia}.png"
        qr_path = os.path.join(qr_folder, qr_filename)
        # Usar la ruta correcta para la vista centralizada si cambió
        qr_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True) 
        
        utils_instance.generar_qr(qr_url, qr_path)
        
        # Obtener fotos de clasificación
        fotos = []
        rutas_fotos_raw = clasificacion_data.get('fotos', [])
        if isinstance(rutas_fotos_raw, list):
            for foto_path in rutas_fotos_raw:
                if foto_path: # Ignorar rutas vacías
                    # Convertir a ruta relativa si es una ruta absoluta DENTRO de static
                    if os.path.isabs(foto_path) and foto_path.startswith(current_app.static_folder):
                        rel_path = os.path.relpath(foto_path, current_app.static_folder)
                        # Asegurarse de que la ruta relativa use separadores '/' para URL
                        fotos.append(rel_path.replace(os.sep, '/'))
                    # Si ya es relativa (o absoluta fuera de static, aunque eso sería raro), usarla tal cual
                    # y asegurar separadores '/' 
                    elif not os.path.isabs(foto_path):
                         fotos.append(foto_path.replace(os.sep, '/'))
                    # else: Manejar rutas absolutas fuera de static si es necesario
                    
        # Preparar la plantilla PDF
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            # Usar timestamps UTC si están disponibles para consistencia
            'fecha_clasificacion': clasificacion_data.get('timestamp_clasificacion_utc', datos_guia.get('timestamp_registro_utc', '')) or clasificacion_data.get('fecha_registro', ''), 
            'hora_clasificacion': '', # La hora se formateará desde el timestamp en la plantilla
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': clasificacion_automatica,
            # Generar URL para el QR relativo a static
            'qr_code': url_for('static', filename=os.path.join(os.path.basename(qr_folder), qr_filename).replace(os.sep, '/')), 
            'fotos': fotos,
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'cantidad_racimos': datos_guia.get('racimos', 'N/A'),
            'transportador': datos_guia.get('transportador', 'N/A'),
            'placa': datos_guia.get('placa', 'N/A'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', 'N/A'),
            'for_pdf': True
        }
        
        # Generar HTML renderizado (asegurarse que la plantilla existe)
        html = render_template('clasificacion/clasificacion_documento.html', **template_data)
        
        # Crear PDF a partir del HTML
        # Asegurarse que PDF_FOLDER está en app.config
        pdf_folder = current_app.config.get('PDF_FOLDER', os.path.join(current_app.static_folder, 'pdfs'))
        pdf_filename = f"clasificacion_{codigo_guia}.pdf"
        pdf_path = os.path.join(pdf_folder, pdf_filename)
        
        # Importar CSS para el PDF (asegurarse que las rutas son correctas)
        css_paths = [
            os.path.join(current_app.static_folder, 'css', 'bootstrap.min.css'),
            os.path.join(current_app.static_folder, 'css', 'documento_styles.css')
        ]
        
        # Generar PDF usando utils (asegurarse que generar_pdf_desde_html existe en Utils)
        pdf_generated = utils_instance.generar_pdf_desde_html(html, pdf_path, css_paths=css_paths)
        
        if not pdf_generated:
             raise Exception("La función generar_pdf_desde_html reportó un error.")
             
        # Devolver el PDF como descarga
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)
        
    except Exception as e:
        # Usar logger aquí también
        logger.error(f"Error generando PDF de clasificación: {str(e)}", exc_info=True) # exc_info=True para traceback
        flash(f"Error generando PDF: {str(e)}", "error")
        # Redirigir a la vista de resultados donde ocurrió el error
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))

@bp.route('/print_view_clasificacion/<codigo_guia>')
@login_required # Añadir protección
def print_view_clasificacion(codigo_guia):
    """
    Muestra una vista para impresión de los resultados de clasificación.
    """
    try:
        logger.info(f"Mostrando vista de impresión para clasificación: {codigo_guia}")
        
        # Obtener datos de clasificación
        # from db_operations import get_clasificacion_by_codigo_guia # Ya importado desde processing
        
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
                return redirect(url_for('.listar_clasificaciones_filtradas')) # Usar . para endpoint local
        
        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('.listar_clasificaciones_filtradas')) # Usar . para endpoint local
        
        # Procesar clasificaciones si están en formato JSON
        clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
        clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
        
        # Preparar datos para la plantilla
        codigo_proveedor = clasificacion_data.get('codigo_proveedor', datos_guia.get('codigo_proveedor', 'N/A'))
        nombre_proveedor = clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre_proveedor', 'N/A'))
        
        # Obtener fotos de clasificación
        fotos = []
        rutas_fotos_raw = clasificacion_data.get('fotos', [])
        if isinstance(rutas_fotos_raw, list):
            for foto_path in rutas_fotos_raw:
                if foto_path: # Ignorar rutas vacías
                    # Convertir a ruta relativa si es una ruta absoluta DENTRO de static
                    if os.path.isabs(foto_path) and foto_path.startswith(current_app.static_folder):
                        rel_path = os.path.relpath(foto_path, current_app.static_folder)
                        fotos.append(rel_path.replace(os.sep, '/'))
                    # Si ya es relativa, usarla tal cual
                    elif not os.path.isabs(foto_path):
                        fotos.append(foto_path.replace(os.sep, '/'))
                    
        # Preparar la plantilla
        template_data = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'fecha_clasificacion': clasificacion_data.get('timestamp_clasificacion_utc', datos_guia.get('timestamp_registro_utc', '')) or clasificacion_data.get('fecha_registro', ''),
            'hora_clasificacion': '', # Formateado en plantilla
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': clasificacion_automatica,
            'fotos': fotos,
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'cantidad_racimos': datos_guia.get('racimos', 'N/A'),
            'transportador': datos_guia.get('transportador', 'N/A'),
            'placa': datos_guia.get('placa', 'N/A'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', 'N/A'),
            'for_print': True
        }
        
        return render_template('clasificacion/clasificacion_documento.html', **template_data)
        
    except Exception as e:
        logger.error(f"Error mostrando vista de impresión: {str(e)}", exc_info=True)
        flash(f"Error mostrando vista de impresión: {str(e)}", "error")
        return redirect(url_for('.ver_resultados_clasificacion', url_guia=codigo_guia))

# --- INICIO DE LA FUNCIÓN VER_DETALLES_CLASIFICACION ---
@bp.route('/ver_detalles_clasificacion/<path:url_guia>')
@login_required # Añadir protección
def ver_detalles_clasificacion(url_guia):
    """
    Muestra los detalles de clasificación por foto para una guía específica,
    usando el conteo de racimos pre-procesado del JSON.
    """
    # Importaciones locales dentro de la función para asegurar disponibilidad
    import time
    import os
    import json
    import traceback
    from flask import current_app, make_response, flash, render_template, url_for, request
    from app.utils.common import CommonUtils as Utils # Asegurar acceso a Utils
    import db_operations # Para guardar consolidado

    start_time = time.time()
    logger.info(f"Iniciando ver_detalles_clasificacion para {url_guia}")

    codigo_guia = url_guia
    logger.info(f"Código de guía a buscar: {codigo_guia}")

    template_data = {
        'url_guia': url_guia,
        'resultados_por_foto': [],
        'fotos_originales': [],
        'fotos_procesadas': [],
        'clasificacion_automatica_consolidada': {},
        'raw_data': {},
        'debug_info': {},
        'json_path': '',
        'tiempo_procesamiento': '',
        'datos_guia': {},
        'error': None,
        'total_racimos_acumulados': 0
    }

    try:
        # Determinar la ruta base para las fotos de esta guía
        guia_fotos_dir_rel = os.path.join('uploads', 'fotos', codigo_guia).replace("\\", "/")
        guia_fotos_dir_abs = os.path.join(current_app.static_folder, guia_fotos_dir_rel)

        # --- Lógica de búsqueda de JSON corregida (igual a ver_resultados_clasificacion) ---
        json_filename_principal = f"clasificacion_{codigo_guia}.json"
        json_filename_detalles = f'clasificacion_auto_detalles_{codigo_guia}.json'

        # Posibles rutas (orden de prioridad)
        clasificacion_path_detalles = os.path.join(guia_fotos_dir_abs, json_filename_detalles)
        clasificacion_path_simple_fotos = os.path.join(guia_fotos_dir_abs, json_filename_principal)

        guia_uploads_dir_rel = os.path.join('uploads', codigo_guia) # Ruta donde se guarda
        guia_uploads_dir_abs = os.path.join(current_app.static_folder, guia_uploads_dir_rel)
        clasificacion_path_simple_uploads = os.path.join(guia_uploads_dir_abs, json_filename_principal)

        clasificacion_path_alt = os.path.join(current_app.config.get('CLASIFICACIONES_FOLDER', os.path.join(current_app.static_folder, 'clasificaciones')), json_filename_principal)

        clasificacion_path = None # Inicializar
        if os.path.exists(clasificacion_path_detalles):
            clasificacion_path = clasificacion_path_detalles
            logger.info(f"[Detalles] Archivo de DETALLES encontrado: {clasificacion_path}")
        elif os.path.exists(clasificacion_path_simple_fotos):
             clasificacion_path = clasificacion_path_simple_fotos
             logger.info(f"[Detalles] Archivo simple encontrado en carpeta FOTOS: {clasificacion_path}")
        elif os.path.exists(clasificacion_path_simple_uploads):
            clasificacion_path = clasificacion_path_simple_uploads
            logger.info(f"[Detalles] Archivo simple encontrado en carpeta UPLOADS: {clasificacion_path}")
        elif os.path.exists(clasificacion_path_alt):
            clasificacion_path = clasificacion_path_alt
            logger.info(f"[Detalles] Archivo simple encontrado en carpeta CLASIFICACIONES: {clasificacion_path}")
        else:
            logger.error(f"[Detalles] No se encontró el archivo JSON para: {codigo_guia} en NINGUNA ruta verificada.")
            flash("No se encontró información de clasificación detallada para esta guía", "error")
            template_data['error'] = "Archivo JSON de detalles no encontrado."
            return make_response(render_template('clasificacion/detalles_clasificacion.html', **template_data))
        # --- Fin Lógica de búsqueda de JSON corregida ---

        template_data['json_path'] = clasificacion_path

        with open(clasificacion_path, 'r', encoding='utf-8') as f:
            clasificacion_data = json.load(f)
            logger.info(f"Clasificación detallada leída del archivo: {clasificacion_path}")
            template_data['raw_data'] = clasificacion_data # Para debug si es necesario
            template_data['tiempo_procesamiento'] = clasificacion_data.get('tiempo_total_procesamiento_seg', 'N/A')

            # === BLOQUE NUEVO: Guardar consolidado automático en la base de datos (si está en este JSON) ===
            consolidado = clasificacion_data.get('clasificacion_consolidada')
            if consolidado:
                try:
                    # from db_operations import store_clasificacion # Ya importado arriba
                    consolidado_json = json.dumps(consolidado, ensure_ascii=False)
                    # Solo actualizamos el campo de clasificación automática
                    clasificacion_data_db = {
                        'codigo_guia': codigo_guia,
                        'clasificacion_automatica_json': consolidado_json,
                        # Podríamos añadir total_racimos_detectados si está disponible aquí
                        'total_racimos_detectados': clasificacion_data.get('total_racimos_detectados')
                    }
                    # Filtrar Nones antes de guardar
                    clasificacion_data_db_final = {k: v for k, v in clasificacion_data_db.items() if v is not None}
                    if len(clasificacion_data_db_final) > 1: # Si hay algo más que el código_guia
                        exito = db_operations.store_clasificacion(clasificacion_data_db_final)
                        if exito:
                            logger.info(f"Consolidado automático guardado/actualizado en BD para {codigo_guia}")
                        else:
                            logger.error(f"Error al guardar consolidado automático en BD para {codigo_guia}")
                    else:
                        logger.info(f"No había datos consolidados nuevos para guardar en BD para {codigo_guia}")
                except Exception as e:
                    logger.error(f"Error inesperado guardando consolidado automático en BD: {e}")
            else:
                logger.warning(f"No se encontró 'clasificacion_consolidada' en el JSON leído para {codigo_guia}")
            # === FIN BLOQUE NUEVO ===

        # Obtener datos generales de la guía (para cabecera, etc.)
        try:
            utils = Utils(current_app)
            datos_guia = utils.get_datos_guia(url_guia)
            template_data['datos_guia'] = datos_guia if datos_guia else {}
            logger.info(f"Datos generales de guía obtenidos: {template_data['datos_guia']}")
        except Exception as e:
            logger.error(f"Error al obtener datos generales de la guía: {str(e)}")
            template_data['datos_guia'] = {}

        # Función auxiliar para generar URL segura y con logging mejorado
        def get_safe_static_url(relative_path_from_json, img_type="imagen"):
            if not relative_path_from_json:
                logger.warning(f"get_safe_static_url: No se proporcionó ruta relativa para {img_type}.")
                return None
            
            clean_rel_path = relative_path_from_json.replace('\\', '/')
            # Eliminar posible / inicial para url_for
            if clean_rel_path.startswith('/'):
                clean_rel_path = clean_rel_path[1:]
                
            # Comprobar si el archivo físico existe
            physical_path = os.path.join(current_app.static_folder, clean_rel_path)
            
            if os.path.exists(physical_path):
                try:
                    # Generar URL usando url_for
                    file_url = url_for('static', filename=clean_rel_path)
                    logger.info(f"get_safe_static_url: OK - Archivo '{physical_path}' existe. URL generada: {file_url}")
                    # Añadir timestamp como query param para evitar caché del navegador si la imagen cambia
                    # file_url += f"?v={int(time.time())}" # <-- Eliminado temporalmente
                    return file_url
                except Exception as url_err:
                    logger.error(f"get_safe_static_url: Error generando URL estática para '{clean_rel_path}': {url_err}")
                    return None
            else:
                logger.warning(f"get_safe_static_url: Archivo estático NO encontrado en disco: '{physical_path}' (ruta JSON: '{relative_path_from_json}')")
                return None

        # Procesar la sección 'imagenes_procesadas' del JSON
        resultados_por_foto_procesados = []
        imagenes_procesadas_json = clasificacion_data.get('imagenes_procesadas', [])
        total_racimos_potholes_acumulados = 0 # Inicializar acumulador aquí

        if isinstance(imagenes_procesadas_json, list):
            logger.info(f"Procesando {len(imagenes_procesadas_json)} entradas de 'imagenes_procesadas' del JSON.")
            for img_data in imagenes_procesadas_json:
                if not isinstance(img_data, dict):
                    logger.warning(f"Elemento no esperado en 'imagenes_procesadas': {img_data}")
                    continue

                foto_numero = img_data.get('numero', img_data.get('indice', '?'))
                imagen_original_url = get_safe_static_url(img_data.get('imagen_original'), f"original (foto {foto_numero})")
                imagen_annotated_url = get_safe_static_url(img_data.get('ruta_anotada', img_data.get('imagen_annotated')), f"anotada (foto {foto_numero})")
                imagen_clasificada_url = get_safe_static_url(img_data.get('ruta_clasificada_rf', img_data.get('imagen_clasificada')), f"clasificada RF (foto {foto_numero})")

                # --- Aplicar strip() para eliminar posibles espacios --- 
                imagen_original_url = imagen_original_url.strip() if imagen_original_url else None
                imagen_annotated_url = imagen_annotated_url.strip() if imagen_annotated_url else None
                imagen_clasificada_url = imagen_clasificada_url.strip() if imagen_clasificada_url else None

                # --- Log Detallado de URLs antes de crear el contexto ---
                logger.info(f"[VER_DETALLES DEBUG Foto {foto_numero}] URL Original: {imagen_original_url}")
                logger.info(f"[VER_DETALLES DEBUG Foto {foto_numero}] URL Anotada (_label_viz): {imagen_annotated_url}")
                logger.info(f"[VER_DETALLES DEBUG Foto {foto_numero}] URL Clasificada (_labeled_rf): {imagen_clasificada_url}")
                # --- Fin Log Detallado ---

                # --- Obtener el conteo de racimos pre-procesado ---
                potholes_count_preprocessed = img_data.get('roboflow_potholes_count')
                total_racimos_foto_base = 0 # Valor por defecto
                try:
                    if potholes_count_preprocessed is not None:
                        total_racimos_foto_base = int(potholes_count_preprocessed)
                        logger.info(f"[Detalles Foto {foto_numero}] Usando valor PRE-PROCESADO 'roboflow_potholes_count': {total_racimos_foto_base}")
                    else:
                         logger.warning(f"[Detalles Foto {foto_numero}] 'roboflow_potholes_count' NO encontrado o es None en JSON. Usando 0.")
                except (ValueError, TypeError) as e:
                    logger.warning(f"[Detalles Foto {foto_numero}] Error convirtiendo 'roboflow_potholes_count' ({potholes_count_preprocessed}) a entero: {e}. Usando 0.")
                    total_racimos_foto_base = 0
                # --- Fin obtener conteo pre-procesado ---

                total_racimos_potholes_acumulados += total_racimos_foto_base # Acumular

                foto_context = {
                    'numero': foto_numero,
                    'total_racimos': total_racimos_foto_base, # Pasar el valor correctamente parseado
                    'imagen_original': imagen_original_url,
                    'imagen_annotated': imagen_annotated_url,
                    'imagen_clasificada': imagen_clasificada_url,
                    'conteo_categorias': img_data.get('conteo_categorias', {}),
                    'detecciones': img_data.get('detecciones', []), # Para mostrar BBOX si es necesario
                    'roboflow_potholes_count_original': potholes_count_preprocessed # Mantener el valor original leído del JSON por si se necesita mostrar
                }
                resultados_por_foto_procesados.append(foto_context)

            template_data['fotos_procesadas'] = resultados_por_foto_procesados
            logger.info(f"Se procesaron {len(resultados_por_foto_procesados)} fotos para la plantilla.")
        else:
            logger.warning(f"'imagenes_procesadas' no es una lista válida en el JSON. Tipo: {type(imagenes_procesadas_json)}")
            template_data['error'] = "El archivo JSON no contiene detalles válidos por imagen."

        # Actualizar el total acumulado en template_data
        template_data['total_racimos_acumulados'] = total_racimos_potholes_acumulados
        logger.info(f"Total racimos acumulados (basado en potholes_count pre-procesados): {total_racimos_potholes_acumulados}")

        end_time = time.time()
        render_duration = round(end_time - start_time, 2)
        template_data['debug_info'] = {'render_time': f"{render_duration}s"} # Sobrescribir debug info

        logger.info(f"Renderizando plantilla 'clasificacion/detalles_clasificacion.html'. Tiempo: {render_duration}s")

        # Renderizar la plantilla de detalles (asegurarse que existe)
        response = make_response(render_template('clasificacion/detalles_clasificacion.html', **template_data))
        # Añadir cabeceras para evitar caché
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    except FileNotFoundError as e:
        logger.error(f"Archivo no encontrado en ver_detalles_clasificacion: {e}")
        flash("No se encontró el archivo de clasificación detallada para esta guía", "error")
        template_data['error'] = f"Error: Archivo no encontrado ({e})."
        return make_response(render_template('clasificacion/detalles_clasificacion.html', **template_data))
    except json.JSONDecodeError as e:
        json_path_error = template_data.get('json_path', 'Desconocido')
        logger.error(f"Error decodificando JSON ({json_path_error}): {e}", exc_info=True)
        flash("Error al leer los detalles. El archivo JSON podría estar corrupto.", "error")
        template_data['error'] = f"Error leyendo JSON: {e}. Archivo: {json_path_error}"
        return make_response(render_template('clasificacion/detalles_clasificacion.html', **template_data))
    except Exception as e:
        logger.error(f"Error inesperado en ver_detalles_clasificacion para {url_guia}: {e}", exc_info=True)
        flash("Ocurrió un error inesperado al mostrar los detalles.", "error")
        template_data['error'] = f"Error inesperado: {e}"
        return make_response(render_template('clasificacion/detalles_clasificacion.html', **template_data))
# --- FIN DE LA FUNCIÓN VER_DETALLES_CLASIFICACION ---

# --- INICIO DE LA FUNCIÓN TEST_ANNOTATED_IMAGE ---
@bp.route('/test_annotated_image/<path:url_guia>')
@login_required # Añadir protección
def test_annotated_image(url_guia):
    """
    Ruta para probar la generación de imágenes anotadas con detecciones simuladas
    """
    # Importaciones locales necesarias
    import random
    import os
    from flask import flash, redirect, url_for, current_app, render_template
    # Asegurarse que generate_annotated_image está importada (asumiendo desde helpers)
    from .helpers import generate_annotated_image 
    
    try:
        logger.info(f"Iniciando test_annotated_image para: {url_guia}")
        # Obtener lista de imágenes disponibles para la guía
        # Ajustar ruta si es necesario (ej: si las fotos están en static/uploads/fotos/...)
        photos_dir_rel = os.path.join('uploads', 'fotos', url_guia).replace('\\','/')
        photos_dir = os.path.join(current_app.static_folder, photos_dir_rel)
        logger.info(f"Buscando fotos en: {photos_dir}")
        
        if not os.path.exists(photos_dir):
            logger.warning(f"Directorio de fotos no encontrado: {photos_dir}")
            flash("No se encontraron imágenes para esta guía", "warning")
            return redirect(url_for('.ver_resultados_clasificacion', url_guia=url_guia)) # Usar . para endpoint local
        
        # Buscar archivos de imagen en el directorio (excluyendo las ya anotadas/redimensionadas)
        image_files = [
            os.path.join(photos_dir, f) for f in os.listdir(photos_dir) 
            if f.lower().endswith(('.jpg', '.jpeg', '.png')) and 
               not f.lower().endswith(('_annotated.jpg', '_resized.jpg', '_labeled_rf.jpg'))
        ]
        logger.info(f"Imágenes encontradas: {image_files}")
        
        if not image_files:
            logger.warning("No se encontraron imágenes originales elegibles.")
            flash("No se encontraron imágenes originales elegibles para anotar en esta guía", "warning")
            return redirect(url_for('.ver_resultados_clasificacion', url_guia=url_guia)) # Usar . para endpoint local
        
        # Seleccionar una imagen aleatoria para la prueba
        image_path = random.choice(image_files)
        logger.info(f"Imagen seleccionada para prueba: {image_path}")
        
        # Crear detecciones de prueba simuladas
        detections = []
        num_detections = random.randint(5, 15)  # Entre 5 y 15 detecciones aleatorias
        
        for _ in range(num_detections):
            class_type = random.choice(['verde', 'maduro', 'sobremaduro', 'danio_corona', 'pendunculo_largo', 'podrido'])
            
            detection = {
                'x': random.uniform(0.1, 0.9),        # Posición X normalizada (centro)
                'y': random.uniform(0.1, 0.9),        # Posición Y normalizada (centro)
                'width': random.uniform(0.05, 0.3),   # Ancho normalizado
                'height': random.uniform(0.05, 0.3),  # Alto normalizado
                'class': class_type,                  # Clase de detección
                'confidence': random.uniform(0.7, 0.99)  # Confianza entre 70% y 99%
            }
            detections.append(detection)
        logger.info(f"Generadas {len(detections)} detecciones simuladas.")
        
        # Preparar ruta para la imagen anotada de prueba
        output_name = f"test_annotated_{os.path.basename(image_path)}"
        output_path = os.path.join(photos_dir, output_name)
        
        # Generar la imagen anotada utilizando la función importada
        result_path = generate_annotated_image(image_path, detections, output_path)
        
        if result_path:
            logger.info(f"Imagen anotada de prueba generada en: {result_path}")
            # Convertir rutas absolutas a relativas para mostrar en el navegador
            def get_url_from_path(absolute_path):
                if os.path.isabs(absolute_path) and absolute_path.startswith(current_app.static_folder):
                    rel_path = os.path.relpath(absolute_path, current_app.static_folder).replace(os.sep, '/')
                    try:
                        return url_for('static', filename=rel_path)
                    except Exception as url_err:
                         logger.error(f"Error generando URL para {rel_path}: {url_err}")
                         return None # O devolver ruta relativa como fallback
                # Si ya es relativa o está fuera de static, devolver None o manejar diferente
                logger.warning(f"No se pudo generar URL para path: {absolute_path}")
                return None 
                
            result_url = get_url_from_path(result_path)
            orig_url = get_url_from_path(image_path)
            
            if not result_url or not orig_url:
                 flash("Error generando URLs para mostrar las imágenes.", "error")
                 return redirect(url_for('.ver_detalles_clasificacion', url_guia=url_guia)) # Usar . para endpoint local
            
            # Renderizar plantilla de prueba (asegurarse que existe)
            return render_template(
                'clasificacion/test_annotated_image.html',
                original_image=orig_url,
                annotated_image=result_url,
                detections=detections,
                num_detections=len(detections),
                guia=url_guia
            )
        else:
            logger.error("La función generate_annotated_image no devolvió una ruta válida.")
            flash("Error al generar la imagen anotada de prueba. Verifique los logs.", "error")
            return redirect(url_for('.ver_detalles_clasificacion', url_guia=url_guia)) # Usar . para endpoint local
            
    except Exception as e:
        logger.error(f"Error en test_annotated_image: {str(e)}", exc_info=True)
        flash(f"Error inesperado al generar imagen anotada de prueba: {str(e)}", "error")
        return redirect(url_for('.ver_detalles_clasificacion', url_guia=url_guia)) # Usar . para endpoint local
# --- FIN DE LA FUNCIÓN TEST_ANNOTATED_IMAGE ---
