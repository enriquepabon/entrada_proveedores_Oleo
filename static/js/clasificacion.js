let clasificacionActual = null;
let imagenesActuales = null;

function mostrarResultadosClasificacion(data) {
    // Mostrar el div de resultados
    document.getElementById('resultadosClasificacion').style.display = 'block';
    
    // Actualizar conteos
    document.getElementById('conteoVerde').textContent = data.clasificacion.verde;
    document.getElementById('conteoSobremaduro').textContent = data.clasificacion.sobremaduro;
    document.getElementById('conteoDanioCorona').textContent = data.clasificacion.danio_corona;
    document.getElementById('conteoPendunculoLargo').textContent = data.clasificacion.pendunculo_largo;
    document.getElementById('conteoPodrido').textContent = data.clasificacion.podrido;
    
    // Mostrar imágenes
    const contenedorImagenes = document.getElementById('imagenesClasificacion');
    contenedorImagenes.innerHTML = '';
    
    if (data.imagenes) {
        Object.entries(data.imagenes).forEach(([tipo, filename]) => {
            const img = document.createElement('img');
            img.src = `/static/uploads/${filename}`;
            img.className = 'img-fluid mb-3';
            img.alt = `Imagen ${tipo}`;
            contenedorImagenes.appendChild(img);
        });
    }
    
    // Guardar datos para registro posterior
    clasificacionActual = data.clasificacion;
    imagenesActuales = data.imagenes;
    
    // Mostrar botón de registro
    document.getElementById('btnRegistrarClasificacion').style.display = 'block';
}

async function procesarClasificacionAutomatica() {
    const fileInput = document.getElementById('clasificacionFoto');
    const codigo = document.getElementById('codigo').value;
    
    if (!fileInput.files[0]) {
        alert('Por favor seleccione una imagen para la clasificación');
        return;
    }

    const formData = new FormData();
    formData.append('foto', fileInput.files[0]);
    formData.append('codigo', codigo);

    try {
        const response = await fetch('/procesar_clasificacion_automatica', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Mostrar los resultados
            mostrarResultadosClasificacion(data);
            // Llenar el formulario manual si existe
            if (typeof llenarFormularioManual === 'function') {
                llenarFormularioManual(data.clasificacion);
            }
        } else {
            alert('Error en la clasificación: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error procesando la clasificación');
    }
}

async function registrarClasificacion() {
    if (!clasificacionActual || !imagenesActuales) {
        alert('No hay resultados de clasificación para registrar');
        return;
    }
    
    const codigo = document.getElementById('codigo').value;
    
    try {
        const response = await fetch('/guardar_clasificacion_automatica', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                codigo: codigo,
                clasificacion: clasificacionActual,
                imagenes: imagenesActuales
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            window.location.href = data.redirect_url;
        } else {
            alert('Error registrando la clasificación: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error registrando la clasificación');
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    const clasificacionForm = document.getElementById('clasificacionForm');
    if (clasificacionForm) {
        clasificacionForm.addEventListener('submit', function(e) {
            e.preventDefault();
            procesarClasificacionAutomatica();
        });
    }
    
    const btnRegistrar = document.getElementById('btnRegistrarClasificacion');
    if (btnRegistrar) {
        btnRegistrar.addEventListener('click', registrarClasificacion);
    }
}); 