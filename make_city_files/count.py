import geopandas as gpd

for name in ["boundary", "buildings", "roads"]:
    path = f"data/zelenograd/{name}.geojson"
    try:
        gdf = gpd.read_file(path)
        print(name)
        print("  objects:", len(gdf))
        print("  crs:", gdf.crs)
        print("  bounds:", gdf.total_bounds)
    except Exception as e:
        print(name, "FAILED:", e)