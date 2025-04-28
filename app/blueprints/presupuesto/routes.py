from flask import request, jsonify, current_app
import os
import logging
from werkzeug.utils import secure_filename
import pandas as pd # Importar pandas
import traceback # Para logging de errores detallado
# Importar login_required
from flask_login import login_required

# Importar el blueprint desde __init__.py
from . import bp 

# Configurar logging
logger = logging.getLogger(__name__)

# Directorio para guardar presupuestos
BUDGET_FOLDER = 'presupuestos' # Subcarpeta dentro de static/uploads
ALLOWED_EXTENSIONS = {'xlsx', 'csv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/upload', methods=['POST'])
@login_required # Añadir protección
def upload_budget():
    """Ruta para manejar la carga y procesamiento inicial del archivo de presupuesto."""
    logger.info("Recibida solicitud POST en /presupuesto/upload")
    
    if 'file' not in request.files:
        logger.warning("No se encontró el archivo en la solicitud.")
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['file']

    if file.filename == '':
        logger.warning("Nombre de archivo vacío.")
        return jsonify({'error': 'No se seleccionó ningún archivo'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower()
        
        # Crear ruta de guardado
        base_upload_folder = current_app.config.get('UPLOAD_FOLDER', os.path.join(current_app.static_folder, 'uploads'))
        budget_save_path = os.path.join(base_upload_folder, BUDGET_FOLDER)
        save_location = os.path.join(budget_save_path, filename)
        
        try:
            # Crear directorio si no existe
            os.makedirs(budget_save_path, exist_ok=True)
            logger.info(f"Directorio de presupuestos asegurado: {budget_save_path}")
            
            # Guardar archivo
            file.save(save_location)
            logger.info(f"Archivo de presupuesto guardado temporalmente en: {save_location}")
            
            # --- Inicio: Parsing con Pandas --- 
            try:
                df = None
                if file_ext == 'xlsx':
                    df = pd.read_excel(save_location, engine='openpyxl')
                elif file_ext == 'csv':
                    # Intentar detectar separador común (;, o \t)
                    try:
                        df = pd.read_csv(save_location, sep=';')
                    except Exception:
                         try:
                             df = pd.read_csv(save_location, sep=',')
                         except Exception:
                              df = pd.read_csv(save_location, sep='\t')
                
                if df is None:
                    raise ValueError("No se pudo leer el archivo con pandas.")
                
                logger.info(f"Archivo leído con pandas. Columnas encontradas: {df.columns.tolist()}")

                # Normalizar nombres de columnas (a minúsculas para búsqueda insensible)
                df.columns = [str(col).lower().strip() for col in df.columns]
                logger.debug(f"Columnas normalizadas: {df.columns.tolist()}")

                # Buscar columnas requeridas (insensible a mayúsculas/minúsculas)
                col_fecha = None
                col_toneladas = None
                
                possible_fecha_cols = ['fecha', 'dia', 'date']
                possible_ton_cols = ['toneladasproyectadas', 'toneladas', 'proyectado', 'presupuesto', 'budget', 'tons']

                for col in df.columns:
                    if col in possible_fecha_cols:
                        col_fecha = col
                        break
                for col in df.columns:
                    if col in possible_ton_cols:
                        col_toneladas = col
                        break
                
                if not col_fecha or not col_toneladas:
                    logger.error(f"Columnas requeridas ('{possible_fecha_cols[0]}', '{possible_ton_cols[0]}') no encontradas en el archivo. Columnas detectadas: {df.columns.tolist()}")
                    return jsonify({'error': f'Columnas requeridas ({possible_fecha_cols[0]} y {possible_ton_cols[0]}) no encontradas.'}), 400
                
                logger.info(f"Columnas mapeadas: Fecha='{col_fecha}', Toneladas='{col_toneladas}'")

                # Seleccionar y renombrar columnas para consistencia
                df_presupuesto = df[[col_fecha, col_toneladas]].rename(columns={
                    col_fecha: 'fecha_presupuesto',
                    col_toneladas: 'toneladas_proyectadas'
                })

                # --- Aquí iría la validación de datos y guardado en BD (Paso 2.1 parte 2 y 2.4) --- 
                logger.info(f"DataFrame de presupuesto extraído (primeras 5 filas):\n{df_presupuesto.head().to_string()}")
                
                # --- Importar y llamar a guardar_datos_presupuesto --- 
                from app.utils.db_budget_operations import guardar_datos_presupuesto
                
                # Convertir DataFrame a lista de diccionarios para la función de guardado
                # Asegurarse de que las fechas estén en formato YYYY-MM-DD
                try:
                    df_presupuesto['fecha_presupuesto'] = pd.to_datetime(df_presupuesto['fecha_presupuesto']).dt.strftime('%Y-%m-%d')
                except Exception as date_err:
                    logger.error(f"Error convirtiendo columna de fecha a string YYYY-MM-DD: {date_err}")
                    return jsonify({'error': 'Error en el formato de la columna de fecha.'}), 400
                    
                datos_para_guardar = df_presupuesto.to_dict('records')
                
                success_db = guardar_datos_presupuesto(datos_para_guardar)
                
                if success_db:
                    return jsonify({
                        'success': True, 
                        'message': f'Archivo \'{filename}\' cargado y los datos de presupuesto han sido guardados/actualizados.',
                        'parsed_rows': len(df_presupuesto)
                    }), 200
                else:
                     return jsonify({'error': 'Archivo procesado pero hubo un error al guardar en la base de datos.'}), 500
                # --- Fin llamada a guardar_datos_presupuesto ---

            except Exception as parse_error:
                logger.error(f"Error al parsear el archivo '{filename}': {parse_error}", exc_info=True)
                # Considerar borrar archivo si falla el parsing: os.remove(save_location)
                return jsonify({'error': f'Error al procesar el archivo: {parse_error}'}), 500
            # --- Fin: Parsing con Pandas --- 
            
        except Exception as e:
            logger.error(f"Error general al cargar el archivo de presupuesto: {e}", exc_info=True)
            return jsonify({'error': 'Error interno al procesar la carga.'}), 500

    else:
        logger.warning(f"Tipo de archivo no permitido: {filename}")
        return jsonify({'error': 'Tipo de archivo no permitido. Use .xlsx o .csv'}), 400 