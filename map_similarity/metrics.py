"""Geometry metric helpers for map similarity scoring.

The goal of this module is to keep all low-level geometry formulas in one place,
so the pipeline logic stays readable and testable.
"""

import math
import warnings
from typing import Sequence

import geopandas as gpd
from shapely.geometry.base import BaseGeometry


def feature_size(geom: BaseGeometry) -> float:
    """Return a comparable size scalar by geometry family."""
    if geom is None or geom.is_empty:
        return 0.0
    geom_type = geom.geom_type
    # Polygon size must be area (requested by reviewer feedback).
    if "Polygon" in geom_type:
        return float(geom.area)
    # Line size must be full path length (sum of segment lengths).
    if "LineString" in geom_type:
        return float(geom.length)
    # Points have no area/length; use neutral scalar.
    return 1.0


def compute_orientation_angle(geom: BaseGeometry) -> float:
    """Compute orientation as bearing from north in [1..360]."""
    if geom is None or geom.is_empty:
        return 360.0

    def bearing(x0: float, y0: float, x1: float, y1: float) -> float:
        # atan2(dx, dy) yields north-based bearing convention.
        angle = (math.degrees(math.atan2(x1 - x0, y1 - y0)) + 360.0) % 360.0
        return 360.0 if angle == 0 else angle

    gtype = geom.geom_type
    if "LineString" in gtype:
        # For multilines, use the longest segment as dominant orientation.
        line = max(getattr(geom, "geoms", [geom]), key=lambda g: g.length)
        coords = list(line.coords)
        if len(coords) < 2:
            return 360.0
        x0, y0 = coords[0]
        x1, y1 = coords[-1]
        return bearing(x0, y0, x1, y1)

    if "Polygon" in gtype:
        # Estimate polygon orientation from its minimum rotated rectangle.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            rect = geom.minimum_rotated_rectangle
        if "Polygon" in rect.geom_type:
            coords = list(rect.exterior.coords)
            best = None
            for i in range(min(4, len(coords) - 1)):
                x0, y0 = coords[i]
                x1, y1 = coords[i + 1]
                edge = math.hypot(x1 - x0, y1 - y0)
                if best is None or edge > best[0]:
                    best = (edge, x0, y0, x1, y1)
            if best is not None:
                _, x0, y0, x1, y1 = best
                return bearing(x0, y0, x1, y1)

        if "LineString" in rect.geom_type:
            # Degenerate polygons can collapse to a line.
            coords = list(rect.coords)
            if len(coords) < 2:
                return 360.0
            x0, y0 = coords[0]
            x1, y1 = coords[-1]
            return bearing(x0, y0, x1, y1)

    return 360.0


def orientation_similarity(angle_a: float, angle_b: float) -> float:
    """Convert circular angle difference into a [0..1] similarity score."""
    diff = abs(angle_a - angle_b) % 360.0
    circular_diff = min(diff, 360.0 - diff)
    return max(0.0, 1.0 - circular_diff / 180.0)


def bearing_between_points(point_a: BaseGeometry, point_b: BaseGeometry) -> float:
    """Bearing from point A to point B using north-based convention."""
    angle = (math.degrees(math.atan2(point_b.x - point_a.x, point_b.y - point_a.y)) + 360.0) % 360.0
    return 360.0 if angle == 0 else angle


def ratio_similarity(a: float, b: float) -> float:
    """Generic ratio similarity used for size and distance consistency."""
    if a == 0 and b == 0:
        return 1.0
    if max(a, b) == 0:
        return 0.0
    return max(0.0, 1.0 - abs(a - b) / max(a, b))


def safe_mean(values: Sequence[float], default: float = 0.0) -> float:
    """Mean with explicit fallback for empty collections."""
    return sum(values) / len(values) if values else default


def topology_relation(a: BaseGeometry, b: BaseGeometry) -> str:
    """Topological relation label using geometry predicates."""
    if a.touches(b):
        return "touch"
    if a.contains(b) or b.contains(a):
        return "contain"
    if a.disjoint(b):
        return "disjoint"
    if a.intersects(b):
        return "intersect"
    return "other"


def map_diagonal(gdf: gpd.GeoDataFrame) -> float:
    """Map-scale normalization factor derived from bbox diagonal."""
    if gdf.empty:
        return 1.0
    minx, miny, maxx, maxy = gdf.total_bounds
    diag = math.hypot(maxx - minx, maxy - miny)
    return diag if diag > 0 else 1.0
