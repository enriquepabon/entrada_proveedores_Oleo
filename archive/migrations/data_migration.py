"""
Script para migrar datos existentes de archivos HTML y JSON a la base de datos SQLite.
Este script debe ejecutarse una sola vez para poblar la base de datos con los datos existentes.
"""

import os
import glob
import json
import logging
import re
from datetime import datetime
from bs4 import BeautifulSoup

# Importar funciones de base de datos
import db_schema
import db_operations

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def migrate_pesajes_bruto():
    """
    Migra los datos de pesajes brutos desde archivos HTML a la base de datos SQLite.
    """
    logger.info("Iniciando migración de pesajes brutos...")
    
    # Directorio donde se encuentran los archivos HTML de guías
    guias_dir = os.path.join('static', 'guias')
    
    if not os.path.exists(guias_dir):
        logger.warning(f"El directorio {guias_dir} no existe. No hay datos para migrar.")
        return 0
    
    count = 0
    for filename in os.listdir(guias_dir):
        if filename.startswith('guia_') and filename.endswith('.html'):
            try:
                # Extraer código de guía del nombre del archivo
                codigo_guia = filename.replace('guia_', '').replace('.html', '')
                
                # Leer el archivo HTML
                with open(os.path.join(guias_dir, filename), 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parsear el HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extraer datos relevantes
                peso_bruto = None
                tipo_pesaje = None
                fecha_pesaje = None
                hora_pesaje = None
                codigo_proveedor = None
                nombre_proveedor = None
                imagen_pesaje = None
                
                # Buscar datos en el HTML
                for row in soup.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].get_text().strip().lower()
                        value = cells[1].get_text().strip()
                        
                        if 'peso bruto' in label:
                            peso_bruto = value
                        elif 'tipo de pesaje' in label:
                            tipo_pesaje = value
                        elif 'fecha de pesaje' in label:
                            fecha_pesaje = value
                        elif 'hora de pesaje' in label:
                            hora_pesaje = value
                        elif 'código de proveedor' in label:
                            codigo_proveedor = value
                        elif 'nombre de proveedor' in label:
                            nombre_proveedor = value
                
                # Buscar imagen de pesaje
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    if 'pesaje' in src.lower():
                        imagen_pesaje = src
                        break
                
                # Solo migrar si tiene peso bruto
                if peso_bruto:
                    # Preparar datos para almacenar
                    datos_pesaje = {
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': codigo_proveedor,
                        'nombre_proveedor': nombre_proveedor,
                        'peso_bruto': peso_bruto,
                        'tipo_pesaje': tipo_pesaje,
                        'fecha_pesaje': fecha_pesaje,
                        'hora_pesaje': hora_pesaje,
                        'imagen_pesaje': imagen_pesaje,
                        'estado': 'activo'
                    }
                    
                    # Almacenar en la base de datos
                    if db_operations.store_pesaje_bruto(datos_pesaje):
                        count += 1
                        logger.info(f"Migrado pesaje bruto para guía: {codigo_guia}")
                    else:
                        logger.error(f"Error al migrar pesaje bruto para guía: {codigo_guia}")
            
            except Exception as e:
                logger.error(f"Error procesando archivo {filename}: {str(e)}")
    
    logger.info(f"Migración de pesajes brutos completada. {count} registros migrados.")
    return count

def migrate_pesajes_neto():
    """
    Migra los datos de pesajes netos desde archivos HTML a la base de datos SQLite.
    """
    logger.info("Iniciando migración de pesajes netos...")
    
    # Directorio donde se encuentran los archivos HTML de guías
    guias_dir = os.path.join('static', 'guias')
    
    if not os.path.exists(guias_dir):
        logger.warning(f"El directorio {guias_dir} no existe. No hay datos para migrar.")
        return 0
    
    count = 0
    for filename in os.listdir(guias_dir):
        if filename.startswith('guia_') and filename.endswith('.html'):
            try:
                # Extraer código de guía del nombre del archivo
                codigo_guia = filename.replace('guia_', '').replace('.html', '')
                
                # Leer el archivo HTML
                with open(os.path.join(guias_dir, filename), 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Parsear el HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Extraer datos relevantes
                peso_bruto = None
                peso_tara = None
                peso_neto = None
                tipo_pesaje = None
                fecha_pesaje = None
                hora_pesaje = None
                codigo_proveedor = None
                nombre_proveedor = None
                imagen_pesaje = None
                
                # Buscar datos en el HTML
                for row in soup.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].get_text().strip().lower()
                        value = cells[1].get_text().strip()
                        
                        if 'peso bruto' in label:
                            peso_bruto = value
                        elif 'peso tara' in label:
                            peso_tara = value
                        elif 'peso neto' in label:
                            peso_neto = value
                        elif 'tipo de pesaje neto' in label:
                            tipo_pesaje = value
                        elif 'fecha de pesaje neto' in label:
                            fecha_pesaje = value
                        elif 'hora de pesaje neto' in label:
                            hora_pesaje = value
                        elif 'código de proveedor' in label:
                            codigo_proveedor = value
                        elif 'nombre de proveedor' in label:
                            nombre_proveedor = value
                
                # Buscar imagen de pesaje neto
                img_tags = soup.find_all('img')
                for img in img_tags:
                    src = img.get('src', '')
                    if 'pesaje_neto' in src.lower():
                        imagen_pesaje = src
                        break
                
                # Solo migrar si tiene peso neto
                if peso_neto:
                    # Preparar datos para almacenar
                    datos_pesaje = {
                        'codigo_guia': codigo_guia,
                        'codigo_proveedor': codigo_proveedor,
                        'nombre_proveedor': nombre_proveedor,
                        'peso_bruto': peso_bruto,
                        'peso_tara': peso_tara,
                        'peso_neto': peso_neto,
                        'tipo_pesaje': tipo_pesaje,
                        'fecha_pesaje': fecha_pesaje,
                        'hora_pesaje': hora_pesaje,
                        'imagen_pesaje': imagen_pesaje,
                        'estado': 'activo'
                    }
                    
                    # Almacenar en la base de datos
                    if db_operations.store_pesaje_neto(datos_pesaje):
                        count += 1
                        logger.info(f"Migrado pesaje neto para guía: {codigo_guia}")
                    else:
                        logger.error(f"Error al migrar pesaje neto para guía: {codigo_guia}")
            
            except Exception as e:
                logger.error(f"Error procesando archivo {filename}: {str(e)}")
    
    logger.info(f"Migración de pesajes netos completada. {count} registros migrados.")
    return count

def migrate_clasificaciones():
    """
    Migra los datos de clasificaciones desde archivos JSON a la base de datos SQLite.
    """
    logger.info("Iniciando migración de clasificaciones...")
    
    # Directorio donde se encuentran los archivos JSON de clasificaciones
    clasificaciones_dir = os.path.join('static', 'clasificaciones')
    
    if not os.path.exists(clasificaciones_dir):
        logger.warning(f"El directorio {clasificaciones_dir} no existe. No hay datos para migrar.")
        return 0
    
    count = 0
    for filename in glob.glob(os.path.join(clasificaciones_dir, 'clasificacion_*.json')):
        try:
            # Extraer código de guía del nombre del archivo
            codigo_guia = os.path.basename(filename).replace('clasificacion_', '').replace('.json', '')
            
            # Leer el archivo JSON
            with open(filename, 'r', encoding='utf-8') as f:
                clasificacion_data = json.load(f)
            
            # Extraer datos relevantes
            fecha_clasificacion = clasificacion_data.get('fecha_registro')
            hora_clasificacion = clasificacion_data.get('hora_registro')
            
            # Obtener datos de la guía para el código de proveedor y nombre
            codigo_proveedor = None
            nombre_proveedor = None
            
            # Intentar obtener estos datos del archivo de guía
            guia_filename = os.path.join('static', 'guias', f'guia_{codigo_guia}.html')
            if os.path.exists(guia_filename):
                with open(guia_filename, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                soup = BeautifulSoup(html_content, 'html.parser')
                
                for row in soup.find_all('tr'):
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        label = cells[0].get_text().strip().lower()
                        value = cells[1].get_text().strip()
                        
                        if 'código de proveedor' in label:
                            codigo_proveedor = value
                        elif 'nombre de proveedor' in label:
                            nombre_proveedor = value
            
            # Preparar datos de clasificación
            clasificacion_manual = clasificacion_data.get('clasificacion_manual', {})
            clasificacion_automatica = clasificacion_data.get('clasificacion_automatica', {})
            
            # Combinar clasificaciones en un formato JSON
            clasificaciones = {
                'manual': clasificacion_manual,
                'automatica': clasificacion_automatica
            }
            
            # Preparar datos para almacenar
            datos_clasificacion = {
                'codigo_guia': codigo_guia,
                'codigo_proveedor': codigo_proveedor,
                'nombre_proveedor': nombre_proveedor,
                'fecha_clasificacion': fecha_clasificacion,
                'hora_clasificacion': hora_clasificacion,
                'clasificaciones': json.dumps(clasificaciones),
                'estado': 'activo'
            }
            
            # Almacenar en la base de datos
            if db_operations.store_clasificacion(datos_clasificacion):
                count += 1
                logger.info(f"Migrada clasificación para guía: {codigo_guia}")
            else:
                logger.error(f"Error al migrar clasificación para guía: {codigo_guia}")
        
        except Exception as e:
            logger.error(f"Error procesando archivo {filename}: {str(e)}")
    
    logger.info(f"Migración de clasificaciones completada. {count} registros migrados.")
    return count

def run_migration():
    """
    Ejecuta la migración completa de datos.
    """
    logger.info("Iniciando migración de datos a SQLite...")
    
    # Crear tablas si no existen
    db_schema.create_tables()
    
    # Migrar datos
    pesajes_bruto_count = migrate_pesajes_bruto()
    clasificaciones_count = migrate_clasificaciones()
    pesajes_neto_count = migrate_pesajes_neto()
    
    # Resumen
    logger.info("Migración completada:")
    logger.info(f"- Pesajes brutos: {pesajes_bruto_count} registros")
    logger.info(f"- Clasificaciones: {clasificaciones_count} registros")
    logger.info(f"- Pesajes netos: {pesajes_neto_count} registros")
    
    return {
        'pesajes_bruto': pesajes_bruto_count,
        'clasificaciones': clasificaciones_count,
        'pesajes_neto': pesajes_neto_count
    }

if __name__ == "__main__":
    run_migration() 