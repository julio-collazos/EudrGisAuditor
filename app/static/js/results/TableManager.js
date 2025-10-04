import { App } from './App.js';
import { Utils } from './Utils.js';

export const TableManager = {
    init: function() {
        try {
            this.initDetailedTable();
        } catch (error) {
            console.error('TableManager initialization failed:', error);
            this.showTableError('Failed to initialize conversion table');
        }
    },

    initDetailedTable: function() {
        const tableElement = document.getElementById('detailed-table');
        if (!tableElement) return;

        if (!App.state.data || !App.state.data.detailed_report_data) {
            this.showEmptyTableState();
            return;
        }

        const allData = App.state.data.detailed_report_data || [];
        const candidatesData = allData.filter(row => 
            row && row.final_status === 'Candidate for Conversion'
        );

        const tableContainer = tableElement.closest('.panel-content');
        if (tableContainer) {
            const existingMessage = tableContainer.querySelector('.no-candidates-message');
            if (existingMessage) {
                existingMessage.remove();
            }
        }

        if (candidatesData.length === 0) {
            this.showNoCandidatesMessage();
            return;
        }

        tableElement.style.display = 'table';
        const tableWrapper = tableElement.closest('.dataTables_wrapper');
        if (tableWrapper) {
            tableWrapper.style.display = 'block';
        }

        try {
            if ($.fn.DataTable.isDataTable('#detailed-table')) {
                $('#detailed-table').DataTable().destroy();
            }

            App.state.detailedTableApi = $('#detailed-table').DataTable({
                data: candidatesData,
                columns: [
                    { 
                        data: 'qa_assistant_id', 
                        title: 'Assistant ID'
                    },
                    { 
                        data: 'reason_notes', 
                        className: 'notes', 
                        title: 'Diagnosis'
                    },
                    {
                        data: 'attribute_status',
                        render: data => data ? Utils.createAttributePills(data) : 'N/A',
                        title: 'Attributes'
                    },
                    {
                        data: 'original_filename',
                        className: 'notes',
                        title: 'Original File'
                    },
                    {
                        data: null,
                        defaultContent: '<button class="action-btn convert-btn">Convert</button>',
                        orderable: false,
                        title: 'Actions'
                    }
                ],
                rowCallback: function(row, data) {
                    row.dataset.qaId = data.qa_assistant_id;
                },
                language: Utils.getDataTablesLang(),
                pageLength: 10
            });

            this.updateConvertAllButton(candidatesData.length);

        } catch (error) {
            console.error('Failed to initialize detailed table:', error);
            this.showTableError('Failed to load conversion candidates');
        }
    },

    validateDataForTable: function() {
        if (!App.state.data) {
            console.error('No app data available for table');
            return false;
        }

        if (!Array.isArray(App.state.data.detailed_report_data)) {
            console.error('Invalid detailed report data format');
            return false;
        }

        return true;
    },

    updateConvertAllButton: function(candidateCount) {
        const convertAllBtn = document.getElementById('convert-all-btn');
        if (convertAllBtn) {
            if (candidateCount > 0) {
                convertAllBtn.style.display = 'block';
                convertAllBtn.textContent = `Convert All ${candidateCount} to Points`;
                convertAllBtn.disabled = false;
            } else {
                convertAllBtn.style.display = 'none';
            }
        }
    },

    showEmptyTableState: function() {
        const tableContainer = document.querySelector('#detailed-table').closest('.panel-content');
        if (tableContainer) {
            const message = document.createElement('div');
            message.className = 'empty-state-message';
            message.style.cssText = 'text-align: center; padding: 3rem 1rem; color: #6c757d;';
            message.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path>
                    <circle cx="12" cy="12" r="4"></circle>
                </svg>
                <h4>No Data Available</h4>
                <p>Unable to load table data. Please check if the processing completed successfully.</p>
            `;
            tableContainer.appendChild(message);
        }
    },

    showNoCandidatesMessage: function() {
        const tableElement = document.getElementById('detailed-table');
        const tableContainer = tableElement?.closest('.panel-content');
        
        if (!tableContainer) return;
        
        if (tableElement) {
            tableElement.style.display = 'none';
        }
        
        const tableWrapper = tableElement?.closest('.dataTables_wrapper');
        if (tableWrapper) {
            tableWrapper.style.display = 'none';
        }

        const existingMessage = tableContainer.querySelector('.no-candidates-message');
        if (existingMessage) {
            existingMessage.remove();
        }

        const message = document.createElement('div');
        message.className = 'no-candidates-message';
        message.style.cssText = 'text-align: center; padding: 3rem 1rem; color: #28a745;';
        message.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path>
                <path d="m9 12 2 2 4-4"></path>
            </svg>
            <h4>All Clear!</h4>
            <p>No candidates found for conversion. All polygons meet the size requirements.</p>
        `;
        tableContainer.appendChild(message);

        this.updateConvertAllButton(0);
    },

    showTableError: function(message) {
        const tableContainer = document.querySelector('#detailed-table').closest('.panel-content');
        if (tableContainer) {
            const errorMessage = document.createElement('div');
            errorMessage.className = 'table-error-message';
            errorMessage.style.cssText = 'text-align: center; padding: 3rem 1rem; color: #dc3545;';
            errorMessage.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="15" y1="9" x2="9" y2="15"></line>
                    <line x1="9" y1="9" x2="15" y2="15"></line>
                </svg>
                <h4>Error Loading Table</h4>
                <p>${message}</p>
                <button onclick="location.reload()" class="button primary" style="margin-top: 1rem;">Reload Page</button>
            `;
            tableContainer.appendChild(message);
        }
    }
};