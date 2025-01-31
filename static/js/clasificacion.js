let clasificacionActual = null;
let imagenesActuales = null;
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

let fotoActual = 1;

let clasificacionManualCompletada = false;
let clasificacionAutomaticaCompletada = false;

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

async function registrarClasificacion() {
    try {
        // Verificaciones iniciales
        if (!resultadosAcumulados || !resultadosAcumulados.porcentajes) {
            alert('No hay datos de clasificación automática completos para registrar');
            return;
        }

        if (!resultadosAcumulados.imagenes || resultadosAcumulados.imagenes.length !== 3) {
            alert('No se han procesado las 3 fotos requeridas');
            return;
        }

        const codigo = document.getElementById('codigo').value;
        const fecha = new Date();

        mostrarCarga(true);

        // Calcular el total de racimos como la suma de los totales individuales
        const totalRacimos = window.resultadosIndividuales ? 
            window.resultadosIndividuales.reduce((sum, resultado) => sum + resultado.total_racimos, 0) : 0;

        // Preparar datos para el webhook en el nuevo formato
        const datosWebhook = {
            codigo_proveedor: codigo,
            url_guia_template: window.location.origin + `/ver_guia/${codigo}`,
            fecha_clasificacion: fecha.toISOString().split('T')[0],
            hora_clasificacion: fecha.toTimeString().split(' ')[0],
            verde_automatica: resultadosAcumulados.clasificacion.verde,
            sobremadura_automatica: resultadosAcumulados.clasificacion.sobremaduro,
            danio_corona_automatica: resultadosAcumulados.clasificacion.danio_corona,
            pendunculo_largo_automatica: resultadosAcumulados.clasificacion.pendunculo_largo,
            podrido_automatica: resultadosAcumulados.clasificacion.podrido,
            cantidad_racimo_automatico: totalRacimos,
            peso_bruto: parseFloat(obtenerValorInfo('Peso Bruto')) || 0,
            codigo_guia: obtenerValorInfo('Guía'),
            nombre: obtenerValorInfo('Proveedor')
        };

        console.log('Enviando datos al webhook:', datosWebhook);

        // URL del webhook de Make
        const webhookUrl = 'https://hook.us2.make.com/ydtogfd3mln2ixbcuam0xrd2m9odfgna';

        const response = await fetch(webhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(datosWebhook)
        });

        if (!response.ok) {
            throw new Error('Error enviando datos al webhook');
        }

        alert('Clasificación automática registrada exitosamente');

        // Marcar clasificación automática como completada
        clasificacionAutomaticaCompletada = true;
        verificarClasificacionesCompletadas();

        // Deshabilitar el botón de registro automático y el checkbox
        document.querySelector('button[onclick="registrarClasificacion()"]').disabled = true;
        document.getElementById('clasificacionAutomatica').disabled = true;

    } catch (error) {
        console.error('Error en registrarClasificacion:', error);
        alert(error.message || 'Error al registrar la clasificación');
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
        verde: parseInt(document.getElementById('racimo_verde').value) || 0,
        sobremaduro: parseInt(document.getElementById('racimo_sobremaduro').value) || 0,
        danio_corona: parseInt(document.getElementById('racimo_danio_corona').value) || 0,
        pendunculo_largo: parseInt(document.getElementById('racimo_pendunculo_largo').value) || 0,
        podrido: parseInt(document.getElementById('racimo_podrido').value) || 0
    };
}

async function registrarClasificacionManual() {
    try {
        const codigo = document.getElementById('codigo').value;
        const clasificacionManual = obtenerDatosManuales();
        const fecha = new Date();

        // Verificar que haya datos
        const totalManual = Object.values(clasificacionManual).reduce((a, b) => a + b, 0);
        if (totalManual === 0) {
            alert('Debe ingresar al menos un valor en la clasificación manual');
            return;
        }

        mostrarCarga(true);

        // Obtener valores de la información general
        const cantidadRacimosInicial = parseInt(obtenerValorInfo('Cantidad de Racimos')) || 0;
        const totalRacimosClasificados = cantidadRacimosInicial >= 1000 ? 100 : 28;
        const pesoBruto = parseFloat(obtenerValorInfo('Peso Bruto')) || 0;
        const codigoGuia = obtenerValorInfo('Guía');
        const nombre = obtenerValorInfo('Proveedor');

        // Preparar datos para el webhook en el formato correcto
        const datosWebhook = {
            codigo_proveedor: codigo,
            url_guia_template: window.location.origin + `/ver_guia/${codigo}`,
            fecha_clasificacion: fecha.toISOString().split('T')[0],
            hora_clasificacion: fecha.toTimeString().split(' ')[0],
            verde_manual: clasificacionManual.verde,
            sobremadura_manual: clasificacionManual.sobremaduro,
            danio_corona_manual: clasificacionManual.danio_corona,
            pendunculo_largo_manual: clasificacionManual.pendunculo_largo,
            podrido_manual: clasificacionManual.podrido,
            cantidad_racimo_manual: totalRacimosClasificados,
            peso_bruto: pesoBruto,
            codigo_guia: codigoGuia,
            nombre: nombre
        };

        console.log('Enviando datos al webhook (manual):', datosWebhook);

        // URL del webhook de Make
        const webhookUrl = 'https://hook.us2.make.com/ydtogfd3mln2ixbcuam0xrd2m9odfgna';

        const response = await fetch(webhookUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(datosWebhook)
        });

        if (!response.ok) {
            throw new Error('Error enviando datos al webhook');
        }

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

    } catch (error) {
        console.error('Error en registrarClasificacionManual:', error);
        alert(error.message || 'Error al registrar la clasificación manual');
    } finally {
        mostrarCarga(false);
    }
}

function verificarClasificacionesCompletadas() {
    console.log('Verificando estado de clasificaciones...');
    const checkAutomatica = document.getElementById('clasificacionAutomatica');
    const checkManual = document.getElementById('clasificacionManual');
    const btnGuardarClasificacion = document.querySelector('button[onclick="guardarClasificacion()"]');
    
    if (!btnGuardarClasificacion) {
        console.log('Botón de guardar clasificación no encontrado');
        return;
    }

    console.log('Estado actual:', {
        'Manual completada': clasificacionManualCompletada,
        'Automática completada': clasificacionAutomaticaCompletada,
        'Check manual': checkManual?.checked,
        'Check automática': checkAutomatica?.checked
    });

    // Verificar si todas las clasificaciones seleccionadas están completadas
    let todasCompletadas = false;

    // Si la clasificación manual está seleccionada y completada
    if (checkManual?.checked && clasificacionManualCompletada) {
        todasCompletadas = true;
    }
    
    // Si la clasificación automática está seleccionada y completada
    if (checkAutomatica?.checked && clasificacionAutomaticaCompletada) {
        todasCompletadas = true;
    }

    // Si ninguna clasificación está seleccionada
    if (!checkManual?.checked && !checkAutomatica?.checked) {
        todasCompletadas = false;
    }

    console.log('¿Todas las clasificaciones completadas?', todasCompletadas);
    btnGuardarClasificacion.disabled = !todasCompletadas;
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

        // Preparar los datos para enviar al backend
        const datosGuardar = {
            codigo: codigo,
            tipo_clasificacion: clasificacionManualCompletada && clasificacionAutomaticaCompletada ? 'ambas' :
                               clasificacionManualCompletada ? 'manual' : 'automatica'
        };

        console.log('Guardando clasificación final:', datosGuardar);

        // Hacer la petición al backend para guardar y generar el PDF
        const response = await fetch('/guardar_clasificacion_final', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(datosGuardar)
        });

        if (!response.ok) {
            throw new Error('Error al guardar la clasificación');
        }

        const data = await response.json();
        
        if (data.success) {
            alert('Clasificación guardada exitosamente');
            // Redirigir al guia_template
            window.location.href = `/ver_guia/${codigo}`;
        } else {
            throw new Error(data.message || 'Error al guardar la clasificación');
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
}); 