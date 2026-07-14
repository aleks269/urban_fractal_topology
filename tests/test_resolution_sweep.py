import geopandas as gpd
from shapely.geometry import box

from urban_fractal.pipeline import AnalysisConfig, analyze_resolution_sweep


def test_resolution_sweep_synthetic(tmp_path):
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

    outdir = tmp_path / "sweep"
    result = analyze_resolution_sweep(
        AnalysisConfig(
            buildings_path=str(bpath),
            boundary_path=str(gpath),
            output_dir=str(outdir),
            min_scaling_points=3,
        ),
        [2, 4],
    )

    assert result["mode"] == "resolution_sweep"
    assert (outdir / "resolution_sweep_summary.csv").exists()
    assert (outdir / "resolution_sweep_summary.json").exists()
    assert (outdir / "resolution_sweep_stability.png").exists()
    assert (outdir / "px_2m" / "summary.json").exists()
    assert (outdir / "px_4m" / "summary.json").exists()
    assert result["stability"]["n_runs_total"] == 2
