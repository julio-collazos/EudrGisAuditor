import shutil
import csv
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, Tuple, List
from osgeo import ogr, osr

from . import reports, validation

ogr.UseExceptions()

def inject_traceability_id(dataset_path: Path, output_dir: Path, id_field_name: str) -> Optional[Path]:
    """Create unique IDs for each feature in the dataset."""
    in_ds, out_ds = None, None
    try:
        in_ds = ogr.Open(str(dataset_path), 0)
        if not in_ds: return None
        in_layer = in_ds.GetLayer()
        driver = ogr.GetDriverByName("GeoJSON" if dataset_path.suffix.lower() == '.geojson' else "ESRI Shapefile")
        output_path = output_dir / dataset_path.name
        if output_path.exists():
            shutil.rmtree(output_path) if output_path.is_dir() else output_path.unlink()
        out_ds = driver.CreateDataSource(str(output_path))
        out_layer = out_ds.CreateLayer(in_layer.GetName(), in_layer.GetSpatialRef(), in_layer.GetGeomType())
        in_layer_defn = in_layer.GetLayerDefn()
        for i in range(in_layer_defn.GetFieldCount()): out_layer.CreateField(in_layer_defn.GetFieldDefn(i))
        out_layer.CreateField(ogr.FieldDefn(id_field_name, ogr.OFTString))
        for i, in_feature in enumerate(in_layer):
            out_feature = ogr.Feature(out_layer.GetLayerDefn())
            out_feature.SetFrom(in_feature)
            out_feature.SetField(id_field_name, f"{dataset_path.stem}_{i}")
            out_layer.CreateFeature(out_feature)
        return output_path
    except Exception as e:
        logging.error(f"Failed to inject ID for {dataset_path.name}: {e}", exc_info=True)
        return None
    finally:
        if in_ds: in_ds = None
        if out_ds: out_ds = None

def explode_multipart_features(dataset_path: Path, output_dir: Path, id_field_name: str) -> Optional[Path]:
    """Explode multipolygon geometries into singlepart features."""
    in_ds, out_ds = None, None
    try:
        in_ds = ogr.Open(str(dataset_path), 0)
        if not in_ds: return None
        in_layer = in_ds.GetLayer()
        in_layer_defn = in_layer.GetLayerDefn()
        driver = ogr.GetDriverByName("GeoJSON" if dataset_path.suffix.lower() == '.geojson' else "ESRI Shapefile")
        exploded_path = output_dir / dataset_path.name
        if exploded_path.exists():
            shutil.rmtree(exploded_path) if exploded_path.is_dir() else exploded_path.unlink()
        out_ds = driver.CreateDataSource(str(exploded_path))
        out_layer = out_ds.CreateLayer("exploded", in_layer.GetSpatialRef(), ogr.wkbPolygon)
        for i in range(in_layer_defn.GetFieldCount()): out_layer.CreateField(in_layer_defn.GetFieldDefn(i))
        for in_feature in in_layer:
            geom = in_feature.GetGeometryRef()
            if geom and geom.GetGeometryType() in [ogr.wkbMultiPolygon]:
                for i in range(geom.GetGeometryCount()):
                    part = geom.GetGeometryRef(i).Clone()
                    out_feature = ogr.Feature(out_layer.GetLayerDefn())
                    out_feature.SetFrom(in_feature)
                    out_feature.SetGeometry(part)
                    original_id = in_feature.GetField(id_field_name)
                    out_feature.SetField(id_field_name, f"{original_id}-p{i}")
                    out_layer.CreateFeature(out_feature)
            elif geom and geom.GetGeometryType() == ogr.wkbPolygon:
                out_layer.CreateFeature(in_feature)
        return exploded_path
    except Exception as e:
        logging.error(f"Failed to explode features for {dataset_path.name}: {e}", exc_info=True)
        return None
    finally:
        if in_ds: in_ds = None
        if out_ds: out_ds = None

def open_dataset(dataset_path: Path) -> Optional[ogr.DataSource]:
    """Opens and returns an OGR dataset."""
    try:
        return ogr.Open(str(dataset_path), 0)
    except Exception:
        return None

def move_and_log_dataset(dataset_path: Path, target_dir: Path, status: str, reason: str, original_name: str, summary_report_path: Path):
    logging.warning(f"  -> Global issue with {original_name}: {reason}. Moving.")
    for component in dataset_path.parent.glob(f'{dataset_path.stem}.*'):
        if component.exists():
            shutil.move(str(component), target_dir / component.name)
    reports.log_to_summary_report(summary_report_path, original_name, status, "SKIPPED", {}, "", reason)

def process_unsupported_files(input_dir: Path, unsupported_dir: Path, summary_report_path: Path):
    for f in input_dir.iterdir():
        if f.is_file() and f.suffix.lower() not in validation.DATASET_TRIGGERS:
            try:
                shutil.move(str(f), unsupported_dir / f.name)
                reports.log_to_summary_report(summary_report_path, f.name, "UNSUPPORTED", "SKIPPED", {}, "", "Not a trigger GIS file")
            except Exception as e:
                logging.warning(f"Could not move unsupported file {f.name}: {e}")

def delete_intermediate_components(processed_path: Path, traced_dir: Path, original_input_dir: Path):
    try:
        for component in traced_dir.glob(f'{processed_path.stem}.*'):
            if component.exists(): component.unlink()
        for component in original_input_dir.glob(f'{processed_path.stem}.*'):
            component.unlink()
    except Exception as e:
        logging.error(f"Failed to delete intermediate or original file components for {processed_path.name}: {e}")

def get_geojson_feature(session_output_dir: Path, layer_type: str, filename: str, qa_id: str) -> Optional[Dict]:
    try:
        dated_output_dir = _find_dated_output_dir(session_output_dir)
        if layer_type == 'review': base_path = dated_output_dir / "05_processed_review_features"
        elif layer_type == 'candidates': base_path = dated_output_dir / "06_candidates_for_conversion"
        elif layer_type == 'valid': base_path = dated_output_dir / "04_processed_valid"
        else: return None
        file_path = base_path / filename
        if not file_path.is_file(): return None
        driver = ogr.GetDriverByName("GeoJSON")
        ds = driver.Open(str(file_path), 0)
        layer = ds.GetLayer()
        feature_geojson = None
        for feature in layer:
            if feature.GetField("qa_assistant_id") == qa_id:
                feature_geojson = json.loads(feature.ExportToJson())
                break
        ds = None
        return feature_geojson
    except Exception as e:
        logging.error(f"Error getting GeoJSON feature: {e}", exc_info=True)
        return None

def _find_dated_output_dir(session_output_dir: Path) -> Path:
    """Helper function to find the dated output directory for the session."""
    try:
        return next(d for d in session_output_dir.iterdir() if d.is_dir())
    except StopIteration:
        raise FileNotFoundError("Results directory not found for this session.")
