import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template

# Configurar logging
logger = logging.getLogger(__name__)

class MiscUtils:
    def __init__(self, app):
        self.app = app
        
    def __init__(self, ...):
self.app = app
        self.ensure_directories()



    def format_date(self, ...):
for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            return datetime.strptime(fecha_str, fmt).strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")



    def get_codigo_from_data(self, ...):
for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Código':
                return row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
        return 'desconocido'



    def registrar_fecha_porteria(self, ...):
return datetime.now().strftime('%d/%m/%Y %H:%M')



    def get_ticket_date(self, ...):
for row in parsed_data.get('table_data', []):
            if row['campo'] == 'Fecha':
                fecha_str = row['original'] if row['sugerido'] == 'No disponible' else row['sugerido']
                try:
                    for fmt in ['%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                        try:
                            fecha_obj = datetime.strptime(fecha_str, fmt)
                            return fecha_obj.strftime("%d/%m/%Y")
                        except ValueError:
                            continue
                except Exception as e:
                    logger.error(f"Error parseando fecha: {str(e)}")
                    return fecha_str
        return datetime.now().strftime("%d/%m/%Y")



    def prepare_revalidation_data(self, ...):
revalidation_data = {}
        for row in parsed_data.get('table_data', []):
            campo = row['campo']
            valor = row['sugerido'] if row['sugerido'] != 'No disponible' else row['original']
            revalidation_data[campo] = valor

        if data:
            if data.get('Nombre'):
                revalidation_data['Nombre del Agricultor'] = data['Nombre']
            if data.get('Codigo'):
                revalidation_data['Código'] = data['Codigo']
            if data.get('Nota'):
                revalidation_data['nota'] = data['Nota']

        return revalidation_data



