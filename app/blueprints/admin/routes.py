from flask import render_template, request, redirect, url_for, session, jsonify, flash, send_file, make_response
import os
import logging
import traceback
from datetime import datetime
import json
from app.blueprints.admin import bp
from app.utils.common import CommonUtils as Utils
# Importar login_required
from flask_login import login_required
# --- NUEVO: Importar funciones de auth_utils ---
from app.utils.auth_utils import get_all_users, activate_user, deactivate_user

# Configurar logging
logger = logging.getLogger(__name__)

@bp.route('/admin/migrar-registros')
@login_required # Añadir protección
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

# --- NUEVO: Rutas para gestión de usuarios ---
@bp.route('/users')
@login_required
def manage_users():
    """Muestra la página de gestión de usuarios."""
    try:
        users = get_all_users()
        # Crear directorio de templates si no existe
        admin_template_dir = os.path.join(current_app.root_path, 'templates', 'admin')
        os.makedirs(admin_template_dir, exist_ok=True)
        return render_template('admin/manage_users.html', users=users, title="Gestionar Usuarios")
    except Exception as e:
        logger.error(f"Error al cargar la página de gestión de usuarios: {e}")
        flash('Error al cargar la lista de usuarios.', 'danger')
        return redirect(url_for('entrada.home')) # O a una página de admin principal

@bp.route('/activate_user/<int:user_id>', methods=['POST'])
@login_required
def activate_user_route(user_id):
    """Activa un usuario."""
    # Aquí podrías añadir una verificación de rol si tuvieras roles implementados
    if activate_user(user_id):
        flash('Usuario activado correctamente.', 'success')
    else:
        flash('Error al activar el usuario.', 'danger')
    return redirect(url_for('admin.manage_users'))

@bp.route('/deactivate_user/<int:user_id>', methods=['POST'])
@login_required
def deactivate_user_route(user_id):
    """Desactiva un usuario."""
    # Aquí podrías añadir una verificación de rol
    if deactivate_user(user_id):
        flash('Usuario desactivado correctamente.', 'warning')
    else:
        flash('Error al desactivar el usuario.', 'danger')
    return redirect(url_for('admin.manage_users'))
# --- FIN NUEVO ---



