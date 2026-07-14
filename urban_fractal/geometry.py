from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import MultiPolygon, Polygon, box
from shapely import union, union_all
from shapely.ops import unary_union


HEIGHT_RE = re.compile(r"([-+]?\d+(?:[\.,]\d+)?)")


@dataclass
class BuildingSurfaceSummary:
    n_buildings: int
    footprint_area_m2: float
    footprint_area_raw_sum_m2: float
    footprint_overlap_fraction: float
    footprint_perimeter_m: float
    footprint_perimeter_raw_sum_m: float
    volume_m3: float
    roof_area_m2: float
    geometric_roof_area_m2: float
    thermal_roof_area_m2: float
    wall_area_m2: float
    wall_area_gross_m2: float
    envelope_area_m2: float
    closed_surface_area_m2: float
    ground_contact_area_m2: float
    mean_height_m: float
    median_height_m: float
    height_source_known_fraction: float
    height_source_known_area_fraction: float
    height_layer_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_metric_crs(gdf: gpd.GeoDataFrame) -> CRS:
    if gdf.crs is None:
        raise ValueError("Input GeoDataFrame has no CRS. Set CRS before analysis.")
    try:
        crs = gdf.estimate_utm_crs()
        if crs is not None:
            return crs
    except Exception:
        pass
    return CRS.from_epsg(3857)


def ensure_metric(gdf: gpd.GeoDataFrame, target_crs: str | CRS | None = None) -> gpd.GeoDataFrame:
    if gdf.empty:
        raise ValueError("GeoDataFrame is empty")
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS")
    crs = CRS.from_user_input(target_crs) if target_crs else estimate_metric_crs(gdf)
    return gdf.to_crs(crs)


def clean_polygons(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Keep polygonal features, repair invalid geometry and drop empties."""
    out = gdf.copy()
    out = out[~out.geometry.isna()].copy()
    out["geometry"] = out.geometry.make_valid()
    out = out[~out.geometry.is_empty].copy()
    out = out[out.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    out["geometry"] = out.geometry.buffer(0)
    out = out[~out.geometry.is_empty].copy()
    return out


def parse_height_value(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return v if np.isfinite(v) and v > 0 else None
    text = str(value).strip().lower().replace(",", ".")
    if not text or text in {"none", "nan", "null"}:
        return None
    m = HEIGHT_RE.search(text)
    if not m:
        return None
    try:
        v = float(m.group(1))
    except ValueError:
        return None
    if v <= 0 or not np.isfinite(v):
        return None
    if "ft" in text or "feet" in text:
        v *= 0.3048
    return v


def height_from_attributes(
    row: pd.Series,
    *,
    floor_height_m: float = 3.0,
    default_height_m: float = 12.0,
) -> tuple[float, str]:
    for key in ("height", "building:height", "HEIGHT", "Height", "h"):
        if key in row:
            h = parse_height_value(row.get(key))
            if h is not None:
                return h, key
    for key in ("building:levels", "levels", "floors", "этажность"):
        if key in row:
            lv = parse_height_value(row.get(key))
            if lv is not None:
                return lv * floor_height_m, key
    return default_height_m, "default"


def add_building_heights(
    buildings: gpd.GeoDataFrame,
    *,
    floor_height_m: float = 3.0,
    default_height_m: float = 12.0,
) -> gpd.GeoDataFrame:
    b = buildings.copy()
    values = [
        height_from_attributes(row, floor_height_m=floor_height_m, default_height_m=default_height_m)
        for _, row in b.iterrows()
    ]
    b["_height_m"] = [v[0] for v in values]
    b["_height_source"] = [v[1] for v in values]
    return b


def replace_default_heights(buildings: gpd.GeoDataFrame, default_height_m: float) -> gpd.GeoDataFrame:
    b = buildings.copy()
    if "_height_source" not in b or "_height_m" not in b:
        raise ValueError("Building heights must be assigned first")
    unknown = b["_height_source"].eq("default")
    b.loc[unknown, "_height_m"] = float(default_height_m)
    return b


def _layered_extrusion_metrics(buildings: gpd.GeoDataFrame) -> tuple[float, float, float, float, object, int]:
    """Return volume, exposed roof, exposed walls, ground area and union.

    The calculation treats buildings as vertical prisms and evaluates the union
    of all footprints at every distinct height layer. Shared walls and overlaps
    are therefore not double-counted. Height steps remain exposed, as they
    should for an exterior envelope.
    """
    b = buildings[["geometry", "_height_m"]].copy()
    b["_height_m"] = pd.to_numeric(b["_height_m"], errors="coerce").round(3)
    b = b[np.isfinite(b["_height_m"]) & (b["_height_m"] > 0)]
    if b.empty:
        raise ValueError("No positive building heights")

    groups: dict[float, list[object]] = {}
    for h, geom in zip(b["_height_m"].to_numpy(dtype=float), b.geometry):
        groups.setdefault(float(h), []).append(geom)
    heights = sorted(groups, reverse=True)

    current = None
    current_area = 0.0
    volume = 0.0
    wall_area = 0.0
    roof_area = 0.0
    for i, height in enumerate(heights):
        group_union = union_all(groups[height], grid_size=0.01)
        new_union = group_union if current is None else union(current, group_union, grid_size=0.01)
        new_area = float(new_union.area)
        roof_area += max(0.0, new_area - current_area)
        next_height = heights[i + 1] if i + 1 < len(heights) else 0.0
        thickness = float(height - next_height)
        if thickness > 0:
            volume += new_area * thickness
            wall_area += float(new_union.length) * thickness
        current = new_union
        current_area = new_area

    assert current is not None
    return volume, roof_area, wall_area, current_area, current, len(heights)


def summarize_building_surfaces(
    buildings: gpd.GeoDataFrame,
    *,
    roof_factor: float = 1.0,
) -> BuildingSurfaceSummary:
    if "_height_m" not in buildings.columns:
        raise ValueError("Call add_building_heights before summarize_building_surfaces")
    if buildings.empty:
        raise ValueError("No buildings")

    b = buildings.copy()
    areas = b.geometry.area.to_numpy(dtype=float)
    perimeters = b.geometry.length.to_numpy(dtype=float)
    heights = b["_height_m"].to_numpy(dtype=float)
    volume, geometric_roof_area, wall_area, union_area, union_geom, n_layers = _layered_extrusion_metrics(b)
    raw_area = float(np.nansum(areas))
    overlap_fraction = max(0.0, (raw_area - union_area) / raw_area) if raw_area > 0 else float("nan")
    known_feature_fraction = float(b["_height_source"].ne("default").mean()) if "_height_source" in b else 0.0
    if "_height_source" in b:
        known_geoms = list(b.loc[b["_height_source"].ne("default"), "geometry"])
        known_union_area = float(union_all(known_geoms, grid_size=0.01).area) if known_geoms else 0.0
        known_area_fraction = min(1.0, known_union_area / union_area) if union_area > 0 else 0.0
    else:
        known_area_fraction = 0.0

    ground = union_area
    thermal_roof_area = geometric_roof_area * float(roof_factor)
    envelope = thermal_roof_area + wall_area
    closed = geometric_roof_area + wall_area + ground
    gross_wall = float(np.nansum(perimeters * heights))
    return BuildingSurfaceSummary(
        n_buildings=int(len(b)),
        footprint_area_m2=float(union_area),
        footprint_area_raw_sum_m2=raw_area,
        footprint_overlap_fraction=float(overlap_fraction),
        footprint_perimeter_m=float(union_geom.length),
        footprint_perimeter_raw_sum_m=float(np.nansum(perimeters)),
        volume_m3=float(volume),
        roof_area_m2=float(thermal_roof_area),
        geometric_roof_area_m2=float(geometric_roof_area),
        thermal_roof_area_m2=float(thermal_roof_area),
        wall_area_m2=float(wall_area),
        wall_area_gross_m2=gross_wall,
        envelope_area_m2=float(envelope),
        closed_surface_area_m2=float(closed),
        ground_contact_area_m2=float(ground),
        mean_height_m=float(np.nanmean(heights)),
        median_height_m=float(np.nanmedian(heights)),
        height_source_known_fraction=known_feature_fraction,
        height_source_known_area_fraction=float(known_area_fraction),
        height_layer_count=int(n_layers),
    )


def total_bounds_polygon(gdf: gpd.GeoDataFrame, buffer_m: float = 0.0) -> Polygon:
    minx, miny, maxx, maxy = gdf.total_bounds
    geom = box(float(minx), float(miny), float(maxx), float(maxy))
    return geom.buffer(buffer_m) if buffer_m else geom


def union_boundary(gdf: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
    return unary_union(list(gdf.geometry))


def area_perimeter(geom) -> tuple[float, float]:
    return float(geom.area), float(geom.length)


def surface_amplification(envelope_area_m2: float, plan_area_m2: float) -> float:
    if plan_area_m2 <= 0:
        return float("nan")
    return float(envelope_area_m2 / plan_area_m2)


def infer_box_sizes_px(
    shape: tuple[int, int],
    *,
    min_px: int = 2,
    max_fraction: float = 0.25,
    min_points: int = 6,
) -> list[int]:
    side = int(min(shape))
    max_size = int(max(2, side * max_fraction))
    sizes: list[int] = []
    n = max(1, int(min_px))
    while n <= max_size:
        sizes.append(n)
        n *= 2
    while len(sizes) < min_points and n <= side:
        sizes.append(n)
        n *= 2
    return sizes
