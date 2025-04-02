from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.pesaje_neto import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/ver_resultados_pesaje_neto/<codigo_guia>')
def ver_resultados_pesaje_neto(codigo_guia):
    """
    Muestra los resultados del pesaje neto para una guía específica.
    """
    try:
        codigo = codigo_guia
        
        # Verificar si hay datos en la sesión
        peso_neto_session = session.get('peso_neto')
        peso_producto_session = session.get('peso_producto')
        fotos_pesaje_neto_session = session.get('fotos_pesaje_neto', [])
        
        logger.info(f"Datos de sesión: peso_neto={peso_neto_session}, peso_producto={peso_producto_session}")
        
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
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Si la URL no tiene el código guía completo, redirigir a la URL correcta
        if codigo != codigo_guia_completo:
            return redirect(url_for('pesaje_neto.ver_resultados_pesaje_neto', codigo_guia=codigo_guia_completo))

        # Verificar que el pesaje neto esté registrado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto', codigo=codigo_guia_completo))

        # Generar QR para la guía si no existe
        qr_filename = f'qr_pesaje_neto_{codigo_guia}.png'
        qr_path = os.path.join(app.config['QR_FOLDER'], qr_filename)
        
        if not os.path.exists(qr_path):
            qr_data = url_for('pesaje_neto.ver_resultados_pesaje_neto', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_data, qr_path)
        
        # Preparar datos para la plantilla
        imagen_bascula_neto = datos_guia.get('foto_bascula_neto')
        qr_code = url_for('static', filename=f'qr/{qr_filename}')
        
        # Obtener información de verificación de placa si existe
        verificacion_placa = datos_guia.get('verificacion_placa')
        
        # Asegurarse de que verificacion_placa sea un diccionario o iniciarlo vacío
        if verificacion_placa is None:
            verificacion_placa = {}
        
        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia_completo,
            'datos_guia': datos_guia,
            'tipo_pesaje_neto': datos_guia.get('tipo_pesaje_neto', 'N/A'),
            'peso_bruto': datos_guia.get('peso_bruto', 'N/A'),
            'peso_neto': datos_guia.get('peso_neto', 'N/A'),
            'peso_producto': datos_guia.get('peso_producto', 'N/A'),
            'fecha_pesaje_neto': datos_guia.get('fecha_pesaje_neto', 'N/A'),
            'hora_pesaje_neto': datos_guia.get('hora_pesaje_neto', 'N/A'),
            'comentarios_neto': datos_guia.get('comentarios_neto', ''),
            'fotos_pesaje_neto': datos_guia.get('fotos_pesaje_neto', []),
            'foto_bascula_neto': imagen_bascula_neto,
            'codigo_proveedor': datos_guia.get('codigo_proveedor', 'No disponible'),
            'nombre_proveedor': datos_guia.get('nombre_agricultor', 'No disponible'),
            'transportador': datos_guia.get('transportador', 'No disponible'),
            'placa': datos_guia.get('placa', 'No disponible'),
            'racimos': datos_guia.get('racimos', 'No disponible'),
            'qr_code': qr_code,
            'verificacion_placa': verificacion_placa
        }
        
        return render_template('resultados_pesaje_neto.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")



