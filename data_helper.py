#!/usr/bin/env python3
"""
Helper para normalizar y consolidar los datos del proveedor en la aplicación.
Este módulo garantiza la consistencia en los nombres de variables y datos
entre los diferentes templates y módulos de la aplicación.
"""

import os
import json
import glob
import logging
from datetime import datetime
from flask import session

# Configurar logging
logger = logging.getLogger('data_helper')

class DataHelper:
    def __init__(self, app):
        self.app = app
        self.guias_folder = app.config['GUIAS_FOLDER']
    
    def normalizar_datos_proveedor(self, datos):
        """
        Normaliza las variables relacionadas con el proveedor para mantener
        consistencia en los nombres de las variables entre diferentes módulos
        """
        if not datos:
            return {}
        
        # Crea una copia de los datos para no modificar el original
        normalizado = datos.copy()
        
        # Normalizar código de proveedor
        if 'codigo_proveedor' in normalizado and not 'codigo' in normalizado:
            normalizado['codigo'] = normalizado['codigo_proveedor']
        elif 'codigo' in normalizado and not 'codigo_proveedor' in normalizado:
            normalizado['codigo_proveedor'] = normalizado['codigo']
        elif not 'codigo' in normalizado and not 'codigo_proveedor' in normalizado:
            # Intentar extraer el código del proveedor del código de guía
            if 'codigo_guia' in normalizado and '_' in normalizado['codigo_guia']:
                codigo_base = normalizado['codigo_guia'].split('_')[0]
                normalizado['codigo'] = codigo_base
                normalizado['codigo_proveedor'] = codigo_base
        
        # Normalizar nombre de proveedor
        if 'nombre_agricultor' in normalizado and not 'nombre_proveedor' in normalizado:
            normalizado['nombre_proveedor'] = normalizado['nombre_agricultor']
        elif 'nombre' in normalizado and not 'nombre_proveedor' in normalizado:
            normalizado['nombre_proveedor'] = normalizado['nombre']
        elif 'nombre_proveedor' in normalizado:
            # Asegurarse que también esté disponible en otros campos comunes
            normalizado['nombre_agricultor'] = normalizado['nombre_proveedor']
            normalizado['nombre'] = normalizado['nombre_proveedor']
        
        # Normalizar cantidad de racimos
        if 'cantidad_racimos' in normalizado and not 'racimos' in normalizado:
            normalizado['racimos'] = normalizado['cantidad_racimos']
        elif 'racimos' in normalizado and not 'cantidad_racimos' in normalizado:
            normalizado['cantidad_racimos'] = normalizado['racimos']
        
        return normalizado
    
    def obtener_datos_completos_guia(self, codigo_guia):
        """
        Obtiene los datos completos de la guía combinando todas las fuentes disponibles
        y normalizando los nombres de las variables.
        """
        datos_combinados = {}
        fuentes_utilizadas = []
        
        # 1. Verificar si hay datos en la sesión
        datos_sesion = {
            'peso_bruto': session.get('peso_bruto'),
            'estado_actual': session.get('estado_actual'),
            'fotos_pesaje': session.get('fotos_pesaje', []),
            'tipo_pesaje': session.get('tipo_pesaje'),
            'nombre_proveedor': session.get('nombre_proveedor'),
            'codigo_proveedor': session.get('codigo_proveedor'),
            'racimos': session.get('racimos'),
            'placa': session.get('placa'),
            'transportador': session.get('transportador'),
            'codigo_guia_transporte_sap': session.get('codigo_guia_transporte_sap'),
        }
        
        # Filtrar valores None o vacíos
        datos_sesion = {k: v for k, v in datos_sesion.items() if v is not None}
        
        if datos_sesion:
            datos_combinados.update(datos_sesion)
            fuentes_utilizadas.append('sesión')
        
        # 2. Intentar obtener datos a través de utils.get_datos_guia
        try:
            from utils import get_datos_guia
            datos_guia = get_datos_guia(codigo_guia)
            if datos_guia:
                # Normalizar y combinar con lo que ya tenemos
                datos_guia = self.normalizar_datos_proveedor(datos_guia)
                datos_combinados.update(datos_guia)
                fuentes_utilizadas.append('utils.get_datos_guia')
        except Exception as e:
            logger.error(f"Error al obtener datos de guía vía utils: {str(e)}")
        
        # 3. Verificar si hay datos en la base de datos
        try:
            from data_access import DataAccess
            dal = DataAccess(self.app)
            datos_guia_db = dal.get_guia_complete_data(codigo_guia)
            if datos_guia_db:
                # Normalizar y combinar con lo que ya tenemos
                datos_guia_db = self.normalizar_datos_proveedor(datos_guia_db)
                datos_combinados.update(datos_guia_db)
                fuentes_utilizadas.append('data_access.get_guia_complete_data')
        except Exception as e:
            logger.error(f"Error al obtener datos de la base de datos: {str(e)}")
        
        # 4. Intentar obtener datos desde la tabla entry_records
        try:
            from db_utils import get_entry_record_by_guide_code
            entry_record = get_entry_record_by_guide_code(codigo_guia)
            if entry_record:
                # Normalizar y combinar con lo que ya tenemos
                entry_record = self.normalizar_datos_proveedor(entry_record)
                datos_combinados.update(entry_record)
                fuentes_utilizadas.append('entry_records')
        except Exception as e:
            logger.error(f"Error al obtener datos desde entry_records: {str(e)}")
        
        # 5. Intentar buscar en archivos JSON
        try:
            codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
            json_paths = [
                # Buscar en archivos con prefijo "datos_" (estructura anterior)
                os.path.join(self.app.static_folder, 'guias', f'datos_{codigo_guia}.json'),
                os.path.join(self.app.static_folder, 'guias', f'datos_{codigo_base}*.json'),
                # Buscar en archivos con prefijo "guia_" (estructura actual)
                os.path.join('guias', f'guia_{codigo_guia}.json'),
                os.path.join('guias', f'guia_{codigo_base}*.json')
            ]
            
            for json_pattern in json_paths:
                for json_path in glob.glob(json_pattern):
                    if os.path.exists(json_path):
                        with open(json_path, 'r') as f:
                            try:
                                datos_json = json.load(f)
                                if datos_json:
                                    # Normalizar y combinar con lo que ya tenemos
                                    datos_json = self.normalizar_datos_proveedor(datos_json)
                                    datos_combinados.update(datos_json)
                                    fuentes_utilizadas.append(f'JSON:{os.path.basename(json_path)}')
                                    logger.info(f"Datos cargados desde archivo JSON: {json_path}")
                                    # Si encontramos el código de guía transporte SAP, registrarlo específicamente
                                    if 'codigo_guia_transporte_sap' in datos_json:
                                        logger.info(f"Código de guía transporte SAP encontrado en {json_path}: {datos_json['codigo_guia_transporte_sap']}")
                                    break
                            except json.JSONDecodeError:
                                logger.warning(f"Error al decodificar JSON en {json_path}")
        except Exception as e:
            logger.error(f"Error al buscar en archivos JSON: {str(e)}")
        
        # Si no hay datos disponibles, crear estructura mínima
        if not datos_combinados and codigo_guia:
            codigo_base = codigo_guia.split('_')[0] if '_' in codigo_guia else codigo_guia
            datos_combinados = {
                'codigo': codigo_base,
                'codigo_proveedor': codigo_base,
                'codigo_guia': codigo_guia,
                'nombre_proveedor': 'No disponible',
                'racimos': 'No disponible',
                'placa': 'No disponible',
                'transportador': 'No disponible'
            }
            fuentes_utilizadas.append('valores_por_defecto')
        
        # Añadir información de las fuentes utilizadas para diagnóstico
        datos_combinados['_fuentes_datos'] = fuentes_utilizadas
        
        # Asegurar que todos los datos estén normalizados antes de devolverlos
        datos_finales = self.normalizar_datos_proveedor(datos_combinados)
        
        # Registrar el resultado para diagnóstico
        logger.info(f"Datos combinados para {codigo_guia} desde fuentes: {', '.join(fuentes_utilizadas)}")
        logger.debug(f"Campos disponibles: {list(datos_finales.keys())}")
        
        return datos_finales
    
    def guardar_datos_combinados(self, codigo_guia, datos):
        """
        Guarda los datos combinados en todas las ubicaciones relevantes
        """
        if not codigo_guia or not datos:
            logger.warning("No se pueden guardar datos vacíos o sin código de guía")
            return False
        
        intentos_exitosos = 0
        errores = []
        
        # 1. Normalizar datos
        datos = self.normalizar_datos_proveedor(datos)
        
        # 2. Guardar en la sesión los campos relevantes
        campos_sesion = ['peso_bruto', 'estado_actual', 'tipo_pesaje', 'nombre_proveedor', 
                          'codigo_proveedor', 'racimos', 'placa', 'transportador']
        for campo in campos_sesion:
            if campo in datos:
                session[campo] = datos[campo]
                session.modified = True
        
        intentos_exitosos += 1
        
        # 3. Guardar en la base de datos
        try:
            from data_access import DataAccess
            dal = DataAccess(self.app)
            
            # Guardar datos de pesaje si existen
            if 'peso_bruto' in datos:
                dal.guardar_pesaje(codigo_guia, datos)
                logger.info(f"Datos de pesaje guardados en BD para guía {codigo_guia}")
            
            # Guardar datos generales de la guía
            dal.guardar_datos_guia(codigo_guia, datos)
            logger.info(f"Datos generales de guía guardados en BD para {codigo_guia}")
            
            intentos_exitosos += 1
        except Exception as e:
            error_msg = f"Error al guardar en base de datos: {str(e)}"
            logger.error(error_msg)
            errores.append(error_msg)
        
        # 4. Guardar en archivo JSON
        try:
            json_path = os.path.join(self.app.static_folder, 'guias', f'datos_{codigo_guia}.json')
            os.makedirs(os.path.dirname(json_path), exist_ok=True)
            
            # Si ya existe, leer y combinar
            datos_existentes = {}
            if os.path.exists(json_path):
                with open(json_path, 'r') as f:
                    try:
                        datos_existentes = json.load(f)
                    except json.JSONDecodeError:
                        logger.warning(f"Archivo JSON corrupto, se sobrescribirá: {json_path}")
            
            # Actualizar datos y guardar
            datos_existentes.update(datos)
            with open(json_path, 'w') as f:
                json.dump(datos_existentes, f, indent=2)
            
            logger.info(f"Datos guardados en JSON para guía {codigo_guia}")
            intentos_exitosos += 1
        except Exception as e:
            error_msg = f"Error al guardar en JSON: {str(e)}"
            logger.error(error_msg)
            errores.append(error_msg)
        
        return intentos_exitosos > 0, errores

def init_data_helper(app):
    """
    Inicializa y devuelve una instancia de DataHelper
    """
    return DataHelper(app) 