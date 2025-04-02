    except Exception as e:
        logger.error(f"Error en test_annotated_image: {str(e)}")
        logger.error(traceback.format_exc())
        flash(f"Error al generar imagen anotada: {str(e)}", "error")
        return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))


@bp.route('/regenerar_imagenes/<url_guia>')
def regenerar_imagenes(url_guia):
    """
    Regenera las imágenes procesadas para una guía de clasificación
    """
    try:
        logger.info(f"Iniciando regeneración de imágenes para {url_guia}")
        
        # Buscar el archivo de clasificación
        clasificacion_path = os.path.join(current_app.static_folder, 'clasificaciones', f"clasificacion_{url_guia}.json")
        
        if not os.path.exists(clasificacion_path):
            # Intentar buscar en subdirectorios
            alt_path = os.path.join(current_app.static_folder, 'fotos_racimos_temp', url_guia, f"clasificacion_{url_guia}.json")
            if os.path.exists(alt_path):
                clasificacion_path = alt_path
            else:
                # Intentar con el directorio configurado
                fotos_racimos_folder = current_app.config.get('FOTOS_RACIMOS_FOLDER', 'fotos_racimos_temp')
                alt_path = os.path.join(current_app.static_folder, fotos_racimos_folder, url_guia, f"clasificacion_{url_guia}.json")
                if os.path.exists(alt_path):
                    clasificacion_path = alt_path
        
        if not os.path.exists(clasificacion_path):
            logger.error(f"No se encontró el archivo de clasificación para: {url_guia}")
            flash("No se encontró información de clasificación para esta guía", "error")
            return redirect(url_for('clasificacion.ver_resultados_clasificacion', url_guia=url_guia))
        
        # Leer el archivo de clasificación
        with open(clasificacion_path, 'r', encoding='utf-8') as f:
            clasificacion_data = json.load(f)
        
        num_imagenes_regeneradas = 0
        errores = []
        
        # Verificar si existe la estructura de resultados_por_foto
        if 'resultados_por_foto' in clasificacion_data:
            resultados_data = clasificacion_data['resultados_por_foto']
            
            # Determinar si es un objeto o array
            if isinstance(resultados_data, dict):
                # Es un objeto con claves
                for key, resultado in resultados_data.items():
                    # Obtener imagen original
                    imagen_original = resultado.get('imagen_original', '')
                    detecciones = resultado.get('detecciones', [])
                    
                    # Solo procesar si hay imagen original y detecciones
                    if imagen_original and detecciones:
                        # Convertir path relativo a absoluto si es necesario
                        original_path = imagen_original
                        if not os.path.isabs(original_path):
                            original_path = os.path.join(current_app.static_folder, original_path)
                        
                        # Verificar que existe
                        if not os.path.exists(original_path):
                            # Buscar en rutas alternativas
                            filename = os.path.basename(original_path)
                            possible_paths = [
                                os.path.join(current_app.static_folder, 'uploads', 'fotos', url_guia, filename),
                                os.path.join(current_app.static_folder, 'fotos_racimos_temp', url_guia, filename),
                                os.path.join(current_app.static_folder, 'uploads', 'clasificacion', url_guia, filename),
                                os.path.join(current_app.static_folder, 'clasificaciones', 'fotos', url_guia, filename)
                            ]
                            
                            for path in possible_paths:
                                if os.path.exists(path):
                                    original_path = path
                                    logger.info(f"Imagen original encontrada en ruta alternativa: {path}")
                                    break
                                results['info_fotos_en_resultados'].append({
                                    'key': key,
                                    'imagen_original': resultado.get('imagen_original', ''),
                                    'imagen_procesada': resultado.get('imagen_procesada', '')
                                })
                        elif isinstance(resultados_data, list):
                            for i, resultado in enumerate(resultados_data):
                                results['info_fotos_en_resultados'].append({
                                    'index': i,
                                    'imagen_original': resultado.get('imagen_original', ''),
                                    'imagen_procesada': resultado.get('imagen_procesada', '')
                                })
                except json.JSONDecodeError:
                    results['error_json'] = "Error al decodificar el JSON de clasificación"
        
        return jsonify(results)
    
    except Exception as e:
        logger.error(f"Error en debug_image_paths: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        })

@bp.route('/debug_image_paths/<url_guia>')
def debug_image_paths(url_guia):
    """
    Ruta de debug para mostrar información sobre las rutas de imágenes de una guía
    """
    try:
        from flask import jsonify
        
        logger.info(f"Iniciando debug_image_paths para {url_guia}")
        
        results = {
            'url_guia': url_guia,
            'static_folder': current_app.static_folder,
            'fotos_encontradas': [],
            'directorios_verificados': [],
            'directorios_existentes': []
        }
        
        # Verificar directorios posibles
        possible_dirs = [
            f"uploads/fotos/{url_guia}",
            f"fotos_racimos_temp/{url_guia}",
            f"uploads/clasificacion/{url_guia}",
            f"clasificaciones/fotos/{url_guia}"
        ]
        
        for dir_path in possible_dirs:
            full_dir_path = os.path.join(current_app.static_folder, dir_path)
            results['directorios_verificados'].append(full_dir_path)
            
            if os.path.exists(full_dir_path) and os.path.isdir(full_dir_path):
                results['directorios_existentes'].append({
                    'path': full_dir_path,
                    'rel_path': dir_path
                })
                
                # Listar archivos en el directorio
                files = os.listdir(full_dir_path)
                for file in files:
                    if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                        file_path = os.path.join(full_dir_path, file)
                        url = url_for('static', filename=f"{dir_path}/{file}")
                        
                        results['fotos_encontradas'].append({
                            'filename': file,
                            'full_path': file_path,
                            'url': url,
                            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                            'is_annotated': '_annotated' in file.lower()
                        })
        
        # Buscar archivo de clasificación
        clasificacion_path = os.path.join(current_app.static_folder, 'clasificaciones', f"clasificacion_{url_guia}.json")
        results['clasificacion_json'] = {
            'path': clasificacion_path,
            'exists': os.path.exists(clasificacion_path),
            'size': os.path.getsize(clasificacion_path) if os.path.exists(clasificacion_path) else 0
        }
        
        # Si el archivo de clasificación existe, extraer información de imágenes
        if os.path.exists(clasificacion_path):
            with open(clasificacion_path, 'r', encoding='utf-8') as f:
                try:
                    clasificacion_data = json.load(f)
                    
                    # Extraer información sobre fotos
                    if 'fotos' in clasificacion_data:
                        results['fotos_en_json'] = clasificacion_data['fotos']
                    
                    # Extraer información sobre resultados por foto
                    if 'resultados_por_foto' in clasificacion_data:
                        results['info_fotos_en_resultados'] = []
                        
                        resultados_data = clasificacion_data['resultados_por_foto']
                        if isinstance(resultados_data, dict):
                            for key, resultado in resultados_data.items():
                                results['info_fotos_en_resultados'].append({
                                    'key': key,
                                    'imagen_original': resultado.get('imagen_original', ''),
                                    'imagen_procesada': resultado.get('imagen_procesada', '')
                                })
                        elif isinstance(resultados_data, list):
                            for i, resultado in enumerate(resultados_data):
                                results['info_fotos_en_resultados'].append({
                                    'index': i,
                                    'imagen_original': resultado.get('imagen_original', ''),
                                    'imagen_procesada': resultado.get('imagen_procesada', '')
                                })
                except json.JSONDecodeError:
                    results['error_json'] = "Error al decodificar el JSON de clasificación"
        
        return jsonify(results)
    
    except Exception as e:
        logger.error(f"Error en debug_image_paths: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': str(e),
