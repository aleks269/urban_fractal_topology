from __future__ import annotations

import argparse
import html
import json
import math
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import pdist, squareform
from scipy.stats import mannwhitneyu, spearmanr

from urban_fractal import __version__


MORPHOLOGY_CANDIDATES = [
    "D_build",
    "lacunarity_mean",
    "compactness_boundary",
    "foreground_fraction",
    "spanning_radius_lr_norm",
    "spanning_radius_tb_norm",
    "giant_component_radius_norm",
    "beta0_density_km2",
    "beta1_density_km2",
    "archipelago_index_harmonized",
    "void_index_harmonized",
    "boundary_complexity_harmonized",
    "Dq_1",
    "multifractal_width",
]

TRANSPORT_FEATURES = [
    "open_space_relative_conductance_lr",
    "open_space_relative_conductance_tb",
    "open_space_transport_anisotropy",
    "buildings_relative_conductance_lr",
    "buildings_relative_conductance_tb",
    "buildings_transport_anisotropy",
]

DESCRIPTIVE_FEATURES = [
    "plan_area_km2",
    "building_count",
    "footprint_area_km2",
    "known_height_area_fraction",
    "thermal_surface_amplification",
    "closed_3d_compactness",
    "thermal_surface_to_volume_1_per_m",
    "transport_pixel_size_m",
    "transport_coarsening_factor",
]


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def finite_float(value: Any) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def q_key(q: float) -> str:
    return f"Dq_{int(q)}" if float(q).is_integer() else "Dq_" + str(q).replace("-", "m").replace(".", "p")


def extract_transport(row: dict[str, Any], transport: dict[str, Any]) -> None:
    row["transport_status"] = transport.get("status")
    row["transport_pixel_size_m"] = finite_float(transport.get("analysis_pixel_size_m"))
    row["transport_coarsening_factor"] = finite_float(transport.get("coarsening_factor"))
    row["transport_energy_error"] = finite_float(transport.get("max_energy_identity_relative_error"))
    results = transport.get("results")
    if not isinstance(results, list):
        return
    # Use the highest requested contrast as the principal high-contrast result.
    contrasts = [finite_float(x.get("contrast")) for x in results if isinstance(x, dict)]
    contrasts = [x for x in contrasts if np.isfinite(x)]
    if not contrasts:
        return
    contrast = max(contrasts)
    row["transport_principal_contrast"] = contrast
    values: dict[tuple[str, str], float] = {}
    for item in results:
        if not isinstance(item, dict) or not np.isclose(finite_float(item.get("contrast")), contrast):
            continue
        phase, direction = str(item.get("phase")), str(item.get("direction"))
        rel = finite_float(item.get("relative_conductance"))
        values[(phase, direction)] = rel
        row[f"{phase}_relative_conductance_{direction}"] = rel
        row[f"{phase}_conductance_{direction}"] = finite_float(item.get("conductance"))
        row[f"{phase}_resistance_{direction}"] = finite_float(item.get("resistance"))
    for phase in ("open_space", "buildings"):
        lr, tb = values.get((phase, "lr"), np.nan), values.get((phase, "tb"), np.nan)
        row[f"{phase}_transport_anisotropy"] = lr / tb if np.isfinite(lr) and np.isfinite(tb) and tb != 0 else np.nan


def extract_row(summary_path: Path, results_root: Path) -> dict[str, Any]:
    data = read_json(summary_path)
    rel = summary_path.parent.relative_to(results_root)
    parts = rel.parts
    row: dict[str, Any] = {
        "mode": parts[0] if parts else "",
        "subset": parts[-2] if len(parts) >= 2 else "",
        "slug": parts[-1] if parts else summary_path.parent.name,
        "summary_path": str(summary_path),
        "result_dir": str(summary_path.parent),
        "software_version": (data.get("software") or {}).get("version"),
    }
    inp = data.get("input") or {}
    planar = data.get("planar_boundary") or {}
    surfaces = data.get("building_surfaces") or {}
    raster = data.get("raster_diagnostics") or {}
    derived = data.get("derived_2_5d") or {}
    fractal = data.get("fractal_dimension_building_footprints") or {}
    lac = data.get("lacunarity_building_footprints") or {}
    topo = data.get("topological_morphology_building_footprints") or {}
    qc = data.get("quality_control") or {}

    row.update({
        "pixel_size_m": finite_float(inp.get("pixel_size_m")),
        "all_touched": inp.get("all_touched"),
        "plan_area_m2": finite_float(planar.get("area_m2")),
        "plan_perimeter_m": finite_float(planar.get("perimeter_m")),
        "compactness_boundary": finite_float(planar.get("compactness_2d_analysis_boundary")),
        "boundary_fallback": planar.get("fallback_used"),
        "domain_fraction_of_bbox": finite_float(raster.get("domain_fraction_of_bbox")),
        "building_count": finite_float(surfaces.get("n_buildings")),
        "footprint_area_m2": finite_float(surfaces.get("footprint_area_m2")),
        "footprint_overlap_fraction": finite_float(surfaces.get("footprint_overlap_fraction")),
        "known_height_fraction": finite_float(surfaces.get("height_source_known_fraction")),
        "known_height_area_fraction": finite_float(surfaces.get("height_source_known_area_fraction")),
        "foreground_fraction": finite_float(raster.get("foreground_fraction_within_domain")),
        "raster_area_error_rel": finite_float(raster.get("raster_area_error_rel")),
        "boundary_raster_area_error_rel": finite_float(raster.get("boundary_raster_area_error_rel")),
        "thermal_surface_amplification": finite_float(derived.get("surface_amplification_thermal_envelope_over_plan")),
        "closed_3d_compactness": finite_float(derived.get("isoperimetric_compactness_3d_closed_surface")),
        "thermal_surface_to_volume_1_per_m": finite_float(derived.get("thermal_surface_to_volume_1_per_m")),
        "2_5d_intercity_eligible": derived.get("intercity_comparison_eligible"),
        "D_build": finite_float(fractal.get("dimension")),
        "D_r2": finite_float(fractal.get("r2")),
        "D_stderr": finite_float(fractal.get("stderr")),
        "D_scale_min_m": finite_float(fractal.get("scale_min")),
        "D_scale_max_m": finite_float(fractal.get("scale_max")),
        "D_n_points": finite_float(fractal.get("n_points")),
        "D_grid_offset_std": finite_float(fractal.get("grid_offset_std")),
        "D_grid_offset_cv": finite_float(fractal.get("grid_offset_cv")),
        "D_leave_one_out_std": finite_float(fractal.get("leave_one_out_std")),
        "D_leave_one_out_cv": finite_float(fractal.get("leave_one_out_cv")),
        "D_scale_span_decades": finite_float(fractal.get("scale_span_decades")),
        "lacunarity_min": finite_float(lac.get("min")),
        "lacunarity_max": finite_float(lac.get("max")),
        "lacunarity_mean": finite_float(lac.get("mean")),
        "giant_component_radius_m": finite_float(topo.get("giant_component_radius_m")),
        "spanning_radius_lr_m": finite_float(
            topo.get("spanning_radius_lr_recommended_m", topo.get("spanning_radius_lr_m"))
        ),
        "spanning_radius_tb_m": finite_float(
            topo.get("spanning_radius_tb_recommended_m", topo.get("spanning_radius_tb_m"))
        ),
        "spanning_reference_recommended": topo.get("spanning_reference_recommended", "bbox"),
        "domain_component_count": finite_float(topo.get("domain_component_count", 1)),
        "largest_domain_component_fraction": finite_float(topo.get("largest_domain_component_fraction", 1.0)),
        "beta0_at_zero": finite_float(topo.get("beta0_at_zero")),
        "beta1_at_zero": finite_float(topo.get("beta1_at_zero")),
        "beta0_lr_at_zero": finite_float(topo.get("beta0_lr_at_zero")),
        "beta0_tb_at_zero": finite_float(topo.get("beta0_tb_at_zero")),
        "beta1_peak_radius_m": finite_float(topo.get("beta1_peak_radius_m")),
        "archipelago_index": finite_float(topo.get("archipelago_index")),
        "void_index": finite_float(topo.get("void_index")),
        "boundary_complexity_index": finite_float(topo.get("boundary_complexity_index")),
        "archipelago_index_norm": finite_float(topo.get("archipelago_index_per_component")),
        "void_index_norm": finite_float(topo.get("void_index_per_component")),
        "boundary_complexity_norm": finite_float(topo.get("boundary_index_per_characteristic_length")),
        "topology_radius_min_m": finite_float(topo.get("topology_radius_min_positive_m")),
        "topology_radius_max_m": finite_float(topo.get("topology_radius_max_m")),
        "core_2d_analysis_pass": qc.get("core_2d_analysis_pass"),
    })

    spectrum = data.get("multifractal_spectrum_building_footprints")
    q_pairs: list[tuple[float, float]] = []
    if isinstance(spectrum, list):
        for item in spectrum:
            if not isinstance(item, dict):
                continue
            q, dq = finite_float(item.get("q")), finite_float(item.get("Dq"))
            atlas_eligible = item.get("atlas_eligible")
            fit_pass = item.get("fit_pass")
            eligible = (atlas_eligible is True) if atlas_eligible is not None else (fit_pass is not False and q >= 0)
            if np.isfinite(q) and np.isfinite(dq) and eligible:
                row[q_key(q)] = dq
                q_pairs.append((q, dq))
    if q_pairs:
        q_pairs.sort()
        row["multifractal_width"] = q_pairs[0][1] - q_pairs[-1][1]
        row["multifractal_range"] = max(v for _, v in q_pairs) - min(v for _, v in q_pairs)
    else:
        row["multifractal_width"] = np.nan
        row["multifractal_range"] = np.nan


    height_spectrum = data.get("multifractal_spectrum_height_weighted_buildings")
    h_pairs: list[tuple[float, float]] = []
    if isinstance(height_spectrum, list):
        for item in height_spectrum:
            if not isinstance(item, dict):
                continue
            q, dq = finite_float(item.get("q")), finite_float(item.get("Dq"))
            atlas_eligible = item.get("atlas_eligible")
            fit_pass = item.get("fit_pass")
            eligible = (atlas_eligible is True) if atlas_eligible is not None else (fit_pass is not False and q >= 0)
            if np.isfinite(q) and np.isfinite(dq) and eligible:
                row["height_" + q_key(q)] = dq
                h_pairs.append((q, dq))
    if h_pairs:
        h_pairs.sort()
        row["height_multifractal_width"] = h_pairs[0][1] - h_pairs[-1][1]
        row["height_multifractal_range"] = max(v for _, v in h_pairs) - min(v for _, v in h_pairs)
    else:
        row["height_multifractal_width"] = np.nan
        row["height_multifractal_range"] = np.nan

    area = row["plan_area_m2"]
    if np.isfinite(area) and area > 0:
        area_km2, sqrt_area = area / 1e6, math.sqrt(area)
        row.update({
            "plan_area_km2": area_km2,
            "footprint_area_km2": row["footprint_area_m2"] / 1e6,
            "spanning_radius_lr_norm": row["spanning_radius_lr_m"] / sqrt_area,
            "spanning_radius_tb_norm": row["spanning_radius_tb_m"] / sqrt_area,
            "giant_component_radius_norm": row["giant_component_radius_m"] / sqrt_area,
            "beta0_density_km2": row["beta0_at_zero"] / area_km2,
            "beta1_density_km2": row["beta1_at_zero"] / area_km2,
            "archipelago_density_km2": row["archipelago_index"] / area_km2,
            "void_density_km2": row["void_index"] / area_km2,
        })
    extract_transport(row, data.get("two_phase_transport") or {})
    return row



def _mean_integral_on_log_interval(x: np.ndarray, y: np.ndarray, x_lo: float, x_hi: float) -> float:
    """Mean of y over a shared log-scale interval using linear interpolation."""
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = np.asarray(x[valid], dtype=float), np.asarray(y[valid], dtype=float)
    if x.size < 2:
        return float("nan")
    order = np.argsort(x)
    x, y = x[order], y[order]
    unique_x, unique_idx = np.unique(x, return_index=True)
    x, y = unique_x, y[unique_idx]
    if x_lo < x[0] - 1e-12 or x_hi > x[-1] + 1e-12 or x_hi <= x_lo:
        return float("nan")
    inside = x[(x > x_lo) & (x < x_hi)]
    grid = np.concatenate(([x_lo], inside, [x_hi]))
    values = np.interp(grid, x, y)
    try:
        trapezoid = np.trapezoid
    except AttributeError:
        trapezoid = np.trapz
    return float(trapezoid(values, grid) / (x_hi - x_lo))


def harmonize_topology_profiles(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]:
    """Recompute topology descriptors on one common relative-radius interval.

    Radius is normalized as rho = r / sqrt(A_domain). For every city, beta0 and
    beta1 are divided by beta0 at the smallest sampled radius, while perimeter
    is divided by sqrt(A_domain). The common interval is the intersection of
    positive-rho coverage across the supplied cities. This avoids comparing
    integrals evaluated over city-specific radius ranges.
    """
    profiles: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    coverage = []
    for idx, row in df.iterrows():
        area = finite_float(row.get("plan_area_m2"))
        path = Path(str(row.get("result_dir", ""))) / "topology_minkowski_betti_profile.csv"
        if not np.isfinite(area) or area <= 0 or not path.exists():
            continue
        try:
            prof = pd.read_csv(path)
            r = pd.to_numeric(prof["radius_m"], errors="coerce").to_numpy(dtype=float)
            b0 = pd.to_numeric(prof["beta0"], errors="coerce").to_numpy(dtype=float)
            b1 = pd.to_numeric(prof["beta1"], errors="coerce").to_numpy(dtype=float)
            perimeter = pd.to_numeric(prof["perimeter_m"], errors="coerce").to_numpy(dtype=float)
        except (KeyError, OSError, ValueError):
            continue
        lc = float(np.sqrt(area))
        positive = np.isfinite(r) & (r > 0)
        if np.count_nonzero(positive) < 2:
            continue
        n0_candidates = b0[np.isfinite(b0)]
        if n0_candidates.size == 0 or n0_candidates[0] <= 0:
            continue
        n0 = float(n0_candidates[0])
        rho = r[positive] / lc
        log_rho = np.log(rho)
        profiles[idx] = (log_rho, b0[positive] / n0, b1[positive] / n0, perimeter[positive] / lc)
        coverage.append((float(np.min(log_rho)), float(np.max(log_rho))))

    columns = [
        "archipelago_index_harmonized",
        "void_index_harmonized",
        "boundary_complexity_harmonized",
        "topology_harmonized_rho_min",
        "topology_harmonized_rho_max",
        "topology_harmonized_log_span",
    ]
    out = pd.DataFrame(np.nan, index=df.index, columns=columns)
    if not coverage:
        return out, {}
    x_lo = max(x[0] for x in coverage)
    x_hi = min(x[1] for x in coverage)
    if not np.isfinite(x_lo) or not np.isfinite(x_hi) or x_hi <= x_lo:
        return out, {"status": "no_common_interval"}

    for idx, (x, b0n, b1n, pn) in profiles.items():
        out.loc[idx, "archipelago_index_harmonized"] = _mean_integral_on_log_interval(x, b0n, x_lo, x_hi)
        out.loc[idx, "void_index_harmonized"] = _mean_integral_on_log_interval(x, b1n, x_lo, x_hi)
        out.loc[idx, "boundary_complexity_harmonized"] = _mean_integral_on_log_interval(x, pn, x_lo, x_hi)
        out.loc[idx, "topology_harmonized_rho_min"] = float(np.exp(x_lo))
        out.loc[idx, "topology_harmonized_rho_max"] = float(np.exp(x_hi))
        out.loc[idx, "topology_harmonized_log_span"] = float(x_hi - x_lo)
    metadata = {
        "status": "ok",
        "cities_with_profiles": int(len(profiles)),
        "rho_min": float(np.exp(x_lo)),
        "rho_max": float(np.exp(x_hi)),
        "log_span": float(x_hi - x_lo),
    }
    return out, metadata

def benjamini_hochberg(pvals: pd.Series) -> pd.Series:
    p = pd.to_numeric(pvals, errors="coerce")
    out = pd.Series(np.nan, index=p.index, dtype=float)
    valid = p.dropna().sort_values()
    m = len(valid)
    if m == 0:
        return out
    adjusted = np.minimum.accumulate((valid.to_numpy() * m / np.arange(1, m + 1))[::-1])[::-1]
    out.loc[valid.index] = np.clip(adjusted, 0, 1)
    return out


def robust_z(series: pd.Series) -> pd.Series:
    x = pd.to_numeric(series, errors="coerce")
    med = x.median()
    mad = (x - med).abs().median()
    if not np.isfinite(mad) or mad == 0:
        sd = x.std(ddof=0)
        return (x - x.mean()) / sd if np.isfinite(sd) and sd > 0 else pd.Series(0.0, index=x.index)
    return 0.67448975 * (x - med) / mad


def prepare_features(df: pd.DataFrame, candidates: list[str], max_missing: float = 0.30) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, kept = [], []
    for col in candidates:
        s = pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(np.nan, index=df.index)
        missing = float(s.isna().mean())
        variance = float(s.var(ddof=0)) if s.notna().sum() > 1 else 0.0
        status = "keep"
        if missing > max_missing:
            status = "drop_missing"
        elif not np.isfinite(variance) or variance <= 0:
            status = "drop_zero_variance"
        else:
            kept.append(col)
        rows.append({"feature": col, "missing_fraction": missing, "variance": variance, "status": status})
    x = df[kept].apply(pd.to_numeric, errors="coerce").copy()
    for col in kept:
        x[col] = x[col].fillna(x[col].median())
    return x, pd.DataFrame(rows)


def remove_redundant_features(x: pd.DataFrame, threshold: float = 0.90) -> tuple[pd.DataFrame, pd.DataFrame]:
    corr = x.corr(method="spearman")
    kept: list[str] = []
    rows = []
    for feature in x.columns:
        conflict = None
        rho = np.nan
        for prior in kept:
            value = corr.loc[feature, prior]
            if np.isfinite(value) and abs(value) >= threshold:
                conflict, rho = prior, float(value)
                break
        if conflict is None:
            kept.append(feature)
            rows.append({"feature": feature, "status": "keep", "redundant_with": "", "spearman_rho": np.nan})
        else:
            rows.append({"feature": feature, "status": "drop_redundant", "redundant_with": conflict, "spearman_rho": rho})
    return x[kept].copy(), pd.DataFrame(rows)


def standardize(x: pd.DataFrame) -> pd.DataFrame:
    out = x.copy()
    for col in out:
        sd = out[col].std(ddof=0)
        out[col] = (out[col] - out[col].mean()) / sd
    return out



def standardize_frame(df: pd.DataFrame, features: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compatibility wrapper for the former postprocessor API."""
    x_raw, quality = prepare_features(df, features)
    return standardize(x_raw), quality

def pca_svd(x: pd.DataFrame):
    arr = x.to_numpy(dtype=float)
    u, s, vt = np.linalg.svd(arr, full_matrices=False)
    scores = u * s
    eig = s**2 / max(1, arr.shape[0] - 1)
    explained = eig / eig.sum() if eig.sum() > 0 else np.zeros_like(eig)
    ncomp = min(arr.shape[1], arr.shape[0] - 1)
    score_df = pd.DataFrame(scores[:, :ncomp], index=x.index, columns=[f"PC{i+1}" for i in range(ncomp)])
    loading_df = pd.DataFrame(vt[:ncomp].T, index=x.columns, columns=score_df.columns)
    ev = pd.DataFrame({
        "component": score_df.columns,
        "explained_variance_ratio": explained[:ncomp],
        "cumulative_explained_variance": np.cumsum(explained[:ncomp]),
    })
    return score_df, loading_df, ev


def silhouette_for_labels(arr: np.ndarray, labels: np.ndarray) -> float:
    if len(np.unique(labels)) < 2 or len(labels) < 3:
        return np.nan
    dist = squareform(pdist(arr))
    values = []
    for i in range(len(arr)):
        own = labels == labels[i]
        own[i] = False
        a = float(dist[i, own].mean()) if own.any() else 0.0
        b = min(float(dist[i, labels == c].mean()) for c in np.unique(labels) if c != labels[i])
        values.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(values))


def choose_clusters(arr: np.ndarray, z: np.ndarray, max_k: int = 8):
    rows = []
    for k in range(2, min(max_k, len(arr) - 1) + 1):
        labels = fcluster(z, k, criterion="maxclust")
        rows.append({"k": k, "silhouette": silhouette_for_labels(arr, labels)})
    table = pd.DataFrame(rows)
    best = 2 if table.empty or table["silhouette"].isna().all() else int(table.loc[table["silhouette"].idxmax(), "k"])
    return best, table


def _comb2(n: np.ndarray | float) -> np.ndarray | float:
    return np.asarray(n) * (np.asarray(n) - 1) / 2


def adjusted_rand_index(a: np.ndarray, b: np.ndarray) -> float:
    ua, ia = np.unique(a, return_inverse=True)
    ub, ib = np.unique(b, return_inverse=True)
    table = np.zeros((len(ua), len(ub)), dtype=int)
    np.add.at(table, (ia, ib), 1)
    sum_nij = float(_comb2(table).sum())
    sum_ai = float(_comb2(table.sum(axis=1)).sum())
    sum_bj = float(_comb2(table.sum(axis=0)).sum())
    total = float(_comb2(len(a)))
    expected = sum_ai * sum_bj / total if total > 0 else 0.0
    maximum = 0.5 * (sum_ai + sum_bj)
    return (sum_nij - expected) / (maximum - expected) if maximum != expected else 1.0


def cluster_stability(x: pd.DataFrame, labels_ref: np.ndarray, k: int, n_iter: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    arr = x.to_numpy(dtype=float)
    rows = []
    for i in range(n_iter):
        if i % 2 == 0:
            trial = arr + rng.normal(0, 0.05, size=arr.shape)
            mode = "noise_5pct"
        else:
            n_features = max(2, int(np.ceil(0.8 * arr.shape[1])))
            cols = rng.choice(arr.shape[1], n_features, replace=False)
            trial = arr[:, cols]
            mode = "feature_subsample_80pct"
        z = linkage(trial, method="ward")
        labels = fcluster(z, k, criterion="maxclust")
        rows.append({"iteration": i + 1, "mode": mode, "adjusted_rand_index": adjusted_rand_index(labels_ref, labels)})
    return pd.DataFrame(rows)


def savefig(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_corr(corr: pd.DataFrame, out: Path):
    if corr.empty:
        return
    plt.figure(figsize=(max(8, .65 * len(corr)), max(7, .6 * len(corr))))
    im = plt.imshow(corr.to_numpy(dtype=float), vmin=-1, vmax=1, aspect="auto")
    plt.colorbar(im, label="Spearman ρ")
    plt.xticks(range(len(corr)), corr.columns, rotation=90, fontsize=8)
    plt.yticks(range(len(corr)), corr.index, fontsize=8)
    plt.title("Spearman correlation matrix")
    savefig(out)


def plot_pca(scores: pd.DataFrame, meta: pd.DataFrame, color_col: str, out: Path, title: str):
    if "PC1" not in scores or "PC2" not in scores:
        return
    plt.figure(figsize=(9, 7))
    cats = meta[color_col].fillna("unknown").astype(str)
    for cat in sorted(cats.unique()):
        idx = cats == cat
        plt.scatter(scores.loc[idx, "PC1"], scores.loc[idx, "PC2"], s=36, label=cat, alpha=.8)
    plt.xlabel("PC1"); plt.ylabel("PC2"); plt.title(title); plt.grid(alpha=.3); plt.legend(fontsize=8)
    savefig(out)


def plot_dendrogram(z: np.ndarray, labels: list[str], out: Path):
    plt.figure(figsize=(14, max(6, .12 * len(labels))))
    dendrogram(z, labels=labels, leaf_font_size=5, orientation="right")
    plt.title("Ward clustering in retained PCA space"); plt.xlabel("Ward distance")
    savefig(out)


def plot_cluster_profiles(profile: pd.DataFrame, out: Path):
    if profile.empty:
        return
    plt.figure(figsize=(max(9, .65 * len(profile.columns)), max(5, .7 * len(profile))))
    im = plt.imshow(profile.to_numpy(dtype=float), aspect="auto", vmin=-2.5, vmax=2.5)
    plt.colorbar(im, label="Mean standardized value")
    plt.xticks(range(len(profile.columns)), profile.columns, rotation=90, fontsize=8)
    plt.yticks(range(len(profile.index)), [f"cluster {x}" for x in profile.index])
    plt.title("Cluster morphology profiles")
    savefig(out)


def plot_stability(stability: pd.DataFrame, out: Path):
    if stability.empty:
        return
    groups = [g["adjusted_rand_index"].to_numpy() for _, g in stability.groupby("mode")]
    labels = [name for name, _ in stability.groupby("mode")]
    plt.figure(figsize=(8, 5))
    plt.boxplot(groups, tick_labels=labels)
    plt.ylabel("Adjusted Rand index"); plt.title("Cluster stability"); plt.grid(axis="y", alpha=.3)
    savefig(out)


def plot_outliers(outliers: pd.DataFrame, out: Path, top_n: int = 25):
    if outliers.empty:
        return
    q = outliers.sort_values("outlier_score", ascending=False).head(top_n).sort_values("outlier_score")
    plt.figure(figsize=(10, max(5, .32 * len(q))))
    plt.barh(q["slug"], q["outlier_score"])
    plt.xlabel("Maximum absolute robust z-score"); plt.title("Most atypical feature combinations")
    savefig(out)


def html_table(df: pd.DataFrame, max_rows: int = 50) -> str:
    return "<p><em>No data.</em></p>" if df.empty else df.head(max_rows).to_html(index=False, border=0, float_format=lambda x: f"{x:.5g}")


def write_report(path: Path, all_df: pd.DataFrame, eligible: pd.DataFrame, quality: pd.DataFrame,
                 redundancy: pd.DataFrame, ev: pd.DataFrame, cluster_choice: pd.DataFrame,
                 stability_summary: pd.DataFrame, subset_tests: pd.DataFrame,
                 outliers: pd.DataFrame, plots: list[Path]):
    parts = ["<!doctype html><html lang='ru'><head><meta charset='utf-8'><title>UrbanFractal analysis</title>"]
    parts.append("""<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:36px;line-height:1.45;color:#111}table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0 24px}th,td{border:1px solid #ccc;padding:5px 7px}th{background:#f2f2f2}img{max-width:100%;border:1px solid #ddd;margin-bottom:22px}code{background:#f4f4f4;padding:1px 4px}</style></head><body>""")
    parts.append("<h1>UrbanFractal: итоговая статистическая обработка</h1>")
    parts.append(f"<p>Найдено результатов: <b>{len(all_df)}</b>; допущено к многомерному анализу: <b>{len(eligible)}</b>.</p>")
    parts.append("<p>Кластеризация выполняется не по исходному перегруженному набору, а после удаления сильно коррелирующих признаков и перехода в пространство главных компонент, объясняющих не менее 90% дисперсии. Номера кластеров являются исследовательскими группами, а не заранее доказанными морфотипами.</p>")
    parts.append("<h2>Контроль признаков</h2>" + html_table(quality, 100))
    parts.append("<h2>Удаление избыточных признаков</h2>" + html_table(redundancy, 100))
    parts.append("<h2>PCA</h2>" + html_table(ev, 30))
    parts.append("<h2>Выбор числа кластеров</h2>" + html_table(cluster_choice, 20))
    parts.append("<h2>Устойчивость кластеров</h2>" + html_table(stability_summary, 20))
    parts.append("<h2>Россия и мировая выборка</h2>" + html_table(subset_tests.sort_values("p_fdr_bh") if "p_fdr_bh" in subset_tests else subset_tests, 100))
    parts.append("<h2>Аномальные города</h2>" + html_table(outliers.sort_values("outlier_score", ascending=False), 50))
    parts.append("<h2>Графики</h2>")
    for p in plots:
        if p.exists():
            parts.append(f"<h3>{html.escape(p.stem)}</h3><img src='{html.escape(str(p.relative_to(path.parent)))}'>")
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality-aware post-processing for UrbanFractal 0.4 results.")
    parser.add_argument("--run-root", default="/Volumes/aglikflash/urban_fractal_200_25m")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--correlation-threshold", type=float, default=0.90)
    parser.add_argument("--cluster-stability-iterations", type=int, default=100)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    run_root = Path(args.run_root).expanduser().resolve()
    project_root = Path(args.project_root).expanduser().resolve()
    results_root = run_root / "results"
    out_root = results_root / "analysis_25m"
    plot_root = out_root / "plots"
    out_root.mkdir(parents=True, exist_ok=True); plot_root.mkdir(parents=True, exist_ok=True)

    summaries = sorted((results_root / "final").glob("*/*/summary.json"))
    if not summaries:
        raise SystemExit(f"No final summary.json files under {results_root}")
    df = pd.DataFrame([extract_row(p, results_root) for p in summaries])
    catalog = pd.read_csv(project_root / "configs" / "city_catalog_200.csv", dtype=str)
    df = df.merge(catalog[["subset", "slug", "name", "query", "morphotype"]], on=["subset", "slug"], how="left")
    df["city"] = df["name"].fillna(df["slug"])

    audit_path = run_root / "audit" / "audit_final_25m.csv"
    if audit_path.exists():
        audit = pd.read_csv(audit_path)
        cols = [c for c in ["subset", "slug", "quality_status", "failure_reasons", "warning_reasons"] if c in audit]
        df = df.merge(audit[cols], on=["subset", "slug"], how="left")
        audit_ok = df["quality_status"].isin(["pass", "pass_with_warnings"])
    else:
        audit_ok = pd.Series(True, index=df.index)
        df["quality_status"] = "audit_missing"
    core_pass = df["core_2d_analysis_pass"].isin([True, 1, "True", "true", "1"])
    version_pass = df["software_version"].eq(__version__)
    df["analysis_eligible"] = audit_ok & core_pass & version_pass
    eligible_index = df.index[df["analysis_eligible"]]
    topology_harmonized, topology_harmonization = harmonize_topology_profiles(df.loc[eligible_index])
    for col in topology_harmonized.columns:
        df.loc[topology_harmonized.index, col] = topology_harmonized[col]
    df.to_csv(out_root / "city_features_enriched.csv", index=False)
    eligible = df[df["analysis_eligible"]].copy().reset_index(drop=True)
    eligible.to_csv(out_root / "analysis_eligible_cities.csv", index=False)
    if len(eligible) < 3:
        raise SystemExit(f"Only {len(eligible)} cities pass quality gates")

    x_raw, feature_quality = prepare_features(eligible, MORPHOLOGY_CANDIDATES)
    x_reduced_raw, redundancy = remove_redundant_features(x_raw, args.correlation_threshold)
    x = standardize(x_reduced_raw)
    feature_quality.to_csv(out_root / "feature_quality.csv", index=False)
    redundancy.to_csv(out_root / "feature_redundancy.csv", index=False)
    pd.concat([eligible[["subset", "slug", "city"]], x], axis=1).to_csv(out_root / "analysis_input_standardized.csv", index=False)

    all_corr_features = [c for c in MORPHOLOGY_CANDIDATES + TRANSPORT_FEATURES if c in eligible and eligible[c].notna().sum() >= 3]
    corr = eligible[all_corr_features].apply(pd.to_numeric, errors="coerce").corr(method="spearman")
    corr.to_csv(out_root / "correlations_spearman.csv")
    pmat = pd.DataFrame(np.nan, index=corr.index, columns=corr.columns)
    for a in corr:
        for b in corr:
            pair = eligible[[a, b]].apply(pd.to_numeric, errors="coerce").dropna()
            if a == b:
                pmat.loc[a, b] = 0.0
            elif len(pair) >= 4:
                pmat.loc[a, b] = spearmanr(pair[a], pair[b]).pvalue
    pmat.to_csv(out_root / "correlations_pvalues.csv")

    scores, loadings, ev = pca_svd(x)
    pd.concat([eligible[["subset", "slug", "city"]], scores], axis=1).to_csv(out_root / "pca_scores.csv", index=False)
    loadings.reset_index(names="feature").to_csv(out_root / "pca_loadings.csv", index=False)
    ev.to_csv(out_root / "pca_explained_variance.csv", index=False)
    n_cluster_pcs = int(np.searchsorted(ev["cumulative_explained_variance"].to_numpy(), .90) + 1)
    n_cluster_pcs = max(2, min(n_cluster_pcs, scores.shape[1]))
    cluster_space = scores.iloc[:, :n_cluster_pcs]

    z = linkage(cluster_space.to_numpy(), method="ward")
    best_k, cluster_choice = choose_clusters(cluster_space.to_numpy(), z)
    labels = fcluster(z, best_k, criterion="maxclust")
    cluster_choice.to_csv(out_root / "cluster_selection.csv", index=False)
    stability = cluster_stability(x, labels, best_k, args.cluster_stability_iterations)
    stability.to_csv(out_root / "cluster_stability_iterations.csv", index=False)
    stability_summary = stability.groupby("mode")["adjusted_rand_index"].agg(["count", "mean", "median", "min", "max"]).reset_index()
    stability_summary.to_csv(out_root / "cluster_stability_summary.csv", index=False)

    eligible["cluster"] = labels
    eligible[["subset", "slug", "city", "morphotype", "cluster"]].to_csv(out_root / "clusters.csv", index=False)
    profile = x.assign(cluster=labels).groupby("cluster").mean()
    profile.to_csv(out_root / "cluster_profiles_standardized.csv")

    rz = pd.DataFrame({c: robust_z(eligible[c]) for c in x.columns})
    eligible["outlier_score"] = rz.abs().max(axis=1)
    eligible["outlier_feature"] = rz.abs().idxmax(axis=1)
    eligible["outlier_signed_z"] = [rz.loc[i, eligible.loc[i, "outlier_feature"]] for i in eligible.index]
    outliers = eligible[["subset", "slug", "city", "outlier_score", "outlier_feature", "outlier_signed_z", "cluster"]]
    outliers.to_csv(out_root / "outliers.csv", index=False)

    tests = []
    for feature in list(x.columns) + [c for c in TRANSPORT_FEATURES if c in eligible]:
        a = pd.to_numeric(eligible.loc[eligible["subset"] == "russia", feature], errors="coerce").dropna()
        b = pd.to_numeric(eligible.loc[eligible["subset"] == "world", feature], errors="coerce").dropna()
        if len(a) >= 3 and len(b) >= 3:
            stat, p = mannwhitneyu(a, b, alternative="two-sided")
            tests.append({"feature": feature, "n_russia": len(a), "n_world": len(b),
                          "median_russia": a.median(), "median_world": b.median(),
                          "median_difference_russia_minus_world": a.median() - b.median(), "U": stat, "p_raw": p})
    subset_tests = pd.DataFrame(tests)
    if not subset_tests.empty:
        subset_tests["p_fdr_bh"] = benjamini_hochberg(subset_tests["p_raw"])
    subset_tests.to_csv(out_root / "subset_comparison.csv", index=False)

    plots = []
    p = plot_root / "correlation_heatmap.png"; plot_corr(corr, p); plots.append(p)
    meta = eligible[["subset", "slug"]].copy(); meta["cluster"] = labels.astype(str)
    p = plot_root / "pca_by_subset.png"; plot_pca(scores, meta, "subset", p, "PCA: Russia vs world"); plots.append(p)
    p = plot_root / "pca_by_cluster.png"; plot_pca(scores, meta, "cluster", p, f"PCA with Ward clusters (k={best_k})"); plots.append(p)
    p = plot_root / "dendrogram_ward.png"; plot_dendrogram(z, eligible["slug"].tolist(), p); plots.append(p)
    p = plot_root / "cluster_profiles.png"; plot_cluster_profiles(profile, p); plots.append(p)
    p = plot_root / "cluster_stability.png"; plot_stability(stability, p); plots.append(p)
    p = plot_root / "top_outliers.png"; plot_outliers(outliers, p); plots.append(p)

    report = out_root / "auto_analysis_report.html"
    write_report(report, df, eligible, feature_quality, redundancy, ev, cluster_choice, stability_summary, subset_tests, outliers, plots)
    manifest = {
        "generated": datetime.now().isoformat(timespec="seconds"),
        "software_version": __version__,
        "summaries_found": len(summaries),
        "analysis_eligible": len(eligible),
        "candidate_features": MORPHOLOGY_CANDIDATES,
        "topology_harmonization": topology_harmonization,
        "features_after_missingness": list(x_raw.columns),
        "features_after_redundancy_filter": list(x.columns),
        "correlation_threshold": args.correlation_threshold,
        "cluster_pca_components": n_cluster_pcs,
        "selected_clusters": best_k,
        "cluster_stability_mean_ari": float(stability["adjusted_rand_index"].mean()),
        "report": str(report),
    }
    (out_root / "analysis_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary files found: {len(summaries)}")
    print(f"Eligible cities: {len(eligible)}")
    print(f"Topology harmonization: {topology_harmonization}")
    print(f"Features after redundancy filter: {len(x.columns)}")
    print(f"Selected clusters: {best_k}")
    print(f"Mean cluster stability ARI: {manifest['cluster_stability_mean_ari']:.3f}")
    print(f"Report: {report}")
    if args.open:
        subprocess.run(["open", str(report)], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
