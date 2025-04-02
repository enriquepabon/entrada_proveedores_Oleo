from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.api import bp
from utils import Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/test_webhook', methods=['GET'])
def test_webhook():
    """
    Ruta de prueba para verificar la conectividad con el webhook.
    """
    try:
        response = requests.get(PROCESS_WEBHOOK_URL)
        return jsonify({
            "status": "webhook accessible" if response.status_code == 200 else "webhook error",
            "status_code": response.status_code,
            "response": response.text
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        })



@bp.route('/test_revalidation', methods=['GET'])
def test_revalidation():
    test_payload = {
        "modificaciones": [
            {
                "campo": "Nombre del Agricultor",
                "valor_anterior": "Test Nombre",
                "valor_modificado": "Test Modificado"
            }
        ]
    }
    
    try:
        response = requests.post(
            REVALIDATION_WEBHOOK_URL,
            json=test_payload,
            headers={'Content-Type': 'application/json'}
        )
        
        return jsonify({
            "status": response.status_code,
            "response": response.text,
            "sent_payload": test_payload
        })
    except Exception as e:
        return jsonify({"error": str(e)})



@bp.route('/verificar_placa', methods=['POST'])
def verificar_placa():
    """
    Procesa una imagen para verificar si la placa detectada coincide con la placa registrada.
    """
    try:
        logger.info("Iniciando verificación de placa")
        
        if 'foto' not in request.files:
            logger.warning("No se encontró imagen en la solicitud")
            return jsonify({
                'success': False,
                'message': 'No se encontró imagen para verificar'
            })
        
        foto = request.files['foto']
        placa_registrada = request.form.get('placa_registrada', '').strip().upper()
        
        if not placa_registrada:
            logger.warning("No hay placa registrada para comparar")
            return jsonify({
                'success': False,
                'message': 'No hay placa registrada para comparar'
            })
        
        if not foto.filename:
            logger.warning("El archivo de imagen está vacío")
            return jsonify({
                'success': False,
                'message': 'El archivo de imagen está vacío'
            })
        
        if not allowed_file(foto.filename):
            logger.warning(f"Tipo de archivo no permitido: {foto.filename}")
            return jsonify({
                'success': False,
                'message': 'Tipo de archivo no permitido'
            })
        
        # Guardar la imagen temporalmente
        filename = secure_filename(f"verificacion_placa_{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        foto.save(temp_path)
        
        logger.info(f"Imagen guardada temporalmente: {temp_path}")
        
        # Enviar la imagen al webhook para procesamiento
        result = process_plate_image(temp_path, filename)
        
        if result.get("result") != "ok":
            logger.warning(f"Error al procesar la placa: {result.get('message')}")
            return jsonify({
                'success': False,
                'message': f"Error al detectar la placa: {result.get('message')}"
            })
        
        # Obtener el texto de la placa detectada
        placa_detectada = result.get("plate_text", "").strip().upper()
        
        if not placa_detectada:
            logger.warning("No se pudo detectar el texto de la placa")
            return jsonify({
                'success': False,
                'message': 'No se pudo detectar el texto de la placa'
            })
        
        # Comparar la placa detectada con la registrada
        # Normalizamos ambas placas para una comparación más flexible
        placa_registrada_norm = ''.join(c for c in placa_registrada if c.isalnum())
        placa_detectada_norm = ''.join(c for c in placa_detectada if c.isalnum())
        
        # Verificar si las placas coinciden
        coincide = placa_registrada_norm == placa_detectada_norm
        
        logger.info(f"Resultado de verificación: Placa registrada: {placa_registrada}, Placa detectada: {placa_detectada}, Coincide: {coincide}")
        
        return jsonify({
            'success': True,
            'placa_detectada': placa_detectada,
            'placa_registrada': placa_registrada,
            'coincide': coincide
        })
        
    except Exception as e:
        logger.error(f"Error en verificación de placa: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'Error al procesar la imagen: {str(e)}'
        })



