from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.entrada import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/index')
def index():
    """
    Renders the index page
    """
    return render_template('index.html')



@bp.route('/home')
def home():
    """
    Renders the home page - dashboard for all app sections
    """
    return render_template('home.html')



@bp.route('/processing')
def processing():
    image_filename = session.get('image_filename')
    if not image_filename:
        return render_template('error.html', message="No se encontró una imagen para procesar.")
    return render_template('processing.html')



@bp.route('/process_image', methods=['POST'])
def process_image():
    try:
        image_filename = session.get('image_filename')
        plate_image_filename = session.get('plate_image_filename')
        
        logger.info(f"Iniciando procesamiento de imagen: {image_filename}")
        
        if not image_filename:
            logger.error("No se encontró imagen en la sesión")
            return jsonify({"result": "error", "message": "No se encontró una imagen para procesar."}), 400
        
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        if not os.path.exists(image_path):
            logger.error(f"Archivo no encontrado: {image_path}")
            return jsonify({"result": "error", "message": "Archivo no encontrado."}), 404
        
        # Procesar imagen del tiquete y placa en paralelo
        tiquete_future = None
        placa_future = None
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Iniciar procesamiento del tiquete
            tiquete_future = executor.submit(process_tiquete_image, image_path, image_filename)
            
            # Iniciar procesamiento de la placa si existe
            if plate_image_filename:
                plate_path = os.path.join(app.config['UPLOAD_FOLDER'], plate_image_filename)
                if os.path.exists(plate_path):
                    placa_future = executor.submit(process_plate_image, plate_path, plate_image_filename)
        
        # Obtener resultados
        tiquete_result = tiquete_future.result() if tiquete_future else {"result": "error", "message": "Error procesando tiquete"}
        placa_result = placa_future.result() if placa_future else {"result": "warning", "message": "No se procesó imagen de placa"}
        
        # Verificar resultado del tiquete
        if tiquete_result.get("result") == "error":
            logger.error(f"Error en el procesamiento del tiquete: {tiquete_result.get('message')}")
            return jsonify({"result": "error", "message": tiquete_result.get("message", "Error en el procesamiento")}), 400
        
        # Guardar resultados en sesión
        try:
            session['parsed_data'] = tiquete_result.get("parsed_data", {})
            logger.info(f"Datos parseados guardados en sesión: {session['parsed_data']}")
            
            if placa_result.get("result") != "error":
                session['plate_text'] = placa_result.get("plate_text")
                logger.info(f"Texto de placa guardado en sesión: {session['plate_text']}")
            else:
                session['plate_error'] = placa_result.get("message")
                logger.warning(f"Error en placa guardado en sesión: {session['plate_error']}")
            
            return jsonify({"result": "ok", "redirect": "/review"})
        except Exception as e:
            logger.error(f"Error al guardar datos en sesión: {str(e)}")
            return jsonify({"result": "error", "message": f"Error al guardar datos en sesión: {str(e)}"}), 500
        
    except Exception as e:
        logger.error(f"Error al procesar la imagen: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "result": "error", 
            "message": f"Error al procesar la imagen: {str(e)}"
        }), 500

def process_tiquete_image(image_path, filename):
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            response = requests.post(PROCESS_WEBHOOK_URL, files=files)
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de tiquete: {response.text}")
            return {"result": "error", "message": f"Error del webhook de tiquete: {response.text}"}
            
        response_text = response.text.strip()
        # Registra la respuesta raw del webhook para debugging
        logger.info(f"Respuesta raw del webhook de tiquete: {response_text}")
        
        if not response_text:
            logger.error("Respuesta vacía del webhook de tiquete")
            return {"result": "error", "message": "Respuesta vacía del webhook de tiquete."}
            
        parsed_data = parse_markdown_response(response_text)
        # Registra los datos parseados para debugging
        logger.info(f"Datos parseados del tiquete: {parsed_data}")
        
        if not parsed_data:
            logger.error("No se pudieron parsear los datos de la respuesta del tiquete")
            return {"result": "error", "message": "No se pudieron parsear los datos del tiquete."}
        
        return {"result": "ok", "parsed_data": parsed_data}
        
    except Exception as e:
        logger.error(f"Error procesando imagen de tiquete: {str(e)}")
        return {"result": "error", "message": str(e)}

def process_plate_image(image_path, filename):
    try:
        with open(image_path, 'rb') as f:
            files = {'file': (filename, f, 'multipart/form-data')}
            response = requests.post(PLACA_WEBHOOK_URL, files=files)
            
        if response.status_code != 200:
            logger.error(f"Error del webhook de placa: {response.text}")
            return {"result": "error", "message": f"Error del webhook de placa: {response.text}"}
            
        plate_text = response.text.strip()
        if not plate_text:
            logger.error("Respuesta vacía del webhook de placa")
            return {"result": "error", "message": "No se pudo detectar la placa."}
        
        return {"result": "ok", "plate_text": plate_text}
        
    except Exception as e:
        logger.error(f"Error procesando imagen de placa: {str(e)}")
        return {"result": "error", "message": str(e)}



@bp.route('/review', methods=['GET'])
def review():
    parsed_data = session.get('parsed_data', {})
    image_filename = session.get('image_filename', '')
    plate_image_filename = session.get('plate_image_filename', '')
    plate_text = session.get('plate_text', '')
    plate_error = session.get('plate_error', '')
    
    if not parsed_data or not image_filename:
        return render_template('error.html', message="No hay datos para revisar.")
    
    if 'table_data' not in parsed_data:
        logger.error("Formato de datos incorrecto")
        return render_template('error.html', message="Error en el formato de los datos.")
    
    timestamp = datetime.now().timestamp()
    
    return render_template(
        'review.html',
        image_filename=image_filename,
        parsed_data=parsed_data,
        timestamp=timestamp,
        plate_image_filename=plate_image_filename,
        plate_text=plate_text,
        plate_error=plate_error
    )



@bp.route('/update_data', methods=['POST'])
def update_data():
    """
    Envía todos los datos al webhook de revalidación y procesa la respuesta.
    """
    try:
        # Obtener datos del request
        request_data = request.get_json()
        if not request_data or 'table_data' not in request_data:
            logger.error("Datos inválidos recibidos en el request")
            return jsonify({
                "status": "error",
                "message": "Datos inválidos",
                "redirect": url_for('review', _external=True)
            }), 400

        table_data = request_data['table_data']
        
        # Obtener el código del agricultor
        codigo = next((row.get('sugerido', row.get('original', '')) 
                     for row in table_data if row.get('campo') == 'Código'), '')
        
        if not codigo:
            logger.error("Código faltante en los datos")
            return jsonify({
                "status": "error",
                "message": "Código faltante en los datos",
                "redirect": url_for('review', _external=True)
            }), 400

        # Preparar datos para el webhook
        payload = {
            "codigo": codigo,
            "datos": [
                {"campo": row.get('campo', ''), 
                 "valor": row.get('sugerido', row.get('original', ''))}
                for row in table_data
            ]
        }
        
        logger.info(f"Enviando datos al webhook: {payload}")
        
        # Guardar table_data en la sesión independientemente del resultado del webhook
        session['table_data'] = table_data
        session.modified = True
        
        # Convertir los datos de la tabla a un formato compatible con la plantilla
        formatted_data = {}
        for item in payload["datos"]:
            campo = item["campo"]
            valor = item["valor"]
            # Mapear los nombres de campos a las claves esperadas por la plantilla
            if campo == "Nombre del Agricultor":
                formatted_data["nombre_agricultor"] = valor
                formatted_data["Nombre del Agricultor"] = valor  # Mantener ambos formatos
            elif campo == "Código":
                formatted_data["codigo"] = valor
                formatted_data["Código"] = valor  # Mantener ambos formatos
            elif campo == "Cantidad de Racimos":
                formatted_data["racimos"] = valor
                formatted_data["Cantidad de Racimos"] = valor  # Mantener ambos formatos
            elif campo == "Placa":
                formatted_data["placa"] = valor
                formatted_data["Placa"] = valor  # Mantener ambos formatos
            elif campo == "Se Acarreó":
                formatted_data["acarreo"] = valor
                formatted_data["Se Acarreó"] = valor  # Mantener ambos formatos
            elif campo == "Se Cargó":
                formatted_data["cargo"] = valor
                formatted_data["Se Cargó"] = valor  # Mantener ambos formatos
            elif campo == "Transportador":
                formatted_data["transportador"] = valor
                formatted_data["Transportador"] = valor  # Mantener ambos formatos
            elif campo == "Fecha":
                formatted_data["fecha_tiquete"] = valor
                formatted_data["Fecha"] = valor  # Mantener ambos formatos
            elif campo == "Nota":
                formatted_data["nota"] = valor
                formatted_data["Nota"] = valor  # Mantener ambos formatos
            else:
                # Para cualquier otro campo, usar el nombre original
                formatted_data[campo.lower().replace(" ", "_")] = valor
                formatted_data[campo] = valor  # Mantener el formato original también
        
        # Registrar los datos formateados para depuración
        logger.info(f"Datos formateados localmente: {formatted_data}")
        
        try:
            # Aumentar el timeout a 60 segundos
            response = requests.post(
                REVALIDATION_WEBHOOK_URL, 
                json=payload, 
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
        
            # Limpiar la respuesta si contiene backticks
            response_text = response.text
            if response_text.startswith('```json'):
                response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            try:
                response_data = json.loads(response_text)
                logger.info(f"Respuesta recibida del webhook: {response_data}")
                
                # Verificar si la respuesta tiene el formato esperado
                if 'status' in response_data and 'data' in response_data:
                    # Asegurarse de que los datos tengan el formato correcto
                    if isinstance(response_data['data'], dict):
                        # Combinar los datos formateados con los datos de la respuesta
                        # para asegurar que tenemos todas las claves necesarias
                        for key, value in formatted_data.items():
                            if key not in response_data['data']:
                                response_data['data'][key] = value
                    else:
                        logger.warning(f"La respuesta del webhook no tiene el formato esperado: {response_data}")
                        response_data = {
                            "status": "success",
                            "data": formatted_data
                        }
                else:
                    logger.warning(f"La respuesta del webhook no tiene el formato esperado: {response_data}")
                    response_data = {
                        "status": "success",
                        "data": formatted_data
                    }
            except json.JSONDecodeError as e:
                logger.error(f"Error decodificando la respuesta JSON del webhook: {str(e)}")
                response_data = {
                    "status": "success",
                    "data": formatted_data
                }
            
            # Guardar datos en la sesión
            session['webhook_response'] = response_data
            session.modified = True
            
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.error(f"Error en la comunicación con el webhook: {str(e)}")
            # Crear respuesta local con los datos del formulario
            response_data = {
                "status": "success",
                "data": formatted_data
            }
            
            # Guardar datos en la sesión
            session['webhook_response'] = response_data
            session.modified = True
                
        if response_data.get('status') == 'success':
                logger.info("Datos guardados en sesión, redirigiendo a revalidation_success")
                return jsonify({
                    "status": "success",
                    "redirect": url_for('revalidation_success', _external=True)
                })
        else:
            logger.error("Error en la validación")
            return jsonify({
                "status": "error", 
                "message": response_data.get('message', 'Error en la validación'),
                    "redirect": url_for('revalidation_results', _external=True)
            })
            
    except Exception as e:
        logger.error(f"Error en update_data: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "status": "error",
            "message": str(e),
            "redirect": url_for('review', _external=True)
        }), 500



@bp.route('/processing', methods=['GET'])
def processing_screen():
    """
    Pantalla de carga mientras se procesa la revalidación.
    """
    return render_template('processing.html')


# >>> NUEVO: Función para generar QR y devolver su nombre o ruta
def generate_qr_image(codigo, nombre, fruta):
    """
    Genera un archivo PNG de código QR que contenga info clave (código, agricultor, fruta).
    Retorna el nombre de archivo PNG.
    """
    content = f"Código: {codigo}\nAgricultor: {nombre}\nFruta: {fruta}"
    qr_img = qrcode.make(content)
    
    # Guardarlo en static con un nombre único
    qr_filename = f"qr_{codigo}_{int(time.time())}.png"
    qr_path = os.path.join(app.static_folder, qr_filename)
    qr_img.save(qr_path)
    
    # Retornar sólo el nombre, para usarlo en la plantilla
    return qr_filename


def generate_pdf(parsed_data, image_filename, fecha_procesamiento, hora_procesamiento, revalidation_data=None):
    try:
        logger.info("Iniciando generación de PDF")
        logger.info(f"Datos de revalidación: {revalidation_data}")
        
        fecha_registro = None
        for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_registro = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                break
        
        if not fecha_registro:
            fecha_registro = datetime.now().strftime("%d-%m-%Y")
       
        qr_data = {
            "codigo": revalidation_data.get('Código') if revalidation_data else parsed_data.get('codigo', ''),
            "nombre": revalidation_data.get('Nombre del Agricultor') if revalidation_data else parsed_data.get('nombre_agricultor', ''),
            "fecha": fecha_registro,
            "placa": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Placa'), ''),
            "transportador": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Transportador'), ''),
            "cantidad_racimos": next((row['sugerido'] for row in parsed_data.get('table_data', []) if row['campo'] == 'Cantidad de Racimos'), '')
        }
        
        qr_filename = f"qr_{qr_data['codigo']}_{int(time.time())}.png"
        qr_path = os.path.join(app.static_folder, qr_filename)
        utils.generate_qr(qr_data, qr_path)
        
        # Renderizar plantilla
        rendered = render_template(
            'pdf_template.html',
            parsed_data=parsed_data,
            revalidation_data=revalidation_data,
            image_filename=image_filename,
            fecha_registro=fecha_registro,
            fecha_procesamiento=fecha_registro,  # Usar la fecha del tiquete
            hora_procesamiento=hora_procesamiento,
            fecha_emision=datetime.now().strftime("%d-%m-%Y"),
            hora_emision=datetime.now().strftime("%H:%M:%S"),
            qr_filename=qr_filename
        )
        
        # Generar PDF
        pdf_filename = f'tiquete_{qr_data["codigo"]}_{fecha_registro}.pdf'
        pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
        
        HTML(
            string=rendered,
            base_url=app.static_folder
        ).write_pdf(pdf_path)
        
        logger.info(f"PDF generado exitosamente: {pdf_filename}")
        return pdf_filename
        
    except Exception as e:
        logger.error(f"Error en generate_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        raise Exception(f"Error generando PDF: {str(e)}")



@bp.route('/register', methods=['POST'])
def register():
    try:
        logger.info("Iniciando proceso de registro")
        
        # Obtener datos del webhook response
        webhook_response = session.get('webhook_response', {})
        if not webhook_response or not webhook_response.get('data'):
            return jsonify({
                "status": "error",
                "message": "No hay datos del webhook para registrar."
            }), 400

        # Obtener datos del webhook
        webhook_data = webhook_response.get('data', {})
        
        # Obtener fecha y hora actual
        now = datetime.now()
        fecha_registro = now.strftime("%d/%m/%Y")
        hora_registro = now.strftime("%H:%M:%S")
        
        # Obtener código del agricultor
        codigo = webhook_data.get('codigo', '').strip()
        if not codigo:
            return jsonify({
                "status": "error",
                "message": "No se encontró el código del agricultor en los datos del webhook."
            }), 400
            
        # Generar código de guía único usando la función en Utils
        codigo_guia = utils.generar_codigo_guia(codigo)
        
        # Guardar en sesión
        session['fecha_registro'] = fecha_registro
        session['hora_registro'] = hora_registro
        session['codigo_guia'] = codigo_guia
        
        # Generar QR
        qr_filename = f"qr_{codigo}_{now.strftime('%Y%m%d_%H%M%S')}.png"
        
        # Preparar datos para el QR
        qr_data = {
            "codigo": webhook_data.get('codigo', ''),
            "nombre": webhook_data.get('nombre_agricultor', ''),
            "placa": webhook_data.get('placa', ''),
            "transportador": webhook_data.get('transportador', ''),
            "cantidad_racimos": webhook_data.get('racimos', ''),
            "acarreo": webhook_data.get('acarreo', 'No'),
            "cargo": webhook_data.get('cargo', 'No'),
            "nota": webhook_data.get('nota', ''),
            "codigo_guia": codigo_guia
        }
        
        logger.info(f"Generando QR con datos: {qr_data}")
        
        # Generar QR usando la utilidad
        utils.generate_qr(qr_data, qr_filename)
        session['qr_filename'] = qr_filename
        
        # Generar URL del código QR
        base_url = "http://localhost:5002"  # Ajusta según tu configuración
        url_qr = f"{base_url}/guias/guia_{codigo_guia}.html"
        
        # Enviar datos al webhook de registro
        try:
            response = requests.post(
                REGISTER_WEBHOOK_URL,
                json={
                    "codigo": webhook_data.get('codigo', ''),
                    "nombre": webhook_data.get('nombre_agricultor', ''),
                    "placa": webhook_data.get('placa', ''),
                    "transportador": webhook_data.get('transportador', ''),
                    "racimos": webhook_data.get('racimos', ''),
                    "acarreo": webhook_data.get('acarreo', 'No'),
                    "cargo": webhook_data.get('cargo', 'No'),
                    "nota": webhook_data.get('nota', ''),
                    "fecha": fecha_registro,
                    "hora": hora_registro,
                    "fecha_tiquete": webhook_data.get('fecha_tiquete', ''),
                    "se_transporto": webhook_data.get('se_transporto', 'No'),
                    "url_qr": f"http://localhost:5002/guias/guia_{codigo_guia}.html",
                    "codigo_guia": codigo_guia
                },
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code != 200:
                logger.error(f"Error en webhook de registro: {response.text}")
                raise Exception("Error al registrar en el sistema central")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error llamando webhook de registro: {str(e)}")
            raise Exception("Error de conexión con el sistema central")
        
        # Generar PDF
        pdf_filename = utils.generate_pdf(
            parsed_data=None,
            image_filename=session.get('image_filename', ''),
            fecha_procesamiento=fecha_registro,
            hora_procesamiento=hora_registro,
            revalidation_data=None,
            codigo_guia=codigo_guia
        )
        
        session['pdf_filename'] = pdf_filename
        session['estado_actual'] = 'pesaje'
        
        # Obtener el código guía completo del nombre del archivo PDF
        codigo_guia_completo = pdf_filename[8:-4]  # Remover 'tiquete_' y '.pdf'
        
        return jsonify({
            "status": "success",
            "message": "Registro completado exitosamente",
            "pdf_filename": pdf_filename,
            "qr_filename": qr_filename,
            "redirect_url": url_for('pesaje', codigo=codigo_guia_completo, _external=True)
        })
        
    except Exception as e:
        logger.error(f"Error general en registro: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"Error al registrar: {str(e)}"
        }), 500


    


@bp.route('/review_pdf')
def review_pdf():
    """
    Muestra una página con el enlace del PDF generado y el código QR.
    """
    pdf_filename = session.get('pdf_filename')
    qr_filename = session.get('qr_filename')
    image_filename = session.get('image_filename')
    plate_image_filename = session.get('plate_image_filename')
    codigo_guia = session.get('codigo_guia')
    
    # Recuperar datos del webhook response guardados en session
    webhook_response = session.get('webhook_response', {})
    webhook_data = webhook_response.get('data', {})
    
    # Intentar obtener todos los datos validados de la revalidation_success
    # Si no están disponibles, usar los datos del webhook_response
    if webhook_data:
        nombre_agricultor = webhook_data.get('nombre_agricultor', 'No disponible')
        codigo = webhook_data.get('codigo', 'No disponible')
        racimos = webhook_data.get('racimos', 'No disponible')
        placa = webhook_data.get('placa', 'No disponible')
        acarreo = webhook_data.get('acarreo', 'No disponible')
        cargo = webhook_data.get('cargo', 'No disponible')
        transportador = webhook_data.get('transportador', 'No disponible')
        fecha_tiquete = webhook_data.get('fecha_tiquete', 'No disponible')
        nota = webhook_data.get('nota', 'No disponible')
    else:
        # Usar los datos guardados directamente en la sesión
        nombre_agricultor = session.get('nombre_agricultor', 'No disponible')
        codigo = session.get('codigo', 'No disponible')
        racimos = session.get('racimos', 'No disponible')
        placa = session.get('placa', 'No disponible')
        acarreo = session.get('acarreo', 'No disponible')
        cargo = session.get('cargo', 'No disponible')
        transportador = session.get('transportador', 'No disponible')
        fecha_tiquete = session.get('fecha_tiquete', 'No disponible')
        nota = session.get('nota', 'No disponible')
    
    # Obtener fecha y hora de registro
    fecha_registro = session.get('fecha_registro', datetime.now().strftime("%d/%m/%Y"))
    hora_registro = session.get('hora_registro', datetime.now().strftime("%H:%M:%S"))
    plate_text = session.get('plate_text', '')
    
    if not pdf_filename or not qr_filename:
        return render_template('error.html', message="No se encontró el PDF o QR generado.")
    
    # Agregar logs para depuración
    logger.info(f"Datos para PDF: nombre={nombre_agricultor}, codigo={codigo}, racimos={racimos}, nota={nota}")
    
    # Recuperar indicadores de campos modificados
    nombre_agricultor_modificado = session.get('nombre_agricultor_modificado', False)
    codigo_modificado = session.get('codigo_modificado', False)
    cantidad_de_racimos_modificado = session.get('cantidad_de_racimos_modificado', False)
    placa_modificado = session.get('placa_modificado', False)
    acarreo_modificado = session.get('acarreo_modificado', False)
    cargo_modificado = session.get('cargo_modificado', False)
    transportador_modificado = session.get('transportador_modificado', False)
    fecha_modificado = session.get('fecha_modificado', False)
    
    return render_template('review_pdf.html', 
                         pdf_filename=pdf_filename,
                          qr_filename=qr_filename,
                          image_filename=image_filename,
                          plate_image_filename=plate_image_filename,
                          codigo_guia=codigo_guia,
                          nombre_agricultor=nombre_agricultor,
                          codigo=codigo,
                          racimos=racimos,
                          placa=placa,
                          acarreo=acarreo,
                          cargo=cargo,
                          transportador=transportador,
                          fecha_tiquete=fecha_tiquete,
                          fecha_registro=fecha_registro,
                          hora_registro=hora_registro,
                          plate_text=plate_text,
                          nota=nota,
                          nombre_agricultor_modificado=nombre_agricultor_modificado,
                          codigo_modificado=codigo_modificado,
                          cantidad_de_racimos_modificado=cantidad_de_racimos_modificado,
                          placa_modificado=placa_modificado,
                          acarreo_modificado=acarreo_modificado,
                          cargo_modificado=cargo_modificado, 
                          transportador_modificado=transportador_modificado,
                          fecha_modificado=fecha_modificado)



@bp.route('/registros-entrada', methods=['GET'])
def lista_registros_entrada():
    """
    Muestra la lista de registros de entrada.
    """
    try:
        # Obtener los parámetros de filtro de la URL
        fecha_desde = request.args.get('fecha_desde', '')
        fecha_hasta = request.args.get('fecha_hasta', '')
        codigo_proveedor = request.args.get('codigo_proveedor', '')
        nombre_proveedor = request.args.get('nombre_proveedor', '')
        placa = request.args.get('placa', '')

        # Preparar filtros para la consulta
        filtros = {
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'codigo_proveedor': codigo_proveedor,
            'nombre_proveedor': nombre_proveedor,
            'placa': placa
        }
        
        # Inicializar la lista de registros
        registros = []
        
        # Intentar obtener registros de la base de datos
        try:
            import db_utils
            from db_operations import get_pesaje_bruto_by_codigo_guia
            
            registros_db = db_utils.get_entry_records(filtros)
            
            if registros_db:
                logger.info(f"Obtenidos {len(registros_db)} registros de la base de datos")
                # Ya están ordenados por fecha_registro DESC, hora_registro DESC
                registros = registros_db
                
                # Cargar los pesajes existentes para verificar cuáles tienen pesaje
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para cada registro
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
            else:
                logger.info("No se encontraron registros en la base de datos. Buscando en archivos.")
                
                # Si no hay registros en la base de datos, buscar en archivos (compatibilidad)
                registros = obtener_registros_desde_archivos(filtros)
                
                # Cargar los pesajes existentes para verificar cuáles tienen pesaje
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para registros de archivos
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
        except Exception as db_error:
            logger.error(f"Error accediendo a la base de datos: {db_error}")
            # En caso de error con la base de datos, buscar en archivos
            registros = obtener_registros_desde_archivos(filtros)
            
            # Cargar los pesajes existentes para verificar cuáles tienen pesaje
            try:
                conn = sqlite3.connect('tiquetes.db')
                cursor = conn.cursor()
                cursor.execute("SELECT codigo_guia FROM pesajes_bruto")
                pesajes_existentes = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                # Verificar el estado de pesaje para registros de archivos
                for registro in registros:
                    # Verificar si existe un pesaje para este código de guía
                    if registro['codigo_guia'] in pesajes_existentes:
                        # Si existe pesaje, marcarlo para que no se muestre el botón de pesaje
                        registro['tiene_pesaje'] = True
                    else:
                        registro['tiene_pesaje'] = False
            except Exception as e:
                logger.error(f"Error al verificar pesajes existentes: {str(e)}")
                # En caso de error, asumir que ningún registro tiene pesaje
                for registro in registros:
                    registro['tiene_pesaje'] = False
        
        
        return render_template('registros_entrada.html', registros=registros, filtros=filtros)
        
    except Exception as e:
        logger.error(f"Error listando registros de entrada: {str(e)}")
        logger.error(traceback.format_exc())
        flash('Error al listar registros de entrada', 'error')
        return redirect(url_for('upload_file'))

def obtener_registros_desde_archivos(filtros):
    """
    Función auxiliar para obtener registros desde archivos HTML (método antiguo).
    
    Args:
        filtros (dict): Diccionario con filtros a aplicar
    
    Returns:
        list: Lista de registros encontrados
    """
    # Extraer filtros
    fecha_desde = filtros.get('fecha_desde', '')
    fecha_hasta = filtros.get('fecha_hasta', '')
    codigo_proveedor = filtros.get('codigo_proveedor', '')
    nombre_proveedor = filtros.get('nombre_proveedor', '')
    placa = filtros.get('placa', '')
    
    # Preparar lista de registros
    registros = []
    
    # Verificar si el directorio de guías existe
    guias_dir = os.path.join(app.static_folder, 'guias')
    
    # Mapa para agrupar guías por código base
    guias_por_codigo_base = {}
    
    if os.path.exists(guias_dir):
        for filename in os.listdir(guias_dir):
            if filename.startswith('guia_') and filename.endswith('.html'):
                codigo_guia = filename.replace('guia_', '').replace('.html', '')
                
                # Extraer el código base (sin timestamp ni versión)
                codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
                
                # Obtener datos de la guía usando la función mejorada get_datos_guia 
                # que primero busca en DB, luego en archivos y finalmente en sesión
                try:
                    # Usar el método mejorado get_datos_guia en lugar de get_datos_registro
                    datos = utils.get_datos_guia(codigo_guia)
                except Exception as e:
                    logger.error(f"Error obteniendo datos para {codigo_guia}: {str(e)}")
                    continue
                
                if datos:
                    # Filtrar por fecha
                    if fecha_desde and fecha_hasta:
                        # Convertir fecha de registro a formato comparable (aaaa-mm-dd)
                        try:
                            fecha_obj = datetime.strptime(datos.get('fecha_registro', ''), '%d/%m/%Y')
                            fecha_registro_str = fecha_obj.strftime('%Y-%m-%d')
                            
                            if fecha_registro_str < fecha_desde or fecha_registro_str > fecha_hasta:
                                continue
                        except:
                            # Si hay error al parsear, no filtrar por fecha
                            pass
                    
                    # Filtrar por código de proveedor
                    if codigo_proveedor and codigo_proveedor.lower() not in datos.get('codigo_proveedor', '').lower():
                        continue
                    
                    # Filtrar por nombre de proveedor
                    if nombre_proveedor and nombre_proveedor.lower() not in datos.get('nombre_proveedor', '').lower():
                        continue
                    
                    # Filtrar por placa
                    if placa and placa.lower() not in datos.get('placa', '').lower():
                        continue
                        
                    # Añadir fecha de modificación del archivo para ordenar correctamente
                    file_path = os.path.join(guias_dir, filename)
                    try:
                        mod_time = os.path.getmtime(file_path)
                        datos['file_mod_time'] = mod_time
                    except Exception:
                        datos['file_mod_time'] = 0
                        
                    # Guardar guías agrupadas por código base
                    if codigo_base not in guias_por_codigo_base:
                        guias_por_codigo_base[codigo_base] = []
                    
                    guias_por_codigo_base[codigo_base].append(datos)
    
    # Ahora procesamos cada grupo de guías con el mismo código base
    for codigo_base, guias_grupo in guias_por_codigo_base.items():
        # Ordenar por tiempo de modificación, más reciente primero
        guias_grupo.sort(key=lambda x: x.get('file_mod_time', 0), reverse=True)
        
        # Para cada grupo, tomamos solo la versión más reciente
        # A menos que tenga un sufijo "_R" que indica una revisión/actualización
        guias_filtradas = []
        ultima_guia = guias_grupo[0]  # La más reciente
        guias_filtradas.append(ultima_guia)
        
        # Buscar si hay revisiones (sufijo _R) y agregarlas también
        for guia in guias_grupo[1:]:
            codigo_guia = guia.get('codigo_guia', '')
            if '_R' in codigo_guia and codigo_guia not in [g.get('codigo_guia', '') for g in guias_filtradas]:
                guias_filtradas.append(guia)
        
        # Convertir las guías filtradas a registros
        for datos in guias_filtradas:
            # Asegurar que el código proveedor termine con A mayúscula
            codigo_proveedor = datos.get('codigo_proveedor', '')
            if codigo_proveedor and codigo_proveedor.endswith('a'):
                datos['codigo_proveedor'] = codigo_proveedor[:-1] + 'A'
            
            # Añadir información estructurada para la tabla
        registro = {
            'codigo_guia': datos.get('codigo_guia', ''),
            'codigo_proveedor': datos.get('codigo_proveedor', ''),
            'nombre_proveedor': datos.get('nombre_proveedor', ''),
            'fecha_registro': datos.get('fecha_registro', ''),
            'hora_registro': datos.get('hora_registro', ''),
            'placa': datos.get('placa', ''),
            'cantidad_racimos': datos.get('cantidad_racimos', ''),
            'transportador': datos.get('transportador', ''),
            'acarreo': datos.get('acarreo', ''),
            'cargo': datos.get('cargo', ''),
            'image_filename': datos.get('image_filename', '')
        }
        registros.append(registro)
        
    # Ordenar por fecha y hora más reciente
    def parse_datetime(registro):
        """
        Convierte fecha y hora de un registro a un objeto datetime para ordenamiento.
        Si no hay fecha o hay un error en el formato, devuelve una fecha muy antigua.
        """
        fecha = registro.get('fecha_registro', '')
        hora = registro.get('hora_registro', '')
        
        # Si no hay fecha y/o hora, intentar extraer del código_guia
        if not fecha or fecha == 'No disponible':
            codigo_guia = registro.get('codigo_guia', '')
            parts = codigo_guia.split('_')
            if len(parts) >= 2 and len(parts[1]) == 8 and parts[1].isdigit():
                try:
                    # Intentar extraer fecha del código_guia formato YYYYMMDD
                    fecha_obj = datetime.strptime(parts[1], '%Y%m%d')
                    fecha = fecha_obj.strftime('%d/%m/%Y')
                except:
                    return datetime(1900, 1, 1)
            else:
                return datetime(1900, 1, 1)
        
        try:
            # Intentar convertir fecha y hora
            fecha_obj = datetime.strptime(f"{fecha} {hora}", "%d/%m/%Y %H:%M:%S")
            return fecha_obj
        except Exception:
            # Intentar solo con la fecha si falla la conversión con hora
            try:
                fecha_obj = datetime.strptime(fecha, "%d/%m/%Y")
                return fecha_obj
            except Exception:
                return None
    
    # Ordenar registros por fecha y hora, más reciente primero
    registros.sort(key=parse_datetime, reverse=True)
    
    return registros



@bp.route('/registro-entrada/<codigo_guia>', methods=['GET'])
def ver_registro_entrada(codigo_guia):
    """
    Muestra los detalles de un registro de entrada específico.
    """
    registro = None
    # Intentar obtener el registro desde la base de datos primero
    try:
        import db_utils
        registro = db_utils.get_entry_record_by_guide_code(codigo_guia)
    except Exception as db_error:
        logger.error(f"Error accediendo a la base de datos: {db_error}")
        
    if registro:
        logger.info(f"Registro encontrado en la base de datos: {codigo_guia}")
    
    # Si no se encontró en la base de datos, intentar obtenerlo del archivo
    if not registro:
            logger.info(f"Buscando registro en archivos: {codigo_guia}")
            registro = utils.get_datos_registro(codigo_guia)
            
            if not registro:
                # Mensaje específico cuando el código no se encuentra en la base de datos ni en archivos
                flash(f'El registro con código {codigo_guia} no fue encontrado ni en la base de datos ni en los archivos', 'warning')
                return redirect(url_for('lista_registros_entrada'))
            try:
                return render_template('registro_entrada_detalle.html', registro=registro)
            except Exception as e:
                logger.error(f"Error obteniendo detalles del registro: {str(e)}")
                logger.error(traceback.format_exc())
                flash('Error al obtener detalles del registro', 'error')
                return redirect(url_for('lista_registros_entrada'))



