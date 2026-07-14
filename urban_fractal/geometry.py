from __future__ import annotations

import math
import re
from dataclasses import dataclass, asdict
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import CRS
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.ops import unary_union


HEIGHT_RE = re.compile(r"([-+]?\d+(?:[\.,]\d+)?)")


@dataclass
class BuildingSurfaceSummary:
    n_buildings: int
    footprint_area_m2: float
    footprint_perimeter_m: float
    volume_m3: float
    roof_area_m2: float
    wall_area_m2: float
    envelope_area_m2: float
    mean_height_m: float
    median_height_m: float
    height_source_known_fraction: float

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_metric_crs(gdf: gpd.GeoDataFrame) -> CRS:
    """Estimate an appropriate metric CRS for a GeoDataFrame."""
    if gdf.crs is None:
        raise ValueError("Input GeoDataFrame has no CRS. Set CRS before analysis.")
    try:
        return gdf.estimate_utm_crs()
    except Exception:
        # Fallback: Web Mercator; not ideal for measurement but better than degrees.
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
    """Parse OSM-style height values such as '12', '12.5', '12 m'."""
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
    # If someone encoded feet, convert. OSM usually uses meters unless specified.
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
    heights = []
    sources = []
    for _, row in b.iterrows():
        h, src = height_from_attributes(row, floor_height_m=floor_height_m, default_height_m=default_height_m)
        heights.append(h)
        sources.append(src)
    b["_height_m"] = heights
    b["_height_source"] = sources
    return b


def summarize_building_surfaces(
    buildings: gpd.GeoDataFrame,
    *,
    roof_factor: float = 1.0,
) -> BuildingSurfaceSummary:
    if "_height_m" not in buildings.columns:
        raise ValueError("Call add_building_heights before summarize_building_surfaces")
    b = buildings.copy()
    areas = b.geometry.area.to_numpy(dtype=float)
    perimeters = b.geometry.length.to_numpy(dtype=float)
    heights = b["_height_m"].to_numpy(dtype=float)
    roof_area = areas * roof_factor
    wall_area = perimeters * heights
    volume = areas * heights
    known = b["_height_source"].ne("default").mean() if "_height_source" in b.columns else 0.0
    return BuildingSurfaceSummary(
        n_buildings=int(len(b)),
        footprint_area_m2=float(np.nansum(areas)),
        footprint_perimeter_m=float(np.nansum(perimeters)),
        volume_m3=float(np.nansum(volume)),
        roof_area_m2=float(np.nansum(roof_area)),
        wall_area_m2=float(np.nansum(wall_area)),
        envelope_area_m2=float(np.nansum(roof_area + wall_area)),
        mean_height_m=float(np.nanmean(heights)) if len(heights) else float("nan"),
        median_height_m=float(np.nanmedian(heights)) if len(heights) else float("nan"),
        height_source_known_fraction=float(known),
    )


def total_bounds_polygon(gdf: gpd.GeoDataFrame, buffer_m: float = 0.0) -> Polygon:
    minx, miny, maxx, maxy = gdf.total_bounds
    geom = box(float(minx), float(miny), float(maxx), float(maxy))
    if buffer_m:
        geom = geom.buffer(buffer_m)
    return geom


def union_boundary(gdf: gpd.GeoDataFrame) -> Polygon | MultiPolygon:
    return unary_union(list(gdf.geometry))


def area_perimeter(geom) -> tuple[float, float]:
    return float(geom.area), float(geom.length)


def surface_amplification(envelope_area_m2: float, plan_area_m2: float) -> float:
    if plan_area_m2 <= 0:
        return float("nan")
    return float(envelope_area_m2 / plan_area_m2)


def infer_box_sizes_px(shape: tuple[int, int], *, min_px: int = 2, max_fraction: float = 0.25) -> list[int]:
    """Power-of-two box sizes suitable for a raster shape.

    For very small rasters the function expands the upper limit to keep at
    least four candidate scales when possible.
    """
    side = int(min(shape))
    max_size = int(max(2, side * max_fraction))
    sizes = []
    n = min_px
    while n <= max_size:
        sizes.append(n)
        n *= 2
    while len(sizes) < 4 and n <= side:
        sizes.append(n)
        n *= 2
    return sizes
