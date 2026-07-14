import geopandas as gpd
from shapely.geometry import box

from urban_fractal.pipeline import AnalysisConfig, analyze_city


def test_pipeline_synthetic(tmp_path):
    buildings = gpd.GeoDataFrame(
        {"height": [10, 12, 8]},
        geometry=[box(0, 0, 10, 10), box(20, 0, 35, 15), box(0, 25, 12, 37)],
        crs="EPSG:3857",
    )
    boundary = gpd.GeoDataFrame(geometry=[box(-10, -10, 50, 50)], crs="EPSG:3857")
    bpath = tmp_path / "buildings.geojson"
    gpath = tmp_path / "boundary.geojson"
    buildings.to_file(bpath, driver="GeoJSON")
    boundary.to_file(gpath, driver="GeoJSON")
    result = analyze_city(AnalysisConfig(
        buildings_path=str(bpath), boundary_path=str(gpath), output_dir=str(tmp_path / "out"), pixel_size_m=2, min_scaling_points=3
    ))
    assert result["building_surfaces"]["n_buildings"] == 3
    assert result["derived_2_5d"]["surface_amplification_envelope_over_plan"] > 0
