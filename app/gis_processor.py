import shutil
import csv
import logging
import math
from datetime import date
from pathlib import Path
from typing import Set, Tuple, Optional, Dict
from osgeo import ogr, osr

ogr.UseExceptions()


class EudrGisQaAssistant:
    """
    Acts as a GIS Quality Assurance assistant. It processes geospatial files by
    validating, auto-fixing, simplifying, and isolating features that are candidates
    for optimization, based on EUDR technical requirements.
    """
    DATASET_TRIGGERS: Set[str] = {".shp", ".geojson"}
    VALID_GEOMETRY_TYPES: Set[int] = {
        ogr.wkbPoint, ogr.wkbPolygon, ogr.wkbMultiPoint, ogr.wkbMultiPolygon
    }
    EXPECTED_EPSG: str = "4326"
    MIN_AREA_HA_FOR_POLYGON: float = 4.0
    METERS_SQ_PER_HECTARE: float = 10000.0
    MAX_FILE_SIZE_MB: int = 25
    SIMPLIFY_TOLERANCE: float = 0.0001

    def __init__(self, input_dir: str, base_output_dir: str,
                 simplify_geometries: bool = True,
                 autofix_geometries: bool = True,
                 identify_candidates: bool = True):
        """Initializes the assistant for a single run with specific settings."""
        self.run_date = date.today().strftime('%Y%m%d')
        self.input_dir = Path(input_dir)
        self.output_dir = Path(base_output_dir) / self.run_date

        self.simplify_geometries = simplify_geometries
        self.autofix_geometries = autofix_geometries
        self.identify_candidates = identify_candidates

        self.unsupported_dir = self.output_dir / "01_unsupported"
        self.invalid_global_dir = self.output_dir / "02_invalid_global"
        self.review_global_dir = self.output_dir / "03_requires_review_global"
        self.processed_valid_dir = self.output_dir / "04_processed_valid"
        self.processed_review_dir = self.output_dir / "05_processed_review_features"
        self.conversion_candidates_dir = self.output_dir / "06_candidates_for_conversion"

        for folder in [
            self.unsupported_dir, self.invalid_global_dir, self.review_global_dir,
            self.processed_valid_dir, self.processed_review_dir, self.conversion_candidates_dir
        ]:
            folder.mkdir(parents=True, exist_ok=True)

        report_name = f"report_{self.run_date}.csv"
        self.report_path = self.output_dir / report_name
        self._initialize_report()

    def _initialize_report(self):
        with open(self.report_path, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Dataset Name", "Initial Status", "Processing Status",
                "Total Features", "Valid Large Polygons", "Features for Review",
                "Auto-fixed Features", "Small Polygons Found (<4ha)", "Reason / Notes"
            ])

    @staticmethod
    def _get_epsg_code(srs: Optional[osr.SpatialReference]) -> Optional[str]:
        if srs is None: return None
        srs.AutoIdentifyEPSG()
        return srs.GetAuthorityCode(None)

    @staticmethod
    def _check_polygon(geom: ogr.Geometry) -> Tuple[bool, str]:
        if geom.IsEmpty(): return False, "Empty geometry"
        if geom.GetGeometryCount() > 1: return False, "Polygon with holes"
        if not geom.IsValid(): return False, "Invalid geometry (self-intersection)"
        return True, ""

    def _get_area_in_hectares(self, geom: ogr.Geometry) -> float:
        if geom is None or geom.IsEmpty(): return 0.0
        source_srs = osr.SpatialReference()
        source_srs.ImportFromEPSG(4326)
        centroid = geom.Centroid()
        if centroid is None: return 0.0
        lon, lat = centroid.GetX(), centroid.GetY()
        if not -90 <= lat <= 90:
            logging.warning(f"Invalid latitude ({lat}) found. Treating area as 0 ha.")
            return 0.0
        utm_zone = math.floor((lon + 180) / 6) + 1
        target_srs = osr.SpatialReference()
        target_srs.SetWellKnownGeogCS("WGS84")
        target_srs.SetUTM(int(utm_zone), lat >= 0)
        try:
            transform = osr.CoordinateTransformation(source_srs, target_srs)
            geom_clone = geom.Clone()
            geom_clone.Transform(transform)
            return geom_clone.GetArea() / self.METERS_SQ_PER_HECTARE
        except RuntimeError as e:
            logging.warning(f"Projection error during area calculation: {e}. Treating as 0 ha.")
            return 0.0

    def _partition_dataset(self, dataset_path: Path) -> Dict:
        stats = {
            'total': 0, 'valid_large': 0, 'review': 0, 'autofixed': 0,
            'initially_invalid': 0, 'candidates': 0
        }
        in_ds, valid_ds, review_ds, candidates_ds = None, None, None, None
        try:
            in_ds = ogr.Open(str(dataset_path), 0)
            in_layer = in_ds.GetLayer()
            in_srs, in_layer_defn = in_layer.GetSpatialRef(), in_layer.GetLayerDefn()

            driver_name = "GeoJSON" if dataset_path.suffix.lower() == '.geojson' else "ESRI Shapefile"
            driver = ogr.GetDriverByName(driver_name)

            base_out_name = dataset_path.stem
            valid_path = self.processed_valid_dir / f"{base_out_name}_valid{dataset_path.suffix}"
            review_path = self.processed_review_dir / f"{base_out_name}_review{dataset_path.suffix}"
            candidates_path = self.conversion_candidates_dir / f"{base_out_name}_candidates{dataset_path.suffix}"

            valid_ds = driver.CreateDataSource(str(valid_path))
            review_ds = driver.CreateDataSource(str(review_path))
            candidates_ds = driver.CreateDataSource(str(candidates_path))

            valid_layer = valid_ds.CreateLayer('valid', in_srs, in_layer.GetGeomType())
            review_layer = review_ds.CreateLayer('review', in_srs, in_layer.GetGeomType())
            candidates_layer = candidates_ds.CreateLayer('candidates', in_srs, in_layer.GetGeomType())

            for i in range(in_layer_defn.GetFieldCount()):
                field_defn = in_layer_defn.GetFieldDefn(i)
                valid_layer.CreateField(field_defn)
                review_layer.CreateField(field_defn)
                candidates_layer.CreateField(field_defn)

            for in_feature in in_layer:
                stats['total'] += 1
                geom = in_feature.GetGeometryRef()
                is_feature_valid, was_autofixed = True, False

                if not geom:
                    is_feature_valid = False
                elif geom.GetGeometryType() in (ogr.wkbPolygon, ogr.wkbMultiPolygon):
                    is_feature_valid, _ = self._check_polygon(geom)
                    if not is_feature_valid:
                        stats['initially_invalid'] += 1
                        if self.autofix_geometries:
                            fixed_geom = geom.Buffer(0)
                            if fixed_geom and not fixed_geom.IsEmpty():
                                if fixed_geom.IsValid():
                                    is_feature_valid, was_autofixed, geom = True, True, fixed_geom

                if is_feature_valid:
                    feature_to_write = in_feature.Clone()
                    if was_autofixed:
                        stats['autofixed'] += 1
                        feature_to_write.SetGeometry(geom)

                    geom_to_write = feature_to_write.GetGeometryRef()

                    if self.identify_candidates and geom_to_write.GetGeometryType() in (
                    ogr.wkbPolygon, ogr.wkbMultiPolygon):
                        area_ha = self._get_area_in_hectares(geom_to_write)
                        if area_ha < self.MIN_AREA_HA_FOR_POLYGON:
                            stats['candidates'] += 1
                            candidates_layer.CreateFeature(feature_to_write)
                        else:
                            stats['valid_large'] += 1
                            if self.simplify_geometries:
                                simplified_geom = geom_to_write.SimplifyPreserveTopology(self.SIMPLIFY_TOLERANCE)
                                feature_to_write.SetGeometry(simplified_geom)
                            valid_layer.CreateFeature(feature_to_write)
                    else:  # It's a Point, or candidate identification is off
                        stats['valid_large'] += 1
                        valid_layer.CreateFeature(feature_to_write)
                else:
                    stats['review'] += 1
                    review_layer.CreateFeature(in_feature.Clone())

            # Clean up empty files
            if stats['valid_large'] == 0: valid_ds = None; driver.DeleteDataSource(str(valid_path))
            if stats['review'] == 0: review_ds = None; driver.DeleteDataSource(str(review_path))
            if stats['candidates'] == 0: candidates_ds = None; driver.DeleteDataSource(str(candidates_path))

            return stats
        finally:
            in_ds, valid_ds, review_ds, candidates_ds = None, None, None, None

    def _log_to_report(self, dataset_name, initial_status, processing_status, stats, reason):
        with open(self.report_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                dataset_name, initial_status, processing_status,
                stats.get('total', 'N/A'), stats.get('valid_large', 'N/A'),
                stats.get('review', 'N/A'), stats.get('autofixed', 'N/A'),
                stats.get('candidates', 'N/A'), reason
            ])

    def _move_and_log_dataset(self, dataset_path, target_dir, status, reason):
        logging.warning(f"  -> Global issue found: {reason}. Moving entire dataset.")
        self._move_dataset_components(dataset_path, target_dir)
        self._log_to_report(dataset_path.name, status, "SKIPPED", {}, reason)

    def _move_dataset_components(self, source_path: Path, target_dir: Path):
        try:
            if source_path.suffix.lower() == '.geojson':
                if source_path.exists(): shutil.move(str(source_path), target_dir / source_path.name)
            elif source_path.suffix.lower() == '.shp':
                base_name = source_path.stem
                for component_file in self.input_dir.glob(f'{base_name}.*'):
                    if component_file.exists():
                        shutil.move(str(component_file), target_dir / component_file.name)
        except Exception as e:
            logging.error(f"Failed to move component {source_path.name}: {e}")

    def _delete_dataset_components(self, source_path: Path):
        logging.info(f"  -> Cleaning up original file: {source_path.name}")
        try:
            if source_path.suffix.lower() == '.geojson':
                if source_path.exists(): source_path.unlink()
            elif source_path.suffix.lower() == '.shp':
                base_name = source_path.stem
                for component_file in self.input_dir.glob(f'{base_name}.*'):
                    if component_file.exists(): component_file.unlink()
        except Exception as e:
            logging.error(f"Failed to delete component {source_path.name}: {e}")

    def run(self):
        """
        Public method to run the entire QA process. This will be called by the web server.
        """
        logging.info(f"--- Starting QA run for {self.run_date} ---")
        logging.info(f"Input directory: {self.input_dir}")
        logging.info(f"Output directory: {self.output_dir}")
        logging.info(f"Geometry simplification is {'ENABLED' if self.simplify_geometries else 'DISABLED'}")
        logging.info(f"Geometry auto-fix is {'ENABLED' if self.autofix_geometries else 'DISABLED'}")
        logging.info(f"Small polygon identification is {'ENABLED' if self.identify_candidates else 'DISABLED'}")

        datasets_to_process = [p for p in self.input_dir.iterdir() if p.suffix.lower() in self.DATASET_TRIGGERS]
        if not datasets_to_process:
            logging.warning("No new datasets found to process.")
            return

        for dataset_path in datasets_to_process:
            if not dataset_path.exists(): continue
            dataset_name = dataset_path.name
            logging.info(f"Processing: {dataset_name}...")

            try:
                total_size_bytes = sum(f.stat().st_size for f in self.input_dir.glob(f'{dataset_path.stem}.*'))
                if (total_size_bytes / (1024 * 1024)) > self.MAX_FILE_SIZE_MB:
                    self._move_and_log_dataset(dataset_path, self.invalid_global_dir, "INVALID_SIZE",
                                               f"Exceeds {self.MAX_FILE_SIZE_MB}MB limit")
                    continue
                ds = ogr.Open(str(dataset_path), 0)
                epsg = self._get_epsg_code(ds.GetLayer().GetSpatialRef())
                ds = None
                if epsg != self.EXPECTED_EPSG:
                    self._move_and_log_dataset(dataset_path, self.review_global_dir, "WRONG_EPSG", f"EPSG is {epsg}")
                    continue

                logging.info("  -> Pre-checks passed. Starting feature-level processing...")
                partition_stats = self._partition_dataset(dataset_path)

                status = "PROCESSED_WITH_ISSUES" if (
                        partition_stats['review'] > 0 or partition_stats['candidates'] > 0) else "PROCESSED_CLEAN"
                note = ""
                if partition_stats[
                    'review'] > 0: note += f"{partition_stats['review']} features require manual review. "
                if partition_stats[
                    'candidates'] > 0: note += f"{partition_stats['candidates']} small polygons identified. "
                if partition_stats['autofixed'] > 0: note += f"{partition_stats['autofixed']} features were auto-fixed."
                if not note: note = "All features are valid."

                self._log_to_report(dataset_name, "PASSED_PRECHECK", status, partition_stats, note.strip())

                logging.info(
                    f"  -> Processing complete. Total: {partition_stats['total']} | "
                    f"Valid (>=4ha): {partition_stats['valid_large']} | "
                    f"For Review: {partition_stats['review']} | "
                    f"Auto-fixed: {partition_stats['autofixed']} | "
                    f"Small Poly Candidates: {partition_stats['candidates']}"
                )

                self._delete_dataset_components(dataset_path)

            except Exception as e:
                logging.error(f"  -> Critical error processing {dataset_name}: {e}", exc_info=True)
                self._move_and_log_dataset(dataset_path, self.invalid_global_dir, "PROCESSING_ERROR", str(e))

        for remaining_file in self.input_dir.iterdir():
            if remaining_file.is_file():
                self._log_to_report(remaining_file.name, "UNSUPPORTED", "SKIPPED", {}, "Not a trigger GIS file")
                shutil.move(str(remaining_file), self.unsupported_dir / remaining_file.name)

        logging.info(f"--- Run completed. Report saved to: {self.report_path} ---")
