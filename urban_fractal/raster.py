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
