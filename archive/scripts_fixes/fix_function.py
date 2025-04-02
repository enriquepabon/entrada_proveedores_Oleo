import os
import sys

# Asegurarse de que el directorio actual está en el path
sys.path.insert(0, os.getcwd())

def fix_sintax_error():
    """
    Corrige errores de sintaxis en la función guardar_clasificacion_final
    """
    # Ruta al archivo 
    file_path = 'app/blueprints/clasificacion/routes.py'
    
    # Leer todo el contenido del archivo
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # Buscar la línea con la definición de la función
    function_start_line = -1
    for i, line in enumerate(lines):
        if "@bp.route('/guardar_clasificacion_final/" in line:
            function_start_line = i
            break
    
    if function_start_line == -1:
        print("No se encontró la función guardar_clasificacion_final")
        return
    
    # Buscar la línea con "flash(\"Clasificación guardada correctamente\"..."
    flash_line = -1
    for i in range(function_start_line, len(lines)):
        if "Clasificación guardada correctamente" in lines[i]:
            flash_line = i
            break
    
    if flash_line == -1:
        print("No se encontró la línea con flash")
        return
    
    # Crear una versión corregida de la función
    correct_end = """        # Esto es crítico para mantener la URL consistente
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
    
    # Crear una copia de seguridad
    with open(file_path + '.bak', 'w') as f:
        f.writelines(lines)
    
    # Tomar las líneas hasta el flash
    new_lines = lines[:flash_line]
    
    # Añadir la versión corregida
    new_lines.append(correct_end)
    
    # Escribir el archivo corregido
    with open(file_path, 'w') as f:
        f.writelines(new_lines)
    
    print("El archivo ha sido corregido con éxito")

if __name__ == "__main__":
    fix_sintax_error() 