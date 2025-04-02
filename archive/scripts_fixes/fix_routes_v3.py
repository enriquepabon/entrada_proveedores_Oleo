#!/usr/bin/env python3
import os
import shutil

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
    nueva_funcion = [
        "@bp.route('/guardar_clasificacion_final/<path:codigo_guia>', methods=['POST'])\n",
        "def guardar_clasificacion_final(codigo_guia):\n",
        "    \"\"\"\n",
        "    Guarda la clasificación final en la base de datos y actualiza el estado de la guía.\n",
        "    \"\"\"\n",
        "    try:\n",
        "        # Obtener datos de la guía\n",
        "        datos_guia = utils.get_datos_guia(codigo_guia)\n",
        "        if not datos_guia:\n",
        "            flash(\"No se encontró la guía especificada\", \"danger\")\n",
        "            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))\n",
        "        \n",
        "        # Actualizar el estado de clasificación en ambas bases de datos\n",
        "        dbs = ['database.db', 'tiquetes.db']\n",
        "        actualizado = False\n",
        "        \n",
        "        for db_path in dbs:\n",
        "            try:\n",
        "                import sqlite3\n",
        "                conn = sqlite3.connect(db_path)\n",
        "                cursor = conn.cursor()\n",
        "                \n",
        "                # Verificar si la tabla pesajes_bruto existe\n",
        "                cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='pesajes_bruto'\")\n",
        "                if not cursor.fetchone():\n",
        "                    logger.warning(f\"Tabla pesajes_bruto no encontrada en {db_path}\")\n",
        "                    continue\n",
        "                \n",
        "                # Verificar si existe el registro\n",
        "                cursor.execute(\"SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia = ?\", (codigo_guia,))\n",
        "                if not cursor.fetchone():\n",
        "                    logger.warning(f\"No se encontró registro para {codigo_guia} en {db_path}\")\n",
        "                    continue\n",
        "                \n",
        "                # Actualizar estado de clasificación\n",
        "                update_query = \"\"\"\n",
        "                UPDATE pesajes_bruto \n",
        "                SET estado_clasificacion = 'completado', \n",
        "                    clasificacion_completada = 1,\n",
        "                    estado_actual = 'clasificacion_completada'\n",
        "                WHERE codigo_guia = ?\n",
        "                \"\"\"\n",
        "                cursor.execute(update_query, (codigo_guia,))\n",
        "                conn.commit()\n",
        "                \n",
        "                logger.info(f\"Estado de clasificación actualizado para {codigo_guia} en {db_path}\")\n",
        "                actualizado = True\n",
        "                \n",
        "                conn.close()\n",
        "            except Exception as e:\n",
        "                logger.error(f\"Error actualizando en {db_path}: {str(e)}\")\n",
        "                if 'conn' in locals():\n",
        "                    conn.close()\n",
        "        \n",
        "        # Actualizar directamente usando la función existente\n",
        "        try:\n",
        "            import db_utils\n",
        "            datos_update = {\n",
        "                'estado_clasificacion': 'completado',\n",
        "                'clasificacion_completada': True,\n",
        "                'estado_actual': 'clasificacion_completada'\n",
        "            }\n",
        "            db_utils.update_pesaje_bruto(codigo_guia, datos_update)\n",
        "            logger.info(f\"Pesaje bruto actualizado con db_utils para {codigo_guia}\")\n",
        "        except Exception as e:\n",
        "            logger.error(f\"Error actualizando con db_utils: {str(e)}\")\n",
        "        \n",
        "        # También intentar actualizar usando utils del app\n",
        "        try:\n",
        "            from app.utils.db_operations import update_pesaje_bruto\n",
        "            datos_update = {\n",
        "                'estado_clasificacion': 'completado',\n",
        "                'clasificacion_completada': True,\n",
        "                'estado_actual': 'clasificacion_completada'\n",
        "            }\n",
        "            update_pesaje_bruto(codigo_guia, datos_update)\n",
        "            logger.info(f\"Pesaje bruto actualizado con app.utils.db_operations para {codigo_guia}\")\n",
        "        except Exception as e:\n",
        "            logger.error(f\"Error actualizando con app.utils.db_operations: {str(e)}\")\n",
        "        \n",
        "        # Actualizar archivo JSON si existe\n",
        "        try:\n",
        "            import json\n",
        "            import os\n",
        "            from flask import current_app\n",
        "            \n",
        "            # Directorio donde se almacenan los archivos JSON de las guías\n",
        "            guias_folder = current_app.config.get('GUIAS_FOLDER')\n",
        "            json_path = os.path.join(guias_folder, f'guia_{codigo_guia}.json')\n",
        "            \n",
        "            if os.path.exists(json_path):\n",
        "                with open(json_path, 'r') as f:\n",
        "                    datos_json = json.load(f)\n",
        "                \n",
        "                # Actualizar datos JSON con la información de clasificación\n",
        "                datos_json['clasificacion_completada'] = True\n",
        "                datos_json['estado_actual'] = 'clasificacion_completada'\n",
        "                datos_json['fecha_clasificacion'] = datos_guia.get('fecha_clasificacion')\n",
        "                datos_json['hora_clasificacion'] = datos_guia.get('hora_clasificacion')\n",
        "                datos_json['estado_clasificacion'] = 'completado'\n",
        "                \n",
        "                if 'pasos_completados' not in datos_json:\n",
        "                    datos_json['pasos_completados'] = ['entrada', 'pesaje', 'clasificacion']\n",
        "                elif 'clasificacion' not in datos_json['pasos_completados']:\n",
        "                    datos_json['pasos_completados'].append('clasificacion')\n",
        "                \n",
        "                # Guardar los cambios en el archivo JSON\n",
        "                with open(json_path, 'w') as f:\n",
        "                    json.dump(datos_json, f, indent=4)\n",
        "                \n",
        "                logger.info(f\"Archivo JSON actualizado para {codigo_guia}\")\n",
        "        except Exception as e:\n",
        "            logger.error(f\"Error actualizando archivo JSON: {str(e)}\")\n",
        "        \n",
        "        flash(\"Clasificación guardada correctamente\", \"success\")\n",
        "        \n",
        "        # Log exactamente qué URL estamos generando para la redirección\n",
        "        redirect_url = url_for('misc.ver_guia_centralizada', codigo_guia=codigo_guia)\n",
        "        logger.info(f\"Redirigiendo a guía centralizada con URL: {redirect_url}\")\n",
        "        \n",
        "        return redirect(redirect_url)\n",
        "    \n",
        "    except Exception as e:\n",
        "        logger.error(f\"Error en guardar_clasificacion_final: {str(e)}\")\n",
        "        logger.error(traceback.format_exc())\n",
        "        flash(f\"Error al guardar la clasificación: {str(e)}\", \"danger\")\n",
        "        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=codigo_guia))\n"
    ]
    
    # Encontrar el final de la función
    end_line = -1
    for i in range(start_line, len(lines)):
        if i+1 < len(lines) and "@bp.route" in lines[i+1]:
            end_line = i
            break
    
    if end_line == -1:
        end_line = len(lines) - 1
    
    # Reemplazar la función
    new_lines = lines[:start_line] + nueva_funcion + lines[end_line+1:]
    
    # Guardar el archivo modificado
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    print(f"Función guardar_clasificacion_final reemplazada con éxito en {file_path}")
    return True

if __name__ == "__main__":
    fix_guardar_clasificacion() 