from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response, current_app
import os
import logging
import traceback
from datetime import datetime
import json
import glob
import sqlite3
from app.blueprints.pesaje_neto import bp
from app.utils.common import CommonUtils as Utils

# Configurar logging
logger = logging.getLogger(__name__)

def ensure_pesajes_neto_schema():
    """
    Asegura que la tabla pesajes_neto tenga todas las columnas necesarias.
    """
    try:
        db_path = 'tiquetes.db'
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verificar columnas existentes
        cursor.execute("PRAGMA table_info(pesajes_neto)")
        columns = {col[1] for col in cursor.fetchall()}
        
        # Añadir columnas faltantes
        columns_to_add = []
        
        if 'peso_producto' not in columns:
            columns_to_add.append("peso_producto REAL")
            
        if 'comentarios' not in columns:
            columns_to_add.append("comentarios TEXT")
            
        if 'tipo_pesaje_neto' not in columns:
            columns_to_add.append("tipo_pesaje_neto TEXT")
            
        if 'respuesta_sap' not in columns:
            columns_to_add.append("respuesta_sap TEXT")
            
        # Ejecutar alters para añadir columnas faltantes
        for column_def in columns_to_add:
            column_name = column_def.split()[0]
            logger.info(f"Añadiendo columna {column_name} a la tabla pesajes_neto")
            try:
                cursor.execute(f"ALTER TABLE pesajes_neto ADD COLUMN {column_def}")
                conn.commit()
                logger.info(f"Columna {column_name} añadida exitosamente")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e):
                    logger.warning(f"La columna {column_name} ya existe en la tabla")
                else:
                    raise
                    
        conn.commit()
        logger.info("Esquema de la tabla pesajes_neto verificado/actualizado")
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error verificando/actualizando esquema de pesajes_neto: {str(e)}")
        if 'conn' in locals():
            conn.close()
        return False

@bp.route('/ver_resultados_pesaje_neto/<codigo_guia>')
def ver_resultados_pesaje_neto(codigo_guia):
    """
    Muestra los resultados del pesaje neto para una guía específica.
    """
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            return render_template('error.html', message="Guía no encontrada"), 404

        # Obtener los datos más recientes de la base de datos
        try:
            conn = sqlite3.connect('tiquetes.db')
            cursor = conn.cursor()
            cursor.execute("""
                SELECT peso_tara, peso_neto, fecha_pesaje, hora_pesaje, comentarios, respuesta_sap
                FROM pesajes_neto 
                WHERE codigo_guia = ?
            """, (codigo_guia,))
            result = cursor.fetchone()
            
            if result:
                peso_tara, peso_neto, fecha_pesaje, hora_pesaje, comentarios, respuesta_sap = result
                # Actualizar los datos con los valores más recientes
                datos_guia.update({
                    'peso_tara': peso_tara,
                    'peso_neto': peso_neto,
                    'fecha_pesaje_neto': fecha_pesaje,
                    'hora_pesaje_neto': hora_pesaje,
                    'comentarios_neto': comentarios,
                    'respuesta_sap': respuesta_sap
                })
                logger.info(f"Datos actualizados desde la base de datos: peso_tara={peso_tara}, peso_neto={peso_neto}")
        except Exception as e:
            logger.error(f"Error recuperando datos de la base de datos: {str(e)}")
        finally:
            if 'conn' in locals():
                conn.close()

        # Preparar los datos para la plantilla
        context = {
            'codigo_guia': codigo_guia,
            'datos_guia': datos_guia
        }
        
        return render_template('resultados_pesaje_neto.html', **context)
    except Exception as e:
        logger.error(f"Error al mostrar resultados de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar resultados: {str(e)}", "error")
        return render_template('error.html', message=f"Error al mostrar resultados: {str(e)}")

@bp.route('/registrar_peso_neto_directo', methods=['POST'])
def registrar_peso_neto_directo():
    """Registra el peso neto para una guía específica usando el método directo."""
    
    # Asegurar que la tabla pesajes_neto tenga todas las columnas necesarias
    ensure_pesajes_neto_schema()
    
    # Inicializar variables
    error_message = None
    data_received = {}
    
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        logger.info("Procesando solicitud de registro de peso neto directo")
        
        # Obtener datos del formulario
        codigo_guia = request.form.get('codigo_guia')
        peso_tara = request.form.get('peso_tara')
        peso_neto = request.form.get('peso_neto')
        comentarios = request.form.get('comentarios', '')
        respuesta_sap = request.form.get('respuesta_sap')
        
        data_received = {k: v for k, v in request.form.items()}
        logger.info(f"Datos recibidos para pesaje neto directo: {data_received}")
        
        # Validar datos requeridos
        if not codigo_guia:
            error_message = "El código de guía es obligatorio"
            raise ValueError(error_message)
        
        if not peso_tara or not peso_neto:
            error_message = "El peso tara y peso neto son obligatorios"
            raise ValueError(error_message)
        
        # Convertir pesos a float para asegurar precisión
        try:
            peso_tara = float(peso_tara)
            peso_neto = float(peso_neto)
        except ValueError:
            error_message = "Los valores de peso deben ser numéricos"
            raise ValueError(error_message)
            
        now = datetime.now()
        
        # Obtener datos originales de la guía
        datos_originales = utils.get_datos_guia(codigo_guia)
        if not datos_originales:
            error_message = "No se encontraron los datos originales de la guía"
            raise ValueError(error_message)
        
        # Actualizar directamente en la base de datos
        try:
            conn = sqlite3.connect('tiquetes.db')
            cursor = conn.cursor()
            
            # Primero verificar si existe el registro
            cursor.execute("SELECT 1 FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia,))
            exists = cursor.fetchone() is not None
            
            if exists:
                # Actualizar registro existente
                cursor.execute("""
                    UPDATE pesajes_neto 
                    SET peso_tara = ?,
                        peso_neto = ?,
                        fecha_pesaje = ?,
                        hora_pesaje = ?,
                        tipo_pesaje_neto = ?,
                        comentarios = ?,
                        respuesta_sap = ?
                    WHERE codigo_guia = ?
                """, (
                    peso_tara,
                    peso_neto,
                    now.strftime('%d/%m/%Y'),
                    now.strftime('%H:%M:%S'),
                    'directo',
                    comentarios,
                    respuesta_sap,
                    codigo_guia
                ))
            else:
                # Insertar nuevo registro
                cursor.execute("""
                    INSERT INTO pesajes_neto (
                        codigo_guia, peso_tara, peso_neto, fecha_pesaje, 
                        hora_pesaje, tipo_pesaje_neto, comentarios, respuesta_sap
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    codigo_guia,
                    peso_tara,
                    peso_neto,
                    now.strftime('%d/%m/%Y'),
                    now.strftime('%H:%M:%S'),
                    'directo',
                    comentarios,
                    respuesta_sap
                ))
            
            conn.commit()
            logger.info(f"Datos actualizados en la base de datos para guía {codigo_guia}")
            
        except Exception as e:
            logger.error(f"Error actualizando la base de datos: {str(e)}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
        
        # Actualizar solo los datos del pesaje en la UI, manteniendo los datos originales del proveedor
        datos_ui = {
            'peso_tara': peso_tara,
            'peso_neto': peso_neto,
            'tipo_pesaje_neto': 'directo',
            'fecha_pesaje_neto': now.strftime('%d/%m/%Y'),
            'hora_pesaje_neto': now.strftime('%H:%M:%S'),
            'comentarios_neto': comentarios,
            'respuesta_sap': respuesta_sap,
            'pesaje_neto_completado': True
        }
        
        # Mantener los datos originales del proveedor
        datos_ui.update({
            'codigo_proveedor': datos_originales.get('codigo_proveedor', datos_originales.get('codigo')),
            'nombre_proveedor': datos_originales.get('nombre_proveedor', datos_originales.get('nombre')),
            'transportador': datos_originales.get('transportador'),
            'placa': datos_originales.get('placa'),
            'codigo_guia_transporte_sap': datos_originales.get('codigo_guia_transporte_sap')
        })
        
        # Guardar los datos actualizados
        if utils.update_datos_guia(codigo_guia, datos_ui):
            logger.info(f"Pesaje neto directo guardado correctamente para guía {codigo_guia}")
            
            return jsonify({
                'success': True,
                'message': 'Pesaje neto registrado correctamente',
                'redirect_url': url_for('pesaje_neto.ver_resultados_pesaje_neto', codigo_guia=codigo_guia)
            })
        else:
            logger.error(f"Error al guardar pesaje neto directo para {codigo_guia}")
            error_message = "No se pudo guardar el pesaje neto"
            raise Exception(error_message)
            
    except Exception as e:
        logger.error(f"Error al registrar peso neto directo: {str(e)}")
        logger.error(f"Datos recibidos: {data_received}")
        logger.error(traceback.format_exc())
        
        if not error_message:
            error_message = f"Error al registrar peso neto directo: {str(e)}"
        
        return jsonify({
            'success': False,
            'message': error_message
        }), 400

@bp.route('/pesaje/<codigo_guia>')
def pesaje_neto(codigo_guia):
    """Muestra el formulario de pesaje neto."""
    try:
        # Inicializar Utils dentro del contexto de la aplicación
        utils = current_app.config.get('utils', Utils(current_app))
        
        # Obtener datos originales de la guía
        datos = utils.get_datos_guia(codigo_guia)
        if not datos:
            flash("No se encontró la guía especificada", "error")
            return redirect(url_for('misc.upload_file'))
            
        logger.info(f"Datos recuperados para pesaje neto: {datos}")
        
        return render_template('pesaje/pesaje_neto.html', datos=datos)
        
    except Exception as e:
        logger.error(f"Error al mostrar formulario de pesaje neto: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al mostrar formulario: {str(e)}", "error")
        return redirect(url_for('misc.upload_file'))



