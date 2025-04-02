from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.pesaje import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/pesaje/<codigo>', methods=['GET'])
def pesaje(codigo):
    """
    Maneja la vista de pesaje y el procesamiento del mismo
    """
    try:
        # Eliminar cualquier sufijo "_R1" o similar para usar el código base
        if "_R" in codigo and codigo.split("_R")[-1].isdigit():
            codigo_limpio = codigo.split("_R")[0]
            logger.info(f"Eliminando sufijo de revisión, usando código base: {codigo_limpio}")
        else:
            codigo_limpio = codigo
        
        # Verificar si tenemos un código guía original guardado en la sesión
        original_codigo_guia = session.get('codigo_guia_original')
        if original_codigo_guia:
            logger.info(f"Usando código guía original de sesión {original_codigo_guia}")
            codigo_guia_completo = original_codigo_guia
            # Guardar en la sesión para mantener consistencia
            session['codigo_guia'] = codigo_guia_completo
            session.modified = True
            
            # Intentar obtener datos con este código
            datos_guia = utils.get_datos_guia(codigo_guia_completo)
            if datos_guia:
                # Si encontramos datos, no necesitamos buscar más
                return render_template('pesaje.html', datos=datos_guia)
        
        # Si no tenemos un código de guía original o no se encontraron datos, continuar con el flujo normal
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo_limpio.split('_')[0] if '_' in codigo_limpio else codigo_limpio
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            
            # Verificar y eliminar sufijo "_R1" si existe
            if "_R" in codigo_guia_completo and codigo_guia_completo.split("_R")[-1].isdigit():
                codigo_guia_completo = codigo_guia_completo.split("_R")[0]
                logger.info(f"Eliminando sufijo de revisión del archivo, usando: {codigo_guia_completo}")
        else:
            codigo_guia_completo = codigo_limpio

        # Intentar obtener datos usando múltiples métodos
        datos_guia = None
        
        # 1. Primero intentar con utils.get_datos_guia
        try:
            datos_guia = utils.get_datos_guia(codigo_guia_completo)
            if datos_guia:
                logger.info(f"Datos obtenidos con utils.get_datos_guia para {codigo_guia_completo}")
        except Exception as e:
            logger.error(f"Error al obtener datos con utils.get_datos_guia: {str(e)}")
        
        # 2. Si no funciona, intentar con la capa DAL
        if not datos_guia:
            try:
                from data_access import DataAccess
                dal = DataAccess(app)
                datos_dal = dal.get_guia_complete_data(codigo_guia_completo)
                if datos_dal:
                    logger.info(f"Datos obtenidos con DataAccess para {codigo_guia_completo}")
                    datos_guia = datos_dal
            except Exception as e:
                logger.error(f"Error al obtener datos con DataAccess: {str(e)}")
        
        # 3. Si todavía no hay datos, intentar con db_operations y db_utils
        if not datos_guia:
            try:
                from db_operations import get_pesaje_bruto_by_codigo_guia
                from db_utils import get_entry_record_by_guide_code
                
                # Intentar obtener desde db_operations
                datos_guia = get_pesaje_bruto_by_codigo_guia(codigo_guia_completo)
                
                # Si todavía no lo encuentra, intentar con entry records
                if not datos_guia:
                    logger.info(f"Intentando obtener desde entry records para {codigo_guia_completo}")
                    registro = get_entry_record_by_guide_code(codigo_guia_completo)
                    if registro:
                        # Crear un diccionario con exactamente los campos que espera la plantilla
                        datos_guia = {
                            'codigo_guia': codigo_guia_completo,
                            'codigo': registro.get('codigo_proveedor', ''),
                            'nombre': registro.get('nombre_proveedor', ''),
                            'cantidad_racimos': registro.get('cantidad_racimos', ''),
                            'placa': registro.get('placa', 'No disponible'),
                            'transportador': registro.get('transportador', 'No disponible'),
                            'fecha_registro': registro.get('fecha_registro', ''),
                            'hora_registro': registro.get('hora_registro', ''),
                            'fecha_tiquete': registro.get('fecha_tiquete', ''),
                            'acarreo': registro.get('acarreo', 'No'),
                            'cargo': registro.get('cargo', 'No'),
                            'estado_actual': 'registro_completado'
                        }
                        
                        # Registrar estos valores en la sesión para garantizar consistencia
                        session['codigo_guia'] = codigo_guia_completo
                        session['codigo_proveedor'] = registro.get('codigo_proveedor', '')
                        session['nombre_proveedor'] = registro.get('nombre_proveedor', '')
                        session['placa'] = registro.get('placa', 'No disponible')
                        session['transportador'] = registro.get('transportador', 'No disponible')
                        session['racimos'] = registro.get('cantidad_racimos', '')
                        session.modified = True
                        
                        logger.info(f"Datos obtenidos desde entry records para {codigo_guia_completo}: proveedor={datos_guia['nombre']}, racimos={datos_guia['cantidad_racimos']}")
            except Exception as e:
                logger.error(f"Error al intentar obtener datos de la base de datos: {str(e)}")
                logger.error(traceback.format_exc())
        
        # 4. Como último recurso, utilizar datos de la sesión
        if not datos_guia:
            logger.info(f"No se encontraron datos para {codigo_guia_completo}, intentando usar datos de sesión")
            if session.get('codigo_guia') and session.get('codigo_proveedor'):
                datos_guia = {
                    'codigo_guia': session.get('codigo_guia', codigo_guia_completo),
                    'codigo': session.get('codigo_proveedor', 'No disponible'),
                    'nombre': session.get('nombre_proveedor', 'No disponible'),
                    'cantidad_racimos': session.get('racimos', 'No disponible'),
                    'placa': session.get('placa', 'No disponible'),
                    'transportador': session.get('transportador', 'No disponible'),
                    'estado_actual': 'registro_completado'
                }
                logger.info(f"Usando datos de sesión para {codigo_guia_completo}")
                
        if not datos_guia:
            logger.error(f"No se pudo encontrar información para la guía: {codigo_guia_completo}")
            flash('Guía no encontrada', 'error')
            return render_template('error.html', message='Guía no encontrada'), 404
            
        # Verificar si la guía ya ha sido procesada más allá del pesaje
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.info(f"La guía {codigo_guia_completo} ya ha sido procesada. Continuando con el mismo código.")
            
            # Limpiar datos de sesión relacionados con la guía anterior pero preservar información de proveedor
            session_keys_to_reset = ['estado_actual', 'peso_bruto', 'tipo_pesaje', 'fecha_pesaje', 'hora_pesaje']
            for key in session_keys_to_reset:
                if key in session:
                    del session[key]
            
            # Guardar el código en la sesión sin sufijo R
            # También guardar como código original si aún no existe
            if 'codigo_guia_original' not in session:
                session['codigo_guia_original'] = codigo_guia_completo
            session['codigo_guia'] = codigo_guia_completo
            session.modified = True
            
        # Asegurarse de que los datos del proveedor estén completos
        if datos_guia:
            # Si falta el campo 'codigo', intentar obtenerlo de otros campos
            if not datos_guia.get('codigo') or datos_guia.get('codigo') == 'N/A':
                # Intentar extraer del codigo_proveedor
                datos_guia['codigo'] = datos_guia.get('codigo_proveedor', 'N/A')
                
            # Si falta el campo 'nombre', intentar obtenerlo de otros campos
            if not datos_guia.get('nombre') or datos_guia.get('nombre') == 'N/A':
                # Intentar extraer del nombre_proveedor
                datos_guia['nombre'] = datos_guia.get('nombre_proveedor', 
                                      datos_guia.get('nombre_agricultor', 'N/A'))
                
            # Si falta el campo 'cantidad_racimos', intentar obtenerlo de otros campos
            if not datos_guia.get('cantidad_racimos') or datos_guia.get('cantidad_racimos') == 'N/A':
                # Intentar extraer del campo racimos
                datos_guia['cantidad_racimos'] = datos_guia.get('racimos', 'N/A')
                
            # Añadir datos adicionales de la sesión si están disponibles
            if session.get('codigo_proveedor') and (not datos_guia.get('codigo') or datos_guia.get('codigo') == 'N/A'):
                datos_guia['codigo'] = session.get('codigo_proveedor')
                
            if session.get('nombre_proveedor') and (not datos_guia.get('nombre') or datos_guia.get('nombre') == 'N/A'):
                datos_guia['nombre'] = session.get('nombre_proveedor')
                
            if session.get('racimos') and (not datos_guia.get('cantidad_racimos') or datos_guia.get('cantidad_racimos') == 'N/A'):
                datos_guia['cantidad_racimos'] = session.get('racimos')
                
            # También actualizar la sesión con estos datos para mantener consistencia
            session['codigo_proveedor'] = datos_guia.get('codigo', session.get('codigo_proveedor', 'N/A'))
            session['nombre_proveedor'] = datos_guia.get('nombre', session.get('nombre_proveedor', 'N/A'))
            session['racimos'] = datos_guia.get('cantidad_racimos', session.get('racimos', 'N/A'))
            session.modified = True
                
        # Log para depuración
        logger.info(f"Datos para template: codigo={datos_guia.get('codigo', 'N/A')}, nombre={datos_guia.get('nombre', 'N/A')}, racimos={datos_guia.get('cantidad_racimos', 'N/A')}")
        
        # Si el código en la URL tiene sufijo pero el real no, redirigir
        if codigo != codigo_limpio:
            logger.info(f"Redirigiendo de URL con sufijo {codigo} a URL sin sufijo {codigo_limpio}")
            return redirect(url_for('pesaje.pesaje', codigo=codigo_limpio))

        # Renderizar template de pesaje
        return render_template('pesaje.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message=f"Error al procesar la solicitud: {str(e)}"), 500


@bp.route('/pesaje-inicial/<codigo>', methods=['GET', 'POST'])
def pesaje_inicial(codigo):
    """Manejo de pesaje inicial (directo o virtual)"""
    pass



@bp.route('/pesaje-tara/<codigo>', methods=['GET', 'POST'])
def pesaje_tara(codigo):
    """
    Maneja la vista de pesaje de tara y el procesamiento del mismo
    """
    try:
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo

        # Obtener datos de la guía usando el código completo
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Verificar que la clasificación esté completada
        if not datos_guia.get('clasificacion_completa'):
            return render_template('error.html', 
                                message="Debe completar el proceso de clasificación antes de realizar el pesaje de tara"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje.pesaje_tara', codigo=codigo_guia_completo))

        # Renderizar template de pesaje de tara
        return render_template('pesaje_tara.html',
                            codigo=codigo_guia_completo,
                            datos=datos_guia)

    except Exception as e:
        logger.error(f"Error en pesaje de tara: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje de tara"), 500



@bp.route('/procesar_pesaje_tara_directo', methods=['POST'])
def procesar_pesaje_tara_directo():
    try:
        # Verificar que haya un archivo cargado
        if 'imagen' not in request.files:
            logger.error("No se envió archivo de imagen para pesaje de tara")
            return jsonify({"success": False, "message": "No se envió archivo de imagen"}), 400
            
        image_file = request.files['imagen']
        codigo_guia = request.form.get('codigo_guia')
        
        if not image_file:
            logger.error("No se seleccionó archivo de imagen para pesaje de tara")
            return jsonify({"success": False, "message": "No se seleccionó archivo de imagen"}), 400
            
        if not codigo_guia:
            logger.error("No se proporcionó código de guía para pesaje de tara")
            return jsonify({"success": False, "message": "No se proporcionó código de guía"}), 400
        
        # Verificar si la guía ya ha sido procesada con pesaje de tara o más allá
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía con pesaje de tara ya procesado: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya tiene registrada la tara y no se puede modificar'
            }), 403
        
        # Guardar imagen temporalmente
        image_filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        image_file.save(image_path)
        
        # Extraer el código del proveedor del codigo_guia
        codigo_proveedor = None
        
        # Si el código de guía contiene un guion, podría seguir el formato FECHA-CODIGO
        if '-' in codigo_guia:
            codigo_proveedor = codigo_guia.split('-')[1]
        # Si el código de guía contiene un guion bajo, podría seguir el formato CODIGO_FECHA_HORA
        elif '_' in codigo_guia:
            codigo_proveedor = codigo_guia.split('_')[0]
        else:
            codigo_proveedor = codigo_guia
            
        # Verificar si hay un código de proveedor específico en la sesión o base de datos
        try:
            # Intentar obtener datos de registro para extraer código de proveedor
            datos_registro = utils.get_datos_registro(codigo_guia)
            if datos_registro and 'codigo_proveedor' in datos_registro and datos_registro['codigo_proveedor']:
                codigo_proveedor = datos_registro['codigo_proveedor']
        except Exception as e:
            logger.warning(f"Error al obtener código proveedor de registro: {str(e)}")
        
        # Enviar al webhook de Make para procesamiento
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            data = {'codigo_proveedor': codigo_proveedor}
            logger.info(f"Enviando imagen al webhook: {PESAJE_WEBHOOK_URL}")
            response = requests.post(PESAJE_WEBHOOK_URL, files=files, data=data)
        
        logger.info(f"Respuesta del Webhook: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({
                'success': False,
                'message': f"Error del webhook: {response.text}"
            }), 500
            
        # Procesar respuesta del webhook
        response_text = response.text.strip()
        if not response_text:
            logger.error("Respuesta vacía del webhook")
            return jsonify({
                'success': False,
                'message': "Respuesta vacía del webhook."
            }), 500

        if "Exitoso!" in response_text:
            import re
            peso_match = re.search(r'El peso tara es:\s*(\d+(?:\.\d+)?)\s*(?:tm)?', response_text)
            if peso_match:
                peso = peso_match.group(1)
                session['imagen_pesaje_tara'] = image_filename
                
                return jsonify({
                    'success': True,
                    'peso': peso,
                    'message': 'Peso tara detectado correctamente'
                })
            else:
                logger.error("No se pudo extraer el peso de la respuesta")
                logger.error(f"Texto de respuesta: {response_text}")
                return jsonify({
                    'success': False,
                    'message': 'No se pudo extraer el peso de la respuesta'
                })
        else:
            logger.error("El código no corresponde a la guía")
            return jsonify({
                'success': False,
                'message': 'El código no corresponde a la guía'
            })
            
    except Exception as e:
        logger.error(f"Error en pesaje tara directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})



@bp.route('/procesar_pesaje_directo', methods=['POST'])
def procesar_pesaje_directo():
    try:
        # Verificar que haya un archivo cargado
        if 'imagen' not in request.files:
            logger.error("No se envió archivo de imagen")
            return jsonify({"success": False, "message": "No se envió archivo de imagen"}), 400
            
        image_file = request.files['imagen']
        codigo_guia = request.form.get('codigo_guia')
        
        if not image_file:
            logger.error("No se seleccionó archivo de imagen")
            return jsonify({"success": False, "message": "No se seleccionó archivo de imagen"}), 400
            
        if not codigo_guia:
            logger.error("No se proporcionó código de guía")
            return jsonify({"success": False, "message": "No se proporcionó código de guía"}), 400
        
        # Verificar si la guía ya ha sido procesada
        datos_guia = utils.get_datos_guia(codigo_guia)
        if datos_guia and datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            logger.warning(f"Intento de modificar una guía ya procesada: {codigo_guia}, estado: {datos_guia.get('estado_actual')}")
            return jsonify({
                'success': False,
                'message': 'Esta guía ya ha sido procesada y no se puede modificar'
            }), 403
            
        # Guardar imagen temporalmente
        image_filename = secure_filename(f"peso_{codigo_guia}_{int(time.time())}.jpg")
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        image_file.save(image_path)
        
        # Extraer el código del proveedor del codigo_guia
        codigo_proveedor = None
        
        # Si el código de guía contiene un guion, podría seguir el formato FECHA-CODIGO
        if '-' in codigo_guia:
            codigo_proveedor = codigo_guia.split('-')[1]
        # Si el código de guía contiene un guion bajo, podría seguir el formato CODIGO_FECHA_HORA
        elif '_' in codigo_guia:
            codigo_proveedor = codigo_guia.split('_')[0]
        else:
            codigo_proveedor = codigo_guia
            
        # Verificar si hay un código de proveedor específico en la sesión o base de datos
        try:
            # Intentar obtener datos de registro para extraer código de proveedor
            datos_registro = utils.get_datos_registro(codigo_guia)
            if datos_registro and 'codigo_proveedor' in datos_registro and datos_registro['codigo_proveedor']:
                codigo_proveedor = datos_registro['codigo_proveedor']
        except Exception as e:
            logger.warning(f"Error al obtener código proveedor de registro: {str(e)}")
        
        # Enviar al webhook de Make para procesamiento
        with open(image_path, 'rb') as f:
            files = {'file': (image_filename, f, 'multipart/form-data')}
            # Enviar tanto el código de proveedor como el código de guía
            data = {
                'codigo_proveedor': codigo_proveedor,
                'codigo_guia': codigo_guia
            }
            
            logger.info(f"Enviando al webhook con datos: {data}")
            response = requests.post(PESAJE_WEBHOOK_URL, files=files, data=data)
        
        logger.info(f"Respuesta del webhook: {response.text}")
        
        if response.status_code != 200:
            logger.error(f"Error del webhook: {response.text}")
            return jsonify({
                'success': False,
                'message': f"Error del webhook: {response.text}"
            }), 500
            
        # Procesar respuesta del webhook
        response_text = response.text.strip()
        if not response_text:
            return jsonify({
                'success': False,
                'message': "Respuesta vacía del webhook."
            }), 500
            
        # Extraer la guía de transporte SAP
        codigo_guia_transporte_sap = None
        match_guia_sap = re.search(r'Guia de transporte SAP:\s*"?(\d+)"?', response_text, re.IGNORECASE)
        if match_guia_sap:
            codigo_guia_transporte_sap = match_guia_sap.group(1)
            # Guardar en la sesión para su uso posterior
            session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
            logger.info(f"Guía de transporte SAP extraída: {codigo_guia_transporte_sap}")
        
        # Buscar el peso en la respuesta usando diferentes patrones
        peso = None
        patrones = [
            r'El peso tara es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'El peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'peso bruto es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'peso es:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'Peso Bruto:\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?',
            r'Exitoso!\s*"?(\d+(?:\.\d+)?)"?\s*(?:tm)?'
        ]
        
        for patron in patrones:
            match = re.search(patron, response_text, re.IGNORECASE)
            if match:
                peso = match.group(1)
                break
        
        if peso:
            session['imagen_pesaje'] = image_filename
            result = {
                'success': True,
                'peso': peso,
                'message': 'Peso detectado correctamente'
            }
            # Añadir la guía de transporte SAP a la respuesta si está disponible
            if codigo_guia_transporte_sap:
                result['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
            
            return jsonify(result)
        else:
            # Intentar una búsqueda más general para cualquier número en la respuesta
            # como último recurso
            general_match = re.search(r'(\d+(?:\.\d+)?)', response_text)
            if general_match and "Exitoso" in response_text:
                peso = general_match.group(1)
                session['imagen_pesaje'] = image_filename
                result = {
                    'success': True,
                    'peso': peso,
                    'message': 'Peso detectado (método alternativo)'
                }
                if codigo_guia_transporte_sap:
                    result['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
                
                return jsonify(result)
            
            logger.error(f"No se pudo extraer el peso de la respuesta: {response_text}")
            return jsonify({
                'success': False,
                'message': 'No se pudo extrair el peso de la respuesta'
                })
    except Exception as e:
        logger.error(f"Error en pesaje directo: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'message': str(e)})



@bp.route('/solicitar_autorizacion_pesaje', methods=['POST'])
def solicitar_autorizacion_pesaje():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        comentarios = data.get('comentarios')
        
        if not codigo_guia or not comentarios:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })

        # Generar código de autorización aleatorio
        codigo_autorizacion = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # Guardar el código en el diccionario con tiempo de expiración
        codigos_autorizacion[codigo_guia] = {
            'codigo': codigo_autorizacion,
            'expira': datetime.now() + timedelta(minutes=30)  # Expira en 30 minutos
        }
        
        # Extraer el código del proveedor del codigo_guia
        codigo_proveedor = None
        
        # Si el código de guía contiene un guion, podría seguir el formato FECHA-CODIGO
        if '-' in codigo_guia:
            codigo_proveedor = codigo_guia.split('-')[1]
        # Si el código de guía contiene un guion bajo, podría seguir el formato CODIGO_FECHA_HORA
        elif '_' in codigo_guia:
            codigo_proveedor = codigo_guia.split('_')[0]
        else:
            codigo_proveedor = codigo_guia
            
        # Verificar si hay un código de proveedor específico en la sesión o base de datos
        try:
            # Intentar obtener datos de registro para extraer código de proveedor
            datos_registro = utils.get_datos_registro(codigo_guia)
            if datos_registro and 'codigo_proveedor' in datos_registro and datos_registro['codigo_proveedor']:
                codigo_proveedor = datos_registro['codigo_proveedor']
        except Exception as e:
            logger.warning(f"Error al obtener código proveedor de registro: {str(e)}")
        
        # Generar URL de la guía
        url_guia = url_for('pesaje', codigo=codigo_guia, _external=True)
        
        # Enviar solicitud al webhook de autorización
        response = requests.post(
            AUTORIZACION_WEBHOOK_URL,
            json={
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'url_guia': url_guia,
                'comentarios': comentarios,
                'codigo_autorizacion': codigo_autorizacion
            }
        )
        
        if response.status_code != 200:
            return jsonify({
                'success': False,
                'message': 'Error al enviar la solicitud de autorización'
            })
            
        return jsonify({
            'success': True,
            'message': 'Solicitud enviada correctamente'
            })
            
    except Exception as e:
        logger.error(f"Error en solicitud de autorización: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })



@bp.route('/validar_codigo_autorizacion', methods=['POST'])
def validar_codigo_autorizacion():
    try:
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        codigo_autorizacion = data.get('codigoAutorizacion')
        
        if not codigo_guia or not codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Faltan datos requeridos'
            })
            
        # Verificar si existe el código para esta guía
        if codigo_guia not in codigos_autorizacion:
            return jsonify({
                'success': False,
                'message': 'No hay código de autorización pendiente para esta guía'
            })
            
        # Obtener datos del código
        auth_data = codigos_autorizacion[codigo_guia]
        
        # Verificar si el código ha expirado
        if datetime.now() > auth_data['expira']:
            del codigos_autorizacion[codigo_guia]
            return jsonify({
                'success': False,
                'message': 'El código de autorización ha expirado'
            })
            
        # Verificar el código
        if auth_data['codigo'] != codigo_autorizacion:
            return jsonify({
                'success': False,
                'message': 'Código de autorización inválido'
            })
        
        # Si el código es válido, eliminarlo para que no se pueda usar nuevamente
        del codigos_autorizacion[codigo_guia]
        
        return jsonify({
            'success': True,
            'message': 'Código validado correctamente'
        })
        
    except Exception as e:
        logger.error(f"Error en validación de código: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })



@bp.route('/registrar_peso_directo', methods=['POST'])
def registrar_peso_directo():
    """
    Registra el peso bruto directo y lo almacena en la base de datos SQLite
    usando la nueva capa de acceso a datos.
    """
    try:
        # Obtener datos de la solicitud
        data = request.json
        logger.info(f"Datos recibidos para registro de peso directo: {data}")
        
        # Validar datos requeridos
        codigo_guia = data.get('codigo_guia')
        peso_bruto = data.get('peso_bruto')
        
        if not codigo_guia or not peso_bruto:
            return jsonify({'success': False, 'message': 'Faltan datos requeridos: código de guía y peso bruto'})
        
        # Usar la nueva capa de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos existentes (si los hay)
        datos_guia = dal.get_guia_complete_data(codigo_guia)
        
        # Preparar los datos para almacenar
        codigo_proveedor = None
        nombre_proveedor = None
        
        # Extraer información relevante si hay datos previos
        if datos_guia:
            codigo_proveedor = datos_guia.get('codigo_proveedor')
            nombre_proveedor = datos_guia.get('nombre_proveedor')
            logger.info(f"Datos previos encontrados para guía {codigo_guia}: proveedor={codigo_proveedor}")
        else:
            # Si no hay datos previos, extraer información del código o sesión
            logger.warning(f"No se encontraron datos previos para la guía {codigo_guia}")
            
            # Intentar obtener de la sesión
            if 'codigo_proveedor' in session:
                codigo_proveedor = session.get('codigo_proveedor')
                logger.info(f"Usando código de proveedor de sesión: {codigo_proveedor}")
            
            if 'nombre_proveedor' in session:
                nombre_proveedor = session.get('nombre_proveedor')
                logger.info(f"Usando nombre de proveedor de sesión: {nombre_proveedor}")
            
            # Si no están en la sesión, extraer del código de guía
            if not codigo_proveedor and '_' in codigo_guia:
                codigo_proveedor = codigo_guia.split('_')[0]
                logger.info(f"Extraído código de proveedor del código de guía: {codigo_proveedor}")
        
        # Si después de todo, no se pudo obtener el código de proveedor, usar un valor predeterminado
        if not codigo_proveedor:
            codigo_proveedor = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
            logger.warning(f"Usando código de proveedor predeterminado: {codigo_proveedor}")
        
        # Si no hay nombre de proveedor, usar 'No disponible'
        if not nombre_proveedor:
            nombre_proveedor = "No disponible"
            logger.warning("Nombre de proveedor no disponible")
        
        # Capturar fecha y hora actuales
        fecha_pesaje = datetime.now().strftime('%d/%m/%Y')
        hora_pesaje = datetime.now().strftime('%H:%M:%S')
        
        # Verificar si hay una guía de transporte SAP disponible
        codigo_guia_transporte_sap = data.get('codigo_guia_transporte_sap')
        if not codigo_guia_transporte_sap and 'codigo_guia_transporte_sap' in session:
            codigo_guia_transporte_sap = session.get('codigo_guia_transporte_sap')
            
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': peso_bruto,
            'tipo_pesaje': 'directo',
            'fecha_pesaje': fecha_pesaje,
            'hora_pesaje': hora_pesaje,
            'imagen_pesaje': '',  # No hay imagen en pesaje directo
            'codigo_guia_transporte_sap': codigo_guia_transporte_sap
        }
        
        # Guardar usando la nueva capa de acceso a datos
        if dal.save_pesaje_bruto(datos_pesaje):
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
            if codigo_guia_transporte_sap:
                logger.info(f"Guía de transporte SAP guardada: {codigo_guia_transporte_sap}")
        else:
            logger.warning(f"Posible problema al guardar peso para {codigo_guia}")
        
        # Actualizar datos en sesión
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = 'directo'
        session['fecha_pesaje'] = fecha_pesaje
        session['hora_pesaje'] = hora_pesaje
        if codigo_guia_transporte_sap:
            session['codigo_guia_transporte_sap'] = codigo_guia_transporte_sap
        
        # Generar URL de redirección a la página de resultados
        redirect_url = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        
        # Registrar la URL para depuración
        logger.info(f"Redirigiendo a la URL: {redirect_url}")
        
        return jsonify({
            'success': True,
            'message': f'Peso bruto registrado: {peso_bruto}kg',
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error en registrar_peso_directo: {str(e)}")
        logger.error(traceback.format_exc())  # Añadir stack trace para mejor diagnóstico
        return jsonify({
            'success': False,
            'message': f'Error al registrar peso: {str(e)}'
        })



@bp.route('/registrar_peso_virtual', methods=['POST'])
def registrar_peso_virtual():
    """
    Registra el peso bruto manual o virtual usando la nueva capa de acceso a datos.
    Puede recibir datos en formato JSON o form-data (con imagen).
    """
    try:
        # Verificar si los datos vienen en JSON o en form-data
        if request.is_json:
            data = request.json
            codigo_guia = data.get('codigo_guia')
            peso_bruto = data.get('peso_bruto')
            tipo_pesaje = data.get('tipo_pesaje', 'manual')  # Por defecto es manual
            
            imagen_path = ''  # Sin imagen en solicitud JSON
        else:
            # Datos de formulario
            codigo_guia = request.form.get('codigo_guia')
            peso_bruto = request.form.get('peso_bruto')
            tipo_pesaje = request.form.get('tipo_pesaje', 'manual')
            
            # Procesar imagen si existe
            imagen_path = ''
            if 'imagen' in request.files and request.files['imagen'].filename:
                imagen = request.files['imagen']
                # Crear directorio si no existe
                img_dir = os.path.join(app.static_folder, 'pesajes', codigo_guia)
                os.makedirs(img_dir, exist_ok=True)
                
                # Guardar imagen
                filename = f"pesaje_{utils.generate_unique_id()}.jpg"
                file_path = os.path.join(img_dir, filename)
                imagen.save(file_path)
                
                # Guardar ruta relativa para acceso web
                imagen_path = os.path.join('static', 'pesajes', codigo_guia, filename)
        
        # Validar datos requeridos
        if not codigo_guia or not peso_bruto:
            return jsonify({'success': False, 'message': 'Faltan datos requeridos: código de guía y peso bruto'})
        
        # Usar la nueva capa de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos existentes (si los hay)
        datos_guia = dal.get_guia_complete_data(codigo_guia)
        
        # Preparar los datos para almacenar
        codigo_proveedor = None
        nombre_proveedor = None
        
        # Extraer información relevante si hay datos previos
        if datos_guia:
            codigo_proveedor = datos_guia.get('codigo_proveedor')
            nombre_proveedor = datos_guia.get('nombre_proveedor')
            logger.info(f"Datos previos encontrados para guía {codigo_guia}")
        else:
            # Si no hay datos previos, extraer información del código o sesión
            logger.warning(f"No se encontraron datos previos para la guía {codigo_guia}")
            
            # Intentar obtener de la sesión
            if 'codigo_proveedor' in session:
                codigo_proveedor = session.get('codigo_proveedor')
            
            if 'nombre_proveedor' in session:
                nombre_proveedor = session.get('nombre_proveedor')
            
            # Si no están en la sesión, extraer del código de guía
            if not codigo_proveedor and '_' in codigo_guia:
                codigo_proveedor = codigo_guia.split('_')[0]
        
        # Si después de todo, no se pudo obtener el código de proveedor, usar un valor predeterminado
        if not codigo_proveedor:
            codigo_proveedor = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
            logger.warning(f"Usando código de proveedor predeterminado: {codigo_proveedor}")
        
        # Si no hay nombre de proveedor, usar 'No disponible'
        if not nombre_proveedor:
            nombre_proveedor = "No disponible"
            logger.warning("Nombre de proveedor no disponible")
        
        # Capturar fecha y hora actuales
        fecha_pesaje = datetime.now().strftime('%d/%m/%Y')
        hora_pesaje = datetime.now().strftime('%H:%M:%S')
        
        # Preparar datos para almacenar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'peso_bruto': peso_bruto,
            'tipo_pesaje': tipo_pesaje,
            'fecha_pesaje': fecha_pesaje,
            'hora_pesaje': hora_pesaje,
            'imagen_pesaje': imagen_path
        }
        
        # Guardar usando la nueva capa de acceso a datos
        if dal.save_pesaje_bruto(datos_pesaje):
            logger.info(f"Peso registrado correctamente para {codigo_guia}: {peso_bruto}kg")
        else:
            logger.warning(f"Posible problema al guardar peso para {codigo_guia}")
        
        # Actualizar datos en sesión
        session['peso_bruto'] = peso_bruto
        session['tipo_pesaje'] = tipo_pesaje
        session['fecha_pesaje'] = fecha_pesaje
        session['hora_pesaje'] = hora_pesaje
        
        # Generar URL de redirección a la página de resultados
        redirect_url = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia)
        
        # Registrar la URL para depuración
        logger.info(f"Redirigiendo a la URL después de pesaje virtual: {redirect_url}")
        
        return jsonify({
            'success': True,
            'message': f'Peso bruto registrado: {peso_bruto}kg',
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error en registrar_peso_virtual: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False, 
            'message': f'Error al registrar peso: {str(e)}'
        })



@bp.route('/pesajes', methods=['GET'])
def lista_pesajes():
    """
    Muestra la lista de registros de pesaje desde la base de datos SQLite.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        tipo_pesaje = request.args.get('tipo_pesaje', '')

        # Preparar filtros para la consulta a la base de datos
        filtros = {}
        if fecha_desde:
            filtros['fecha_desde'] = fecha_desde
        if fecha_hasta:
            filtros['fecha_hasta'] = fecha_hasta
        if codigo_proveedor:
            filtros['codigo_proveedor'] = codigo_proveedor
        if nombre_proveedor:
            filtros['nombre_proveedor'] = nombre_proveedor
        if tipo_pesaje:
            filtros['tipo_pesaje'] = tipo_pesaje
        
        # Obtener datos de la base de datos
        from db_operations import get_pesajes_bruto, get_clasificacion_by_codigo_guia
        pesajes = get_pesajes_bruto(filtros)
        
        # Verificar el estado de clasificación para cada pesaje
        for pesaje in pesajes:
            # Si no tiene estado_actual, asumimos que está en pesaje_completado
            if not pesaje.get('estado_actual'):
                pesaje['estado_actual'] = 'pesaje_completado'
                
            # Verificar si existe una clasificación para este código de guía
            clasificacion = get_clasificacion_by_codigo_guia(pesaje['codigo_guia'])
            if clasificacion:
                # Si existe clasificación, actualizar el estado
                pesaje['estado_actual'] = 'clasificacion_completada'
            
            # También verificar en el sistema de archivos (legado)
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
            archivo_clasificacion = os.path.join(clasificaciones_dir, f"clasificacion_{pesaje['codigo_guia']}.json")
            if os.path.exists(archivo_clasificacion):
                pesaje['estado_actual'] = 'clasificacion_completada'
        
        # Preparar filtros para la plantilla
        filtros_template = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'tipo_pesaje': tipo_pesaje
        }
        
        return render_template('pesajes_lista.html', pesajes=pesajes, filtros=filtros_template)
        
    except Exception as e:
        logger.error(f"Error listando pesajes: {str(e)}")
        flash(f"Error al cargar la lista de pesajes: {str(e)}", "error")
        return redirect(url_for('home'))



@bp.route('/verificar_placa_pesaje', methods=['POST'])
def verificar_placa_pesaje():
    """
    Procesa una imagen de placa durante el pesaje para verificar si coincide con la placa registrada.
    """
    try:
        logger.info("Iniciando verificación de placa en pesaje")
        
        if 'placa_foto' not in request.files:
            logger.warning("No se encontró imagen de placa en la solicitud")
            return jsonify({
                'success': False,
                'message': 'No se encontró imagen de placa'
            })
        
        placa_foto = request.files['placa_foto']
        codigo_guia = request.form.get('codigo_guia')
        placa_registrada = request.form.get('placa_registrada', '').strip().upper()
        
        if not codigo_guia:
            logger.warning("Falta el código de guía en la solicitud")
            return jsonify({
                'success': False,
                'message': 'Falta el código de guía'
            })
        
        if not placa_registrada:
            logger.warning("No hay placa registrada para comparar")
            return jsonify({
                'success': False,
                'message': 'No hay placa registrada para comparar'
            })
        
        if not placa_foto.filename:
            logger.warning("El archivo de imagen de placa está vacío")
            return jsonify({
                'success': False,
                'message': 'El archivo de imagen está vacío'
            })
        
        if not allowed_file(placa_foto.filename):
            logger.warning(f"Tipo de archivo no permitido: {placa_foto.filename}")
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido'
            })
        
        # Guardar la imagen temporalmente
        filename = secure_filename(f"verificacion_placa_{codigo_guia}_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        placa_foto.save(temp_path)
        
        logger.info(f"Imagen de placa guardada temporalmente: {temp_path}")
        
        # Enviar la imagen al webhook para procesamiento
        result = process_plate_image(temp_path, filename)
        
        if result.get("result") != "ok":
            logger.warning(f"Error al procesar la placa: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': f"Error al detectar la placa: {result.get('message')}"
            })
        
        # Obtener el texto de la placa detectada
        placa_detectada = result.get("plate_text", "").strip().upper()
        
        if not placa_detectada:
            logger.warning("No se pudo detectar el texto de la placa")
            return jsonify({
                'success': False,
                'message': 'No se pudo detectar el texto de la placa'
            })
        
        # Comparar la placa detectada con la registrada
        # Normalizamos ambas placas para una comparación más flexible
        placa_registrada_norm = ''.join(c for c in placa_registrada if c.isalnum())
        placa_detectada_norm = ''.join(c for c in placa_detectada if c.isalnum())
        
        # Verificar si las placas coinciden
        coincide = placa_registrada_norm == placa_detectada_norm
        
        logger.info(f"Resultado de verificación: Placa registrada: {placa_registrada}, Placa detectada: {placa_detectada}, Coincide: {coincide}")
        
        # Guardar esta verificación en la información de la guía
        try:
            datos_guia = utils.get_datos_guia(codigo_guia)
            if datos_guia:
                if 'verificaciones_placa' not in datos_guia:
                    datos_guia['verificaciones_placa'] = []
                
                datos_guia['verificaciones_placa'].append({
                    'fecha': datetime.now().strftime('%d/%m/%Y'),
                    'hora': datetime.now().strftime('%H:%M:%S'),
                    'placa_registrada': placa_registrada,
                    'placa_detectada': placa_detectada,
                    'coincide': coincide
                })
        except Exception as e:
            logger.error(f"Error al guardar verificación de placa: {str(e)}")

        return jsonify({
            'success': True,
            'placa_detectada': placa_detectada,
            'placa_registrada': placa_registrada,
            'coincide': coincide
        })
        
    except Exception as e:
        logger.error(f"Error en verificación de placa: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al procesar la imagen: {str(e)}'
        })



@bp.route('/pesaje-neto/<codigo>', methods=['GET'])
def pesaje_neto(codigo):
    """
    Maneja la vista de pesaje neto y el procesamiento del mismo
    """
    try:
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        
        # Si no se encuentra en utils, buscar directamente en la base de datos
        if not datos_guia:
            logger.info(f"Intentando obtener datos de la guía {codigo_guia_completo} directamente de la base de datos")
            try:
                from db_operations import get_pesaje_bruto_by_codigo_guia
                from db_utils import get_entry_record_by_guide_code
                
                # Intentar obtener desde db_operations
                datos_guia = get_pesaje_bruto_by_codigo_guia(codigo_guia_completo)
                
                # Si todavía no lo encuentra, intentar con entry records
                if not datos_guia:
                    logger.info(f"Intentando obtener desde entry records para {codigo_guia_completo}")
                    registro = get_entry_record_by_guide_code(codigo_guia_completo)
                    if registro:
                        # Convertir registro a formato de datos_guia
                        datos_guia = {
                            'codigo_guia': registro.get('codigo_guia'),
                            'codigo_proveedor': registro.get('codigo_proveedor'),
                            'nombre_proveedor': registro.get('nombre_proveedor'),
                            'placa': registro.get('placa'),
                            'transportador': registro.get('transportador'),
                            'racimos': registro.get('cantidad_racimos'),
                            'fecha_registro': registro.get('fecha_registro'),
                            'hora_registro': registro.get('hora_registro'),
                            'estado_actual': 'registro_completado'
                        }
                        logger.info(f"Datos obtenidos desde entry records para {codigo_guia_completo}")
            except Exception as e:
                logger.error(f"Error al intentar obtener datos de la base de datos: {str(e)}")
                logger.error(traceback.format_exc())
                
        if not datos_guia:
            logger.error(f"No se pudo encontrar información para la guía: {codigo_guia_completo}")
            flash('Guía no encontrada', 'error')
            return render_template('error.html', message="Guía no encontrada"), 404

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje.pesaje_neto', codigo=codigo_guia_completo))

        # Verificar si la guía ya tiene registrado el peso neto (para tara) o ha sido completada
        if datos_guia.get('estado_actual') in ['pesaje_tara_completado', 'registro_completado']:
            flash("Esta guía ya tiene registrado el peso neto y no se puede modificar.", "warning")
            return render_template('error.html', 
                          message="Esta guía ya tiene registrado el peso neto y no se puede modificar. Por favor, contacte al administrador si necesita realizar cambios."), 403

        # Verificar que el pesaje esté completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            flash("El pesaje no ha sido completado para esta guía.", "warning")
            return redirect(url_for('pesaje', codigo=codigo_guia_completo))

        # Renderizar template de pesaje neto
        return render_template('pesaje_neto.html', datos=datos_guia)
                           
    except Exception as e:
        logger.error(f"Error en pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando pesaje neto"), 500



@bp.route('/registrar_peso_neto_directo', methods=['POST'])
def registrar_peso_neto_directo():
    """Registra el peso neto para una guía específica usando el método directo."""
    
    # Inicializar variables
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        logger.info("Procesando solicitud de registro de peso neto directo")
        
        # Obtener datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        peso_tara = request.form.get('peso_tara')
        peso_producto = request.form.get('peso_producto', '')
        
        data_received = {k: v for k, v in request.form.items()}
        logger.info(f"Datos recibidos para pesaje neto directo: {data_received}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos del pesaje
        now = datetime.now()
        
        # Manejar archivos de imágenes si están presentes
        fotos_guardadas = []
        
        if 'fotos[]' in request.files:
            fotos = request.files.getlist('fotos[]')
            
            if fotos and any(foto.filename for foto in fotos):
                # Crear directorio para las fotos si no existe
                fotos_pesaje_neto_dir = os.path.join(app.static_folder, 'fotos_pesaje_neto', codigo_guia)
                os.makedirs(fotos_pesaje_neto_dir, exist_ok=True)
                
                # Guardar cada foto
                for foto in fotos:
                    if foto and foto.filename:
                        # Crear nombre de archivo único
                        timestamp = now.strftime("%Y%m%d%H%M%S")
                        random_suffix = os.urandom(4).hex()
                        filename = f"neto_{timestamp}_{random_suffix}.jpg"
                        
                        # Guardar archivo
                        filepath = os.path.join(fotos_pesaje_neto_dir, filename)
                        foto.save(filepath)
                        
                        # Guardar ruta relativa
                        fotos_guardadas.append(os.path.join('fotos_pesaje_neto', codigo_guia, filename))
        
        # Actualizar la sesión
        session['codigo_guia'] = codigo_guia
        session['peso_tara'] = peso_tara
        session['tipo_pesaje_neto'] = 'directo'
        session['hora_pesaje_neto'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje_neto'] = now.strftime('%d/%m/%Y')
        
        if fotos_guardadas:
            session['fotos_pesaje_neto'] = fotos_guardadas
            
        # Guardar en la base de datos usando DAL
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara,
            'peso_producto': peso_producto if peso_producto else None,
            'tipo_pesaje_neto': 'directo',
            'fecha_pesaje_neto': now.strftime('%d/%m/%Y'),
            'hora_pesaje_neto': now.strftime('%H:%M:%S'),
            'fotos_pesaje_neto': fotos_guardadas
        }
        
        if dal.save_pesaje_neto(datos_pesaje):
            logger.info(f"Pesaje neto directo guardado correctamente para guía {codigo_guia}")
            
            # Redirigir a la página de resultados
            return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))
        else:
            logger.error(f"Error al guardar pesaje neto directo en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
            
    except Exception as e:
        logger.error(f"Error al registrar peso neto directo: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar peso neto directo: {str(e)}"
            
        flash(error_message, 'danger')
        return redirect(url_for('pesaje_neto', codigo=codigo_guia if 'codigo_guia' in locals() else None))


@bp.route('/registrar_peso_neto_virtual', methods=['POST'])
def registrar_peso_neto_virtual():
    """Registra el peso neto para una guía específica usando el método virtual."""
    
    # Inicializar variables
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        logger.info("Procesando solicitud de registro de peso neto virtual")
        
        # Primero procesamos los datos JSON de la solicitud
        if not request.is_json:
            error_message = "Se esperaba una solicitud JSON"
            raise ValueError(error_message)
        
        data = request.get_json()
        data_received = data
        
        # Obtener datos de la solicitud JSON
        codigo_guia = data.get('codigo_guia')
        peso_tara = data.get('peso_tara')
        peso_producto = data.get('peso_producto', '')
        imagen_base64 = data.get('imagen')
        
        logger.info(f"Datos recibidos para pesaje neto virtual: codigo_guia={codigo_guia}, peso_tara={peso_tara}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos del pesaje
        now = datetime.now()
        
        # Manejar la imagen base64 si está presente
        fotos_guardadas = []
        
        if imagen_base64:
            try:
                # Decodificar la imagen base64
                import base64
                imagen_bytes = base64.b64decode(imagen_base64.split(',')[1] if ',' in imagen_base64 else imagen_base64)
                
                # Crear directorio para la imagen si no existe
                fotos_pesaje_neto_dir = os.path.join(app.static_folder, 'fotos_pesaje_neto', codigo_guia)
                os.makedirs(fotos_pesaje_neto_dir, exist_ok=True)
                
                # Crear nombre de archivo único
                timestamp = now.strftime("%Y%m%d%H%M%S")
                random_suffix = os.urandom(4).hex()
                filename = f"neto_virtual_{timestamp}_{random_suffix}.jpg"
                
                # Guardar archivo
                filepath = os.path.join(fotos_pesaje_neto_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(imagen_bytes)
                
                # Guardar ruta relativa
                fotos_guardadas.append(os.path.join('fotos_pesaje_neto', codigo_guia, filename))
                
            except Exception as e:
                logger.error(f"Error al procesar imagen base64: {str(e)}")
                logger.error(traceback.format_exc())
        
        # Actualizar la sesión
        session['codigo_guia'] = codigo_guia
        session['peso_tara'] = peso_tara
        session['tipo_pesaje_neto'] = 'virtual'
        session['hora_pesaje_neto'] = now.strftime('%H:%M:%S')
        session['fecha_pesaje_neto'] = now.strftime('%d/%m/%Y')
        session['fotos_pesaje_neto'] = fotos_guardadas
        
        # Registro para depuración
        logger.info(f"  codigo_guia: {session.get('codigo_guia')}")
        logger.info(f"  peso_tara: {session.get('peso_tara')}")
        logger.info(f"  tipo_pesaje_neto: {session.get('tipo_pesaje_neto')}")
        logger.info(f"  fotos_pesaje_neto: {session.get('fotos_pesaje_neto')}")
        
        # Guardar en la base de datos usando DAL
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara,
            'peso_producto': peso_producto if peso_producto else None,
            'tipo_pesaje_neto': 'virtual',
            'fecha_pesaje_neto': now.strftime('%d/%m/%Y'),
            'hora_pesaje_neto': now.strftime('%H:%M:%S'),
            'fotos_pesaje_neto': fotos_guardadas
        }
        
        if dal.save_pesaje_neto(datos_pesaje):
            logger.info(f"Pesaje neto virtual guardado correctamente para guía {codigo_guia}")
            
            # Devolver respuesta JSON con la URL de redirección
            return jsonify({
                'status': 'success',
                'message': 'Pesaje neto virtual registrado correctamente',
                'redirect_url': url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
            })
        else:
            logger.error(f"Error al guardar pesaje neto virtual en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
            
    except Exception as e:
        logger.error(f"Error al registrar peso neto virtual: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar peso neto virtual: {str(e)}"
            
        return jsonify({
            'status': 'error',
            'message': error_message
        }), 400


@bp.route('/pesajes-neto-lista', methods=['GET'])
def lista_pesajes_neto():
    """
    Muestra la lista de registros de pesaje neto desde la base de datos SQLite.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_inicio = request.args.get('fecha_inicio', '')
        fecha_fin = request.args.get('fecha_fin', '')
        codigo_guia = request.args.get('codigo_guia', '')
        
        # Preparar filtros para la consulta a la base de datos
        filtros = {}
        if fecha_inicio:
            filtros['fecha_desde'] = fecha_inicio
        if fecha_fin:
            filtros['fecha_hasta'] = fecha_fin
        if codigo_guia:
            filtros['codigo_guia'] = codigo_guia
        
        # Obtener datos de la base de datos
        from db_operations import get_pesajes_neto
        pesajes = get_pesajes_neto(filtros)
        
        # Preparar filtros para la plantilla
        filtros_template = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'codigo_guia': codigo_guia
        }
        
        return render_template('pesajes_neto_lista.html', pesajes=pesajes, filtros=filtros_template)
        
    except Exception as e:
        logger.error(f"Error listando pesajes neto: {str(e)}")
        flash(f"Error al cargar la lista de pesajes neto: {str(e)}", "error")
        return redirect(url_for('home'))



@bp.route('/registrar_peso_neto', methods=['POST'])
def registrar_peso_neto():
    """Registra el peso neto para una guía específica."""
    
    # Inicializar registro de errores con información detallada
    error_message = None
    data_received = {}
    
    try:
        # Obtener el objeto de acceso a datos
        from data_access import DataAccess
        dal = DataAccess(app)
        
        # Obtener datos de la solicitud
        if request.is_json:
            data = request.get_json()
            data_received = data
            codigo_guia = data.get('codigo_guia')
            peso_tara = data.get('peso_tara')
            tipo_pesaje = data.get('tipo_pesaje', 'directo')
        else:
            data_received = {k: v for k, v in request.form.items()}
            codigo_guia = request.form.get('codigo_guia')
            peso_tara = request.form.get('peso_tara')
            tipo_pesaje = request.form.get('tipo_pesaje', 'directo')
        
        logger.info(f"Registrando pesaje neto para guía {codigo_guia}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara:
            error_message = "El peso tara es obligatorio"
            raise ValueError(error_message)
        
        # Preparar datos para guardar
        datos_pesaje = {
            'codigo_guia': codigo_guia,
            'peso_tara': peso_tara
        }
        
        # Obtener datos adicionales del formulario o JSON
        for key in ['peso_bruto', 'peso_producto', 'tipo_pesaje_neto', 'imagen_pesaje_neto']:
            if request.is_json:
                if key in data:
                    datos_pesaje[key] = data.get(key)
            else:
                if key in request.form:
                    datos_pesaje[key] = request.form.get(key)
        
        # Manejar imagen si está presente
        if 'imagen_pesaje_neto' not in datos_pesaje and 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename:
                # Guardar imagen temporalmente
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                filename = f"pesaje_neto_{codigo_guia}_{timestamp}.jpg"
                
                # Asegurarse de que el directorio existe
                os.makedirs('static/uploads', exist_ok=True)
                
                # Guardar archivo
                filepath = os.path.join('static/uploads', filename)
                file.save(filepath)
                
                # Guardar ruta relativa en datos_pesaje
                datos_pesaje['imagen_pesaje_neto'] = f"uploads/{filename}"
        
        # Establecer fecha y hora actuales si no se proporcionan
        if 'fecha_pesaje_neto' not in datos_pesaje:
            datos_pesaje['fecha_pesaje_neto'] = datetime.now().strftime('%d/%m/%Y')
        
        if 'hora_pesaje_neto' not in datos_pesaje:
            datos_pesaje['hora_pesaje_neto'] = datetime.now().strftime('%H:%M:%S')
        
        # Guardar datos utilizando la capa DAL
        if dal.save_pesaje_neto(datos_pesaje):
            # Actualizar datos en sesión
            session['codigo_guia'] = codigo_guia
            session['peso_tara'] = peso_tara
            
            # Si peso_neto está en datos_pesaje, usarlo; si no, será calculado por la función DAL
            if 'peso_neto' in datos_pesaje:
                session['peso_neto'] = datos_pesaje['peso_neto']
            
            # Determinar redirección basada en si es una solicitud AJAX
            if request.is_json:
                return jsonify({
                    'status': 'success',
                    'message': 'Pesaje neto registrado correctamente',
                    'redirect_url': url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
                })
            else:
                return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))
        else:
            logger.error(f"Error al guardar pesaje neto en la base de datos para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto en la base de datos"
            raise Exception(error_message)
    
    except Exception as e:
        logger.error(f"Error al registrar pesaje neto: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar pesaje neto: {str(e)}"
        
        if request.is_json:
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 400
        else:
            flash(error_message, 'danger')
            return redirect(url_for('pesaje_neto'))


