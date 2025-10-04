import { DashboardView } from './DashboardView.js';
import { GisView } from './GisView.js';
import { DownloadManager } from './DownloadManager.js';
import { TableManager } from './TableManager.js';

export const App = {
    state: {
        map: null,
        detailedTableApi: null,
        currentReviewLayer: null,
        currentCandidateLayer: null,
        convertedPointsLayer: null,
        highlightedFeatureLayer: null,
        chart: null,
        data: {},
        layersCache: {},
        featureCounts: { total: 0, review: 0, candidate: 0, valid: 0, fixed: 0 },
        isDataLoaded: false,
        hasErrors: false
    },

    init: function() {
        this.ViewManager.init();
        this.showLoadingState();
        
        this.loadInitialData()
            .then(() => {
                this.state.isDataLoaded = true;
                this.hideLoadingState();
                this.initializeComponents();
            })
            .catch(error => {
                this.state.hasErrors = true;
                this.hideLoadingState();
                this.handleInitializationError(error);
            });
    },

    showLoadingState: function() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.classList.remove('hidden');
        }
    },

    hideLoadingState: function() {
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.classList.add('hidden');
        }
    },

    initializeComponents: function() {
        if (!this.state.isDataLoaded) {
            this.showNoDataMessage();
            return;
        }

        try {
            DashboardView.init();
            GisView.init();
            TableManager.init();
            DownloadManager.init();
        } catch (error) {
            console.error('Component initialization failed:', error);
            this.showError('Failed to initialize dashboard components');
        }
    },

    handleInitializationError: function(error) {
        const errorMessage = error.message || 'Application initialization failed';
        console.error('App initialization error:', error);
        
        this.showError(errorMessage);
        this.showNoDataMessage();
    },

    loadInitialData: function() {
        if (typeof SESSION_ID === 'undefined') {
            return Promise.reject(new Error('Session ID not found'));
        }

        return fetch(`/api/data/${SESSION_ID}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                
                this.state.data = this.validateAndSanitizeData(data);
                return this.state.data;
            })
            .catch(error => {
                console.error('Data loading failed:', error);
                this.state.data = this.createEmptyDataStructure();
                throw error;
            });
    },

    validateAndSanitizeData: function(data) {
        if (!data || typeof data !== 'object') {
            console.warn('Invalid data format, using empty structure');
            return this.createEmptyDataStructure();
        }

        const sanitized = {
            summary_report_data: Array.isArray(data.summary_report_data) ? data.summary_report_data : [],
            detailed_report_data: Array.isArray(data.detailed_report_data) ? data.detailed_report_data : [],
            map_layers: Array.isArray(data.map_layers) ? data.map_layers : [],
            clean_file_count: typeof data.clean_file_count === 'number' ? data.clean_file_count : 0
        };
        return sanitized;
    },

    createEmptyDataStructure: function() {
        return {
            summary_report_data: [],
            detailed_report_data: [],
            map_layers: [],
            clean_file_count: 0
        };
    },

    showNoDataMessage: function() {
        const dashboardView = document.getElementById('dashboard-view');
        if (dashboardView && !dashboardView.querySelector('.no-data-message')) {
            const message = document.createElement('div');
            message.className = 'no-data-message';
            message.style.cssText = `
                text-align: center;
                padding: 3rem;
                color: #6c757d;
                font-size: 1.1rem;
            `;
            message.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M16 16s-1.5-2-4-2-4 2-4 2"></path>
                    <line x1="9" y1="9" x2="9.01" y2="9"></line>
                    <line x1="15" y1="9" x2="15.01" y2="9"></line>
                </svg>
                <h3>No Data Available</h3>
                <p>The processing session may not be complete or may have failed.<br>
                Please check the processing status or try uploading files again.</p>
                <a href="/" class="button primary" style="margin-top: 1rem;">Upload New Files</a>
            `;
            dashboardView.insertBefore(message, dashboardView.firstChild);
        }
    },

    showError: function(message) {
        if (typeof DownloadManager !== 'undefined' && DownloadManager.showError) {
            DownloadManager.showError(message);
        } else {
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
            errorDiv.textContent = `Error: ${message}`;
            document.body.appendChild(errorDiv);
            
            setTimeout(() => {
                if (errorDiv.parentNode) {
                    errorDiv.parentNode.removeChild(errorDiv);
                }
            }, 10000);
        }
    },

    ViewManager: {
        init: function() {
            const switcher = document.querySelector('.view-switcher');
            if (!switcher) return;

            switcher.addEventListener('click', (e) => {
                if (e.target.tagName !== 'BUTTON' || !e.target.dataset.view) return;
                
                this.switchView(e.target.dataset.view);
                
                const currentActive = e.target.parentNode.querySelector('.active');
                if (currentActive) {
                    currentActive.classList.remove('active');
                }
                e.target.classList.add('active');
            });
        },

        switchView: function(targetView) {
            const dashboardView = document.getElementById('dashboard-view');
            const gisView = document.getElementById('gis-view');
            
            if (!dashboardView || !gisView) return;
            
            dashboardView.classList.toggle('active', targetView === 'dashboard');
            gisView.classList.toggle('active', targetView === 'gis');
            
            if (targetView === 'gis' && App.state.map) {
                setTimeout(() => {
                    App.state.map.invalidateSize();
                }, 100);
            }
            
            try {
                if ($.fn.dataTable && $.fn.dataTable.tables) {
                    $.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
                }
            } catch (error) {
                // Ignore DataTable adjustment errors
            }
        }
    }
};