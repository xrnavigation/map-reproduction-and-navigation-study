"""End-to-end participant-vs-baseline scoring pipeline.

This module handles:
1) loading and normalizing GeoJSON features,
2) preset-object exclusions per map,
3) feature matching,
4) metric aggregation and report generation.
"""

import json
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import geopandas as gpd
import pandas as pd

from .constants import BASELINE_DIR, BLIND_DIR, RESULTS_XLSX, SIGHTED_DIR
from .metrics import (
    bearing_between_points,
    compute_orientation_angle,
    feature_size,
    map_diagonal,
    orientation_similarity,
    ratio_similarity,
    safe_mean,
    topology_relation,
)


def normalize_feature_name(name: Optional[str]) -> str:
    """Normalize labels to simplify robust matching."""
    if not name:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def infer_map_number(file_path: Path) -> Optional[int]:
    """Parse map id from participant filename."""
    match = re.search(r"_map_(\d+)\.geojson$", file_path.name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def load_geojson_features(path: Path) -> gpd.GeoDataFrame:
    """Load one GeoJSON file and add helper columns used downstream."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    features = raw.get("features", [])
    gdf = gpd.GeoDataFrame.from_features(features) if features else gpd.GeoDataFrame()
    if gdf.empty:
        return gdf

    # Ensure geometry column exists for GeoPandas operations.
    if "geometry" not in gdf.columns:
        gdf["geometry"] = None
    gdf = gdf.set_geometry("geometry")

    def extract_name(row: pd.Series) -> str:
        for key in ("name", "label", "title"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    # Canonical helper columns used by matching/exclusion/scoring.
    gdf["feature_name"] = gdf.apply(extract_name, axis=1)
    gdf["name_norm"] = gdf["feature_name"].apply(normalize_feature_name)
    gdf["geom_type"] = gdf.geometry.geom_type
    gdf["centroid_y"] = gdf.geometry.centroid.y
    return gdf


def apply_preset_exclusions(gdf: gpd.GeoDataFrame, map_number: int) -> gpd.GeoDataFrame:
    """Remove objects that should be excluded from scoring for each map."""
    if gdf.empty:
        return gdf

    # Grid points are scaffolding, not target map objects.
    filtered = gdf[~gdf["name_norm"].str.startswith("gridpoint", na=False)].copy()

    if map_number == 2:
        # Requested static exclusions for Map 2.
        filtered = filtered[~filtered["name_norm"].isin({"breakroom", "flagpole", "elevator"})]
        # "Top 2 roads": remove the top two walkways by y-centroid.
        walkways = filtered[filtered["name_norm"] == "walkway"].sort_values("centroid_y", ascending=False)
        if len(walkways) >= 2:
            filtered = filtered.drop(index=walkways.head(2).index)

    if map_number == 3:
        # Requested static exclusions for Map 3.
        filtered = filtered[~filtered["name_norm"].isin({"dancestudio", "watermachine"})]
        # Remove top and bottom walkways by y-centroid.
        walkways = filtered[filtered["name_norm"] == "walkway"].sort_values("centroid_y", ascending=False)
        if len(walkways) >= 1:
            filtered = filtered.drop(index=walkways.head(1).index)
        if len(walkways) >= 2:
            filtered = filtered.drop(index=walkways.tail(1).index)

    return filtered.reset_index(drop=True)


def nearest_match(base_row: pd.Series, participant_df: gpd.GeoDataFrame, candidate_indices: List[int]) -> Optional[int]:
    """Select nearest centroid candidate among valid indices."""
    if not candidate_indices:
        return None

    base_centroid = base_row.geometry.centroid
    best_idx = None
    best_distance = float("inf")
    for idx in candidate_indices:
        distance = base_centroid.distance(participant_df.loc[idx, "geometry"].centroid)
        if distance < best_distance:
            best_distance = distance
            best_idx = idx
    return best_idx


def match_features(
    baseline_df: gpd.GeoDataFrame,
    participant_df: gpd.GeoDataFrame,
) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
    """Two-stage greedy matching: exact name+type first, then type fallback."""
    if baseline_df.empty and participant_df.empty:
        return [], [], []

    base_remaining = list(baseline_df.index)
    part_remaining = set(participant_df.index)
    matched: List[Tuple[int, int]] = []

    # Pass 1: exact semantic + geometry type match.
    for b_idx in list(base_remaining):
        b_row = baseline_df.loc[b_idx]
        candidates = [
            p_idx
            for p_idx in part_remaining
            if participant_df.loc[p_idx, "geom_type"] == b_row["geom_type"]
            and participant_df.loc[p_idx, "name_norm"] == b_row["name_norm"]
        ]
        chosen = nearest_match(b_row, participant_df, candidates)
        if chosen is not None:
            matched.append((b_idx, chosen))
            part_remaining.remove(chosen)
            base_remaining.remove(b_idx)

    # Pass 2: geometry-type fallback to maximize total pairing.
    for b_idx in list(base_remaining):
        b_row = baseline_df.loc[b_idx]
        candidates = [
            p_idx
            for p_idx in part_remaining
            if participant_df.loc[p_idx, "geom_type"] == b_row["geom_type"]
        ]
        chosen = nearest_match(b_row, participant_df, candidates)
        if chosen is not None:
            matched.append((b_idx, chosen))
            part_remaining.remove(chosen)
            base_remaining.remove(b_idx)

    return matched, base_remaining, sorted(part_remaining)


def explain_missing_extra(
    missing_count: int,
    extra_count: int,
    missing_names: Sequence[str],
    extra_names: Sequence[str],
) -> str:
    """Human-readable explanation for missing/extra counts."""
    if missing_count == 0 and extra_count == 0:
        return "All baseline features were matched; no extra participant features remained."

    if missing_count == 1 and extra_count == 1:
        return (
            "One baseline feature was not matched and one participant feature was unmatched. "
            "This usually means one drawn object was misplaced, mislabeled, or had a different geometry type. "
            f"Missing sample: {', '.join(missing_names[:3]) or 'n/a'}. "
            f"Extra sample: {', '.join(extra_names[:3]) or 'n/a'}."
        )

    return (
        f"{missing_count} baseline features were unmatched and {extra_count} participant features were unmatched. "
        f"Missing sample: {', '.join(missing_names[:3]) or 'n/a'}. "
        f"Extra sample: {', '.join(extra_names[:3]) or 'n/a'}."
    )


def build_description_row() -> Dict[str, str]:
    """Static formula definitions inserted as row 2 in report output."""
    return {
        "Group": "Scoring metadata",
        "Participant": "Folder participant id (p#)",
        "Map": "Baseline map number used for comparison",
        "Reference Features": "Count of baseline features after preset-object exclusions",
        "Participant Features": "Count of participant features after the same exclusions",
        "Matched Features": "Number of baseline-participant feature pairs matched by name/type then centroid proximity",
        "Missing Features": "Missing baseline features = Reference Features - Matched Features (baseline objects with no acceptable match)",
        "Extra Features": "Participant Features - Matched Features (participant objects not matched to baseline)",
        "Missing/Extra Notes": "Explanation of why missing/extra can happen (e.g., mislabel, misplaced object, type mismatch)",
        "Name/Type": "matched exact (name + geometry type) / Reference Features",
        "Shape": "1 - min(HausdorffDistance / map diagonal, 1)",
        "Size": "Polygon: area ratio similarity; Line: total length ratio similarity; Point: neutral size",
        "Orientation": "1 - (orientation mismatch from north in degrees / 180), using 1..360 angle scale",
        "Distance": "Pairwise centroid distance consistency between matched baseline objects and participant objects",
        "Direction": "Pairwise centroid bearing consistency (angle-from-north comparison)",
        "Topological": "Fraction of matched pair-combinations with same topological relation (touch/contain/disjoint/intersect)",
        "Exact Location": "1 - min(centroid distance / map diagonal, 1) averaged over matched features",
        "Composite Map Similarity Score": "Average of Name/Type, Shape, Size, Orientation, Distance, Direction, Topological, Exact Location",
        "Accuracy %": "Composite Map Similarity Score * 100",
    }


@dataclass
class AnalysisContext:
    group: str
    participant: str
    map_number: int
    baseline_file: Path
    participant_file: Path


def collect_participant_maps() -> List[AnalysisContext]:
    """Discover all participant map files that can be scored."""
    contexts: List[AnalysisContext] = []
    for group, group_dir in (("blind", BLIND_DIR), ("sighted", SIGHTED_DIR)):
        if not group_dir.exists():
            continue
        for participant_dir in sorted(group_dir.glob("p*")):
            if not participant_dir.is_dir():
                continue
            for geojson_file in sorted(participant_dir.glob("*.geojson")):
                map_number = infer_map_number(geojson_file)
                if map_number is None:
                    continue
                baseline_file = BASELINE_DIR / f"baseline_map_{map_number}.geojson"
                if baseline_file.exists():
                    # Keep one context per participant-map file.
                    contexts.append(
                        AnalysisContext(
                            group=group,
                            participant=participant_dir.name,
                            map_number=map_number,
                            baseline_file=baseline_file,
                            participant_file=geojson_file,
                        )
                    )
    return contexts


def analyze_single_context(ctx: AnalysisContext) -> Dict[str, object]:
    """Run full scoring workflow for one participant-map pair."""
    baseline = apply_preset_exclusions(load_geojson_features(ctx.baseline_file), ctx.map_number)
    participant = apply_preset_exclusions(load_geojson_features(ctx.participant_file), ctx.map_number)

    matched_pairs, missing_indices, extra_indices = match_features(baseline, participant)
    ref_count = len(baseline)
    participant_count = len(participant)
    map_diag = map_diagonal(baseline if not baseline.empty else participant)

    shape_scores: List[float] = []
    size_scores: List[float] = []
    orientation_scores: List[float] = []
    location_scores: List[float] = []

    # Per-object metrics on matched feature pairs.
    for b_idx, p_idx in matched_pairs:
        b_geom = baseline.loc[b_idx, "geometry"]
        p_geom = participant.loc[p_idx, "geometry"]
        shape_scores.append(max(0.0, 1.0 - min(b_geom.hausdorff_distance(p_geom) / map_diag, 1.0)))
        size_scores.append(ratio_similarity(feature_size(b_geom), feature_size(p_geom)))
        orientation_scores.append(orientation_similarity(compute_orientation_angle(b_geom), compute_orientation_angle(p_geom)))
        location_scores.append(max(0.0, 1.0 - min(b_geom.centroid.distance(p_geom.centroid) / map_diag, 1.0)))

    distance_scores: List[float] = []
    direction_scores: List[float] = []
    topology_scores: List[float] = []

    # Pairwise relational metrics preserve map structure consistency.
    for (b1, p1), (b2, p2) in combinations(matched_pairs, 2):
        bg1 = baseline.loc[b1, "geometry"]
        bg2 = baseline.loc[b2, "geometry"]
        pg1 = participant.loc[p1, "geometry"]
        pg2 = participant.loc[p2, "geometry"]

        distance_scores.append(ratio_similarity(bg1.centroid.distance(bg2.centroid), pg1.centroid.distance(pg2.centroid)))
        direction_scores.append(
            orientation_similarity(
                bearing_between_points(bg1.centroid, bg2.centroid),
                bearing_between_points(pg1.centroid, pg2.centroid),
            )
        )
        topology_scores.append(1.0 if topology_relation(bg1, bg2) == topology_relation(pg1, pg2) else 0.0)

    # Name/Type rewards exact semantic match within aligned geometry class.
    exact_name_type = sum(
        1
        for b_idx, p_idx in matched_pairs
        if baseline.loc[b_idx, "name_norm"] == participant.loc[p_idx, "name_norm"]
        and baseline.loc[b_idx, "geom_type"] == participant.loc[p_idx, "geom_type"]
    )

    row = {
        "Group": ctx.group,
        "Participant": ctx.participant,
        "Map": ctx.map_number,
        "Reference Features": ref_count,
        "Participant Features": participant_count,
        "Matched Features": len(matched_pairs),
        "Missing Features": len(missing_indices),
        "Extra Features": len(extra_indices),
        "Missing/Extra Notes": explain_missing_extra(
            missing_count=len(missing_indices),
            extra_count=len(extra_indices),
            missing_names=[str(baseline.loc[i, "feature_name"]) for i in missing_indices],
            extra_names=[str(participant.loc[i, "feature_name"]) for i in extra_indices],
        ),
        "Name/Type": round((exact_name_type / ref_count) if ref_count else 1.0, 3),
        "Shape": round(safe_mean(shape_scores), 3),
        "Size": round(safe_mean(size_scores), 3),
        "Orientation": round(safe_mean(orientation_scores), 3),
        "Distance": round(safe_mean(distance_scores), 3),
        "Direction": round(safe_mean(direction_scores), 3),
        "Topological": round(safe_mean(topology_scores), 3),
        "Exact Location": round(safe_mean(location_scores), 3),
    }

    # Composite is the uniform average of the eight core dimensions.
    metrics = [
        row["Name/Type"],
        row["Shape"],
        row["Size"],
        row["Orientation"],
        row["Distance"],
        row["Direction"],
        row["Topological"],
        row["Exact Location"],
    ]
    composite = sum(metrics) / len(metrics)
    row["Composite Map Similarity Score"] = round(composite, 3)
    row["Accuracy %"] = round(composite * 100.0, 2)
    return row


def run_analysis() -> pd.DataFrame:
    """Run full dataset analysis and persist CSV/XLSX reports."""
    rows = [analyze_single_context(ctx) for ctx in collect_participant_maps()]
    # Sort output for stable review/diff behavior.
    rows = sorted(rows, key=lambda r: (r["Group"], int(str(r["Participant"]).lstrip("p")), r["Map"]))

    score_df = pd.DataFrame(rows)
    # Excel output must have two sheets: blind and sighted.
    with pd.ExcelWriter(RESULTS_XLSX, engine="openpyxl") as writer:
        for group_name in ("blind", "sighted"):
            group_df = score_df[score_df["Group"] == group_name].copy()
            if not group_df.empty:
                group_df["__participant_num"] = group_df["Participant"].map(lambda v: int(str(v).lstrip("p")))
                group_df = group_df.sort_values(by=["__participant_num", "Map"]).drop(columns=["__participant_num"])
            sheet_df = pd.concat([pd.DataFrame([build_description_row()]), group_df], ignore_index=True)
            sheet_df.to_excel(writer, sheet_name=group_name, index=False)
    return score_df
