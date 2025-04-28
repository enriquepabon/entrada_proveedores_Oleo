# Plan de Implementación de Autenticación con Flask-Login (Adaptado)

**Objetivo:** Integrar un sistema de autenticación de usuarios en la aplicación Flask (`TiquetesApp`) utilizando la librería `Flask-Login` y la base de datos SQLite existente (`tiquetes.db`), siguiendo las prácticas actuales del proyecto.

**Recursos:**
*   Librería: `Flask-Login`
*   Base de Datos: SQLite (`tiquetes.db` accedida vía módulo `sqlite3`)
*   Hashing Contraseñas: `Werkzeug` (ya es dependencia de Flask)
*   Formularios: `Flask-WTF` (se instalará)
*   Documentación de referencia: [https://flask-login.readthedocs.io/](https://flask-login.readthedocs.io/)
*   Archivos Clave a Modificar: `app/__init__.py`, `db_schema.py`, `templates/base.html`, y creación de nuevos módulos/archivos para autenticación.

**Instrucciones Generales:**
1.  Revisa cada paso del plan adaptado.
2.  Ejecuta las acciones descritas en cada paso en tu entorno local.
3.  Confirma que el paso se completó correctamente antes de solicitar proceder al siguiente.
4.  **Importante:** Después de instalar nuevas librerías (como en el Paso 1), actualizaremos el archivo `requirements.txt` para reflejar las nuevas dependencias.
5.  **Despliegue:** Ten presente que el objetivo final es desplegar en PythonAnywhere. Asegúrate de que los cambios funcionen allí y que las dependencias se instalen correctamente (`pip install -r requirements.txt` en la consola de PythonAnywhere).
6.  Si encuentras algún problema o tienes una estructura preferida (ej. dónde ubicar modelos/utils de auth), házmelo saber.

---

## Pasos Detallados (Adaptados):

**Paso 1: Instalación y Configuración Inicial**

*   **Acción:** Instalar `Flask-Login` y `Flask-WTF`. Configurar la extensión `LoginManager` en la fábrica de la aplicación y asegurar que exista una `SECRET_KEY`.
*   **Comandos:**
    ```bash
    pip install Flask-Login Flask-WTF
    pip freeze > requirements.txt  # Actualizar requirements
    ```
    *(Nota: `Werkzeug` ya debería estar instalado como dependencia de Flask).*
*   **Código (`app/__init__.py`):**
    *   Importar `LoginManager`.
    *   Instanciar `login_manager = LoginManager()`.
    *   Inicializarlo con la app: `login_manager.init_app(app)`.
    *   Asegurar que `app.config['SECRET_KEY']` esté definida (esencial para sesiones). Si no existe, añadirla (preferiblemente cargada desde variables de entorno o `config.py`).
    *   Configurar la vista de login: `login_manager.login_view = 'auth.login'` (el endpoint 'auth.login' se creará en pasos posteriores).

**Paso 2: Modelo de Usuario y Utils de Autenticación**

*   **Acción:** Definir una clase `User` que represente a los usuarios y herede de `UserMixin` de `Flask-Login`. Crear funciones de utilidad para interactuar con la tabla de usuarios en `tiquetes.db` usando `sqlite3`.
*   **Código:**
    *   Crear un nuevo archivo, por ejemplo, `app/models/user_model.py` (o `app/utils/auth_utils.py` si prefieres mantenerlo en utils).
    *   Definir la clase `User(UserMixin)` con atributos como `id`, `username`, `email`, `password_hash`.
    *   Implementar métodos en la clase o funciones de utilidad separadas (ej. en `app/utils/auth_utils.py`) para:
        *   `set_password(password)`: Genera un hash de la contraseña usando `generate_password_hash` de `werkzeug.security`.
        *   `check_password(password)`: Verifica una contraseña contra el hash usando `check_password_hash` de `werkzeug.security`.
        *   `get_user_by_id(user_id)`: Obtiene un usuario de `tiquetes.db` por su ID usando `sqlite3`.
        *   `get_user_by_username(username)`: Obtiene un usuario por su nombre de usuario usando `sqlite3`.
        *   `create_user(...)`: Inserta un nuevo usuario en la tabla `users` de `tiquetes.db` usando `sqlite3`.

**Paso 3: Función `load_user`**

*   **Acción:** Implementar la función `load_user` requerida por `Flask-Login` para cargar un usuario desde la sesión, utilizando la función de utilidad creada en el Paso 2.
*   **Código (en `app/__init__.py` o cerca del modelo `User`):**
    *   Importar la función `get_user_by_id` (del Paso 2).
    *   Definir la función:
      ```python
      @login_manager.user_loader
      def load_user(user_id):
          # Llamar a la función que usa sqlite3 para obtener el usuario
          return get_user_by_id(int(user_id))
      ```

**Paso 4: Formularios de Login y Registro**

*   **Acción:** Crear formularios `FlaskForm` (usando `Flask-WTF`) para el inicio de sesión (`LoginForm`) y el registro (`RegistrationForm`).
*   **Código:**
    *   Crear un archivo `app/blueprints/auth/forms.py` (o similar).
    *   Importar `FlaskForm`, `StringField`, `PasswordField`, `SubmitField`, `validators` de `wtforms`.
    *   Definir `RegistrationForm` con campos para username, email, password, confirm password, y submit. Incluir validadores (`DataRequired`, `Email`, `EqualTo`, `Length`).
    *   Definir `LoginForm` con campos para username (o email), password, remember_me (BooleanField), y submit.

**Paso 5: Blueprint y Rutas de Autenticación (Registro)**

*   **Acción:** Crear un nuevo Blueprint para la autenticación (`auth`). Implementar la ruta y la vista para el registro de usuarios, utilizando el formulario y las funciones de utilidad de base de datos.
*   **Código:**
    *   Crear directorio `app/blueprints/auth/`.
    *   Crear `app/blueprints/auth/__init__.py` para definir el Blueprint: `bp = Blueprint('auth', __name__, template_folder='templates')`.
    *   Crear `app/blueprints/auth/routes.py`.
    *   Importar `Blueprint`, `render_template`, `redirect`, `url_for`, `flash`, el formulario `RegistrationForm` y las funciones de utilidad `create_user`, `get_user_by_username`.
    *   Definir la vista `register()`:
        *   Aceptar métodos GET y POST.
        *   Crear instancia de `RegistrationForm`.
        *   Si el formulario es válido en POST:
            *   Verificar si el usuario ya existe (usando `get_user_by_username`).
            *   Si no existe, crear el usuario (usando `create_user`, asegurándose de hashear la contraseña).
            *   Mostrar mensaje flash y redirigir a login.
        *   Renderizar la plantilla de registro pasando el formulario.
    *   Crear la plantilla `app/templates/auth/register.html` que renderice el `RegistrationForm`.
    *   Registrar el Blueprint en `app/__init__.py`: `from app.blueprints.auth import bp as auth_bp; app.register_blueprint(auth_bp, url_prefix='/auth')`.

**Paso 6: Rutas de Autenticación (Login y Logout)**

*   **Acción:** Implementar las vistas para el inicio de sesión (`login`) y cierre de sesión (`logout`) en el blueprint `auth`.
*   **Código (`app/blueprints/auth/routes.py`):**
    *   Importar `login_user`, `logout_user`, `login_required` de `flask_login`, y el formulario `LoginForm`.
    *   Definir la vista `login()`:
        *   Aceptar métodos GET y POST.
        *   Crear instancia de `LoginForm`.
        *   Si el formulario es válido en POST:
            *   Obtener el usuario (usando `get_user_by_username`).
            *   Verificar si el usuario existe y la contraseña es correcta (usando `check_password`).
            *   Si es válido, llamar a `login_user(user, remember=form.remember_me.data)`.
            *   Redirigir a la página principal (ej. `entrada.home`) o a la página solicitada originalmente (`next` page).
            *   Si no es válido, mostrar mensaje flash de error.
        *   Renderizar la plantilla de login pasando el formulario.
    *   Definir la vista `logout()`:
        *   Añadir decorador `@login_required`.
        *   Llamar a `logout_user()`.
        *   Mostrar mensaje flash y redirigir a la página de inicio (ej. `auth.login` o `entrada.home`).
    *   Crear la plantilla `app/templates/auth/login.html` que renderice el `LoginForm`.
    *   **Modificar `templates/base.html`:** Añadir lógica condicional para mostrar enlaces de "Login"/"Registro" o "Logout" en la barra de navegación, usando `current_user.is_authenticated`.

**Paso 7: Protección de Rutas**

*   **Acción:** Proteger las vistas existentes que requieran autenticación usando el decorador `@login_required`.
*   **Código (en los archivos `routes.py` de los blueprints correspondientes, ej. `app/blueprints/entrada/routes.py`):**
    *   Importar `login_required` de `flask_login`.
    *   Añadir el decorador `@login_required` justo debajo del decorador `@bp.route(...)` para las vistas que necesiten protección (ej. `ver_registro_entrada`, `lista_entradas`, `dashboard`, etc.).
    *   *Recordatorio: `login_manager.login_view` ya se configuró en el Paso 1 para redirigir a los usuarios no autenticados.*

**Paso 8: Creación de Tabla de Usuarios**

*   **Acción:** Añadir la definición de la tabla `users` al archivo `db_schema.py` y asegurarse de que la función que crea/actualiza el esquema (`create_tables()` o similar) la incluya.
*   **Código (`db_schema.py`):**
    *   Añadir una constante `CREATE_USERS_TABLE` con el SQL:
      ```sql
      CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      ```
    *   Asegurarse de que la función `create_tables()` (o la que uses para inicializar/actualizar el esquema) ejecute `cursor.execute(CREATE_USERS_TABLE)`.
    *   Ejecutar el script o la función que actualiza el esquema para crear la tabla en `tiquetes.db`.

**Paso 9: Pruebas**

*   **Acción:** Probar exhaustivamente todo el flujo: registro de nuevos usuarios, inicio de sesión con credenciales correctas e incorrectas, funcionalidad "recordarme", cierre de sesión, acceso a rutas protegidas (debería redirigir a login si no está autenticado) y acceso a rutas no protegidas.
*   **Verificación:** Asegurarse de que solo los usuarios autenticados puedan acceder a las rutas protegidas con `@login_required` y que las redirecciones funcionen como se espera.

---

Este plan actualizado se alinea mejor con la estructura y el uso de `sqlite3` en tu proyecto. Por favor, revísalo. Si estás de acuerdo, podemos comenzar con el **Paso 1 (Adaptado): Instalación y Configuración Inicial**. 