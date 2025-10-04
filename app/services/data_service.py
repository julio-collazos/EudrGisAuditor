import json
import logging
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
import csv
from osgeo import ogr, osr

from ..gis_processing import transformations, validation

def _find_dated_output_dir(session_output_dir: Path) -> Path:
    """Helper function to find the dated output directory for the session."""
    try:
        dirs = [d for d in session_output_dir.iterdir() if d.is_dir()]
        if not dirs:
            raise FileNotFoundError("No dated directory found")
        return dirs[0]
    except StopIteration:
        raise FileNotFoundError("Results directory not found for this session.")

def _get_session_output_dir(session_id: str, upload_folder: str) -> Path:
    """Helper function to get the session output directory safely."""
    base_dir = Path(upload_folder).resolve()
    session_dir = (base_dir / session_id).resolve()
    if not session_dir.is_relative_to(base_dir) or not session_dir.is_dir():
        raise FileNotFoundError("Invalid or non-existent session directory.")
    output_dir = session_dir / 'output'
    if not output_dir.is_dir():
        raise FileNotFoundError("Output directory not found for this session.")
    return output_dir

def save_task_status(session_id: str, status: Dict[str, Any], upload_folder: str):
    """Saves the current task status to a JSON file."""
    try:
        session_dir = Path(upload_folder) / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        status_file = session_dir / 'task_status.json'
        with open(status_file, 'w') as f:
            json.dump(status, f)
    except Exception as e:
        logging.error(f"Failed to save task status for session {session_id}: {e}")

def load_task_status(session_id: str, upload_folder: str) -> Optional[Dict[str, Any]]:
    """Loads a task's status from a JSON file."""
    try:
        status_file = Path(upload_folder) / session_id / 'task_status.json'
        if status_file.exists():
            with open(status_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load task status for session {session_id}: {e}")
    return None

def get_report_data(session_id: str, upload_folder: str) -> Dict:
    """Retrieves and consolidates all report data for a session."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        summary_report_path = dated_output_dir / f"summary_report_{dated_output_dir.name}.csv"
        detailed_report_path = dated_output_dir / f"detailed_report_{dated_output_dir.name}.csv"
        
        summary_data, detailed_data = [], []
        if summary_report_path.exists():
            with open(summary_report_path, encoding='utf-8') as f:
                summary_data = list(csv.DictReader(f))
        if detailed_report_path.exists():
            with open(detailed_report_path, encoding='utf-8') as f:
                detailed_data = list(csv.DictReader(f))

        layers = []
        review_dir = dated_output_dir / "05_processed_review_features"
        for file_path in review_dir.glob("*.geojson"):
            try:
                ds = ogr.Open(str(file_path), 0)
                if ds and ds.GetLayer().GetFeatureCount() > 0:
                    original_stem = file_path.stem.replace('_review', '')
                    layers.append({"name": file_path.name, "label": f"{original_stem}.geojson", "type": "review"})
            except Exception as e:
                logging.warning(f"Could not read feature count from {file_path.name}: {e}")
        
        all_original_files = {p.stem.replace('_exploded', '') for p in list((dated_output_dir / "00a_exploded_features").glob("*.geojson"))}
        files_with_review_layers = {layer['label'].replace('.geojson', '') for layer in layers}
        clean_file_count = len(all_original_files - files_with_review_layers)
        
        return {
            'summary_report_data': summary_data,
            'detailed_report_data': detailed_data,
            'map_layers': layers,
            'clean_file_count': clean_file_count
        }
    except Exception as e:
        logging.error(f"Error getting report data for session {session_id}: {e}")
        raise FileNotFoundError(f"Report data not found for session {session_id}")

def get_geojson_layer(session_id: str, layer_type: str, filename: str, upload_folder: str) -> Path:
    """Returns the file path for a specific GeoJSON layer."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        
        layer_dirs = {
            'review': "05_processed_review_features",
            'candidates': "06_candidates_for_conversion",
            'valid': "04_processed_valid"
        }
        
        if layer_type not in layer_dirs:
            raise ValueError("Invalid layer type")
        
        base_path = dated_output_dir / layer_dirs[layer_type]
        file_path = base_path / filename
        
        if not file_path.is_file():
            raise FileNotFoundError("File not found")
        
        return file_path
    except Exception as e:
        logging.error(f"Error getting geojson layer for session {session_id}: {e}")
        raise FileNotFoundError(f"Layer file not found for session {session_id}")

def get_all_valid_points(session_id: str, upload_folder: str) -> Dict:
    """Consolidates all valid point features into a single GeoJSON FeatureCollection."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        valid_dir = dated_output_dir / "04_processed_valid"
        point_features = []
        for file_path in valid_dir.glob("*_valid.geojson"):
            in_ds = None
            try:
                in_ds = ogr.Open(str(file_path), 0)
                in_layer = in_ds.GetLayer()
                for feature in in_layer:
                    geom = feature.GetGeometryRef()
                    if geom and (geom.GetGeometryType() & 0x000000ff) == ogr.wkbPoint:
                        point_features.append(json.loads(feature.ExportToJson()))
            except Exception as e:
                logging.error(f"Failed to read valid points from {file_path}: {e}")
            finally:
                if in_ds: del in_ds
        return {"type": "FeatureCollection", "features": point_features}
    except Exception as e:
        logging.error(f"Error getting all valid points for session {session_id}: {e}")
        raise FileNotFoundError(f"Valid points data not found for session {session_id}")

def convert_to_point(session_id: str, qa_id: str, upload_folder: str) -> bool:
    """Converts a single candidate polygon to a point feature."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        converted_count, failed_ids = transformations.batch_convert_candidates_to_points(
            session_output_dir, [qa_id]
        )
        return converted_count > 0 and qa_id not in failed_ids
    except Exception as e:
        logging.error(f"Error converting to point for session {session_id}: {e}")
        raise e

def batch_convert_all(session_id: str, qa_ids: list, upload_folder: str) -> Dict[str, Any]:
    """Converts a list of candidate polygons to points in a single operation."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        converted_count, failed_ids = transformations.batch_convert_candidates_to_points(
            session_output_dir, qa_ids
        )
        return {"converted_count": converted_count, "failed_ids": failed_ids}
    except Exception as e:
        logging.error(f"Error batch converting all for session {session_id}: {e}")
        raise e

def consolidate_features(session_id: str, upload_folder: str) -> Optional[Path]:
    """Consolidates all valid features into a single GeoJSON file."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        return transformations.consolidate_valid_features(session_output_dir)
    except Exception as e:
        logging.error(f"Error consolidating features for session {session_id}: {e}")
        raise e

def create_zip_archive(session_id: str, upload_folder: str):
    """Creates a zip archive of the session's output directory."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        zip_base_name = f"eudr_results_{dated_output_dir.name}"
        zip_path = shutil.make_archive(str(session_output_dir / zip_base_name), 'zip', str(dated_output_dir))
        return Path(zip_path)
    except Exception as e:
        logging.error(f"Error creating zip archive for session {session_id}: {e}")
        raise e

def get_zip_file_path(session_id: str, upload_folder: str) -> Path:
    """Gets the path to the zipped results file."""
    try:
        session_output_dir = _get_session_output_dir(session_id, upload_folder)
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        zip_base_name = f"eudr_results_{dated_output_dir.name}"
        zip_path = session_output_dir / (zip_base_name + '.zip')
        if not zip_path.is_file():
            raise FileNotFoundError("Zip file not found.")
        return zip_path
    except Exception as e:
        logging.error(f"Error getting zip file path for session {session_id}: {e}")
        raise e
