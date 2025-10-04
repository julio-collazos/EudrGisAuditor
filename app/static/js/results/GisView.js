import { App } from './App.js';
import { DashboardView } from './DashboardView.js';
import { TableManager } from './TableManager.js';
import { Utils } from './Utils.js';

export const GisView = {
    init: function() {
        this.initMap();
        this.initPanels();
        this.initEventListeners();
        this.initConvertedPointsLayer();
        this.loadValidPoints();
        this.populateLayerList();
    },

    initMap: function() {
        const mapElement = document.getElementById('map');
        if (!mapElement) return;

        App.state.map = L.map('map').setView([20, 0], 2);

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(App.state.map);
    },

    initConvertedPointsLayer: function() {
        if (!App.state.convertedPointsLayer) {
            App.state.convertedPointsLayer = L.geoJSON(null, {
                pointToLayer: function(feature, latlng) {
                    return L.circleMarker(latlng, {
                        radius: 6,
                        color: '#28a745',
                        weight: 2,
                        fillColor: '#28a745',
                        fillOpacity: 0.6
                    });
                },
                onEachFeature: (feature, layer) => {
                    if (feature.properties) {
                        layer.bindPopup(Utils.createPopupContent(feature.properties));
                    }
                }
            }).addTo(App.state.map);
        }
    },

    initPanels: function() {
        const layerPanelToggle = document.getElementById('layer-panel-toggle');
        const dataDrawerToggle = document.getElementById('data-drawer-toggle');
        const layerPanel = document.getElementById('gis-layer-panel');
        const dataDrawer = document.getElementById('gis-data-drawer');

        if (layerPanelToggle) {
            layerPanelToggle.addEventListener('click', () => {
                if (layerPanel) {
                    dataDrawer?.classList.remove('open');
                    layerPanel.classList.toggle('closed');
                    dataDrawerToggle?.classList.remove('open');
                }
            });
        }

        if (dataDrawerToggle) {
            dataDrawerToggle.addEventListener('click', () => {
                if (dataDrawer) {
                    layerPanel?.classList.add('closed');
                    dataDrawer.classList.toggle('open');
                    dataDrawerToggle.classList.toggle('open');
                    
                    const buttonLabel = dataDrawerToggle.querySelector('.button-label');
                    if (buttonLabel) {
                        buttonLabel.textContent = dataDrawer.classList.contains('open') ?
                            "Close Table" : "Work Table";
                    }

                    if (App.state.map) {
                        setTimeout(() => {
                            App.state.map.invalidateSize({ pan: true });
                        }, 300);
                    }
                }
            });
        }
    },

    initEventListeners: function() {
        const layerList = document.getElementById('layer-list');
        if (layerList) {
            layerList.addEventListener('click', this.handleLayerListClick.bind(this));
        }

        const convertAllBtn = document.getElementById('convert-all-btn');
        if (convertAllBtn) {
            convertAllBtn.addEventListener('click', this.handleConvertAll.bind(this));
        }

        $(document).on('click', '#detailed-table tbody tr', this.handleRowClick.bind(this));
        $(document).on('click', '.convert-btn', this.handleConvert.bind(this));
    },

    showLoadingOverlay: function() {
        let overlay = document.getElementById('conversion-loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'conversion-loading-overlay';
            overlay.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 10000;
            `;
            overlay.innerHTML = `
                <div style="background: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <svg width="40" height="40" viewBox="0 0 50 50" style="animation: spin 1s linear infinite;">
                        <circle cx="25" cy="25" r="20" fill="none" stroke="#28a745" stroke-width="4" stroke-dasharray="90, 150" />
                    </svg>
                    <p style="margin-top: 10px; color: #333;">Converting polygons to points...</p>
                </div>
            `;
            document.body.appendChild(overlay);

            const style = document.createElement('style');
            style.textContent = `
                @keyframes spin {
                    0% { transform: rotate(0deg); }
                    100% { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
        }
        overlay.style.display = 'flex';

        document.querySelectorAll('button, input, select, #map, #layer-list, #detailed-table').forEach(el => {
            el.style.pointerEvents = 'none';
            el.style.opacity = '0.6';
        });
    },

    hideLoadingOverlay: function() {
        const overlay = document.getElementById('conversion-loading-overlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
        document.querySelectorAll('button, input, select, #map, #layer-list, #detailed-table').forEach(el => {
            el.style.pointerEvents = 'auto';
            el.style.opacity = '1';
        });
    },

    populateLayerList: function() {
        const layerList = document.getElementById('layer-list');
        const footer = document.getElementById('layer-list-footer');
        
        if (!layerList) return;

        const layers = App.state.data.map_layers || [];
        const cleanCount = App.state.data.clean_file_count || 0;

        if (layers.length > 0) {
            layerList.innerHTML = layers.map(layer =>
                `<li data-filename="${layer.name}" data-type="${layer.type}">${layer.label}</li>`
            ).join('');
        } else {
            layerList.innerHTML = '<li class="empty-list-item">No layers with errors to show.</li>';
        }

        if (footer && cleanCount > 0) {
            footer.textContent = `${cleanCount} file(s) did not contain entities for review.`;
            footer.classList.remove('hidden');
        }
    },

    handleLayerListClick: function(e) {
        const target = e.target.closest('li');
        if (!target || !target.dataset.filename || target.classList.contains('active')) {
            return;
        }

        if (App.state.currentReviewLayer && App.state.map) {
            App.state.map.removeLayer(App.state.currentReviewLayer);
            App.state.currentReviewLayer = null;
        }

        this.resetHighlight();

        document.querySelectorAll('#layer-list li').forEach(li => li.classList.remove('active'));
        target.classList.add('active');

        this.loadLayer(target.dataset.filename, 'review');
    },

    loadLayer: function(filename, layerType) {
        if (!App.state.map) return;

        const url = `/api/geojson/${SESSION_ID}/${layerType}/${filename}`;
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to load layer: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                this.createLayerFromData(data, filename, layerType);
            })
            .catch(err => {
                console.error('Error loading GeoJSON:', err);
            });
    },

    createLayerFromData: function(data, filename, layerType) {
        if (!data || !data.features || data.features.length === 0) return;

        const style = layerType === 'review' ?
            { color: '#dc3545', weight: 2, fillColor: '#dc3545', fillOpacity: 0.4 } :
            { color: '#ffc107', weight: 2, fillColor: '#ffc107', fillOpacity: 0.4 };

        const newLayer = L.geoJSON(data, {
            style: () => style,
            onEachFeature: (feature, layer) => {
                if (feature.properties && feature.properties.qa_assistant_id) {
                    layer.qa_id = feature.properties.qa_assistant_id;
                }
                if (feature.properties) {
                    layer.bindPopup(Utils.createPopupContent(feature.properties));
                }
            }
        }).addTo(App.state.map);

        newLayer.filename = filename;

        if (layerType === 'review') {
            App.state.currentReviewLayer = newLayer;
            App.state.map.fitBounds(newLayer.getBounds());
        }
    },

    loadValidPoints: function() {
        this.initConvertedPointsLayer();
        fetch(`/api/all_valid_points/${SESSION_ID}`)
            .then(response => response.json())
            .then(geojson => {
                App.state.convertedPointsLayer.clearLayers();
                if (geojson && geojson.features && geojson.features.length > 0) {
                    App.state.convertedPointsLayer.addData(geojson);
                    const bounds = App.state.convertedPointsLayer.getBounds();
                    if (bounds.isValid()) {
                        App.state.map.fitBounds(bounds, { padding: [50, 50] });
                    }
                }
            })
            .catch(error => {
                console.error("Error loading valid points:", error);
            });
    },

    handleRowClick: function(e) {
        if ($(e.target).hasClass('convert-btn')) return;
        
        const row = e.target.closest('tr');
        const qaId = row?.dataset.qaId;
        
        if (!qaId) return;

        const rowIndex = $(row).index();
        let rowData = null;
        
        if (App.state.detailedTableApi) {
            rowData = App.state.detailedTableApi.row(row).data();
        }
        
        if (!rowData || !rowData.original_filename) {
            console.warn('Could not find row data or filename');
            return;
        }
        
        const filename = rowData.original_filename;

        const drawer = document.getElementById('gis-data-drawer');
        if (drawer && !drawer.classList.contains('open')) {
            drawer.classList.add('open');
            const toggle = document.getElementById('data-drawer-toggle');
            if (toggle) {
                toggle.classList.add('open');
                const buttonLabel = toggle.querySelector('.button-label');
                if (buttonLabel) {
                    buttonLabel.textContent = "Close Table";
                }
            }
        }

        this.resetHighlight();

        if (App.state.currentReviewLayer && App.state.currentReviewLayer.filename === filename) {
            this.zoomToFeatureById(qaId);
        } else {
            this.loadLayerAndZoomToFeature(filename, qaId);
        }
    },

    zoomToFeatureById: function(qaId) {
        if (!App.state.currentReviewLayer) {
            console.warn('No review layer available');
            return;
        }
        
        let targetFeature = null;
        
        App.state.currentReviewLayer.eachLayer(layer => {
            if (layer.qa_id === qaId) {
                targetFeature = layer;
            }
        });
        
        if (targetFeature) {
            if (targetFeature.getBounds) {
                App.state.map.fitBounds(targetFeature.getBounds(), { 
                    padding: [50, 50],
                    maxZoom: 16 
                });
            } else if (targetFeature.getLatLng) {
                App.state.map.setView(targetFeature.getLatLng(), 16);
            }

            const highlightStyle = {
                color: '#00ff00',
                weight: 4,
                fillColor: '#00ff00',
                fillOpacity: 0.6
            };
            
            if (targetFeature.setStyle) {
                targetFeature.setStyle(highlightStyle);
            }

            App.state.highlightedFeatureLayer = targetFeature;
            App.state.highlightedFeatureLayer.targetLayer = App.state.currentReviewLayer;
            
            if (targetFeature.getPopup()) {
                targetFeature.openPopup();
            }
        } else {
            console.warn(`Feature with qa_id ${qaId} not found in current layer`);
        }
    },
    
    loadLayerAndZoomToFeature: function(filename, qaId) {
        if (!App.state.map) return;

        if (App.state.currentReviewLayer && App.state.map) {
            App.state.map.removeLayer(App.state.currentReviewLayer);
            App.state.currentReviewLayer = null;
        }

        let layerType = 'review';
        let layerFilename = '';
        
        if (App.state.detailedTableApi) {
            const allData = App.state.detailedTableApi.rows().data().toArray();
            const rowData = allData.find(row => row.qa_assistant_id === qaId);
            
            if (rowData) {
                if (rowData.final_status === 'Candidate for Conversion') {
                    layerType = 'candidates';
                    const baseFilename = filename.replace(/\.geojson$/i, '');
                    layerFilename = `${baseFilename}_candidates.geojson`;
                } else {
                    layerType = 'review';
                    const baseFilename = filename.replace(/\.geojson$/i, '');
                    layerFilename = `${baseFilename}_review.geojson`;
                }
            }
        }
        
        if (!layerFilename) {
            const baseFilename = filename.replace(/\.geojson$/i, '');
            layerFilename = `${baseFilename}_review.geojson`;
        }

        const url = `/api/geojson/${SESSION_ID}/${layerType}/${layerFilename}`;
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Failed to load layer: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                if (!data || !data.features || data.features.length === 0) {
                    console.warn('No features in loaded layer');
                    return;
                }
                
                const style = layerType === 'candidates' ? 
                    { color: '#ffc107', weight: 2, fillColor: '#ffc107', fillOpacity: 0.4 } :
                    { color: '#dc3545', weight: 2, fillColor: '#dc3545', fillOpacity: 0.4 };
                
                const newLayer = L.geoJSON(data, {
                    style: () => style,
                    onEachFeature: (feature, layer) => {
                        if (feature.properties && feature.properties.qa_assistant_id) {
                            layer.qa_id = feature.properties.qa_assistant_id;
                        }
                        if (feature.properties) {
                            layer.bindPopup(Utils.createPopupContent(feature.properties));
                        }
                    }
                }).addTo(App.state.map);
                
                newLayer.filename = layerFilename;
                App.state.currentReviewLayer = newLayer;
                
                setTimeout(() => {
                    this.zoomToFeatureById(qaId);
                }, 100);
            })
            .catch(err => {
                console.error('Error loading GeoJSON:', err);
                alert(`Could not load layer for ${filename}. The feature may have been converted already.`);
            });
    },

    handleConvert: async function(e) {
        const button = e.target;
        const row = button.closest('tr');
        const qaId = row?.dataset.qaId;
        
        if (!qaId || button.disabled) return;

        button.disabled = true;
        button.textContent = 'Converting...';

        try {
            const response = await fetch(`/api/convert/${SESSION_ID}/${qaId}`, {
                method: 'POST'
            });

            const result = await response.json();
            
            if (result.success) {
                window.location.reload();
            } else {
                throw new Error(result.error || 'Conversion failed');
            }
        } catch (error) {
            alert(`Error converting entity: ${error.message}`);
            button.disabled = false;
            button.textContent = 'Convert';
        }
    },

    handleConvertAll: async function() {
        if (!confirm("Convert all candidate entities to points?")) return;

        const convertAllBtn = document.getElementById('convert-all-btn');
        if (!App.state.detailedTableApi || !convertAllBtn) return;

        const allData = App.state.detailedTableApi.rows().data().toArray();
        const qaIds = allData.map(data => data.qa_assistant_id).filter(id => id);

        if (qaIds.length === 0) {
            alert("No candidates available for conversion.");
            return;
        }

        convertAllBtn.disabled = true;
        convertAllBtn.textContent = 'Processing...';
        this.showLoadingOverlay();

        try {
            const response = await fetch(`/api/convert_all/${SESSION_ID}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ qa_ids: qaIds })
            });

            const result = await response.json();
            
            if (result.success) {
                this.hideLoadingOverlay();
                alert(`${result.converted_count} entities converted successfully!`);
                window.location.reload();
            } else {
                throw new Error(result.error || 'Batch conversion failed');
            }
        } catch (error) {
            this.hideLoadingOverlay();
            alert(`Error converting entities: ${error.message}`);
            convertAllBtn.disabled = false;
            convertAllBtn.textContent = `Convert All ${qaIds.length} to Points`;
        }
    },

    resetHighlight: function() {
        if (App.state.highlightedFeatureLayer) {
            const originalLayer = App.state.highlightedFeatureLayer.targetLayer;
            if (originalLayer) {
                originalLayer.resetStyle(App.state.highlightedFeatureLayer);
            }
            App.state.highlightedFeatureLayer = null;
        }
    }
};