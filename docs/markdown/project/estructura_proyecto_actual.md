# Estructura Actual del Proyecto TiquetesApp

## 1. Organización General

El proyecto ha sido refactorizado utilizando la arquitectura de blueprints de Flask, permitiendo una mejor organización y separación de responsabilidades.

### 1.1 Estructura de Directorios Principal

```
TiquetesApp/
├── app/                      # Directorio principal de la aplicación
│   ├── __init__.py           # Configuración e inicialización de la app Flask
│   ├── models/               # Modelos de datos (actualmente poco utilizados)
│   ├── utils/                # Utilidades generales
│   ├── blueprints/           # Módulos funcionales (blueprints)
│       ├── entrada/          # Funcionalidad de registro de entrada
│       ├── pesaje/           # Funcionalidad de pesaje
│       ├── clasificacion/    # Funcionalidad de clasificación
│       ├── misc/             # Funcionalidades misceláneas
│       ├── admin/            # Funcionalidades de administración
│       ├── api/              # Endpoints de API
│       └── salida/           # Funcionalidad de registro de salida
├── static/                   # Archivos estáticos (CSS, JS, imágenes)
│   ├── uploads/              # Imágenes subidas por usuarios
│   ├── pdfs/                 # PDFs generados
│   ├── guias/                # Archivos de guías
│   └── images/               # Imágenes del sistema
├── templates/                # Plantillas HTML
├── scripts/                  # Scripts de utilidades y migración
├── venv/                     # Entorno virtual (no incluido en control de versiones)
├── data/                     # Datos persistentes (JSONs, SQLite DB)
└── run.py                    # Punto de entrada de la aplicación
```

### 1.2 Estructura de un Blueprint

Cada blueprint sigue una estructura similar:

```
blueprints/nombre_blueprint/
├── __init__.py               # Inicialización del blueprint
├── routes.py                 # Definición de rutas y controladores
├── forms.py                  # Formularios (opcional)
└── utils.py                  # Utilidades específicas del blueprint (opcional)
```

## 2. Flujos Principales y Rutas

### 2.1 Entrada de Proveedores

- **Blueprint**: `entrada`
- **Rutas principales**:
  - `/index`: Página de subida de imágenes de tiquetes
  - `/home`: Dashboard principal
  - `/processing`: Procesamiento de imágenes
  - `/review`: Revisión de datos extraídos
  - `/register`: Registro de datos
  - `/registros-entrada`: Lista de registros

### 2.2 Pesaje

- **Blueprint**: `pesaje`
- **Rutas principales**:
  - `/pesaje/<codigo>`: Página de pesaje
  - `/pesaje-inicial/<codigo>`: Pesaje bruto inicial
  - `/pesaje-tara/<codigo>`: Pesaje de tara
  - `/pesajes`: Lista de pesajes

### 2.3 Clasificación

- **Blueprint**: `clasificacion`
- **Rutas principales**:
  - `/clasificacion/<codigo>`: Página de clasificación
  - `/registrar_clasificacion`: Registro de clasificación
  - `/clasificaciones/lista`: Lista de clasificaciones

### 2.4 Misceláneos

- **Blueprint**: `misc`
- **Rutas principales**:
  - `/guias/<filename>`: Servir archivos de guías
  - `/`: Ruta raíz (upload_file)
  - `/revalidation_results`: Resultados de revalidación
  - `/revalidation_success`: Éxito de revalidación

### 2.5 API

- **Blueprint**: `api`
- **Rutas principales**:
  - `/api/test_webhook`: Testing de webhooks
  - `/api/verificar_placa`: Verificación de placas

## 3. Problemas Actuales y Soluciones

### 3.1 Problemas Resueltos

1. **Problemas de indentación**: Se corrigieron problemas de indentación en `routes.py` mediante scripts.
2. **Referencias a endpoints sin prefijos de blueprint**: Se actualizaron las plantillas para usar los prefijos correctos.
3. **Inicialización de Utils fuera del contexto de aplicación**: Se modificó para inicializar dentro del contexto de la aplicación.

### 3.2 Problemas Pendientes

1. **Falta de clave secreta**: Se detectó el error "The session is unavailable because no secret key was set" al intentar usar `session.clear()`. Es necesario configurar `app.secret_key` en `app/__init__.py`.

2. **Referencias a rutas en plantillas**: Algunas plantillas pueden tener referencias a rutas sin los prefijos de blueprint correctos, como:
   - `registros_entrada_lista.html`
   - `registro_entrada_detalle.html`

3. **Redirecciones a blueprints**: Puede haber redirecciones desde un blueprint a otro que no estén utilizando el prefijo correcto.

4. **Actualización de URLs en JavaScript**: Es posible que algunos scripts JavaScript contengan URLs hardcodeadas que necesiten actualizarse.

## 4. Archivos Redundantes a Considerar para Eliminación

### 4.1 Scripts de Migración Ya Utilizados

- `scripts/fix_indentation.py`: Ya se ha usado para corregir la indentación.
- `scripts/fix_utils_initialization.py`: Ya se ha usado para corregir la inicialización de Utils.

### 4.2 Copias de Seguridad Antiguas

- Archivos `.bak` y `.bak_*` generados durante las migraciones.
- Directorio `TiquetesApp_backup/` si ya no es necesario.

### 4.3 Archivos del Proyecto Original

- `implementacion_clasificacion.py`: Código que ya ha sido integrado en los blueprints.
- `apptiquetes.py`: El archivo principal antiguo que ha sido reemplazado por la estructura de blueprints.
- Otros archivos .py en el directorio raíz que ahora están en los blueprints correspondientes.

## 5. Próximos Pasos Recomendados

1. **Resolver el problema de la clave secreta** en `app/__init__.py`.
2. **Revisar todas las plantillas** para asegurar que usen los prefijos de blueprint correctos.
3. **Crear un script para verificar y corregir URLs** en todas las plantillas.
4. **Limpiar archivos redundantes** después de confirmar su obsolescencia.
5. **Completar la documentación** de la estructura de blueprints.
6. **Implementar pruebas unitarias** para validar la funcionalidad después de los cambios.

## 6. Nota sobre la Base de Datos

Según `README_ACTUALIZACION.md`, se ha implementado una capa unificada de acceso a datos que utiliza SQLite, manteniendo compatibilidad con el formato JSON existente. Esto ha afectado principalmente a:

- Funciones de registro de peso: `registrar_peso_directo` y `registrar_peso_virtual`
- Funciones de registro de peso neto: `registrar_peso_neto`, `registrar_peso_neto_directo` y `registrar_peso_neto_virtual`

La estructura de la base de datos incluye tablas para registros de entrada, pesajes brutos, pesajes netos y salidas. 