import { App } from './App.js';

document.addEventListener('DOMContentLoaded', function() {
    if (typeof SESSION_ID === 'undefined') {
        showError('Session ID missing. Please refresh the page.');
        return;
    }

    const requiredLibraries = [
        { name: 'jQuery', check: () => typeof $ !== 'undefined' },
        { name: 'Leaflet', check: () => typeof L !== 'undefined' },
        { name: 'Chart.js', check: () => typeof Chart !== 'undefined' }
    ];

    for (const lib of requiredLibraries) {
        if (!lib.check()) {
            showError(`${lib.name} library not loaded. Please refresh the page.`);
            return;
        }
    }

    try {
        App.init();
    } catch (error) {
        console.error('Application initialization failed:', error);
        showError('Failed to initialize application. Please refresh the page.');
    }
});

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message active';
    errorDiv.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background-color: #f8d7da;
        color: #721c24;
        padding: 12px 20px;
        border: 1px solid #f5c6cb;
        border-radius: 6px;
        z-index: 9999;
        max-width: 400px;
    `;
    errorDiv.textContent = message;
    document.body.appendChild(errorDiv);

    setTimeout(() => {
        if (errorDiv.parentNode) {
            errorDiv.parentNode.removeChild(errorDiv);
        }
    }, 10000);
}
