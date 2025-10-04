import csv
from pathlib import Path
from typing import Dict, List, Any

def initialize_reports(summary_path: Path, detailed_path: Path):
    """Initialize report CSV files with headers."""
    with open(summary_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Dataset Name", "Initial Status", "Processing Status", "Total Features",
            "Valid Large Polygons", "Features for Review", "Auto-fixed Features",
            "Small Polygons Found (<4ha)", "Attribute Status", "Reason / Notes"
        ])
    
    with open(detailed_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "original_filename", "qa_assistant_id", "final_status",
            "action_taken", "reason_notes", "attribute_status"
        ])

def log_to_summary_report(summary_path: Path, name: str, initial: str, processing: str,
                         stats: Dict[str, Any], attr_status: str, reason: str):
    """Append a row to the summary report CSV."""
    try:
        with open(summary_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                name, initial, processing,
                stats.get('total', 'N/A'),
                stats.get('valid_large', 'N/A'),
                stats.get('review', 'N/A'),
                stats.get('autofixed', 'N/A'),
                stats.get('candidates', 'N/A'),
                attr_status,
                reason
            ])
    except Exception:
        pass

def log_detailed_rows_to_report(detailed_path: Path, rows: List[Dict]):
    """Append multiple rows to the detailed report CSV."""
    if not rows:
        return
    
    try:
        with open(detailed_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writerows(rows)
    except Exception:
        pass
