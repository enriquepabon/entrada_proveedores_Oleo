# Refactorización de TiquetesApp

## Estructura del Proyecto Refactorizado

La aplicación ha sido refactorizada para seguir una estructura modular basada en blueprints de Flask. Esta nueva estructura mejora la organización del código, facilita el mantenimiento y permite un desarrollo más ágil.

```
TiquetesApp/
├── app/
│   ├── __init__.py                 # Inicialización de la app
│   ├── run.py                      # Punto de entrada
│   ├── blueprints/                 # Módulos por funcionalidad
│   │   ├── __init__.py
│   │   ├── entrada/                # Registro de entrada
│   │   │   ├── __init__.py
│   │   │   ├── routes.py           
│   │   ├── pesaje/                 # Pesaje bruto y tara
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   ├── clasificacion/          # Clasificación manual/automática
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   ├── pesaje_neto/            # Pesaje neto
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   ├── salida/                 # Registro de salida
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   ├── admin/                  # Rutas administrativas
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   │   ├── api/                    # Endpoints API
│   │   │   ├── __init__.py
│   │   │   ├── routes.py
│   ├── utils/                      # Funciones utilitarias
│   │   ├── __init__.py
│   │   ├── common.py               # Utilidades comunes
│   │   ├── pdf_generator.py        # Generación de PDFs
│   │   ├── image_processing.py     # Procesamiento de imágenes
│   ├── models/                     # Modelos de datos
│   │   ├── __init__.py
├── templates/                      # Templates HTML
├── static/                         # Archivos estáticos
├── config.py                       # Configuración
├── db_schema.py                    # Esquema de base de datos
├── db_operations.py                # Operaciones de base de datos
├── data_access.py                  # Capa de acceso a datos
├── data_helper.py                  # Funciones auxiliares para datos
```

## Proceso de Migración

La migración desde el archivo monolítico `apptiquetes.py` a la estructura modular se realizó siguiendo estos pasos:

1. **Análisis del código original**: Se identificaron las diferentes funcionalidades y se categorizaron las rutas.
2. **Creación de blueprints**: Se crearon blueprints para cada área funcional de la aplicación.
3. **Migración de rutas**: Se trasladaron las rutas a sus respectivos blueprints, adaptando las referencias a `url_for`.
4. **Refactorización de utilidades**: Se separaron las funciones utilitarias en módulos específicos.
5. **Pruebas**: Se verificó que todas las funcionalidades siguieran operando correctamente.

## Beneficios de la Refactorización

- **Mejor organización**: Código agrupado por funcionalidad, facilitando la navegación y comprensión.
- **Mantenimiento simplificado**: Cambios en una funcionalidad no afectan a otras áreas.
- **Desarrollo paralelo**: Diferentes desarrolladores pueden trabajar en distintos blueprints simultáneamente.
- **Escalabilidad**: Facilita la adición de nuevas funcionalidades sin afectar el código existente.
- **Testabilidad**: Estructura modular que facilita la implementación de pruebas unitarias.

## Cómo Ejecutar la Aplicación

Para ejecutar la aplicación refactorizada:

```bash
# Desde el directorio raíz del proyecto
python app/run.py
```

## Notas para Desarrolladores

- Los blueprints están organizados por dominio funcional, no por tipo de operación.
- Las utilidades comunes se encuentran en el módulo `app.utils`.
- La configuración sigue estando centralizada en `config.py`.
- Se mantiene compatibilidad con la estructura de archivos JSON existente.

## Próximos Pasos

1. Completar la migración de todas las rutas a sus respectivos blueprints.
2. Refactorizar las funciones utilitarias para eliminar código duplicado.
3. Implementar pruebas unitarias para cada blueprint.
4. Mejorar la documentación de cada módulo.
5. Optimizar consultas a la base de datos. 