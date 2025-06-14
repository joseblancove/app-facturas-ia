// static/app.js - VERSIÓN FINAL REFACTORIZADA
document.addEventListener('DOMContentLoaded', () => {
    // Referencias a Elementos del DOM
    const form = document.getElementById('invoice-form');
    const prepareBtn = document.getElementById('prepare-btn');
    const uploadSection = document.getElementById('upload-section');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const browseBtn = document.getElementById('browse-btn');
    const fileList = document.getElementById('file-list');
    const uploadBtn = document.getElementById('upload-btn');
    const resetBtn = document.getElementById('reset-btn');
    const statusMessage = document.getElementById('status-message');
    const mainTitle = document.getElementById('main-title');
    
    let fileQueue = [];

    // --- MANEJO DE EVENTOS ---
    function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => dropZone.addEventListener(eventName, preventDefaults, false));
    ['dragenter', 'dragover'].forEach(e => dropZone.addEventListener(e, () => dropZone.classList.add('highlight'), false));
    ['dragleave', 'drop'].forEach(e => dropZone.addEventListener(e, () => dropZone.classList.remove('highlight'), false));
    
    dropZone.addEventListener('drop', e => handleFiles(e.dataTransfer.files));
    browseBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', e => {
        handleFiles(e.target.files);
        e.target.value = '';
    });

    fileList.addEventListener('click', (e) => {
        if (e.target && e.target.classList.contains('delete-btn')) {
            const fileIdToRemove = e.target.dataset.fileId;
            fileQueue = fileQueue.filter(file => `file-${file.name}-${file.size}` !== fileIdToRemove);
            renderFileList();
        }
    });

    prepareBtn.addEventListener('click', () => {
        if (!form.checkValidity()) { form.reportValidity(); return; }
        enterUploadMode();
    });
    
    uploadBtn.addEventListener('click', () => {
        if (fileQueue.length === 0) { alert('Por favor, selecciona o arrastra al menos un documento.'); return; }
        processAndConsolidate();
    });

    resetBtn.addEventListener('click', () => resetToInitialState());

    // --- FUNCIONES DE LA INTERFAZ ---
    function handleFiles(files) {
        const newFiles = [...files].filter(file => !fileQueue.some(existing => existing.name === file.name && existing.size === file.size));
        fileQueue.push(...newFiles);
        renderFileList();
    }

    function enterUploadMode() {
        Array.from(form.elements).forEach(el => {
            if(el.tagName === 'INPUT' || el.tagName === 'SELECT') { el.disabled = true; }
        });
        prepareBtn.style.display = 'none';
        mainTitle.textContent = `Cargando para: ${document.getElementById('entity_name').value}`;
        uploadSection.style.display = 'block';
    }

    function resetToInitialState() {
        fileQueue = [];
        fileList.innerHTML = '';
        form.reset();
        Array.from(form.elements).forEach(el => el.disabled = false);
        prepareBtn.style.display = 'block';
        uploadSection.style.display = 'none';
        resetBtn.style.display = 'none';
        statusMessage.style.display = 'none';
        mainTitle.textContent = 'Registrar Lote de Documentos';
    }

    function renderFileList() {
        fileList.innerHTML = '';
        fileQueue.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.classList.add('file-item');
            const fileId = `file-${file.name}-${file.size}`;
            fileItem.innerHTML = `<span>${file.name}</span><button type="button" class="delete-btn" data-file-id="${fileId}">&times;</button>`;
            fileList.appendChild(fileItem);
        });
        if (fileQueue.length > 0) uploadBtn.style.display = 'block';
        else uploadBtn.style.display = 'none';
    }

    async function processAndConsolidate() {
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Analizando y Consolidando...';
        statusMessage.textContent = `Enviando ${fileQueue.length} documentos a la IA...`;
        statusMessage.className = 'alert info-alert';
        statusMessage.style.display = 'block';

        const formData = new FormData();
        // Nombres de campos actualizados para la lógica de facturas
        formData.append('entity_name', document.getElementById('entity_name').value);
        formData.append('project_name', document.getElementById('project_name').value);
        formData.append('doc_type', document.getElementById('doc_type').value);
        formData.append('accounting_month', document.getElementById('accounting_month').value);
        formData.append('batch_id', document.getElementById('batch_id').value);
        
        fileQueue.forEach(file => {
            // Nombre del campo de archivo actualizado
            formData.append('invoice_images[]', file, file.name);
        });

        try {
            const response = await fetch('/upload', { method: 'POST', body: formData });
            const data = await response.json();
            if (response.ok && data.status === 'success') {
                statusMessage.textContent = '¡Éxito! Lote consolidado y guardado.';
                statusMessage.className = 'alert success-alert';
                uploadBtn.style.display = 'none';
                resetBtn.style.display = 'block';
            } else {
                throw new Error(data.message || 'Error desconocido del servidor.');
            }
        } catch (error) {
            statusMessage.textContent = `Error: ${error.message}`;
            statusMessage.className = 'alert error-alert';
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Analizar y Consolidar';
        }
    }
});
