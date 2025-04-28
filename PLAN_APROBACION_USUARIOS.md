# Plan de Implementación: Aprobación de Usuarios

**Objetivo:** Modificar el sistema de autenticación de `TiquetesApp` para que los nuevos usuarios puedan registrarse, pero requieran la activación manual por parte de un administrador antes de poder iniciar sesión y acceder a las funciones protegidas.

**Metodología:**

1.  **Extender el Modelo de Usuario:** Añadiremos un campo `is_active` a la tabla `users` en la base de datos.
2.  **Actualizar Creación:** Los nuevos usuarios se crearán con `is_active` establecido en `False` (o `0`).
3.  **Modificar Login:** La función de inicio de sesión verificará el estado `is_active` además de la contraseña.
4.  **Crear Interfaz de Administración:** Se desarrollará una nueva sección dentro del blueprint `admin` para listar usuarios y permitir la activación/desactivación.
5.  **Seguridad:** Protegeremos adecuadamente la nueva interfaz de administración. *(Nota: Por ahora, asumiremos que cualquier usuario logueado puede acceder a la administración. La implementación de roles específicos de 'administrador' podría ser un paso futuro).*

**Recursos:**

*   Archivos a Modificar: `db_schema.py`, `app/utils/auth_utils.py`, `app/blueprints/auth/routes.py`, `app/blueprints/admin/routes.py`.
*   Nuevos Archivos: `app/templates/admin/manage_users.html` (plantilla para administrar usuarios).

**Instrucciones Generales:**

*   Seguiremos los pasos secuencialmente.
*   Realizaremos pruebas después de cada paso lógico.
*   Actualizaremos `requirements.txt` si se añaden nuevas dependencias (aunque no se esperan para este plan).

---

## Pasos Detallados:

**Paso 1: Modificar Esquema de Base de Datos**

*   **Acción:** Añadir la columna `is_active` a la tabla `users`.
*   **Código (`db_schema.py`):**
    *   Modificar `CREATE_USERS_TABLE` para incluir la nueva columna:
      ```sql
      CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          is_active INTEGER DEFAULT 0,  -- 0 para False, 1 para True
          fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      );
      ```
    *   Dentro de la función `create_tables()` (o la función que uses para actualizar esquemas), añadir una llamada a `add_column_if_not_exists` (o lógica similar) para agregar la columna `is_active INTEGER DEFAULT 0` a la tabla `users` si aún no existe.
*   **Ejecución:** Reiniciar la aplicación Flask para que `create_tables()` se ejecute y actualice el esquema de la base de datos `tiquetes.db`.

**Paso 2: Modificar Creación de Usuario**

*   **Acción:** Asegurar que los nuevos usuarios se creen como inactivos.
*   **Código (`app/utils/auth_utils.py` - función `create_user`):**
    *   Revisar la sentencia `INSERT` dentro de `create_user`. Asegurarse de que *no* intente establecer `is_active` o que lo establezca explícitamente en `0`. El `DEFAULT 0` definido en el esquema debería encargarse de esto si la columna no se menciona en el `INSERT`, pero es bueno verificar.
    *   *(No debería ser necesario cambiar el código si se confía en el DEFAULT 0 del esquema, pero es una buena práctica revisar).*

**Paso 3: Modificar Lógica de Login**

*   **Acción:** Impedir el inicio de sesión a usuarios inactivos.
*   **Código (`app/blueprints/auth/routes.py` - función `login`):**
    *   Localizar el bloque `if user and check_password_hash(user.password_hash, form.password.data):`.
    *   Añadir una condición para verificar `user.is_active`:
      ```python
      if user and check_password_hash(user.password_hash, form.password.data):
          if user.is_active: # <--- NUEVA COMPROBACIÓN
              login_user(user, remember=form.remember.data)
              flash('Inicio de sesión exitoso.', 'success')
              next_page = request.args.get('next')
              return redirect(next_page) if next_page else redirect(url_for('entrada.home'))
          else:
              flash('Tu cuenta está pendiente de activación por un administrador.', 'warning')
      else:
          flash('Inicio de sesión fallido. Verifica tu nombre de usuario/correo y contraseña.', 'danger')
      # Si llega aquí (contraseña incorrecta, usuario no activo, o usuario no encontrado)
      return render_template('login.html', title='Iniciar Sesión', form=form)
      ```
    *   **Importante:** Modificar la clase `User` en `app/models/user_model.py` (o donde esté definida) para que tenga el atributo `is_active`. Flask-Login no lo añade automáticamente.
        ```python
        from flask_login import UserMixin

        class User(UserMixin):
            def __init__(self, id, username, email, password_hash, is_active): # Añadir is_active
                self.id = id
                self.username = username
                self.email = email
                self.password_hash = password_hash
                self.is_active = bool(is_active) # Convertir a booleano
            # ... (métodos set_password, check_password) ...

            # Flask-Login necesita este método
            @property
            def active(self):
                 return self.is_active
        ```
    *   Asegurarse de que la función `load_user` (y las funciones `get_user_by_id`, `get_user_by_username`) recuperen y pasen el valor `is_active` al crear el objeto `User`.

**Paso 4: Crear Interfaz de Administración de Usuarios**

*   **Acción:** Crear las rutas, funciones de base de datos y plantilla para gestionar usuarios.
*   **Código (Nuevas funciones en `app/utils/auth_utils.py`):**
    *   `get_all_users()`: Ejecuta `SELECT id, username, email, is_active FROM users ORDER BY fecha_creacion DESC` y devuelve una lista de diccionarios o objetos `User`.
    *   `activate_user(user_id)`: Ejecuta `UPDATE users SET is_active = 1 WHERE id = ?`.
    *   `deactivate_user(user_id)`: Ejecuta `UPDATE users SET is_active = 0 WHERE id = ?`.
*   **Código (Nuevas rutas en `app/blueprints/admin/routes.py`):**
    *   Importar `get_all_users`, `activate_user`, `deactivate_user`.
    *   Crear ruta `/admin/users` (GET):
        *   Proteger con `@login_required`.
        *   Llamar a `get_all_users()`.
        *   Renderizar `admin/manage_users.html` pasando la lista de usuarios.
    *   Crear ruta `/admin/activate_user/<int:user_id>` (POST):
        *   Proteger con `@login_required`.
        *   Llamar a `activate_user(user_id)`.
        *   Mostrar flash de éxito.
        *   Redirigir a `/admin/users`.
    *   Crear ruta `/admin/deactivate_user/<int:user_id>` (POST):
        *   Proteger con `@login_required`.
        *   Llamar a `deactivate_user(user_id)`.
        *   Mostrar flash de éxito.
        *   Redirigir a `/admin/users`.
*   **Código (Nueva plantilla `app/templates/admin/manage_users.html`):**
    *   Heredar de `base.html`.
    *   Mostrar una tabla con columnas: Username, Email, Estado (Activo/Pendiente).
    *   Para cada usuario, añadir un botón "Activar" (si está inactivo) o "Desactivar" (si está activo).
    *   Estos botones deben estar dentro de un `<form>` que haga POST a la ruta de activación/desactivación correspondiente, pasando el `user_id`.

**Paso 5: Pruebas**

*   **Acción:** Probar exhaustivamente el nuevo flujo de aprobación.
*   **Verificación:**
    *   Registrar un nuevo usuario.
    *   Intentar iniciar sesión con él (debe fallar indicando pendiente).
    *   Iniciar sesión como administrador (el primer usuario que creaste o uno designado).
    *   Navegar a `/admin/users`. Verificar que el nuevo usuario aparezca como pendiente.
    *   Hacer clic en "Activar" para ese usuario. Verificar el mensaje flash y que el estado cambie en la tabla.
    *   Cerrar sesión.
    *   Iniciar sesión con el usuario recién activado (debe funcionar).
    *   Volver a `/admin/users` como administrador.
    *   Desactivar el usuario.
    *   Cerrar sesión.
    *   Intentar iniciar sesión con el usuario desactivado (debe fallar indicando pendiente o error). 