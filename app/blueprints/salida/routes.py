from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import logging
import traceback
from datetime import datetime
import json
import sqlite3
from app.blueprints.salida import bp
from app.utils.common import CommonUtils as Utils
from flask_login import login_required

# Configurar logging
logger = logging.getLogger(__name__)

def ensure_salidas_schema():
    """
    Asegura que la tabla salidas tenga todas las columnas necesarias.
    """
    conn = None  # Inicializar conn fuera del try para asegurar que exista en el finally
    try:
        # --- CORRECCIÓN: Usar la ruta de la configuración de la app ---
        db_path = current_app.config['TIQUETES_DB_PATH'] 
        logger.info(f"[ensure_salidas_schema] Usando DB path: {db_path}") # Añadir log para confirmar ruta
        # --- FIN CORRECCIÓN ---
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(salidas)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Añadir columnas faltantes
        columns_to_add = []
        
        if 'comentarios_salida' not in columns:
            columns_to_add.append("comentarios_salida TEXT")
            
        if 'firma_salida' not in columns:
            columns_to_add.append("firma_salida TEXT")
            
        # Ejecutar alters para añadir columnas faltantes
        for column_def in columns_to_add:
            column_name = column_def.split()[0]
            logger.info(f"Añadiendo columna {column_name} a la tabla salidas")
            try:
                cursor.execute(f"ALTER TABLE salidas ADD COLUMN {column_def}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.warning(f"La columna {column_name} ya existe en la tabla")
                else:
                    raise
                    
        conn.commit()
        logger.info("Esquema de la tabla salidas verificado/actualizado")
        return True  # Devolver True al final si todo fue bien
    except KeyError:
        logger.error("[ensure_salidas_schema] Error: 'TIQUETES_DB_PATH' no está configurada.")
        return False # Indicar fallo
    except sqlite3.Error as e: # Capturar errores de SQLite más genéricos también
        logger.error(f"Error SQLite en ensure_salidas_schema: {str(e)}")
        logger.error(traceback.format_exc()) # Loguear el traceback completo
        return False # Indicar fallo
    except Exception as e:
        logger.error(f"Error general verificando/actualizando esquema de salidas: {str(e)}")
        logger.error(traceback.format_exc()) # Loguear el traceback completo
        return False # Indicar fallo
    finally:
        if conn: # Asegurar que conn se cierre si se abrió
            conn.close()

@bp.route('/registro_salida/<codigo_guia>')
@login_required
def registro_salida(codigo_guia):
    """
    Muestra la vista de registro de salida para una guía específica.
    Esta es la etapa final del proceso después del pesaje neto.
    """
    try:
        # Verificar y actualizar el esquema de la tabla salidas
        ensure_salidas_schema()
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("Guía no encontrada", "error")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar que el pesaje neto esté completado
        if not datos_guia.get('peso_neto'):
            flash("El pesaje neto no ha sido registrado para esta guía.", "warning")
            return redirect(url_for('pesaje_neto.pesaje_neto', codigo_guia=codigo_guia))
            
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
        return render_template('error.html', message=f"Error al mostrar registro de salida: {str(e)}")

@bp.route('/completar_registro_salida', methods=['POST'])
@login_required
def completar_registro_salida():
    """
    Procesa el formulario de registro de salida y completa el proceso.
    """
    conn = None  # Inicializar conn fuera del try
    try:
        # Verificar y actualizar el esquema de la tabla salidas
        ensure_salidas_schema()
        
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Determinar si los datos vienen como JSON o como formulario
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form
        
        # Obtener datos del formulario
        codigo_guia = data.get('codigo_guia')
        fecha_salida = data.get('fecha_salida')
        hora_salida = data.get('hora_salida')
        comentarios = data.get('comentarios', '')
        
        logger.info(f"Procesando registro de salida para guía {codigo_guia}. Datos: {data}")
        
        if not codigo_guia:
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Falta el código de guía'
                }), 400
            else:
                flash("Falta el código de guía", "error")
                return redirect(url_for('misc.index'))
            
        # Obtener datos actuales de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Guía no encontrada'
                }), 404
            else:
                flash("Guía no encontrada", "error")
                return redirect(url_for('misc.index'))
        
        # Convertir fecha y hora a UTC y formatear
        fecha_hora_actual_utc = datetime.utcnow()
        timestamp_utc = fecha_hora_actual_utc.strftime('%Y-%m-%d %H:%M:%S')
        
        # Actualizar datos de la guía
        datos_actualizados = {
            'timestamp_salida_utc': timestamp_utc,
            'comentarios_salida': comentarios,
            'estado_actual': 'proceso_completado',
            'estado_salida': 'Completado',
            'estado_final': 'completado'
        }
        
        # Guardar los datos actualizados en la guía
        if utils.update_datos_guia(codigo_guia, datos_actualizados):
            logger.info(f"Registro de salida completado para guía {codigo_guia}")
            
            # Registrar en la tabla de salidas
            try:
                # --- CORRECCIÓN: Usar la ruta de la configuración ---
                db_path = current_app.config['TIQUETES_DB_PATH']
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                
                # Verificar si ya existe un registro para este código de guía
                cursor.execute("SELECT id FROM salidas WHERE codigo_guia = ?", (codigo_guia,))
                existing = cursor.fetchone()
                
                if existing:
                    # Actualizar registro existente
                    cursor.execute("""
                        UPDATE salidas
                        SET timestamp_salida_utc = ?, comentarios_salida = ?, estado = ?
                        WHERE codigo_guia = ?
                    """, (
                        timestamp_utc,
                        comentarios,
                        'completado',
                        codigo_guia
                    ))
                else:
                    # Insertar nuevo registro
                    cursor.execute("""
                        INSERT INTO salidas (codigo_guia, codigo_proveedor, nombre_proveedor, timestamp_salida_utc, comentarios_salida)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        codigo_guia,
                        datos_guia.get('codigo_proveedor', ''),
                        datos_guia.get('nombre_proveedor', ''),
                        timestamp_utc,
                        comentarios
                    ))
                
                conn.commit()
                logger.info(f"Datos de salida guardados en la tabla salidas para guía {codigo_guia}")
                
                # Forzar una actualización completa de los datos de guía
                try:
                    datos_actualizados_completos = utils.get_datos_guia(codigo_guia, force_reload=True)
                    if datos_actualizados_completos:
                        datos_actualizados_completos.update({
                            'timestamp_salida_utc': timestamp_utc,
                            'comentarios_salida': comentarios,
                            'estado_actual': 'proceso_completado',
                            'estado_salida': 'Completado',
                            'estado_final': 'completado'
                        })
                        utils.update_datos_guia(codigo_guia, datos_actualizados_completos)
                        logger.info(f"Datos de guía sincronizados completamente para {codigo_guia}")
                except Exception as sync_error:
                    logger.error(f"Error al sincronizar datos de guía: {str(sync_error)}")
                    logger.error(traceback.format_exc())
            except Exception as db_error:
                logger.error(f"Error al guardar en la tabla salidas: {str(db_error)}")
                logger.error(traceback.format_exc())
                raise  # Re-lanzar el error para manejarlo en el catch exterior
            finally:
                if conn:
                    conn.close()
            
            # Responder según el tipo de solicitud
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Registro de salida completado exitosamente',
                    'redirect_url': url_for('salida.ver_resultados_salida', codigo_guia=codigo_guia)
                })
            else:
                flash("Registro de salida completado exitosamente", "success")
                return redirect(url_for('salida.ver_resultados_salida', codigo_guia=codigo_guia))
        else:
            logger.error(f"Error al actualizar datos para registro de salida de guía {codigo_guia}")
            if request.is_json:
                return jsonify({
                    'success': False,
                    'message': 'Error al guardar los datos de salida'
                }), 500
            else:
                flash("Error al guardar los datos de salida", "error")
                return redirect(url_for('salida.registro_salida', codigo_guia=codigo_guia))
            
    except Exception as e:
        logger.error(f"Error al completar registro de salida: {str(e)}")
        logger.error(traceback.format_exc())
        if request.is_json:
            return jsonify({
                'success': False,
                'message': f'Error al completar registro de salida: {str(e)}'
            }), 500
        else:
            flash(f"Error al completar registro de salida: {str(e)}", "error")
            return redirect(url_for('misc.index'))
    finally:
        if conn:
            conn.close()

@bp.route('/ver_resultados_salida/<codigo_guia>')
@login_required
def ver_resultados_salida(codigo_guia):
    """
    Muestra los resultados del registro de salida para una guía específica.
    """
    conn = None
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = Utils(current_app)
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("Guía no encontrada", "error")
            return render_template('error.html', message="Guía no encontrada"), 404
            
        # Verificar si la salida ha sido registrada en la tabla salidas
        try:
            # --- CORRECCIÓN: Usar la ruta de la configuración ---
            db_path = current_app.config['TIQUETES_DB_PATH']
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT timestamp_salida_utc, comentarios_salida FROM salidas WHERE codigo_guia = ?", (codigo_guia,))
            salida_data = cursor.fetchone()
            
            if salida_data:
                datos_guia['timestamp_salida_utc'] = salida_data[0]
                datos_guia['comentarios_salida'] = salida_data[1]
                logger.info(f"Datos de salida encontrados en la tabla para {codigo_guia}: {salida_data}")
            else:
                if not datos_guia.get('timestamp_salida_utc'):
                    flash("El registro de salida no ha sido completado para esta guía.", "warning")
                    return redirect(url_for('salida.registro_salida', codigo_guia=codigo_guia))
        except Exception as db_error:
            logger.error(f"Error al verificar datos de salida en la base de datos: {str(db_error)}")
            logger.error(traceback.format_exc())
            if not datos_guia.get('timestamp_salida_utc'):
                flash("El registro de salida no ha sido completado para esta guía.", "warning")
                return redirect(url_for('salida.registro_salida', codigo_guia=codigo_guia))
        finally:
            if conn:
                conn.close()
        
        # Generar QR para la guía si no existe
        qr_filename = f'qr_guia_{codigo_guia}.png'
        qr_path = os.path.join(current_app.static_folder, 'qr', qr_filename)
        
        if not os.path.exists(qr_path):
            qr_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia, _external=True)
            utils.generar_qr(qr_url, qr_path)
            
        # Preparar los datos para la plantilla
        context = {
            'datos': datos_guia,
            'qr_code_url': url_for('static', filename=f'qr/{qr_filename}'),
            'proceso_completado': True
        }
        
        return render_template('resultados_salida.html', **context)
        
    except Exception as e:
        logger.error(f"Error al mostrar resultados de salida: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

# Función deshabilitada - El usuario prefiere impresión directa desde el navegador
# 

@bp.route('/debug_logs')
@login_required
def debug_logs():
    """
    Ruta de debug para verificar logs recientes.
    """
    import sys
    import traceback
    
    # Obtener los últimos errores registrados
    last_errors = []
    try:
        # Crear un resumen de la información de depuración
        debug_info = {
            "recent_errors": last_errors,
            "session_data": {k: v for k, v in session.items() if k != '_flashes'},
            "request_headers": dict(request.headers),
            "routes": [str(rule) for rule in current_app.url_map.iter_rules()]
        }
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        })

