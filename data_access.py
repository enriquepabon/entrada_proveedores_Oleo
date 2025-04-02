import os
import json
import sqlite3
import logging
import traceback
from datetime import datetime

logger = logging.getLogger(__name__)

class DataAccess:
    def __init__(self, app):
        self.app = app
    
    def get_guia_complete_data(self, codigo_guia):
        """
        Obtiene datos completos de una guía, consolidando información de todas las tablas.
        """
        if not codigo_guia:
            return None
            
        try:
            with self.app.app_context():
                conn = sqlite3.connect(self.app.config.get('DATABASE', 'database.db'))
                conn.row_factory = sqlite3.Row  # Para acceder a resultados por nombre de columna
                c = conn.cursor()
                
                # Consulta que une todas las tablas relevantes
                query = '''
                SELECT 
                    e.*, 
                    pb.peso_bruto, pb.tipo_pesaje, pb.fecha_pesaje, pb.hora_pesaje, pb.imagen_pesaje,
                    pb.codigo_guia_transporte_sap, 
                    c.clasificacion_manual, c.clasificacion_automatica, c.fecha_clasificacion, c.hora_clasificacion,
                    pn.peso_tara, pn.peso_neto, pn.peso_producto, pn.fecha_pesaje_neto, pn.hora_pesaje_neto
                FROM entry_records e
                LEFT JOIN pesajes_bruto pb ON e.codigo_guia = pb.codigo_guia
                LEFT JOIN clasificaciones c ON e.codigo_guia = c.codigo_guia
                LEFT JOIN pesajes_neto pn ON e.codigo_guia = pn.codigo_guia
                WHERE e.codigo_guia = ?
                '''
                
                c.execute(query, (codigo_guia,))
                result = c.fetchone()
                
                if result:
                    # Convertir a diccionario para mayor facilidad de uso
                    datos = dict(result)
                    conn.close()
                    return datos
                
                # Si no encontramos datos en la BD, intentar con archivos JSON
                conn.close()
                return self._get_from_json(codigo_guia)
                
        except Exception as e:
            logger.error(f"Error al obtener datos de guía {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            # Intentar con el JSON como fallback
            return self._get_from_json(codigo_guia)
    
    def _get_from_json(self, codigo_guia):
        """Método auxiliar para obtener datos de un archivo JSON (compatibilidad)"""
        try:
            directorio_guias = self.app.config.get('GUIAS_DIR', 'guias')
            archivo_guia = os.path.join(directorio_guias, f'guia_{codigo_guia}.json')
            
            if os.path.exists(archivo_guia):
                with open(archivo_guia, 'r', encoding='utf-8') as file:
                    return json.load(file)
        except Exception as e:
            logger.error(f"Error al leer archivo JSON para {codigo_guia}: {str(e)}")
        
        return None
    
    def save_pesaje_bruto(self, datos_pesaje):
        """
        Guarda datos de pesaje bruto asegurando consistencia en la BD.
        """
        codigo_guia = datos_pesaje.get('codigo_guia')
        if not codigo_guia:
            raise ValueError("El código de guía es obligatorio")
        
        peso_bruto = datos_pesaje.get('peso_bruto')
        if not peso_bruto:
            raise ValueError("El peso bruto es obligatorio")
            
        try:
            with self.app.app_context():
                conn = sqlite3.connect(self.app.config.get('DATABASE', 'database.db'))
                c = conn.cursor()
                
                # Extraer código de guía transporte SAP si existe
                codigo_guia_transporte_sap = datos_pesaje.get('codigo_guia_transporte_sap', '')
                
                # Verificar si existe el registro de entrada
                c.execute('SELECT codigo_guia FROM entry_records WHERE codigo_guia = ?', (codigo_guia,))
                if not c.fetchone():
                    # Extraer código de proveedor
                    codigo_proveedor = datos_pesaje.get('codigo_proveedor')
                    nombre_proveedor = datos_pesaje.get('nombre_proveedor', 'No disponible')
                    
                    if not codigo_proveedor and '_' in codigo_guia:
                        codigo_proveedor = codigo_guia.split('_')[0]
                    
                    # Crear entry_record básico
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    fecha_registro = datos_pesaje.get('fecha_pesaje') or datetime.now().strftime('%d/%m/%Y')
                    hora_registro = datos_pesaje.get('hora_pesaje') or datetime.now().strftime('%H:%M:%S')
                    
                    c.execute('''
                    INSERT OR IGNORE INTO entry_records (
                        codigo_guia, codigo_proveedor, nombre_proveedor, fecha_registro, hora_registro, 
                        estado, fecha_creacion, codigo_guia_transporte_sap
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        codigo_guia, 
                        codigo_proveedor,
                        nombre_proveedor,
                        fecha_registro, 
                        hora_registro,
                        'entrada_completada',
                        now,
                        codigo_guia_transporte_sap
                    ))
                else:
                    # Actualizar el código de guía transporte SAP en entry_records si existe
                    if codigo_guia_transporte_sap:
                        c.execute('''
                        UPDATE entry_records SET 
                            codigo_guia_transporte_sap = ?
                        WHERE codigo_guia = ?
                        ''', (codigo_guia_transporte_sap, codigo_guia))
                
                # Insertar o actualizar pesaje bruto
                c.execute('SELECT codigo_guia FROM pesajes_bruto WHERE codigo_guia = ?', (codigo_guia,))
                if c.fetchone():
                    # Actualizar registro existente
                    c.execute('''
                    UPDATE pesajes_bruto SET 
                        peso_bruto = ?,
                        tipo_pesaje = ?,
                        fecha_pesaje = ?,
                        hora_pesaje = ?,
                        imagen_pesaje = ?,
                        codigo_guia_transporte_sap = ?
                    WHERE codigo_guia = ?
                    ''', (
                        datos_pesaje.get('peso_bruto'),
                        datos_pesaje.get('tipo_pesaje', 'directo'),
                        datos_pesaje.get('fecha_pesaje', datetime.now().strftime('%d/%m/%Y')),
                        datos_pesaje.get('hora_pesaje', datetime.now().strftime('%H:%M:%S')),
                        datos_pesaje.get('imagen_pesaje', ''),
                        codigo_guia_transporte_sap,
                        codigo_guia
                    ))
                else:
                    # Insertar nuevo registro
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    c.execute('''
                    INSERT INTO pesajes_bruto (
                        codigo_guia, peso_bruto, tipo_pesaje, fecha_pesaje, hora_pesaje, 
                        imagen_pesaje, estado, fecha_creacion, codigo_guia_transporte_sap
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        codigo_guia,
                        datos_pesaje.get('peso_bruto'),
                        datos_pesaje.get('tipo_pesaje', 'directo'),
                        datos_pesaje.get('fecha_pesaje', datetime.now().strftime('%d/%m/%Y')),
                        datos_pesaje.get('hora_pesaje', datetime.now().strftime('%H:%M:%S')),
                        datos_pesaje.get('imagen_pesaje', ''),
                        'pesaje_bruto_completado',
                        now,
                        codigo_guia_transporte_sap
                    ))
                
                # Actualizar el archivo JSON para compatibilidad
                self._update_json_file(codigo_guia, datos_pesaje)
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Error al guardar pesaje bruto para {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Intentar guardar sólo en JSON como fallback
            try:
                self._update_json_file(codigo_guia, datos_pesaje)
                return True
            except:
                pass
                
            return False
    
    def _update_json_file(self, codigo_guia, nuevos_datos):
        """Método auxiliar para actualizar un archivo JSON (compatibilidad)"""
        try:
            directorio_guias = self.app.config.get('GUIAS_DIR', 'guias')
            os.makedirs(directorio_guias, exist_ok=True)
            archivo_guia = os.path.join(directorio_guias, f'guia_{codigo_guia}.json')
            
            # Obtener datos actuales si existe el archivo
            datos_actuales = {}
            if os.path.exists(archivo_guia):
                with open(archivo_guia, 'r', encoding='utf-8') as file:
                    datos_actuales = json.load(file)
            
            # Preservar datos importantes del registro de entrada
            campos_importantes = [
                'codigo_proveedor', 'nombre_proveedor', 'nombre_agricultor', 
                'nombre', 'cantidad_racimos', 'racimos', 'transportador', 
                'transportista', 'placa', 'acarreo', 'cargo', 'codigo_transportista',
                'fecha_registro', 'hora_registro'
            ]
            
            # Combinar datos: para campos importantes, solo actualizar si el valor nuevo no es 'N/A' o vacío
            for campo in campos_importantes:
                if campo in datos_actuales and (campo not in nuevos_datos or 
                                               nuevos_datos.get(campo) in ['N/A', 'No disponible', '', None]):
                    nuevos_datos[campo] = datos_actuales[campo]
                    logger.info(f"Preservado campo importante: {campo}={datos_actuales[campo]}")
            
            # Actualizar con nuevos datos y preservar el resto de campos existentes
            datos_actuales.update(nuevos_datos)
            datos_actuales['codigo_guia'] = codigo_guia  # Asegurar que esté presente
            
            # Guardar archivo actualizado
            with open(archivo_guia, 'w', encoding='utf-8') as file:
                json.dump(datos_actuales, file, ensure_ascii=False, indent=4)
            
            logger.info(f"Archivo JSON actualizado para guía {codigo_guia} conservando datos de entrada")
            return True
        except Exception as e:
            logger.error(f"Error al actualizar archivo JSON para {codigo_guia}: {str(e)}")
            return False
    
    def save_pesaje_neto(self, datos_pesaje):
        """
        Guarda datos de pesaje neto asegurando consistencia en la BD.
        """
        codigo_guia = datos_pesaje.get('codigo_guia')
        if not codigo_guia:
            raise ValueError("El código de guía es obligatorio")
        
        peso_tara = datos_pesaje.get('peso_tara')
        if not peso_tara:
            raise ValueError("El peso tara es obligatorio")
            
        try:
            with self.app.app_context():
                conn = sqlite3.connect(self.app.config.get('DATABASE', 'database.db'))
                c = conn.cursor()
                
                # Verificar si existe el registro de pesaje bruto
                c.execute('SELECT codigo_guia, peso_bruto FROM pesajes_bruto WHERE codigo_guia = ?', (codigo_guia,))
                pesaje_bruto = c.fetchone()
                
                if not pesaje_bruto:
                    logger.warning(f"No se encontró pesaje bruto para {codigo_guia}. Intentando crear uno básico.")
                    
                    # Obtener datos de la guía para crear un pesaje bruto básico
                    datos_guia = self.get_guia_complete_data(codigo_guia)
                    if datos_guia:
                        # Crear un registro de pesaje bruto básico
                        peso_bruto = datos_pesaje.get('peso_bruto', 0)
                        
                        # Insertar pesaje bruto básico
                        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        c.execute('''
                        INSERT OR IGNORE INTO pesajes_bruto (
                            codigo_guia, peso_bruto, tipo_pesaje, fecha_pesaje, hora_pesaje, 
                            estado, fecha_creacion
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            codigo_guia,
                            peso_bruto,
                            'desconocido',
                            datetime.now().strftime('%d/%m/%Y'),
                            datetime.now().strftime('%H:%M:%S'),
                            'pesaje_bruto_completado',
                            now
                        ))
                    else:
                        # No podemos continuar sin datos de pesaje bruto o de guía
                        logger.error(f"No se puede crear pesaje neto sin datos previos para {codigo_guia}")
                        conn.close()
                        return False
                else:
                    # Si hay pesaje bruto, obtener el peso bruto para calcular el neto
                    peso_bruto = pesaje_bruto[1]
                    
                # Calcular peso neto (bruto - tara)
                try:
                    peso_bruto_float = float(peso_bruto)
                    peso_tara_float = float(peso_tara)
                    peso_neto = peso_bruto_float - peso_tara_float
                except (ValueError, TypeError):
                    logger.error(f"Error al convertir pesos a números: bruto={peso_bruto}, tara={peso_tara}")
                    peso_neto = 0
                
                # Si se proporciona peso_producto, usarlo; de lo contrario, es igual al peso neto
                if 'peso_producto' in datos_pesaje and datos_pesaje['peso_producto']:
                    peso_producto = datos_pesaje['peso_producto']
                else:
                    peso_producto = peso_neto
                
                # Insertar o actualizar pesaje neto
                c.execute('SELECT codigo_guia FROM pesajes_neto WHERE codigo_guia = ?', (codigo_guia,))
                if c.fetchone():
                    # Actualizar registro existente
                    c.execute('''
                    UPDATE pesajes_neto SET 
                        peso_tara = ?,
                        peso_neto = ?,
                        peso_producto = ?,
                        tipo_pesaje_neto = ?,
                        fecha_pesaje_neto = ?,
                        hora_pesaje_neto = ?,
                        imagen_pesaje_neto = ?
                    WHERE codigo_guia = ?
                    ''', (
                        peso_tara,
                        peso_neto,
                        peso_producto,
                        datos_pesaje.get('tipo_pesaje_neto', 'directo'),
                        datos_pesaje.get('fecha_pesaje_neto', datetime.now().strftime('%d/%m/%Y')),
                        datos_pesaje.get('hora_pesaje_neto', datetime.now().strftime('%H:%M:%S')),
                        datos_pesaje.get('imagen_pesaje_neto', ''),
                        codigo_guia
                    ))
                else:
                    # Insertar nuevo registro
                    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    c.execute('''
                    INSERT INTO pesajes_neto (
                        codigo_guia, peso_tara, peso_neto, peso_producto, tipo_pesaje_neto, 
                        fecha_pesaje_neto, hora_pesaje_neto, imagen_pesaje_neto, estado, fecha_creacion
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        codigo_guia,
                        peso_tara,
                        peso_neto,
                        peso_producto,
                        datos_pesaje.get('tipo_pesaje_neto', 'directo'),
                        datos_pesaje.get('fecha_pesaje_neto', datetime.now().strftime('%d/%m/%Y')),
                        datos_pesaje.get('hora_pesaje_neto', datetime.now().strftime('%H:%M:%S')),
                        datos_pesaje.get('imagen_pesaje_neto', ''),
                        'pesaje_neto_completado',
                        now
                    ))
                
                # Actualizar el archivo JSON para compatibilidad
                nuevos_datos = {
                    'codigo_guia': codigo_guia,
                    'peso_tara': peso_tara,
                    'peso_neto': str(peso_neto),
                    'peso_producto': str(peso_producto),
                    'tipo_pesaje_neto': datos_pesaje.get('tipo_pesaje_neto', 'directo'),
                    'fecha_pesaje_neto': datos_pesaje.get('fecha_pesaje_neto', datetime.now().strftime('%d/%m/%Y')),
                    'hora_pesaje_neto': datos_pesaje.get('hora_pesaje_neto', datetime.now().strftime('%H:%M:%S')),
                    'imagen_pesaje_neto': datos_pesaje.get('imagen_pesaje_neto', ''),
                    'estado_actual': 'pesaje_neto_completado'
                }
                self._update_json_file(codigo_guia, nuevos_datos)
                
                conn.commit()
                conn.close()
                return True
                
        except Exception as e:
            logger.error(f"Error al guardar pesaje neto para {codigo_guia}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # Intentar guardar sólo en JSON como fallback
            try:
                nuevos_datos = {
                    'codigo_guia': codigo_guia,
                    'peso_tara': peso_tara,
                    'peso_neto': datos_pesaje.get('peso_neto', '0'),
                    'peso_producto': datos_pesaje.get('peso_producto', '0'),
                    'tipo_pesaje_neto': datos_pesaje.get('tipo_pesaje_neto', 'directo'),
                    'fecha_pesaje_neto': datos_pesaje.get('fecha_pesaje_neto', datetime.now().strftime('%d/%m/%Y')),
                    'hora_pesaje_neto': datos_pesaje.get('hora_pesaje_neto', datetime.now().strftime('%H:%M:%S')),
                    'imagen_pesaje_neto': datos_pesaje.get('imagen_pesaje_neto', ''),
                    'estado_actual': 'pesaje_neto_completado'
                }
                self._update_json_file(codigo_guia, nuevos_datos)
                return True
            except:
                pass
                
            return False 