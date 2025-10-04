export const Utils = {
    createPopupContent: function(properties) {
        let content = '<div class="map-popup"><h4>Audit Details</h4><table>';
        const mapping = {
            'qa_assistant_id': 'Assistant ID',
            'qa_issue': 'Diagnosis'
        };
        
        for (const [key, label] of Object.entries(mapping)) {
            if (properties[key]) {
                content += `<tr><th>${label}</th><td>${properties[key]}</td></tr>`;
            }
        }
        
        if (properties.attribute_status) {
            content += `<tr><th>Attributes</th><td>${this.createAttributePills(properties.attribute_status)}</td></tr>`;
        }
        
        content += '</table></div>';
        return content;
    },

    createStatusPill: function(statusText) {
        const statusClasses = {
            'PROCESSED_CLEAN': 'status-clean',
            'PROCESSED_WITH_ISSUES': 'status-issues',
            'SKIPPED': 'status-skipped'
        };
        const cssClass = statusClasses[statusText] || '';
        return `<span class="status-pill ${cssClass}">${statusText}</span>`;
    },

    createAttributePills: function(statusString) {
        if (!statusString) return '';
        
        const statuses = statusString.split('; ');
        const labels = ['N', 'C', 'A'];
        
        return statuses.map((status, i) => {
            let cssClass, tooltipText;
            if (status.toLowerCase().includes('ok')) {
                cssClass = 'ok';
                tooltipText = 'OK';
            } else if (status.toLowerCase().includes('invalid')) {
                cssClass = 'invalid';
                tooltipText = status;
            } else {
                cssClass = 'missing';
                tooltipText = 'Not Included';
            }
            
            return `<span class="attr-pill ${cssClass}">${labels[i]}<span class="tooltip-text">${tooltipText}</span></span>`;
        }).join('');
    },

    getDataTablesLang: function() {
        return {
            "search": "Search:",
            "lengthMenu": "Show _MENU_ entries",
            "info": "Showing _START_ to _END_ of _TOTAL_ entries",
            "infoEmpty": "Showing 0 to 0 of 0 entries",
            "infoFiltered": "(filtered from _MAX_ total entries)",
            "paginate": {
                "first": "First",
                "last": "Last",
                "next": "Next",
                "previous": "Previous"
            },
            "emptyTable": "No candidates for conversion in this batch."
        };
    }
};
