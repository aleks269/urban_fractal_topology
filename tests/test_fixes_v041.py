"""Regression tests for the reviewed v0.4.1 changes."""

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from urban_fractal.metrics import multifractal_spectrum_2d
from urban_fractal.raster import rasterize_geometries, rasterize_weighted
from urban_fractal.topology import (
    domain_side_masks,
    minkowski_betti_profile_2d,
    spanning_component_counts,
)


def test_side_bands_offer_bbox_and_main_component_definitions():
    domain = np.zeros((15, 50), dtype=bool)
    domain[5:10, 2:41] = True
    domain[5:10, 45:48] = True

    bbox_sides = domain_side_masks(domain, reference="bbox")
    main_sides = domain_side_masks(domain, reference="largest_component")

    assert bbox_sides["right"][:, 45:].any()
    assert main_sides["right"][:, 40].any()
    assert not main_sides["right"][:, 45:].any()


def test_spanning_is_reported_both_for_full_bbox_and_main_component():
    domain = np.zeros((15, 50), dtype=bool)
    domain[5:10, 2:41] = True
    domain[5:10, 45:48] = True
    mask = np.zeros_like(domain)
    mask[5:10, 2:41] = True

    lr_bbox, _ = spanning_component_counts(mask, domain_mask=domain, reference="bbox")
    lr_main, _ = spanning_component_counts(mask, domain_mask=domain, reference="largest_component")
    assert lr_bbox == 0
    assert lr_main == 1

    _, summary = minkowski_betti_profile_2d(mask, [0, 1, 2], pixel_size_m=10.0, domain_mask=domain)
    d = summary.to_dict()
    assert d["domain_component_count"] == 2
    assert d["full_domain_spanning_interpretable"] is False
    assert d["spanning_reference_recommended"] == "largest_component"
    assert d["spanning_radius_lr_m"] is None
    assert d["spanning_radius_lr_main_component_m"] == 0.0
    assert d["spanning_radius_lr_recommended_m"] == 0.0


def test_topology_normalized_indices_are_present_and_dimensionless():
    domain = np.ones((60, 60), dtype=bool)
    rng = np.random.default_rng(0)
    mask = rng.random((60, 60)) < 0.2
    profile, summary = minkowski_betti_profile_2d(
        mask, [0, 1, 2, 4, 8, 12], pixel_size_m=10.0, domain_mask=domain
    )
    d = summary.to_dict()
    assert abs(d["characteristic_length_m"] - 600.0) < 1e-9
    assert abs(
        d["archipelago_index_per_component"]
        - d["archipelago_index_mean"] / d["n_components"]
    ) < 1e-12
    assert "beta0_per_initial_component" in profile.columns
    assert "perimeter_per_characteristic_length" in profile.columns
    assert d["normalized_indices_radius_interval_comparable"] is False


def _sierpinski_carpet(levels: int) -> np.ndarray:
    base = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=float)
    out = np.ones((1, 1), dtype=float)
    for _ in range(levels):
        out = np.kron(out, base)
    return out


def test_binary_occupancy_is_a_valid_uniform_area_measure():
    # Uniform mass on a Sierpinski carpet is monofractal: D_q = log(8)/log(3)
    # for all q. This directly verifies that a binary occupancy raster is not an
    # invalid multifractal input; it represents equal mass per occupied cell.
    field = _sierpinski_carpet(5)  # 243 x 243
    spectrum, _ = multifractal_spectrum_2d(
        field,
        [1, 3, 9, 27, 81],
        [-5, -2, -1, 0, 1, 2, 5],
        pixel_size_m=1.0,
        min_points=5,
    )
    expected = np.log(8.0) / np.log(3.0)
    assert np.allclose(spectrum["Dq"], expected, atol=1e-10)
    assert bool(spectrum["dq_monotonic_within_uncertainty"].iloc[0]) is True


def _pmodel_cascade(levels: int, weights: np.ndarray) -> np.ndarray:
    out = np.ones((1, 1), dtype=float)
    for _ in range(levels):
        out = np.kron(out, weights)
    return out


def test_multifractal_diagnostics_pass_true_cascade():
    weights = np.array([[0.40, 0.30], [0.20, 0.10]])
    field = _pmodel_cascade(8, weights)
    spectrum, _ = multifractal_spectrum_2d(
        field,
        [2, 4, 8, 16, 32, 64, 128],
        [-5, -2, -1, 0, 1, 2, 5],
        pixel_size_m=1.0,
        min_points=6,
    )
    assert bool(spectrum["dq_monotonic_within_uncertainty"].iloc[0]) is True
    assert int(spectrum["dq_valid_q_count"].iloc[0]) >= 2


def test_weighted_raster_max_overlap_and_definition():
    gdf = gpd.GeoDataFrame(
        {"height": [10.0, 20.0]},
        geometry=[box(0, 0, 2, 2), box(1, 0, 3, 2)],
        crs="EPSG:3857",
    )
    ref = rasterize_geometries(gdf, pixel_size_m=1.0, bounds=(0, 0, 3, 2))
    arr = rasterize_weighted(gdf, ref, "height", reduce="max")
    assert arr.shape == (2, 3)
    assert np.all(arr[:, 0] == 10.0)
    assert np.all(arr[:, 1:] == 20.0)


def test_multifractal_stderr_is_propagated_from_tau_to_dq():
    rng = np.random.default_rng(42)
    field = rng.lognormal(size=(128, 128))
    spectrum, _ = multifractal_spectrum_2d(
        field, [2, 4, 8, 16, 32, 64], [-2, 0, 1, 2], pixel_size_m=1.0, min_points=6
    )
    for row in spectrum.itertuples():
        if row.q == 1.0:
            assert np.isclose(row.stderr, row.slope_stderr)
        else:
            assert np.isclose(row.stderr, row.slope_stderr / abs(row.q - 1.0))


def test_negative_orders_are_diagnostic_not_atlas_features():
    rng = np.random.default_rng(7)
    field = rng.lognormal(size=(128, 128))
    spectrum, _ = multifractal_spectrum_2d(
        field, [2, 4, 8, 16, 32, 64], [-2, -1, 0, 1, 2], pixel_size_m=1.0, min_points=6
    )
    negative = spectrum[spectrum["q"] < 0]
    nonnegative = spectrum[spectrum["q"] >= 0]
    assert not negative["atlas_eligible"].any()
    assert (nonnegative["atlas_eligible"] == nonnegative["fit_pass"]).all()
    assert "dq_monotonic_all_fitted_within_uncertainty" in spectrum.columns
