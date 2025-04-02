#!/usr/bin/env python3
import os
import shutil
import sys

def fix_guardar_clasificacion():
    """Función para corregir el error de sintaxis en guardar_clasificacion_final"""
    
    file_path = 'app/blueprints/clasificacion/routes.py'
    backup_path = f"{file_path}.bak3"
    
    # Hacer una copia de seguridad
    shutil.copy2(file_path, backup_path)
    print(f"Copia de seguridad creada en: {backup_path}")
    
    # Reemplazar completamente la función problemática con una versión correcta
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Encontrar el inicio de la función 'guardar_clasificacion_final'
    start_line = -1
    for i, line in enumerate(lines):
        if "@bp.route('/guardar_clasificacion_final/" in line:
            start_line = i
            break
    
    if start_line == -1:
        print("No se encontró la función guardar_clasificacion_final. Abortando.")
        return False
    
    # Reemplazar la función completa con una versión conocida que funciona
    # Esta es una implementación simplificada que mantiene la funcionalidad principal
    nueva_funcion = """@bp.route('/guardar_clasificacion_final/<path:codigo_guia>', methods=['POST'])
def guardar_clasificacion_final(codigo_guia):
    """
    Guarda la clasificación final en la base de datos y actualiza el estado de la guía.
    """
    try:
        # Obtener datos de la guía
        datos_guia = utils.get_datos_guia(codigo_guia)
        if not datos_guia:
            flash("No se encontró la guía especificada", "danger")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))
        
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
        
        # Log exactamente qué URL estamos generando para la redirección
        redirect_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia)
        logger.info(f"Redirigiendo a guía centralizada con URL: {redirect_url}")
        
        return redirect(redirect_url)
    
    except Exception as e:
        logger.error(f"Error en guardar_clasificacion_final: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al guardar la clasificación: {str(e)}", "danger")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))
"""
    
    # Encontrar el final de la función
    end_line = -1
    for i in range(start_line, len(lines)):
        if i+1 < len(lines) and "@bp.route" in lines[i+1]:
            end_line = i
            break
    
    if end_line == -1:
        end_line = len(lines) - 1
    
    # Reemplazar la función
    new_lines = lines[:start_line] + [nueva_funcion] + lines[end_line+1:]
    
    # Guardar el archivo modificado
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Función guardar_clasificacion_final reemplazada con éxito en {file_path}")
    return True

if __name__ == "__main__":
    fix_guardar_clasificacion() 