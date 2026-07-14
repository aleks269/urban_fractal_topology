import sys
from pathlib import Path

import geopandas as gpd
import osmnx as ox


def save_city(place: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Downloading boundary for: {place}")
    boundary = ox.geocoder.geocode_to_gdf(place)
    boundary = boundary[boundary.geometry.notna()].copy()
    boundary = boundary.to_crs(4326)
    boundary.to_file(out / "boundary.geojson", driver="GeoJSON")

    poly = boundary.geometry.iloc[0]

    print("Downloading buildings...")
    buildings = ox.features.features_from_polygon(poly, tags={"building": True})
    buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    buildings = buildings.to_crs(4326)

    keep_cols = [
        "geometry",
        "building",
        "height",
        "building:levels",
        "levels",
        "roof:shape",
        "roof:height",
        "addr:street",
        "name",
    ]
    keep_cols = [c for c in keep_cols if c in buildings.columns]
    buildings = buildings[keep_cols]

    buildings.to_file(out / "buildings.geojson", driver="GeoJSON")
    print(f"Saved {len(buildings)} buildings to {out / 'buildings.geojson'}")

    print("Downloading roads...")
    try:
        G = ox.graph.graph_from_polygon(poly, network_type="drive", simplify=True)
        _, edges = ox.convert.graph_to_gdfs(G)
        edges = edges.to_crs(4326)
        edges.to_file(out / "roads.geojson", driver="GeoJSON")
        print(f"Saved roads to {out / 'roads.geojson'}")
    except Exception as e:
        print(f"Road download failed: {e}")

    print("Done.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: python make_city_files.py "Zelenograd, Moscow, Russia" data/zelenograd')
        raise SystemExit(1)

    save_city(sys.argv[1], sys.argv[2])