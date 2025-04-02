let estadoFotos = {
    foto1: { procesada: false, estado: 'pendiente', imagen: null },
    foto2: { procesada: false, estado: 'pendiente', imagen: null },
    foto3: { procesada: false, estado: 'pendiente', imagen: null }
};

let resultadosAcumulados = {
    total_racimos: 0,
    clasificacion: {
        verde: 0,
        sobremaduro: 0,
        danio_corona: 0,
        pendunculo_largo: 0,
        podrido: 0
    },
    porcentajes: {
        verde: 0,
        sobremaduro: 0,
        danio_corona: 0,
        pendunculo_largo: 0,
        podrido: 0
    },
    imagenes: []
};

let clasificacionManualCompletada = false;
let clasificacionAutomaticaCompletada = false;
let fotoActual = 1;

function mostrarCarga(mostrar) {
    const loadingOverlay = document.getElementById('loadingOverlay');
    if (loadingOverlay) {
        loadingOverlay.style.display = mostrar ? 'flex' : 'none';
    }
}

function mostrarResultadosClasificacion(data) {
    try {
        console.log('Mostrando resultados:', data);
        
        const resultadosDiv = document.getElementById('resultadosClasificacion');
        if (!resultadosDiv) return;
        resultadosDiv.style.display = 'block';
        
        // Actualizar total de racimos
        const totalRacimosElement = document.getElementById('totalRacimos');
        if (totalRacimosElement) {
            totalRacimosElement.textContent = data.total_racimos || '0';
        }
        
        // Actualizar conteos y porcentajes
        const tipos = {
            'Verde': 'verde',
            'Sobremaduro': 'sobremaduro',
            'DanioCorona': 'danio_corona',
            'PendunculoLargo': 'pendunculo_largo',
            'Podrido': 'podrido'
        };

        Object.entries(tipos).forEach(([displayTipo, dataTipo]) => {
            const conteoElement = document.getElementById(`conteo${displayTipo}`);
            const porcentajeElement = document.getElementById(`porcentaje${displayTipo}`);
            
            if (conteoElement && data.clasificacion && data.clasificacion[dataTipo] !== undefined) {
                conteoElement.textContent = data.clasificacion[dataTipo];
            }
            if (porcentajeElement && data.porcentajes && data.porcentajes[dataTipo] !== undefined) {
                porcentajeElement.textContent = `(${data.porcentajes[dataTipo]}%)`;
            }
        });
        
        // Mostrar imágenes
        const contenedorImagenes = document.getElementById('imagenesClasificacion');
        if (contenedorImagenes && data.imagenes) {
            contenedorImagenes.innerHTML = '';
            Object.entries(data.imagenes).forEach(([tipo, filename]) => {
                if (filename) {
                    const img = document.createElement('img');
                    img.src = `/static/uploads/${filename}`;
                    img.className = 'img-fluid mb-3';
                    img.alt = `Imagen ${tipo}`;
                    contenedorImagenes.appendChild(img);
                }
            });
        }
        
        // Guardar resultados individuales
        if (!window.resultadosIndividuales) {
            window.resultadosIndividuales = [];
        }
        
        const resultadoIndividual = {
            verde: data.clasificacion.verde,
            sobremaduro: data.clasificacion.sobremaduro,
            danio_corona: data.clasificacion.danio_corona,
            pendunculo_largo: data.clasificacion.pendunculo_largo,
            podrido: data.clasificacion.podrido,
            total_racimos: data.total_racimos,
            porcentajes: data.porcentajes,
            imagenes: data.imagenes
        };
        
        window.resultadosIndividuales.push(resultadoIndividual);
        
        // Llenar formulario manual con los resultados automáticos
        if (fotoActual === 3 && resultadosAcumulados.porcentajes) {
            llenarFormularioManual(resultadosAcumulados.porcentajes);
        }
        
    } catch (error) {
        console.error('Error específico mostrando resultados:', error);
    }
}

function acumularResultados(data) {
    // Si es el primer resultado, inicializar la estructura
    if (!resultadosAcumulados.clasificacion) {
        resultadosAcumulados.clasificacion = {
            verde: 0,
            sobremaduro: 0,
            danio_corona: 0,
            pendunculo_largo: 0,
            podrido: 0
        };
    }
    
    // Acumular clasificaciones
    resultadosAcumulados.clasificacion.verde += data.clasificacion.verde;
    resultadosAcumulados.clasificacion.sobremaduro += data.clasificacion.sobremaduro;
    resultadosAcumulados.clasificacion.danio_corona += data.clasificacion.danio_corona;
    resultadosAcumulados.clasificacion.pendunculo_largo += data.clasificacion.pendunculo_largo;
    resultadosAcumulados.clasificacion.podrido += data.clasificacion.podrido;
    
    // Acumular total de racimos
    resultadosAcumulados.total_racimos += data.total_racimos;
    
    // Guardar imagen
    if (data.imagenes) {
        resultadosAcumulados.imagenes.push(data.imagenes);
    }
    
    // Recalcular porcentajes
    const total = resultadosAcumulados.total_racimos;
    if (total > 0) {
        resultadosAcumulados.porcentajes = {
            verde: ((resultadosAcumulados.clasificacion.verde / total) * 100).toFixed(1),
            sobremaduro: ((resultadosAcumulados.clasificacion.sobremaduro / total) * 100).toFixed(1),
            danio_corona: ((resultadosAcumulados.clasificacion.danio_corona / total) * 100).toFixed(1),
            pendunculo_largo: ((resultadosAcumulados.clasificacion.pendunculo_largo / total) * 100).toFixed(1),
            podrido: ((resultadosAcumulados.clasificacion.podrido / total) * 100).toFixed(1)
        };
    }
    
    // Actualizar display de resultados acumulados
    actualizarResultadosAcumulados();
    
    console.log('Resultados acumulados actualizados:', resultadosAcumulados);
}

function actualizarResultadosAcumulados() {
    const resultadosAcumuladosDiv = document.getElementById('resultadosAcumulados');
    resultadosAcumuladosDiv.style.display = 'block';
    
    // Actualizar total de racimos
    document.getElementById('totalRacimosAcumulados').textContent = resultadosAcumulados.total_racimos;

    // Actualizar conteos y porcentajes
    const tipos = {
        'Verde': 'verde',
        'Sobremaduro': 'sobremaduro',
        'DanioCorona': 'danio_corona',
        'PendunculoLargo': 'pendunculo_largo',
        'Podrido': 'podrido'
    };

    Object.entries(tipos).forEach(([displayTipo, dataTipo]) => {
        const conteoElement = document.getElementById(`conteo${displayTipo}`);
        const porcentajeElement = document.getElementById(`porcentaje${displayTipo}`);
        
        if (conteoElement) {
            conteoElement.textContent = resultadosAcumulados.clasificacion[dataTipo];
        }
        if (porcentajeElement) {
            porcentajeElement.textContent = `(${resultadosAcumulados.porcentajes[dataTipo]}%)`;
        }
    });
}

function prepararSiguienteFoto() {
    if (fotoActual < 3) {
        fotoActual++;
        // Actualizar contador
        document.getElementById('contadorFotos').textContent = fotoActual;
        // Limpiar preview y input
        document.getElementById('previewImage').style.display = 'none';
        document.getElementById('clasificacionFoto').value = '';
    } else {
        // Habilitar botón de registro
        const registroBtn = document.querySelector('button[onclick="registrarClasificacion()"]');
        if (registroBtn) {
            registroBtn.disabled = false;
        }
        // Mostrar mensaje de finalización
        alert('Has completado el procesamiento de las 3 fotos. Ahora puedes registrar la clasificación.');
    }
}

async function procesarClasificacionAutomatica() {
    const fileInput = document.getElementById('clasificacionFoto');
    const codigo = document.getElementById('codigo').value;
    
    if (!fileInput.files[0]) {
        alert('Por favor seleccione una imagen para la clasificación');
        return;
    }

    mostrarCarga(true);

    const formData = new FormData();
    formData.append('foto', fileInput.files[0]);
    formData.append('codigo', codigo);

    try {
        const response = await fetch('/procesar_clasificacion_automatica', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        console.log('Respuesta del servidor:', data);

        if (data.success) {
            // Acumular resultados
            acumularResultados(data);
            // Mostrar resultados de la foto actual
            mostrarResultadosClasificacion(data);
            // Preparar para la siguiente foto
            prepararSiguienteFoto();
            // Marcar clasificación automática como completada si es la última foto
            if (fotoActual > 3) {
                clasificacionAutomaticaCompletada = true;
                verificarClasificacionesCompletadas();
                
                // Mostrar indicador visual de clasificación completa
                const statusIndicator = document.getElementById('procesamiento-status');
                if (statusIndicator) {
                    statusIndicator.classList.remove('d-none', 'alert-info');
                    statusIndicator.classList.add('alert-success');
                    
                    // Actualizar mensaje y ocultar spinner
                    const spinner = statusIndicator.querySelector('.spinner-grow');
                    if (spinner) spinner.style.display = 'none';
                    
                    const mensaje = statusIndicator.querySelector('#estado-mensaje');
                    if (mensaje) mensaje.innerHTML = '<i class="fas fa-check-circle me-2"></i>Clasificación automática completada';
                    
                    const detalle = statusIndicator.querySelector('#estado-detalle');
                    if (detalle) detalle.textContent = `Completado el ${data.timestamp || new Date().toLocaleString()}`;
                    
                    // Actualizar barra de progreso
                    const progressBar = statusIndicator.querySelector('#progress-bar');
                    if (progressBar) {
                        progressBar.style.width = '100%';
                        progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                        progressBar.classList.add('bg-success');
                    }
                }
                
                // Habilitar botón de ver detalles por foto si existe
                const verDetallesBtn = document.getElementById('btn-ver-detalles');
                const verDetallesContainer = document.getElementById('ver-detalles-container');
                if (verDetallesBtn && verDetallesContainer) {
                    verDetallesContainer.classList.remove('d-none');
                    verDetallesBtn.classList.remove('disabled');
                }
            }
        } else {
            alert('Error en la clasificación: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error procesando la clasificación');
    } finally {
        mostrarCarga(false);
    }
}

async function registrarClasificacionManual() {
    try {
        const codigo = document.getElementById('codigo').value;
        const clasificacionManual = obtenerDatosManuales();

        // Verificar que haya datos
        const totalManual = Object.values(clasificacionManual).reduce((a, b) => a + b, 0);
        if (totalManual === 0) {
            alert('Debe ingresar al menos un valor en la clasificación manual');
            return;
        }

        mostrarCarga(true);

        // Guardar datos internamente
        const response = await fetch('/guardar_clasificacion_manual', {  // Nuevo endpoint
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                codigo: codigo,
                clasificacion: clasificacionManual
            })
        });

        if (!response.ok) {
            throw new Error('Error al registrar la clasificación manual');
        }

        const data = await response.json();
        
        if (data.success) {
            alert('Clasificación manual registrada exitosamente');
            // Marcar clasificación manual como completada
            clasificacionManualCompletada = true;
            console.log('Clasificación manual completada');
            
            // Deshabilitar el formulario manual
            const manualForm = document.getElementById('manualForm');
            if (manualForm) {
                const inputs = manualForm.querySelectorAll('input[type="number"]');
                inputs.forEach(input => input.disabled = true);
                manualForm.querySelector('button[type="submit"]').disabled = true;
            }
            
            // Verificar estado de clasificaciones
            verificarClasificacionesCompletadas();
        } else {
            throw new Error(data.message || 'Error al registrar la clasificación manual');
        }

    } catch (error) {
        console.error('Error en registrarClasificacionManual:', error);
        alert(error.message || 'Error al registrar la clasificación manual');
    } finally {
        mostrarCarga(false);
    }
}

async function registrarClasificacion() {
    try {
        const codigo = document.getElementById('codigo').value;

        // Verificar que se hayan completado ambas clasificaciones
        if (!clasificacionManualCompletada && !clasificacionAutomaticaCompletada) {
            alert('Debe completar al menos una clasificación (manual o automática) antes de registrar.');
            return;
        }

        mostrarCarga(true);

        // Preparar datos para enviar
        const datosFinales = {
            codigo: codigo,
            resultados_acumulados: resultadosAcumulados,
            resultados_individuales: window.resultadosIndividuales || [],
            clasificacion_manual: obtenerDatosManuales(),
            nombre_proveedor: obtenerNombreProveedor()
        };

        const response = await fetch('/clasificacion/registrar_clasificacion_api', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(datosFinales)
        });

        const data = await response.json();
        
        if (data.success) {
            alert('Clasificación registrada exitosamente');
            // Redirigir a la página de la guía
            window.location.href = data.redirect_url;
        } else {
            alert('Error al registrar la clasificación: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al registrar la clasificación');
    } finally {
        mostrarCarga(false);
    }
}

function obtenerValorInfo(etiqueta) {
    const elementos = document.querySelectorAll('.info-section p');
    for (const elemento of elementos) {
        if (elemento.textContent.includes(etiqueta + ':')) {
            return elemento.textContent.split(':')[1].trim();
        }
    }
    return '';
}

function obtenerDatosManuales() {
    return {
        verde: parseFloat(document.getElementById('verdeManual').value) || 0,
        sobremaduro: parseFloat(document.getElementById('sobreMaduroManual').value) || 0,
        danio_corona: parseFloat(document.getElementById('danioCoronaManual').value) || 0,
        pendunculo_largo: parseFloat(document.getElementById('pendunculoLargoManual').value) || 0,
        podrido: parseFloat(document.getElementById('podridoManual').value) || 0
    };
}

function verificarClasificacionesCompletadas() {
    // Verificar clasificación manual
    const camposManual = ['verdeManual', 'sobreMaduroManual', 'danioCoronaManual', 'pendunculoLargoManual', 'podridoManual'];
    const todosLlenosManual = camposManual.every(campo => {
        const valor = document.getElementById(campo).value;
        return valor !== '' && !isNaN(parseFloat(valor));
    });
    
    clasificacionManualCompletada = todosLlenosManual;
    
    // Verificar clasificación automática
    clasificacionAutomaticaCompletada = window.resultadosIndividuales && window.resultadosIndividuales.length === 3;
    
    // Habilitar o deshabilitar botón de registro
    const botonRegistro = document.querySelector('button[onclick="registrarClasificacion()"]');
    if (botonRegistro) {
        botonRegistro.disabled = !(clasificacionManualCompletada || clasificacionAutomaticaCompletada);
    }
}

async function guardarClasificacionFinal() {
    try {
        mostrarCarga(true);
        const codigo = document.getElementById('codigo').value;
        
        // Verificar que al menos una clasificación esté completada
        if (!clasificacionManualCompletada && !clasificacionAutomaticaCompletada) {
            alert('Debe completar al menos una clasificación (manual o automática) antes de guardar');
            return;
        }

        // Determinar el tipo de clasificación
        let tipo_clasificacion = 'manual';
        if (clasificacionManualCompletada && clasificacionAutomaticaCompletada) {
            tipo_clasificacion = 'ambas';
        } else if (clasificacionAutomaticaCompletada) {
            tipo_clasificacion = 'automatica';
        }

        // Preparar los datos para enviar al backend
        const datosGuardar = {
            codigo: codigo,
            tipo_clasificacion: tipo_clasificacion,
            terminado: "ok"  // Flag para el webhook
        };

        console.log('Guardando clasificación final:', datosGuardar);

        // Hacer la petición al backend
        const response = await fetch('/finalizar_clasificacion', {  // Nuevo endpoint
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(datosGuardar)
        });

        const data = await response.json();
        
        if (response.ok && data.success) {
            alert('Clasificación guardada exitosamente');
            // Redirigir al guia_template
            window.location.href = `/ver_guia/${codigo}`;
        } else {
            throw new Error(data.message || 'Error al guardar la clasificación final');
        }

    } catch (error) {
        console.error('Error en guardarClasificacionFinal:', error);
        alert(error.message || 'Error al guardar la clasificación final');
    } finally {
        mostrarCarga(false);
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM Content Loaded - Configurando event listeners');
    
    // Event listener para el formulario de clasificación automática
    const clasificacionForm = document.getElementById('clasificacionForm');
    if (clasificacionForm) {
        clasificacionForm.addEventListener('submit', function(e) {
            e.preventDefault();
            procesarClasificacionAutomatica();
        });
    }

    // Event listener para el formulario de clasificación manual
    const manualForm = document.getElementById('manualForm');
    if (manualForm) {
        manualForm.addEventListener('submit', function(e) {
            e.preventDefault();
            registrarClasificacionManual();
        });
    }

    // Event listener para el botón de guardar clasificación final
    const btnGuardarClasificacion = document.querySelector('button[onclick="guardarClasificacion()"]');
    if (btnGuardarClasificacion) {
        console.log('Botón de guardar clasificación encontrado');
        // Remover el onclick del HTML
        btnGuardarClasificacion.removeAttribute('onclick');
        // Agregar el event listener
        btnGuardarClasificacion.addEventListener('click', function(e) {
            console.log('Click en botón guardar clasificación');
            e.preventDefault();
            guardarClasificacionFinal();
        });
    } else {
        console.log('No se encontró el botón de guardar clasificación');
    }

    // Event listeners para los checkboxes de tipo de clasificación
    const checkAutomatica = document.getElementById('clasificacionAutomatica');
    const checkManual = document.getElementById('clasificacionManual');
    
    if (checkAutomatica) {
        checkAutomatica.addEventListener('change', function() {
            console.log('Cambio en checkbox automática:', this.checked);
            const seccionAutomatica = document.getElementById('seccionAutomatica');
            if (seccionAutomatica) {
                seccionAutomatica.style.display = this.checked ? 'block' : 'none';
            }
            verificarClasificacionesCompletadas();
        });
    }
    
    if (checkManual) {
        checkManual.addEventListener('change', function() {
            console.log('Cambio en checkbox manual:', this.checked);
            const seccionManual = document.getElementById('seccionManual');
            if (seccionManual) {
                seccionManual.style.display = this.checked ? 'block' : 'none';
            }
            verificarClasificacionesCompletadas();
        });
    }

    // Verificar estado inicial de las clasificaciones
    verificarClasificacionesCompletadas();

    // Agregar event listeners para los campos manuales
    const camposManual = ['verdeManual', 'sobreMaduroManual', 'danioCoronaManual', 'pendunculoLargoManual', 'podridoManual'];
    
    camposManual.forEach(campo => {
        const elemento = document.getElementById(campo);
        if (elemento) {
            elemento.addEventListener('input', verificarClasificacionesCompletadas);
        }
    });
});

function obtenerNombreProveedor() {
    const elemento = document.getElementById('nombreProveedor');
    return elemento ? elemento.value : '';
}

// Función para actualizar el estado visual de las fotos
function actualizarEstadoFotos() {
    for (let i = 1; i <= 3; i++) {
        const estadoFoto = document.getElementById(`estadoFoto${i}`);
        const foto = estadoFotos[`foto${i}`];
        
        if (estadoFoto) {
            estadoFoto.className = `indicator ${foto.procesada ? 'uploaded' : 'pending'}`;
            estadoFoto.nextElementSibling.textContent = `Foto ${i}: ${foto.estado}`;
        }
    }
}

// Función para procesar una foto específica
async function procesarFoto(file, numeroFoto) {
    try {
        mostrarCarga(true);
        
        const formData = new FormData();
        formData.append('foto', file);
        formData.append('numero_foto', numeroFoto);
        formData.append('codigo', document.getElementById('codigo').value);
        
        const response = await fetch('/procesar_clasificacion_automatica', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            estadoFotos[`foto${numeroFoto}`] = {
                procesada: true,
                estado: 'completada',
                imagen: data.imagen_etiquetada
            };
            
            acumularResultados(data);
            mostrarResultadosClasificacion(data);
            actualizarEstadoFotos();
            
            if (numeroFoto < 3) {
                fotoActual++;
            } else {
                clasificacionAutomaticaCompletada = true;
                verificarProcesoCompleto();
            }
            
            return true;
        } else {
            throw new Error(data.message || 'Error en el procesamiento');
        }
    } catch (error) {
        console.error('Error procesando foto:', error);
        estadoFotos[`foto${numeroFoto}`].estado = 'error';
        actualizarEstadoFotos();
        alert(`Error procesando la foto ${numeroFoto}: ${error.message}`);
        return false;
    } finally {
        mostrarCarga(false);
    }
}

// Función para reintentar el procesamiento de una foto
async function reintentarFoto(numeroFoto) {
    const fileInput = document.getElementById('clasificacionFoto');
    if (fileInput.files[0]) {
        await procesarFoto(fileInput.files[0], numeroFoto);
    } else {
        alert('Por favor, seleccione una imagen para procesar');
    }
}

// Función para verificar si el proceso está completo
function verificarProcesoCompleto() {
    const clasificacionAutomaticaCheck = document.getElementById('clasificacionAutomatica');
    const clasificacionManualCheck = document.getElementById('clasificacionManual');
    const btnRegistrar = document.querySelector('button[onclick="registrarClasificacion()"]');
    
    let procesoCompleto = false;
    
    if (clasificacionAutomaticaCheck.checked && clasificacionManualCheck.checked) {
        procesoCompleto = clasificacionAutomaticaCompletada && clasificacionManualCompletada;
    } else if (clasificacionAutomaticaCheck.checked) {
        procesoCompleto = clasificacionAutomaticaCompletada;
    } else if (clasificacionManualCheck.checked) {
        procesoCompleto = clasificacionManualCompletada;
    }
    
    if (btnRegistrar) {
        btnRegistrar.disabled = !procesoCompleto;
    }
    
    return procesoCompleto;
}

// Función para reiniciar el proceso
function reiniciarProceso() {
    if (confirm('¿Está seguro de reiniciar el proceso? Se perderán todos los datos no guardados.')) {
        estadoFotos = {
            foto1: { procesada: false, estado: 'pendiente', imagen: null },
            foto2: { procesada: false, estado: 'pendiente', imagen: null },
            foto3: { procesada: false, estado: 'pendiente', imagen: null }
        };
        
        resultadosAcumulados = {
            total_racimos: 0,
            clasificacion: {
                verde: 0,
                sobremaduro: 0,
                danio_corona: 0,
                pendunculo_largo: 0,
                podrido: 0
            },
            porcentajes: {
                verde: 0,
                sobremaduro: 0,
                danio_corona: 0,
                pendunculo_largo: 0,
                podrido: 0
            },
            imagenes: []
        };
        
        clasificacionManualCompletada = false;
        clasificacionAutomaticaCompletada = false;
        fotoActual = 1;
        
        // Limpiar formularios
        document.getElementById('clasificacionFoto').value = '';
        document.getElementById('manualForm').reset();
        
        // Habilitar campos del formulario manual
        const inputs = document.querySelectorAll('#manualForm input');
        inputs.forEach(input => input.disabled = false);
        
        // Actualizar estado visual
        actualizarEstadoFotos();
        verificarProcesoCompleto();
        
        // Limpiar resultados
        const resultadosDiv = document.getElementById('resultadosClasificacion');
        if (resultadosDiv) {
            resultadosDiv.style.display = 'none';
        }
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Configurar event listeners para el formulario de clasificación automática
    const clasificacionForm = document.getElementById('clasificacionForm');
    if (clasificacionForm) {
        clasificacionForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const fileInput = document.getElementById('clasificacionFoto');
            if (fileInput.files[0]) {
                await procesarFoto(fileInput.files[0], fotoActual);
            }
        });
    }
    
    // Event listeners para los checkboxes de tipo de clasificación
    const checkAutomatica = document.getElementById('clasificacionAutomatica');
    const checkManual = document.getElementById('clasificacionManual');
    
    if (checkAutomatica) {
        checkAutomatica.addEventListener('change', function() {
            const seccionAutomatica = document.getElementById('seccionAutomatica');
            if (seccionAutomatica) {
                seccionAutomatica.style.display = this.checked ? 'block' : 'none';
            }
            verificarProcesoCompleto();
        });
    }
    
    if (checkManual) {
        checkManual.addEventListener('change', function() {
            const seccionManual = document.getElementById('seccionManual');
            if (seccionManual) {
                seccionManual.style.display = this.checked ? 'block' : 'none';
            }
            verificarProcesoCompleto();
        });
    }
    
    // Event listeners para los campos del formulario manual
    const camposManual = document.querySelectorAll('#manualForm input[type="number"]');
    camposManual.forEach(campo => {
        campo.addEventListener('input', verificarProcesoCompleto);
    });
    
    // Inicializar estado de las fotos
    actualizarEstadoFotos();
    verificarProcesoCompleto();
});

/**
 * Verifica el estado de procesamiento de una guía
 * @param {string} codigoGuia - Código de la guía
 */
function checkProcesamiento(codigoGuia) {
    const statusUrl = `/clasificacion/check_procesamiento_status/${codigoGuia}`;
    
    console.log("Verificando estado de procesamiento para guía:", codigoGuia);
    
    // Elementos de interfaz
    const procesamientoStatus = document.getElementById('procesamiento-status');
    const spinner = document.querySelector('#procesamiento-status .spinner-grow');
    const mensaje = document.getElementById('estado-mensaje');
    const detalle = document.getElementById('estado-detalle');
    const progressBar = document.getElementById('progress-bar');
    const btnVerDetalles = document.getElementById('btn-ver-detalles');
    
    // Modal de procesamiento
    const modalProcesando = new bootstrap.Modal(document.getElementById('modal-procesando'));
    const modalProgressBar = document.getElementById('modal-progress-bar');
    const modalCountdown = document.getElementById('modal-countdown');
    
    // Mostrar modal en lugar de la alerta
    modalProcesando.show();
    
    // Iniciar temporizador y actualizar barra de progreso
    let timeLeft = 20;
    let progressValue = 0;
    
    const progressInterval = setInterval(() => {
        progressValue += 5;
        if (modalProgressBar) {
            modalProgressBar.style.width = `${progressValue}%`;
            modalProgressBar.setAttribute('aria-valuenow', progressValue);
        }
    }, 1000);
    
    const countdownInterval = setInterval(() => {
        timeLeft -= 1;
        if (modalCountdown) {
            modalCountdown.textContent = timeLeft;
        }
        
        if (timeLeft <= 0) {
            clearInterval(countdownInterval);
            clearInterval(progressInterval);
            // Recargar la página después de 20 segundos
            window.location.reload();
        }
    }, 1000);
    
    // También seguimos verificando el estado real en el servidor
    const checkInterval = setInterval(function() {
        fetch(statusUrl)
        .then(response => response.json())
        .then(data => {
            console.log("Respuesta de estado:", data);
            
            // Verificar si la clasificación está completa
            if (data.clasificacion_completa === true || data.status === 'completed') {
                console.log("¡Clasificación completada!");
                clearInterval(checkInterval);
                clearInterval(countdownInterval);
                clearInterval(progressInterval);
                
                // Actualizar barra de progreso a 100%
                if (modalProgressBar) {
                    modalProgressBar.style.width = '100%';
                }
                
                // Recargar página con un pequeño retraso
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            }
        })
        .catch(error => {
            console.error("Error al verificar estado:", error);
        });
    }, 3000); // Verificar cada 3 segundos
} 