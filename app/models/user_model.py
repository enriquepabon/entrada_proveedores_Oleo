from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin):
    """Modelo de usuario para la autenticación."""
    def __init__(self, id, username, email, password_hash, is_active=True):
        self.id = id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        # Almacenar el estado internamente para evitar conflicto con la propiedad de UserMixin
        self._db_is_active = bool(is_active)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Flask-Login busca esta propiedad
    @property
    def is_active(self):
        """Propiedad requerida por Flask-Login."""
        return self._db_is_active

    # UserMixin ya proporciona los métodos requeridos por Flask-Login:
    # is_authenticated, is_anonymous, get_id() 
    # (Eliminamos la propiedad @property def active(self) que era redundante) 