from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .geometry import (
    add_building_heights,
    area_perimeter,
    clean_polygons,
    ensure_metric,
    infer_box_sizes_px,
    summarize_building_surfaces,
    surface_amplification,
    total_bounds_polygon,
    union_boundary,
)
from .io import fetch_osm_boundary, fetch_osm_buildings, read_vector, write_csv, write_json
from .metrics import box_count_dimension_2d, compactness_2d, compactness_3d, lacunarity_2d, multifractal_spectrum_2d
from .topology import default_radii_px, minkowski_betti_profile_2d
from .plots import (
    plot_betti_profile,
    plot_box_count,
    plot_lacunarity,
    plot_mask,
    plot_minkowski_profile,
    plot_percolation_profile,
    plot_resolution_sweep,
)
from .raster import rasterize_geometries


@dataclass
class AnalysisConfig:
    city_name: str | None = None
    buildings_path: str | None = None
    boundary_path: str | None = None
    output_dir: str = "results"
    pixel_size_m: float = 25.0
    floor_height_m: float = 3.0
    default_height_m: float = 12.0
    roof_factor: float = 1.0
    buffer_m: float = 0.0
    min_box_px: int = 2
    max_box_fraction: float = 0.25
    min_scaling_points: int = 4
    lacunarity_windows_px: tuple[int, ...] | None = None
    multifractal: bool = False
    topology: bool = False
    topology_radii_px: tuple[int, ...] | None = None
    topology_max_radius_fraction: float = 0.05
    topology_n_radii: int = 18
    topology_connectivity: int = 1
    giant_threshold: float = 0.5


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


def analyze_city(cfg: AnalysisConfig) -> dict[str, Any]:
    outdir = Path(cfg.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    raw_buildings, raw_boundary = load_inputs(cfg)
    buildings = clean_polygons(raw_buildings)
    buildings = ensure_metric(buildings)

    if raw_boundary is not None and not raw_boundary.empty:
        boundary = ensure_metric(clean_polygons(raw_boundary), buildings.crs)
    else:
        boundary = gpd.GeoDataFrame(geometry=[total_bounds_polygon(buildings, cfg.buffer_m)], crs=buildings.crs)

    # Clip buildings to boundary if possible.
    try:
        buildings = gpd.clip(buildings, boundary)
        buildings = clean_polygons(buildings)
    except Exception:
        pass

    if buildings.empty:
        raise ValueError("No building polygons after cleaning/clipping")

    buildings = add_building_heights(
        buildings,
        floor_height_m=cfg.floor_height_m,
        default_height_m=cfg.default_height_m,
    )
    surface_summary = summarize_building_surfaces(buildings, roof_factor=cfg.roof_factor)

    boundary_geom = union_boundary(boundary)
    plan_area_m2, plan_perimeter_m = area_perimeter(boundary_geom)
    if plan_area_m2 <= 0:
        # Fallback to bounding box if boundary is invalid or line-like.
        bounds_poly = total_bounds_polygon(buildings, cfg.buffer_m)
        plan_area_m2, plan_perimeter_m = area_perimeter(bounds_poly)
        boundary_geom = bounds_poly

    # Raster analysis of building footprints.
    bounds = boundary_geom.bounds
    rmask = rasterize_geometries(buildings, pixel_size_m=cfg.pixel_size_m, bounds=bounds, all_touched=True)
    mask = rmask.mask
    n_pixels_total = int(mask.size)
    n_pixels_buildings = int(np.count_nonzero(mask))
    building_area_raster_m2 = float(n_pixels_buildings * cfg.pixel_size_m * cfg.pixel_size_m)
    building_area_vector_m2 = float(surface_summary.footprint_area_m2)
    raster_area_error_rel = (
        abs(building_area_raster_m2 - building_area_vector_m2) / building_area_vector_m2
        if building_area_vector_m2 > 0 else float("nan")
    )
    plot_mask(mask, outdir / "building_mask.png")

    box_sizes = infer_box_sizes_px(mask.shape, min_px=cfg.min_box_px, max_fraction=cfg.max_box_fraction)
    fit, counts, candidates = box_count_dimension_2d(
        mask,
        cfg.pixel_size_m,
        box_sizes,
        min_points=cfg.min_scaling_points,
    )
    write_csv(counts, outdir / "box_counts_buildings.csv")
    write_csv(candidates.head(100), outdir / "scaling_window_candidates.csv")
    plot_box_count(counts, fit.to_dict(), outdir / "box_count_buildings.png")

    if cfg.lacunarity_windows_px is None:
        lac_windows = tuple(box_sizes)
    else:
        lac_windows = cfg.lacunarity_windows_px
    lac = lacunarity_2d(mask.astype(float), lac_windows)
    lac["window_size_m"] = lac["window_size_px"] * cfg.pixel_size_m
    write_csv(lac, outdir / "lacunarity_buildings.csv")
    plot_lacunarity(lac, cfg.pixel_size_m, outdir / "lacunarity_buildings.png")

    topology_summary = None
    if cfg.topology:
        if cfg.topology_radii_px is None:
            topo_radii = default_radii_px(
                mask.shape,
                max_radius_fraction=cfg.topology_max_radius_fraction,
                n_radii=cfg.topology_n_radii,
            )
        else:
            topo_radii = list(cfg.topology_radii_px)
        topo_profile, topo_summary_obj = minkowski_betti_profile_2d(
            mask,
            topo_radii,
            pixel_size_m=cfg.pixel_size_m,
            connectivity=cfg.topology_connectivity,
            giant_threshold=cfg.giant_threshold,
        )
        write_csv(topo_profile, outdir / "topology_minkowski_betti_profile.csv")
        plot_minkowski_profile(topo_profile, outdir / "minkowski_profile.png")
        plot_betti_profile(topo_profile, outdir / "betti_profile.png")
        plot_percolation_profile(topo_profile, outdir / "percolation_profile.png")
        topology_summary = topo_summary_obj.to_dict()

    mf_summary = None
    if cfg.multifractal:
        q_values = [-5, -2, -1, 0, 1, 2, 5]
        spectrum, raw_mf = multifractal_spectrum_2d(mask.astype(float), box_sizes, q_values, cfg.pixel_size_m)
        write_csv(spectrum, outdir / "multifractal_spectrum_buildings.csv")
        write_csv(raw_mf, outdir / "multifractal_raw_buildings.csv")
        mf_summary = spectrum.to_dict(orient="records")

    c2d = compactness_2d(plan_area_m2, plan_perimeter_m)
    k_env = surface_amplification(surface_summary.envelope_area_m2, plan_area_m2)
    c3d = compactness_3d(surface_summary.volume_m3, surface_summary.envelope_area_m2)

    result = {
        "city_name": cfg.city_name,
        "data_level": "2D+2.5D_extruded_buildings",
        "crs": str(buildings.crs),
        "input": {
            "buildings_path": cfg.buildings_path,
            "boundary_path": cfg.boundary_path,
            "pixel_size_m": cfg.pixel_size_m,
            "floor_height_m": cfg.floor_height_m,
            "default_height_m": cfg.default_height_m,
            "roof_factor": cfg.roof_factor,
            "topology": cfg.topology,
            "topology_connectivity": cfg.topology_connectivity,
            "giant_threshold": cfg.giant_threshold,
        },
        "planar_boundary": {
            "area_m2": plan_area_m2,
            "perimeter_m": plan_perimeter_m,
            "compactness_2d": c2d,
        },
        "building_surfaces": surface_summary.to_dict(),
        "raster_diagnostics": {
            "n_rows": int(mask.shape[0]),
            "n_cols": int(mask.shape[1]),
            "n_pixels_total": n_pixels_total,
            "n_pixels_buildings": n_pixels_buildings,
            "foreground_fraction": float(n_pixels_buildings / n_pixels_total) if n_pixels_total > 0 else float("nan"),
            "building_area_raster_m2": building_area_raster_m2,
            "building_area_vector_m2": building_area_vector_m2,
            "raster_area_error_rel": raster_area_error_rel,
            "all_touched": True,
        },
        "derived_2_5d": {
            "surface_amplification_envelope_over_plan": k_env,
            "compactness_3d": c3d,
            "surface_to_volume_1_per_m": surface_summary.envelope_area_m2 / surface_summary.volume_m3
            if surface_summary.volume_m3 > 0 else float("nan"),
        },
        "fractal_dimension_building_footprints": fit.to_dict(),
        "lacunarity_building_footprints": {
            "min": float(np.nanmin(lac["lacunarity"])),
            "max": float(np.nanmax(lac["lacunarity"])),
            "mean": float(np.nanmean(lac["lacunarity"])),
            "peak_window_m": float(lac.loc[lac["lacunarity"].idxmax(), "window_size_m"]),
        },
        "topological_morphology_building_footprints": topology_summary,
        "multifractal_spectrum_building_footprints": mf_summary,
        "outputs": {
            "box_counts": "box_counts_buildings.csv",
            "lacunarity": "lacunarity_buildings.csv",
            "mask": "building_mask.png",
            "box_count_plot": "box_count_buildings.png",
            "lacunarity_plot": "lacunarity_buildings.png",
            "topology_profile": "topology_minkowski_betti_profile.csv" if cfg.topology else None,
            "minkowski_plot": "minkowski_profile.png" if cfg.topology else None,
            "betti_plot": "betti_profile.png" if cfg.topology else None,
            "percolation_plot": "percolation_profile.png" if cfg.topology else None,
        },
        "method_notes": [
            "D_build is a 2D box-counting dimension of building footprints, not a full 3D envelope dimension.",
            "2.5D envelope area is estimated by extrusion: roof_area=A_footprint*roof_factor, wall_area=perimeter*height.",
            "If height is absent, default_height_m is used; height_source_known_fraction reports data completeness.",
            "All fractal dimensions are finite-scale estimates; scale_min and scale_max must be reported with D.",
            "If topology=True, Minkowski/Betti profiles are computed for disk dilations of the building mask: X_r = X ⊕ B_r.",
        ],
    }
    write_json(result, outdir / "summary.json")
    return result



def _pixel_label(pixel_size_m: float) -> str:
    """Return a filesystem-safe label for a pixel size in meters."""
    value = f"{float(pixel_size_m):g}".replace("-", "m").replace(".", "p")
    return f"px_{value}m"


def _finite_cv(values: pd.Series) -> float:
    arr = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return float("nan")
    mean = float(np.mean(arr))
    if abs(mean) < 1e-15:
        return float("nan")
    return float(np.std(arr, ddof=1) / abs(mean))


def _extract_sweep_row(pixel_size_m: float, outdir: Path, result: dict[str, Any]) -> dict[str, Any]:
    raster = result.get("raster_diagnostics", {}) or {}
    fractal = result.get("fractal_dimension_building_footprints", {}) or {}
    lac = result.get("lacunarity_building_footprints", {}) or {}
    topology = result.get("topological_morphology_building_footprints") or {}
    surfaces = result.get("building_surfaces", {}) or {}

    return {
        "pixel_size_m": float(pixel_size_m),
        "run_dir": str(outdir),
        "status": "ok",
        "n_rows": raster.get("n_rows"),
        "n_cols": raster.get("n_cols"),
        "n_pixels_total": raster.get("n_pixels_total"),
        "n_pixels_buildings": raster.get("n_pixels_buildings"),
        "foreground_fraction": raster.get("foreground_fraction"),
        "building_area_raster_m2": raster.get("building_area_raster_m2"),
        "building_area_vector_m2": raster.get("building_area_vector_m2"),
        "raster_area_error_rel": raster.get("raster_area_error_rel"),
        "n_buildings": surfaces.get("n_buildings"),
        "D_build": fractal.get("dimension"),
        "D_r2": fractal.get("r2"),
        "D_stderr": fractal.get("stderr"),
        "D_scale_min_m": fractal.get("scale_min"),
        "D_scale_max_m": fractal.get("scale_max"),
        "D_n_points": fractal.get("n_points"),
        "lacunarity_min": lac.get("min"),
        "lacunarity_max": lac.get("max"),
        "lacunarity_mean": lac.get("mean"),
        "lacunarity_peak_window_m": lac.get("peak_window_m"),
        "rc_m": topology.get("rc_m"),
        "beta0_at_zero": topology.get("beta0_at_zero"),
        "beta1_at_zero": topology.get("beta1_at_zero"),
        "beta0_min": topology.get("beta0_min"),
        "beta0_max": topology.get("beta0_max"),
        "beta1_min": topology.get("beta1_min"),
        "beta1_max": topology.get("beta1_max"),
        "beta1_peak_radius_m": topology.get("beta1_peak_radius_m"),
        "chi_min": topology.get("chi_min"),
        "chi_max": topology.get("chi_max"),
        "archipelago_index": topology.get("archipelago_index"),
        "void_index": topology.get("void_index"),
        "boundary_complexity_index": topology.get("boundary_complexity_index"),
    }


def _extract_error_sweep_row(pixel_size_m: float, outdir: Path, exc: Exception) -> dict[str, Any]:
    return {
        "pixel_size_m": float(pixel_size_m),
        "run_dir": str(outdir),
        "status": "error",
        "error_type": exc.__class__.__name__,
        "error_message": str(exc),
    }


def _longest_stable_window(
    df: pd.DataFrame,
    *,
    d_cv_threshold: float,
    rc_cv_threshold: float,
    require_rc: bool,
) -> pd.DataFrame:
    if df.empty:
        return df
    best = df.iloc[0:0]
    ordered = df.sort_values("pixel_size_m").reset_index(drop=True)
    n = len(ordered)
    for i in range(n):
        for j in range(i + 1, n + 1):
            sub = ordered.iloc[i:j]
            if len(sub) < 2:
                continue
            d_cv = _finite_cv(sub["D_build"])
            if not np.isfinite(d_cv) or d_cv > d_cv_threshold:
                continue
            if require_rc:
                rc_cv = _finite_cv(sub["rc_m"])
                if not np.isfinite(rc_cv) or rc_cv > rc_cv_threshold:
                    continue
            if len(sub) > len(best):
                best = sub.copy()
            elif len(sub) == len(best) and not best.empty:
                old_span = float(best["pixel_size_m"].max() - best["pixel_size_m"].min())
                new_span = float(sub["pixel_size_m"].max() - sub["pixel_size_m"].min())
                if new_span > old_span:
                    best = sub.copy()
    return best


def summarize_resolution_stability(
    summary_df: pd.DataFrame,
    *,
    max_area_error_rel: float = 0.05,
    min_r2: float = 0.98,
    min_fit_points: int = 4,
    d_cv_threshold: float = 0.05,
    rc_cv_threshold: float = 0.10,
) -> dict[str, Any]:
    """Summarize resolution dependence of one-city repeated raster analyses."""
    if summary_df.empty:
        return {
            "status": "no_runs",
            "method": "resolution_sweep_stability_check",
            "stable": False,
            "reason": "No sweep rows were produced.",
        }

    df = summary_df.copy()
    for col in ("pixel_size_m", "raster_area_error_rel", "D_r2", "D_n_points", "D_build", "rc_m"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    ok = df.get("status", pd.Series(["ok"] * len(df), index=df.index)).eq("ok")
    area_ok = df["raster_area_error_rel"].le(max_area_error_rel) if "raster_area_error_rel" in df else False
    fit_ok = df["D_r2"].ge(min_r2) if "D_r2" in df else False
    points_ok = df["D_n_points"].ge(min_fit_points) if "D_n_points" in df else False
    quality = df[ok & area_ok & fit_ok & points_ok].sort_values("pixel_size_m")

    require_rc = "rc_m" in quality and quality["rc_m"].notna().sum() >= 2
    stable_window = _longest_stable_window(
        quality,
        d_cv_threshold=d_cv_threshold,
        rc_cv_threshold=rc_cv_threshold,
        require_rc=require_rc,
    )

    d_cv_all_quality = _finite_cv(quality["D_build"]) if not quality.empty and "D_build" in quality else float("nan")
    rc_cv_all_quality = _finite_cv(quality["rc_m"]) if require_rc else float("nan")

    stable = len(stable_window) >= 2
    recommended_pixel_size_m = None
    if stable:
        recommended_pixel_size_m = float(stable_window["pixel_size_m"].median())

    excluded = df.loc[~df.index.isin(quality.index), "pixel_size_m"].dropna().astype(float).tolist()
    reason = None
    if not stable:
        if quality.empty:
            reason = "No resolution passed raster-area, box-fit R² and fit-point quality filters."
        else:
            reason = "Quality-filtered resolutions did not form a stable D_build/rc_m window."

    return {
        "status": "ok",
        "method": "resolution_sweep_stability_check",
        "stable": stable,
        "recommended_pixel_size_m": recommended_pixel_size_m,
        "stable_window_pixel_sizes_m": stable_window["pixel_size_m"].astype(float).tolist() if stable else [],
        "stable_window_min_pixel_size_m": float(stable_window["pixel_size_m"].min()) if stable else None,
        "stable_window_max_pixel_size_m": float(stable_window["pixel_size_m"].max()) if stable else None,
        "n_runs_total": int(len(df)),
        "n_runs_ok": int(ok.sum()),
        "n_quality_runs": int(len(quality)),
        "excluded_pixel_sizes_m": excluded,
        "d_cv_quality_runs": d_cv_all_quality,
        "rc_cv_quality_runs": rc_cv_all_quality,
        "thresholds": {
            "max_area_error_rel": float(max_area_error_rel),
            "min_r2": float(min_r2),
            "min_fit_points": int(min_fit_points),
            "d_cv_threshold": float(d_cv_threshold),
            "rc_cv_threshold": float(rc_cv_threshold),
        },
        "reason": reason,
        "notes": [
            "The stability check is a diagnostic heuristic, not a statistical proof of scale invariance.",
            "A stable window means that D_build and, when available, rc_m vary weakly over a contiguous set of pixel sizes after basic quality filtering.",
        ],
    }


def analyze_resolution_sweep(
    cfg: AnalysisConfig,
    pixel_sizes_m: list[float] | tuple[float, ...],
    *,
    continue_on_error: bool = True,
    max_area_error_rel: float = 0.05,
    min_r2: float = 0.98,
    min_fit_points: int | None = None,
    d_cv_threshold: float = 0.05,
    rc_cv_threshold: float = 0.10,
) -> dict[str, Any]:
    """Run the same city analysis at several raster resolutions and summarize stability."""
    pixels = [float(p) for p in pixel_sizes_m]
    if not pixels:
        raise ValueError("At least one pixel size must be supplied for a resolution sweep")
    if any((not np.isfinite(p)) or p <= 0 for p in pixels):
        raise ValueError("All pixel sizes must be positive finite numbers")

    # Keep order deterministic and avoid duplicate runs.
    pixels = sorted(set(pixels))
    outdir = Path(cfg.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    run_summaries: list[dict[str, Any]] = []
    for pixel in pixels:
        run_dir = outdir / _pixel_label(pixel)
        run_cfg = replace(cfg, pixel_size_m=pixel, output_dir=str(run_dir))
        try:
            result = analyze_city(run_cfg)
        except Exception as exc:
            if not continue_on_error:
                raise
            rows.append(_extract_error_sweep_row(pixel, run_dir, exc))
            continue
        rows.append(_extract_sweep_row(pixel, run_dir, result))
        run_summaries.append({
            "pixel_size_m": float(pixel),
            "summary_json": str(run_dir / "summary.json"),
        })

    summary_df = pd.DataFrame(rows).sort_values("pixel_size_m").reset_index(drop=True)
    write_csv(summary_df, outdir / "resolution_sweep_summary.csv")

    stability = summarize_resolution_stability(
        summary_df,
        max_area_error_rel=max_area_error_rel,
        min_r2=min_r2,
        min_fit_points=cfg.min_scaling_points if min_fit_points is None else min_fit_points,
        d_cv_threshold=d_cv_threshold,
        rc_cv_threshold=rc_cv_threshold,
    )
    plot_resolution_sweep(summary_df, outdir / "resolution_sweep_stability.png")

    result = {
        "city_name": cfg.city_name,
        "mode": "resolution_sweep",
        "pixel_sizes_m": pixels,
        "input": {
            "buildings_path": cfg.buildings_path,
            "boundary_path": cfg.boundary_path,
            "floor_height_m": cfg.floor_height_m,
            "default_height_m": cfg.default_height_m,
            "roof_factor": cfg.roof_factor,
            "topology": cfg.topology,
            "multifractal": cfg.multifractal,
        },
        "stability": stability,
        "runs": run_summaries,
        "outputs": {
            "summary_csv": "resolution_sweep_summary.csv",
            "summary_json": "resolution_sweep_summary.json",
            "stability_plot": "resolution_sweep_stability.png",
        },
        "method_notes": [
            "Each run uses the same vector inputs and analysis settings, changing only pixel_size_m and output_dir.",
            "The sweep is intended to detect raster-discretization sensitivity of finite-scale descriptors.",
            "Pixel sizes that fail area-error, fit-quality or stability diagnostics should not be used for final inter-city comparison.",
        ],
    }
    write_json(result, outdir / "resolution_sweep_summary.json")
    return result
