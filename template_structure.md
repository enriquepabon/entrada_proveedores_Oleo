# Estructura de Templates de TiquetesApp

## Introducción

Esta documentación define la estructura oficial de templates en TiquetesApp. Su objetivo es 
evitar confusiones y facilitar el mantenimiento del proyecto.

## Reglas de Ubicación de Templates

Actualmente existen templates en dos ubicaciones principales:
- `templates/` (directorio raíz)
- `app/templates/`

### Reglas para templates existentes
- Los templates en `templates/` se mantienen en su ubicación por compatibilidad con el código existente
- Los templates en `app/templates/` se mantienen en su ubicación por compatibilidad con el código existente

### Reglas para nuevos templates
- **TODOS los nuevos templates deben colocarse en `app/templates/`**
- Organizar los templates por módulo en subdirectorios (ej: `app/templates/pesaje/`)
- Nunca duplicar templates entre las dos ubicaciones

## Mapeo de Rutas a Templates (Guía de Referencia)

| Ruta | Blueprint | Función | Ubicación de Template |
|------|-----------|---------|----------------------|
| `/pesaje/pesaje-neto/<codigo>` | `pesaje` | `pesaje_neto()` | `templates/pesaje/pesaje_neto.html` |
| `/pesaje-neto/ver_resultados_pesaje_neto/<codigo>` | `pesaje_neto` | `ver_resultados_pesaje_neto()` | `templates/resultados_pesaje_neto.html` |
| `/pesaje-neto/registrar_peso_neto_directo` | `pesaje_neto` | `registrar_peso_neto_directo()` | (Procesa datos, no renderiza template) |

## Herramientas Disponibles para Documentación de Templates

Se han implementado las siguientes herramientas para ayudar a documentar y mantener la estructura de templates:

1. **Configuración Centralizada**: Archivo `app/config/template_config.py` que mapea cada función a su template correspondiente.

2. **Decoradores**: Disponible en `app/utils/decorators.py` para documentar qué template usa cada función.

## Buenas Prácticas

1. **Comentarios en el Código**: Añadir un comentario antes de cada `render_template()` indicando la ubicación exacta del template.

2. **Actualizar la Documentación**: Mantener este archivo actualizado cuando se añadan nuevos templates o rutas.

3. **Consistencia**: Usar los decoradores `@uses_template` en todos los nuevos controladores.

4. **Evitar Duplicación**: Nunca duplicar templates entre las dos ubicaciones.

5. **Migración Gradual**: A largo plazo, considerar migrar todos los templates a una estructura uniforme. 