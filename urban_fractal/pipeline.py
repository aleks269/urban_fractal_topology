from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from . import __version__
from .geometry import (
    add_building_heights,
    area_perimeter,
    clean_polygons,
    ensure_metric,
    infer_box_sizes_px,
    replace_default_heights,
    summarize_building_surfaces,
    surface_amplification,
    total_bounds_polygon,
    union_boundary,
)
from .io import fetch_osm_boundary, fetch_osm_buildings, read_vector, write_csv, write_json
from .metrics import (
    box_count_dimension_2d,
    compactness_2d,
    isoperimetric_compactness_3d,
    lacunarity_2d,
    multifractal_spectrum_2d,
)
from .plots import (
    plot_betti_profile,
    plot_box_count,
    plot_lacunarity,
    plot_mask,
    plot_minkowski_profile,
    plot_percolation_profile,
    plot_resolution_sweep,
    plot_transport_potential,
)
from .raster import rasterize_geometries, rasterize_like, rasterize_weighted
from .topology import default_radii_px, minkowski_betti_profile_2d
from .transport import analyze_transport_phase, prepare_transport_grid


@dataclass
class AnalysisConfig:
    city_name: str | None = None
    buildings_path: str | None = None
    boundary_path: str | None = None
    output_dir: str = "results"
    pixel_size_m: float = 25.0
    floor_height_m: float = 3.0
    default_height_m: float = 12.0
    height_scenarios_m: tuple[float, ...] = (9.0, 12.0, 15.0)
    roof_factor: float = 1.0
    buffer_m: float = 0.0
    min_box_px: int = 2
    max_box_fraction: float = 0.25
    min_scaling_points: int = 6
    scaling_scale_min_m: float = 50.0
    scaling_scale_max_m: float = 3200.0
    lacunarity_windows_px: tuple[int, ...] | None = None
    lacunarity_min_domain_fraction: float = 0.95
    multifractal: bool = False
    topology: bool = False
    topology_radii_px: tuple[int, ...] | None = None
    topology_max_radius_fraction: float = 0.25
    topology_n_radii: int = 18
    topology_connectivity: int = 1
    giant_threshold: float = 0.5
    all_touched: bool = False
    transport: bool = False
    transport_phases: tuple[str, ...] = ("open_space", "buildings")
    transport_contrasts: tuple[float, ...] = (1000.0,)
    transport_max_active_cells: int = 250_000


def load_inputs(cfg: AnalysisConfig) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame | None]:
    if cfg.buildings_path:
        buildings = read_vector(cfg.buildings_path)
    elif cfg.city_name:
        buildings = fetch_osm_buildings(cfg.city_name)
    else:
        raise ValueError("Either buildings_path or city_name must be provided")

    boundary = None
    if cfg.boundary_path:
        boundary = read_vector(cfg.boundary_path)
    elif cfg.city_name:
        try:
            boundary = fetch_osm_boundary(cfg.city_name)
        except Exception:
            boundary = None
    return buildings, boundary


def _prepare_geometry(cfg: AnalysisConfig):
    raw_buildings, raw_boundary = load_inputs(cfg)
    buildings = ensure_metric(clean_polygons(raw_buildings))
    boundary_fallback = raw_boundary is None or raw_boundary.empty
    if not boundary_fallback:
        boundary = ensure_metric(clean_polygons(raw_boundary), buildings.crs)
        boundary_geom = union_boundary(boundary)
    else:
        boundary_geom = total_bounds_polygon(buildings, cfg.buffer_m)
        boundary = gpd.GeoDataFrame(geometry=[boundary_geom], crs=buildings.crs)

    plan_area, _ = area_perimeter(boundary_geom)
    if plan_area <= 0:
        boundary_fallback = True
        boundary_geom = total_bounds_polygon(buildings, cfg.buffer_m)
        boundary = gpd.GeoDataFrame(geometry=[boundary_geom], crs=buildings.crs)

    # Avoid applying an expensive polygon intersection to thousands of features
    # already wholly inside the city. Only boundary-crossing objects are cut.
    inside = buildings.geometry.within(boundary_geom)
    intersects = buildings.geometry.intersects(boundary_geom)
    kept = buildings.loc[inside].copy()
    crossing = buildings.loc[~inside & intersects].copy()
    if not crossing.empty:
        crossing["geometry"] = crossing.geometry.intersection(boundary_geom)
        crossing = clean_polygons(crossing)
        buildings = gpd.GeoDataFrame(pd.concat([kept, crossing], ignore_index=True), crs=buildings.crs)
    else:
        buildings = kept
    if buildings.empty:
        raise ValueError("No building polygons after cleaning and strict boundary clipping")
    return buildings, boundary, boundary_geom, boundary_fallback


def _height_sensitivity(buildings: gpd.GeoDataFrame, cfg: AnalysisConfig) -> tuple[object, pd.DataFrame]:
    base = summarize_building_surfaces(buildings, roof_factor=cfg.roof_factor)
    scenarios = sorted(set(float(x) for x in (*cfg.height_scenarios_m, cfg.default_height_m) if float(x) > 0))
    rows = []
    for default_h in scenarios:
        scenario_buildings = replace_default_heights(buildings, default_h)
        summary = summarize_building_surfaces(scenario_buildings, roof_factor=cfg.roof_factor)
        row = {"default_height_m": default_h, **summary.to_dict()}
        row["is_primary"] = bool(np.isclose(default_h, cfg.default_height_m))
        rows.append(row)
    return base, pd.DataFrame(rows)


def _transport_summary(mask: np.ndarray, domain_mask: np.ndarray, cfg: AnalysisConfig, outdir: Path) -> dict[str, Any]:
    building_fraction, transport_domain, transport_pixel, factor = prepare_transport_grid(
        mask, domain_mask, pixel_size_m=cfg.pixel_size_m, max_active_cells=cfg.transport_max_active_cells
    )
    homogeneous_cache: dict[str, tuple[dict, np.ndarray]] = {}
    rows: list[dict[str, Any]] = []
    for contrast in cfg.transport_contrasts:
        for phase in cfg.transport_phases:
            for direction in ("lr", "tb"):
                result, potential = analyze_transport_phase(
                    building_fraction,
                    transport_domain,
                    phase=phase,  # type: ignore[arg-type]
                    contrast=float(contrast),
                    pixel_size_m=transport_pixel,
                    original_pixel_size_m=cfg.pixel_size_m,
                    coarsening_factor=factor,
                    direction=direction,  # type: ignore[arg-type]
                    homogeneous_cache=homogeneous_cache,
                )
                row = result.to_dict()
                rows.append(row)
                suffix = f"{phase}_{direction}_contrast_{float(contrast):g}".replace(".", "p")
                plot_transport_potential(
                    potential,
                    outdir / f"transport_potential_{suffix}.png",
                    f"{phase}, {direction.upper()}, contrast={float(contrast):g}",
                )
    table = pd.DataFrame(rows)
    write_csv(table, outdir / "transport_results.csv")

    aggregate: dict[str, Any] = {
        "status": "ok" if bool(table["converged"].all()) else "solver_warning",
        "analysis_pixel_size_m": float(transport_pixel),
        "original_pixel_size_m": float(cfg.pixel_size_m),
        "coarsening_factor": int(factor),
        "active_cells": int(transport_domain.sum()),
        "results": rows,
        "max_energy_identity_relative_error": float(table["energy_identity_relative_error"].max()),
    }
    for contrast in cfg.transport_contrasts:
        for phase in cfg.transport_phases:
            sub = table[(table["phase"] == phase) & np.isclose(table["contrast"], contrast)]
            values = {r["direction"]: r["relative_conductance"] for _, r in sub.iterrows()}
            lr, tb = values.get("lr"), values.get("tb")
            if lr is not None and tb is not None and np.isfinite(lr) and np.isfinite(tb) and tb != 0:
                aggregate[f"anisotropy_relative_conductance_{phase}_contrast_{float(contrast):g}"] = float(lr / tb)
    return aggregate


def analyze_city(cfg: AnalysisConfig) -> dict[str, Any]:
    outdir = Path(cfg.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    buildings, boundary, boundary_geom, boundary_fallback = _prepare_geometry(cfg)
    buildings = add_building_heights(
        buildings, floor_height_m=cfg.floor_height_m, default_height_m=cfg.default_height_m
    )
    surface_summary, height_sensitivity = _height_sensitivity(buildings, cfg)
    write_csv(height_sensitivity, outdir / "height_sensitivity_2_5d.csv")

    plan_area_m2, plan_perimeter_m = area_perimeter(boundary_geom)
    bounds = tuple(map(float, boundary_geom.bounds))
    # Boundary and buildings share one exact grid. The city domain is therefore
    # explicit and all later calculations are clipped to it.
    domain_raster = rasterize_geometries(
        boundary, pixel_size_m=cfg.pixel_size_m, bounds=bounds, all_touched=False
    )
    domain_mask = domain_raster.mask
    if not domain_mask.any():
        raise ValueError("City boundary has no raster cells at the requested resolution")
    building_mask = rasterize_like(
        buildings, domain_raster, all_touched=cfg.all_touched
    ) & domain_mask
    if not building_mask.any():
        raise ValueError("Building raster is empty inside the city boundary")

    n_pixels_bbox = int(building_mask.size)
    n_pixels_domain = int(domain_mask.sum())
    n_pixels_buildings = int(building_mask.sum())
    pixel_area = cfg.pixel_size_m**2
    building_area_raster_m2 = float(n_pixels_buildings * pixel_area)
    building_area_vector_m2 = float(surface_summary.footprint_area_m2)
    raster_area_error_rel = abs(building_area_raster_m2 - building_area_vector_m2) / building_area_vector_m2
    boundary_area_raster_m2 = float(n_pixels_domain * pixel_area)
    boundary_raster_area_error_rel = abs(boundary_area_raster_m2 - plan_area_m2) / plan_area_m2
    domain_fraction_bbox = float(n_pixels_domain / n_pixels_bbox)

    plot_mask(building_mask, outdir / "building_mask.png", domain_mask=domain_mask)
    plot_mask(domain_mask, outdir / "analysis_domain_mask.png")

    # Two distinct multifractal measures are retained. The binary raster is a
    # uniform footprint-area measure. The height field is an optional
    # height-weighted built-form measure and must not replace the footprint
    # measure silently because it changes the scientific interpretation.
    height_field = None
    if cfg.multifractal:
        height_field = rasterize_weighted(
            buildings, domain_raster, "_height_m", all_touched=cfg.all_touched, reduce="max"
        ) * domain_mask

    mask_payload = {
        "building_mask": building_mask.astype(np.uint8),
        "domain_mask": domain_mask.astype(np.uint8),
        "pixel_size_m": np.array([cfg.pixel_size_m]),
    }
    if height_field is not None:
        mask_payload["building_height_field_m"] = height_field.astype(np.float32)
    np.savez_compressed(outdir / "analysis_masks.npz", **mask_payload)

    box_sizes = infer_box_sizes_px(
        building_mask.shape,
        min_px=cfg.min_box_px,
        max_fraction=cfg.max_box_fraction,
        min_points=cfg.min_scaling_points,
    )
    # Extend powers of two up to the requested common physical upper scale,
    # provided the raster can support them. This keeps inter-city scale ranges
    # as comparable as the finite domain permits.
    max_physical_px = min(
        min(building_mask.shape),
        max(1, int(np.floor(cfg.scaling_scale_max_m / cfg.pixel_size_m))),
    )
    n = max(box_sizes) * 2 if box_sizes else max(1, cfg.min_box_px)
    while n <= max_physical_px:
        box_sizes.append(int(n))
        n *= 2
    box_sizes = sorted(set(box_sizes))
    fit, counts, candidates = box_count_dimension_2d(
        building_mask,
        cfg.pixel_size_m,
        box_sizes,
        min_points=cfg.min_scaling_points,
        scale_min_m=cfg.scaling_scale_min_m,
        scale_max_m=cfg.scaling_scale_max_m,
    )
    write_csv(counts, outdir / "box_counts_buildings.csv")
    write_csv(candidates.head(200), outdir / "scaling_window_candidates_diagnostic.csv")
    plot_box_count(counts, fit.to_dict(), outdir / "box_count_buildings.png")

    lac_windows = tuple(box_sizes) if cfg.lacunarity_windows_px is None else cfg.lacunarity_windows_px
    lac = lacunarity_2d(
        building_mask.astype(float),
        lac_windows,
        domain_mask=domain_mask,
        min_domain_fraction=cfg.lacunarity_min_domain_fraction,
    )
    lac["window_size_m"] = lac["window_size_px"] * cfg.pixel_size_m
    write_csv(lac, outdir / "lacunarity_buildings.csv")
    plot_lacunarity(lac, cfg.pixel_size_m, outdir / "lacunarity_buildings.png")

    topology_summary = None
    if cfg.topology:
        topo_radii = (
            default_radii_px(
                building_mask.shape,
                max_radius_fraction=cfg.topology_max_radius_fraction,
                n_radii=cfg.topology_n_radii,
            )
            if cfg.topology_radii_px is None
            else list(cfg.topology_radii_px)
        )
        topo_profile, topo_obj = minkowski_betti_profile_2d(
            building_mask,
            topo_radii,
            pixel_size_m=cfg.pixel_size_m,
            connectivity=cfg.topology_connectivity,
            giant_threshold=cfg.giant_threshold,
            domain_mask=domain_mask,
        )
        write_csv(topo_profile, outdir / "topology_minkowski_betti_profile.csv")
        plot_minkowski_profile(topo_profile, outdir / "minkowski_profile.png")
        plot_betti_profile(topo_profile, outdir / "betti_profile.png")
        plot_percolation_profile(topo_profile, outdir / "percolation_profile.png")
        topology_summary = topo_obj.to_dict()

    mf_summary = None
    mf_height_summary = None
    mf_footprint_pass = None
    mf_height_pass = None
    mf_footprint_all_q_pass = None
    mf_height_all_q_pass = None
    if cfg.multifractal:
        q_values = [-5, -2, -1, 0, 1, 2, 5]
        spectrum, raw_mf = multifractal_spectrum_2d(
            building_mask.astype(float),
            box_sizes,
            q_values,
            cfg.pixel_size_m,
            min_points=cfg.min_scaling_points,
        )
        write_csv(spectrum, outdir / "multifractal_spectrum_buildings.csv")
        write_csv(raw_mf, outdir / "multifractal_raw_buildings.csv")
        mf_summary = spectrum.to_dict(orient="records")
        if not spectrum.empty:
            mf_footprint_pass = bool(spectrum["dq_monotonic_within_uncertainty"].iloc[0])
            mf_footprint_all_q_pass = bool(spectrum["dq_monotonic_all_fitted_within_uncertainty"].iloc[0])

        if height_field is None:
            raise RuntimeError("height_field was not prepared for multifractal analysis")
        spectrum_h, raw_h = multifractal_spectrum_2d(
            height_field,
            box_sizes,
            q_values,
            cfg.pixel_size_m,
            min_points=cfg.min_scaling_points,
        )
        write_csv(spectrum_h, outdir / "multifractal_spectrum_height_weighted.csv")
        write_csv(raw_h, outdir / "multifractal_raw_height_weighted.csv")
        mf_height_summary = spectrum_h.to_dict(orient="records")
        if not spectrum_h.empty:
            mf_height_pass = bool(spectrum_h["dq_monotonic_within_uncertainty"].iloc[0])
            mf_height_all_q_pass = bool(spectrum_h["dq_monotonic_all_fitted_within_uncertainty"].iloc[0])

    transport_summary = _transport_summary(building_mask, domain_mask, cfg, outdir) if cfg.transport else None

    boundary_compactness = compactness_2d(plan_area_m2, plan_perimeter_m)
    thermal_amplification = surface_amplification(surface_summary.envelope_area_m2, plan_area_m2)
    closed_compactness = isoperimetric_compactness_3d(
        surface_summary.volume_m3, surface_summary.closed_surface_area_m2
    )

    quality = {
        "raster_building_area_pass": bool(raster_area_error_rel <= 0.05),
        "raster_boundary_area_pass": bool(boundary_raster_area_error_rel <= 0.03),
        "fractal_r2_pass": bool(fit.r2 >= 0.95),
        "fractal_min_points_pass": bool(fit.n_points >= cfg.min_scaling_points),
        "fractal_grid_origin_stability_pass": bool(fit.grid_offset_cv <= 0.05),
        "fractal_leave_one_scale_out_pass": bool(fit.leave_one_out_cv <= 0.05),
        "fractal_scale_span_pass": bool(fit.scale_span_decades >= 1.0),
        "height_completeness_for_intercity_2_5d": bool(surface_summary.height_source_known_area_fraction >= 0.5),
        "multifractal_footprint_monotonic_q_ge_0_within_uncertainty": mf_footprint_pass,
        "multifractal_height_weighted_monotonic_q_ge_0_within_uncertainty": mf_height_pass,
        "multifractal_footprint_monotonic_all_fitted_within_uncertainty": mf_footprint_all_q_pass,
        "multifractal_height_weighted_monotonic_all_fitted_within_uncertainty": mf_height_all_q_pass,
        # Compatibility aliases: these refer to the principal q >= 0 check.
        "multifractal_footprint_monotonic_within_uncertainty": mf_footprint_pass,
        "multifractal_height_weighted_monotonic_within_uncertainty": mf_height_pass,
        "multifractal_height_weighted_intercity_eligible": (
            None if not cfg.multifractal else bool(surface_summary.height_source_known_area_fraction >= 0.5)
        ),
        "transport_energy_identity_pass": (
            None if transport_summary is None else bool(transport_summary["max_energy_identity_relative_error"] <= 1e-5)
        ),
        "boundary_source": "fallback_building_bbox" if boundary_fallback else "provided_or_osm_boundary",
        "osm_building_completeness": "not_assessed_without_independent_reference",
        "water_green_fraction": "not_available_in_building_boundary_input",
    }
    critical = [
        quality["raster_building_area_pass"],
        quality["raster_boundary_area_pass"],
        quality["fractal_r2_pass"],
        quality["fractal_min_points_pass"],
        quality["fractal_grid_origin_stability_pass"],
        quality["fractal_leave_one_scale_out_pass"],
        quality["fractal_scale_span_pass"],
    ]
    if transport_summary is not None:
        critical.append(bool(quality["transport_energy_identity_pass"]))
    quality["core_2d_analysis_pass"] = bool(all(critical) and not boundary_fallback)

    result = {
        "software": {"name": "urban-fractal", "version": __version__, "methodology": "boundary-aware-v2"},
        "city_name": cfg.city_name,
        "data_level": "2D_boundary_aware+2.5D_layered_extrusion+optional_two_phase_transport",
        "crs": str(buildings.crs),
        "input": {
            **asdict(cfg),
            "output_dir": str(cfg.output_dir),
        },
        "planar_boundary": {
            "area_m2": plan_area_m2,
            "perimeter_m": plan_perimeter_m,
            "compactness_2d_analysis_boundary": boundary_compactness,
            "definition": "compactness of the supplied analysis boundary, not of building fabric",
            "fallback_used": bool(boundary_fallback),
            "bbox_area_m2": float((bounds[2] - bounds[0]) * (bounds[3] - bounds[1])),
            "domain_fraction_of_bbox": domain_fraction_bbox,
        },
        "building_surfaces": surface_summary.to_dict(),
        "raster_diagnostics": {
            "n_rows": int(building_mask.shape[0]),
            "n_cols": int(building_mask.shape[1]),
            "n_pixels_bbox": n_pixels_bbox,
            "n_pixels_domain": n_pixels_domain,
            "n_pixels_buildings": n_pixels_buildings,
            "foreground_fraction_within_domain": float(n_pixels_buildings / n_pixels_domain),
            "building_area_raster_m2": building_area_raster_m2,
            "building_area_vector_m2": building_area_vector_m2,
            "raster_area_error_rel": raster_area_error_rel,
            "boundary_area_raster_m2": boundary_area_raster_m2,
            "boundary_area_vector_m2": plan_area_m2,
            "boundary_raster_area_error_rel": boundary_raster_area_error_rel,
            "domain_fraction_of_bbox": domain_fraction_bbox,
            "all_touched": cfg.all_touched,
        },
        "derived_2_5d": {
            "thermal_envelope_area_m2": surface_summary.envelope_area_m2,
            "closed_geometric_surface_area_m2": surface_summary.closed_surface_area_m2,
            "surface_amplification_thermal_envelope_over_plan": thermal_amplification,
            "surface_amplification_envelope_over_plan": thermal_amplification,
            "isoperimetric_compactness_3d_closed_surface": closed_compactness,
            "thermal_surface_to_volume_1_per_m": (
                surface_summary.envelope_area_m2 / surface_summary.volume_m3
                if surface_summary.volume_m3 > 0 else float("nan")
            ),
            "intercity_comparison_eligible": bool(surface_summary.height_source_known_area_fraction >= 0.5),
            "sensitivity_file": "height_sensitivity_2_5d.csv",
        },
        "fractal_dimension_building_footprints": fit.to_dict(),
        "lacunarity_building_footprints": {
            "min": float(np.nanmin(lac["lacunarity"])),
            "max": float(np.nanmax(lac["lacunarity"])),
            "mean": float(np.nanmean(lac["lacunarity"])),
            "peak_window_m": float(lac.loc[lac["lacunarity"].idxmax(), "window_size_m"]),
            "domain_rule": f"windows with domain fraction >= {cfg.lacunarity_min_domain_fraction:g}",
        },
        "topological_morphology_building_footprints": topology_summary,
        "multifractal_spectrum_building_footprints": mf_summary,
        "multifractal_spectrum_height_weighted_buildings": mf_height_summary,
        "multifractal_measure_definitions": (
            None if not cfg.multifractal else {
                "footprint_area": "uniform mass per occupied raster cell; proportional to rasterized footprint area",
                "height_weighted": "cell-centre building height per occupied cell; equal cell area cancels after normalization; not exact volume",
                "height_known_area_fraction": surface_summary.height_source_known_area_fraction,
                "default_height_m": cfg.default_height_m,
            }
        ),
        "two_phase_transport": transport_summary,
        "quality_control": quality,
        "outputs": {
            "masks_npz": "analysis_masks.npz",
            "domain_mask": "analysis_domain_mask.png",
            "building_mask": "building_mask.png",
            "box_counts": "box_counts_buildings.csv",
            "lacunarity": "lacunarity_buildings.csv",
            "topology_profile": "topology_minkowski_betti_profile.csv" if cfg.topology else None,
            "multifractal_spectrum": "multifractal_spectrum_buildings.csv" if cfg.multifractal else None,
            "multifractal_spectrum_height_weighted": "multifractal_spectrum_height_weighted.csv" if cfg.multifractal else None,
            "transport_results": "transport_results.csv" if cfg.transport else None,
        },
        "method_notes": [
            "All raster metrics are restricted to the rasterized analysis boundary; bounding-box exterior pixels are never treated as urban voids.",
            "D_build is fitted on a fixed physical scale range and averaged over four grid origins; automatic windows are diagnostic only.",
            "Digital topology uses dual foreground/background connectivity and holes are defined relative to the irregular domain boundary.",
            "Giant-component radius and directional boundary-spanning radii are reported separately; full-domain and largest-domain-component spanning are both retained.",
            "Raw topology integrals are accompanied by normalized descriptors, but inter-city use requires a harmonized radius interval.",
            "Multifractal probabilities are normalized after zero padding at every scale; footprint-area and height-weighted measures are reported separately.",
            "Exact D_q is non-increasing in q; empirical monotonicity is checked against regression uncertainty rather than a machine-precision threshold.",
            "2.5D exterior walls are computed from unions of height layers, so shared walls and overlaps are not double-counted.",
            "Classical 3D compactness uses a closed surface; the thermal envelope remains a separate open-surface quantity.",
            "Transport reports both fixed-potential dissipation (equal to conductance for Δu=1) and fixed-unit-flux dissipation (equal to resistance).",
            "Transport may be explicitly coarsened when the full 25 m domain exceeds transport_max_active_cells; actual transport pixel size is recorded.",
        ],
    }
    write_json(result, outdir / "summary.json")
    return result


def _pixel_label(pixel_size_m: float) -> str:
    return f"px_{float(pixel_size_m):g}m".replace(".", "p")


def _finite_cv(values: pd.Series) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2 or abs(float(np.mean(arr))) < 1e-15:
        return float("nan")
    return float(np.std(arr, ddof=1) / abs(np.mean(arr)))


def analyze_resolution_sweep(
    cfg: AnalysisConfig,
    pixel_sizes_m: list[float] | tuple[float, ...],
    *,
    continue_on_error: bool = False,
    max_area_error_rel: float = 0.05,
    min_r2: float = 0.95,
    d_cv_threshold: float = 0.05,
    rc_cv_threshold: float = 0.10,
    **_: Any,
) -> dict[str, Any]:
    outdir = Path(cfg.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    rows, runs = [], []
    for pixel in sorted(set(float(x) for x in pixel_sizes_m if float(x) > 0)):
        run_dir = outdir / _pixel_label(pixel)
        run_cfg = replace(cfg, pixel_size_m=pixel, output_dir=str(run_dir), transport=False)
        try:
            result = analyze_city(run_cfg)
            fractal = result["fractal_dimension_building_footprints"]
            raster = result["raster_diagnostics"]
            topo = result.get("topological_morphology_building_footprints") or {}
            row = {
                "pixel_size_m": pixel,
                "status": "ok",
                "D_build": fractal.get("dimension"),
                "D_r2": fractal.get("r2"),
                "D_n_points": fractal.get("n_points"),
                "D_grid_offset_std": fractal.get("grid_offset_std"),
                "raster_area_error_rel": raster.get("raster_area_error_rel"),
                "boundary_raster_area_error_rel": raster.get("boundary_raster_area_error_rel"),
                "lacunarity_mean": result["lacunarity_building_footprints"].get("mean"),
                "spanning_radius_any_m": topo.get("spanning_radius_any_m"),
                "giant_component_radius_m": topo.get("giant_component_radius_m"),
                "summary_json": str(run_dir / "summary.json"),
            }
            rows.append(row)
            runs.append(result)
        except Exception as exc:
            rows.append({"pixel_size_m": pixel, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
            if not continue_on_error:
                raise
    df = pd.DataFrame(rows).sort_values("pixel_size_m")
    write_csv(df, outdir / "resolution_sweep_summary.csv")
    plot_resolution_sweep(df, outdir / "resolution_sweep_stability.png")

    ok = df[df["status"].eq("ok")].copy()
    quality = ok[
        (pd.to_numeric(ok["raster_area_error_rel"], errors="coerce") <= max_area_error_rel)
        & (pd.to_numeric(ok["D_r2"], errors="coerce") >= min_r2)
        & (pd.to_numeric(ok["D_n_points"], errors="coerce") >= cfg.min_scaling_points)
    ]
    d_cv = _finite_cv(quality["D_build"]) if not quality.empty else np.nan
    span_cv = _finite_cv(quality["spanning_radius_any_m"]) if "spanning_radius_any_m" in quality else np.nan
    stable = bool(len(quality) >= 2 and np.isfinite(d_cv) and d_cv <= d_cv_threshold)
    if np.isfinite(span_cv):
        stable = stable and span_cv <= rc_cv_threshold
    result = {
        "software": {"name": "urban-fractal", "version": __version__},
        "city_name": cfg.city_name,
        "mode": "resolution_sweep",
        "pixel_sizes_m": df["pixel_size_m"].tolist(),
        "stability": {
            "n_runs_total": int(len(df)),
            "n_runs_ok": int(len(ok)),
            "n_runs_quality": int(len(quality)),
            "stable": stable,
            "D_build_cv": d_cv,
            "spanning_radius_cv": span_cv,
            "quality_resolutions_m": quality["pixel_size_m"].tolist(),
            "recommended_pixel_size_m": float(quality["pixel_size_m"].median()) if stable else None,
        },
        "runs": runs,
        "outputs": {
            "summary_csv": "resolution_sweep_summary.csv",
            "stability_plot": "resolution_sweep_stability.png",
        },
    }
    write_json(result, outdir / "resolution_sweep_summary.json")
    return result
