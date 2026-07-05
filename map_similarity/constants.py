from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "Analysis"
BASELINE_DIR = PROJECT_ROOT / "baseline_maps"
BLIND_DIR = PROJECT_ROOT / "blind_participants"
SIGHTED_DIR = PROJECT_ROOT / "sighted_participants"

RESULTS_XLSX = PROJECT_ROOT / "map_similarity_results.xlsx"
