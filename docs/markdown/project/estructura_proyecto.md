# Estructura del Proyecto: Sistema de Gestión de Tiquetes MLB

## 1. Objetivo del Proyecto

El sistema "TiquetesApp" es una aplicación web desarrollada con Flask que gestiona el proceso completo de recepción, clasificación y pesaje de racimos de fruta para la Extractora María La Baja. El proyecto permite:

1. **Registro de entrada**: Captura de datos iniciales del proveedor, vehículo y carga.
2. **Pesaje en báscula**: Control del peso bruto, tara y cálculo de peso neto.
3. **Clasificación de racimos**: Evaluación manual y automática (IA) de la calidad de los racimos.
4. **Generación de reportes**: PDFs y documentación completa de todo el proceso.
5. **Consulta y seguimiento**: Visualización y filtrado de registros históricos.

## 2. Arquitectura del Sistema

### 2.1 Estructura de Archivos Principales

- **apptiquetes.py**: Archivo principal con todas las rutas y lógica de negocio.
- **utils.py**: Contiene funciones auxiliares y utilitarias para el sistema.
- **db_operations.py**: Operaciones CRUD para la base de datos SQLite.
- **db_schema.py**: Definición del esquema de la base de datos.
- **data_access.py**: Capa de acceso a datos unificada (DB + archivos JSON).
- **data_helper.py**: Funciones auxiliares para procesamiento de datos.
- **config.py**: Configuración de la aplicación.

### 2.2 Bases de Datos

El sistema utiliza SQLite como base de datos principal, con las siguientes tablas:

1. **entry_records**: Registros de entrada de vehículos y proveedores.
2. **pesajes_bruto**: Datos de pesaje inicial (bruto).
3. **pesajes_neto**: Datos de pesaje final (neto).
4. **clasificaciones**: Resultados de clasificación de racimos.

Para mantener compatibilidad con versiones anteriores, el sistema también utiliza archivos JSON como respaldo.

## 3. Flujo de Trabajo y Procesos

### 3.1 Registro de Entrada

1. **Captura inicial**: El usuario sube una foto del tiquete en la página principal (`index.html`).
2. **Procesamiento de imagen**: El sistema extrae información del tiquete usando reconocimiento de texto.
3. **Verificación y edición**: El usuario revisa y confirma los datos extraídos en la página de revisión (`review.html`).
4. **Registro de datos**: Se genera un código único para la guía y se registran los datos confirmados.

### 3.2 Proceso de Pesaje Bruto

1. **Inicio de pesaje**: Desde la pantalla de inicio (`home.html`), se accede al pesaje bruto mediante código.
2. **Captura de peso**: Se registra el peso bruto del vehículo en `pesaje.html`.
3. **Confirmación**: Se muestran los resultados del pesaje en `resultados_pesaje.html`.
4. **Generación de PDF**: Se crea un documento PDF con los detalles del pesaje.

### 3.3 Proceso de Clasificación

1. **Acceso a clasificación**: Mediante código de guía se accede a la pantalla de clasificación.
2. **Clasificación manual**: El usuario registra la cantidad de racimos por categoría (`clasificacion.html`).
3. **Procesamiento automático** (opcional): Las imágenes pueden ser procesadas con IA para detectar y clasificar racimos.
4. **Resultados**: Se visualizan los resultados en `resultados_clasificacion.html` y se pueden generar reportes.

### 3.4 Proceso de Pesaje Neto

1. **Registro de tara**: Cuando el vehículo regresa vacío, se registra el peso tara.
2. **Cálculo de peso neto**: Se calcula la diferencia entre el peso bruto y tara para obtener el peso neto.
3. **Confirmación**: Se visualizan y confirman los resultados del pesaje neto.
4. **Documentación**: Se genera la documentación completa del proceso.

### 3.5 Registro de Salida

1. **Finalización del proceso**: Se registra la salida del vehículo.
2. **Generación de documentación final**: PDF con todo el proceso completo.

## 4. Templates y su Función

### 4.1 Templates de Registro y Entrada
| Template | Función |
|----------|---------|
| **index.html** | Pantalla principal para subir imagen de tiquete |
| **processing.html** | Muestra que se está procesando la imagen |
| **review.html** | Revisión y edición de datos extraídos |
| **revalidation_success.html** | Confirmación de datos validados |
| **review_pdf.html** | Vista previa del PDF generado |
| **registros_entrada_lista.html** | Lista todos los registros de entrada |
| **registro_entrada_detalle.html** | Muestra detalles de un registro específico |

### 4.2 Templates de Pesaje Bruto
| Template | Función |
|----------|---------|
| **pesaje.html** | Formulario para registrar peso bruto |
| **resultados_pesaje.html** | Muestra resultados del pesaje bruto |
| **pesaje_print_view.html** | Vista para impresión de pesaje |
| **pesaje_pdf_template.html** | Plantilla para generar PDF de pesaje |
| **pesajes_lista.html** | Lista de todos los pesajes realizados |

### 4.3 Templates de Clasificación
| Template | Función |
|----------|---------|
| **clasificacion.html** | Interfaz para clasificación manual de racimos |
| **clasificacion_print_view.html** | Vista para impresión de clasificación |
| **resultados_clasificacion.html** | Muestra resultados de clasificación |
| **auto_clasificacion_inicio.html** | Inicia proceso de clasificación automática |
| **procesando_clasificacion.html** | Muestra progreso de clasificación automática |
| **resultados_automaticos.html** | Muestra resultados de clasificación automática |
| **clasificaciones_lista.html** | Lista todas las clasificaciones realizadas |
| **clasificacion_pdf_template.html** | Plantilla para PDF de clasificación |

### 4.4 Templates de Pesaje Neto
| Template | Función |
|----------|---------|
| **pesaje_neto.html** | Interfaz para registrar peso tara y calcular neto |
| **resultados_pesaje_neto.html** | Muestra resultados de pesaje neto |
| **pesaje_neto_pdf_template.html** | Plantilla para PDF de pesaje neto |
| **pesajes_neto_lista.html** | Lista todos los pesajes neto realizados |

### 4.5 Templates de Registro de Salida
| Template | Función |
|----------|---------|
| **registro_salida.html** | Interfaz para registrar salida de vehículo |
| **resultados_salida.html** | Confirmación de registro de salida |

### 4.6 Templates Base y Utilidades
| Template | Función |
|----------|---------|
| **base.html** | Template base con estructura común para todas las páginas |
| **home.html** | Pantalla de inicio con acceso a todas las funciones |
| **error.html** | Página de error genérica |
| **guia_template.html** | Plantilla para generar página de guía completa |

## 5. Manejo de Base de Datos

### 5.1 Estructura de Tablas

**entry_records**:
- Información del proveedor y vehículo
- Datos de entrada inicial
- Código único de guía

**pesajes_bruto**:
- Peso bruto del vehículo con carga
- Tipo de pesaje (directo/virtual)
- Fecha y hora del pesaje

**clasificaciones**:
- Resultados de clasificación manual
- Resultados de clasificación automática
- Cantidad de racimos por categoría

**pesajes_neto**:
- Peso tara (vehículo vacío)
- Cálculo de peso neto (bruto - tara)
- Fecha y hora del pesaje

### 5.2 Capa de Acceso a Datos

El sistema implementa una capa de acceso a datos unificada a través de las clases:
- **DataAccess**: Proporciona métodos para obtener y guardar datos entre SQLite y archivos JSON.
- **DataHelper**: Funciones auxiliares para normalizar y procesar datos.

## 6. Funcionalidades de Inteligencia Artificial

El sistema utiliza Roboflow para implementar funcionalidades de IA:

1. **Reconocimiento de placas**: Identifica automáticamente las placas de vehículos.
2. **Clasificación automática de racimos**: Detecta y clasifica racimos en categorías:
   - Verdes
   - Maduros
   - Sobremaduros
   - Podridos
   - Con daño en corona
   - Con pedúnculo largo

## 7. Estado Actual y Pendientes

### 7.1 Funcionalidades Implementadas
- Registro completo de entrada con procesamiento de imágenes
- Sistema de pesaje bruto y neto
- Clasificación manual y automática de racimos
- Generación de PDFs y reportes
- Consulta y filtrado de registros históricos
- Sincronización entre bases de datos y archivos JSON

### 7.2 Pendientes y Mejoras Sugeridas

1. **Optimización de código**:
   - Refactorizar el archivo principal `apptiquetes.py` para mejor organización
   - Separar la lógica en blueprints para cada proceso

2. **Mejoras en UI/UX**:
   - Unificar estilos en todos los templates
   - Mejorar la navegación entre pantallas

3. **Integración con otros sistemas**:
   - Implementar APIs para comunicación con sistemas externos
   - Exportación de datos a formatos estándar (Excel, CSV)

4. **Auditoría y seguridad**:
   - Implementar sistema de usuarios y roles
   - Registro de auditoría de acciones

5. **Desempeño**:
   - Optimizar consultas a base de datos
   - Implementar caché para consultas frecuentes

6. **Validación de datos**:
   - Mejorar validación en formularios
   - Implementar validación servidor-cliente

7. **Testing**:
   - Desarrollar pruebas automatizadas
   - Implementar CI/CD

## 8. Conclusiones

TiquetesApp es un sistema completo para la gestión del proceso de recepción, clasificación y pesaje de racimos de fruta. Su implementación actual cubre todas las etapas del proceso, desde el registro inicial hasta la generación de documentación final.

La arquitectura del sistema permite flexibilidad y continuidad mediante el uso de múltiples formas de almacenamiento (SQLite y JSON), lo que facilita la transición y compatibilidad con versiones anteriores.

Se recomienda continuar el desarrollo enfocándose en las mejoras mencionadas en la sección 7.2, priorizando la refactorización del código para mejor mantenibilidad y la optimización de la experiencia de usuario.

## 9. Diagrama de Flujo Simplificado

```
[Inicio] → [Registro Entrada] → [Pesaje Bruto] → [Clasificación] → [Pesaje Neto] → [Registro Salida] → [Fin]
   ↓                ↓                 ↓                ↓                ↓                ↓
[index.html] → [review.html] → [pesaje.html] → [clasificacion.html] → [pesaje_neto.html] → [registro_salida.html]
   ↓                ↓                 ↓                ↓                ↓                ↓
[PDF Entrada] → [PDF Pesaje] → [PDF Clasificación] → [PDF Pesaje Neto] → [PDF Completo]
``` 