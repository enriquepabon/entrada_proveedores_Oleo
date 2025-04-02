# Actualización de TiquetesApp: Consolidación de Datos en SQLite

## Resumen de Cambios

Se ha implementado una capa unificada de acceso a datos para la aplicación TiquetesApp, permitiendo una gestión más robusta y consistente de los datos. Esta actualización mejora la fiabilidad del sistema al consolidar la información en una base de datos SQLite, manteniendo compatibilidad con el formato JSON existente.

## Componentes Actualizados

### 1. Capa de Acceso a Datos (DAL)

Se ha creado un nuevo archivo `data_access.py` que implementa la clase `DataAccess` con los siguientes métodos:

- `get_guia_complete_data`: Recupera datos completos de una guía, consultando primero en la base de datos y luego en archivos JSON si es necesario.
- `save_pesaje_bruto`: Guarda o actualiza datos de pesaje bruto en la base de datos y mantiene compatibilidad con archivos JSON.
- `save_pesaje_neto`: Guarda o actualiza datos de pesaje neto en la base de datos y mantiene compatibilidad con archivos JSON.

### 2. Funciones de Registro de Peso

Las siguientes funciones han sido actualizadas para utilizar la nueva capa de acceso a datos:

- `registrar_peso_directo` y `registrar_peso_virtual`: Para el registro de peso bruto.
- `registrar_peso_neto`, `registrar_peso_neto_directo` y `registrar_peso_neto_virtual`: Para el registro de peso neto.

### 3. Estructura de Base de Datos

Se ha verificado y actualizado la estructura de la base de datos SQLite con las siguientes tablas:

- `entry_records`: Almacena datos de registro de entrada de vehículos.
- `pesajes_bruto`: Almacena datos de pesaje bruto.
- `pesajes_neto`: Almacena datos de pesaje neto.
- `salidas`: Almacena datos de registro de salida.

### 4. Scripts de Mantenimiento

Se han creado scripts para facilitar la actualización y mantenimiento:

- `scripts/check_create_tables.py`: Verifica y crea las tablas necesarias en la base de datos.
- `fix_registrar_peso.py`: Actualiza las funciones de registro de peso bruto.
- `fix_registrar_pesaje_neto.py`: Actualiza la función principal de registro de peso neto.
- `fix_registrar_peso_neto_direct_virtual.py`: Actualiza las funciones específicas de registro de peso neto.

## Beneficios de la Actualización

1. **Mayor Consistencia de Datos**: Al centralizar el almacenamiento en SQLite, se reduce el riesgo de inconsistencias entre diferentes sistemas de almacenamiento.

2. **Mejor Manejo de Errores**: Las funciones actualizadas incluyen un manejo de errores más robusto, con registro detallado de problemas y mensajes de error más informativos.

3. **Compatibilidad con el Sistema Existente**: Se mantiene la compatibilidad con los archivos JSON, permitiendo una transición gradual sin afectar la funcionalidad existente.

4. **Base para Futuras Mejoras**: Esta arquitectura facilita la implementación de futuras mejoras, como búsquedas más eficientes, reportes avanzados o sincronización con sistemas externos.

## Instrucciones para Reinstalación

Si necesitas reinstalar o actualizar estos componentes:

1. Asegúrate de tener el archivo `data_access.py` en el directorio principal de la aplicación.
2. Ejecuta el script `scripts/check_create_tables.py` para verificar la estructura de la base de datos.
3. Ejecuta los scripts `fix_registrar_peso.py`, `fix_registrar_pesaje_neto.py` y `fix_registrar_peso_neto_direct_virtual.py` para actualizar las funciones de registro.
4. Reinicia el servidor Flask para aplicar los cambios.

## Notas Importantes

- Se han creado copias de seguridad automáticas de los archivos modificados con extensiones `.bak_peso`, `.bak_peso_neto_*` y `.bak_peso_neto_dir_virt_*`.
- Es recomendable realizar una copia de seguridad completa del sistema antes de aplicar estas actualizaciones en un entorno de producción.
- Para cualquier problema, consulta los archivos de registro de la aplicación para obtener información detallada sobre posibles errores. 