from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
# import pandas as pd # Ya no se usará pandas para leer este archivo específico
from . import bp # Importar el blueprint local
import sqlite3 # Para la conexión a la DB
from app.utils.common import get_db_connection, format_datetime_filter, format_number_es # Utilitarios

@bp.route('/', methods=['GET', 'POST'])
@login_required
def comparar_guias_sap_view():
    resultados_comparacion = [] # Inicializar fuera del bloque try

    if request.method == 'POST':
        if 'archivo_sap' not in request.files:
            flash('No se encontró el archivo en la solicitud.', 'warning')
            return redirect(request.url)
        
        file = request.files['archivo_sap']
        
        if file.filename == '':
            flash('No se seleccionó ningún archivo.', 'warning')
            return redirect(request.url)

        if file and (file.filename.endswith('.txt') or file.filename.endswith('.tsv')):
            conn = None # Inicializar conexión DB
            try:
                # --- Inicio: Lectura Manual del Archivo ---
                file_content = file.read().decode('utf-8') 
                lines = file_content.splitlines()
                current_app.logger.info(f"Archivo '{file.filename}' leído manualmente. Total líneas: {len(lines)}")
                # --- Fin: Lectura Manual del Archivo ---

                conn = get_db_connection()
                cursor = conn.cursor()

                # Indices esperados (contando desde 0)
                doc_mat_index = 4
                peso_index = 8
                
                # Líneas a saltar al inicio (ajustar si es necesario)
                skip_initial_lines = 4 
                line_number = 0

                for line in lines:
                    line_number += 1
                    # Saltar las primeras N líneas y líneas vacías
                    if line_number <= skip_initial_lines or not line.strip(): 
                        continue

                    try:
                        fields = line.split('	')
                        # Quitar espacios extra de cada campo por si acaso
                        fields = [field.strip() for field in fields] 

                        # Verificar si la línea tiene suficientes campos
                        if len(fields) > max(doc_mat_index, peso_index):
                            codigo_sap_archivo = fields[doc_mat_index]
                            peso_neto_archivo_str = fields[peso_index]

                            # Ignorar la línea de Total al final si existe
                            if codigo_sap_archivo.lower() == '* total' or 'total' in line.lower():
                                continue

                            # Inicializar datos para la tabla
                            codigo_guia_app = '-'
                            fecha_registro_app_str = '-'
                            peso_neto_app = None
                            peso_neto_archivo = None
                            diferencia_peso_str = '-'
                            alerta_icono = '' # Puede ser 'peso_invalido', 'no_encontrado_db'

                            # 1. Validar y convertir peso del archivo
                            if not peso_neto_archivo_str: # Chequear si está vacío
                                alerta_icono = 'peso_invalido'
                                current_app.logger.warning(f"Peso vacío en archivo para SAP {codigo_sap_archivo} en línea {line_number}")
                            else:
                                try:
                                    # Intentar reemplazar punto (miles) y luego coma (decimal)
                                    peso_neto_archivo = float(peso_neto_archivo_str.replace('.', '').replace(',', '.'))
                                except ValueError:
                                    current_app.logger.warning(f"Peso inválido en archivo para SAP {codigo_sap_archivo}: '{peso_neto_archivo_str}' en línea {line_number}")
                                    alerta_icono = 'peso_invalido'

                            # 2. Búsqueda en la Base de Datos (solo si el peso del archivo es válido y doc.mat no está vacío)
                            if alerta_icono != 'peso_invalido' and codigo_sap_archivo:
                                cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia_transporte_sap = ?", (codigo_sap_archivo,))
                                pesaje_bruto_result = cursor.fetchone()

                                if pesaje_bruto_result:
                                    codigo_guia_app = pesaje_bruto_result['codigo_guia']

                                    # Buscar fecha de registro en entry_records
                                    cursor.execute("SELECT timestamp_registro_utc FROM entry_records WHERE codigo_guia = ?", (codigo_guia_app,))
                                    entry_result = cursor.fetchone()
                                    if entry_result and entry_result['timestamp_registro_utc']:
                                        fecha_registro_app_str = format_datetime_filter(entry_result['timestamp_registro_utc'], format='%d/%m/%Y %H:%M')
                                    else:
                                        fecha_registro_app_str = 'Fecha no encontrada'

                                    # Buscar peso neto en pesajes_neto
                                    cursor.execute("SELECT peso_neto FROM pesajes_neto WHERE codigo_guia = ?", (codigo_guia_app,))
                                    pesaje_neto_result = cursor.fetchone()
                                    if pesaje_neto_result and pesaje_neto_result['peso_neto'] is not None:
                                        try:
                                            peso_neto_app = float(pesaje_neto_result['peso_neto'])
                                        except (ValueError, TypeError):
                                            current_app.logger.warning(f"Peso neto inválido en DB para guía {codigo_guia_app}: '{pesaje_neto_result['peso_neto']}'")
                                            peso_neto_app = None
                                    else:
                                        current_app.logger.info(f"No se encontró peso neto en DB para guía {codigo_guia_app}")

                                else:
                                    current_app.logger.info(f"Guía SAP {codigo_sap_archivo} (línea {line_number}) no encontrada en pesajes_bruto")
                                    alerta_icono = 'no_encontrado_db'
                            elif not codigo_sap_archivo:
                                 current_app.logger.warning(f"Doc. mat. vacío en línea {line_number}. Línea ignorada.")
                                 continue # Saltar al siguiente ciclo del for si no hay código SAP

                            # 3. Calcular diferencia
                            if peso_neto_archivo is not None and peso_neto_app is not None:
                                diferencia = peso_neto_archivo - peso_neto_app
                                diferencia_peso_str = format_number_es(diferencia)
                            elif alerta_icono == '' and codigo_sap_archivo: # Solo si no hay otra alerta y hay código
                                diferencia_peso_str = "Falta un peso"
                            elif alerta_icono == 'peso_invalido':
                                diferencia_peso_str = "Peso Arch. Inválido"


                            # Añadir resultado a la lista
                            resultados_comparacion.append({
                                'codigo_sap_archivo': codigo_sap_archivo if codigo_sap_archivo else 'Vacío',
                                'codigo_guia_app': codigo_guia_app,
                                'fecha_registro_app': fecha_registro_app_str,
                                'peso_neto_archivo': peso_neto_archivo, # Número o None
                                'peso_neto_archivo_str_original': peso_neto_archivo_str, # String original para mostrar si es inválido
                                'peso_neto_app': peso_neto_app,         # Número o None
                                'diferencia_peso': diferencia_peso_str,
                                'alerta_icono': alerta_icono
                            })

                        else:
                             current_app.logger.warning(f"Línea {line_number} ignorada: No tiene suficientes campos ({len(fields)}). Contenido: '{line[:100]}...'") # Log limitado

                    except Exception as inner_e:
                         current_app.logger.error(f"Error procesando línea {line_number}: {inner_e}", exc_info=True)
                         # Considerar añadir un resultado con error a la tabla o solo loguear
                
            except UnicodeDecodeError:
                 flash('Error al decodificar el archivo. Asegúrate que use codificación UTF-8.', 'danger')
                 # Renderizar con tabla vacía
                 return render_template('comparar_guias_sap.html', resultados_comparacion=[])
            except Exception as e:
                current_app.logger.error(f"Error general procesando archivo o consultando DB: {e}", exc_info=True)
                flash(f'Error general al procesar el archivo: {e}', 'danger')
                 # Renderizar con tabla vacía
                return render_template('comparar_guias_sap.html', resultados_comparacion=[])
            finally:
                if conn:
                    conn.close() 

            # Mostrar mensaje de éxito/aviso al final del procesamiento
            if resultados_comparacion:
                 flash(f'Archivo "{file.filename}" procesado. Se encontraron {len(resultados_comparacion)} registros de datos para comparar.', 'success')
            elif not get_flashed_messages(category_filter=['danger', 'warning']): # Solo mostrar si no hubo error previo
                 flash('No se encontraron datos procesables en el formato esperado dentro del archivo.', 'warning')

            # Renderizar la plantilla con los resultados (incluso si está vacía)
            return render_template('comparar_guias_sap.html', resultados_comparacion=resultados_comparacion)

        else: # Si el formato de archivo no es .txt o .tsv
            flash('Formato de archivo no válido. Sube un archivo .txt o .tsv.', 'danger')
            return redirect(request.url)

    # Método GET: solo mostrar el formulario vacío
    return render_template('comparar_guias_sap.html', resultados_comparacion=[]) 