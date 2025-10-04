document.addEventListener('DOMContentLoaded', function () {
    const uploadFieldset = document.getElementById('upload-fieldset');
    const progressSection = document.getElementById('progress-section');
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const fileListArea = document.getElementById('file-list-area');
    const fileListContainer = document.getElementById('file-list-container');
    const processBtn = document.getElementById('process-btn');
    const progressBar = document.getElementById('progress-bar');
    const statusMessage = document.getElementById('status-message');
    const progressStep = document.getElementById('progress-step');
    const resultsLink = document.getElementById('results-link');

    let selectedFiles = [];

    dropZone.addEventListener('click', (e) => {
        if (e.target.tagName === 'LABEL' || e.target.closest('label')) {
            return;
        }
        fileInput.click();
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('active');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('active');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('active');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', () => {
        handleFiles(fileInput.files);
    });

    function handleFiles(files) {
        selectedFiles = Array.from(files);
        updateFileList();
    }

    function updateFileList() {
        if (selectedFiles.length > 0) {
            fileListArea.classList.remove('hidden');
            fileListContainer.innerHTML = '';
            
            const filesToShow = selectedFiles.slice(0, 10);
            filesToShow.forEach(file => {
                const fileItem = document.createElement('div');
                fileItem.className = 'file-item';
                fileItem.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"></path>
                        <polyline points="14 2 14 8 20 8"></polyline>
                    </svg>
                    <span>${file.webkitRelativePath || file.name}</span>
                `;
                fileListContainer.appendChild(fileItem);
            });

            if (selectedFiles.length > 10) {
                const moreFilesItem = document.createElement('div');
                moreFilesItem.className = 'file-item more-files';
                moreFilesItem.textContent = `...and ${selectedFiles.length - 10} more file(s).`;
                fileListContainer.appendChild(moreFilesItem);
            }

            processBtn.disabled = false;
        } else {
            fileListArea.classList.add('hidden');
            fileListContainer.innerHTML = '';
            processBtn.disabled = true;
        }
    }

    processBtn.addEventListener('click', () => {
        uploadFieldset.disabled = true;
        progressSection.classList.remove('hidden');
        
        const formData = new FormData();
        selectedFiles.forEach(file => {
            formData.append('files', file, file.webkitRelativePath || file.name);
        });
        
        formData.append('simplify', document.getElementById('simplify').checked);
        formData.append('autofix', document.getElementById('autofix').checked);
        formData.append('identify_candidates', document.getElementById('identify_candidates').checked);
        
        fetch('/process', { method: 'POST', body: formData })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                pollStatus(data.session_id);
            })
            .catch(handleError);
    });

    function pollStatus(sessionId) {
        let lastProgress = 0;
        
        const smoothProgressBar = (targetProgress) => {
            const currentProgress = parseInt(progressBar.style.width) || 0;
            if (targetProgress < currentProgress) return;
            
            const step = (targetProgress - currentProgress) / 10;
            let current = currentProgress;
            
            const animate = () => {
                if (current < targetProgress) {
                    current = Math.min(current + step, targetProgress);
                    progressBar.style.width = `${current}%`;
                    requestAnimationFrame(animate);
                }
            };
            
            if (step > 0) {
                animate();
            }
        };
        
        const interval = setInterval(() => {
            fetch(`/status/${sessionId}`)
                .then(response => response.json())
                .then(status => {
                    const currentProgress = status.progress || 0;

                    if (currentProgress >= lastProgress) {
                        smoothProgressBar(currentProgress);
                        lastProgress = currentProgress;
                    }
                    
                    statusMessage.textContent = status.message || '...';
                    progressStep.textContent = status.step || 'Processing...';
                    
                    if (status.progress >= 100) {
                        clearInterval(interval);
                        if (status.error) {
                            handleError(new Error(status.message));
                        } else {
                            progressStep.textContent = "Processing Complete!";
                            statusMessage.textContent = "Results are ready for review.";
                            progressBar.classList.add('complete');
                            resultsLink.href = `/results/${sessionId}`;
                            resultsLink.classList.remove('disabled');
                            resultsLink.classList.add('primary');
                        }
                    }
                })
                .catch(error => {
                    clearInterval(interval);
                    handleError(error);
                });
        }, 2000);
    }

    function handleError(error) {
        console.error('Processing error:', error);
        progressStep.textContent = 'An Error Occurred';
        statusMessage.textContent = error.message;
        progressBar.style.width = '100%';
        progressBar.classList.add('error');
        progressBar.classList.remove('complete');
        
        resultsLink.textContent = "Retry";
        resultsLink.href = "/"; 
        resultsLink.classList.remove('disabled', 'primary');

        uploadFieldset.disabled = false;
    }
});