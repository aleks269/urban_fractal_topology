import inspect

from urban_fractal.pipeline import AnalysisConfig
from urban_fractal.raster import rasterize_geometries


def test_pixel_center_rasterization_is_default():
    assert AnalysisConfig().all_touched is False
    assert inspect.signature(rasterize_geometries).parameters["all_touched"].default is False
