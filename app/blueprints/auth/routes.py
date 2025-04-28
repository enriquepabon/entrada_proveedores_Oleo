from flask import render_template, redirect, url_for, flash, request, current_app, session
from flask_login import login_user, logout_user, login_required, current_user
from . import bp
from .forms import RegistrationForm, LoginForm
from app.utils.auth_utils import create_user, get_user_by_username
# Importar check_password_hash para usar en la vista de login (Paso 6)
from werkzeug.security import check_password_hash

@bp.route('/register', methods=['GET', 'POST'])
def register():
    """Maneja el registro de nuevos usuarios."""
    form = RegistrationForm()
    if form.validate_on_submit():
        # El validador personalizado validate_username en forms.py ya verifica si existe
        # Crear usuario (la función create_user maneja el hash de la contraseña)
        if create_user(username=form.username.data, email=form.email.data, password=form.password.data):
            flash(f'Cuenta creada para {form.username.data}! Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
        else:
            # create_user devuelve False si hubo un error (ej. IntegrityError ya manejado)
            flash('Hubo un error al crear la cuenta. Inténtalo de nuevo.', 'danger')
            
    return render_template('register.html', title='Registro', form=form)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('entrada.home')) # O a donde quieras redirigir usuarios ya logueados
    
    form = LoginForm()

    if form.validate_on_submit():
        user = get_user_by_username(form.username.data)
        
        if user and check_password_hash(user.password_hash, form.password.data):
            if user.is_active: 
                login_user(user, remember=form.remember.data)
                flash('Inicio de sesión exitoso.', 'success')
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('entrada.home'))
            else:
                flash('Tu cuenta está pendiente de activación por un administrador.', 'warning')
                return redirect(url_for('auth.login'))
        else:
            flash('Inicio de sesión fallido. Verifica tu nombre de usuario/correo y contraseña.', 'danger')
            return redirect(url_for('auth.login'))

    return render_template('login.html', title='Iniciar Sesión', form=form)

@bp.route('/logout')
@login_required # Asegurar que el usuario esté logueado para poder desloguearse
def logout():
    """Maneja el cierre de sesión del usuario."""
    logout_user()
    flash('Has cerrado sesión exitosamente.', 'info')
    return redirect(url_for('auth.login')) 