import shutil
from pathlib import Path
from typing import Optional, Dict, Callable

from . import validation, reports, transformations, io
from .validation import ID_FIELD_NAME, DATASET_TRIGGERS


class EudrGisQaAssistant:
    EXPECTED_EPSG = "4326"

    def __init__(self, input_dir: str, base_output_dir: str,
                 simplify_geometries: bool = True,
                 autofix_geometries: bool = True,
                 identify_candidates: bool = True):
        self.run_date = Path(base_output_dir).name
        self.input_dir = Path(input_dir)
        self.output_dir = Path(base_output_dir)
        self.simplify_geometries = simplify_geometries
        self.autofix_geometries = autofix_geometries
        self.identify_candidates = identify_candidates
        
        self.traced_originals_dir = self.output_dir / "00_original_with_ids"
        self.exploded_dir = self.output_dir / "00a_exploded_features"
        self.unsupported_dir = self.output_dir / "01_unsupported"
        self.invalid_global_dir = self.output_dir / "02_invalid_global"
        self.processed_valid_dir = self.output_dir / "04_processed_valid"
        self.processed_review_dir = self.output_dir / "05_processed_review_features"
        self.conversion_candidates_dir = self.output_dir / "06_candidates_for_conversion"
        
        for folder in [self.traced_originals_dir, self.exploded_dir, self.unsupported_dir, 
                       self.invalid_global_dir, self.processed_valid_dir, self.processed_review_dir, 
                       self.conversion_candidates_dir]:
            folder.mkdir(parents=True, exist_ok=True)
        
        self.summary_report_path = self.output_dir / f"summary_report_{self.run_date}.csv"
        self.detailed_report_path = self.output_dir / f"detailed_report_{self.run_date}.csv"
        reports.initialize_reports(self.summary_report_path, self.detailed_report_path)

    def run(self, update_progress: Optional[Callable[[Dict], None]] = None):
        datasets_to_process = [p for p in self.input_dir.iterdir() 
                               if p.is_file() and p.suffix.lower() in DATASET_TRIGGERS]
        
        if not datasets_to_process:
            if update_progress:
                update_progress({'progress': 100, 'message': 'No GIS files found.', 'step': 'Completed'})
            return

        def update_step_progress(step_key, step_progress, message, step_name):
            progress_ranges = {
                'inject_ids': (0, 10), 'explode': (10, 20), 'validate': (20, 80), 
                'reports': (80, 90), 'cleanup': (90, 95)
            }
            start, end = progress_ranges[step_key]
            total_progress = start + (step_progress * (end - start) / 100)
            if update_progress:
                update_progress({'progress': int(total_progress), 'message': message, 'step': step_name})

        traced_files = []
        for i, dataset_path in enumerate(datasets_to_process):
            step_progress = (i / len(datasets_to_process)) * 100
            update_step_progress('inject_ids', step_progress, f'Processing {dataset_path.name}...', 'Step 1/5: Adding IDs')
            traced_file = io.inject_traceability_id(dataset_path, self.traced_originals_dir, ID_FIELD_NAME)
            if traced_file:
                traced_files.append(traced_file)

        exploded_files = []
        for i, traced_file_path in enumerate(traced_files):
            step_progress = (i / len(traced_files)) * 100
            update_step_progress('explode', step_progress, f'Exploding {traced_file_path.name}...', 'Step 2/5: Exploding Features')
            exploded_file = io.explode_multipart_features(traced_file_path, self.exploded_dir, ID_FIELD_NAME)
            if exploded_file:
                exploded_files.append(exploded_file)

        update_step_progress('validate', 0, 'Starting validation...', 'Step 3/5: Validating')
        all_detailed_rows = []
        for i, dataset_path in enumerate(exploded_files):
            step_progress = (i / len(exploded_files)) * 100
            update_step_progress('validate', step_progress, f'Validating {dataset_path.name}...', 'Step 3/5: Validating')
            
            ds = io.open_dataset(dataset_path)
            if not ds:
                continue
            
            original_name = Path(dataset_path.name).name
            
            if not validation.validate_global_crs(ds):
                io.move_and_log_dataset(dataset_path, self.invalid_global_dir, 
                                        "WRONG_EPSG", f"EPSG is not {self.EXPECTED_EPSG}", 
                                        original_name, self.summary_report_path)
                continue

            partition_stats, detailed_rows = transformations.partition_and_process_dataset(
                ds, dataset_path.stem, self.processed_valid_dir, self.processed_review_dir,
                self.conversion_candidates_dir, self.simplify_geometries, self.autofix_geometries,
                self.identify_candidates
            )
            all_detailed_rows.extend(detailed_rows)
            
            status = "PROCESSED_WITH_ISSUES" if (partition_stats['review'] > 0 or partition_stats['candidates'] > 0) else "PROCESSED_CLEAN"
            note_parts = []
            if partition_stats['review'] > 0:
                note_parts.append(f"{partition_stats['review']} features for review")
            if partition_stats['candidates'] > 0:
                note_parts.append(f"{partition_stats['candidates']} small polygons found")
            
            attribute_summary = validation.summarize_attribute_status([row['attribute_status'] for row in detailed_rows])
            reports.log_to_summary_report(self.summary_report_path, original_name, "PASSED_PRECHECK", 
                                        status, partition_stats, attribute_summary, 
                                        " ".join(note_parts) or "All features are valid.")
            
            io.delete_intermediate_components(dataset_path, self.traced_originals_dir, self.input_dir)

        update_step_progress('reports', 50, 'Generating reports...', 'Step 4/5: Reporting')
        reports.log_detailed_rows_to_report(self.detailed_report_path, all_detailed_rows)
        io.process_unsupported_files(self.input_dir, self.unsupported_dir, self.summary_report_path)
        
        update_step_progress('cleanup', 100, 'Analysis complete', 'Step 5/5: Complete')
