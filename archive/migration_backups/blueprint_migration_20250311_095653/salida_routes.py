from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.salida import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/registro-salida/<codigo_guia>')
def registro_salida(codigo_guia):
    """
    Muestra la vista de registro de salida para una guía específica.
    Esta es la etapa final del proceso después del pesaje neto.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar que el pesaje neto esté completado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia))
            
        # Obtener fecha y hora actuales para mostrar en el formulario
        now = datetime.now()
        now_date = now.strftime('%d/%m/%Y')
        now_time = now.strftime('%H:%M:%S')
        
        return render_template('registro_salida.html', 
                              datos=datos_guia,
                              now_date=now_date,
                              now_time=now_time)
    except Exception as e:
        logger.error(f"Error al mostrar registro de salida: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar registro de salida: {str(e)}", "error")
        return redirect(url_for('index'))



@bp.route('/completar_registro_salida', methods=['POST'])
def completar_registro_salida():
    """
    Procesa el formulario de registro de salida y completa el proceso.
    """
    try:
        # Obtener datos del formulario
        data = request.get_json()
        codigo_guia = data.get('codigo_guia')
        fecha_salida = data.get('fecha_salida')
        hora_salida = data.get('hora_salida')
        comentarios = data.get('comentarios', '')
        firma_base64 = data.get('firma')
        
        if not codigo_guia:
            return jsonify({
                'success': False,
                'message': 'Falta el código de guía'
            }), 400
            
        # Obtener datos actuales de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return jsonify({
                'success': False,
                'message': 'Guía no encontrada'
            }), 404
            
        # Guardar la firma si se proporcionó
        firma_filename = None
        if firma_base64 and firma_base64.startswith('data:image/png;base64,'):
            # Extraer la parte de datos base64
            firma_data = firma_base64.split(',')[1]
            # Decodificar y guardar como archivo
            firma_filename = f'firma_{codigo_guia}.png'
            firma_path = os.path.join(app.config['STATIC_FOLDER'], 'firmas', firma_filename)
            
            # Asegurar que el directorio existe
            os.makedirs(os.path.dirname(firma_path), exist_ok=True)
            
            # Guardar el archivo
            with open(firma_path, 'wb') as f:
                f.write(base64.b64decode(firma_data))
        
        # Actualizar datos de la guía
        datos_guia.update({
            'fecha_salida': fecha_salida,
            'hora_salida': hora_salida,
            'comentarios_salida': comentarios,
            'firma_salida': firma_filename,
            'estado_actual': 'registro_completado'
        })
        
        # Guardar en la base de datos si está configurado
        try:
            import db_operations
            db_operations.store_registro_salida({
                'codigo_guia': codigo_guia,
                'fecha_salida': fecha_salida,
                'hora_salida': hora_salida,
                'comentarios': comentarios,
                'firma_path': firma_filename,
                'fecha_registro': datetime.now().strftime('%d/%m/%Y'),
                'hora_registro': datetime.now().strftime('%H:%M:%S')
            })
        except Exception as db_error:
            logger.error(f"Error al guardar en la base de datos: {str(db_error)}")
            # Continuamos aunque falle la base de datos
        
        # Generar HTML actualizado
        html_content = render_template(
            'guia_template.html',
            **datos_guia
        )
        
        # Actualizar el archivo de la guía
        guia_path = os.path.join(app.config['GUIAS_FOLDER'], f'guia_{codigo_guia}.html')
        with open(guia_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Generar un nuevo PDF con los datos actualizados
        try:
            pdf_filename = f'guia_{codigo_guia}.pdf'
            pdf_path = os.path.join(app.config['PDF_FOLDER'], pdf_filename)
            utils.generate_pdf(datos_guia, None, fecha_salida, hora_salida, None, codigo_guia)
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF: {str(pdf_error)}")
            # Continuamos aunque falle la generación del PDF
        
        return jsonify({
            'success': True,
            'message': 'Registro de salida completado exitosamente',
            'redirect_url': url_for('ver_resultados_salida', codigo_guia=codigo_guia)
        })
    except Exception as e:
        logger.error(f"Error al completar registro de salida: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al completar registro de salida: {str(e)}'
        }), 500



@bp.route('/ver_resultados_salida/<codigo_guia>')
def ver_resultados_salida(codigo_guia):
    """
    Muestra los resultados del registro de salida para una guía específica.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la salida ha sido registrada
        if 'fecha_salida' not in datos_guia or not datos_guia['fecha_salida']:
            flash("El registro de salida no ha sido completado para esta guía.", "warning")
            return redirect(url_for('registro_salida', codigo_guia=codigo_guia))
        
        # Asegurarse de que todos los datos necesarios estén disponibles
        datos_completos = {
            # Datos básicos
            'codigo_guia': codigo_guia,
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_proveedor', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'cantidad_racimos': datos_guia.get('cantidad_racimos', 'No disponible'),
            
            # Datos de registro de entrada
            'fecha_registro': datos_guia.get('fecha_registro', 'No disponible'),
            'hora_registro': datos_guia.get('hora_registro', 'No disponible'),
            
            # Datos de pesaje bruto
            'peso_bruto': datos_guia.get('peso_bruto', 'No disponible'),
            'fecha_pesaje': datos_guia.get('fecha_pesaje', 'No disponible'),
            'hora_pesaje': datos_guia.get('hora_pesaje', 'No disponible'),
            'imagen_peso': datos_guia.get('imagen_peso', None),
            
            # Datos de pesaje neto
            'peso_neto': datos_guia.get('peso_neto', 'No disponible'),
            'peso_producto': datos_guia.get('peso_producto', 'No disponible'),
            'fecha_pesaje_neto': datos_guia.get('fecha_pesaje_neto', 'No disponible'),
            'hora_pesaje_neto': datos_guia.get('hora_pesaje_neto', 'No disponible'),
            'imagen_peso_neto': datos_guia.get('imagen_peso_neto', None),
            
            # Datos de registro de salida
            'fecha_salida': datos_guia.get('fecha_salida', 'No disponible'),
            'hora_salida': datos_guia.get('hora_salida', 'No disponible'),
            'comentarios_salida': datos_guia.get('comentarios_salida', ''),
            'firma_salida': datos_guia.get('firma_salida', None),
            
            # Datos adicionales
            'verificacion_placa': datos_guia.get('verificacion_placa')
        }
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if datos_completos['verificacion_placa'] is None:
            datos_completos['verificacion_placa'] = {}
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_salida_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('salida.ver_resultados_salida', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
            
        datos_completos['qr_code'] = url_for('static', filename=f'qr/{qr_filename}')
        
        # Si hay firma, asegurarse de que se pueda mostrar correctamente
        if datos_completos['firma_salida']:
            datos_completos['firma_salida_url'] = url_for('static', filename=f'firmas/{datos_completos["firma_salida"]}')
        
        # Generar PDF completo si no existe
        try:
            pdf_filename = generar_pdf_completo(codigo_guia)
            if pdf_filename:
                datos_completos['pdf_url'] = url_for('static', filename=f'pdf/{pdf_filename}')
        except Exception as pdf_error:
            logger.error(f"Error al generar PDF completo: {str(pdf_error)}")
            datos_completos['pdf_error'] = str(pdf_error)
        
        return render_template('resultados_salida.html', datos=datos_completos)
        
    except Exception as e:
        logger.error(f"Error al mostrar resultados de salida: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

# Función deshabilitada - El usuario prefiere impresión directa desde el navegador
# 

