import numpy as np

from urban_fractal.metrics import box_count_dimension_2d, lacunarity_2d, compactness_2d, compactness_3d


def test_box_count_dimension_filled_square_close_to_2():
    mask = np.ones((256, 256), dtype=bool)
    fit, counts, candidates = box_count_dimension_2d(mask, 1.0, [2, 4, 8, 16, 32, 64], min_points=4)
    assert abs(fit.dimension - 2.0) < 0.05
    assert fit.r2 > 0.99


def test_lacunarity_uniform_low():
    mask = np.ones((64, 64), dtype=bool)
    lac = lacunarity_2d(mask, [4, 8, 16])
    assert np.allclose(lac["lacunarity"].to_numpy(), 1.0)


def test_compactness_values():
    assert 0 < compactness_2d(1.0, 4.0) < 1
    assert 0 < compactness_3d(1.0, 6.0) < 1
