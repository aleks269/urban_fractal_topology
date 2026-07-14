from __future__ import annotations

import argparse
import csv
import html
import json
import math
import subprocess
from pathlib import Path
from datetime import datetime

import matplotlib.pyplot as plt
import pandas as pd


IMAGE_NAMES = [
    "analysis_domain_mask.png",
    "building_mask.png",
    "box_count_buildings.png",
    "lacunarity_buildings.png",
    "minkowski_profile.png",
    "betti_profile.png",
    "percolation_profile.png",
    "transport_potential_open_space_lr_contrast_1000.png",
    "transport_potential_open_space_tb_contrast_1000.png",
    "transport_potential_buildings_lr_contrast_1000.png",
    "transport_potential_buildings_tb_contrast_1000.png",
]

CSV_NAMES = [
    "box_counts_buildings.csv",
    "scaling_window_candidates_diagnostic.csv",
    "lacunarity_buildings.csv",
    "topology_minkowski_betti_profile.csv",
    "multifractal_spectrum_buildings.csv",
    "multifractal_raw_buildings.csv",
    "height_sensitivity_2_5d.csv",
    "transport_results.csv",
]


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def flatten(d, prefix="") -> dict:
    out = {}
    if not isinstance(d, dict):
        out[prefix] = d
        return out

    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def find_value(flat: dict, candidates: list[str]):
    for c in candidates:
        if c in flat:
            return flat[c]

    for c in candidates:
        for k, v in flat.items():
            if k.endswith("." + c):
                return v

    return ""


def to_float(x):
    try:
        if x == "" or x is None:
            return math.nan
        return float(x)
    except Exception:
        return math.nan


def fmt(v):
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:.6g}"
    return "" if v is None else str(v)


def city_title(result_dir: Path, summary: dict) -> str:
    for key in ["city", "city_name", "name", "slug"]:
        if key in summary and summary[key]:
            return str(summary[key])

    # Example folder name: zelenograd_50m
    name = result_dir.name
    if name.endswith("_50m") or name.endswith("_25m") or name.endswith("_100m"):
        name = name.rsplit("_", 1)[0]
    return name


def read_manifest_near_result(result_dir: Path) -> dict:
    # Usually result folder does not contain manifest.
    # Try data/approved_cities/... pattern is not guaranteed, so this is optional.
    p = result_dir / "manifest.json"
    if p.exists():
        return read_json(p)
    return {}


def collect_row(root: Path, result_dir: Path) -> dict:
    summary = read_json(result_dir / "summary.json")
    flat = flatten(summary)
    manifest = read_manifest_near_result(result_dir)
    rel = result_dir.relative_to(root)

    row = {
        "result_dir": str(rel),
        "city": city_title(result_dir, summary),
        "subset": manifest.get("subset", ""),
        "slug": manifest.get("slug", ""),
        "morphotype": manifest.get("morphotype", ""),
        "report": str(rel / "auto_report.html"),
        "summary_json": str(rel / "summary.json"),
    }

    aliases = {
        "pixel_size_m": [
            "input.pixel_size_m",
            "pixel_size_m",
            "pixel_m",
            "resolution_m",
            "pixel",
        ],
        "D_build": [
            "fractal_dimension_building_footprints.dimension",
            "D_build",
            "fractal_dimension",
            "box_counting_dimension",
            "dimension",
        ],
        "D_r2": [
            "fractal_dimension_building_footprints.r2",
            "r2",
        ],
        "D_scale_min_m": [
            "fractal_dimension_building_footprints.scale_min",
            "scale_min",
        ],
        "D_scale_max_m": [
            "fractal_dimension_building_footprints.scale_max",
            "scale_max",
        ],
        "plan_area_m2": [
            "planar_boundary.area_m2",
            "area_m2",
        ],
        "plan_perimeter_m": [
            "planar_boundary.perimeter_m",
            "perimeter_m",
        ],
        "compactness_2d": [
            "planar_boundary.compactness_2d_analysis_boundary",
            "planar_boundary.compactness_2d",
            "compactness_2d",
            "C_2D",
            "compactness",
        ],
        "building_count": [
            "building_surfaces.n_buildings",
            "building_surfaces.count",
            "count",
            "n_buildings",
        ],
        "footprint_area_m2": [
            "building_surfaces.footprint_area_m2",
        ],
        "roof_area_m2": [
            "building_surfaces.roof_area_m2",
        ],
        "wall_area_m2": [
            "building_surfaces.wall_area_m2",
        ],
        "envelope_area_m2": [
            "building_surfaces.envelope_area_m2",
        ],
        "volume_m3": [
            "building_surfaces.volume_m3",
        ],
        "known_height_fraction": [
            "building_surfaces.height_source_known_area_fraction",
            "building_surfaces.height_source_known_fraction",
            "height_source_known_fraction",
        ],
        "surface_amplification": [
            "derived_2_5d.surface_amplification_thermal_envelope_over_plan",
            "derived_2_5d.surface_amplification_envelope_over_plan",
            "surface_amplification",
            "A_env_over_A0",
            "k_env",
        ],
        "closed_3d_compactness": [
            "derived_2_5d.isoperimetric_compactness_3d_closed_surface",
            "derived_2_5d.compactness_3d",
            "C_3D",
            "compactness_3d",
        ],
        "thermal_surface_to_volume_1_per_m": [
            "derived_2_5d.thermal_surface_to_volume_1_per_m",
            "derived_2_5d.surface_to_volume_1_per_m",
        ],
        "lacunarity_min": [
            "lacunarity_building_footprints.min",
        ],
        "lacunarity_max": [
            "lacunarity_building_footprints.max",
        ],
        "lacunarity_mean": [
            "lacunarity_building_footprints.mean",
        ],
        "lacunarity_peak_window_m": [
            "lacunarity_building_footprints.peak_window_m",
        ],
        "giant_component_radius_m": [
            "topological_morphology_building_footprints.giant_component_radius_m",
            "topological_morphology_building_footprints.rc_m",
            "rc_m",
            "percolation_radius",
            "r_c",
        ],
        "spanning_radius_lr_m": [
            "topological_morphology_building_footprints.spanning_radius_lr_m",
        ],
        "spanning_radius_tb_m": [
            "topological_morphology_building_footprints.spanning_radius_tb_m",
        ],
        "foreground_fraction_within_domain": [
            "raster_diagnostics.foreground_fraction_within_domain",
        ],
        "domain_fraction_of_bbox": [
            "raster_diagnostics.domain_fraction_of_bbox",
        ],
        "beta0_at_zero": [
            "topological_morphology_building_footprints.beta0_at_zero",
            "beta0_at_zero",
        ],
        "beta1_at_zero": [
            "topological_morphology_building_footprints.beta1_at_zero",
            "beta1_at_zero",
        ],
        "beta1_peak_radius_m": [
            "topological_morphology_building_footprints.beta1_peak_radius_m",
            "beta1_peak_radius_m",
        ],
        "archipelago_index": [
            "topological_morphology_building_footprints.archipelago_index",
            "I_arch",
        ],
        "void_index": [
            "topological_morphology_building_footprints.void_index",
            "I_void",
        ],
        "boundary_complexity_index": [
            "topological_morphology_building_footprints.boundary_complexity_index",
            "I_boundary",
        ],
    }

    for out_key, names in aliases.items():
        row[out_key] = find_value(flat, names)

    transport = (summary.get("two_phase_transport") or {}).get("results") or []
    for item in transport:
        if not isinstance(item, dict):
            continue
        phase = str(item.get("phase", "")).strip()
        direction = str(item.get("direction", "")).strip()
        if not phase or not direction:
            continue
        prefix = f"transport_{phase}_{direction}"
        row[f"{prefix}_relative_conductance"] = item.get("relative_conductance", "")
        row[f"{prefix}_resistance"] = item.get("resistance", "")
        row[f"{prefix}_energy_error"] = item.get("energy_identity_relative_error", "")

    return row


def find_result_dirs(root: Path) -> list[Path]:
    return sorted(p.parent for p in root.rglob("summary.json") if p.is_file())


def make_single_report(result_dir: Path) -> None:
    summary = read_json(result_dir / "summary.json")
    flat = flatten(summary)
    title = city_title(result_dir, summary)

    images = []
    for name in IMAGE_NAMES:
        p = result_dir / name
        if p.exists():
            images.append(p)
    for p in sorted(result_dir.glob("*.png")):
        if p not in images:
            images.append(p)

    csv_files = []
    for name in CSV_NAMES:
        p = result_dir / name
        if p.exists():
            csv_files.append(p)
    for p in sorted(result_dir.glob("*.csv")):
        if p not in csv_files:
            csv_files.append(p)

    parts = []
    parts.append("<!doctype html>")
    parts.append("<html lang='ru'>")
    parts.append("<head>")
    parts.append("<meta charset='utf-8'>")
    parts.append(f"<title>UrbanFractal report: {html.escape(title)}</title>")
    parts.append("""
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 40px;
  color: #111;
  line-height: 1.45;
}
table {
  border-collapse: collapse;
  margin: 12px 0 24px 0;
  font-size: 14px;
}
td, th {
  border: 1px solid #ccc;
  padding: 6px 9px;
  vertical-align: top;
}
th { background: #f2f2f2; }
code {
  background: #f5f5f5;
  padding: 1px 4px;
  border-radius: 3px;
}
img {
  max-width: 100%;
  border: 1px solid #ddd;
  margin: 8px 0 24px 0;
}
.small { color: #666; font-size: 13px; }
</style>
""")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(f"<h1>UrbanFractal report: {html.escape(title)}</h1>")
    parts.append(f"<p class='small'>Generated: <code>{datetime.now().isoformat(timespec='seconds')}</code></p>")
    parts.append(f"<p class='small'>Folder: <code>{html.escape(str(result_dir))}</code></p>")

    parts.append("<h2>1. Summary</h2>")
    if flat:
        parts.append("<table>")
        parts.append("<tr><th>Parameter</th><th>Value</th></tr>")
        for k in sorted(flat.keys()):
            parts.append(
                f"<tr><td><code>{html.escape(str(k))}</code></td>"
                f"<td><code>{html.escape(fmt(flat[k]))}</code></td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<p><em>summary.json not found or empty.</em></p>")

    parts.append("<h2>2. Figures</h2>")
    if images:
        for p in images:
            parts.append(f"<h3>{html.escape(p.name)}</h3>")
            parts.append(f"<img src='{html.escape(p.name)}' alt='{html.escape(p.name)}'>")
    else:
        parts.append("<p><em>No PNG figures found.</em></p>")

    parts.append("<h2>3. Data files</h2>")
    if csv_files:
        parts.append("<ul>")
        for p in csv_files:
            parts.append(f"<li><a href='{html.escape(p.name)}'>{html.escape(p.name)}</a></li>")
        parts.append("</ul>")
    else:
        parts.append("<p><em>No CSV files found.</em></p>")

    parts.append("</body></html>")
    (result_dir / "auto_report.html").write_text("\n".join(parts), encoding="utf-8")


def write_global_csv(rows: list[dict], path: Path) -> None:
    preferred = [
        "result_dir",
        "city",
        "subset",
        "slug",
        "morphotype",
        "pixel_size_m",
        "D_build",
        "D_r2",
        "D_scale_min_m",
        "D_scale_max_m",
        "plan_area_m2",
        "compactness_2d",
        "building_count",
        "known_height_fraction",
        "foreground_fraction_within_domain",
        "domain_fraction_of_bbox",
        "surface_amplification",
        "closed_3d_compactness",
        "thermal_surface_to_volume_1_per_m",
        "lacunarity_min",
        "lacunarity_max",
        "lacunarity_mean",
        "lacunarity_peak_window_m",
        "giant_component_radius_m",
        "spanning_radius_lr_m",
        "spanning_radius_tb_m",
        "beta0_at_zero",
        "beta1_at_zero",
        "beta1_peak_radius_m",
        "archipelago_index",
        "void_index",
        "boundary_complexity_index",
        "transport_open_space_lr_relative_conductance",
        "transport_open_space_tb_relative_conductance",
        "transport_buildings_lr_relative_conductance",
        "transport_buildings_tb_relative_conductance",
        "report",
        "summary_json",
    ]

    keys = []
    for k in preferred:
        if any(k in r for r in rows):
            keys.append(k)
    extra = sorted({k for r in rows for k in r.keys()} - set(keys))
    keys.extend(extra)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def maybe_label(ax, n: int):
    if n <= 35:
        ax.legend(fontsize=7, loc="best")
    elif n <= 80:
        ax.legend(fontsize=6, loc="center left", bbox_to_anchor=(1.02, 0.5))
    else:
        ax.text(
            0.02,
            0.02,
            f"{n} cities; legend suppressed",
            transform=ax.transAxes,
            fontsize=9,
        )


def save_fig(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(path, dpi=220, bbox_inches="tight")
    plt.close()


def plot_metric_bar(rows: list[dict], metric: str, title: str, ylabel: str, out: Path, top: int | None = None):
    data = []
    for r in rows:
        val = to_float(r.get(metric))
        if math.isfinite(val):
            data.append((r["city"], val))
    if not data:
        return None

    data = sorted(data, key=lambda x: x[1])
    if top is not None and len(data) > top:
        data = data[-top:]

    names = [x[0] for x in data]
    vals = [x[1] for x in data]

    h = max(5, 0.23 * len(data))
    plt.figure(figsize=(10, h))
    plt.barh(names, vals)
    plt.xlabel(ylabel)
    plt.title(title)
    plt.grid(axis="x", alpha=0.3)
    save_fig(out)
    return out


def plot_metric_scatter(
    rows: list[dict],
    xmetric: str,
    ymetric: str,
    title: str,
    xlabel: str,
    ylabel: str,
    out: Path,
):
    data = []
    for r in rows:
        x = to_float(r.get(xmetric))
        y = to_float(r.get(ymetric))
        if math.isfinite(x) and math.isfinite(y):
            data.append((r["city"], x, y))
    if not data:
        return None

    plt.figure(figsize=(8, 6))
    for city, x, y in data:
        plt.scatter([x], [y], s=25)
        if len(data) <= 35:
            plt.text(x, y, " " + city, fontsize=7, alpha=0.8)

    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(alpha=0.3)
    save_fig(out)
    return out


def plot_box_count_profiles(result_dirs: list[Path], rows_by_dir: dict[str, dict], root: Path, out: Path):
    plotted = 0
    plt.figure(figsize=(9, 7))

    for d in result_dirs:
        p = d / "box_counts_buildings.csv"
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue
        if not {"scale_m", "count"}.issubset(df.columns):
            continue

        scale = pd.to_numeric(df["scale_m"], errors="coerce")
        count = pd.to_numeric(df["count"], errors="coerce")
        ok = (scale > 0) & (count > 0)
        if ok.sum() < 2:
            continue

        rel = str(d.relative_to(root))
        city = rows_by_dir.get(rel, {}).get("city", d.name)

        x = (1.0 / scale[ok]).map(math.log)
        y = count[ok].map(math.log)

        plt.plot(x, y, marker="o", linewidth=1, markersize=3, label=city)
        plotted += 1

    if plotted == 0:
        plt.close()
        return None

    plt.xlabel("log(1 / scale_m)")
    plt.ylabel("log(N)")
    plt.title("Box-counting profiles: all cities")
    plt.grid(alpha=0.3)
    maybe_label(plt.gca(), plotted)
    save_fig(out)
    return out


def plot_lacunarity_profiles(result_dirs: list[Path], rows_by_dir: dict[str, dict], root: Path, out: Path):
    plotted = 0
    plt.figure(figsize=(9, 7))

    for d in result_dirs:
        p = d / "lacunarity_buildings.csv"
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue

        xcol = "window_size_m" if "window_size_m" in df.columns else "scale_m"
        if xcol not in df.columns or "lacunarity" not in df.columns:
            continue

        x = pd.to_numeric(df[xcol], errors="coerce")
        y = pd.to_numeric(df["lacunarity"], errors="coerce")
        ok = (x > 0) & (y > 0)
        if ok.sum() < 2:
            continue

        rel = str(d.relative_to(root))
        city = rows_by_dir.get(rel, {}).get("city", d.name)

        plt.plot(x[ok], y[ok], marker="o", linewidth=1, markersize=3, label=city)
        plotted += 1

    if plotted == 0:
        plt.close()
        return None

    plt.xscale("log")
    plt.xlabel("Window size, m")
    plt.ylabel("Lacunarity")
    plt.title("Lacunarity profiles: all cities")
    plt.grid(alpha=0.3)
    maybe_label(plt.gca(), plotted)
    save_fig(out)
    return out


def plot_topology_profile(
    result_dirs: list[Path],
    rows_by_dir: dict[str, dict],
    root: Path,
    ycol: str,
    title: str,
    ylabel: str,
    out: Path,
    normalize: bool = False,
):
    plotted = 0
    plt.figure(figsize=(9, 7))

    for d in result_dirs:
        p = d / "topology_minkowski_betti_profile.csv"
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue

        if "radius_m" not in df.columns or ycol not in df.columns:
            continue

        x = pd.to_numeric(df["radius_m"], errors="coerce")
        y = pd.to_numeric(df[ycol], errors="coerce")

        ok = x.notna() & y.notna()
        if ok.sum() < 2:
            continue

        x = x[ok]
        y = y[ok]

        if normalize:
            y0 = y.iloc[0]
            if y0 == 0 or not math.isfinite(float(y0)):
                continue
            y = y / y0

        rel = str(d.relative_to(root))
        city = rows_by_dir.get(rel, {}).get("city", d.name)

        plt.plot(x, y, marker="o", linewidth=1, markersize=3, label=city)
        plotted += 1

    if plotted == 0:
        plt.close()
        return None

    plt.xlabel("Dilation radius r, m")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.grid(alpha=0.3)
    maybe_label(plt.gca(), plotted)
    save_fig(out)
    return out


def plot_multifractal_profiles(result_dirs: list[Path], rows_by_dir: dict[str, dict], root: Path, out: Path):
    plotted = 0
    plt.figure(figsize=(9, 7))

    for d in result_dirs:
        p = d / "multifractal_spectrum_buildings.csv"
        if not p.exists():
            continue
        try:
            df = pd.read_csv(p)
        except Exception:
            continue

        if not {"q", "Dq"}.issubset(df.columns):
            continue

        x = pd.to_numeric(df["q"], errors="coerce")
        y = pd.to_numeric(df["Dq"], errors="coerce")
        ok = x.notna() & y.notna()
        if ok.sum() < 2:
            continue

        rel = str(d.relative_to(root))
        city = rows_by_dir.get(rel, {}).get("city", d.name)

        order = x[ok].argsort()
        x2 = x[ok].iloc[order]
        y2 = y[ok].iloc[order]

        plt.plot(x2, y2, marker="o", linewidth=1, markersize=3, label=city)
        plotted += 1

    if plotted == 0:
        plt.close()
        return None

    plt.xlabel("q")
    plt.ylabel("Dq")
    plt.title("Multifractal spectra: all cities")
    plt.grid(alpha=0.3)
    maybe_label(plt.gca(), plotted)
    save_fig(out)
    return out


def make_comparison_plots(root: Path, result_dirs: list[Path], rows: list[dict]) -> list[Path]:
    plot_dir = root / "comparison_plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    rows_by_dir = {r["result_dir"]: r for r in rows}
    made = []

    tasks = [
        plot_metric_bar(rows, "D_build", "Building footprint fractal dimension", "D_build", plot_dir / "rank_D_build.png"),
        plot_metric_bar(rows, "lacunarity_mean", "Mean lacunarity by city", "Mean lacunarity", plot_dir / "rank_lacunarity_mean.png"),
        plot_metric_bar(rows, "surface_amplification", "Envelope surface amplification", "A_env / A_plan", plot_dir / "rank_surface_amplification.png"),
        plot_metric_bar(rows, "compactness_2d", "2D compactness by city", "4πA / P²", plot_dir / "rank_compactness_2d.png"),
        plot_metric_bar(rows, "giant_component_radius_m", "Giant-component radius by city", "r_giant, m", plot_dir / "rank_giant_component_radius.png"),
        plot_metric_bar(rows, "spanning_radius_lr_m", "Left-right spanning radius by city", "r_span,LR, m", plot_dir / "rank_spanning_radius_lr.png"),
        plot_metric_scatter(
            rows,
            "D_build",
            "lacunarity_mean",
            "Fractal dimension vs mean lacunarity",
            "D_build",
            "Mean lacunarity",
            plot_dir / "scatter_D_vs_lacunarity.png",
        ),
        plot_metric_scatter(
            rows,
            "D_build",
            "surface_amplification",
            "Fractal dimension vs envelope amplification",
            "D_build",
            "A_env / A_plan",
            plot_dir / "scatter_D_vs_surface_amplification.png",
        ),
        plot_metric_scatter(
            rows,
            "compactness_2d",
            "surface_amplification",
            "2D compactness vs envelope amplification",
            "2D compactness",
            "A_env / A_plan",
            plot_dir / "scatter_compactness_vs_surface_amplification.png",
        ),
        plot_metric_scatter(
            rows,
            "D_build",
            "spanning_radius_lr_m",
            "Fractal dimension vs left-right spanning radius",
            "D_build",
            "r_span,LR, m",
            plot_dir / "scatter_D_vs_spanning_lr.png",
        ),
        plot_box_count_profiles(
            result_dirs,
            rows_by_dir,
            root,
            plot_dir / "profiles_box_count_loglog.png",
        ),
        plot_lacunarity_profiles(
            result_dirs,
            rows_by_dir,
            root,
            plot_dir / "profiles_lacunarity.png",
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "beta0",
            "Betti-0 profiles: connected components under dilation",
            "β0(r)",
            plot_dir / "profiles_beta0.png",
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "beta1",
            "Betti-1 profiles: holes under dilation",
            "β1(r)",
            plot_dir / "profiles_beta1.png",
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "chi",
            "Euler characteristic profiles",
            "χ(r) = β0(r) - β1(r)",
            plot_dir / "profiles_chi.png",
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "giant_fraction",
            "Giant-component profiles",
            "Largest component fraction G(r)",
            plot_dir / "profiles_giant_fraction.png",
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "area_m2",
            "Normalized Minkowski area profiles",
            "A(r) / A(0)",
            plot_dir / "profiles_area_normalized.png",
            normalize=True,
        ),
        plot_topology_profile(
            result_dirs,
            rows_by_dir,
            root,
            "perimeter_m",
            "Normalized perimeter profiles",
            "P(r) / P(0)",
            plot_dir / "profiles_perimeter_normalized.png",
            normalize=True,
        ),
        plot_multifractal_profiles(
            result_dirs,
            rows_by_dir,
            root,
            plot_dir / "profiles_multifractal_Dq.png",
        ),
    ]

    for p in tasks:
        if p is not None:
            made.append(p)

    return made


def write_global_html(rows: list[dict], root: Path, plots: list[Path], path: Path) -> None:
    cols = [
        "city",
        "pixel_size_m",
        "D_build",
        "D_r2",
        "compactness_2d",
        "surface_amplification",
        "closed_3d_compactness",
        "lacunarity_mean",
        "giant_component_radius_m",
        "spanning_radius_lr_m",
        "spanning_radius_tb_m",
        "transport_open_space_lr_relative_conductance",
        "transport_open_space_tb_relative_conductance",
        "beta0_at_zero",
        "beta1_at_zero",
        "archipelago_index",
        "void_index",
        "boundary_complexity_index",
    ]

    parts = []
    parts.append("<!doctype html>")
    parts.append("<html lang='ru'>")
    parts.append("<head>")
    parts.append("<meta charset='utf-8'>")
    parts.append("<title>UrbanFractal all results</title>")
    parts.append("""
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 40px;
  color: #111;
  line-height: 1.45;
}
table {
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
}
td, th {
  border: 1px solid #ccc;
  padding: 5px 7px;
  vertical-align: top;
}
th {
  background: #f2f2f2;
  position: sticky;
  top: 0;
}
code { background: #f5f5f5; padding: 1px 4px; }
img {
  max-width: 100%;
  border: 1px solid #ddd;
  margin: 10px 0 32px 0;
}
.small { color: #666; font-size: 13px; }
.warning {
  background: #fff8df;
  border-left: 4px solid #c58b00;
  padding: 10px 14px;
}
</style>
""")
    parts.append("</head>")
    parts.append("<body>")
    parts.append("<h1>UrbanFractal: all results</h1>")
    parts.append(f"<p class='small'>Generated: <code>{datetime.now().isoformat(timespec='seconds')}</code></p>")
    parts.append(f"<p class='small'>Root: <code>{html.escape(str(root))}</code></p>")
    parts.append(f"<p>Total result folders: <b>{len(rows)}</b></p>")
    parts.append("<p><a href='all_results_summary.csv'>all_results_summary.csv</a></p>")

    parts.append("<div class='warning'>")
    parts.append(
        "Сравнительные графики корректны только для одинакового размера пикселя, "
        "сопоставимого определения городской границы и одинаковой полноты исходных OSM-данных. "
        "Если в одном наборе смешаны 25 м, 50 м и 100 м, сначала сравнивать надо внутри каждого разрешения."
    )
    parts.append("</div>")

    parts.append("<h2>1. Comparative plots</h2>")
    if plots:
        for p in plots:
            rel = p.relative_to(root)
            parts.append(f"<h3>{html.escape(p.stem)}</h3>")
            parts.append(f"<img src='{html.escape(str(rel))}' alt='{html.escape(p.name)}'>")
    else:
        parts.append("<p><em>No comparison plots were generated.</em></p>")

    parts.append("<h2>2. Summary table</h2>")
    parts.append("<table>")
    parts.append("<tr>")
    parts.append("<th>#</th>")
    for c in cols:
        parts.append(f"<th>{html.escape(c)}</th>")
    parts.append("<th>report</th>")
    parts.append("<th>folder</th>")
    parts.append("</tr>")

    for i, r in enumerate(rows, 1):
        parts.append("<tr>")
        parts.append(f"<td>{i}</td>")
        for c in cols:
            parts.append(f"<td>{html.escape(fmt(r.get(c, '')))}</td>")
        parts.append(f"<td><a href='{html.escape(r['report'])}'>auto_report.html</a></td>")
        parts.append(f"<td><code>{html.escape(r['result_dir'])}</code></td>")
        parts.append("</tr>")

    parts.append("</table>")
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="results", help="Root folder with result directories")
    parser.add_argument("--open", action="store_true", help="Open global report")
    parser.add_argument("--no-single", action="store_true", help="Do not regenerate per-city reports")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root does not exist: {root}")

    result_dirs = find_result_dirs(root)
    print(f"Found summary.json files: {len(result_dirs)}")

    rows = []
    for d in result_dirs:
        print("Found:", d)
        if not args.no_single:
            make_single_report(d)
        rows.append(collect_row(root, d))

    csv_path = root / "all_results_summary.csv"
    html_path = root / "all_results_index.html"

    write_global_csv(rows, csv_path)
    plots = make_comparison_plots(root, result_dirs, rows)
    write_global_html(rows, root, plots, html_path)

    print("Saved:", csv_path)
    print("Saved:", html_path)
    print("Comparison plots:", root / "comparison_plots")

    if args.open:
        subprocess.run(["open", str(html_path)], check=False)


if __name__ == "__main__":
    main()
