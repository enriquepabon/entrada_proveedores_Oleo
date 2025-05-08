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
    resultados_comparacion = []
    totales = { # Inicializar diccionario de totales
        'peso_archivo': 0.0,
        'peso_app': 0.0,
        'diferencia': 0.0
    }

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
                col_codigo_sap_excel = "Guia de transporte"
                col_peso_excel = "Peso neto"

                # Verificar que el DataFrame tenga al menos dos columnas
                if len(df.columns) < 2:
                    flash(f'El archivo Excel debe contener al menos dos columnas. Se detectaron {len(df.columns)} columnas.', 'danger')
                    return redirect(request.url)

                # Intentar encontrar por nombre, si no, usar por posición
                # Columna para Guía SAP
                if col_codigo_sap_excel not in df.columns:
                    current_app.logger.warning(f"Columna '{col_codigo_sap_excel}' no encontrada. Usando la primera columna (índice 0) por defecto.")
                    actual_col_codigo_sap = df.columns[0]
                else:
                    actual_col_codigo_sap = col_codigo_sap_excel

                # Columna para Peso Neto
                if col_peso_excel not in df.columns:
                    current_app.logger.warning(f"Columna '{col_peso_excel}' no encontrada. Usando la segunda columna (índice 1) por defecto.")
                    actual_col_peso = df.columns[1]
                else:
                    actual_col_peso = col_peso_excel

                # Asegurar que la columna de código SAP se trate como string y limpiar el ".0"
                if actual_col_codigo_sap in df.columns:
                    # Primero convertir a string para manejar posibles floats leídos por Pandas
                    df[actual_col_codigo_sap] = df[actual_col_codigo_sap].astype(str)
                    # Eliminar el sufijo .0 si existe (común si Pandas leyó números como float)
                    df[actual_col_codigo_sap] = df[actual_col_codigo_sap].apply(
                        lambda x: x[:-2] if isinstance(x, str) and x.endswith('.0') and x[:-2].isdigit() else x
                    )
                    # También quitar cualquier espacio en blanco residual después de la conversión y limpieza
                    df[actual_col_codigo_sap] = df[actual_col_codigo_sap].str.strip()

                conn = get_db_connection()
                cursor = conn.cursor()

                # Iterar sobre las filas del DataFrame
                for index, row in df.iterrows():
                    # Obtener valores usando los nombres de columna identificados
                    # La columna SAP ya es string y ha sido limpiada, y strip() aplicado
                    codigo_sap_bruto = row[actual_col_codigo_sap] if pd.notna(row[actual_col_codigo_sap]) else ''
                    peso_neto_archivo_valor = row[actual_col_peso]
                    peso_neto_archivo_str = str(peso_neto_archivo_valor) if pd.notna(peso_neto_archivo_valor) else ''

                    # El código SAP ya no necesita ser procesado para quitar '-AÑO'
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
                        current_app.logger.warning(f"Peso vacío en archivo Excel para SAP {codigo_sap_archivo} (fila {index+2})")
                    else:
                        try:
                            # Corregir parseo para formato Excel: quitar comas de miles, mantener punto decimal
                            # Asegurarse que el valor sea tratado como string antes de reemplazar
                            peso_neto_archivo = float(str(peso_neto_archivo_valor).replace('.', '').replace(',', '.'))
                        except (ValueError, TypeError):
                            current_app.logger.warning(f"Peso inválido en archivo Excel para SAP {codigo_sap_archivo}: '{peso_neto_archivo_str}' (fila {index+2})")
                            alerta_icono = 'peso_invalido'

                    # 2. Búsqueda en la Base de Datos
                    if alerta_icono != 'peso_invalido' and codigo_sap_archivo:
                        current_app.logger.debug(f"Buscando en DB por codigo_guia_transporte_sap = '{codigo_sap_archivo}'")
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
                            current_app.logger.info(f"Guía SAP {codigo_sap_archivo} (fila {index+2}) no encontrada en pesajes_bruto")
                            alerta_icono = 'no_encontrado_db'
                    elif not codigo_sap_archivo:
                        current_app.logger.warning(f"Código SAP extraído vacío en fila {index+2}. Fila ignorada.")
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
                    # ACTUALIZACIÓN PENDIENTE PARA XML - ESPERANDO NOMBRES DE ETIQUETAS
                    # Si no se proporcionan, usaré inferencias y podrás ajustarlas.
                    tag_codigo_sap = 'Guia_de_transporte' # Placeholder - A ACTUALIZAR
                    tag_peso = 'Peso_neto' # Placeholder - A ACTUALIZAR

                    for item_index, item_element in enumerate(root.findall(tag_item)):
                        codigo_sap_bruto_element = item_element.find(tag_codigo_sap)
                        peso_neto_archivo_element = item_element.find(tag_peso)

                        codigo_sap_bruto = codigo_sap_bruto_element.text.strip() if codigo_sap_bruto_element is not None and codigo_sap_bruto_element.text else ''
                        peso_neto_archivo_str = peso_neto_archivo_element.text.strip() if peso_neto_archivo_element is not None and peso_neto_archivo_element.text else ''
                        
                        # El código SAP ya no necesita ser procesado para quitar '-AÑO'
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
                            current_app.logger.warning(f"Peso vacío en archivo XML para SAP {codigo_sap_archivo} (item {item_index+1})")
                        else:
                            try:
                                # Asegurarse que el valor sea tratado como string antes de reemplazar
                                peso_neto_archivo = float(str(peso_neto_archivo_str).replace('.', '').replace(',', '.'))
                            except (ValueError, TypeError):
                                current_app.logger.warning(f"Peso inválido en XML para SAP {codigo_sap_archivo}: '{peso_neto_archivo_str}' (item {item_index+1})")
                                alerta_icono = 'peso_invalido'

                        # 2. Búsqueda en la Base de Datos
                        if alerta_icono != 'peso_invalido' and codigo_sap_archivo:
                            current_app.logger.debug(f"Buscando en DB por codigo_guia_transporte_sap = '{codigo_sap_archivo}'")
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

            # --- Calcular Totales DESPUÉS de procesar todas las filas/items ---
            for resultado in resultados_comparacion:
                if resultado['peso_neto_archivo'] is not None:
                    totales['peso_archivo'] += resultado['peso_neto_archivo']
                if resultado['peso_neto_app'] is not None:
                    totales['peso_app'] += resultado['peso_neto_app']
                # Sumar la diferencia solo si ambos pesos existen
                if resultado['peso_neto_archivo'] is not None and resultado['peso_neto_app'] is not None:
                    diff_numeric = resultado['peso_neto_archivo'] - resultado['peso_neto_app']
                    totales['diferencia'] += diff_numeric

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

        # Pasar tanto los resultados como los totales al template
        return render_template('comparar_guias_sap.html', 
                               resultados_comparacion=resultados_comparacion,
                               totales=totales) # Añadir totales aquí

    # Método GET
    return render_template('comparar_guias_sap.html', 
                           resultados_comparacion=[], 
                           totales=totales) # Pasar totales también en GET (aunque sean 0) 