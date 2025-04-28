from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError
from app.utils.auth_utils import get_user_by_username # Para validación personalizada

class RegistrationForm(FlaskForm):
    """Formulario para el registro de nuevos usuarios."""
    username = StringField('Nombre de Usuario', 
                           validators=[DataRequired(), Length(min=4, max=25)])
    email = StringField('Correo Electrónico', 
                        validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', 
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrarse')

    # Validación personalizada para asegurar que el username no esté ya en uso
    def validate_username(self, username):
        user = get_user_by_username(username.data)
        if user:
            raise ValidationError('Ese nombre de usuario ya está en uso. Por favor, elige otro.')

    # Validación personalizada para asegurar que el email no esté ya en uso
    def validate_email(self, email):
        # Necesitaríamos una función get_user_by_email en auth_utils.py para esto
        # Por ahora, asumimos que el username es el identificador principal
        # Si se requiere validar email único, añadiremos get_user_by_email
        pass 

class LoginForm(FlaskForm):
    """Formulario para el inicio de sesión de usuarios."""
    # Se puede usar email o username para iniciar sesión
    username = StringField('Nombre de Usuario o Correo', validators=[DataRequired()]) 
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember = BooleanField('Recordarme')
    submit = SubmitField('Iniciar Sesión') 

    # --- TEMPORAL: Desactivar CSRF para diagnóstico --- # <-- Eliminar/Comentar
    # class Meta:                                         # <-- Eliminar/Comentar
    #     csrf = False                                    # <-- Eliminar/Comentar
    # --- FIN TEMPORAL ---                                # <-- Eliminar/Comentar 