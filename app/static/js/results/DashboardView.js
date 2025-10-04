import { App } from './App.js';
import { Utils } from './Utils.js';

export const DashboardView = {
    init: function() {
        if (!this.validateDataAvailable()) {
            this.showNoDataState();
            return;
        }

        try {
            this.calculateCounts();
            this.renderSummaryCards();
            this.initSummaryTable();
            this.initStatusChart();
        } catch (error) {
            console.error('DashboardView initialization failed:', error);
            this.showErrorState(error.message);
        }
    },

    validateDataAvailable: function() {
        if (!App.state.data) {
            console.error("DashboardView: No data object available");
            return false;
        }

        if (!Array.isArray(App.state.data.detailed_report_data)) {
            console.error("DashboardView: detailed_report_data is not an array");
            return false;
        }

        if (!Array.isArray(App.state.data.summary_report_data)) {
            console.error("DashboardView: summary_report_data is not an array");
            return false;
        }

        return true;
    },

    calculateCounts: function() {
        const data = App.state.data.detailed_report_data || [];
        
        App.state.featureCounts = {
            total: data.length,
            review: data.filter(r => r && r.final_status === 'Requires Review').length,
            candidate: data.filter(r => r && r.final_status === 'Candidate for Conversion').length,
            valid: data.filter(r => r && r.final_status === 'Valid').length,
            fixed: data.filter(r => 
                r && r.action_taken && r.action_taken.toLowerCase().includes('auto-fixed')
            ).length
        };

        console.log('Feature counts calculated:', App.state.featureCounts);
    },

    renderSummaryCards: function() {
        const container = document.getElementById('summary-cards');
        if (!container) {
            console.warn('Summary cards container not found');
            return;
        }

        const counts = App.state.featureCounts;
        const actualErrors = counts.review + counts.candidate;

        const cards = [
            { title: 'Total Entities Analyzed', value: counts.total, icon: 'layers' },
            { 
                title: 'Entities with Detected Errors', 
                value: actualErrors, 
                styleClass: actualErrors > 0 ? 'is-warning' : '',
                icon: 'alert-triangle'
            },
            { 
                title: 'Automatically Corrected Errors', 
                value: counts.fixed, 
                styleClass: counts.fixed > 0 ? 'is-success' : '',
                icon: 'check-circle'
            },
            { 
                title: 'Require Manual Review', 
                value: counts.review, 
                styleClass: counts.review > 0 ? 'is-danger' : '',
                icon: 'eye'
            }
        ];

        container.innerHTML = cards.map(card => `
            <div class="summary-card ${card.styleClass || ''}">
                <div class="card-header">
                    <h4>${card.title}</h4>
                    <div class="card-icon">${this.getIconSvg(card.icon)}</div>
                </div>
                <p class="value">${card.value}</p>
            </div>
        `).join('');
    },

    getIconSvg: function(iconName) {
        const icons = {
            'layers': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>',
            'alert-triangle': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
            'check-circle': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"></path><path d="m9 12 2 2 4-4"></path></svg>',
            'eye': '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg>'
        };
        return icons[iconName] || '';
    },

    initSummaryTable: function() {
        const tableElement = document.getElementById('summary-table');
        if (!tableElement) {
            console.warn('Summary table element not found');
            return;
        }

        if ($.fn.DataTable.isDataTable('#summary-table')) {
            $('#summary-table').DataTable().destroy();
        }

        const summaryData = App.state.data.summary_report_data || [];
        
        if (summaryData.length === 0) {
            console.warn('No summary data available for table');
            this.showEmptyTableMessage(tableElement);
            return;
        }

        try {
            $('#summary-table').DataTable({
                data: summaryData,
                columns: [
                    { 
                        data: 'Dataset Name', 
                        render: data => data ? data.replace('_exploded', '') : 'N/A'
                    },
                    { 
                        data: 'Processing Status',
                        render: cellData => Utils.createStatusPill(cellData)
                    },
                    { data: 'Total Features' },
                    { data: 'Valid Large Polygons' },
                    { data: 'Features for Review' },
                    { data: 'Small Polygons Found (<4ha)' },
                    { 
                        data: 'Attribute Status',
                        render: function(cellData) {
                            if (cellData && cellData.includes("issues")) {
                                return `<span class="is-warning">${cellData}</span>`;
                            }
                            return cellData || 'N/A';
                        }
                    }
                ],
                language: Utils.getDataTablesLang(),
                pageLength: 10,
                searching: false,
                lengthChange: false,
                info: false,
                order: [[0, 'asc']]
            });
        } catch (error) {
            console.error('Failed to initialize summary table:', error);
            this.showEmptyTableMessage(tableElement);
        }
    },

    initStatusChart: function() {
        const ctx = document.getElementById('status-chart');
        if (!ctx) {
            console.warn('Status chart canvas not found');
            return;
        }

        const existingChart = Chart.getChart(ctx);
        if (existingChart) {
            existingChart.destroy();
        }

        const counts = App.state.featureCounts;
        
        if (counts.total === 0) {
            console.warn('No data available for chart');
            this.showEmptyChartMessage(ctx);
            return;
        }

        try {
            const chartData = {
                labels: ['Valid', 'Manual Review', 'Candidate for Conversion'],
                datasets: [{
                    label: 'Entities',
                    data: [counts.valid, counts.review, counts.candidate],
                    backgroundColor: ['#28a745', '#dc3545', '#ffc107'],
                    borderColor: '#ffffff',
                    borderWidth: 2
                }]
            };

            App.state.chart = new Chart(ctx, {
                type: 'doughnut',
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: {
                                usePointStyle: true,
                                boxWidth: 8,
                                padding: 15
                            }
                        },
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
                                    return `${label}: ${value} (${percentage}%)`;
                                }
                            }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Failed to initialize status chart:', error);
            this.showEmptyChartMessage(ctx);
        }
    },

    showNoDataState: function() {
        const container = document.getElementById('summary-cards');
        if (container) {
            container.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: #6c757d;">
                    <p>No data available to display dashboard.</p>
                </div>
            `;
        }
    },

    showErrorState: function(message) {
        const container = document.getElementById('summary-cards');
        if (container) {
            container.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: #dc3545;">
                    <p>Error loading dashboard: ${message}</p>
                </div>
            `;
        }
    },

    showEmptyTableMessage: function(tableElement) {
        const wrapper = tableElement.closest('.data-table-wrapper');
        if (wrapper) {
            const message = document.createElement('div');
            message.style.cssText = 'text-align: center; padding: 2rem; color: #6c757d;';
            message.innerHTML = '<p>No summary data available.</p>';
            wrapper.appendChild(message);
        }
    },

    showEmptyChartMessage: function(chartElement) {
        const container = chartElement.parentNode;
        if (container) {
            container.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; height: 300px; color: #6c757d;">
                    <p>No data available for chart visualization.</p>
                </div>
            `;
        }
    }
};