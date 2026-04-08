from map_similarity import (
    apply_preset_exclusions,
    build_description_row,
    compute_orientation_angle,
    explain_missing_extra,
    feature_size,
    orientation_similarity,
    run_analysis,
)
from map_similarity.constants import RESULTS_XLSX


# Re-exported symbols above are intentionally kept for backward compatibility
# with existing imports/tests.


def main() -> None:
    run_analysis()
    print(f"analysis complete -> {RESULTS_XLSX.name}")


if __name__ == "__main__":
    main()
