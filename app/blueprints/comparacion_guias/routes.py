from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required
import pandas as pd # Re-habilitar pandas para leer Excel
from . import bp # Importar el blueprint local
import sqlite3 # Para la conexión a la DB
from app.utils.common import get_db_connection, format_datetime_filter, format_number_es # Utilitarios
import io # Para leer el archivo Excel en memoria
import xml.etree.ElementTree as ET # Para parsear XML

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

        conn = None # Inicializar conexión DB
        filename_lower = file.filename.lower() # Convertir nombre de archivo a minúsculas para la comprobación

        try:
            if filename_lower.endswith(('.xlsx', '.xls')):
                # --- Inicio: Lectura con Pandas read_excel ---
                # Leer el contenido del archivo en memoria
                file_content = io.BytesIO(file.read())
                # Leer el archivo Excel (asume cabecera en la primera fila)
                df = pd.read_excel(file_content)
                current_app.logger.info(f"Archivo Excel '{file.filename}' leído. Columnas detectadas: {list(df.columns)}")
                # --- Fin: Lectura con Pandas read_excel ---

                # Limpiar nombres de columnas (eliminar espacios extra)
                df.columns = df.columns.str.strip()
                current_app.logger.info(f"Columnas después de limpiar espacios: {list(df.columns)}")

                # Verificar columnas requeridas (ajustadas al nuevo formato)
                # Corregir nombres de columnas esperadas según el archivo real
                col_codigo_sap_excel = "Texto cab.documento" 
                col_peso_excel = "Ctd.en UM entrada"
                if col_codigo_sap_excel not in df.columns or col_peso_excel not in df.columns:
                    flash(f'El archivo Excel debe contener las columnas "{col_codigo_sap_excel}" y "{col_peso_excel}". Columnas encontradas: {list(df.columns)}', 'danger')
                    return redirect(request.url)

                conn = get_db_connection()
                cursor = conn.cursor()

                # Iterar sobre las filas del DataFrame
                for index, row in df.iterrows():
                    # Obtener valores usando los nombres de columna limpios
                    codigo_sap_bruto = str(row[col_codigo_sap_excel]) if pd.notna(row[col_codigo_sap_excel]) else ''
                    peso_neto_archivo_valor = row[col_peso_excel] # Puede ser número o string
                    peso_neto_archivo_str = str(peso_neto_archivo_valor) if pd.notna(peso_neto_archivo_valor) else ''

                    # Extraer la parte antes del guion del código SAP
                    if '-' in codigo_sap_bruto:
                        codigo_sap_archivo = codigo_sap_bruto.split('-')[0].strip()
                    else:
                        codigo_sap_archivo = codigo_sap_bruto.strip()

                    # Inicializar datos para la tabla
                    codigo_guia_app = '-'
                    fecha_registro_app_str = '-'
                    peso_neto_app = None
                    peso_neto_archivo = None
                    diferencia_peso_str = '-'
                    alerta_icono = ''

                    # 1. Validar y convertir peso del archivo
                    if not peso_neto_archivo_str:
                        alerta_icono = 'peso_invalido'
                        current_app.logger.warning(f"Peso vacío en archivo Excel para SAP bruto {codigo_sap_bruto} (fila {index+2})")
                    else:
                        try:
                            # Intentar convertir directamente a float (pandas puede manejar tipos)
                            # O aplicar lógica de limpieza si es necesario
                            peso_neto_archivo = float(str(peso_neto_archivo_valor).replace('.', '').replace(',', '.')) # Mantener limpieza por si acaso
                        except (ValueError, TypeError):
                            current_app.logger.warning(f"Peso inválido en archivo Excel para SAP bruto {codigo_sap_bruto}: '{peso_neto_archivo_str}' (fila {index+2})")
                            alerta_icono = 'peso_invalido'

                    # 2. Búsqueda en la Base de Datos
                    if alerta_icono != 'peso_invalido' and codigo_sap_archivo:
                        current_app.logger.debug(f"Buscando en DB por codigo_guia_transporte_sap = '{codigo_sap_archivo}' (extraído de '{codigo_sap_bruto}')")
                        cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia_transporte_sap = ?", (codigo_sap_archivo,))
                        pesaje_bruto_result = cursor.fetchone()

                        if pesaje_bruto_result:
                            codigo_guia_app = pesaje_bruto_result['codigo_guia']
                            # ... (lógica de búsqueda de fecha y peso neto se mantiene igual)
                            cursor.execute("SELECT timestamp_registro_utc FROM entry_records WHERE codigo_guia = ?", (codigo_guia_app,))
                            entry_result = cursor.fetchone()
                            if entry_result and entry_result['timestamp_registro_utc']:
                                fecha_registro_app_str = format_datetime_filter(entry_result['timestamp_registro_utc'], format='%d/%m/%Y %H:%M')
                            else:
                                fecha_registro_app_str = 'Fecha no encontrada'
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
                            current_app.logger.info(f"Guía SAP {codigo_sap_archivo} (fila {index+2}) no encontrada en pesajes_bruto")
                            alerta_icono = 'no_encontrado_db'
                    elif not codigo_sap_archivo:
                        current_app.logger.warning(f"Código SAP extraído vacío en fila {index+2} (de '{codigo_sap_bruto}'). Fila ignorada.")
                        continue

                    # 3. Calcular diferencia
                    if peso_neto_archivo is not None and peso_neto_app is not None:
                        diferencia = peso_neto_archivo - peso_neto_app
                        diferencia_peso_str = format_number_es(diferencia)
                    elif alerta_icono == '' and codigo_sap_archivo:
                        diferencia_peso_str = "Falta un peso"
                    elif alerta_icono == 'peso_invalido':
                        diferencia_peso_str = "Peso Arch. Inválido"

                    # Añadir resultado a la lista
                    resultados_comparacion.append({
                        'codigo_sap_archivo': codigo_sap_archivo if codigo_sap_archivo else 'Vacío',
                        'codigo_guia_app': codigo_guia_app,
                        'fecha_registro_app': fecha_registro_app_str,
                        'peso_neto_archivo': peso_neto_archivo,
                        'peso_neto_archivo_str_original': peso_neto_archivo_str,
                        'peso_neto_app': peso_neto_app,
                        'diferencia_peso': diferencia_peso_str,
                        'alerta_icono': alerta_icono
                    })

            elif filename_lower.endswith('.xml'):
                # --- Lectura de XML ---
                current_app.logger.info(f"Procesando archivo XML: {file.filename}")
                try:
                    tree = ET.parse(file) # Parsear directamente desde el objeto file
                    root = tree.getroot()
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # Asumiendo estructura: <registros><item><documentoMaterial>...</documentoMaterial><cantidad>...</cantidad></item></registros>
                    tag_item = 'item' # Etiqueta para cada registro/item
                    tag_codigo_sap = 'documentoMaterial' # Etiqueta para el código SAP bruto
                    tag_peso = 'cantidad' # Etiqueta para la cantidad/peso

                    for item_index, item_element in enumerate(root.findall(tag_item)):
                        codigo_sap_bruto_element = item_element.find(tag_codigo_sap)
                        peso_neto_archivo_element = item_element.find(tag_peso)

                        codigo_sap_bruto = codigo_sap_bruto_element.text.strip() if codigo_sap_bruto_element is not None and codigo_sap_bruto_element.text else ''
                        peso_neto_archivo_str = peso_neto_archivo_element.text.strip() if peso_neto_archivo_element is not None and peso_neto_archivo_element.text else ''
                        
                        # Extraer la parte antes del guion del código SAP
                        if '-' in codigo_sap_bruto:
                            codigo_sap_archivo = codigo_sap_bruto.split('-')[0].strip()
                        else:
                            codigo_sap_archivo = codigo_sap_bruto.strip()

                        # Inicializar datos para la tabla
                        codigo_guia_app = '-'
                        fecha_registro_app_str = '-'
                        peso_neto_app = None
                        peso_neto_archivo = None
                        diferencia_peso_str = '-'
                        alerta_icono = ''

                        # 1. Validar y convertir peso del archivo
                        if not peso_neto_archivo_str:
                            alerta_icono = 'peso_invalido'
                            current_app.logger.warning(f"Peso vacío en archivo XML para SAP bruto {codigo_sap_bruto} (item {item_index+1})")
                        else:
                            try:
                                peso_neto_archivo = float(peso_neto_archivo_str.replace('.', '').replace(',', '.'))
                            except (ValueError, TypeError):
                                current_app.logger.warning(f"Peso inválido en XML para SAP bruto {codigo_sap_bruto}: '{peso_neto_archivo_str}' (item {item_index+1})")
                                alerta_icono = 'peso_invalido'

                        # 2. Búsqueda en la Base de Datos
                        if alerta_icono != 'peso_invalido' and codigo_sap_archivo:
                            current_app.logger.debug(f"Buscando en DB por codigo_guia_transporte_sap = '{codigo_sap_archivo}' (extraído de '{codigo_sap_bruto}')")
                            cursor.execute("SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia_transporte_sap = ?", (codigo_sap_archivo,))
                            pesaje_bruto_result = cursor.fetchone()
                            if pesaje_bruto_result:
                                codigo_guia_app = pesaje_bruto_result['codigo_guia']
                                cursor.execute("SELECT timestamp_registro_utc FROM entry_records WHERE codigo_guia = ?", (codigo_guia_app,))
                                entry_result = cursor.fetchone()
                                if entry_result and entry_result['timestamp_registro_utc']:
                                    fecha_registro_app_str = format_datetime_filter(entry_result['timestamp_registro_utc'], format='%d/%m/%Y %H:%M')
                                else:
                                    fecha_registro_app_str = 'Fecha no encontrada'
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
                                current_app.logger.info(f"Guía SAP {codigo_sap_archivo} (item {item_index+1}) no encontrada en pesajes_bruto")
                                alerta_icono = 'no_encontrado_db'
                        elif not codigo_sap_archivo:
                            current_app.logger.warning(f"Código SAP extraído vacío en item {item_index+1} (de '{codigo_sap_bruto}'). Item ignorado.")
                            continue

                        # 3. Calcular diferencia
                        if peso_neto_archivo is not None and peso_neto_app is not None:
                            diferencia = peso_neto_archivo - peso_neto_app
                            diferencia_peso_str = format_number_es(diferencia)
                        elif alerta_icono == '' and codigo_sap_archivo:
                            diferencia_peso_str = "Falta un peso"
                        elif alerta_icono == 'peso_invalido':
                            diferencia_peso_str = "Peso Arch. Inválido"

                        # Añadir resultado a la lista
                        resultados_comparacion.append({
                            'codigo_sap_archivo': codigo_sap_archivo if codigo_sap_archivo else 'Vacío',
                            'codigo_guia_app': codigo_guia_app,
                            'fecha_registro_app': fecha_registro_app_str,
                            'peso_neto_archivo': peso_neto_archivo,
                            'peso_neto_archivo_str_original': peso_neto_archivo_str,
                            'peso_neto_app': peso_neto_app,
                            'diferencia_peso': diferencia_peso_str,
                            'alerta_icono': alerta_icono
                        })
                except ET.ParseError as xml_err:
                    flash(f'Error al parsear el archivo XML: {xml_err}. Verifica la estructura del archivo.', 'danger')
                    current_app.logger.error(f"Error parseando XML: {xml_err}", exc_info=True)
                    return render_template('comparar_guias_sap.html', resultados_comparacion=[])
            
            else: # Si no es Excel ni XML
                flash('Formato de archivo no válido. Sube un archivo .xlsx, .xls o .xml.', 'danger')
                return redirect(request.url)

        except ImportError:
            flash('Error interno: No se pudo importar la librería necesaria para leer el archivo.', 'danger')
            current_app.logger.error("Error importando librería (pandas, io o xml.etree)", exc_info=True)
        except FileNotFoundError:
            flash('Error interno: Archivo no encontrado después de la carga.', 'danger')
            current_app.logger.error("FileNotFoundError durante procesamiento", exc_info=True)
        except ValueError as ve:
            flash(f'Error en los datos del archivo: {ve}. Verifica el formato de números y fechas.', 'danger')
            current_app.logger.error(f"ValueError procesando archivo: {ve}", exc_info=True)
        except Exception as e:
            current_app.logger.error(f"Error general procesando archivo o consultando DB: {e}", exc_info=True)
            flash(f'Error general al procesar el archivo: {e}', 'danger')
        finally:
            if conn:
                conn.close()

        if resultados_comparacion:
            flash(f'Archivo "{file.filename}" procesado. Se compararon {len(resultados_comparacion)} registros.', 'success')
        elif not get_flashed_messages(category_filter=['danger', 'warning']):
            flash('No se encontraron datos procesables en el formato esperado dentro del archivo.', 'warning')

        return render_template('comparar_guias_sap.html', resultados_comparacion=resultados_comparacion)

    # Método GET
    return render_template('comparar_guias_sap.html', resultados_comparacion=[]) 