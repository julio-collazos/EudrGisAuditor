import json
import logging
import shutil
import time
import csv
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from osgeo import ogr, osr

from . import validation, reports, io

def get_area_in_hectares(geom: ogr.Geometry) -> Optional[float]:
    """Calculates geometry area in hectares using appropriate projection."""
    if not geom or geom.IsEmpty():
        return 0.0
    
    centroid = geom.Centroid()
    if not centroid:
        return None
        
    lon, lat = centroid.GetX(), centroid.GetY()
    if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
        return None
    
    utm_zone = int((lon + 180) / 6) + 1
    
    source_srs = osr.SpatialReference()
    source_srs.ImportFromEPSG(4326)
    source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    
    target_srs = osr.SpatialReference()
    target_srs.SetWellKnownGeogCS("WGS84")
    target_srs.SetUTM(utm_zone, lat >= 0)
    
    try:
        transform = osr.CoordinateTransformation(source_srs, target_srs)
        geom_clone = geom.Clone()
        geom_clone.Transform(transform)
        return geom_clone.GetArea() / validation.METERS_SQ_PER_HECTARE
    except RuntimeError:
        return None

def partition_and_process_dataset(ds: ogr.DataSource, dataset_stem: str, valid_dir: Path,
                                review_dir: Path, candidates_dir: Path, simplify: bool,
                                autofix: bool, identify_candidates: bool) -> Tuple[Dict, List[Dict]]:
    """Partitions dataset features into valid, review, and candidate categories."""
    stats = {'total': 0, 'valid_large': 0, 'review': 0, 'autofixed': 0, 'candidates': 0}
    detailed_rows = []
    
    in_layer = ds.GetLayer()
    in_srs = in_layer.GetSpatialRef()
    in_layer_defn = in_layer.GetLayerDefn()
    driver = ogr.GetDriverByName("GeoJSON")

    review_ds = driver.CreateDataSource(str(review_dir / f"{dataset_stem}_review.geojson"))
    review_layer = review_ds.CreateLayer('review', in_srs, ogr.wkbPolygon)
    for i in range(in_layer_defn.GetFieldCount()):
        review_layer.CreateField(in_layer_defn.GetFieldDefn(i))
    review_layer.CreateField(ogr.FieldDefn("qa_issue", ogr.OFTString))

    candidates_ds = driver.CreateDataSource(str(candidates_dir / f"{dataset_stem}_candidates.geojson"))
    candidates_layer = candidates_ds.CreateLayer('candidates', in_srs, ogr.wkbPolygon)
    for i in range(in_layer_defn.GetFieldCount()):
        candidates_layer.CreateField(in_layer_defn.GetFieldDefn(i))

    valid_ds = driver.CreateDataSource(str(valid_dir / f"{dataset_stem}_valid.geojson"))
    valid_layer = valid_ds.CreateLayer('valid', in_srs, ogr.wkbUnknown)
    for i in range(in_layer_defn.GetFieldCount()):
        valid_layer.CreateField(in_layer_defn.GetFieldDefn(i))
    if 'Area' not in [in_layer_defn.GetFieldDefn(i).GetName() for i in range(in_layer_defn.GetFieldCount())]:
        valid_layer.CreateField(ogr.FieldDefn('Area', ogr.OFTReal))

    for in_feature in in_layer:
        stats['total'] += 1
        geom = in_feature.GetGeometryRef()
        qa_id = in_feature.GetField(validation.ID_FIELD_NAME)
        attribute_status = validation.check_optional_properties(in_feature)
        
        is_valid, reason, action_taken = validate_and_fix_geometry(geom, autofix, simplify)
        if action_taken == "Auto-fixed":
            stats['autofixed'] += 1

        if not is_valid:
            stats['review'] += 1
            review_feature = ogr.Feature(review_layer.GetLayerDefn())
            review_feature.SetFrom(in_feature)
            review_feature.SetGeometry(geom)
            review_feature.SetField("qa_issue", reason)
            review_layer.CreateFeature(review_feature)
            
            detailed_rows.append({
                'original_filename': dataset_stem + ".geojson",
                'qa_assistant_id': qa_id,
                'final_status': 'Requires Review',
                'action_taken': action_taken or "Segregated",
                'reason_notes': reason,
                'attribute_status': attribute_status
            })
            continue

        area_ha = get_area_in_hectares(geom)
        if area_ha is None:
            stats['review'] += 1
            reason = "Could not calculate area"
            review_feature = ogr.Feature(review_layer.GetLayerDefn())
            review_feature.SetFrom(in_feature)
            review_feature.SetField("qa_issue", reason)
            review_layer.CreateFeature(review_feature)
            
            detailed_rows.append({
                'original_filename': dataset_stem + ".geojson",
                'qa_assistant_id': qa_id,
                'final_status': 'Requires Review',
                'action_taken': action_taken or "Segregated",
                'reason_notes': reason,
                'attribute_status': attribute_status
            })
            continue

        valid_feature = ogr.Feature(valid_layer.GetLayerDefn())
        valid_feature.SetFrom(in_feature)
        valid_feature.SetGeometry(geom)

        geom_type = geom.GetGeometryType() & 0x000000ff
        if (identify_candidates and geom_type == ogr.wkbPolygon and 
            area_ha < validation.MIN_AREA_HA_FOR_POLYGON):
            stats['candidates'] += 1
            candidates_layer.CreateFeature(valid_feature)
            
            detailed_rows.append({
                'original_filename': dataset_stem + ".geojson",
                'qa_assistant_id': qa_id,
                'final_status': 'Candidate for Conversion',
                'action_taken': action_taken or "Identified",
                'reason_notes': f"Area is {area_ha:.2f} ha (< 4ha)",
                'attribute_status': attribute_status
            })
        else:
            stats['valid_large'] += 1
            valid_layer.CreateFeature(valid_feature)
            
            detailed_rows.append({
                'original_filename': dataset_stem + ".geojson",
                'qa_assistant_id': qa_id,
                'final_status': 'Valid',
                'action_taken': action_taken or "N/A",
                'reason_notes': "Valid",
                'attribute_status': attribute_status
            })
    
    del review_ds, candidates_ds, valid_ds
    return stats, detailed_rows

def validate_and_fix_geometry(geom, autofix: bool, simplify: bool) -> Tuple[bool, str, Optional[str]]:
    """Validates and optionally fixes geometry issues."""
    if not geom or geom.IsEmpty():
        return False, "Missing or empty geometry", None
    
    geom_type = geom.GetGeometryType() & 0x000000ff
    if geom_type in [ogr.wkbLineString, ogr.wkbMultiLineString]:
        return False, "Invalid geometry type (LineString)", None
    
    if not geom.IsValid():
        if autofix:
            fixed_geom = geom.Buffer(0)
            if fixed_geom and not fixed_geom.IsEmpty() and fixed_geom.IsValid():
                geom = fixed_geom
                return True, "Valid", "Auto-fixed"
            else:
                return False, "Invalid geometry (unfixable)", None
        else:
            return False, "Invalid geometry", None
    
    if geom_type == ogr.wkbPolygon and geom.GetGeometryCount() > 1:
        return False, "Polygon with holes not supported", None
    
    valid_verts, reason = validation.validate_geometry_vertices(geom)
    if not valid_verts:
        return False, reason, None
    
    if simplify and geom_type == ogr.wkbPolygon:
        geom = geom.SimplifyPreserveTopology(validation.SIMPLIFY_TOLERANCE)
        return True, "Valid", "Simplified"
    
    return True, "Valid", None

def batch_convert_candidates_to_points(session_output_dir: Path, qa_ids_to_convert: List[str]) -> Tuple[int, List[str]]:
    """Converts candidate polygons to points in a batch operation."""
    dated_output_dir = _find_dated_output_dir(session_output_dir)
    candidates_dir = dated_output_dir / "06_candidates_for_conversion"
    valid_dir = dated_output_dir / "04_processed_valid"
    detailed_report_path = dated_output_dir / f"detailed_report_{dated_output_dir.name}.csv"
    
    converted_count = 0
    failed_ids = []
    
    candidates_by_file = {}
    for qa_id in qa_ids_to_convert:
        original_stem = "_".join(qa_id.split('_')[:-1]).split('-p')[0]
        if original_stem not in candidates_by_file:
            candidates_by_file[original_stem] = []
        candidates_by_file[original_stem].append(qa_id)
        
    converted_features = {}
    for original_stem, ids in candidates_by_file.items():
        candidate_filepath = candidates_dir / f"{original_stem}_candidates.geojson"
        valid_filepath = valid_dir / f"{original_stem}_valid.geojson"
        
        if not candidate_filepath.exists():
            logging.error(f"Candidate file not found: {candidate_filepath}")
            failed_ids.extend(ids)
            continue
            
        existing_valid_features = []
        if valid_filepath.exists():
            try:
                with open(valid_filepath, 'r', encoding='utf-8') as f:
                    valid_data = json.load(f)
                    existing_valid_features = valid_data.get('features', [])
            except Exception as e:
                logging.error(f"Error reading existing valid file {valid_filepath}: {e}")
                failed_ids.extend(ids)
                continue
                
        candidates_to_remove = []
        new_point_features = []
        try:
            with open(candidate_filepath, 'r', encoding='utf-8') as f:
                candidates_data = json.load(f)
            
            for feature in candidates_data.get('features', []):
                qa_id = feature['properties'].get(validation.ID_FIELD_NAME)
                if qa_id in ids:
                    try:
                        polygon_geom = json.dumps(feature['geometry'])
                        geom = ogr.CreateGeometryFromJson(polygon_geom)
                        if not geom or geom.IsEmpty():
                            failed_ids.append(qa_id)
                            continue
                            
                        centroid = geom.Centroid()
                        if not centroid:
                            failed_ids.append(qa_id)
                            continue
                            
                        feature['geometry'] = json.loads(centroid.ExportToJson())
                        if 'Area' in feature['properties']:
                            feature['properties']['Area'] = validation.MIN_AREA_HA_FOR_POLYGON
                        
                        new_point_features.append(feature)
                        candidates_to_remove.append(qa_id)
                        converted_count += 1
                    except Exception as e:
                        logging.error(f"Failed to convert {qa_id}: {e}")
                        failed_ids.append(qa_id)
        except Exception as e:
            logging.error(f"Error processing candidates file {candidate_filepath}: {e}")
            failed_ids.extend(ids)
            continue
            
        if new_point_features:
            converted_features[original_stem] = {
                'existing_features': existing_valid_features,
                'new_features': new_point_features,
                'valid_filepath': valid_filepath,
                'candidate_filepath': candidate_filepath,
                'candidates_to_remove': candidates_to_remove
            }
    
    for original_stem, data in converted_features.items():
        try:
            all_features = data['existing_features'] + data['new_features']
            output_geojson = {
                "type": "FeatureCollection",
                "name": f"{original_stem}_valid",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                "features": all_features
            }
            with open(data['valid_filepath'], 'w', encoding='utf-8') as f:
                json.dump(output_geojson, f, indent=2)
            
            time.sleep(0.5)
            
            remaining_candidates = []
            with open(data['candidate_filepath'], 'r', encoding='utf-8') as f:
                candidates_data = json.load(f)
                for feature in candidates_data.get('features', []):
                    qa_id = feature['properties'].get(validation.ID_FIELD_NAME)
                    if qa_id not in data['candidates_to_remove']:
                        remaining_candidates.append(feature)
            
            candidates_output = {
                "type": "FeatureCollection",
                "name": f"{original_stem}_candidates",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                "features": remaining_candidates
            }
            with open(data['candidate_filepath'], 'w', encoding='utf-8') as f:
                json.dump(candidates_output, f, indent=2)
                
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Error writing converted features for {original_stem}: {e}")
            for feature in data['new_features']:
                qa_id = feature['properties'].get(validation.ID_FIELD_NAME)
                if qa_id:
                    failed_ids.append(qa_id)
            converted_count -= len(data['new_features'])
            
    detailed_report_data = []
    if detailed_report_path.exists():
        try:
            with open(detailed_report_path, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                detailed_report_data = list(reader)
        except Exception as e:
            logging.error(f"Error reading detailed report: {e}")
            
    successfully_converted = [qa_id for qa_id in qa_ids_to_convert if qa_id not in failed_ids]
    for row in detailed_report_data:
        if row['qa_assistant_id'] in successfully_converted:
            row['final_status'] = 'Valid'
            row['action_taken'] = 'Converted to Point'
            
    if detailed_report_data:
        try:
            with open(detailed_report_path, mode='w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=detailed_report_data[0].keys())
                writer.writeheader()
                writer.writerows(detailed_report_data)
            time.sleep(0.5)
        except Exception as e:
            logging.error(f"Error writing detailed report: {e}")
            
    return converted_count, failed_ids

def consolidate_valid_features(session_output_dir: Path) -> Optional[Path]:
    """Consolidates all valid features into a single GeoJSON file."""
    try:
        dated_output_dir = _find_dated_output_dir(session_output_dir)
    except StopIteration:
        return None

    valid_dir = dated_output_dir / "04_processed_valid"
    consolidated_file_path = dated_output_dir / "consolidated_valid_features.geojson"
    all_features = []
    
    for file_path in valid_dir.glob("*.geojson"):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                features = data.get('features', [])
                all_features.extend(features)
        except Exception:
            continue
    
    if all_features:
        output_geojson = {
            "type": "FeatureCollection",
            "features": all_features
        }
        with open(consolidated_file_path, 'w', encoding='utf-8') as f:
            json.dump(output_geojson, f, indent=2)
        return consolidated_file_path
    
    return None

def _find_dated_output_dir(session_output_dir: Path) -> Path:
    """Finds the dated output directory for the session."""
    try:
        return next(d for d in session_output_dir.iterdir() if d.is_dir())
    except StopIteration:
        raise FileNotFoundError("Results directory not found for this session.")
