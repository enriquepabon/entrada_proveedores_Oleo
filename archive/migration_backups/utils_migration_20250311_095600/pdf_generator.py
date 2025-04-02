import os
import logging
import traceback
from datetime import datetime
import json
from flask import current_app, render_template

# Configurar logging
logger = logging.getLogger(__name__)

class Pdf_generatorUtils:
    def __init__(self, app):
        self.app = app
        
    def generate_pdf(self, ...):
try:
            now = datetime.now()
            
            # Extraer datos del webhook response
            data = {}
            if 'webhook_response' in session and session['webhook_response'].get('data'):
                webhook_data = session['webhook_response']['data']
                data = {
                    'codigo': webhook_data.get('codigo', ''),
                    'nombre_agricultor': webhook_data.get('nombre_agricultor', ''),
                    'racimos': webhook_data.get('racimos', ''),
                    'placa': webhook_data.get('placa', ''),
                    'acarreo': webhook_data.get('acarreo', 'No'),
                    'cargo': webhook_data.get('cargo', 'No'),
                    'transportador': webhook_data.get('transportador', 'No registrado'),
                    'fecha_tiquete': webhook_data.get('fecha_tiquete', ''),
                    'nota': webhook_data.get('nota', '')
                }
            else:
                logger.warning("No se encontró webhook_response en la sesión")
                return None

            # Obtener el QR filename de la sesión
            qr_filename = session.get('qr_filename')
            if not qr_filename:
                # Si no hay QR filename, crear uno predeterminado
                qr_filename = f"default_qr_{now.strftime('%Y%m%d%H%M%S')}.png"
                try:
                    # Generar un QR simple con el código de guía
                    codigo = data.get('codigo', 'unknown')
                

