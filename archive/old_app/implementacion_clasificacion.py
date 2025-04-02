"""
Implementación para resolver el problema de visualización en la plantilla de clasificación.
Este archivo contiene código a implementar en apptiquetes.py.
"""

import os
import json
import logging
import traceback
from flask import render_template, jsonify, redirect, url_for, session, flash, current_app as app

logger = logging.getLogger(__name__)

# 1. Ruta de diagnóstico para verificar los datos disponibles en una guía
@app.route('/api/debug/datos-guia/<codigo>')
def debug_datos_guia(codigo):
    """
    Endpoint API para depuración que muestra los datos disponibles para una guía.
    Útil para verificar que campos están disponibles y qué valores contienen.
    """
    try:
        # Obtener el código guía completo
        codigo_base = codigo.split('_')[0] if '_' in codigo else codigo
        guias_folder = app.config['GUIAS_FOLDER']
        guias_files = glob.glob(os.path.join(guias_folder, f'guia_{codigo_base}_*.html'))
        
        if guias_files:
            guias_files.sort(key=os.path.getmtime, reverse=True)
            latest_guia = os.path.basename(guias_files[0])
            codigo_guia_completo = latest_guia[5:-5]  # Remover 'guia_' y '.html'
        else:
            codigo_guia_completo = codigo
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            return jsonify({
                "error": "Guía no encontrada",
                "codigo_solicitado": codigo,
                "codigo_guia_completo": codigo_guia_completo
            }), 404
        
        # Preparar datos de diagnóstico
        diagnostico = {
            "codigo_solicitado": codigo,
            "codigo_guia_completo": codigo_guia_completo,
            "campos_disponibles": list(datos_guia.keys()),
            "datos_proveedor": {
                "nombre": datos_guia.get('nombre'),
                "nombre_proveedor": datos_guia.get('nombre_proveedor'),
                "nombre_agricultor": datos_guia.get('nombre_agricultor'),
                "nombre_resultante": datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible')
            },
            "datos_racimos": {
                "cantidad_racimos": datos_guia.get('cantidad_racimos'),
                "racimos": datos_guia.get('racimos'),
                "cantidad_resultante": datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible')
            },
            "datos_peso": {
                "peso_bruto": datos_guia.get('peso_bruto'),
                "tipo_pesaje": datos_guia.get('tipo_pesaje'),
                "estado_actual": datos_guia.get('estado_actual')
            },
            # Campos generales importantes
            "codigo": datos_guia.get('codigo'),
            "codigo_proveedor": datos_guia.get('codigo_proveedor'),
            "fecha_registro": datos_guia.get('fecha_registro'),
            "placa": datos_guia.get('placa')
        }
        
        # Obtener ruta al archivo JSON
        json_path = os.path.join(guias_folder, f'guia_{codigo_guia_completo}.json')
        diagnostico["archivo_json_existe"] = os.path.exists(json_path)
        
        # Retornar datos completos para diagnóstico
        return jsonify(diagnostico)
        
    except Exception as e:
        logger.error(f"Error en debug_datos_guia: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            "error": "Error al obtener datos de guía",
            "mensaje": str(e),
            "traceback": traceback.format_exc()
        }), 500


# 2. Modificación de la función de clasificación para solucionar el problema
@app.route('/clasificacion/<codigo>', methods=['GET'])
def clasificacion(codigo):
    """
    Maneja la vista de clasificación y el procesamiento de la misma.
    Versión actualizada con mejor manejo de datos para la plantilla.
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

        # Verificar si ya existe archivo de clasificación para este código
        clasificaciones_dir = os.path.join(app.static_folder, 'clasificaciones')
        archivo_clasificacion_exacto = os.path.join(clasificaciones_dir, f"clasificacion_{codigo_guia_completo}.json")
        
        if os.path.exists(archivo_clasificacion_exacto):
            logger.info(f"Se encontró un archivo de clasificación exacto para la guía actual: {codigo_guia_completo}")
            # Redirigir a la página de resultados de clasificación si ya existe para esta guía específica
            return redirect(url_for('ver_resultados_clasificacion', url_guia=codigo_guia_completo))

        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia_completo)
        if not datos_guia:
            logger.error(f"No se encontraron datos para la guía: {codigo_guia_completo}")
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

        # Obtener datos de la guía usando el código completo (se repite para asegurar datos completos)
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
            return redirect(url_for('clasificacion', codigo=codigo_guia_completo))

        # Logs para depuración de datos que se van a renderizar
        logger.info("=" * 50)
        logger.info(f"DATOS PARA RENDERIZAR CLASIFICACIÓN GUÍA: {codigo_guia_completo}")
        logger.info(f"Campos disponibles en datos_guia: {list(datos_guia.keys())}")
        logger.info(f"Nombre proveedor: {datos_guia.get('nombre_proveedor')}")
        logger.info(f"Nombre (alternativo): {datos_guia.get('nombre')}")
        logger.info(f"Nombre agricultor: {datos_guia.get('nombre_agricultor')}")
        logger.info(f"Cantidad racimos: {datos_guia.get('cantidad_racimos')}")
        logger.info(f"Racimos (alternativo): {datos_guia.get('racimos')}")
        logger.info("=" * 50)

        # Renderizar template de clasificación con nombres de variables explícitos
        # Se mantienen los nombres originales para compatibilidad pero se agregan nuevos nombres más explícitos
        return render_template('clasificacion.html', 
                            # Variables originales
                            codigo=datos_guia.get('codigo'),
                            codigo_guia=codigo_guia_completo,
                            nombre=datos_guia.get('nombre') or datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                            
                            # Variables adicionales con nombres explícitos
                            nombre_proveedor=datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            codigo_proveedor=datos_guia.get('codigo_proveedor') or datos_guia.get('codigo', 'No disponible'),
                            
                            # Variables originales restantes
                            peso_bruto=datos_guia.get('peso_bruto'),
                            tipo_pesaje=datos_guia.get('tipo_pesaje'),
                            fecha_registro=datos_guia.get('fecha_registro'),
                            hora_registro=datos_guia.get('hora_registro'),
                            fecha_pesaje=datos_guia.get('fecha_pesaje'),
                            hora_pesaje=datos_guia.get('hora_pesaje'),
                            transportador=datos_guia.get('transportador'),
                            placa=datos_guia.get('placa'),
                            guia_transporte=datos_guia.get('guia_transito'),
                            codigo_guia_transporte_sap=datos_guia.get('codigo_guia_transporte_sap'),
                            
                            # Flag de depuración
                            debug=app.config.get('DEBUG', False))
                           
    except Exception as e:
        logger.error(f"Error en clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando clasificación"), 500 