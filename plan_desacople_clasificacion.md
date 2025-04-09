**Plan de Implementación: Desacople de Clasificación Manual y Automática**

1.  [X] **Modificar `templates/clasificacion/clasificacion_form.html`:**
    *   Eliminar el `div` que contiene los checkboxes "Clasificación Automática" y "Clasificación Manual".
    *   Asegurar que las secciones `seccionFotos` y `seccionClasificacionManual` sean visibles por defecto.
    *   Cambiar el texto del botón principal de envío (`id="btn-guardar"`) a "Guardar Fotos y Clasificación Manual".
    *   Eliminar la sección de Debug (`div#debug-data-passed`).
    *   Eliminar la sección de Resultados (contenedora de "Resultados Automáticos" y "Resultados Manuales").
    *   Eliminar los botones de prueba (`btn-debug`, `direct-form`).
    *   Revisar la funcionalidad de los botones de cámara.

2.  [ ] **Modificar Ruta Backend para Guardar Manual/Fotos (`clasificacion.registrar_clasificacion`):**
    *   Identificar la ruta que maneja el envío de `clasificacion_form.html`. --> `clasificacion.registrar_clasificacion`
    *   Eliminar el inicio del procesamiento automático.
    *   Asegurar el guardado correcto de datos manuales y rutas de fotos.
    *   Añadir/Actualizar un campo de estado para indicar la finalización de este paso (ej., `estado_manual_fotos = 'completado')`.
    *   Cambiar la redirección a `misc.ver_guia_centralizada`.

3.  [ ] **Modificar `templates/guia_centralizada.html`:**
    *   Mostrar estado intermedio ("Clasificación Manual/Fotos Guardadas").
    *   Añadir tabla de resultados de clasificación manual (con porcentajes).
    *   Actualizar lógica de botones/enlaces ("Registrar Clasificación Manual y Fotos" o "Ver Resultados / Procesar Automática").

4.  [ ] **Modificar Ruta Backend (`/clasificacion/ver_resultados_clasificacion`):**
    *   Asegurar carga de datos manuales.
    *   Verificar existencia de resultados automáticos.
    *   Pasar variables al template sobre existencia de fotos y resultados automáticos.

5.  [ ] **Modificar `templates/clasificacion_resultados.html`:**
    *   Mostrar siempre resultados manuales.
    *   Mostrar resultados automáticos y botón "Ver Detalles" condicionalmente.
    *   Mostrar botón "Iniciar Clasificación Automática" condicionalmente (fotos sí, resultados automáticos no). 