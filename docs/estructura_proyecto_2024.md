# Estructura del Proyecto TiquetesApp - Marzo 2024

Este documento detalla la estructura actual del proyecto TiquetesApp, enfocándose en la organización de archivos, módulos funcionales, plantillas en uso, y estructura de la base de datos.

**Fecha de actualización:** 18 de marzo de 2024

## 1. Organización General

El proyecto ha sido completamente refactorizado utilizando la arquitectura de blueprints de Flask, lo que permite una mejor separación de responsabilidades y modularidad.

### 1.1 Estructura de Directorios Principal

```
TiquetesApp/
├── app/                      # Directorio principal de la aplicación
│   ├── __init__.py           # Configuración e inicialización de la app Flask
│   ├── blueprints/           # Módulos funcionales (blueprints)
│   ├── models/               # Modelos de datos
│   └── utils/                # Utilidades generales
├── static/                   # Archivos estáticos (CSS, JS, imágenes)
├── templates/                # Plantillas HTML
├── data/                     # Datos persistentes (JSON)
├── scripts/                  # Scripts de utilidades y migración
├── docs/                     # Documentación
├── tiquetes.db               # Base de datos SQLite principal
├── database.db               # Base de datos SQLite legado
└── run.py                    # Punto de entrada de la aplicación
```

### 1.2 Estructura de la Aplicación (Blueprints)

La aplicación está organizada en módulos funcionales utilizando Flask Blueprints:

```
app/blueprints/
├── entrada/                  # Gestión de registros de entrada
│   ├── __init__.py
│   └── routes.py
├── pesaje/                   # Proceso de pesaje bruto
│   ├── __init__.py
│   └── routes.py
├── clasificacion/            # Sistema de clasificación
│   ├── __init__.py
│   └── routes.py
├── pesaje_neto/              # Proceso de pesaje neto
│   ├── __init__.py
│   └── routes.py
├── salida/                   # Registro de salida
│   ├── __init__.py
│   └── routes.py
├── misc/                     # Funcionalidades misceláneas
│   ├── __init__.py
│   └── routes.py
├── admin/                    # Administración
│   ├── __init__.py
│   └── routes.py
└── api/                      # API RESTful
    ├── __init__.py
    └── routes.py
```

## 2. Plantillas en Uso

Las plantillas están organizadas por módulo funcional y siguiendo una estructura jerárquica con plantillas base y componentes reutilizables.

### 2.1 Plantillas Base

- **base.html**: Plantilla base principal con estructura HTML, CSS y JS compartidos
- **guia_base.html**: Plantilla base para guías y documentos
- **layouts/base.html**: Estructura alternativa (legado)

### 2.2 Plantillas por Módulo

#### Entrada
- **entrada/review.html**: Revisión de datos extraídos de tiquetes
- **entrada/review_pdf.html**: Versión PDF de datos de entrada
- **entrada/home.html**: Dashboard principal
- **entrada/index.html**: Página de captura de tiquetes
- **entrada/processing.html**: Procesamiento de imágenes
- **entrada/register.html**: Registro final de datos
- **entrada/registros_entrada_lista.html**: Lista de registros

#### Pesaje
- **pesaje/pesaje.html**: Página principal de pesaje
- **pesaje/pesaje_inicial.html**: Registro de peso bruto
- **pesaje/pesajes_lista.html**: Lista de pesajes realizados
- **pesaje/print_view.html**: Vista para impresión de pesaje

#### Clasificación
- **clasificacion/clasificacion.html**: Página principal de clasificación
- **clasificacion/clasificaciones_lista.html**: Lista de clasificaciones
- **clasificacion/print_view.html**: Vista para impresión de clasificación
- **clasificacion/resultados_clasificacion.html**: Resultados de clasificación

#### Pesaje Neto
- **pesaje_neto/pesaje_neto.html**: Registro de peso neto (tara)
- **pesaje_neto/resultados_pesaje_neto.html**: Resultados de pesaje neto
- **pesaje_neto/pesajes_neto_lista.html**: Lista de pesajes netos

#### Salida
- **salida/registro_salida.html**: Registro de salida de vehículos
- **salida/resultados_salida.html**: Resultados del registro de salida

#### Vistas Centralizadas
- **guia_centralizada.html**: Vista centralizada del proceso completo
- **guia_template.html**: Plantilla para generación de guías HTML

#### Administración
- **admin/resultado_operacion.html**: Resultado de operaciones administrativas

#### Componentes
- **components/header.html**: Encabezado reutilizable
- **components/footer.html**: Pie de página reutilizable
- **components/navigation.html**: Barra de navegación
- **components/process_timeline.html**: Línea de tiempo del proceso

### 2.3 Plantillas Actualmente en Uso

| Módulo | Plantilla | Descripción | Ruta de acceso |
|--------|-----------|-------------|----------------|
| Entrada | review.html | Revisión de datos extraídos | /review |
| Entrada | home.html | Dashboard principal | /home |
| Entrada | index.html | Captura de tiquetes | / o /index |
| Pesaje | pesaje.html | Página de pesaje | /pesaje/<codigo> |
| Pesaje | pesajes_lista.html | Lista de pesajes | /pesajes |
| Clasificación | clasificacion.html | Página de clasificación | /clasificacion/<codigo> |
| Clasificación | clasificaciones_lista.html | Lista de clasificaciones | /clasificaciones/lista |
| Pesaje Neto | pesaje_neto.html | Registro de peso neto | /pesaje-neto/<codigo> |
| Pesaje Neto | resultados_pesaje_neto.html | Resultados de pesaje neto | /pesaje-neto/ver_resultados_pesaje_neto/<codigo> |
| Salida | registro_salida.html | Registro de salida | /salida/registro_salida/<codigo> |
| Salida | resultados_salida.html | Resultados de salida | /salida/ver_resultados_salida/<codigo> |
| Centralizada | guia_centralizada.html | Vista completa del proceso | /guia-centralizada/<codigo> |

## 3. Base de Datos

La aplicación utiliza SQLite como motor de base de datos principal, con dos archivos de base de datos:

- **tiquetes.db**: Base de datos principal actual
- **database.db**: Base de datos legado (mantiene compatibilidad)

### 3.1 Estructura de las Tablas

Las tablas principales del sistema son:

#### entry_records
Almacena información sobre los registros de entrada de vehículos.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código único de guía (llave primaria lógica) |
| nombre_proveedor | TEXT | Nombre del proveedor |
| codigo_proveedor | TEXT | Código del proveedor |
| fecha_registro | TEXT | Fecha de registro |
| hora_registro | TEXT | Hora de registro |
| num_cedula | TEXT | Número de cédula del conductor |
| num_placa | TEXT | Número de placa del vehículo |
| conductor | TEXT | Nombre del conductor |
| tipo_fruta | TEXT | Tipo de fruta transportada |
| lote | TEXT | Lote de origen |
| estado | TEXT | Estado del registro (default: 'activo') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

#### pesajes_bruto
Almacena información sobre pesajes brutos (iniciales).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código de guía (llave foránea) |
| codigo_proveedor | TEXT | Código del proveedor |
| nombre_proveedor | TEXT | Nombre del proveedor |
| peso_bruto | REAL | Peso bruto registrado |
| tipo_pesaje | TEXT | Tipo de pesaje (directo, virtual) |
| fecha_pesaje | TEXT | Fecha del pesaje |
| hora_pesaje | TEXT | Hora del pesaje |
| imagen_pesaje | TEXT | Ruta a la imagen del pesaje |
| codigo_guia_transporte_sap | TEXT | Código SAP de transporte |
| estado | TEXT | Estado del pesaje (default: 'activo') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

#### clasificaciones
Almacena resultados de la clasificación de racimos.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código de guía (llave foránea) |
| codigo_proveedor | TEXT | Código del proveedor |
| nombre_proveedor | TEXT | Nombre del proveedor |
| fecha_clasificacion | TEXT | Fecha de clasificación |
| hora_clasificacion | TEXT | Hora de clasificación |
| clasificaciones | TEXT | Resultados de clasificación (JSON) |
| observaciones | TEXT | Observaciones adicionales |
| estado | TEXT | Estado de la clasificación (default: 'activo') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

#### pesajes_neto
Almacena información sobre pesajes netos (finales).

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código de guía (llave foránea) |
| codigo_proveedor | TEXT | Código del proveedor |
| nombre_proveedor | TEXT | Nombre del proveedor |
| peso_bruto | REAL | Peso bruto registrado previamente |
| peso_tara | REAL | Peso tara (vehículo vacío) |
| peso_neto | REAL | Peso neto calculado (bruto - tara) |
| peso_producto | REAL | Peso del producto |
| tipo_pesaje | TEXT | Tipo de pesaje (directo, virtual) |
| tipo_pesaje_neto | TEXT | Tipo específico de pesaje neto |
| fecha_pesaje | TEXT | Fecha del pesaje |
| hora_pesaje | TEXT | Hora del pesaje |
| imagen_pesaje | TEXT | Ruta a la imagen del pesaje |
| comentarios | TEXT | Comentarios adicionales |
| estado | TEXT | Estado del pesaje (default: 'activo') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

#### fotos_clasificacion
Almacena referencias a las imágenes de clasificación.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código de guía (llave foránea) |
| ruta_foto | TEXT | Ruta a la imagen de clasificación |
| numero_foto | INTEGER | Número secuencial de la foto |
| tipo_foto | TEXT | Tipo de foto (racimo, conjunto, detalle) |
| fecha_subida | TEXT | Fecha de subida |
| hora_subida | TEXT | Hora de subida |
| estado | TEXT | Estado de la foto (default: 'activo') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

#### salidas
Almacena información sobre salidas de vehículos.

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | INTEGER | Identificador único autoincremental |
| codigo_guia | TEXT | Código de guía (llave foránea) |
| codigo_proveedor | TEXT | Código del proveedor |
| nombre_proveedor | TEXT | Nombre del proveedor |
| fecha_salida | TEXT | Fecha de salida |
| hora_salida | TEXT | Hora de salida |
| comentarios_salida | TEXT | Comentarios adicionales |
| firma_salida | TEXT | Ruta a imagen de firma |
| estado | TEXT | Estado de la salida (default: 'completado') |
| fecha_creacion | TIMESTAMP | Fecha y hora de creación del registro |

### 3.2 Tablas Históricas y de Legado

La base de datos `database.db` mantiene algunas tablas históricas para compatibilidad con versiones anteriores. La aplicación puede consultar ambas bases de datos cuando es necesario.

## 4. Almacenamiento de Archivos

Los archivos generados por la aplicación se almacenan en las siguientes ubicaciones dentro del directorio `static/`:

### 4.1 Imágenes y Fotos

- **uploads/**: Imágenes de tiquetes y fotos generales
  - **uploads/clasificacion/**: Fotos específicas para clasificación de racimos
  - **uploads/bascula/**: Imágenes de básculas
  - **uploads/placas/**: Imágenes de placas de vehículos

### 4.2 Documentos Generados

- **pdfs/**: Documentos PDF generados (tiquetes, guías, certificados)
- **guias/**: Archivos HTML de guías generadas
- **qr/**: Códigos QR generados para acceso rápido a guías

## 5. Módulos y Funcionalidades Principales

### 5.1 Módulo de Entrada

Gestiona el registro inicial de proveedores que ingresan a la planta.

**Funcionalidades principales**:
- Captura y procesamiento de imágenes de tiquetes
- Reconocimiento de datos (conductor, placa, proveedor)
- Validación y corrección de datos extraídos
- Registro en la base de datos

### 5.2 Módulo de Pesaje (Bruto)

Maneja el proceso de pesaje inicial de vehículos con carga.

**Funcionalidades principales**:
- Registro de peso bruto (manual o automático)
- Captura de imágenes de báscula
- Verificación de placa (opcional)
- Generación de comprobantes de pesaje

### 5.3 Módulo de Clasificación

Sistema de clasificación de racimos mediante inteligencia artificial.

**Funcionalidades principales**:
- Captura de imágenes de racimos
- Procesamiento automático con Roboflow
- Clasificación en categorías predefinidas
- Generación de reportes de clasificación

### 5.4 Módulo de Pesaje Neto

Gestiona el proceso de pesaje final (tara) y cálculo de peso neto.

**Funcionalidades principales**:
- Registro de peso tara (vehículo vacío)
- Cálculo automático de peso neto
- Verificación de datos (opcional)
- Generación de comprobantes de peso neto

### 5.5 Módulo de Salida

Registra la salida de vehículos de la planta.

**Funcionalidades principales**:
- Confirmación de finalización del proceso
- Registro de fecha y hora de salida
- Comentarios adicionales
- Generación de documentación final

## 6. Próximos Pasos y Mejoras Pendientes

### 6.1 Mejoras de Diseño
- ✅ Homologación de interfaces de usuario entre módulos
- ⚠️ Mejora de responsividad en dispositivos móviles
- ⚠️ Estandarización completa de componentes

### 6.2 Mejoras Técnicas
- ✅ Refactorización completa a arquitectura de Blueprints
- ✅ Implementación de base de datos SQLite
- ⚠️ Implementación de un sistema de caché para mejorar rendimiento
- ⚠️ Mejora de manejo de errores y excepciones

### 6.3 Nuevas Funcionalidades
- ✅ Módulo de salida completamente funcional
- ✅ Vista centralizada de todo el proceso
- ⚠️ Reportes estadísticos avanzados
- ⚠️ Panel administrativo completo 