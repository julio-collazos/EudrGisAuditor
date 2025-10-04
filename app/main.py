import os
import uuid
import logging
import shutil
import json
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from threading import Thread
from werkzeug.utils import secure_filename

from .gis_processing.core import EudrGisQaAssistant
from .services import data_service

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.getenv('UPLOAD_FOLDER', './uploads')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

tasks = {}

def validate_path(base_dir: Path, path_segment: str) -> Path:
    """Safely validates and resolves a path within a base directory."""
    base_dir = Path(base_dir).resolve()
    path = (base_dir / path_segment).resolve()
    if not path.is_relative_to(base_dir):
        raise ValueError("Invalid path segment")
    return path

def create_empty_data_response():
    """Returns standardized empty data structure."""
    return {
        "summary_report_data": [],
        "detailed_report_data": [],
        "map_layers": [],
        "clean_file_count": 0
    }

@app.route('/')
def index():
    """Renders the file upload page."""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200

@app.route('/process', methods=['POST'])
def process_files():
    """Handles file upload and initiates the GIS processing task."""
    try:
        if 'files' not in request.files:
            return jsonify({"error": "No files uploaded"}), 400
            
        files = request.files.getlist('files')
        if not files or all(file.filename == '' for file in files):
            return jsonify({"error": "No valid files selected"}), 400

        session_id = str(uuid.uuid4())
        session_input_dir = Path(app.config['UPLOAD_FOLDER']) / session_id / 'input'
        session_output_dir = Path(app.config['UPLOAD_FOLDER']) / session_id / 'output'
        
        session_input_dir.mkdir(parents=True, exist_ok=True)

        for file in files:
            if file.filename:
                filename = secure_filename(Path(file.filename).name)
                if filename:
                    file_path = session_input_dir / filename
                    file.save(file_path)

        tasks[session_id] = {
            'progress': 0, 
            'message': 'Initializing...', 
            'step': 'Preparing...',
            'finished': False,
            'error': False
        }

        thread = Thread(target=run_gis_task, args=(
            session_id, str(session_input_dir), str(session_output_dir),
            request.form.get('simplify') == 'true',
            request.form.get('autofix') == 'true',
            request.form.get('identify_candidates') == 'true'
        ))
        thread.daemon = True
        thread.start()
        
        return jsonify({"session_id": session_id})
        
    except Exception as e:
        logging.error(f"Error in process_files: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/status/<session_id>')
def task_status(session_id: str):
    """Provides the current status of a processing task."""
    try:
        validate_path(Path(app.config['UPLOAD_FOLDER']), session_id)
        
        status = tasks.get(session_id)
        if not status:
            status = data_service.load_task_status(session_id, app.config['UPLOAD_FOLDER'])
            if status:
                tasks[session_id] = status
            else:
                return jsonify({"error": "Session not found"}), 404
                
        return jsonify(status)
    except Exception as e:
        logging.error(f"Error getting status: {e}", exc_info=True)
        return jsonify({"error": "Error retrieving status"}), 500

@app.route('/api/data/<session_id>')
def get_session_data(session_id: str):
    """API endpoint to get consolidated session data for the dashboard."""
    try:
        validate_path(Path(app.config['UPLOAD_FOLDER']), session_id)
        
        task = tasks.get(session_id) or data_service.load_task_status(session_id, app.config['UPLOAD_FOLDER'])
        if not task:
            return jsonify({
                "error": "Session not found"
            }), 404
            
        if not task.get('finished') or task.get('error'):
            return jsonify({
                "error": "Session not complete or failed"
            }), 400

        data = data_service.get_report_data(session_id, app.config['UPLOAD_FOLDER'])
        if not data:
            return jsonify({
                "error": "No data available"
            }), 404
                
        return jsonify(data)
            
    except FileNotFoundError:
        return jsonify({"error": "Data files not found"}), 404
    except Exception as e:
        logging.error(f"Error reading session data: {e}", exc_info=True)
        return jsonify({"error": f"Error reading session data: {str(e)}"}), 500
        
@app.route('/results/<session_id>')
def show_results(session_id: str):
    """Renders the results dashboard page."""
    try:
        validate_path(Path(app.config['UPLOAD_FOLDER']), session_id)
        return render_template('results.html', session_id=session_id)
    except Exception as e:
        logging.error(f"Error showing results page for session {session_id}: {e}", exc_info=True)
        return "Session not found", 404

@app.route('/download/<session_id>')
def download_results(session_id: str):
    """Downloads the complete results as a ZIP file."""
    try:
        zip_path = data_service.get_zip_file_path(session_id, app.config['UPLOAD_FOLDER'])
        return send_from_directory(
            directory=str(zip_path.parent),
            path=zip_path.name,
            as_attachment=True,
            download_name=zip_path.name
        )
    except FileNotFoundError:
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        logging.error(f"Error downloading results for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Download error"}), 500

@app.route('/api/geojson/<session_id>/<layer_type>/<filename>')
def get_geojson_layer(session_id: str, layer_type: str, filename: str):
    """API endpoint to get a specific GeoJSON layer file."""
    try:
        file_path = data_service.get_geojson_layer(session_id, layer_type, filename, app.config['UPLOAD_FOLDER'])
        return send_from_directory(directory=str(file_path.parent), path=file_path.name)
    except FileNotFoundError:
        return jsonify({"error": "Layer not found"}), 404
    except Exception as e:
        logging.error(f"Error getting geojson layer for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Error retrieving layer"}), 500

@app.route('/api/all_valid_points/<session_id>')
def get_all_valid_points(session_id: str):
    """API endpoint to get all valid points for map visualization."""
    try:
        geojson_data = data_service.get_all_valid_points(session_id, app.config['UPLOAD_FOLDER'])
        if not geojson_data or not geojson_data.get('features'):
            return jsonify({"type": "FeatureCollection", "features": []})
        return jsonify(geojson_data)
    except FileNotFoundError:
        return jsonify({"type": "FeatureCollection", "features": []})
    except Exception as e:
        logging.error(f"Error getting all valid points for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Error retrieving data"}), 500

@app.route('/api/convert/<session_id>/<qa_id>', methods=['POST'])
def convert_to_point(session_id: str, qa_id: str):
    """API endpoint to convert a single feature to a point."""
    try:
        success = data_service.convert_to_point(session_id, qa_id, app.config['UPLOAD_FOLDER'])
        return jsonify({"success": success})
    except Exception as e:
        logging.error(f"Error converting to point for session {session_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/convert_all/<session_id>', methods=['POST'])
def convert_all_to_point(session_id: str):
    """API endpoint to convert all candidate features to points."""
    try:
        data = request.get_json()
        qa_ids = data.get('qa_ids', [])
        if not qa_ids:
            return jsonify({"success": False, "error": "No QA IDs provided"}), 400
            
        result = data_service.batch_convert_all(session_id, qa_ids, app.config['UPLOAD_FOLDER'])
        return jsonify({"success": True, **result})
    except Exception as e:
        logging.error(f"Error converting all to points for session {session_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/consolidate/<session_id>')
def consolidate_features(session_id: str):
    """API endpoint to download a consolidated GeoJSON file."""
    try:
        consolidated_path = data_service.consolidate_features(session_id, app.config['UPLOAD_FOLDER'])
        if not consolidated_path:
            return jsonify({"error": "No valid features found"}), 404
        
        return send_file(
            consolidated_path,
            as_attachment=True,
            download_name='consolidated_valid_features.geojson'
        )
    except Exception as e:
        logging.error(f"Error consolidating features for session {session_id}: {e}", exc_info=True)
        return jsonify({"error": "Consolidation error"}), 500

@app.route('/cleanup/<session_id>', methods=['POST'])
def cleanup_session_data(session_id: str):
    """Removes a session's data from the server."""
    try:
        session_dir = validate_path(Path(app.config['UPLOAD_FOLDER']), session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)
        
        if session_id in tasks:
            del tasks[session_id]
        
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Error cleaning up session {session_id}: {e}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

def run_gis_task(session_id, input_dir, output_dir, simplify, autofix, identify_candidates):
    """Runs the GIS processing task in a separate thread."""
    def update_progress(status):
        tasks[session_id].update(status)
        data_service.save_task_status(session_id, tasks[session_id], Path(app.config['UPLOAD_FOLDER']))

    try:
        from datetime import datetime
        dated_name = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        dated_output_dir = Path(output_dir) / dated_name
        dated_output_dir.mkdir(parents=True, exist_ok=True)

        assistant = EudrGisQaAssistant(input_dir, str(dated_output_dir), simplify, autofix, identify_candidates)
        assistant.run(update_progress=update_progress)
        
        update_progress({
            'progress': 95, 
            'message': 'Creating archive...', 
            'step': 'Step 5/5: Finalizing'
        })

        data_service.consolidate_features(session_id, app.config['UPLOAD_FOLDER'])
        data_service.create_zip_archive(session_id, app.config['UPLOAD_FOLDER'])

        tasks[session_id].update({
            'finished': True,
            'progress': 100,
            'message': 'Complete!',
            'step': 'Completed',
            'error': False
        })
        data_service.save_task_status(session_id, tasks[session_id], Path(app.config['UPLOAD_FOLDER']))
        
    except Exception as e:
        tasks[session_id].update({
            'progress': 100, 
            'message': f'Error: {str(e)}', 
            'error': True, 
            'finished': True,
            'step': 'Error'
        })
        data_service.save_task_status(session_id, tasks[session_id], Path(app.config['UPLOAD_FOLDER']))

        try:
            shutil.rmtree(input_dir, ignore_errors=True)
            output_dir_path = Path(output_dir)
            if output_dir_path.exists() and len(list(output_dir_path.iterdir())) > 0:
                shutil.rmtree(output_dir_path, ignore_errors=True)
        except Exception:
            pass