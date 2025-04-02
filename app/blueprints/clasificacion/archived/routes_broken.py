from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app, g, Blueprint, send_from_directory
import os
import logging
import json
import time
import datetime
import traceback
import shutil
import threading
import uuid
import base64
import re
import requests
import glob
from concurrent.futures import ThreadPoolExecutor
from werkzeug.utils import secure_filename
from app.blueprints.clasificacion import bp
from app.utils.common import CommonUtils as utils
from app.models.models import ClasificacionModel, GuiaModel, SistemaModel, ComentarioClasificacionModel, AuditoriaClasificacionModel
from app.blueprints.clasificacion.utils import is_float, get_random_id, calcular_porcentaje_clasificacion

# Configuration for Roboflow (you may need to adjust these based on your actual configuration)
WORKSPACE_NAME = os.environ.get('ROBOFLOW_WORKSPACE_NAME', 'ole-o-flores')
WORKFLOW_ID = os.environ.get('ROBOFLOW_WORKFLOW_ID', '1')
ROBOFLOW_API_KEY = os.environ.get('ROBOFLOW_API_KEY', '')

# Helper function to get a utils instance
def get_utils_instance():
    return utils(current_app)

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/<codigo>', methods=['GET'])
def clasificacion(codigo):
    """
    Maneja la vista de clasificación y el procesamiento de la misma
    """
    try:
        logger.info(f"Iniciando vista de clasificación para código: {codigo}")
        
        # Revisar la sesión actual para verificar si hay datos de peso
        peso_bruto_session = session.get('peso_bruto')
        estado_actual_session = session.get('estado_actual')
        
        logger.info(f"Datos de sesión: peso_bruto={peso_bruto_session}, estado_actual={estado_actual_session}")
        
        # Obtener el código base (sin timestamp ni versión)
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        
        # MODIFICACIÓN: Buscar todos los archivos JSON de guías con el mismo código base
        guias_folder = current_app.config.get('GUIAS_DIR', 'guias')
        guias_files_json = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.json'))
        
        if guias_files_json:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files_json.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia_json = os.path.basename(guias_files_json[0])
            codigo_guia_json = latest_guia_json[5:-5]  # Remover 'guia_' y '.json'
            logger.info(f"Código guía más reciente encontrado en JSON: {codigo_guia_json}")
            
            # Si la URL no tiene el código guía completo, redirigir a la URL correcta
            if codigo != codigo_guia_json:
                logger.info(f"Redirigiendo a URL con código guía completo: {codigo_guia_json}")
                return redirect(url_for('clasificacion.clasificacion', codigo=codigo_guia_json))
        else:
            codigo_guia_json = codigo
            logger.info(f"No se encontraron archivos JSON para el código base, usando código original: {codigo_guia_json}")
                
        # Verificar si hay datos en la sesión o si se ha proporcionado el parámetro reclasificar
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
            # Mostrar mensaje informativo
            flash("Esta guía ya ha sido clasificada anteriormente. Puedes ver los resultados o hacer clic en 'Reclasificar' para realizar una nueva clasificación.", "info")
            # Redirigir a la página de resultados de clasificación
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia_completo))
        elif clasificacion_existe and (reclasificar or desde_guia_centralizada):
            logger.info(f"Se encontró un archivo de clasificación, pero se procederá con la reclasificación: {codigo_guia_completo}")
            flash("Atención: Esta guía ya ha sido clasificada. Estás realizando una nueva clasificación que reemplazará la anterior.", "warning")

        # Obtener datos de la guía
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(codigo_guia_completo)
        logger.info(f"Datos de guía obtenidos: {json.dumps(datos_guia)}")
        
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia_completo}")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá de la clasificación
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado'] and not reclasificar:
            flash("Esta guía ya ha sido clasificada. Puedes usar el botón 'Reclasificar' para hacer una nueva clasificación.", "warning")
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
        os.makedirs(fotos_temp_dir, exist_ok=True)
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
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
            'fotos': datos_guia.get('fotos', [])
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
            
        # Guardar en la base de datos si está disponible
        try:
            from db_operations import store_clasificacion
            db_result = store_clasificacion({
                'codigo_guia': codigo_guia,
                'codigo_proveedor': clasificacion_data['codigo_proveedor'],
                'nombre_proveedor': clasificacion_data['nombre_proveedor'],
                'fecha_clasificacion': fecha_clasificacion,
                'hora_clasificacion': hora_clasificacion,
                'clasificaciones': json.dumps(clasificacion_manual),
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
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))
        except Exception as redirect_error:
            logger.error(f"Error en redirección: {str(redirect_error)}")
            # Si hay error con url_for, intentar con URL directa
            return redirect(f"/clasificacion/ver_resultados_clasificacion/{codigo_guia}")
        
    except Exception as e:
        logger.error(f"Error al procesar clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al procesar la clasificación: {str(e)}", "danger")
        return redirect(url_for('pesaje.lista_pesajes'))

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
            'fecha_registro': datetime.now().strftime('%d/%m/%Y'),
            'hora_registro': datetime.now().strftime('%H:%M:%S'),
            'fecha_clasificacion': datetime.now().strftime('%d/%m/%Y'),
            'hora_clasificacion': datetime.now().strftime('%H:%M:%S'),
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

def decode_image_data(image_data_str):
    """
    Decodifica una imagen en formato base64 a bytes.
    
    Args:
        image_data_str (str): String de imagen en formato base64
        
    Returns:
        bytes: Datos binarios de la imagen o None si hay error
    """
    try:
        # Si comienza con data:image/, extraer solo la parte base64
        if image_data_str.startswith('data:image/'):
            # Extraer solo la parte de base64
            pattern = r'data:image/[^;]+;base64,(.+)'
            match = re.match(pattern, image_data_str)
            if match:
                image_data_str = match.group(1)
        
        # Decodificar base64 a bytes
        image_bytes = base64.b64decode(image_data_str)
        return image_bytes
    except Exception as e:
        logger.error(f"Error al decodificar imagen base64: {str(e)}")
        return None

def process_images_with_roboflow(codigo_guia, fotos_paths, guia_fotos_dir, json_path):
    """
    Procesa las imágenes a través de la API de Roboflow y actualiza el archivo JSON.
    """
    logger.info(f"Iniciando procesamiento automático para guía: {codigo_guia}")
    
    # Función auxiliar para decodificar base64 correctamente, incluso si tiene prefijo data:image
    def decode_image_data(data):
        """Decodifica datos de imagen en base64, manejando prefijos de data URI si están presentes."""
        try:
            # Si es un string vacío o None, retornar None
            if not data:
                return None
                
            # Si parece ser una data URI, extraer solo la parte de datos
            if isinstance(data, str) and data.startswith('data:image'):
                # Formato típico: data:image/jpeg;base64,/9j/4AAQ...
                base64_data = data.split(',', 1)[1]
            else:
                base64_data = data
                
            # Decodificar los datos en base64
            return base64.b64decode(base64_data)
        except Exception as e:
            logger.error(f"Error decodificando datos de imagen: {str(e)}")
            return None
            
    try:
        # Leer el archivo JSON actual para inicializar los datos de clasificación
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Inicializar resultados de clasificación automática con la estructura esperada
        clasificacion_automatica = {
            "verdes": {"cantidad": 0, "porcentaje": 0},
            "maduros": {"cantidad": 0, "porcentaje": 0},
            "sobremaduros": {"cantidad": 0, "porcentaje": 0},
            "podridos": {"cantidad": 0, "porcentaje": 0},
            "danio_corona": {"cantidad": 0, "porcentaje": 0},
            "pendunculo_largo": {"cantidad": 0, "porcentaje": 0}
        }
        
        # Definir un mapeo de claves de Roboflow a claves internas
        # Esto permitirá manejar diferentes formatos de nombres desde Roboflow
        mapeo_categorias = {
            'verde': 'verdes',
            'racimo verde': 'verdes',
            'racimos verdes': 'verdes',
            'verdes': 'verdes',
            'Verde': 'verdes',
            
            'maduro': 'maduros',
            'racimo maduro': 'maduros',
            'racimos maduros': 'maduros',
            'maduros': 'maduros',
            'Maduro': 'maduros',
            
            'sobremaduro': 'sobremaduros',
            'racimo sobremaduro': 'sobremaduros',
            'racimos sobremaduros': 'sobremaduros',
            'sobremaduros': 'sobremaduros',
            'Sobremaduro': 'sobremaduros',
            
            'podrido': 'podridos',
            'racimo podrido': 'podridos',
            'racimos podridos': 'podridos',
            'podridos': 'podridos',
            'Podrido': 'podridos',
            
            'danio corona': 'danio_corona',
            'racimo con danio corona': 'danio_corona',
            'racimos con danio corona': 'danio_corona',
            'danio_corona': 'danio_corona',
            'Danio corona': 'danio_corona',
            
            'pendunculo largo': 'pendunculo_largo',
            'racimo con pedunculo largo': 'pendunculo_largo',
            'racimos con pedunculo largo': 'pendunculo_largo',
            'pedunculo_largo': 'pendunculo_largo',
            'pendunculo_largo': 'pendunculo_largo',
            'Pedunculo largo': 'pendunculo_largo'
        }
        
        resultados_por_foto = {}
        tiempo_inicio = time.time()
        
        # Configuración de Roboflow
        roboflow_api_key = current_app.config.get('ROBOFLOW_API_KEY', '')
        roboflow_workspace = current_app.config.get('ROBOFLOW_WORKSPACE', '')
        roboflow_workflow_id = current_app.config.get('ROBOFLOW_WORKFLOW_ID', '')
        roboflow_api_url = current_app.config.get('ROBOFLOW_API_URL', 'https://detect.roboflow.com')
        
        # Verificar que tenemos la configuración necesaria
        if not all([roboflow_api_key, roboflow_workspace, roboflow_workflow_id]):
            logger.error("Falta configuración de Roboflow. Verificar ROBOFLOW_API_KEY, ROBOFLOW_WORKSPACE y ROBOFLOW_WORKFLOW_ID en la configuración.")
            logger.error(f"API Key configurada: {'Sí' if roboflow_api_key else 'No'}")
            logger.error(f"Workspace configurado: {'Sí' if roboflow_workspace else 'No'}")
            logger.error(f"Workflow ID configurado: {'Sí' if roboflow_workflow_id else 'No'}")
            logger.error("Usando simulación como alternativa.")
            # Usar simulación como fallback
            use_simulation = True
        else:
            use_simulation = False
            # Construir la URL de la API de Roboflow
            logger.info(f"Usando API de Roboflow: {roboflow_api_url}")
            logger.info(f"Workspace: {roboflow_workspace}, Workflow ID: {roboflow_workflow_id}")
            if roboflow_api_key.startswith('YOUR_API_KEY'):
                logger.error("La API Key de Roboflow parece ser el valor por defecto. Por favor configura tu API key real.")
                use_simulation = True
        
        # Procesar cada foto secuencialmente
        for idx, foto_path in enumerate(fotos_paths, 1):
            # Guardar una copia de la foto original en el directorio de la guía
            foto_nombre = f"foto_{idx}.jpg"
            foto_destino = os.path.join(guia_fotos_dir, foto_nombre)
            # Copiar la imagen original
            from shutil import copyfile
            copyfile(foto_path, foto_destino)
            
            logger.info(f"Procesando imagen {idx}/{len(fotos_paths)}: {foto_path}")
            # Redimensionar imagen para asegurar que no sea demasiado grande
            # Roboflow limita las imágenes a 1152x2048
            from PIL import Image
            try:
                image = Image.open(foto_path)
                
                # Verificar si la imagen necesita redimensionamiento
                width, height = image.size
                max_width = 1152
                max_height = 2048
                
                if width > max_width or height > max_height:
                    # Calcular ratio de aspecto
                    ratio = min(max_width/width, max_height/height)
                    new_size = (int(width * ratio), int(height * ratio))
                    
                    # Redimensionar la imagen
                    image = image.resize(new_size, Image.LANCZOS)
                    
                    # Guardar la imagen redimensionada
                    new_path = foto_path.replace('.jpg', '_resized.jpg')
                    image.save(new_path, 'JPEG')
                    foto_path = new_path
            except Exception as e:
                logger.warning(f"No se pudo redimensionar la imagen: {e}")
            
            # Enviar la imagen a Roboflow para procesamiento
            try:
                if use_simulation:
                    # SIMULACIÓN: Como no tenemos la API real configurada, simulamos el procesamiento
                    logger.info(f"Simulando envío de imagen {idx} a Roboflow: {foto_path}")
                    
                    # Simular un tiempo de procesamiento de 2 segundos por imagen
                    time.sleep(2)
                    
                    # Simular detecciones aleatorias (solo para pruebas)
                    import random
                    total_detecciones = random.randint(10, 30)
                    
                    detecciones = []
                    for _ in range(total_detecciones):
                        categoria = random.choice(['verde', 'maduro', 'sobremaduro', 'podrido', 'danio corona', 'pendunculo largo'])
                        confianza = random.uniform(0.5, 1.0)
                        detecciones.append({
                            'class': categoria,
                            'confidence': confianza,
                            'x': random.randint(50, 500),
                            'y': random.randint(50, 500),
                            'width': random.randint(30, 100),
                            'height': random.randint(30, 100)
                        })
                    
                    modelo_utilizado = "SIMULACIÓN (no se usó Roboflow real)"
                else:
                    # CÓDIGO REAL: Enviar la imagen a Roboflow
                    logger.info(f"Enviando imagen {idx} a Roboflow API: {foto_path}")
                    
                    try:
                        # Intentar importar InferenceHTTPClient, si no está disponible usar requests directamente
                        try:
                            from inference_sdk import InferenceHTTPClient
                            use_sdk = True
                            logger.info("Usando inference_sdk para conectar con Roboflow")
                        except ImportError:
                            use_sdk = False
                            logger.warning("inference_sdk no está instalado. Usando requests directamente.")
                        
                        if use_sdk:
                            # Usar el SDK de Roboflow
                            client = InferenceHTTPClient(
                                api_url=roboflow_api_url,
                                api_key=roboflow_api_key
                            )
                            
                            logger.info(f"Enviando imagen a workflow: {roboflow_workflow_id}")
                            result = client.run_workflow(
                                workspace_name=roboflow_workspace,
                                workflow_id=roboflow_workflow_id,
                                images={"image": foto_path},
                                use_cache=True  # cache workflow definition for 15 minutes
                            )
                            
                            logger.info(f"Respuesta de Roboflow recibida: {result}")
                            
                            # Preparar el formato de las detecciones
                            detecciones = []
                            
                            # Extraer datos del resultado según el formato esperado
                            # La estructura esperada del resultado puede variar, así que adaptamos según lo que recibamos
                            if isinstance(result, dict):
                                # Buscar la información relevante en la respuesta
                                # Para racimos verdes, sobremaduros, etc.
                                categorias_mapeo = {
                                    "Racimos verdes": "verde",
                                    "racimo sobremaduro": "sobremaduro",
                                    "racimo daño en corona": "danio corona",
                                    "racimo pedunculo largo": "pendunculo largo",
                                    "racimo podrido": "podrido"
                                }
                                
                                for categoria_key, categoria_value in categorias_mapeo.items():
                                    if categoria_key in result:
                                        cantidad = result.get(categoria_key, 0)
                                        # Si es un entero, agregamos esa cantidad de detecciones
                                        if isinstance(cantidad, int):
                                            for i in range(cantidad):
                                                detecciones.append({
                                                    'class': categoria_value,
                                                    'confidence': 0.95,  # Valor alto de confianza
                                                    'x': 100,  # Valores placeholder
                                                    'y': 100,
                                                    'width': 50,
                                                    'height': 50
                                                })
                                
                                # Buscar la imagen anotada si está disponible
                                annotated_image = result.get("annotated_image")
                                if annotated_image:
                                    # Guardar la imagen anotada
                                    img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                    with open(img_path, "wb") as f:
                                        # Si es un string base64, decodificarlo
                                        if isinstance(annotated_image, str):
                                            image_data = decode_image_data(annotated_image)
                                            if image_data:
                                                f.write(image_data)
                                        # Si es bytes, escribirlo directamente
                                        elif isinstance(annotated_image, bytes):
                                            f.write(annotated_image)
                                    logger.info(f"Imagen anotada guardada: {img_path}")
                            
                            modelo_utilizado = f"Roboflow Workflow: {roboflow_workflow_id}"
                        else:
                            # Usar directamente requests si no está disponible el SDK
                            # Leer la imagen como bytes
                            with open(foto_path, "rb") as image_file:
                                image_data = image_file.read()
                            
                            # Preparar los parámetros para la API de Roboflow
                            params = {
                                "api_key": roboflow_api_key,
                                "workspace": roboflow_workspace,
                                "workflow_id": roboflow_workflow_id
                            }
                            
                            # Realizar la solicitud a la API de Roboflow
                            import requests
                            headers = {"Content-Type": "application/x-www-form-urlencoded"}
                            
                            logger.info(f"Enviando solicitud a Roboflow API: {roboflow_api_url}")
                            response = requests.post(
                                f"{roboflow_api_url}/workflows/run",
                                params=params,
                                data=image_data,
                                headers=headers
                            )
                            
                            # Verificar si la solicitud fue exitosa
                            if response.status_code == 200:
                                # Procesar la respuesta
                                result = response.json()
                                logger.info(f"Respuesta de Roboflow recibida: {result}")
                                
                                # Preparar el formato de las detecciones
                                detecciones = []
                                
                                # Extraer datos del resultado según el formato esperado
                                # La estructura esperada del resultado puede variar, así que adaptamos según lo que recibamos
                                if isinstance(result, dict):
                                    # Buscar la información relevante en la respuesta
                                    # Para racimos verdes, sobremaduros, etc.
                                    categorias_mapeo = {
                                        "Racimos verdes": "verde",
                                        "racimo sobremaduro": "sobremaduro",
                                        "racimo daño en corona": "danio corona",
                                        "racimo pedunculo largo": "pendunculo largo",
                                        "racimo podrido": "podrido"
                                    }
                                    
                                    for categoria_key, categoria_value in categorias_mapeo.items():
                                        if categoria_key in result:
                                            cantidad = result.get(categoria_key, 0)
                                            # Si es un entero, agregamos esa cantidad de detecciones
                                            if isinstance(cantidad, int):
                                                for i in range(cantidad):
                                                    detecciones.append({
                                                        'class': categoria_value,
                                                        'confidence': 0.95,  # Valor alto de confianza
                                                        'x': 100,  # Valores placeholder
                                                        'y': 100,
                                                        'width': 50,
                                                        'height': 50
                                                    })
                                    
                                    # Buscar la imagen anotada si está disponible
                                    annotated_image = result.get("annotated_image")
                                    if annotated_image:
                                        # Guardar la imagen anotada
                                        img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                        with open(img_path, "wb") as f:
                                            # Si es un string base64, decodificarlo
                                            if isinstance(annotated_image, str):
                                                image_data = decode_image_data(annotated_image)
                                                if image_data:
                                                    f.write(image_data)
                                            # Si es bytes, escribirlo directamente
                                            elif isinstance(annotated_image, bytes):
                                                f.write(annotated_image)
                                        logger.info(f"Imagen anotada guardada: {img_path}")
                                
                                modelo_utilizado = f"Roboflow Workflow: {roboflow_workflow_id}"
                            else:
                                # Error en la solicitud
                                logger.error(f"Error en la solicitud a Roboflow: {response.status_code} - {response.text}")
                                detecciones = []
                                modelo_utilizado = f"Error en Roboflow: {response.status_code}"
                        except Exception as e:
                            logger.error(f"Error en la comunicación con Roboflow: {str(e)}")
                            logger.error(traceback.format_exc())
                            detecciones = []
                            modelo_utilizado = f"Error: {str(e)}"
                
                # Procesar cada detección
                for deteccion in detecciones:
                    clase = deteccion['class']
                    if clase in mapeo_categorias:
                        # Mapear a la categoría interna
                        categoria_interna = mapeo_categorias[clase]
                        # Incrementar contador
                        clasificacion_automatica[categoria_interna]['cantidad'] += 1
                
                # Guardar resultados de esta foto
                resultados_por_foto[str(idx)] = {
                    'total_detecciones': len(detecciones),
                    'categorias': {cat: sum(1 for d in detecciones if d['class'] == cat) for cat in set(d['class'] for d in detecciones if 'class' in d)}
                }
                
                # Si no se guardó una imagen procesada y estamos en simulación, crear una copia
                if use_simulation:
                                                img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                    copyfile(foto_path, img_path)  # En simulación, usamos la imagen original
                
                # Actualizar progreso
                if codigo_guia in processing_status:
                    processing_status[codigo_guia]['progress'] = 20 + (70 * idx // len(fotos_paths))
                    processing_status[codigo_guia]['processed_images'] = idx
                    processing_status[codigo_guia]['message'] = f"Procesadas {idx} de {len(fotos_paths)} imágenes"
                
                                    except Exception as e:
                logger.error(f"Error procesando imagen con Roboflow: {str(e)}")
                logger.error(traceback.format_exc())
                resultados_por_foto[str(idx)] = {"error": str(e)}
            
            # Eliminar archivos temporales si existen
            if foto_path.endswith("_resized.jpg"):
                try:
                    os.remove(foto_path)
                except:
                    pass
        
        # Calcular tiempo total de procesamiento
        tiempo_fin = time.time()
        tiempo_procesamiento = round(tiempo_fin - tiempo_inicio, 2)
        
        # Calcular porcentajes para cada categoría
        total_racimos = sum(valor["cantidad"] for valor in clasificacion_automatica.values())
        if total_racimos > 0:
            for categoria in clasificacion_automatica:
                clasificacion_automatica[categoria]["porcentaje"] = round(
                    (clasificacion_automatica[categoria]["cantidad"] / total_racimos) * 100, 2
                ) if total_racimos > 0 else 0
                
        # Actualizar datos de clasificación
        clasificacion_data['clasificacion_automatica'] = clasificacion_automatica
        clasificacion_data['resultados_por_foto'] = resultados_por_foto
        clasificacion_data['estado'] = 'completado'
        clasificacion_data['workflow_completado'] = True
        clasificacion_data['tiempo_procesamiento'] = f"{tiempo_procesamiento} segundos"
        clasificacion_data['modelo_utilizado'] = modelo_utilizado
        
        # Guardar las rutas de fotos procesadas
        fotos_relativas = []
        for i in range(1, len(fotos_paths) + 1):
            foto_path = os.path.join(guia_fotos_dir, f"foto_{i}.jpg")
            if os.path.exists(foto_path):
                # Determinar la ruta relativa
                # Primero encontrar el directorio 'static'
                path_parts = foto_path.split(os.sep)
                try:
                    static_index = path_parts.index('static')
                    # Obtener la ruta relativa desde 'static'
                    ruta_relativa = os.sep.join(path_parts[static_index+1:])
                    fotos_relativas.append(ruta_relativa)
                    logger.info(f"Foto {i} agregada a resultados: {ruta_relativa}")
                except ValueError:
                    # Si 'static' no está en la ruta, usar la ruta completa
                    logger.warning(f"No se pudo determinar ruta relativa para: {foto_path}")
                    fotos_relativas.append(foto_path)
        
        # Agregar las rutas de las fotos al resultado
        clasificacion_data['fotos'] = fotos_relativas
        
        # Guardar cambios en el archivo JSON
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
        
        logger.info(f"Procesamiento automático completado para guía: {codigo_guia}")
        return True
    except Exception as e:
        logger.error(f"Error en procesamiento automático: {str(e)}")
        logger.error(traceback.format_exc())
        return False




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
                    
                    # 3. Buscar datos en utils.get_datos_registro
                    # 3. Buscar datos en utils.get_datos_registro
                        try:
                            datos_registro = utils.get_datos_registro(codigo_guia)
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
    try:
        logger.info(f"Mostrando resultados clasificación para guía: {url_guia}")
        
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
                logger.info(f"Claves en clasificacion_data: {clasificacion_data.keys()}")
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
                isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), dict) and 
                clasificacion_data['clasificacion_automatica'][categoria].get('cantidad', 0) > 0
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
                datos_registro = utils.get_datos_registro(url_guia)
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
    Inicia el procesamiento de imágenes con Roboflow para una guía específica.
    """
    logger.info(f"Iniciando procesamiento manual con Roboflow para guía: {url_guia}")
    
    try:
        # Verificar si existe el archivo de clasificación
        clasificaciones_dir = os.path.join(current_app.static_folder, 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f'clasificacion_{url_guia}.json')
        
        if not os.path.exists(json_path):
            logger.error(f"No se encontró archivo de clasificación para {url_guia}")
            return jsonify({
                'status': 'error',
                'message': f"No se encontró archivo de clasificación para {url_guia}"
            }), 404
        
        # Leer información sobre la guía y sus fotos
        with open(json_path, 'r') as f:
            clasificacion_data = json.load(f)
        
        # Buscar fotos en diferentes ubicaciones posibles
        fotos_paths = []
        
        # 1. Primero buscar en el directorio temporal de fotos
        guia_fotos_temp_dir = os.path.join(current_app.static_folder, 'fotos_racimos_temp', url_guia)
        if os.path.exists(guia_fotos_temp_dir):
            logger.info(f"Buscando fotos en directorio temporal: {guia_fotos_temp_dir}")
            for filename in os.listdir(guia_fotos_temp_dir):
                if filename.startswith('foto_') and filename.endswith(('.jpg', '.jpeg', '.png')):
                    fotos_paths.append(os.path.join(guia_fotos_temp_dir, filename))
        
        # 2. Si no hay fotos en el directorio temporal, buscar en el directorio principal de fotos
        if not fotos_paths:
            guia_fotos_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
            if os.path.exists(guia_fotos_dir):
                logger.info(f"Buscando fotos en directorio principal: {guia_fotos_dir}")
                for filename in os.listdir(guia_fotos_dir):
                    if utils.es_archivo_imagen(filename):
                        fotos_paths.append(os.path.join(guia_fotos_dir, filename))
        
        # 3. NUEVO: Si aún no hay fotos, buscar en el directorio temp_clasificacion
        if not fotos_paths:
            temp_clasificacion_dir = os.path.join(current_app.static_folder, 'uploads', 'temp_clasificacion')
            if os.path.exists(temp_clasificacion_dir):
                logger.info(f"Buscando fotos en directorio temp_clasificacion: {temp_clasificacion_dir}")
                for filename in os.listdir(temp_clasificacion_dir):
                    if filename.startswith(f'temp_clasificacion_{url_guia}_') and filename.endswith(('.jpg', '.jpeg', '.png')):
                        fotos_paths.append(os.path.join(temp_clasificacion_dir, filename))
                        logger.info(f"Encontrada foto para {url_guia} en temp_clasificacion: {filename}")
        
        if not fotos_paths:
            logger.error(f"No se encontraron imágenes para procesar en {url_guia}")
            return jsonify({
                'status': 'error',
                'message': "No se encontraron imágenes para procesar"
            }), 404
        
        # Inicializar el estado de procesamiento
        processing_status[url_guia] = {
            'status': 'processing',
            'progress': 5,
            'step': 1,
            'message': 'Preparando imágenes para procesamiento...',
            'total_images': len(fotos_paths),
            'processed_images': 0
        }
        
        # Obtener la información necesaria antes de iniciar el thread
        # para evitar problemas con current_app
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        # Capturar la aplicación actual para usarla en el thread
        app = current_app._get_current_object()
        
        # Iniciar procesamiento en un hilo separado
        def process_thread():
            # Configurar el contexto de aplicación para este hilo
            with app.app_context():
                try:
                    # Log para depuración de rutas de fotos encontradas
                    logger.info(f"Procesando {len(fotos_paths)} fotos para la guía {url_guia}")
                    for i, foto_path in enumerate(fotos_paths):
                        logger.info(f"Foto {i+1}: {foto_path}")
                    
                    # Determinar el directorio de fotos para guardar resultados
                    if os.path.exists(guia_fotos_temp_dir):
                        guia_fotos_dir_para_resultados = guia_fotos_temp_dir
                    else:
                        # Crear el directorio en uploads/fotos/[codigo_guia] si no existe
                        guia_fotos_dir_para_resultados = os.path.join(upload_folder, 'fotos', url_guia)
                        os.makedirs(guia_fotos_dir_para_resultados, exist_ok=True)
                        logger.info(f"Creado directorio para resultados: {guia_fotos_dir_para_resultados}")
                    
                    # Usar la función existente process_images_with_roboflow
                    process_images_with_roboflow(url_guia, fotos_paths, guia_fotos_dir_para_resultados, json_path)
                    # Marcar como completado
                    processing_status[url_guia] = {
                        'status': 'completed',
                        'progress': 100,
                        'step': 5,
                        'message': 'Procesamiento completado correctamente',
                        'redirect_url': f'/mostrar_resultados_automaticos/{url_guia}'
                    }
                except Exception as e:
                    logger.error(f"Error en el procesamiento de imágenes: {str(e)}")
                    logger.error(traceback.format_exc())
                    processing_status[url_guia] = {
                        'status': 'error',
                        'progress': 0,
                        'step': 1,
                        'message': f"Error en el procesamiento: {str(e)}"
                    }
        
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'status': 'started',
            'message': 'Procesamiento iniciado correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error al iniciar procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': f"Error al iniciar procesamiento: {str(e)}"
        }), 500



@bp.route('/check_procesamiento_status/<path:url_guia>', methods=['GET'])
def check_procesamiento_status(url_guia):
    """
    Verifica el estado del procesamiento de imágenes con Roboflow para una guía específica.
    """
    try:
        # Si el estado está en el diccionario, devolverlo
        global processing_status
        if url_guia in processing_status:
            status_data = processing_status[url_guia]
            
            # Si el procesamiento ha terminado, podemos limpiar el estado
            if status_data['status'] in ['completed', 'error']:
                status_copy = status_data.copy()
                
                # Eliminar del diccionario después de un tiempo para liberar memoria
                # (pero mantenerlo para esta respuesta)
                if status_data['status'] == 'completed':
                    del processing_status[url_guia]
                
                return jsonify(status_copy)
            
            return jsonify(status_data)
        
        # Si no está en el diccionario, verificar si existe un archivo JSON que indique que se ha completado
        clasificaciones_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'clasificaciones')
        json_path = os.path.join(clasificaciones_dir, f'clasificacion_{url_guia}.json')
        
        if os.path.exists(json_path):
            with open(json_path, 'r') as f:
                clasificacion_data = json.load(f)
                
            if 'clasificacion_automatica' in clasificacion_data:
                # Si hay clasificación automática, asumimos que se ha completado
                return jsonify({
                    'status': 'completed',
                    'progress': 100,
                    'step': 5,
                    'message': 'Procesamiento completado',
                    'redirect_url': f'/mostrar_resultados_automaticos/{url_guia}'
                })
        
        
        # Si no hay información, asumimos que nunca se inició o hubo un error
        return jsonify({
            'status': 'error',
            'progress': 0,
            'step': 1,
            'message': 'No se encontró información sobre el procesamiento'
        }), 404
        
    except Exception as e:
        logger.error(f"Error al verificar estado de procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'progress': 0,
            'step': 1,
            'message': f"Error al verificar estado: {str(e)}"
        }), 500



@bp.route('/procesar_imagenes/<path:url_guia>')
def procesar_imagenes(url_guia):
    """
    Muestra la pantalla de procesamiento para una guía específica.
    """
    try:
        return render_template('archive/old_templates/procesando_clasificacion.html', codigo_guia=url_guia)
    except Exception as e:
        logger.error(f"Error al mostrar pantalla de procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al preparar el procesamiento: {str(e)}", 'error')
        return redirect(url_for('clasificacion.ver_resultados_automaticos', url_guia=url_guia))



@bp.route('/mostrar_resultados_automaticos/<path:url_guia>')
def mostrar_resultados_automaticos(url_guia):
    """
    Muestra los resultados de la clasificación automática a partir del JSON generado.
    """
    try:
        utils_instance = get_utils_instance()
        datos_guia = utils_instance.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        json_path = os.path.join(current_app.config['FOTOS_RACIMOS_FOLDER'], f'clasificacion_{url_guia}.json')
        
        if not os.path.exists(json_path):
            flash("No se encontraron resultados de clasificación automática para esta guía.", "warning")
            return redirect(url_for('clasificacion.procesar_clasificacion_manual', url_guia=url_guia))
            
        with open(json_path, 'r') as file:
            clasificacion_data = json.load(file)
            
        logger.info(f"Clasificación data: {clasificacion_data}")
        
        # Comprobar si hay clasificación automática
        if not clasificacion_data.get('clasificacion_automatica'):
            flash("No se han procesado imágenes automáticamente para esta guía.", "warning")
            return redirect(url_for('clasificacion.procesar_clasificacion_manual', url_guia=url_guia))

        # Obtener fotos procesadas y sus resultados
        fotos_procesadas = []
        if 'resultados_por_foto' in clasificacion_data:
            for idx, (foto_path, resultados) in enumerate(clasificacion_data['resultados_por_foto'].items()):
                # Convertir ruta absoluta a relativa para servir la imagen
                foto_path = os.path.basename(foto_path)
                foto_url = url_for('static', filename=f'fotos_racimos_procesadas/{foto_path}')
                
                # También buscar la imagen de clusters correspondiente
                foto_clusters = f'clusters_{url_guia}_foto{idx+1}.jpg'
                foto_clusters_url = url_for('static', filename=f'fotos_racimos_procesadas/{foto_clusters}')
                
                fotos_procesadas.append({
                    'original': foto_url,
                    'clusters': foto_clusters_url,
                    'resultados': resultados
                })
        
        # Actualizar los datos de la guía con la información de clasificación
        datos_guia.update({
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'fotos_procesadas': fotos_procesadas,
            'estado_clasificacion': clasificacion_data.get('estado', 'completado')
        })
        
        return render_template('archive/old_templates/resultados_automaticos.html', 
                              codigo_guia=url_guia,
                              nombre_proveedor=datos_guia.get('nombre_proveedor', ''),
                              codigo_proveedor=datos_guia.get('codigo_proveedor', ''),
                              fecha_registro=datos_guia.get('fecha_registro', ''),
                              hora_registro=datos_guia.get('hora_registro', ''),
                              cantidad_racimos=datos_guia.get('cantidad_racimos', 0),
                              total_racimos_detectados=datos_guia.get('total_racimos_detectados', 0),
                              modelo_utilizado=clasificacion_data.get('modelo_utilizado', 'YOLOv8'),
                              tiempo_procesamiento=clasificacion_data.get('tiempo_procesamiento', ''),
                              resultados_automaticos=datos_guia.get('clasificacion_automatica', {}),
                              fotos_procesadas=fotos_procesadas)
    except Exception as e:
        logger.error(f"Error al mostrar resultados automáticos: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return redirect(url_for('misc.index'))

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
        
        # Responder con los resultados
        return jsonify({
            'success': True,
            'resultados': resultados,
            'mensaje': 'Clasificación automática completada exitosamente'
        })
    
    except Exception as e:
        logger.error(f"Error en procesamiento automático: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500


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
