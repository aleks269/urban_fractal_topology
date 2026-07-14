from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import geopandas as gpd
import numpy as np
from rasterio import features


@dataclass
class RasterMask:
    mask: np.ndarray
    transform: object
    pixel_size_m: float
    bounds: tuple[float, float, float, float]

    @property
    def shape(self) -> tuple[int, int]:
        return self.mask.shape


def _valid_shapes(gdf: gpd.GeoDataFrame, burn_value: int = 1) -> Iterable[tuple[object, int]]:
    for geom in gdf.geometry:
        if geom is not None and not geom.is_empty:
            yield geom, burn_value


def rasterize_geometries(
    gdf: gpd.GeoDataFrame,
    *,
    pixel_size_m: float,
    bounds: tuple[float, float, float, float] | None = None,
    all_touched: bool = False,
    burn_value: int = 1,
) -> RasterMask:
    """Rasterize geometries on a metric, north-up square grid.

    By default a pixel is burned only when its centre lies inside a geometry.
    This avoids the severe occupied-area inflation caused by ``all_touched`` at
    coarse urban resolutions.
    """
    if pixel_size_m <= 0:
        raise ValueError("pixel_size_m must be positive")
    if gdf.empty:
        raise ValueError("Cannot rasterize empty GeoDataFrame")
    if bounds is None:
        minx, miny, maxx, maxy = map(float, gdf.total_bounds)
    else:
        minx, miny, maxx, maxy = map(float, bounds)
    width = int(math.ceil((maxx - minx) / pixel_size_m))
    height = int(math.ceil((maxy - miny) / pixel_size_m))
    if width <= 0 or height <= 0:
        raise ValueError("Invalid raster bounds")

    from rasterio.transform import from_origin

    transform = from_origin(minx, maxy, pixel_size_m, pixel_size_m)
    arr = features.rasterize(
        _valid_shapes(gdf, burn_value),
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=all_touched,
    )
    return RasterMask(arr.astype(bool), transform, float(pixel_size_m), (minx, miny, maxx, maxy))


def rasterize_like(
    gdf: gpd.GeoDataFrame,
    reference: RasterMask,
    *,
    all_touched: bool = False,
    burn_value: int = 1,
) -> np.ndarray:
    """Rasterize geometries exactly on an existing grid."""
    if gdf.empty:
        raise ValueError("Cannot rasterize empty GeoDataFrame")
    arr = features.rasterize(
        _valid_shapes(gdf, burn_value),
        out_shape=reference.shape,
        transform=reference.transform,
        fill=0,
        dtype="uint8",
        all_touched=all_touched,
    )
    return arr.astype(bool)


def rasterize_weighted(
    gdf: gpd.GeoDataFrame,
    reference: RasterMask,
    value_column: str,
    *,
    all_touched: bool = False,
    fill: float = 0.0,
    reduce: str = "max",
) -> np.ndarray:
    """Rasterize a numeric feature attribute on an existing grid.

    The returned array is a cell-centre sampled attribute field. For building
    heights, each occupied raster cell receives the height of the polygon that
    contains its centre. Since all cells have equal area, this field may be used
    as a *height-weighted built-form measure* after normalization. It is not an
    exact volume raster because fractional footprint coverage within a cell is
    not computed.

    Overlap handling:

    - ``reduce="max"``: retain the largest value in an overlap;
    - ``reduce="replace"``: retain the last burned value;
    - ``reduce="add"``: sum values (appropriate only when addition is intended).
    """
    if gdf.empty:
        raise ValueError("Cannot rasterize empty GeoDataFrame")
    if value_column not in gdf.columns:
        raise ValueError(f"value_column '{value_column}' not present in GeoDataFrame")
    if reduce not in {"max", "replace", "add"}:
        raise ValueError("reduce must be one of: 'max', 'replace', 'add'")

    from rasterio.enums import MergeAlg

    shapes: list[tuple[object, float]] = []
    for geom, value in zip(gdf.geometry, gdf[value_column]):
        if geom is None or geom.is_empty or value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(numeric):
            shapes.append((geom, numeric))
    if not shapes:
        raise ValueError("No valid (geometry, value) pairs to rasterize")

    if reduce == "add":
        merge_alg = MergeAlg.add
    else:
        merge_alg = MergeAlg.replace
        if reduce == "max":
            # Rasterio uses a painter's algorithm: later shapes overwrite earlier
            # ones under MergeAlg.replace. Sorting ascending therefore leaves the
            # largest value in every overlap.
            shapes.sort(key=lambda item: item[1])

    arr = features.rasterize(
        shapes,
        out_shape=reference.shape,
        transform=reference.transform,
        fill=float(fill),
        dtype="float32",
        all_touched=all_touched,
        merge_alg=merge_alg,
    )
    return arr.astype(np.float64)
