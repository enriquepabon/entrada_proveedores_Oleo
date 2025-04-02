from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.clasificacion import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/clasificacion/<codigo>', methods=['GET'])
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
        
        # Obtener el código guía completo del archivo HTML más reciente
        guias_folder = app.config['GUIAS_FOLDER']
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

        # Verificar si ya existe un archivo de clasificación para este código de guía COMPLETO
        # (no solo el código base como antes)
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        archivo_clasificacion_exacto = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_completo}.json")
        
        if os.path.exists(archivo_clasificacion_exacto):
            logger.info(f"Se encontró un archivo de clasificación exacto para la guía actual: {codigo_guia_completo}")
            # Redirigir a la página de resultados de clasificación si ya existe para esta guía específica
            return redirect(url_for('ver_resultados_clasificacion', url_guia=codigo_guia_completo))

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá de la clasificación
        if datos_guia.get('estado_actual') in ['clasificacion_completada', 'pesaje_tara_completado', 'registro_completado']:
            flash("Esta guía ya ha sido clasificada y no se puede modificar.", "warning")
            return render_template('error.html', 
                          message="Esta guía ya ha sido clasificada y no se puede modificar. Por favor, contacte al administrador si necesita realizar cambios."), 403

        # Verificar si hay datos en la sesión para peso
        tiene_peso_en_sesion = False
        if peso_bruto_session and estado_actual_session == 'pesaje_completado':
            tiene_peso_en_sesion = True
            logger.info(f"La sesión tiene datos de peso: {peso_bruto_session}, estado: {estado_actual_session}")

        # Obtener datos de la guía usando el código completo
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia_completo}")
            return render_template('error.html', message="Guía no encontrada"), 404

        logger.info(f"Datos de guía obtenidos: peso_bruto={datos_guia.get('peso_bruto')}, estado_actual={datos_guia.get('estado_actual')}")

        # Si hay peso en la sesión, asegurarnos de que datos_guia también lo tenga
        if tiene_peso_en_sesion and not datos_guia.get('peso_bruto'):
            logger.info(f"Actualizando datos_guia con información de la sesión")
            datos_guia['peso_bruto'] = peso_bruto_session
            datos_guia['tipo_pesaje'] = session.get('tipo_pesaje')
            datos_guia['hora_pesaje'] = session.get('hora_pesaje')
            datos_guia['fecha_pesaje'] = session.get('fecha_pesaje')
            datos_guia['estado_actual'] = 'pesaje_completado'
            
            # También actualizamos el archivo HTML
            html_content = render_template(
                'guia_template.html',
                **datos_guia
            )
            
            html_filename = f'guia_{codigo_guia_completo}.html'
            html_path = os.path.join(app.config['GUIAS_FOLDER'], html_filename)
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            logger.info(f"Archivo de guía actualizado con datos de sesión: {html_path}")

        # Verificar que el pesaje esté completado (desde datos_guia o desde la sesión)
        tiene_peso_en_guia = datos_guia.get('peso_bruto') and datos_guia.get('estado_actual') == 'pesaje_completado'
        pesaje_completado = tiene_peso_en_guia or tiene_peso_en_sesion
        
        logger.info(f"Verificación de pesaje completado: {pesaje_completado} (guía: {tiene_peso_en_guia}, sesión: {tiene_peso_en_sesion})")
        
        if not pesaje_completado:
            logger.error(f"Pesaje no completado para guía {codigo_guia_completo}. Estado en guía: {datos_guia.get('estado_actual')}, Estado en sesión: {estado_actual_session}")
            return render_template('error.html', 
                                message="¡Error! Debe completar el proceso de pesaje antes de realizar la clasificación"), 400

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            logger.info(f"Redirigiendo a URL con código guía completo: {codigo_guia_completo}")
            return redirect(url_for('clasificacion.clasificacion', codigo=codigo_guia_completo))

        # Renderizar template de clasificación
        return render_template('clasificacion.html', 
                            codigo=datos_guia.get('codigo'),
                            codigo_guia=codigo_guia_completo,
                            nombre=datos_guia.get('nombre') or datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                            peso_bruto=datos_guia.get('peso_bruto'),
                            tipo_pesaje=datos_guia.get('tipo_pesaje'),
                            fecha_registro=datos_guia.get('fecha_registro'),
                            hora_registro=datos_guia.get('hora_registro'),
                            fecha_pesaje=datos_guia.get('fecha_pesaje'),
                            hora_pesaje=datos_guia.get('hora_pesaje'),
                            transportador=datos_guia.get('transportador'),
                            placa=datos_guia.get('placa'),
                            guia_transporte=datos_guia.get('guia_transito'),
                            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap'))
                           
    except Exception as e:
        logger.error(f"Error en clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando clasificación"), 500



@bp.route('/registrar_clasificacion', methods=['POST'])
def registrar_clasificacion():
    """
    Registra la clasificación manual de racimos.
    """
    try:
        codigo_guia = request.form.get('codigo_guia')
        if not codigo_guia:
            logger.error("No se proporcionó un código de guía")
            return jsonify({
                'success': False,
                'message': 'Error: No se proporcionó un código de guía'
            })
        
        # Crear directorios para imágenes y clasificaciones si no existen
        fotos_temp_dir = os.path.join(app.static_folder, 'fotos_racimos_temp')
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        os.makedirs(fotos_temp_dir, exist_ok=True)
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Guardar el código original para referencia
        codigo_guia_original = codigo_guia
        
        # Obtener el código base (sin timestamp ni versión)
        codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
        
        # Extraer código proveedor y asegurar formato correcto
        codigo_proveedor = codigo_base
        if re.match(r'\d+[aA]?$', codigo_proveedor):
            if codigo_proveedor.endswith('a'):
                codigo_proveedor = codigo_proveedor[:-1] + 'A'
            elif not codigo_proveedor.endswith('A'):
                codigo_proveedor = codigo_proveedor + 'A'
                
        # Intentar encontrar el código guía completo del archivo HTML más reciente
        # para asegurar consistencia con el proceso de pesaje
        guias_folder = app.config['GUIAS_FOLDER']
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            # Ordenar por fecha de modificación, más reciente primero
            guias_files.sort(key=os.path.getmtime, reverse=True)
            # Extraer el codigo_guia del nombre del archivo más reciente
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_a_usar = latest_guia[5:-5]  # Remover 'guia_' y '.html'
            logger.info(f"Código guía completo obtenido del archivo HTML: {codigo_guia_a_usar}")
        else:
            # Si no hay archivos HTML con este código base, intentar buscar en la base de datos
            from db_operations import get_pesaje_bruto_by_codigo_guia
            pesaje = get_pesaje_bruto_by_codigo_guia(codigo_base)
            if pesaje and 'codigo_guia' in pesaje:
                codigo_guia_a_usar = pesaje['codigo_guia']
                logger.info(f"Código guía completo obtenido de la base de datos: {codigo_guia_a_usar}")
            else:
                # Si no se encuentra, usar el código original
                codigo_guia_a_usar = codigo_guia_original
                logger.info(f"Usando código guía original: {codigo_guia_a_usar}")
        
        # Obtener datos de la guía para recuperar el nombre del proveedor
        datos_guia = utils.get_datos_guia(codigo_guia_a_usar)
        nombre_proveedor = datos_guia.get('nombre') if datos_guia else 'No disponible'
        
        # Preparar datos de clasificación
        fecha_clasificacion = datetime.now().strftime('%d/%m/%Y')
        hora_clasificacion = datetime.now().strftime('%H:%M:%S')
        
        datos_clasificacion = {
            'codigo_guia': codigo_guia_a_usar,
            'codigo_guia_original': codigo_guia_original,
            'codigo_proveedor': codigo_proveedor,  # Guardar el código del proveedor
            'nombre_proveedor': nombre_proveedor,  # Guardar el nombre del proveedor
            'fecha_clasificacion': fecha_clasificacion,
            'hora_clasificacion': hora_clasificacion,
            'clasificacion_manual': {},
            'imagenes': {}
        }
        
        # Recopilar datos de clasificación manual
        clasificacion_manual = {}
        
        # Verificar primero si hay datos en el formato "cantidad_*"
        for key in request.form:
            if key.startswith('cantidad_'):
                categoria = key.replace('cantidad_', '')
                try:
                    clasificacion_manual[categoria] = int(request.form[key])
                except:
                    clasificacion_manual[categoria] = 0
        
        # Verificar si hay datos en el formato usado por el formulario de clasificación.html
        # donde los IDs son directamente los nombres de las categorías
        categoria_mapping = {
            'verdes': 'verdes',
            'sobremaduros': 'sobremaduros', 
            'danio-corona': 'danio_corona',
            'pendunculo-largo': 'pendunculo_largo',
            'podridos': 'podridos'
        }
        
        # Si no se han encontrado datos por el primer método, revisar en el formato directo
        if not clasificacion_manual:
            for form_id, categoria in categoria_mapping.items():
                if form_id in request.form and request.form[form_id]:
                    try:
                        clasificacion_manual[categoria] = int(float(request.form[form_id]))
                    except:
                        clasificacion_manual[categoria] = 0
        
        # También verificar el formato "clasificacion_X_peso" que viene del JS
        if not clasificacion_manual:
            for i, categoria in enumerate(['verdes', 'sobremaduros', 'danio_corona', 'pendunculo_largo', 'podridos']):
                key_name = f'clasificacion_{i}_peso'
                if key_name in request.form and request.form[key_name]:
                    try:
                        clasificacion_manual[categoria] = int(float(request.form[key_name]))
                    except:
                        clasificacion_manual[categoria] = 0
        
        # Registrar las cantidades de clasificación y el formato en que se encontraron
        logger.info(f"Clasificación manual registrada: {clasificacion_manual}")
        logger.info(f"Claves del formulario: {list(request.form.keys())}")
        datos_clasificacion['clasificacion_manual'] = clasificacion_manual
        
        # Guardar imágenes adjuntas
        imagenes = {}
        fotos_paths = []
        
        # Procesar cada imagen regular (no asociada a una clasificación específica)
        for idx in range(1, 4):  # Permitimos hasta 3 fotos regulares
            foto_key = f'foto{idx}'
            if foto_key in request.files:
                file = request.files[foto_key]
                if file and file.filename and allowed_file(file.filename):
                    # Usar el nombre de la guía para prevenir colisiones
                    filename = f"foto{idx}_{codigo_guia_a_usar}.jpg"
                    file_path = os.path.join(fotos_temp_dir, filename)
                    file.save(file_path)
                    
                    # Guardar rutas para el procesamiento automático
                    fotos_paths.append(file_path)
                    
                    # Guardar ruta web para la interfaz
                    web_path = f"fotos_racimos_temp/{filename}"
                    imagenes[foto_key] = web_path
                    datos_clasificacion['imagenes'][foto_key] = web_path
        
        # Almacenar datos en la base de datos
        from db_operations import store_clasificacion
        store_clasificacion(datos_clasificacion)
        
        # Preparar datos para el procesamiento automático
        clasificacion_data = {
            'id': f"Clasificacion_{codigo_guia_a_usar}",
            'fecha_registro': fecha_clasificacion,
            'hora_registro': hora_clasificacion,
            'codigo_proveedor': codigo_proveedor,  # Incluir código del proveedor
            'nombre_proveedor': nombre_proveedor,  # Incluir nombre del proveedor
            'fotos': fotos_paths,
            'estado': 'en_proceso',
            'clasificacion_manual': clasificacion_manual,
            'clasificacion_automatica': {
                "verdes": {"cantidad": 0, "porcentaje": 0},
                "maduros": {"cantidad": 0, "porcentaje": 0}, 
                "sobremaduros": {"cantidad": 0, "porcentaje": 0},
                "podridos": {"cantidad": 0, "porcentaje": 0},
                "danio_corona": {"cantidad": 0, "porcentaje": 0},
                "pendunculo_largo": {"cantidad": 0, "porcentaje": 0}
            },
            'resultados_por_foto': {}
        }
        
        # Guardar en archivo JSON para procesamiento automático
        json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_a_usar}.json")
        with open(json_path, 'w') as f:
            json.dump(clasificacion_data, f, indent=4)
            
        logger.info(f"Guardados datos de clasificación para guía {codigo_guia_a_usar} con clasificación manual: {clasificacion_manual}")
        
        # Crear directorio específico para las fotos de esta guía
        guia_fotos_dir = os.path.join(fotos_temp_dir, codigo_guia_a_usar)
        os.makedirs(guia_fotos_dir, exist_ok=True)
        
        # Mover las fotos al directorio específico de la guía
        for foto_path in fotos_paths:
            filename = os.path.basename(foto_path)
            dest_path = os.path.join(guia_fotos_dir, filename)
            if os.path.exists(foto_path) and foto_path != dest_path:
                try:
                    shutil.copy2(foto_path, dest_path)
                    logger.info(f"Copiada foto {foto_path} a {dest_path}")
                except Exception as e:
                    logger.error(f"Error copiando foto: {str(e)}")
        
        # Crear la URL de redirección para ver los resultados
        redirect_url = url_for('ver_resultados_clasificacion', url_guia=codigo_guia_a_usar)
        logger.info(f"Redirección a: {redirect_url}")
        
        return jsonify({
            'success': True,
            'redirect_url': redirect_url
        })
        
    except Exception as e:
        logger.error(f"Error registrando clasificación: {str(e)}")
        import traceback
        traceback.print_exc()  # Imprimir el traceback completo
        return jsonify({
            'success': False,
            'message': f'Error al registrar clasificación: {str(e)}'
        })

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
            # Mapeo para verdes
            'racimos verdes': 'verdes',
            'racimo verde': 'verdes',
            'racimos_verdes': 'verdes',
            'racimo_verde': 'verdes',
            'verde': 'verdes',
            'verdes': 'verdes',
            'racimo verde inm.': 'verdes',
            'racimos verde inm.': 'verdes',
            'Racimos verdes': 'verdes',
            
            # Mapeo para maduros
            'racimos maduros': 'maduros',
            'racimo maduro': 'maduros',
            'racimos_maduros': 'maduros',
            'racimo_maduro': 'maduros',
            'maduro': 'maduros',
            'maduros': 'maduros',
            'Racimos maduros': 'maduros',
            
            # Mapeo para sobremaduros
            'racimos sobremaduros': 'sobremaduros',
            'racimo sobremaduro': 'sobremaduros',
            'racimos_sobremaduros': 'sobremaduros',
            'racimo_sobremaduro': 'sobremaduros',
            'sobremaduro': 'sobremaduros',
            'sobremaduros': 'sobremaduros',
            'racimo sobre maduro': 'sobremaduros',
            'Racimos sobremaduros': 'sobremaduros',
            
            # Mapeo para podridos
            'racimos podridos': 'podridos',
            'racimo podrido': 'podridos',
            'racimos_podridos': 'podridos',
            'racimo_podrido': 'podridos',
            'podrido': 'podridos',
            'podridos': 'podridos',
            'Racimos podridos': 'podridos',
            
            # Mapeo para daño en corona
            'daño corona': 'danio_corona',
            'racimo con daño en corona': 'danio_corona',
            'racimos con daño en corona': 'danio_corona',
            'danio_corona': 'danio_corona',
            'daño_corona': 'danio_corona',
            'corona': 'danio_corona',
            'Daño corona': 'danio_corona',
            
            # Mapeo para pedúnculo largo
            'pedunculo largo': 'pendunculo_largo',
            'racimo con pedunculo largo': 'pendunculo_largo',
            'racimos con pedunculo largo': 'pendunculo_largo',
            'pedunculo_largo': 'pendunculo_largo',
            'pendunculo_largo': 'pendunculo_largo',
            'Pedunculo largo': 'pendunculo_largo'
        }
        
        resultados_por_foto = {}
        tiempo_inicio = time.time()
        
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
            
            # Convertir la imagen a base64 para enviar en formato JSON
            try:
                with open(foto_path, 'rb') as image_file:
                    image_bytes = image_file.read()
                    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
                    # Configurar la URL de la API y encabezados según la documentación
                    url = f"https://detect.roboflow.com/infer/workflows/{WORKSPACE_NAME}/{WORKFLOW_ID}"
                    
                    # Enviar la solicitud en el formato esperado por Roboflow
                    headers = {
                        'Content-Type': 'application/json'
                    }
                    
                    # Preparar el cuerpo de la solicitud según la documentación
                    payload = {
                        'api_key': ROBOFLOW_API_KEY,
                        'inputs': {
                            'image': {
                                'type': 'base64',
                                'value': encoded_image
                            }
                        }
                    }
                    
                    # Registrar detalles de la solicitud (sin la imagen por razones de espacio)
                    logger.info(f"Enviando solicitud a URL: {url}")
                    
                    # Realizar la solicitud
                    response = requests.post(url, json=payload, headers=headers, timeout=60)
                    
                    # Registrar la respuesta detallada para diagnóstico
                    logger.info(f"Respuesta de Roboflow para imagen {idx}: Código {response.status_code}")
                    logger.info(f"Respuesta Completa: {response.text[:500]}...")
                    
                    # Procesar la respuesta
                    if response.status_code == 200:
                        result = response.json()
                        logger.info(f"TODAS LAS CLAVES de la respuesta: {list(result.keys())}")
                        logger.info(f"DUMP de respuesta completa: {json.dumps(result, indent=2)[:1000]}...")
                        
                        # Imprimir información sobre la estructura de outputs
                        if 'outputs' in result:
                            logger.info(f"OUTPUTS: Hay {len(result['outputs'])} elementos")
                            if result['outputs'] and len(result['outputs']) > 0:
                                for i, output in enumerate(result['outputs']):
                                    if isinstance(output, dict):
                                        logger.info(f"OUTPUT[{i}] CLAVES: {list(output.keys())}")
                                    else:
                                        logger.info(f"OUTPUT[{i}] NO ES DICCIONARIO: {type(output)}")
                        
                        # Extraer conteos de racimos por categoría utilizando el mapeo
                        detecciones = {
                            "verdes": 0,
                            "maduros": 0, 
                            "sobremaduros": 0,
                            "podridos": 0,
                            "danio_corona": 0,
                            "pendunculo_largo": 0
                        }
                        
                        # Extraer el número total de racimos detectados (potholes_detected)
                        total_racimos_detectados = 0
                        if 'potholes_detected' in result:
                            try:
                                total_racimos_detectados = int(result['potholes_detected'])
                                logger.info(f"Total racimos detectados (potholes_detected): {total_racimos_detectados}")
                            except (ValueError, TypeError):
                                logger.warning(f"No se pudo convertir potholes_detected a entero: {result['potholes_detected']}")
                        
                        # Extraer racimos detectados usando el mapeo de categorías
                        for key, value in result.items():
                            logger.info(f"Verificando clave: {key} (valor: {value})")
                            
                            # Verificar si la clave está en nuestro mapeo
                            key_lower = key.lower()
                            for roboflow_key, internal_key in mapeo_categorias.items():
                                if roboflow_key.lower() == key_lower:
                                    try:
                                        if isinstance(value, (int, float)):
                                            detecciones[internal_key] = int(value)
                                        elif isinstance(value, str) and value.isdigit():
                                            detecciones[internal_key] = int(value)
                                        elif isinstance(value, dict) and 'count' in value:
                                            detecciones[internal_key] = int(value['count'])
                                        logger.info(f"Coincidencia encontrada: {key} -> {internal_key} = {detecciones[internal_key]}")
                                    except (ValueError, TypeError):
                                        logger.warning(f"No se pudo convertir a entero: {value} para la clave {key}")
                                    break
                        
                        # Buscar en la estructura de outputs si está disponible
                        if 'outputs' in result and isinstance(result['outputs'], list) and len(result['outputs']) > 0:
                            for output in result['outputs']:
                                if isinstance(output, dict):
                                    for key, value in output.items():
                                        # Intentar buscar en el mapeo primero
                                        key_lower = key.lower()
                                        for roboflow_key, internal_key in mapeo_categorias.items():
                                            if roboflow_key.lower() == key_lower:
                                                try:
                                                    if isinstance(value, (int, float)):
                                                        detecciones[internal_key] += int(value)
                                                    elif isinstance(value, str) and value.isdigit():
                                                        detecciones[internal_key] += int(value)
                                                    elif isinstance(value, dict) and 'count' in value:
                                                        detecciones[internal_key] += int(value['count'])
                                                    logger.info(f"Coincidencia en outputs: {key} -> {internal_key} = {value}")
                                                except (ValueError, TypeError):
                                                    logger.warning(f"No se pudo convertir a entero en outputs: {value}")
                                                break
                                            
                                            # Si el valor es un diccionario, buscar dentro de él
                                            if isinstance(value, dict):
                                                for subkey, subvalue in value.items():
                                                    subkey_lower = subkey.lower()
                                                    for roboflow_key, internal_key in mapeo_categorias.items():
                                                        if roboflow_key.lower() == subkey_lower:
                                                            try:
                                                                if isinstance(subvalue, (int, float)):
                                                                    detecciones[internal_key] += int(subvalue)
                                                                elif isinstance(subvalue, str) and subvalue.isdigit():
                                                                    detecciones[internal_key] += int(subvalue)
                                                                elif isinstance(subvalue, dict) and 'count' in subvalue:
                                                                    detecciones[internal_key] += int(subvalue['count'])
                                                                logger.info(f"Coincidencia en subclave: {subkey} -> {internal_key} = {subvalue}")
                                                            except (ValueError, TypeError):
                                                                logger.warning(f"No se pudo convertir subclave a entero: {subvalue}")
                                                            break
                        
                        # Si no se detectaron racimos específicos pero hay un total, asignar proporciones por defecto
                        if total_racimos_detectados > 0 and sum(detecciones.values()) == 0:
                            # Asignar todos como maduros por defecto, pero puede cambiarse a una distribución si se conoce
                            detecciones["maduros"] = total_racimos_detectados
                            logger.info(f"No se detectaron categorías específicas, asignando {total_racimos_detectados} racimos como maduros")
                        
                        # Si no hay total pero hay detecciones, calcular el total
                        if total_racimos_detectados == 0 and sum(detecciones.values()) > 0:
                            total_racimos_detectados = sum(detecciones.values())
                            logger.info(f"Total racimos calculado de detecciones: {total_racimos_detectados}")
                        
                        # Actualizar conteo global
                        for categoria, cantidad in detecciones.items():
                            if cantidad > 0:
                                clasificacion_automatica[categoria]["cantidad"] += cantidad
                        
                        # Guardar resultados para esta foto
                        resultados_por_foto[str(idx)] = {
                            "potholes_detected": total_racimos_detectados,
                            "detecciones": detecciones
                        }
                        
                        logger.info(f"Detecciones finales para imagen {idx}: {detecciones}")
                        logger.info(f"Total racimos detectados: {total_racimos_detectados}")
                        
                        # Guardar imágenes anotadas si están disponibles
                        if 'annotated_image' in result:
                            try:
                                logger.info("Encontrada imagen anotada en la respuesta principal")
                                if isinstance(result['annotated_image'], dict) and 'value' in result['annotated_image']:
                                    img_data = decode_image_data(result['annotated_image']['value'])
                                else:
                                    img_data = decode_image_data(result['annotated_image'])
                                    
                                if img_data:
                                    img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data)
                                    logger.info(f"Imagen anotada guardada en {img_path}")
                            except Exception as e:
                                logger.error(f"Error al guardar imagen anotada: {str(e)}")
                        
                        # Comprobar si hay label_visualization
                        if 'label_visualization_1' in result:
                            try:
                                logger.info("Encontrada visualización de etiquetas en la respuesta")
                                if isinstance(result['label_visualization_1'], dict):
                                    if 'value' in result['label_visualization_1']:
                                        img_data = decode_image_data(result['label_visualization_1']['value'])
                                else:
                                    # Decodificar como cadena normal
                                    img_data = decode_image_data(result['label_visualization_1'])
                                
                                if img_data:
                                    img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_etiquetas.jpg")
                                    with open(img_path, 'wb') as f:
                                        f.write(img_data)
                                    logger.info(f"Visualización de etiquetas guardada en {img_path}")
                            except Exception as e:
                                logger.error(f"Error al procesar label_visualization_1: {str(e)}")
                        
                        # Buscar más campos de imágenes en la estructura de respuesta
                        for i, output in enumerate(result.get('outputs', [])):
                            if isinstance(output, dict):
                                # Intentar extraer imágenes de la salida
                                logger.info(f"Revisando output[{i}] para imágenes: {list(output.keys())[:10]}")
                                
                                # Buscar campos comunes de imágenes
                                for img_field in ['annotated_image', 'visualization', 'image', 'processed_image']:
                                    if img_field in output:
                                        try:
                                            logger.info(f"Encontrado campo de imagen {img_field}")
                                            # Manejar si es dict o string
                                            if isinstance(output[img_field], dict) and 'value' in output[img_field]:
                                                img_data = decode_image_data(output[img_field]['value'])
                                            else:
                                                img_data = decode_image_data(output[img_field])
                                                
                                                img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                                with open(img_path, 'wb') as f:
                                                    f.write(img_data)
                                                logger.info(f"Imagen guardada desde output[{i}].{img_field}")
                                                break
                                        except Exception as e:
                                            logger.error(f"Error guardando imagen desde output[{i}].{img_field}: {str(e)}")
                        
                        # Intentar encontrar imágenes anotadas en otras ubicaciones de la respuesta
                        if not os.path.exists(os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")):
                            # Buscar en campos comunes donde la API podría devolver imágenes procesadas
                            for field_name in ['visualization', 'visualizations', 'image', 'processed_image', 'annotated', 'predictions', 'annotated_image']:
                                if field_name in result:
                                    try:
                                        logger.info(f"Intentando procesar campo de imagen: {field_name}")
                                        # Manejar tanto cadenas base64 como listas de cadenas
                                        if isinstance(result[field_name], list) and len(result[field_name]) > 0:
                                            if isinstance(result[field_name][0], dict) and 'value' in result[field_name][0]:
                                                img_data = decode_image_data(result[field_name][0]['value'])
                                            else:
                                                img_data = decode_image_data(result[field_name][0])
                                        elif isinstance(result[field_name], dict):
                                            if 'value' in result[field_name]:
                                                img_data = decode_image_data(result[field_name]['value'])
                                            elif 'image' in result[field_name] and isinstance(result[field_name]['image'], str):
                                                img_data = decode_image_data(result[field_name]['image'])
                                            elif 'base64' in result[field_name] and isinstance(result[field_name]['base64'], str):
                                                img_data = decode_image_data(result[field_name]['base64'])
                                            else:
                                                for subfield in ['data', 'image_data', 'base64_data']:
                                                    if subfield in result[field_name] and isinstance(result[field_name][subfield], str):
                                                        img_data = decode_image_data(result[field_name][subfield])
                                                        break
                                                else:
                                                    logger.warning(f"No se pudo extraer datos de imagen de {field_name}")
                                                    continue
                                        else:
                                            img_data = decode_image_data(result[field_name])
                                            
                                        # Guardar la imagen procesada
                                        img_path = os.path.join(guia_fotos_dir, f"foto_{idx}_procesada.jpg")
                                        with open(img_path, 'wb') as f:
                                            f.write(img_data)
                                        logger.info(f"Imagen procesada guardada desde campo '{field_name}'")
                                        break
                                    except Exception as e:
                                        logger.error(f"Error procesando campo '{field_name}': {str(e)}")
                                        continue
            except Exception as e:
                logger.error(f"Error enviando imagen a Roboflow: {str(e)}")
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
        clasificacion_data['modelo_utilizado'] = f"{WORKSPACE_NAME}/{WORKFLOW_ID}"
        clasificacion_data['total_racimos_detectados'] = sum(cat["cantidad"] for cat in clasificacion_automatica.values())
        
        # Guardar datos actualizados
        logger.info(f"Guardando clasificación_data en: {json_path}")
        logger.info(f"Estructura clasificacion_automatica: {clasificacion_automatica}")
        logger.info(f"DUMP de clasificacion_data completo antes de guardar: {json.dumps(clasificacion_data, indent=2)}")
        try:
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
            logger.info(f"Datos JSON guardados correctamente")
        except Exception as e:
            logger.error(f"Error al guardar datos JSON: {str(e)}")
            logger.error(traceback.format_exc())
        
        logger.info(f"Procesamiento automático completado para guía: {codigo_guia}")

    except Exception as e:
        logger.error(f"Error en el procesamiento automático: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Intentar actualizar el estado en caso de error
        try:
            with open(json_path, 'r') as f:
                clasificacion_data = json.load(f)
            
            clasificacion_data['estado'] = 'error'
            clasificacion_data['error_mensaje'] = str(e)
            
            with open(json_path, 'w') as f:
                json.dump(clasificacion_data, f, indent=4)
        except Exception as inner_e:
            logger.error(f"Error al actualizar estado en archivo JSON: {str(inner_e)}")




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
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        
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
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{url_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
                logger.info(f"Claves en clasificacion_data: {clasificacion_data.keys()}")
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
        datos_guia = utils.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Datos de guía no encontrados"), 404
            
        # Procesar clasificaciones si están en formato JSON
        clasificaciones = []
        if isinstance(clasificacion_data.get('clasificaciones'), str):
            try:
                clasificaciones = json.loads(clasificacion_data['clasificaciones'])
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
                
        # Si clasificacion_data tiene nombre o codigo_proveedor, usarlo para datos_guia
        if not datos_guia.get('nombre') and clasificacion_data.get('nombre_proveedor'):
            datos_guia['nombre'] = clasificacion_data.get('nombre_proveedor')
            
        if not datos_guia.get('codigo') and clasificacion_data.get('codigo_proveedor'):
            datos_guia['codigo'] = clasificacion_data.get('codigo_proveedor')
            
        # Asegurar que tenemos cantidad_racimos
        if not datos_guia.get('cantidad_racimos') and clasificacion_data.get('racimos'):
            datos_guia['cantidad_racimos'] = clasificacion_data.get('racimos')
            
        # Asegurar que tenemos código guía transporte SAP
        if not datos_guia.get('codigo_guia_transporte_sap') and clasificacion_data.get('codigo_guia_transporte_sap'):
            datos_guia['codigo_guia_transporte_sap'] = clasificacion_data.get('codigo_guia_transporte_sap')
            
        # Preparar datos para la plantilla de resultados
        template_data = {
            'codigo_guia': url_guia,
            'codigo_proveedor': codigo_proveedor,  # Agregar código de proveedor extraído
            'id': clasificacion_data.get('id', ''),  # Añadir el ID para las rutas de imágenes
            'fecha_registro': datos_guia.get('fecha_registro'),
            'hora_registro': datos_guia.get('hora_registro'),
            'fecha_clasificacion': clasificacion_data.get('fecha_clasificacion'),
            'hora_clasificacion': clasificacion_data.get('hora_clasificacion'),
            'nombre': clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre')),
            'nombre_proveedor': clasificacion_data.get('nombre_proveedor', datos_guia.get('nombre')),
            'cantidad_racimos': datos_guia.get('cantidad_racimos') or clasificacion_data.get('racimos'),
            'clasificacion_manual': clasificacion_data.get('clasificacion_manual', {}),
            'clasificacion_automatica': clasificacion_data.get('clasificacion_automatica', {}),
            'total_racimos_detectados': clasificacion_data.get('total_racimos_detectados', 0),
            'resultados_por_foto': clasificacion_data.get('resultados_por_foto', {}),  # Añadir resultados por foto
            'clasificaciones': clasificaciones,
            'fotos': clasificacion_data.get('fotos', []),
            'modelo_utilizado': clasificacion_data.get('modelo_utilizado', 'No especificado'),
            'tiempo_procesamiento': clasificacion_data.get('tiempo_procesamiento', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap') or clasificacion_data.get('codigo_guia_transporte_sap'),
            'automatica_completado': 'clasificacion_automatica' in clasificacion_data and any(
                isinstance(clasificacion_data['clasificacion_automatica'].get(categoria), dict) and 
                clasificacion_data['clasificacion_automatica'][categoria].get('cantidad', 0) > 0
                for categoria in ['verdes', 'maduros', 'sobremaduros', 'podridos', 'danio_corona', 'pendunculo_largo']
            ),
            'datos_guia': datos_guia  # Incluir datos_guia completo para la plantilla
        }
        
        # Registrar lo que estamos enviando a la plantilla
        logger.info(f"Enviando a template - código_proveedor: {template_data['codigo_proveedor']}")
        logger.info(f"Enviando a template - clasificacion_manual: {json.dumps(template_data.get('clasificacion_manual', {}))}")
        logger.info(f"Enviando a template - clasificacion_automatica: {json.dumps(template_data.get('clasificacion_automatica', {}))}")
        logger.info(f"Enviando a template - total_racimos_detectados: {template_data.get('total_racimos_detectados', 0)}")
        logger.info(f"Enviando a template - codigo_guia_transporte_sap: {template_data.get('codigo_guia_transporte_sap', 'No disponible')}")
        
        logger.info(f"Mostrando resultados de clasificación para: {url_guia}")
        return render_template('resultados_clasificacion.html', **template_data)
    except Exception as e:
        logger.error(f"Error en ver_resultados_clasificacion: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error al cargar los resultados de clasificación")



@bp.route('/procesar_clasificacion', methods=['POST'])
def procesar_clasificacion():
    try:
        # Obtener datos del formulario
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        clasificacion_manual = data.get('clasificacion_manual', {})
        
        if not codigo_guia:
            logger.error("Falta código guía en la solicitud de clasificación")
            return jsonify({"success": False, "message": "Falta código guía"}), 400
            
        # Verificar si la guía ya ha sido clasificada o procesada más allá
        datos_guia = utils.get_datos_guia(codigo_guia)
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
        clasificaciones_dir = os.path.join(app.config['CLASIFICACIONES_FOLDER'])
        os.makedirs(clasificaciones_dir, exist_ok=True)
        
        # Guardar la clasificación manual
        now = datetime.now()
        fecha_registro = now.strftime('%d/%m/%Y')
        hora_registro = now.strftime('%H:%M:%S')
        
        clasificacion_data = {
            'codigo_guia': codigo_guia,
            'clasificacion_manual': clasificacion_manual,
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
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        return jsonify({
            'success': True,
            'message': 'Clasificación guardada exitosamente',
            'redirect_url': url_for('pesaje_neto', codigo=codigo_guia, _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error al procesar clasificación: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error al procesar la clasificación: {str(e)}'
        }), 500



@bp.route('/procesar_clasificacion_manual/<path:url_guia>', methods=['GET', 'POST'])
def procesar_clasificacion_manual(url_guia):
    """
    Muestra la pantalla de procesamiento para clasificación automática manual
    """
    try:
        logger.info(f"Iniciando pantalla de procesamiento para clasificación manual de: {url_guia}")
        
        # Obtener datos de clasificación desde el archivo JSON
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
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
        
        return render_template('procesando_clasificacion.html', 
                              codigo_guia=url_guia, 
                              nombre=nombre,
                              codigo_proveedor=codigo_proveedor,
                              cantidad_fotos=len(fotos))
    except Exception as e:
        logger.error(f"Error al mostrar la pantalla de procesamiento: {str(e)}")
        return render_template('error.html', 
                              mensaje=f"Error al preparar el procesamiento de clasificación: {str(e)}",
                              volver_url=url_for('ver_resultados_automaticos', url_guia=url_guia))

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
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
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
        guia_fotos_temp_dir = os.path.join(app.static_folder, 'fotos_racimos_temp', url_guia)
        if os.path.exists(guia_fotos_temp_dir):
            logger.info(f"Buscando fotos en directorio temporal: {guia_fotos_temp_dir}")
            for filename in os.listdir(guia_fotos_temp_dir):
                if filename.startswith('foto_') and filename.endswith(('.jpg', '.jpeg', '.png')):
                    fotos_paths.append(os.path.join(guia_fotos_temp_dir, filename))
        
        # 2. Si no hay fotos en el directorio temporal, buscar en el directorio principal de fotos
        if not fotos_paths:
            guia_fotos_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
            if os.path.exists(guia_fotos_dir):
                logger.info(f"Buscando fotos en directorio principal: {guia_fotos_dir}")
                for filename in os.listdir(guia_fotos_dir):
                    if utils.es_archivo_imagen(filename):
                        fotos_paths.append(os.path.join(guia_fotos_dir, filename))
        
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
        
        # Iniciar procesamiento en un hilo separado
        def process_thread():
            try:
                # Log para depuración de rutas de fotos encontradas
                logger.info(f"Procesando {len(fotos_paths)} fotos para la guía {url_guia}")
                for i, foto_path in enumerate(fotos_paths):
                    logger.info(f"Foto {i+1}: {foto_path}")
                
                # Determinar el directorio de fotos para guardar resultados
                if os.path.exists(guia_fotos_temp_dir):
                    guia_fotos_dir_para_resultados = guia_fotos_temp_dir
                else:
                    guia_fotos_dir_para_resultados = os.path.join(app.config['UPLOAD_FOLDER'], 'fotos', url_guia)
                    
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
        clasificaciones_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'clasificaciones')
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
        return render_template('procesando_clasificacion.html', codigo_guia=url_guia)
    except Exception as e:
        logger.error(f"Error al mostrar pantalla de procesamiento: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al preparar el procesamiento: {str(e)}", 'error')
        return redirect(url_for('ver_resultados_automaticos', url_guia=url_guia))



@bp.route('/mostrar_resultados_automaticos/<path:url_guia>')
def mostrar_resultados_automaticos(url_guia):
    """
    Muestra los resultados de la clasificación automática a partir del JSON generado.
    """
    try:
        datos_guia = utils.get_datos_guia(url_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        json_path = os.path.join(app.config['FOTOS_RACIMOS_FOLDER'], f'clasificacion_{url_guia}.json')
        
        if not os.path.exists(json_path):
            flash("No se encontraron resultados de clasificación automática para esta guía.", "warning")
            return redirect(url_for('procesar_clasificacion_manual', url_guia=url_guia))
            
        with open(json_path, 'r') as file:
            clasificacion_data = json.load(file)
            
        logger.info(f"Clasificación data: {clasificacion_data}")
        
        # Comprobar si hay clasificación automática
        if not clasificacion_data.get('clasificacion_automatica'):
            flash("No se han procesado imágenes automáticamente para esta guía.", "warning")
            return redirect(url_for('procesar_clasificacion_manual', url_guia=url_guia))

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
        
        return render_template('auto_clasificacion_resultados.html', datos=datos_guia)
    except Exception as e:
        logger.error(f"Error al mostrar resultados automáticos: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return redirect(url_for('index'))



