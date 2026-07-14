from pathlib import Path
import geopandas as gpd
import matplotlib.pyplot as plt

city = "zelenograd"
data_dir = Path("data") / city
out_dir = Path("results") / city / "_preview"
out_dir.mkdir(parents=True, exist_ok=True)

boundary = gpd.read_file(data_dir / "boundary.geojson").to_crs(3857)
buildings = gpd.read_file(data_dir / "buildings.geojson").to_crs(3857)

roads_path = data_dir / "roads.geojson"
roads = None
if roads_path.exists():
    roads = gpd.read_file(roads_path).to_crs(3857)

fig, ax = plt.subplots(figsize=(10, 10))

boundary.boundary.plot(ax=ax, linewidth=2)
buildings.plot(ax=ax, markersize=0.1, linewidth=0, alpha=0.8)

if roads is not None and len(roads) > 0:
    roads.plot(ax=ax, linewidth=0.3, alpha=0.6)

ax.set_title(f"{city}: downloaded OSM data")
ax.set_axis_off()
ax.set_aspect("equal")

png = out_dir / "downloaded_data_preview.png"
plt.savefig(png, dpi=250, bbox_inches="tight")
print("Saved:", png)