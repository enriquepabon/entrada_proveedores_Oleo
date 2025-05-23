from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.misc import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/guias/<filename>')
def serve_guia(filename):
    """
    Sirve los archivos HTML de las guías de proceso
    """
    try:
        logger.info(f"Intentando servir guía: {filename}")
        
        # Extraer el código de guía del nombre del archivo
        codigo_guia = filename.replace('guia_', '').replace('.html', '')
        
        # Ruta del archivo de guía solicitado
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], filename)
        
        # Si el archivo no existe, verificar si tenemos que buscar por código base
        if not os.path.exists(guia_path):
            logger.info(f"Archivo de guía no encontrado directamente: {guia_path}")
            # Extraer el código base si el código contiene guión bajo
            if '_' in codigo_guia:
                codigo_base = codigo_guia.split('_')[0]
                guias_folder = app.config['GUIAS_FOLDER']
                # Buscar las guías con ese código base
                guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}*.html'))
                
                if guias_files:
                    # Ordenar por fecha de modificación, más reciente primero
                    guias_files.sort(key=os.path.getmtime, reverse=True)
                    latest_guia = os.path.basename(guias_files[0])
                    logger.info(f"Redirigiendo a la guía más reciente: {latest_guia}")
                    # Redirigir a la versión más reciente
                    return redirect(url_for('misc.serve_guia', filename=latest_guia))
            
            logger.error(f"No se encontró ninguna guía para: {codigo_guia}")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Obtener datos actualizados de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia}")
            return render_template('error.html', message="Datos de guía no encontrados"), 404
            
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
            
        # Servir el archivo actualizado
        return send_from_directory(app.config['GUIAS_FOLDER'], filename)
        
    except Exception as e:
        logger.error(f"Error sirviendo guía: {str(e)}")
        return render_template('error.html', message="Error al servir la guía"), 500

# URLs de los Webhooks en Make.com
PROCESS_WEBHOOK_URL = "https://hook.us2.make.com/asrfb3kv3cw4o4nd43wylyasfx5yq55f"
REGISTER_WEBHOOK_URL = "https://hook.us2.make.com/f63o7rmsuixytjfqxq3gjljnscqhiedl"
REVALIDATION_WEBHOOK_URL = "https://hook.us2.make.com/bok045bvtwpj89ig58nhrmx1x09yh56u"
ADMIN_NOTIFICATION_WEBHOOK_URL = "https://hook.us2.make.com/wpeskbay7k21c3jnthu86lyo081r76fe"
PESAJE_WEBHOOK_URL = "https://hook.us2.make.com/srw5ti54ulwuxtvocrj2lypa5pmq3im4"
AUTORIZACION_WEBHOOK_URL = "https://hook.us2.make.com/py29fwgfrehp9il45832acotytu8xr5s"
REGISTRO_PESO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"
CLASIFICACION_WEBHOOK_URL = "https://hook.us2.make.com/clasificacion_webhook_url"
REGISTRO_CLASIFICACION_WEBHOOK_URL = "https://hook.us2.make.com/ydtogfd3mln2ixbcuam0xrd2m9odfgna"
PLACA_WEBHOOK_URL = "https://hook.us2.make.com/a2yotw5cls6qxom2iacvyaoh2b9uk9ip"
REGISTRO_PESO_NETO_WEBHOOK_URL = "https://hook.us2.make.com/agxyjbyswl2cg1bor1wdrlfcgrll0y15"  # Using the same URL as REGISTRO_PESO_WEBHOOK_URL for now

codigos_autorizacion = {}


# Extensiones permitidas para subir
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'tiff'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS



@bp.route('/', methods=['GET', 'POST'])
def upload_file():
    """
    Handles file upload and processing
    """
    if request.method == 'POST':
        session.clear()
        
        if 'file' not in request.files:
            return render_template('error.html', message="No se ha seleccionado ningún archivo.")
            
        file = request.files['file']
        plate_file = request.files.get('plate_file')
        
        if file.filename == '':
            return render_template('error.html', message="No se ha seleccionado ningún archivo.")
            
        if file and allowed_file(file.filename):
            try:
                # Guardar imagen del tiquete
                filename = secure_filename(file.filename)
                image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(image_path)
                session['image_filename'] = filename

                # Procesar imagen de placa si existe
                if plate_file and plate_file.filename != '' and allowed_file(plate_file.filename):
                    plate_filename = secure_filename(plate_file.filename)
                    plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_filename)
                    plate_file.save(plate_path)
                    session['plate_image_filename'] = plate_filename
                
                return redirect(url_for('processing'))
            except Exception as e:
                logger.error(f"Error guardando archivo: {str(e)}")
                return render_template('error.html', message="Error procesando el archivo.")
        else:
            return render_template('error.html', message="Tipo de archivo no permitido.")
    else:
        # Si es una solicitud GET, redirigir a home
        return redirect(url_for('home'))



@bp.route('/reprocess_plate', methods=['POST'])
def reprocess_plate():
    try:
        plate_image_filename = session.get('plate_image_filename')
        if not plate_image_filename:
            return jsonify({
                'success': False,
                'message': 'No hay imagen de placa para procesar'
            })
        
        plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_image_filename)
        if not os.path.exists(plate_path):
            return jsonify({
                'success': False,
                'message': 'No se encontró la imagen de la placa'
            })
        
        # Procesar la imagen de la placa
        result = process_plate_image(plate_path, plate_image_filename)
        
        if result.get("result") == "ok":
            session['plate_text'] = result.get("plate_text")
            session.pop('plate_error', None)
            return jsonify({
                'success': True,
                'message': 'Placa procesada correctamente'
            })
        else:
            session['plate_error'] = result.get("message")
            session.pop('plate_text', None)
            return jsonify({
                'success': False,
                'message': result.get("message")
            })
            
    except Exception as e:
        logger.error(f"Error reprocesando placa: {str(e)}")
        return jsonify({
            'success': False,
            'message': str(e)
        })



@bp.route('/revalidation_results')
def revalidation_results():
    """
    Renderiza la página de resultados de revalidación
    """
    return render_template('revalidation_results.html')



@bp.route('/revalidation_success')
def revalidation_success():
    """
    Renderiza la página de éxito de revalidación
    """
    webhook_response = session.get('webhook_response', {})
    table_data = session.get('table_data', [])
    
    if not webhook_response or not webhook_response.get('data'):
        # Log para depuración
        logger.warning("No se encontró webhook_response o data en la sesión. webhook_response: %s", webhook_response)
        logger.warning("table_data: %s", table_data)
        flash('El proceso de revalidación ha sido interrumpido o la sesión ha expirado', 'warning')
        return redirect(url_for('review'))
        
    data = webhook_response['data']
    
    # Determinar qué campos fueron modificados
    modified_fields = {}
    for row in table_data:
        campo = row.get('campo')
        original = row.get('original')
        sugerido = row.get('sugerido')
        if original != sugerido:
            modified_fields[campo] = True
    
    # Guardar los indicadores de campos modificados en la sesión
    session['nombre_agricultor_modificado'] = modified_fields.get('Nombre del Agricultor', False)
    session['codigo_modificado'] = modified_fields.get('Código', False)
    session['cantidad_de_racimos_modificado'] = modified_fields.get('Cantidad de Racimos', False)
    session['placa_modificado'] = modified_fields.get('Placa', False)
    session['acarreo_modificado'] = modified_fields.get('Se Acarreó', False)
    session['cargo_modificado'] = modified_fields.get('Se Cargó', False)
    session['transportador_modificado'] = modified_fields.get('Transportador', False)
    session['fecha_modificado'] = modified_fields.get('Fecha', False)
    session.modified = True
    
    # Logging para verificar
    logger.info(f"Campos modificados: {modified_fields}")
    logger.info(f"Guardados en sesión: nombre_modificado={session.get('nombre_agricultor_modificado')}, codigo_modificado={session.get('codigo_modificado')}")
    logger.info(f"Data para la plantilla: {data}")
    
    # Asegurar que todos los campos necesarios estén presentes
    nombre_agricultor = data.get('Nombre del Agricultor') or data.get('nombre_agricultor', '')
    codigo = data.get('Código') or data.get('codigo', '')
    racimos = data.get('Cantidad de Racimos') or data.get('racimos', '')
    placa = data.get('Placa') or data.get('placa', '')
    acarreo = data.get('Se Acarreó') or data.get('acarreo', '')
    cargo = data.get('Se Cargó') or data.get('cargo', '')
    transportador = data.get('Transportador') or data.get('transportador', '')
    fecha_tiquete = data.get('Fecha') or data.get('fecha_tiquete', '')
    nota = data.get('Nota') or data.get('nota', '')
    
    return render_template('revalidation_success.html',
                         image_filename=session.get('image_filename'),
                         nombre_agricultor=nombre_agricultor,
                         codigo=codigo,
                         racimos=racimos,
                         placa=placa,
                         acarreo=acarreo,
                         cargo=cargo,
                         transportador=transportador,
                         fecha_tiquete=fecha_tiquete,
                         hora_registro=datetime.now().strftime('%H:%M:%S'),
                         nota=nota,
                         plate_text=session.get('plate_text'),
                         nombre_agricultor_modificado=modified_fields.get('Nombre del Agricultor'),
                         codigo_modificado=modified_fields.get('Código'),
                         cantidad_de_racimos_modificado=modified_fields.get('Cantidad de Racimos'),
                         placa_modificado=modified_fields.get('Placa'),
                         acarreo_modificado=modified_fields.get('Se Acarreó'),
                         cargo_modificado=modified_fields.get('Se Cargó'),
                         transportador_modificado=modified_fields.get('Transportador'),
                         fecha_modificado=modified_fields.get('Fecha'))



@bp.route('/ver_resultados_pesaje/<codigo_guia>')
def ver_resultados_pesaje(codigo_guia):
    try:
        codigo = codigo_guia
        
        # Variables para seguimiento
        datos_encontrados = False
        fuente_datos = None
        
        
        # Verificar si tenemos un código guía original guardado en la sesión
        original_codigo_guia = session.get('codigo_guia_original')
        if original_codigo_guia and original_codigo_guia != codigo_guia:
            logger.info(f"Usando código guía original de sesión {original_codigo_guia} en lugar de {codigo_guia}")
            codigo_guia = original_codigo_guia
        
        # Verificar si hay datos en la sesión
        peso_bruto_session = session.get('peso_bruto')
        estado_actual_session = session.get('estado_actual')
        fotos_pesaje_session = session.get('fotos_pesaje', [])
        
        logger.info(f"ver_resultados_pesaje: Datos de sesión: peso_bruto={peso_bruto_session}, estado_actual={estado_actual_session}, codigo_guia={codigo_guia}")
        
        # Utilizar el helper de datos para obtener datos completos y normalizados
        from data_helper import init_data_helper
        data_helper = init_data_helper(app)
        datos_guia = data_helper.obtener_datos_completos_guia(codigo_guia)
        
        # Si aún no hay datos, mostrar error
        if not datos_guia:
            return render_template('error.html', message=f"No se encontraron datos para la guía {codigo_guia}"), 404
        
        # Verificar que el pesaje esté completado - Preferir el estado de la sesión si está disponible
        if estado_actual_session == 'pesaje_completado':
            datos_guia['estado_actual'] = 'pesaje_completado'
        
        # Si el pesaje no está completado, simplemente mostrar los datos disponibles
        # y no redireccionar automáticamente a pesaje
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            logger.warning(f"Mostrando resultados para guía {codigo_guia} sin estado completado")
            # Añadir un mensaje de advertencia en el contexto
            datos_guia['advertencia'] = "Esta guía aún no tiene un pesaje completado."
        
        # Asegurar que el estado se actualice a pesaje_completado en la sesión si hay peso
        if peso_bruto_session:
            session['estado_actual'] = 'pesaje_completado'
            session.modified = True
            
            # Guardar el peso en los datos si no existe
            if not datos_guia.get('peso_bruto'):
                datos_guia['peso_bruto'] = peso_bruto_session
                
            # Guardar los datos actualizados
            data_helper.guardar_datos_combinados(codigo_guia, datos_guia)
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('misc.ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para la plantilla
        imagen_pesaje = None
        if datos_guia.get('imagen_peso'):
            imagen_pesaje = url_for('static', filename=f'uploads/{datos_guia["imagen_peso"]}')
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa')
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if verificacion_placa is None:
            verificacion_placa = {}
            
        placa_detectada = verificacion_placa.get('placa_detectada', '')
        placa_coincide = verificacion_placa.get('coincide', False)
        
        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia,
            'tiene_peso': True if datos_guia.get('peso_bruto') else False,
            'tiene_clasificacion': True if datos_guia.get('clasificacion') else False,
            'tipo_pesaje': datos_guia.get('tipo_pesaje', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'N/A'),
            'hora_pesaje': datos_guia.get('hora_pesaje', 'N/A'),
            'clasificacion': datos_guia.get('clasificacion', 'N/A'),
            'peso_neto': datos_guia.get('peso_neto', 'N/A'),
            'fecha_clasificacion': datos_guia.get('fecha_clasificacion', 'N/A'),
            'hora_clasificacion': datos_guia.get('hora_clasificacion', 'N/A'),
            'fotos_pesaje': datos_guia.get('fotos_pesaje', []),
            'codigo_proveedor': datos_guia.get('codigo', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'racimos': datos_guia.get('racimos', 'No disponible'),
            'codigo_guia_transporte_sap': datos_guia.get('codigo_guia_transporte_sap', ''),
            'imagen_pesaje': imagen_pesaje,
            'qr_code': qr_code,
            'verificacion_placa': verificacion_placa,
            'placa_detectada': placa_detectada,
            'placa_coincide': placa_coincide
        }
        
        return render_template('resultados_pesaje.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")



@bp.route('/generar_pdf_pesaje/<codigo_guia>')
def generar_pdf_pesaje(codigo_guia):
    """
    Genera un PDF con los resultados del pesaje.
    """
    try:
        logger.info(f"Generando PDF de pesaje para guía: {codigo_guia}")
            
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el pesaje está completado
        if datos_guia.get('estado_actual') != 'pesaje_completado':
            flash("El pesaje no ha sido completado para esta guía.", "warning")
            return redirect(url_for('pesaje', codigo=codigo_guia))
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para el PDF
        imagen_pesaje = None
        if datos_guia.get('imagen_peso'):
            imagen_pesaje = url_for('static', filename=f'uploads/{datos_guia["imagen_peso"]}', _external=True)
        
        qr_code = url_for('static', filename=f'qr/{qr_filename}', _external=True)
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa', {})
        placa_detectada = verificacion_placa.get('placa_detectada', '')
        placa_coincide = verificacion_placa.get('coincide', False)
        
        # Obtener fotos de pesaje si existen
        fotos_pesaje = []
        # Verificar si hay fotos en los datos de la guía
        if 'fotos_pesaje' in datos_guia and datos_guia['fotos_pesaje']:
            fotos_pesaje = datos_guia['fotos_pesaje']
        else:
            # Verificar si hay fotos en la sesión
            session_fotos = session.get('fotos_pesaje', [])
            if session_fotos:
                fotos_pesaje = session_fotos
            else:
                # Buscar fotos en el directorio del código guía
                fotos_dir = os.path.join(app.static_folder, 'fotos_pesaje', codigo_guia)
                if os.path.exists(fotos_dir):
                    for foto_file in os.listdir(fotos_dir):
                        if foto_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            fotos_pesaje.append(os.path.join('static', 'fotos_pesaje', codigo_guia, foto_file))
        
        # Asegurar que las fotos existen físicamente
        valid_fotos = []
        for foto in fotos_pesaje:
            foto_path = foto.replace('static/', '')
            full_path = os.path.join(app.static_folder, foto_path)
            if os.path.exists(full_path):
                valid_fotos.append(foto)
                
        logger.info(f"Fotos de pesaje encontradas para PDF: {len(valid_fotos)}")
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF usando el mismo template que la vista
        html = render_template('pesaje_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
            transportador=datos_guia.get('transportador', 'No disponible'),
            placa=datos_guia.get('placa', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            tipo_pesaje=datos_guia.get('tipo_pesaje', 'No disponible'),
            fecha_pesaje=datos_guia.get('fecha_pesaje', 'No disponible'),
            hora_pesaje=datos_guia.get('hora_pesaje', 'No disponible'),
            racimos=datos_guia.get('racimos', 'No disponible'),
            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', ''),
            imagen_pesaje=imagen_pesaje,
            qr_code=qr_code,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            fotos_pesaje=valid_fotos,
            verificacion_placa=verificacion_placa,
            placa_detectada=placa_detectada,
            placa_coincide=placa_coincide
        )
        
        try:
            # Configuración para pdfkit
            options = {
                'page-size': 'Letter',
                'encoding': 'UTF-8',
                'margin-top': '0.5in',
                'margin-right': '0.5in',
                'margin-bottom': '0.5in',
                'margin-left': '0.5in',
                'dpi': 300,
                'disable-smart-shrinking': True
            }
            
            # Intentar encontrar el binario de wkhtmltopdf con which
            wkhtmltopdf_path = None
            try:
                import subprocess
                result = subprocess.run(['which', 'wkhtmltopdf'], capture_output=True, text=True)
                if result.returncode == 0:
                    wkhtmltopdf_path = result.stdout.strip()
                    logger.info(f"wkhtmltopdf encontrado en: {wkhtmltopdf_path}")
            except Exception as e:
                logger.warning(f"Error al buscar wkhtmltopdf: {e}")
            
            # Si hay una ruta válida, crear configuración personalizada
            if wkhtmltopdf_path:
                config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                pdf = pdfkit.from_string(html, False, options=options, configuration=config)
            else:
                # Si no se encuentra wkhtmltopdf, intentar sin configuración específica
                pdf = pdfkit.from_string(html, False, options=options)
            # Preparar respuesta
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=pesaje_{codigo_guia}.pdf'
            
            return response
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF con pdfkit: {str(pdf_error)}")
            
            # Fallback method - Redirect to rendering the template directly
            flash("Generando versión imprimible del documento.", "info")
            return render_template('pesaje_print_view.html',
                codigo_guia=codigo_guia,
                codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
                nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
                transportador=datos_guia.get('transportador', 'No disponible'),
                placa=datos_guia.get('placa', 'No disponible'),
                peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
                tipo_pesaje=datos_guia.get('tipo_pesaje', 'No disponible'),
                fecha_pesaje=datos_guia.get('fecha_pesaje', 'No disponible'),
                hora_pesaje=datos_guia.get('hora_pesaje', 'No disponible'),
                racimos=datos_guia.get('racimos', 'No disponible'),
                codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', ''),
                imagen_pesaje=imagen_pesaje,
                qr_code=qr_code,
                fecha_generacion=fecha_generacion,
                hora_generacion=hora_generacion,
                fotos_pesaje=valid_fotos
            )
        
    except Exception as e:
        logger.error(f"Error general en generar_pdf_pesaje: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar el PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_pesaje', codigo_guia=codigo_guia))



@bp.route('/generar-pdf-registro/<codigo_guia>', methods=['GET'])
def generar_pdf_registro(codigo_guia):
    """
    Genera un PDF para un registro de entrada específico.
    """
    try:
        registro = None
        
        # Intentar obtener el registro desde la base de datos primero
        try:
            import db_utils
            registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
            
            if registro:
                logger.info(f"Registro encontrado en la base de datos para PDF: {codigo_guia}")
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos para PDF: {db_error}")
        
        # Si no se encontró en la base de datos, intentar obtenerlo del archivo
        if not registro:
            logger.info(f"Buscando registro en archivos para PDF: {codigo_guia}")
            registro = utils.get_datos_registro(codigo_guia)
        
        if not registro:
            # Mensaje específico cuando el código no se encuentra en la base de datos ni en archivos
            flash(f'El registro con código {codigo_guia} no fue encontrado ni en la base de datos ni en los archivos', 'warning')
            return redirect(url_for('lista_registros_entrada'))
        
        # Verificar si el PDF ya existe
        pdf_filename = f"registro_{codigo_guia}.pdf"
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        # Obtener fotos de pesaje si existen
        fotos_pesaje = []
        # Verificar si hay fotos en el registro
        if 'fotos_pesaje' in registro and registro['fotos_pesaje']:
            fotos_pesaje = registro['fotos_pesaje']
        else:
            # Verificar si hay fotos en la sesión
            session_fotos = session.get('fotos_pesaje', [])
            if session_fotos:
                fotos_pesaje = session_fotos
            else:
                # Buscar fotos en el directorio del código guía
                fotos_dir = os.path.join(app.static_folder, 'fotos_pesaje', codigo_guia)
                if os.path.exists(fotos_dir):
                    for foto_file in os.listdir(fotos_dir):
                        if foto_file.lower().endswith(('.jpg', '.jpeg', '.png')):
                            fotos_pesaje.append(os.path.join('static', 'fotos_pesaje', codigo_guia, foto_file))
        
        # Asegurar que las fotos existen físicamente
        valid_fotos = []
        for foto in fotos_pesaje:
            foto_path = foto.replace('static/', '')
            full_path = os.path.join(app.static_folder, foto_path)
            if os.path.exists(full_path):
                valid_fotos.append(foto)
        
        # Si el PDF no existe, generarlo
        if not os.path.exists(pdf_path):
            # Obtener información de campos modificados
            modified_fields = registro.get('modified_fields', {})
            
            # Renderizar la plantilla para el PDF
            rendered = render_template(
                'pdf_template.html',
                codigo=registro.get('codigo_proveedor', ''),
                nombre_agricultor=registro.get('nombre_proveedor', ''),
                racimos=registro.get('cantidad_racimos', ''),
                placa=registro.get('placa', ''),
                acarreo=registro.get('acarreo', 'No'),
                cargo=registro.get('cargo', 'No'),
                transportador=registro.get('transportador', ''),
                fecha_tiquete=registro.get('fecha_tiquete', ''),
                hora_registro=registro.get('hora_registro', ''),
                fecha_emision=datetime.now().strftime("%d/%m/%Y"),
                hora_emision=datetime.now().strftime("%H:%M:%S"),
                nota=registro.get('nota', ''),
                qr_filename=registro.get('qr_filename', ''),
                image_filename=registro.get('image_filename', ''),
                # Agregar fotos de pesaje
                fotos_pesaje=valid_fotos,
                peso_bruto=registro.get('peso_bruto', ''),
                tipo_pesaje=registro.get('tipo_pesaje', ''),
                fecha_pesaje=registro.get('fecha_pesaje', ''),
                hora_pesaje=registro.get('hora_pesaje', ''),
                # Agregar indicadores de campos modificados
                codigo_modificado=modified_fields.get('codigo', False),
                nombre_agricultor_modificado=modified_fields.get('nombre_agricultor', False),
                cantidad_de_racimos_modificado=modified_fields.get('racimos', False),
                placa_modificado=modified_fields.get('placa', False),
                acarreo_modificado=modified_fields.get('acarreo', False),
                cargo_modificado=modified_fields.get('cargo', False),
                transportador_modificado=modified_fields.get('transportador', False),
                fecha_modificado=modified_fields.get('fecha_tiquete', False)
            )
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
            
            # Generar PDF
            HTML(
                string=rendered,
                base_url=app.static_folder
            ).write_pdf(pdf_path)
            
            logger.info(f"PDF generado exitosamente: {pdf_filename}")
        
        # Retornar el archivo PDF
        return send_file(pdf_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"Error generando PDF del registro: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al generar PDF del registro', 'error')
        return redirect(url_for('lista_registros_entrada'))



@bp.route('/process_validated_data', methods=['POST'])
def process_validated_data():
    """
    Procesa los datos validados y genera el PDF final.
    """
    try:
        # Obtener el webhook response guardado en la sesión
        webhook_response = session.get('webhook_response', {})
        webhook_data = webhook_response.get('data', {})
        
        if not webhook_data:
            logger.error("No hay datos validados para procesar")
            return jsonify({
                "status": "error",
                "message": "No hay datos validados"
            }), 400
        
        # Logging para depuración
        logger.info(f"Datos recibidos en process_validated_data: {webhook_data}")
        
        # Sanitizar la nota para evitar datos que puedan causar problemas (máximo 500 caracteres)
        if 'nota' in webhook_data and webhook_data['nota']:
            webhook_data['nota'] = webhook_data['nota'][:500]
            logger.info(f"Nota sanitizada: {webhook_data['nota']}")
        
        # Validar que hay datos esenciales
        # Verificar tanto las claves en formato camelCase como las claves en formato con espacios
        codigo = webhook_data.get('codigo') or webhook_data.get('Código', '')
        nombre_agricultor = webhook_data.get('nombre_agricultor') or webhook_data.get('Nombre del Agricultor', '')
        
        if not codigo or not nombre_agricultor:
            logger.error("Faltan datos esenciales en la respuesta del webhook")
            logger.error(f"Datos disponibles: codigo={codigo}, nombre={nombre_agricultor}")
            return jsonify({
                "status": "error", 
                "message": "Faltan datos esenciales (código o nombre)"
            }), 400
        
        # Normalizar los datos para asegurar que todas las claves necesarias estén presentes
        normalized_data = {
            'nombre_agricultor': nombre_agricultor,
            'codigo': codigo,
            'racimos': webhook_data.get('racimos') or webhook_data.get('Cantidad de Racimos', ''),
            'placa': webhook_data.get('placa') or webhook_data.get('Placa', ''),
            'acarreo': webhook_data.get('acarreo') or webhook_data.get('Se Acarreó', ''),
            'cargo': webhook_data.get('cargo') or webhook_data.get('Se Cargó', ''),
            'transportador': webhook_data.get('transportador') or webhook_data.get('Transportador', ''),
            'fecha_tiquete': webhook_data.get('fecha_tiquete') or webhook_data.get('Fecha', ''),
            'nota': webhook_data.get('nota') or webhook_data.get('Nota', '')
        }
        
        # Guardar todos los datos relevantes en la sesión para uso posterior
        session['nombre_agricultor'] = normalized_data['nombre_agricultor']
        session['codigo'] = normalized_data['codigo']
        session['racimos'] = normalized_data['racimos']
        session['placa'] = normalized_data['placa']
        session['acarreo'] = normalized_data['acarreo']
        session['cargo'] = normalized_data['cargo']
        session['transportador'] = normalized_data['transportador']
        session['fecha_tiquete'] = normalized_data['fecha_tiquete']
        session['nota'] = normalized_data['nota']
        
        # Verificar y registrar el estado de los indicadores de campos modificados
        nombre_agricultor_modificado = session.get('nombre_agricultor_modificado', False)
        codigo_modificado = session.get('codigo_modificado', False)
        cantidad_de_racimos_modificado = session.get('cantidad_de_racimos_modificado', False)
        placa_modificado = session.get('placa_modificado', False)
        acarreo_modificado = session.get('acarreo_modificado', False)
        cargo_modificado = session.get('cargo_modificado', False)
        transportador_modificado = session.get('transportador_modificado', False)
        fecha_modificado = session.get('fecha_modificado', False)
        
        logger.info(f"Indicadores de modificación recuperados: nombre={nombre_agricultor_modificado}, " 
                 f"codigo={codigo_modificado}, racimos={cantidad_de_racimos_modificado}, "
                 f"placa={placa_modificado}, acarreo={acarreo_modificado}, "
                 f"cargo={cargo_modificado}, transportador={transportador_modificado}, "
                 f"fecha={fecha_modificado}")
        
        # Preservar los indicadores de campos modificados
        session['nombre_agricultor_modificado'] = nombre_agricultor_modificado
        session['codigo_modificado'] = codigo_modificado
        session['cantidad_de_racimos_modificado'] = cantidad_de_racimos_modificado
        session['placa_modificado'] = placa_modificado
        session['acarreo_modificado'] = acarreo_modificado
        session['cargo_modificado'] = cargo_modificado
        session['transportador_modificado'] = transportador_modificado
        session['fecha_modificado'] = fecha_modificado
        
        session.modified = True
        
        # Generar código único para la guía usando la función estándar de utils
        codigo_proveedor = normalized_data['codigo']
        codigo_guia = utils.generar_codigo_guia(codigo_proveedor)
        session['codigo_guia'] = codigo_guia
        
        # Registro de fecha y hora
        fecha_registro = datetime.now().strftime("%d/%m/%Y")
        hora_registro = datetime.now().strftime("%H:%M:%S")
        
        session['fecha_registro'] = fecha_registro
        session['hora_registro'] = hora_registro
        
        # Generar PDF con los datos validados
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        
        # Preparar los datos para el PDF
        parsed_data = {
            "codigo": normalized_data['codigo'],
            "nombre_agricultor": normalized_data['nombre_agricultor'],
            "cantidad_de_racimos": normalized_data['racimos'],
            "placa": normalized_data['placa'],
            "acarreo": normalized_data['acarreo'],
            "cargo": normalized_data['cargo'],
            "transportador": normalized_data['transportador'],
            "fecha": normalized_data['fecha_tiquete'],
            "codigo_guia": codigo_guia,
            "nota": normalized_data['nota']
        }
        
        # Generar PDF
        pdf_filename = utils.generate_pdf(
            parsed_data,
            image_filename,
            fecha_registro,
            hora_registro,
            revalidation_data=None,
            codigo_guia=codigo_guia
        )
        
        # Generar QR
        qr_filename = f"qr_{codigo_guia}.png"
        try:
            utils.generate_qr(codigo_guia, qr_filename)
            # Guardar en sesión
            session['qr_filename'] = qr_filename
        except Exception as e:
            logger.error(f"Error generando QR: {str(e)}")
            # Fallback para asegurar que siempre tenemos un valor para qr_filename
            session['qr_filename'] = "default_qr.png"
            qr_filename = "default_qr.png"
        
        session.modified = True
        
        # Guardar en sesión
        session['pdf_filename'] = pdf_filename
        
        # Crear directorio para guardar la guía
        guias_dir = os.path.join(app.static_folder, 'guias')
        if not os.path.exists(guias_dir):
            os.makedirs(guias_dir)
            
        # Guardar una copia del HTML como guía
        guia_path = os.path.join(guias_dir, f"guia_{codigo_guia}.html")
        
        # Crear objeto con indicadores de campos modificados
        modified_fields = {
            'nombre_agricultor': nombre_agricultor_modificado,
            'codigo': codigo_modificado,
            'racimos': cantidad_de_racimos_modificado,
            'placa': placa_modificado,
            'acarreo': acarreo_modificado,
            'cargo': cargo_modificado,
            'transportador': transportador_modificado,
            'fecha_tiquete': fecha_modificado
        }
        
        # Convertir a JSON string para almacenar en la base de datos
        modified_fields_json = json.dumps(modified_fields)
        
        # Datos del registro completo
        datos_registro = {
            'codigo_guia': codigo_guia,
            'codigo_proveedor': normalized_data['codigo'],
            'nombre_proveedor': normalized_data['nombre_agricultor'],
            'fecha_registro': fecha_registro,
            'hora_registro': hora_registro,
            'placa': webhook_data.get('placa', ''),
            'cantidad_racimos': webhook_data.get('racimos', ''),
            'transportador': webhook_data.get('transportador', ''),
            'acarreo': webhook_data.get('acarreo', ''),
            'cargo': webhook_data.get('cargo', ''),
            'fecha_tiquete': webhook_data.get('fecha_tiquete', ''),
            'image_filename': image_filename,
            'plate_image_filename': plate_image_filename,
            'pdf_filename': pdf_filename,
            'qr_filename': qr_filename,
            'plate_text': session.get('plate_text', ''),
            'nota': webhook_data.get('nota', ''),
            'modified_fields': modified_fields_json
        }
        
        # Guardar datos en el archivo HTML (mantener compatibilidad con el sistema actual)
        with open(guia_path, 'w') as f:
            f.write(json.dumps(datos_registro))
            
        logger.info(f"Guía generada: {guia_path}")
        
        # Guardar en la base de datos SQLite
        try:
            import db_utils
            db_utils.store_entry_record(datos_registro)
            logger.info(f"Registro guardado en la base de datos: {codigo_guia}")
        except Exception as e:
            logger.error(f"Error guardando registro en la base de datos: {str(e)}")
            logger.error(traceback.format_exc())
            # Continuar con el proceso aunque falle la base de datos
        
        # Guardamos el estado actual en la sesión
        session['estado_actual'] = 'registro_completado'
        session.modified = True
            
        return jsonify({
            "status": "success",
            "redirect": url_for('review_pdf', _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error procesando datos validados: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500



@bp.route('/generar_pdf_pesaje_neto/<codigo_guia>')
def generar_pdf_pesaje_neto(codigo_guia):
    """
    Genera un PDF con los resultados del pesaje neto.
    """
    try:
        logger.info(f"Generando PDF de pesaje neto para guía: {codigo_guia}")
            
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el pesaje neto está registrado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia))
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_neto_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para el PDF
        imagen_bascula_neto = datos_guia.get('foto_bascula_neto')
        qr_code = url_for('static', filename=f'qr/{qr_filename}', _external=True)
        
        # Obtener fotos de pesaje neto si existen
        fotos_pesaje_neto = []
        # Verificar si hay fotos en los datos de la guía
        if 'fotos_pesaje_neto' in datos_guia and datos_guia['fotos_pesaje_neto']:
            fotos_pesaje_neto = datos_guia['fotos_pesaje_neto']
        
        # Filtrar fotos válidas (que existan en el sistema de archivos)
        valid_fotos = []
        for foto_path in fotos_pesaje_neto:
            if foto_path and os.path.exists(os.path.join(app.root_path, foto_path)):
                # Convertir ruta relativa a URL absoluta
                valid_fotos.append(url_for('static', filename=foto_path.replace('static/', ''), _external=True))
        
        # Fecha y hora de generación del PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF usando el mismo template que la vista
        html = render_template('pesaje_neto_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', 'No disponible'),
            nombre_proveedor=datos_guia.get('nombre_agricultor', 'No disponible'),
            transportador=datos_guia.get('transportador', 'No disponible'),
            placa=datos_guia.get('placa', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            peso_neto=datos_guia.get('peso_neto', 'No disponible'),
            peso_producto=datos_guia.get('peso_producto', 'No disponible'),
            tipo_pesaje_neto=datos_guia.get('tipo_pesaje_neto', 'No disponible'),
            fecha_pesaje_neto=datos_guia.get('fecha_pesaje_neto', 'No disponible'),
            hora_pesaje_neto=datos_guia.get('hora_pesaje_neto', 'No disponible'),
            racimos=datos_guia.get('racimos', 'No disponible'),
            imagen_bascula_neto=imagen_bascula_neto,
            qr_code=qr_code,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            fotos_pesaje_neto=valid_fotos,
            comentarios_neto=datos_guia.get('comentarios_neto', '')
        )
        
        # Generar PDF desde HTML
        options = {
            'page-size': 'Letter',
            'margin-top': '0.5in',
            'margin-right': '0.5in',
            'margin-bottom': '0.5in',
            'margin-left': '0.5in',
            'encoding': "UTF-8"
        }
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"pesaje_neto_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF
        pdfkit.from_string(html, pdf_path, options=options)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_pesaje_neto', codigo_guia=codigo_guia))



@bp.route('/ver_detalles_registro/<codigo_guia>')
def ver_detalles_registro(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    registro = None
    
    try:
        # Intentar obtener el registro desde la base de datos primero
        archivos = glob.glob(os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html'))
        if archivos:
            archivo_reciente = max(archivos, key=os.path.getmtime)
    except Exception as e:
        logger.error(f"Error al buscar archivo de guía: {str(e)}")
        flash("Error al buscar el registro", "error")
        return redirect(url_for('index'))
        
        with open(archivo_reciente, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
            registro = {
                'codigo_guia': codigo_guia,
                'nombre': soup.find('span', {'id': 'nombre'}).text if soup.find('span', {'id': 'nombre'}) else 'No disponible',
                    'codigo': soup.find('span', {'id': 'codigo'}).text if soup.find('span', {'id': 'codigo'}) else 'No disponible',
                    'fecha_registro': soup.find('span', {'id': 'fecha_registro'}).text if soup.find('span', {'id': 'fecha_registro'}) else 'No disponible',
                    'hora_registro': soup.find('span', {'id': 'hora_registro'}).text if soup.find('span', {'id': 'hora_registro'}) else 'No disponible'
                }



@bp.route('/generar_pdf_completo/<codigo_guia>')
def generar_pdf_completo(codigo_guia):
    """
    Genera un PDF completo con toda la información del proceso.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el registro de salida está completado
        if datos_guia.get('estado_actual') != 'registro_completado':
            flash("El proceso no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Preparar datos para el PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('resultados_salida.html',
            datos=datos_guia,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            is_pdf=True
        )
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"proceso_completo_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF usando WeasyPrint
        HTML(
            string=html,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF completo: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_salida', codigo_guia=codigo_guia))

# Función deshabilitada - El usuario prefiere impresión directa desde el navegador
# 

@bp.route('/generar_pdf_proceso_completo/<codigo_guia>')
def generar_pdf_proceso_completo(codigo_guia):
    """
    Genera un PDF completo con toda la información del proceso.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
        # Verificar que el registro de salida está completado
        if datos_guia.get('estado_actual') != 'registro_completado':
            flash("El proceso no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Preparar datos para el PDF
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('resultados_salida.html',
            datos=datos_guia,
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            is_pdf=True
        )
        
        # Crear directorio para guardar PDFs si no existe
        pdf_dir = os.path.join(app.root_path, 'static', 'pdfs')
        os.makedirs(pdf_dir, exist_ok=True)
        
        # Nombre del archivo PDF
        pdf_filename = f"proceso_completo_{codigo_guia}_{now.strftime('%Y%m%d%H%M%S')}.pdf"
        pdf_path = os.path.join(pdf_dir, pdf_filename)
        
        # Generar el PDF usando WeasyPrint
        HTML(
            string=html,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        # Ruta para acceder al PDF
        pdf_url = url_for('static', filename=f'pdfs/{pdf_filename}')
        
        # Retornar la respuesta
        return redirect(pdf_url)
    except Exception as e:
        logger.error(f"Error generando PDF completo: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error generando PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_salida', codigo_guia=codigo_guia))



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
            clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
            json_path = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia}.json")
            
            if os.path.exists(json_path):
                # Leer los datos de clasificación del archivo JSON
                with open(json_path, 'r') as f:
                    clasificacion_data = json.load(f)
                logger.info(f"Clasificación leída del archivo: {json_path}")
            else:
                flash("No se encontró la clasificación para la guía especificada.", "error")
                return redirect(url_for('index'))
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontraron datos para la guía especificada.", "error")
            return redirect(url_for('index'))
        
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
                
        # Generar QR para la guía si no existe
        qr_filename = f'qr_clasificacion_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('ver_resultados_clasificacion', url_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Obtener fotos de clasificación
        fotos = clasificacion_data.get('fotos', [])
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_generacion = now.strftime('%d/%m/%Y')
        hora_generacion = now.strftime('%H:%M:%S')
        
        # Renderizar el HTML para el PDF
        html = render_template('clasificacion_pdf_template.html',
            codigo_guia=codigo_guia,
            codigo_proveedor=datos_guia.get('codigo_proveedor', clasificacion_data.get('codigo_proveedor', 'No disponible')),
            nombre_proveedor=datos_guia.get('nombre', clasificacion_data.get('nombre_proveedor', 'No disponible')),
            fecha_clasificacion=clasificacion_data.get('fecha_clasificacion', clasificacion_data.get('fecha_registro', 'No disponible')),
            hora_clasificacion=clasificacion_data.get('hora_clasificacion', clasificacion_data.get('hora_registro', 'No disponible')),
            cantidad_racimos=datos_guia.get('cantidad_racimos', clasificacion_data.get('racimos', 'No disponible')),
            clasificacion_manual=clasificacion_data.get('clasificacion_manual', {}),
            clasificacion_automatica=clasificacion_data.get('clasificacion_automatica', {}),
            clasificaciones=clasificaciones,
            fotos=fotos,
            qr_code=url_for('static', filename=f'qr/{qr_filename}', _external=True),
            fecha_generacion=fecha_generacion,
            hora_generacion=hora_generacion,
            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', 'No disponible'),
            peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
            datos_guia=datos_guia
        )
        
        try:
            # Configuración para pdfkit
            options = {
                'page-size': 'Letter',
                'encoding': 'UTF-8',
                'margin-top': '0.5in',
                'margin-right': '0.5in',
                'margin-bottom': '0.5in',
                'margin-left': '0.5in',
                'dpi': 300,
                'disable-smart-shrinking': True
            }
            
            # Intentar encontrar el binario de wkhtmltopdf con which
            wkhtmltopdf_path = None
            try:
                import subprocess
                result = subprocess.run(['which', 'wkhtmltopdf'], capture_output=True, text=True)
                if result.returncode == 0:
                    wkhtmltopdf_path = result.stdout.strip()
                    logger.info(f"wkhtmltopdf encontrado en: {wkhtmltopdf_path}")
            except Exception as e:
                logger.warning(f"Error al buscar wkhtmltopdf: {e}")
            
            # Si hay una ruta válida, crear configuración personalizada
            if wkhtmltopdf_path:
                config = pdfkit.configuration(wkhtmltopdf=wkhtmltopdf_path)
                pdf = pdfkit.from_string(html, False, options=options, configuration=config)
            else:
                # Si no se encuentra wkhtmltopdf, intentar sin configuración específica
                pdf = pdfkit.from_string(html, False, options=options)
            
            # Preparar respuesta
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = f'inline; filename=clasificacion_{codigo_guia}.pdf'
            
            return response
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF con pdfkit: {str(pdf_error)}")
            
            # Fallback method - Redirect to rendering the template directly
            flash("Generando versión imprimible del documento.", "info")
            return render_template('clasificacion_print_view.html',
                codigo_guia=codigo_guia,
                codigo_proveedor=datos_guia.get('codigo_proveedor', clasificacion_data.get('codigo_proveedor', 'No disponible')),
                nombre_proveedor=datos_guia.get('nombre', clasificacion_data.get('nombre_proveedor', 'No disponible')),
                fecha_clasificacion=clasificacion_data.get('fecha_clasificacion', clasificacion_data.get('fecha_registro', 'No disponible')),
                hora_clasificacion=clasificacion_data.get('hora_clasificacion', clasificacion_data.get('hora_registro', 'No disponible')),
                cantidad_racimos=datos_guia.get('cantidad_racimos', clasificacion_data.get('racimos', 'No disponible')),
                clasificacion_manual=clasificacion_data.get('clasificacion_manual', {}),
                clasificacion_automatica=clasificacion_data.get('clasificacion_automatica', {}),
                clasificaciones=clasificaciones,
                fotos=fotos,
                qr_code=url_for('static', filename=f'qr/{qr_filename}', _external=True),
                fecha_generacion=fecha_generacion,
                hora_generacion=hora_generacion,
                codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap', 'No disponible'),
                peso_bruto=datos_guia.get('peso_bruto', 'No disponible'),
                datos_guia=datos_guia
            )
            
    except Exception as e:
        logger.error(f"Error al generar PDF de clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar PDF: {str(e)}", "error")
        return redirect(url_for('ver_resultados_clasificacion', url_guia=codigo_guia))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)


