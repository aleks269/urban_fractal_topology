import numpy as np
import geopandas as gpd
from shapely.geometry import Polygon, box

from urban_fractal.geometry import add_building_heights, summarize_building_surfaces
from urban_fractal.metrics import multifractal_spectrum_2d
from urban_fractal.raster import rasterize_geometries, rasterize_like
from urban_fractal.topology import betti_numbers_2d, minkowski_betti_profile_2d, spanning_component_counts
from urban_fractal.transport import analyze_transport_phase, prepare_transport_grid


def test_boundary_mask_is_separate_from_bounding_box():
    boundary_geom = Polygon([(0, 0), (100, 0), (100, 40), (40, 40), (40, 100), (0, 100)])
    boundary = gpd.GeoDataFrame(geometry=[boundary_geom], crs="EPSG:3857")
    buildings = gpd.GeoDataFrame(geometry=[box(10, 10, 30, 30)], crs="EPSG:3857")
    domain_raster = rasterize_geometries(boundary, pixel_size_m=10, bounds=boundary_geom.bounds)
    domain = domain_raster.mask
    mask = rasterize_like(buildings, domain_raster) & domain
    assert domain.sum() == 64
    assert domain.size == 100
    assert mask.sum() == 4
    assert not domain[1, 8]


def test_dual_connectivity_for_diagonal_foreground():
    mask = np.zeros((5, 5), dtype=bool)
    mask[1, 1] = True
    mask[2, 2] = True
    beta0_4, beta1_4, _, _ = betti_numbers_2d(mask, connectivity=1)
    beta0_8, beta1_8, _, _ = betti_numbers_2d(mask, connectivity=2)
    assert beta0_4 == 2
    assert beta0_8 == 1
    assert beta1_4 == 0
    assert beta1_8 == 0


def test_interior_island_does_not_count_as_global_spanning():
    domain = np.ones((30, 30), dtype=bool)
    mask = np.zeros_like(domain)
    mask[10:20, 10:20] = True
    lr, tb = spanning_component_counts(mask, domain_mask=domain)
    assert lr == 0
    assert tb == 0
    mask[14:16, :] = True
    lr, tb = spanning_component_counts(mask, domain_mask=domain)
    assert lr == 1
    assert tb == 0


def test_true_spanning_radius_is_separate_from_giant_component_radius():
    domain = np.ones((50, 50), dtype=bool)
    mask = np.zeros_like(domain)
    mask[20:30, 5:15] = True
    mask[20:30, 18:28] = True
    profile, summary = minkowski_betti_profile_2d(
        mask, [0, 1, 2, 4, 8, 16, 24], pixel_size_m=1.0, domain_mask=domain, giant_threshold=0.5
    )
    assert summary.giant_component_radius_m is not None
    assert summary.spanning_radius_lr_m is not None
    assert summary.spanning_radius_lr_m >= summary.giant_component_radius_m
    assert "spans_lr" in profile.columns


def test_multifractal_padding_preserves_probability_normalization():
    mass = np.zeros((11, 13), dtype=float)
    mass[1:10, 2:12] = 1.0
    spectrum, raw = multifractal_spectrum_2d(mass, [2, 3, 5], [-2, 0, 1, 2], 1.0, min_points=3)
    assert np.allclose(raw["probability_sum"], 1.0, atol=1e-12)
    assert np.allclose(raw["mass_sum"], mass.sum(), atol=1e-12)
    assert not spectrum.empty


def test_layered_surface_union_removes_shared_wall_double_counting():
    buildings = gpd.GeoDataFrame(
        {"height": [10.0, 10.0]},
        geometry=[box(0, 0, 10, 10), box(10, 0, 20, 10)],
        crs="EPSG:3857",
    )
    buildings = add_building_heights(buildings, default_height_m=12)
    summary = summarize_building_surfaces(buildings)
    assert np.isclose(summary.footprint_area_m2, 200.0)
    assert np.isclose(summary.roof_area_m2, 200.0)
    assert np.isclose(summary.geometric_roof_area_m2, 200.0)
    assert np.isclose(summary.thermal_roof_area_m2, 200.0)
    assert np.isclose(summary.wall_area_m2, 600.0)
    assert np.isclose(summary.wall_area_gross_m2, 800.0)
    assert np.isclose(summary.closed_surface_area_m2, 1000.0)
    assert np.isclose(summary.volume_m3, 2000.0)


def test_closed_surface_is_independent_of_thermal_roof_factor():
    buildings = gpd.GeoDataFrame(
        {"height": [10.0]},
        geometry=[box(0, 0, 10, 10)],
        crs="EPSG:3857",
    )
    buildings = add_building_heights(buildings, default_height_m=12)
    base = summarize_building_surfaces(buildings, roof_factor=1.0)
    amplified = summarize_building_surfaces(buildings, roof_factor=1.5)
    assert np.isclose(base.closed_surface_area_m2, amplified.closed_surface_area_m2)
    assert amplified.envelope_area_m2 > base.envelope_area_m2


def test_transport_homogeneous_energy_identity_and_normalization():
    domain = np.ones((20, 20), dtype=bool)
    buildings = np.zeros_like(domain)
    fraction, domain2, pixel, factor = prepare_transport_grid(
        buildings, domain, pixel_size_m=1.0, max_active_cells=10000
    )
    cache = {}
    result, potential = analyze_transport_phase(
        fraction,
        domain2,
        phase="open_space",
        contrast=1000.0,
        pixel_size_m=pixel,
        original_pixel_size_m=1.0,
        coarsening_factor=factor,
        direction="lr",
        homogeneous_cache=cache,
    )
    assert result.converged
    assert result.energy_identity_relative_error < 1e-10
    assert np.isclose(result.relative_conductance, 1.0, atol=1e-10)
    assert np.isclose(result.effective_conductivity_bbox, 1.0, atol=1e-10)
    assert np.nanmin(potential) >= 0
    assert np.nanmax(potential) <= 1
