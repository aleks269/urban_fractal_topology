from __future__ import annotations

import math
from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from rasterio import features
from shapely.geometry import box


@dataclass
class RasterMask:
    mask: np.ndarray
    transform: object
    pixel_size_m: float
    bounds: tuple[float, float, float, float]


def rasterize_geometries(
    gdf: gpd.GeoDataFrame,
    *,
    pixel_size_m: float,
    bounds: tuple[float, float, float, float] | None = None,
    all_touched: bool = True,
    burn_value: int = 1,
) -> RasterMask:
    if pixel_size_m <= 0:
        raise ValueError("pixel_size_m must be positive")
    if gdf.empty:
        raise ValueError("Cannot rasterize empty GeoDataFrame")
    if bounds is None:
        minx, miny, maxx, maxy = gdf.total_bounds
    else:
        minx, miny, maxx, maxy = bounds
    width = int(math.ceil((maxx - minx) / pixel_size_m))
    height = int(math.ceil((maxy - miny) / pixel_size_m))
    if width <= 0 or height <= 0:
        raise ValueError("Invalid raster bounds")
    from rasterio.transform import from_origin

    transform = from_origin(minx, maxy, pixel_size_m, pixel_size_m)
    shapes = ((geom, burn_value) for geom in gdf.geometry if geom is not None and not geom.is_empty)
    arr = features.rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="uint8",
        all_touched=all_touched,
    )
    return RasterMask(arr.astype(bool), transform, pixel_size_m, (minx, miny, maxx, maxy))
