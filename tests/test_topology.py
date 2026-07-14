import numpy as np

from urban_fractal.topology import betti_numbers_2d, minkowski_betti_profile_2d


def test_betti_numbers_one_disk_like_component_no_hole():
    mask = np.zeros((20, 20), dtype=bool)
    mask[5:15, 5:15] = True
    beta0, beta1, chi, largest = betti_numbers_2d(mask)
    assert beta0 == 1
    assert beta1 == 0
    assert chi == 1
    assert largest == 100


def test_betti_numbers_ring_has_one_hole():
    mask = np.zeros((30, 30), dtype=bool)
    mask[5:25, 5:25] = True
    mask[10:20, 10:20] = False
    beta0, beta1, chi, largest = betti_numbers_2d(mask)
    assert beta0 == 1
    assert beta1 == 1
    assert chi == 0
    assert largest == 300


def test_minkowski_profile_reduces_components_under_dilation():
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:14, 10:14] = True
    mask[10:14, 20:24] = True
    profile, summary = minkowski_betti_profile_2d(mask, [0, 1, 2, 4, 8], pixel_size_m=1.0)
    assert int(profile.iloc[0]["beta0"]) == 2
    assert profile["beta0"].iloc[-1] <= 1
    assert summary.beta0_at_zero == 2
    assert summary.rc_m is not None
