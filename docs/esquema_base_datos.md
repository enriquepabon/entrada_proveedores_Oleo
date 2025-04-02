# Esquema y Estructura de Base de Datos - TiquetesApp

Este documento detalla la estructura de la base de datos de TiquetesApp, incluyendo esquemas de tablas, relaciones, y estrategias de migración.

**Fecha de actualización:** 18 de marzo de 2024

## 1. Visión General

TiquetesApp utiliza SQLite como sistema de gestión de base de datos principal, con dos archivos de base de datos:

- **tiquetes.db**: Base de datos principal que almacena toda la información del sistema
- **database.db**: Base de datos secundaria/legado que mantiene compatibilidad con versiones anteriores

La aplicación implementa una capa de abstracción que permite consultar ambas bases de datos cuando es necesario, priorizando `tiquetes.db` para datos nuevos.

## 2. Modelo de Datos

### 2.1 Diagrama Entidad-Relación Simplificado

```
+-----------------+       +-----------------+       +------------------+
| entry_records   | 1---* | pesajes_bruto   | 1---* | clasificaciones  |
+-----------------+       +-----------------+       +------------------+
        |                         |                         |
        |                         |                         |
        |                         |                         |
        *                         *                         *
+-----------------+       +-----------------+       +------------------+
| pesajes_neto    | *---1 | salidas         |       | fotos_clasific.  |
+-----------------+       +-----------------+       +------------------+
```

La relación principal se basa en el código de guía (`codigo_guia`) que funciona como clave primaria lógica a través de todas las tablas.

## 3. Definición de Tablas

### 3.1 entry_records

Almacena los registros de entrada inicial de vehículos a la planta.

```sql
CREATE TABLE IF NOT EXISTS entry_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    nombre_proveedor TEXT,
    codigo_proveedor TEXT,
    fecha_registro TEXT,
    hora_registro TEXT,
    num_cedula TEXT,
    num_placa TEXT,
    conductor TEXT,
    tipo_fruta TEXT,
    lote TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.2 pesajes_bruto

Almacena los datos del pesaje bruto inicial.

```sql
CREATE TABLE IF NOT EXISTS pesajes_bruto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    peso_bruto REAL,
    tipo_pesaje TEXT,
    fecha_pesaje TEXT,
    hora_pesaje TEXT,
    imagen_pesaje TEXT,
    codigo_guia_transporte_sap TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.3 clasificaciones

Almacena los resultados de la clasificación de racimos.

```sql
CREATE TABLE IF NOT EXISTS clasificaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    fecha_clasificacion TEXT,
    hora_clasificacion TEXT,
    clasificaciones TEXT,
    observaciones TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.4 pesajes_neto

Almacena los datos del pesaje neto (tara y cálculo de peso neto).

```sql
CREATE TABLE IF NOT EXISTS pesajes_neto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    peso_bruto REAL,
    peso_tara REAL,
    peso_neto REAL,
    peso_producto REAL,
    tipo_pesaje TEXT,
    tipo_pesaje_neto TEXT,
    fecha_pesaje TEXT,
    hora_pesaje TEXT,
    imagen_pesaje TEXT,
    comentarios TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3.5 fotos_clasificacion

Almacena referencias a las imágenes utilizadas en el proceso de clasificación.

```sql
CREATE TABLE IF NOT EXISTS fotos_clasificacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT NOT NULL,
    ruta_foto TEXT NOT NULL,
    numero_foto INTEGER,
    tipo_foto TEXT,
    fecha_subida TEXT,
    hora_subida TEXT,
    estado TEXT DEFAULT 'activo',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (codigo_guia) REFERENCES clasificaciones(codigo_guia)
);
```

### 3.6 salidas

Almacena la información del registro de salida de vehículos.

```sql
CREATE TABLE IF NOT EXISTS salidas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_guia TEXT UNIQUE NOT NULL,
    codigo_proveedor TEXT,
    nombre_proveedor TEXT,
    fecha_salida TEXT,
    hora_salida TEXT,
    comentarios_salida TEXT,
    firma_salida TEXT,
    estado TEXT DEFAULT 'completado',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 4. Funciones de Acceso a Datos

La aplicación utiliza varias funciones para acceder y manipular los datos en la base de datos. Las principales se encuentran en los siguientes archivos:

- **db_operations.py**: Funciones para operaciones CRUD básicas
- **db_utils.py**: Utilidades relacionadas con la base de datos
- **data_access.py**: Capa de abstracción para acceso a datos

### 4.1 Funciones Principales

#### Operaciones de Entrada
- `store_entry_record`: Almacena un nuevo registro de entrada
- `get_entry_records`: Obtiene registros de entrada según filtros
- `get_entry_record_by_guide_code`: Obtiene un registro específico por código de guía

#### Operaciones de Pesaje Bruto
- `store_pesaje_bruto`: Almacena un nuevo registro de pesaje bruto
- `get_pesajes_bruto`: Obtiene registros de pesaje bruto según filtros
- `update_pesaje_bruto`: Actualiza un registro de pesaje bruto existente

#### Operaciones de Clasificación
- `store_clasificacion`: Almacena un nuevo registro de clasificación
- `get_clasificaciones`: Obtiene registros de clasificación según filtros
- `get_clasificacion_by_codigo_guia`: Obtiene una clasificación específica por código de guía

#### Operaciones de Pesaje Neto
- `store_pesaje_neto`: Almacena un nuevo registro de pesaje neto
- `get_pesajes_neto`: Obtiene registros de pesaje neto según filtros
- `get_pesaje_neto_by_codigo_guia`: Obtiene un pesaje neto específico por código de guía

#### Operaciones de Salida
- `store_salida`: Almacena un nuevo registro de salida
- `get_salidas`: Obtiene registros de salida según filtros
- `get_salida_by_codigo_guia`: Obtiene un registro de salida específico por código de guía

## 5. Estrategia de Migración y Compatibilidad

### 5.1 Migración desde JSON a SQLite

La aplicación originalmente utilizaba archivos JSON para almacenar datos. La migración a SQLite se ha implementado manteniendo compatibilidad con el formato JSON anterior.

El proceso de migración se realiza mediante los siguientes scripts:

- **sync_database.py**: Sincroniza datos entre JSON y SQLite
- **migrate_records.py**: Migra registros específicos a la base de datos SQLite
- **data_migration.py**: Funciones generales para migración de datos

### 5.2 Compatibilidad con Versiones Anteriores

Para mantener compatibilidad con implementaciones existentes, la aplicación:

1. Verifica la existencia de datos en ambas fuentes (JSON y SQLite)
2. Prioriza los datos más recientes de cualquier fuente
3. Sincroniza cambios realizados en cualquier formato

La función `CommonUtils.get_datos_guia()` implementa esta lógica, verificando todas las fuentes de datos disponibles.

### 5.3 Actualización de Esquema

El esquema de la base de datos puede ser actualizado añadiendo nuevas columnas a las tablas existentes. Los módulos contienen funciones que verifican y actualizan el esquema en tiempo de ejecución:

- `ensure_pesajes_neto_schema()`: Asegura que la tabla `pesajes_neto` tenga las columnas necesarias
- `ensure_salidas_schema()`: Asegura que la tabla `salidas` tenga las columnas necesarias

## 6. Consideraciones de Rendimiento

### 6.1 Índices

La base de datos utiliza índices implícitos en las claves primarias (`id`) y en los campos únicos (`codigo_guia`). Se recomienda añadir índices adicionales para consultas frecuentes:

```sql
CREATE INDEX IF NOT EXISTS idx_entry_proveedor ON entry_records(codigo_proveedor);
CREATE INDEX IF NOT EXISTS idx_pesajes_fecha ON pesajes_bruto(fecha_pesaje);
CREATE INDEX IF NOT EXISTS idx_clasificaciones_fecha ON clasificaciones(fecha_clasificacion);
```

### 6.2 Optimización de Consultas

Las consultas más críticas incluyen:

1. Búsqueda por código de guía (utilizadas en todas las operaciones de seguimiento)
2. Búsqueda por código de proveedor (utilizadas en informes)
3. Búsquedas por fecha (utilizadas en informes y filtros)

Se recomienda optimizar estas consultas mediante el uso adecuado de índices y la limitación de resultados.

### 6.3 Mantenimiento

Para mantener un rendimiento óptimo, se recomienda:

1. Ejecutar `VACUUM` periódicamente para optimizar el almacenamiento
2. Implementar una estrategia de archivado para datos antiguos
3. Monitorear el tamaño de la base de datos y el rendimiento de consultas

## 7. Respaldo y Recuperación

### 7.1 Estrategia de Respaldo

Se recomienda realizar respaldos periódicos de los archivos de base de datos:

```bash
# Respaldo básico
cp tiquetes.db tiquetes.db.backup

# Respaldo completo con fecha
sqlite3 tiquetes.db .dump > backup_$(date +%Y%m%d).sql
```

### 7.2 Recuperación

Para restaurar desde un respaldo:

```bash
# Restaurar desde archivo SQL
sqlite3 tiquetes.db < backup_YYYYMMDD.sql

# Restaurar desde copia
cp tiquetes.db.backup tiquetes.db
```

### 7.3 Verificación de Integridad

Para verificar la integridad de la base de datos:

```bash
sqlite3 tiquetes.db "PRAGMA integrity_check;"
```

## 8. Notas sobre Compatibilidad con Versiones Futuras

Para futuras expansiones del esquema, considere:

1. Añadir nuevas columnas con valores predeterminados para mantener compatibilidad
2. Implementar verificación y actualización de esquema en tiempo de ejecución
3. Documentar todas las modificaciones al esquema para facilitar migraciones futuras

---

Documento preparado por [nombre del autor]  
Última actualización: 18 de marzo de 2024 