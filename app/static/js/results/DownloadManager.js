import { App } from './App.js';

export const DownloadManager = {
    init: function() {
        const consolidatedBtn = document.getElementById('download-consolidated-btn');
        const allBtn = document.getElementById('download-all-btn');
        const newUploadBtn = document.querySelector('a[title="Process new files"]');

        if (newUploadBtn) {
            newUploadBtn.addEventListener('click', async (e) => {
                e.preventDefault();
                const sessionId = newUploadBtn.href.split('/').pop();
                if (sessionId) {
                    try {
                        await fetch(`/cleanup/${sessionId}`, { method: 'POST' });
                    } catch (error) {
                        console.error('Cleanup failed:', error);
                    }
                }
                window.location.href = '/';
            });
        }

        const handleDownload = (button, url, defaultFilename) => {
            if (button.classList.contains('loading')) return;

            button.classList.add('loading');
            this.clearMessages();

            fetch(url)
                .then(response => {
                    if (!response.ok) {
                        throw new Error(response.status === 404 ? 'File not found' : 'Download failed');
                    }
                    const filename = response.headers.get('X-Filename') || defaultFilename;
                    return response.blob().then(blob => ({ blob, filename }));
                })
                .then(({ blob, filename }) => {
                    const link = document.createElement('a');
                    const objectUrl = window.URL.createObjectURL(blob);
                    link.href = objectUrl;
                    link.download = filename;
                    link.style.display = 'none';

                    document.body.appendChild(link);
                    link.click();
                    document.body.removeChild(link);

                    setTimeout(() => window.URL.revokeObjectURL(objectUrl), 100);

                    button.classList.remove('loading');
                    this.showSuccess(`Downloaded: ${filename}`);
                })
                .catch(error => {
                    button.classList.remove('loading');
                    this.showError(error.message);
                });
        };

        if (consolidatedBtn) {
            consolidatedBtn.addEventListener('click', (e) => {
                e.preventDefault();
                handleDownload(consolidatedBtn, `/api/consolidate/${SESSION_ID}`, 'consolidated_valid_features.geojson');
            });
        }

        if (allBtn) {
            allBtn.addEventListener('click', (e) => {
                e.preventDefault();
                handleDownload(allBtn, `/download/${SESSION_ID}`, 'eudr_results.zip');
            });
        }
    },

    showError: function(message) {
        this.showMessage(message, 'error');
    },

    showSuccess: function(message) {
        this.showMessage(message, 'success');
    },

    showMessage: function(message, type) {
        let errorElement = document.querySelector('.error-message');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'error-message';
            document.querySelector('.header-actions').appendChild(errorElement);
        }

        errorElement.textContent = message;
        errorElement.classList.remove('active', 'success');
        errorElement.classList.add('active', type);

        setTimeout(() => {
            errorElement.classList.remove('active', type);
        }, type === 'success' ? 3000 : 5000);
    },

    clearMessages: function() {
        const errorElement = document.querySelector('.error-message');
        if (errorElement) {
            errorElement.classList.remove('active', 'success');
        }
    }
};
