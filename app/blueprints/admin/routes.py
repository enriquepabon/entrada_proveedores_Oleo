from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.admin import bp
from app.utils.common import CommonUtils as Utils

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/admin/migrar-registros')
def migrar_registros():
    """
    Ruta administrativa para migrar registros de entrada a la base de datos.
    """
    try:
        # Importar la función de migración
        from migrate_records import migrate_entry_records
        
        # Ejecutar la migración
        result = migrate_entry_records()
        
        if result:
            return render_template('admin/resultado_operacion.html', 
                                   titulo="Migración de Registros", 
                                   mensaje="Migración de registros completada correctamente. Consulte los logs para más detalles.",
                                   exito=True)
        else:
            return render_template('admin/resultado_operacion.html', 
                                   titulo="Migración de Registros", 
                                   mensaje="Error en la migración de registros. Consulte los logs para más detalles.",
                                   exito=False)
    except Exception as e:
        logger.error(f"Error en migración de registros: {str(e)}")
        return render_template('error.html', mensaje=f"Error en migración de registros: {str(e)}")



