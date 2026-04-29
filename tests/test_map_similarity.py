import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import geopandas as gpd
from shapely.geometry import LineString, Polygon, Point

from audiom_map_similarity_analysis import (
    compute_orientation_angle,
    orientation_similarity,
    feature_size,
    build_description_row,
    explain_missing_extra,
    apply_preset_exclusions,
)
from map_similarity.metrics import safe_mean
from map_similarity.pipeline import collect_participant_maps


class MapSimilarityTests(unittest.TestCase):
    def test_polygon_size_uses_area(self):
        square = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])
        self.assertAlmostEqual(feature_size(square), 4.0)

    def test_linestring_size_uses_segment_length_sum(self):
        # Segment lengths: 5 and 5, total = 10
        line = LineString([(0, 0), (3, 4), (6, 8)])
        self.assertAlmostEqual(feature_size(line), 10.0)

    def test_orientation_is_angle_from_north_in_valid_range(self):
        north_line = LineString([(0, 0), (0, 10)])
        east_line = LineString([(0, 0), (10, 0)])
        north_angle = compute_orientation_angle(north_line)
        east_angle = compute_orientation_angle(east_line)
        self.assertTrue(1 <= north_angle <= 360)
        self.assertTrue(1 <= east_angle <= 360)
        self.assertAlmostEqual(north_angle, 360.0)
        self.assertAlmostEqual(east_angle, 90.0)

    def test_orientation_similarity_wraps_360(self):
        # 359 vs 1 degrees should be very close, not opposite.
        score = orientation_similarity(359.0, 1.0)
        self.assertGreater(score, 0.95)

    def test_build_description_row_has_static_formula_text(self):
        row = build_description_row()
        self.assertIn("Shape", row)
        self.assertIn("orientation mismatch", row["Orientation"].lower())
        self.assertIn("missing", row["Missing Features"].lower())

    def test_explain_missing_extra_reason(self):
        note = explain_missing_extra(
            missing_count=1,
            extra_count=1,
            missing_names=["conference room"],
            extra_names=["meeting room"],
        )
        self.assertIn("one baseline feature was not matched", note.lower())
        self.assertIn("one participant feature was unmatched", note.lower())

    def test_safe_mean_empty_defaults_to_zero(self):
        self.assertEqual(safe_mean([]), 0.0)

    def test_apply_preset_exclusions_map2(self):
        rows = [
            {"name_norm": "breakroom", "geom_type": "Polygon", "centroid_y": 5.0},
            {"name_norm": "flagpole", "geom_type": "Point", "centroid_y": 4.0},
            {"name_norm": "elevator", "geom_type": "Polygon", "centroid_y": 3.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 10.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 9.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 1.0},
            {"name_norm": "storage", "geom_type": "Polygon", "centroid_y": 2.0},
        ]
        gdf = gpd.GeoDataFrame(rows, geometry=[Point(0, 0)] * len(rows))
        filtered = apply_preset_exclusions(gdf, map_number=2)
        names = list(filtered["name_norm"])
        self.assertNotIn("breakroom", names)
        self.assertNotIn("flagpole", names)
        self.assertNotIn("elevator", names)
        self.assertEqual(names.count("walkway"), 1)

    def test_apply_preset_exclusions_map3(self):
        rows = [
            {"name_norm": "dancestudio", "geom_type": "Polygon", "centroid_y": 5.0},
            {"name_norm": "watermachine", "geom_type": "Point", "centroid_y": 4.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 10.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 6.0},
            {"name_norm": "walkway", "geom_type": "LineString", "centroid_y": 1.0},
            {"name_norm": "frontdesk", "geom_type": "Polygon", "centroid_y": 2.0},
        ]
        gdf = gpd.GeoDataFrame(rows, geometry=[Point(0, 0)] * len(rows))
        filtered = apply_preset_exclusions(gdf, map_number=3)
        names = list(filtered["name_norm"])
        self.assertNotIn("dancestudio", names)
        self.assertNotIn("watermachine", names)
        self.assertEqual(names.count("walkway"), 1)
        self.assertIn("frontdesk", names)

    def test_collect_participant_maps_uses_expected_assignments(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blind_dir = root / "blind_participants"
            sighted_dir = root / "sighted_participants"
            baseline_dir = root / "baseline_maps"
            blind_p1 = blind_dir / "p1"
            sighted_p6 = sighted_dir / "p6"
            blind_p1.mkdir(parents=True)
            sighted_p6.mkdir(parents=True)
            baseline_dir.mkdir()

            for map_number in (1, 2, 3):
                baseline = f'{{"type":"FeatureCollection","features":[],"baseline":{map_number}}}'
                participant = f'{{"type":"FeatureCollection","features":[],"participant":{map_number}}}'
                (baseline_dir / f"baseline_map_{map_number}.geojson").write_text(baseline, encoding="utf-8")
                (blind_p1 / f"Blind_p1_Spatial_Knowledge_map_{map_number}.geojson").write_text(
                    participant, encoding="utf-8"
                )
                (sighted_p6 / f"Sighted_p6_Spatial_Knowledge_map_{map_number}.geojson").write_text(
                    participant, encoding="utf-8"
                )

            assignments = {
                "blind": {"p1": {2}},
                "sighted": {"p6": {2, 3}},
            }
            with patch("map_similarity.pipeline.BLIND_DIR", blind_dir), patch(
                "map_similarity.pipeline.SIGHTED_DIR", sighted_dir
            ), patch("map_similarity.pipeline.BASELINE_DIR", baseline_dir):
                contexts = collect_participant_maps(assignments)

        scored = sorted((ctx.group, ctx.participant, ctx.map_number) for ctx in contexts)
        self.assertEqual(scored, [("blind", "p1", 2), ("sighted", "p6", 2), ("sighted", "p6", 3)])


if __name__ == "__main__":
    unittest.main()
