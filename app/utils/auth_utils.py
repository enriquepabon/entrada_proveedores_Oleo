import sqlite3
import logging
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash
from app.models.user_model import User

logger = logging.getLogger(__name__)

def get_db_connection():
    """Establece conexión con la base de datos SQLite."""
    try:
        db_path = current_app.config['TIQUETES_DB_PATH']
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Devolver filas como diccionarios
        return conn
    except KeyError:
        logger.error("Error: 'TIQUETES_DB_PATH' no está configurada.")
        return None
    except sqlite3.Error as e:
        logger.error(f"Error conectando a la base de datos: {e}")
        return None

def ensure_users_schema_admin_column():
    """Asegura que la tabla users tenga la columna is_admin."""
    conn = get_db_connection()
    if not conn:
        logger.error("No se pudo conectar a la base de datos para verificar esquema de users.")
        return False
    try:
        cursor = conn.cursor()
        # Verificar si la columna is_admin existe
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        if 'is_admin' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            conn.commit()
            logger.info("Columna 'is_admin' añadida a la tabla 'users' con valor por defecto 0.")
        else:
            logger.info("Columna 'is_admin' ya existe en la tabla 'users'.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error al verificar/añadir columna 'is_admin' a 'users': {e}")
        return False
    finally:
        if conn:
            conn.close()

def get_user_by_id(user_id):
    """Obtiene un usuario por su ID."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password_hash, is_active, is_admin FROM users WHERE id = ?", (user_id,))
        user_data = cursor.fetchone()
        if user_data:
            admin_val = user_data['is_admin'] if 'is_admin' in user_data.keys() else 0
            return User(id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        password_hash=user_data['password_hash'],
                        is_active=user_data['is_active'],
                        is_admin=admin_val)
        return None
    except sqlite3.Error as e:
        logger.error(f"Error obteniendo usuario por ID {user_id}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_user_by_username(username):
    """Obtiene un usuario por su nombre de usuario."""
    conn = get_db_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, password_hash, is_active, is_admin FROM users WHERE username = ?", (username,))
        user_data = cursor.fetchone()
        if user_data:
            admin_val = user_data['is_admin'] if 'is_admin' in user_data.keys() else 0
            return User(id=user_data['id'],
                        username=user_data['username'],
                        email=user_data['email'],
                        password_hash=user_data['password_hash'],
                        is_active=user_data['is_active'],
                        is_admin=admin_val)
        return None
    except sqlite3.Error as e:
        logger.error(f"Error obteniendo usuario por username {username}: {e}")
        return None
    finally:
        if conn:
            conn.close()

def create_user(username, email, password):
    """Crea un nuevo usuario en la base de datos."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
            (username, email, password_hash)
        )
        conn.commit()
        logger.info(f"Usuario '{username}' creado exitosamente.")
        return True
    except sqlite3.IntegrityError:
        # Error común si el username o email ya existen (debido a UNIQUE constraint)
        logger.warning(f"Error al crear usuario: Username '{username}' o Email '{email}' ya existen.")
        conn.rollback()
        return False
    except sqlite3.Error as e:
        logger.error(f"Error creando usuario {username}: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# La función check_password puede estar aquí o ser llamada desde la ruta
# directamente sobre el objeto User obtenido, ya que el hash está en el objeto.
# Por simplicidad, la dejamos fuera por ahora, se usará así en la ruta:
# user = get_user_by_username(form_username)
# if user and check_password_hash(user.password_hash, form_password):
#    login_user(user) 

def get_all_users():
    """Obtiene todos los usuarios registrados."""
    conn = get_db_connection()
    if not conn:
        return []
    users = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, username, email, is_active, fecha_creacion FROM users ORDER BY fecha_creacion DESC")
        users_data = cursor.fetchall()
        for user_data in users_data:
            # Crear diccionarios simples en lugar de objetos User completos para la lista admin
            users.append({
                'id': user_data['id'],
                'username': user_data['username'],
                'email': user_data['email'],
                'is_active': bool(user_data['is_active']),
                'fecha_creacion': user_data['fecha_creacion']
            })
        return users
    except sqlite3.Error as e:
        logger.error(f"Error obteniendo todos los usuarios: {e}")
        return []
    finally:
        if conn:
            conn.close()

def activate_user(user_id):
    """Activa un usuario estableciendo is_active = 1."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
        conn.commit()
        logger.info(f"Usuario ID {user_id} activado.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error activando usuario ID {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def deactivate_user(user_id):
    """Desactiva un usuario estableciendo is_active = 0."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        logger.info(f"Usuario ID {user_id} desactivado.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error desactivando usuario ID {user_id}: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close() 