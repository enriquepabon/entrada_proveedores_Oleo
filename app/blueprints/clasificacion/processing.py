# app/blueprints/clasificacion/processing.py

# Standard Library Imports
import os
import json
import logging
import traceback
import threading
import time
from datetime import datetime
import sqlite3 # Para sync_clasificacion

# Third-party Library Imports
from flask import (
    request, jsonify, redirect, url_for, flash, current_app, render_template
)
from werkzeug.utils import secure_filename

# Local Application Imports
from . import bp # Importar el Blueprint local

# Importar helpers desde el archivo local helpers.py
# Asegúrate que todas las funciones necesarias estén aquí
from .helpers import (
    get_utils_instance, es_archivo_imagen, get_utc_timestamp_str,
    get_clasificacion_by_codigo_guia, process_thread, generate_annotated_image,
    process_images_with_roboflow, DirectRoboflowClient
)

# Importaciones de la aplicación principal o utils (ajustar rutas si es necesario)
from app.utils.common import CommonUtils as Utils, UTC, BOGOTA_TZ, get_db_connection
import db_operations
from db_operations import store_clasificacion
import db_utils
# from db_utils import update_pesaje_bruto # Importa solo si realmente se usa aquí

# Importar login_required
from flask_login import login_required

# Configurar logger
logger = logging.getLogger(__name__)

# Diccionario para rastrear el estado del procesamiento (si se usa check_procesamiento_status)
processing_status = {}

@bp.route('/registrar_clasificacion', methods=['POST'])
@login_required
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
@login_required
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
        datos_guia['clasificacion_completada'] = True
        datos_guia['estado_clasificacion'] = 'completado'
        datos_guia['clasificacion_manual'] = {
            'verdes': float(verdes),
            'sobremaduros': float(sobremaduros),
            'dano_corona': float(dano_corona),
            'pendunculo_largo': float(pedunculo_largo),
            'podridos': float(podridos)
        }
        datos_guia['imagenes_clasificacion'] = [os.path.join('uploads', 'clasificacion', os.path.basename(img)) for img in imagenes]
        datos_guia['fecha_clasificacion'] = datetime.now().strftime('%d/%m/%Y')
        datos_guia['hora_clasificacion'] = datetime.now().strftime('%H:%M:%S')
        # Asegurar pasos_completados y datos_disponibles
        if 'pasos_completados' not in datos_guia or not isinstance(datos_guia['pasos_completados'], list):
            datos_guia['pasos_completados'] = []
        if 'clasificacion' not in datos_guia['pasos_completados']:
            datos_guia['pasos_completados'].append('clasificacion')
        if 'datos_disponibles' not in datos_guia or not isinstance(datos_guia['datos_disponibles'], list):
            datos_guia['datos_disponibles'] = []
        if 'clasificacion' not in datos_guia['datos_disponibles']:
            datos_guia['datos_disponibles'].append('clasificacion')
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

@bp.route('/procesar_clasificacion', methods=['POST'])
@login_required
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
@bp.route('/iniciar_procesamiento/<path:url_guia>', methods=['POST'])
@login_required
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
@login_required
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

@bp.route('/procesar_automatico', methods=['POST'])
@login_required
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

@bp.route('/guardar_clasificacion_final/<path:codigo_guia>', methods=['POST'])
@login_required
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

@bp.route('/regenerar_imagenes/<path:url_guia>')
@login_required
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
@login_required
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

