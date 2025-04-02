# Plan de Mejora para la Plantilla de Clasificación

## 1. Problema Identificado

La plantilla de clasificación (`clasificacion.html`) no está mostrando correctamente el nombre del proveedor y la cantidad de racimos. Tras analizar el código, se han identificado las siguientes posibles causas:

1. Los datos podrían no estar siendo pasados correctamente desde la función `clasificacion(codigo)` a la plantilla.
2. La plantilla podría tener problemas al acceder a estas variables.
3. La estructura de datos no es consistente entre diferentes partes del sistema.

## 2. Análisis del Problema

### 2.1 Desde el Controlador (`apptiquetes.py`)

En la función `clasificacion(codigo)`, los datos se pasan a la plantilla con las siguientes variables:

```python
return render_template('clasificacion.html', 
                    codigo=datos_guia.get('codigo'),
                    codigo_guia=codigo_guia_completo,
                    nombre=datos_guia.get('nombre') or datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor', 'No disponible'),
                    cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                    # ... otras variables ...
                    )
```

**Observaciones:**
- Los datos del proveedor se buscan en tres campos posibles: `nombre`, `nombre_proveedor`, o `nombre_agricultor`.
- La cantidad de racimos se busca en dos campos: `cantidad_racimos` o `racimos`.
- Ambos variables tienen valores por defecto de "No disponible" si no se encuentran.

### 2.2 En la Plantilla (`clasificacion.html`)

La plantilla podría estar tratando de acceder a variables con nombres diferentes a los que se pasan desde el controlador.

## 3. Plan de Acción

### 3.1 Diagnóstico y Solución Inmediata

1. **Agregar código de depuración**:
   - Insertar un bloque de código HTML en la plantilla para mostrar todas las variables disponibles.
   - Agregar logs detallados en la función del controlador para ver qué valores se están enviando.

2. **Verificar la estructura de `datos_guia`**:
   - Agregar un paso para imprimir en el log todos los campos disponibles en `datos_guia` justo antes de renderizar la plantilla.
   - Verificar cómo se está obteniendo `datos_guia` a través de `utils.get_datos_guia(codigo_guia_completo)`.

3. **Corregir la Función del Controlador**:
   ```python
   # Código mejorado para el controlador
   return render_template('clasificacion.html', 
                       codigo=datos_guia.get('codigo'),
                       codigo_guia=codigo_guia_completo,
                       # Asegurarse de pasar los datos con nombres claros y consistentes
                       nombre_proveedor=datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible'),
                       codigo_proveedor=datos_guia.get('codigo_proveedor') or datos_guia.get('codigo', 'No disponible'),
                       cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                       # Pasar todos los datos originales para depuración
                       datos_guia=datos_guia,
                       # ... otras variables ...
                       )
   ```

4. **Corregir la Plantilla**:
   - Asegurarse de que la plantilla use los nombres de variables exactos que se pasan desde el controlador.
   - Agregar lógica condicional para manejar casos donde los datos no estén disponibles.

### 3.2 Implementación de la Solución

1. **Modificación del Controlador (`apptiquetes.py`)**:
   - Actualizar la función `clasificacion(codigo)` con los cambios propuestos.
   - Agregar logs adicionales para rastrear el flujo de datos.

2. **Modificación de la Plantilla (`clasificacion.html`)**:
   - Agregar un bloque de depuración que solo se muestre durante el desarrollo:
   ```html
   {% if debug %}
   <div class="debug-info">
       <h3>Información de Depuración</h3>
       <ul>
           <li>codigo_guia: {{ codigo_guia }}</li>
           <li>nombre_proveedor: {{ nombre_proveedor }}</li>
           <li>codigo_proveedor: {{ codigo_proveedor }}</li>
           <li>cantidad_racimos: {{ cantidad_racimos }}</li>
           <!-- Listar todas las variables disponibles -->
       </ul>
   </div>
   {% endif %}
   ```
   
   - Asegurarse de que todos los lugares donde se usan estas variables tengan el nombre correcto:
   ```html
   <!-- Ejemplo de corrección -->
   <h3>Proveedor: {{ nombre_proveedor }}</h3>
   <p>Cantidad de Racimos: {{ cantidad_racimos }}</p>
   ```

### 3.3 Pruebas y Validación

1. **Crear un endpoint de prueba**:
   Implementar una ruta de prueba específica para verificar la correcta visualización de datos:

   ```python
   @app.route('/prueba-clasificacion/<codigo>')
   def prueba_clasificacion(codigo):
       # Obtener datos como en la función normal
       datos_guia = utils.get_datos_guia(codigo)
       if not datos_guia:
           return jsonify({"error": "Guía no encontrada"}), 404
           
       # Mostrar los datos disponibles en la guía
       return jsonify({
           "datos_guia_completos": datos_guia,
           "nombre_proveedor": datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible'),
           "cantidad_racimos": datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
       })
   ```

2. **Prueba A/B**:
   - Implementar una versión alternativa de la plantilla con las correcciones.
   - Probar ambas versiones para validar la solución.

### 3.4 Mejoras a Largo Plazo

1. **Estandarización de nombres de campo**:
   - Definir una estructura de datos consistente para todo el sistema.
   - Crear una función de normalización de datos en `utils.py` que asegure que todos los campos tengan nombres consistentes.

2. **Mejorar el manejo de errores y valores predeterminados**:
   - Implementar una estrategia más robusta para manejar valores nulos o faltantes.
   - Agregar validaciones en el backend antes de renderizar las plantillas.

3. **Refactorizar la función `get_datos_guia` en `utils.py`**:
   - Asegurar que siempre devuelve datos con la misma estructura.
   - Normalizar los nombres de los campos para evitar inconsistencias.

## 4. Implementación Inmediata

A continuación se detallan los cambios específicos a realizar de inmediato:

### 4.1 En `apptiquetes.py`

```python
@app.route('/clasificacion/<codigo>', methods=['GET'])
def clasificacion(codigo):
    try:
        logger.info(f"Iniciando vista de clasificación para código: {codigo}")
        
        # Código existente...
        
        # Antes de renderizar, agregar logs detallados
        logger.info(f"Datos de guía disponibles: {datos_guia.keys()}")
        logger.info(f"Nombre proveedor: {datos_guia.get('nombre_proveedor')} o {datos_guia.get('nombre')} o {datos_guia.get('nombre_agricultor')}")
        logger.info(f"Cantidad racimos: {datos_guia.get('cantidad_racimos')} o {datos_guia.get('racimos')}")
        
        # Renderizar con nombres de variables claros y consistentes
        return render_template('clasificacion.html', 
                            codigo=datos_guia.get('codigo'),
                            codigo_guia=codigo_guia_completo,
                            nombre_proveedor=datos_guia.get('nombre_proveedor') or datos_guia.get('nombre') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            codigo_proveedor=datos_guia.get('codigo_proveedor') or datos_guia.get('codigo', 'No disponible'),
                            cantidad_racimos=datos_guia.get('cantidad_racimos') or datos_guia.get('racimos', 'No disponible'),
                            # Mantener estas variables para compatibilidad
                            nombre=datos_guia.get('nombre') or datos_guia.get('nombre_proveedor') or datos_guia.get('nombre_agricultor', 'No disponible'),
                            # Resto de variables...
                            debug=app.config.get('DEBUG', False)  # Pasar flag de depuración
                           )
    
    except Exception as e:
        logger.error(f"Error en clasificación: {str(e)}")
        logger.error(traceback.format_exc())
        return render_template('error.html', message="Error procesando clasificación"), 500
```

### 4.2 En `clasificacion.html`

Agregar al principio de la plantilla:

```html
{% if debug %}
<!-- Bloque de depuración -->
<div class="card my-3 border-danger">
    <div class="card-header bg-danger text-white">
        <h5 class="mb-0">Información de Depuración</h5>
    </div>
    <div class="card-body">
        <h6>Variables disponibles:</h6>
        <ul>
            <li><strong>codigo_guia:</strong> {{ codigo_guia }}</li>
            <li><strong>nombre_proveedor:</strong> {{ nombre_proveedor }}</li>
            <li><strong>nombre (fallback):</strong> {{ nombre }}</li>
            <li><strong>codigo_proveedor:</strong> {{ codigo_proveedor }}</li>
            <li><strong>cantidad_racimos:</strong> {{ cantidad_racimos }}</li>
        </ul>
    </div>
</div>
{% endif %}
```

Y corregir todas las referencias a estas variables en la plantilla para asegurar consistencia.

## 5. Seguimiento y Evaluación

1. Implementar los cambios propuestos.
2. Probar con diferentes guías que tengan estructuras de datos variadas.
3. Monitorear los logs para identificar posibles problemas adicionales.
4. Recopilar feedback de los usuarios sobre la visualización correcta de los datos.

Este plan aborda tanto la solución inmediata como las mejoras a largo plazo para asegurar que la plantilla de clasificación funcione correctamente y de manera consistente. 