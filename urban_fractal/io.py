from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd


def read_vector(path: str | Path, layer: str | None = None) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if layer:
        return gpd.read_file(path, layer=layer)
    return gpd.read_file(path)


def fetch_osm_buildings(place: str, *, tags: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    """Fetch building footprints from OpenStreetMap via osmnx.

    This requires the optional dependency: pip install 'urban-fractal[osm]'.
    """
    try:
        import osmnx as ox
    except ImportError as exc:
        raise ImportError("OSM download requires osmnx. Install with: pip install 'urban-fractal[osm]'") from exc
    tags = tags or {"building": True}
    gdf = ox.features_from_place(place, tags=tags)
    gdf = gdf.reset_index()
    return gdf


def fetch_osm_boundary(place: str) -> gpd.GeoDataFrame:
    try:
        import osmnx as ox
    except ImportError as exc:
        raise ImportError("OSM download requires osmnx. Install with: pip install 'urban-fractal[osm]'") from exc
    gdf = ox.geocode_to_gdf(place)
    return gdf


def write_json(data: dict, path: str | Path) -> None:
    import json

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
