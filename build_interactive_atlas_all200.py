#!/usr/bin/env python3
"""Build an offline interactive Urban Fractal Topology atlas.

The generated report is a static directory: index.html contains all tabular and
curve data plus an embedded Plotly runtime; city images/reports are copied to
assets/. It can be opened directly from the filesystem without a web server.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
from plotly.offline.offline import get_plotlyjs

DISPLAY_NAME_COLUMNS = (
    "display_name_ru",
    "name_ru",
    "display_name",
    "city",
    "name",
)

METRICS: list[dict[str, str]] = [
    {"key": "D_build", "label": "Фрактальная размерность D", "unit": "", "group": "Фрактальные"},
    {"key": "D_r2", "label": "R² фрактальной аппроксимации", "unit": "", "group": "Фрактальные"},
    {"key": "D_stderr", "label": "Стандартная ошибка D", "unit": "", "group": "Фрактальные"},
    {"key": "D_grid_offset_cv", "label": "CV при сдвиге сетки", "unit": "", "group": "Фрактальные"},
    {"key": "D_leave_one_out_cv", "label": "CV при исключении масштаба", "unit": "", "group": "Фрактальные"},
    {"key": "D_scale_span_decades", "label": "Диапазон масштабов", "unit": "декады", "group": "Фрактальные"},
    {"key": "lacunarity_mean", "label": "Средняя лакунарность", "unit": "", "group": "Фрактальные"},
    {"key": "lacunarity_max", "label": "Максимальная лакунарность", "unit": "", "group": "Фрактальные"},
    {"key": "Dq_0", "label": "D₀", "unit": "", "group": "Мультифрактальные"},
    {"key": "Dq_1", "label": "D₁", "unit": "", "group": "Мультифрактальные"},
    {"key": "Dq_2", "label": "D₂", "unit": "", "group": "Мультифрактальные"},
    {"key": "multifractal_range", "label": "Диапазон Dq", "unit": "", "group": "Мультифрактальные"},
    {"key": "plan_area_km2", "label": "Площадь области", "unit": "км²", "group": "Геометрия"},
    {"key": "compactness_boundary", "label": "Компактность границы", "unit": "", "group": "Геометрия"},
    {"key": "domain_fraction_of_bbox", "label": "Доля области в bbox", "unit": "", "group": "Геометрия"},
    {"key": "building_count", "label": "Число зданий", "unit": "", "group": "Застройка"},
    {"key": "footprint_area_km2", "label": "Площадь пятен зданий", "unit": "км²", "group": "Застройка"},
    {"key": "foreground_fraction", "label": "Доля застройки", "unit": "", "group": "Застройка"},
    {"key": "known_height_area_fraction", "label": "Известная по площади высота", "unit": "", "group": "2,5D"},
    {"key": "thermal_surface_amplification", "label": "Амплификация поверхности", "unit": "", "group": "2,5D"},
    {"key": "thermal_surface_to_volume_1_per_m", "label": "S/V тепловой оболочки", "unit": "1/м", "group": "2,5D"},
    {"key": "beta0_density_km2", "label": "Плотность β₀", "unit": "км⁻²", "group": "Топология"},
    {"key": "beta1_density_km2", "label": "Плотность β₁", "unit": "км⁻²", "group": "Топология"},
    {"key": "archipelago_index_harmonized", "label": "Архипелажность (гарм.)", "unit": "", "group": "Топология"},
    {"key": "void_index_harmonized", "label": "Индекс пустот (гарм.)", "unit": "", "group": "Топология"},
    {"key": "boundary_complexity_harmonized", "label": "Сложность границы (гарм.)", "unit": "", "group": "Топология"},
    {"key": "giant_component_radius_norm", "label": "Радиус гигантской компоненты ρ", "unit": "", "group": "Перколяция"},
    {"key": "spanning_radius_lr_norm", "label": "LR-перколяция ρ", "unit": "", "group": "Перколяция"},
    {"key": "spanning_radius_tb_norm", "label": "TB-перколяция ρ", "unit": "", "group": "Перколяция"},
    {"key": "open_space_relative_conductance_lr", "label": "Проводимость пустот LR", "unit": "отн.", "group": "Транспорт"},
    {"key": "open_space_relative_conductance_tb", "label": "Проводимость пустот TB", "unit": "отн.", "group": "Транспорт"},
    {"key": "buildings_relative_conductance_lr", "label": "Проводимость зданий LR", "unit": "отн.", "group": "Транспорт"},
    {"key": "buildings_relative_conductance_tb", "label": "Проводимость зданий TB", "unit": "отн.", "group": "Транспорт"},
    {"key": "open_space_transport_anisotropy", "label": "Анизотропия пустот", "unit": "", "group": "Транспорт"},
    {"key": "buildings_transport_anisotropy", "label": "Анизотропия зданий", "unit": "", "group": "Транспорт"},
    {"key": "transport_energy_error", "label": "Ошибка энергетического тождества", "unit": "", "group": "QC"},
    {"key": "raster_area_error_rel", "label": "Ошибка площади зданий", "unit": "", "group": "QC"},
    {"key": "boundary_raster_area_error_rel", "label": "Ошибка площади границы", "unit": "", "group": "QC"},
]

CORE_TABLE_KEYS = [
    "D_build", "lacunarity_mean", "plan_area_km2", "building_count",
    "foreground_fraction", "beta0_density_km2", "beta1_density_km2",
    "archipelago_index_harmonized", "spanning_radius_lr_norm",
    "spanning_radius_tb_norm", "known_height_area_fraction",
    "transport_energy_error",
]

CURVE_FILES = {
    "box": "box_counts_buildings.csv",
    "lacunarity": "lacunarity_buildings.csv",
    "topology": "topology_minkowski_betti_profile.csv",
    "multifractal": "multifractal_spectrum_buildings.csv",
    "height": "height_sensitivity_2_5d.csv",
}

ASSET_FILES = [
    "building_mask.png", "analysis_domain_mask.png", "box_count_buildings.png",
    "lacunarity_buildings.png", "betti_profile.png", "minkowski_profile.png",
    "percolation_profile.png", "transport_potential_open_space_lr_contrast_1000.png",
    "transport_potential_buildings_lr_contrast_1000.png", "auto_report.html",
]


def json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, (bool, str)):
        return value
    if hasattr(value, "item"):
        return json_value(value.item())
    return str(value)


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [{str(k): json_value(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def find_one(base: Path, patterns: list[str], required: bool = True) -> Path | None:
    for pattern in patterns:
        matches = sorted(base.glob(pattern))
        if matches:
            return matches[0]
    if required:
        raise FileNotFoundError(f"Не найден файл по шаблонам {patterns} в {base}")
    return None


def read_optional_csv(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def first_nonempty(mapping: Any, keys: tuple[str, ...]) -> str | None:
    """Return the first non-empty textual value from a Series/dict-like object."""
    if mapping is None:
        return None
    for key in keys:
        try:
            value = mapping.get(key)
        except AttributeError:
            continue
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        text = str(value).strip()
        if text:
            return text
    return None


def load_name_overrides(path: Path | None) -> dict[str, str]:
    """Load optional display-name overrides from JSON or CSV.

    JSON may be a simple {slug: display_name} mapping. CSV must contain a
    ``slug`` column and one of: display_name_ru, name_ru, display_name, name, city.
    """
    if path is None:
        return {}
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Не найден файл названий: {path}")
    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("JSON-файл названий должен быть объектом {slug: name}")
        return {str(k): str(v).strip() for k, v in raw.items() if str(v).strip()}
    frame = pd.read_csv(path)
    if "slug" not in frame.columns:
        raise ValueError("CSV-файл названий должен содержать столбец slug")
    result: dict[str, str] = {}
    for _, row in frame.iterrows():
        slug = str(row.get("slug", "")).strip()
        name = first_nonempty(row, DISPLAY_NAME_COLUMNS)
        if slug and name:
            result[slug] = name
    return result


def locate_city_catalog(source_root: Path, explicit: Path | None = None) -> Path | None:
    """Locate the 200-city catalog without assuming where the run directory lives."""
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit.expanduser())
    script_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()
    candidates.extend([
        source_root / "configs" / "city_catalog_200.csv",
        source_root.parent / "configs" / "city_catalog_200.csv",
        cwd / "configs" / "city_catalog_200.csv",
        cwd / "city_catalog_200.csv",
        script_dir / "configs" / "city_catalog_200.csv",
        script_dir / "city_catalog_200.csv",
        script_dir.parent / "configs" / "city_catalog_200.csv",
    ])
    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return candidate
    if explicit is not None:
        raise FileNotFoundError(f"Не найден каталог городов: {explicit}")
    return None


def load_city_catalog(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    frame = pd.read_csv(path)
    if "slug" not in frame.columns:
        raise ValueError(f"В каталоге {path} отсутствует столбец slug")
    frame["slug"] = frame["slug"].astype(str)
    return frame


def resolve_display_name(
    slug: str,
    result_row: Any,
    catalog_row: Any,
    overrides: dict[str, str],
) -> str:
    """Resolve a name for every city; no finite hard-coded city list is used."""
    if slug in overrides:
        return overrides[slug]
    name = first_nonempty(catalog_row, DISPLAY_NAME_COLUMNS)
    if name:
        return name
    name = first_nonempty(result_row, DISPLAY_NAME_COLUMNS)
    if name:
        return name
    return slug.replace("_", " ").replace("-", " ").title()


def safe_curve(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return records(pd.read_csv(path))
    except Exception:
        return []


def normalize_results_root(path: Path) -> tuple[Path, Path]:
    path = path.resolve()
    if (path / "results").is_dir():
        return path, path / "results"
    if path.name == "results":
        return path.parent, path
    if (path / "final").is_dir():
        return path.parent, path
    raise FileNotFoundError("Ожидался каталог архива, results/ или каталог с final/")


def collect_payload(
    source_root: Path,
    results_root: Path,
    output_dir: Path,
    copy_assets: bool,
    catalog_path: Path | None = None,
    names_path: Path | None = None,
) -> dict[str, Any]:
    enriched_path = find_one(results_root, ["analysis_*/city_features_enriched.csv", "city_features*_enriched.csv"])
    enriched = pd.read_csv(enriched_path)

    resolved_catalog_path = locate_city_catalog(source_root, catalog_path)
    catalog = load_city_catalog(resolved_catalog_path)
    catalog_lookup = (
        catalog.set_index("slug").to_dict(orient="index")
        if not catalog.empty
        else {}
    )
    display_name_overrides = load_name_overrides(names_path)

    audit_path = find_one(source_root, ["audit/audit*.csv", "results/audit/audit*.csv"], required=False)
    audit = read_optional_csv(audit_path)
    pca = read_optional_csv(find_one(results_root, ["analysis_*/pca_scores.csv"], required=False))
    clusters = read_optional_csv(find_one(results_root, ["analysis_*/clusters.csv"], required=False))
    outliers = read_optional_csv(find_one(results_root, ["analysis_*/outliers.csv"], required=False))
    pca_var = read_optional_csv(find_one(results_root, ["analysis_*/pca_explained_variance.csv"], required=False))
    pca_loadings = read_optional_csv(find_one(results_root, ["analysis_*/pca_loadings.csv"], required=False))
    feature_quality = read_optional_csv(find_one(results_root, ["analysis_*/feature_quality.csv"], required=False))

    for frame in (enriched, audit, pca, clusters, outliers):
        if not frame.empty and "slug" in frame.columns:
            frame["slug"] = frame["slug"].astype(str)

    audit_lookup = audit.set_index("slug").to_dict(orient="index") if not audit.empty and "slug" in audit.columns else {}
    pca_lookup = pca.set_index("slug").to_dict(orient="index") if not pca.empty and "slug" in pca.columns else {}
    cluster_lookup = clusters.set_index("slug").to_dict(orient="index") if not clusters.empty and "slug" in clusters.columns else {}
    outlier_lookup = outliers.set_index("slug").to_dict(orient="index") if not outliers.empty and "slug" in outliers.columns else {}

    final_root = results_root / "final"
    city_dirs: dict[str, Path] = {}
    for summary in final_root.glob("*/*/summary.json"):
        city_dirs[summary.parent.name] = summary.parent

    assets_root = output_dir / "assets" / "cities"
    if copy_assets:
        assets_root.mkdir(parents=True, exist_ok=True)

    cities: list[dict[str, Any]] = []
    curves: dict[str, dict[str, list[dict[str, Any]]]] = {}
    available_columns = set(enriched.columns)
    active_metrics = [m for m in METRICS if m["key"] in available_columns]

    for _, row in enriched.iterrows():
        slug = str(row.get("slug"))
        source_city_dir = city_dirs.get(slug)
        audit_row = audit_lookup.get(slug, {})
        pca_row = pca_lookup.get(slug, {})
        cluster_row = cluster_lookup.get(slug, {})
        outlier_row = outlier_lookup.get(slug, {})
        catalog_row = catalog_lookup.get(slug, {})

        source_name = (
            first_nonempty(row, ("city", "name"))
            or first_nonempty(catalog_row, ("name", "city"))
            or slug.replace("_", " ").title()
        )
        name = resolve_display_name(slug, row, catalog_row, display_name_overrides)
        quality_status = audit_row.get("quality_status") or row.get("quality_status") or "unknown"
        warnings = audit_row.get("warning_reasons")
        failures = audit_row.get("failure_reasons")

        metrics = {m["key"]: json_value(row.get(m["key"])) for m in active_metrics}
        all_values = {str(k): json_value(v) for k, v in row.items()}
        pca_values = {str(k): json_value(v) for k, v in pca_row.items() if str(k).startswith("PC")}

        asset_map: dict[str, str] = {}
        if source_city_dir and source_city_dir.exists():
            if copy_assets:
                target = assets_root / slug
                target.mkdir(parents=True, exist_ok=True)
                # Copy the complete per-city result directory so that the original
                # auto_report.html keeps all image and CSV links functional offline.
                for src in source_city_dir.iterdir():
                    if src.is_file():
                        shutil.copy2(src, target / src.name)
                for filename in ASSET_FILES:
                    if (target / filename).exists():
                        asset_map[filename] = f"assets/cities/{slug}/{filename}"
            else:
                for filename in ASSET_FILES:
                    if (source_city_dir / filename).exists():
                        asset_map[filename] = str((source_city_dir / filename).resolve().as_uri())
            curves[slug] = {kind: safe_curve(source_city_dir / filename) for kind, filename in CURVE_FILES.items()}
        else:
            curves[slug] = {kind: [] for kind in CURVE_FILES}

        city = {
            "slug": slug,
            "name": name,
            "source_name": json_value(source_name),
            "subset": json_value(row.get("subset") or catalog_row.get("subset")),
            "morphotype": json_value(
                cluster_row.get("morphotype")
                or row.get("morphotype")
                or catalog_row.get("morphotype")
            ),
            "cluster": json_value(cluster_row.get("cluster")),
            "quality_status": json_value(quality_status),
            "analysis_eligible": bool(row.get("analysis_eligible")) if not pd.isna(row.get("analysis_eligible")) else False,
            "warnings": [] if warnings is None or pd.isna(warnings) else [x for x in str(warnings).split(";") if x],
            "failures": [] if failures is None or pd.isna(failures) else [x for x in str(failures).split(";") if x],
            "metrics": metrics,
            "all_values": all_values,
            "pca": pca_values,
            "outlier_score": json_value(outlier_row.get("outlier_score")),
            "outlier_feature": json_value(outlier_row.get("outlier_feature")),
            "outlier_signed_z": json_value(outlier_row.get("outlier_signed_z")),
            "assets": asset_map,
        }
        cities.append(city)

    cities.sort(key=lambda c: c["name"])
    versions = sorted({str(c["all_values"].get("software_version")) for c in cities if c["all_values"].get("software_version")})
    pixel_sizes = sorted({c["all_values"].get("pixel_size_m") for c in cities if c["all_values"].get("pixel_size_m") is not None})

    return {
        "meta": {
            "title": "Urban Fractal Topology — интерактивный атлас",
            "source_root": str(source_root),
            "city_count": len(cities),
            "software_versions": versions,
            "pixel_sizes_m": pixel_sizes,
            "generated_from": str(enriched_path),
            "city_catalog": str(resolved_catalog_path) if resolved_catalog_path else None,
            "display_names_file": str(names_path.resolve()) if names_path else None,
        },
        "metrics": active_metrics,
        "core_table_keys": [x for x in CORE_TABLE_KEYS if x in available_columns],
        "cities": cities,
        "curves": curves,
        "pca_variance": records(pca_var),
        "pca_loadings": records(pca_loadings),
        "feature_quality": records(feature_quality),
    }


HTML_TEMPLATE = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Urban Fractal Topology — интерактивный атлас</title>
<style>
:root{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#637083;--line:#dce2e8;--accent:#315a7d;--accent2:#6f8fa8;--bad:#a33;--warn:#9a6b00;--ok:#27653b;--shadow:0 2px 10px rgba(20,35,50,.08)}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;font-size:14px}
body.dark{--bg:#12171d;--panel:#1b222b;--ink:#e5e9ed;--muted:#9ba7b4;--line:#34404c;--accent:#8ab4d0;--accent2:#5e8198;--shadow:none}
button,input,select{font:inherit} button{cursor:pointer}.app{display:grid;grid-template-columns:310px 1fr;min-height:100vh}.sidebar{position:fixed;inset:0 auto 0 0;width:310px;background:var(--panel);border-right:1px solid var(--line);padding:18px;overflow:auto;z-index:4}.main{grid-column:2;padding:0 22px 50px}.brand h1{font-size:18px;margin:0 0 5px}.brand p{color:var(--muted);margin:0 0 14px;font-size:12px}.section-title{font-weight:650;margin:18px 0 8px}.search,.ctrl{width:100%;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:7px;padding:8px}.buttons{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.btn{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:6px 9px}.btn.primary{background:var(--accent);color:white;border-color:var(--accent)}.btn.danger{color:var(--bad)}.city-list{border:1px solid var(--line);border-radius:7px;max-height:360px;overflow:auto;padding:5px}.city-item{display:flex;gap:8px;align-items:center;padding:5px 4px;border-radius:5px}.city-item:hover{background:var(--bg)}.city-item .status{width:8px;height:8px;border-radius:50%;margin-left:auto}.status.pass{background:var(--ok)}.status.pass_with_warnings{background:var(--warn)}.status.fail{background:var(--bad)}.status.unknown{background:var(--muted)}
.topbar{position:sticky;top:0;z-index:3;background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(8px);padding:14px 0 8px}.tabs{display:flex;gap:5px;flex-wrap:wrap}.tab-btn{border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:7px;padding:8px 11px}.tab-btn.active{background:var(--accent);border-color:var(--accent);color:white}.tab{display:none}.tab.active{display:block}.page-title{display:flex;justify-content:space-between;align-items:flex-end;margin:20px 0 12px}.page-title h2{margin:0;font-size:22px}.page-title .note{color:var(--muted)}
.grid{display:grid;gap:14px}.grid.cols-2{grid-template-columns:repeat(2,minmax(0,1fr))}.grid.cols-3{grid-template-columns:repeat(3,minmax(0,1fr))}.grid.cols-4{grid-template-columns:repeat(4,minmax(0,1fr))}.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;box-shadow:var(--shadow);min-width:0}.card h3{margin:0 0 10px;font-size:15px}.kpi{font-size:28px;font-weight:700}.kpi-label{color:var(--muted);margin-top:4px}.controls{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:9px;margin-bottom:12px}.controls label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:var(--muted)}.plot{height:520px}.plot.small{height:360px}.plot.tall{height:680px}.muted{color:var(--muted)}.selection-box{padding:8px;border:1px dashed var(--line);border-radius:7px;margin-bottom:10px}.metric-list{height:250px;width:100%;background:var(--panel);color:var(--ink);border:1px solid var(--line);border-radius:7px;padding:5px}.compare-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}.city-card img{width:100%;height:240px;object-fit:contain;background:#fff;border:1px solid var(--line);border-radius:6px}.city-card table{width:100%;border-collapse:collapse}.city-card td{border-bottom:1px solid var(--line);padding:5px 2px}.city-card td:last-child{text-align:right;font-variant-numeric:tabular-nums}.badge{display:inline-block;padding:2px 6px;border-radius:9px;background:var(--bg);border:1px solid var(--line);font-size:11px}.warning{border-left:3px solid var(--warn);padding-left:8px}.failure{border-left:3px solid var(--bad);padding-left:8px}.table-wrap{overflow:auto;max-height:680px;border:1px solid var(--line);border-radius:8px}.data-table{border-collapse:collapse;width:100%;background:var(--panel);font-size:12px}.data-table th,.data-table td{padding:7px 8px;border-bottom:1px solid var(--line);white-space:nowrap;text-align:right}.data-table th{position:sticky;top:0;background:var(--panel);cursor:pointer;z-index:1}.data-table th:first-child,.data-table td:first-child{text-align:left;position:sticky;left:0;background:var(--panel)}.qc-row{padding:10px;border-bottom:1px solid var(--line)}.footer{margin-top:22px;color:var(--muted);font-size:12px}.hidden{display:none!important}
@media(max-width:1050px){.app{display:block}.sidebar{position:static;width:auto;border-right:0;border-bottom:1px solid var(--line)}.main{padding:0 12px 40px}.controls{grid-template-columns:repeat(2,minmax(130px,1fr))}.grid.cols-4,.grid.cols-3{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:650px){.controls,.grid.cols-2,.grid.cols-3,.grid.cols-4{grid-template-columns:1fr}.plot{height:430px}}
</style>
<script>__PLOTLY_JS__</script>
</head>
<body>
<div class="app">
<aside class="sidebar">
  <div class="brand"><h1>Urban Fractal Topology</h1><p id="metaText"></p></div>
  <input id="citySearch" class="search" placeholder="Поиск города">
  <div class="buttons">
    <button class="btn" id="allBtn">Все</button><button class="btn" id="noneBtn">Снять</button><button class="btn" id="invertBtn">Инверсия</button>
    <button class="btn" id="eligibleBtn">Допущенные</button><button class="btn" id="qcBtn">Без fail</button>
  </div>
  <select id="statusFilter" class="ctrl"><option value="all">Все QC-статусы</option><option value="pass">pass</option><option value="pass_with_warnings">pass_with_warnings</option><option value="fail">fail</option><option value="unknown">unknown</option></select>
  <div class="section-title" id="selectedCount"></div>
  <div id="cityList" class="city-list"></div>
  <div class="section-title">Выделение на scatter</div>
  <div id="brushInfo" class="muted">Нет выделения</div>
  <div class="buttons"><button class="btn" id="keepBrushBtn">Оставить</button><button class="btn" id="addBrushBtn">Добавить</button><button class="btn danger" id="removeBrushBtn">Исключить</button></div>
  <div class="section-title">Состояние атласа</div>
  <div class="buttons"><button class="btn" id="saveStateBtn">Сохранить JSON</button><label class="btn">Загрузить<input id="loadStateInput" type="file" accept="application/json" hidden></label><button class="btn" id="themeBtn">Тёмная тема</button></div>
</aside>
<main class="main">
<div class="topbar"><div class="tabs">
<button class="tab-btn active" data-tab="overview">Обзор</button><button class="tab-btn" data-tab="explore">Связи и рейтинги</button><button class="tab-btn" data-tab="corr">Корреляции</button><button class="tab-btn" data-tab="pca">PCA и кластеры</button><button class="tab-btn" data-tab="curves">Масштабные кривые</button><button class="tab-btn" data-tab="compare">Сравнение</button><button class="tab-btn" data-tab="table">Таблица и QC</button>
</div></div>

<section id="overview" class="tab active">
<div class="page-title"><h2>Обзор выборки</h2><div class="note">Все показатели перестраиваются по отмеченным городам</div></div>
<div class="grid cols-4">
<div class="card"><div class="kpi" id="kpiCities">0</div><div class="kpi-label">выбрано городов</div></div>
<div class="card"><div class="kpi" id="kpiEligible">0</div><div class="kpi-label">допущено к анализу</div></div>
<div class="card"><div class="kpi" id="kpiArea">—</div><div class="kpi-label">медианная площадь, км²</div></div>
<div class="card"><div class="kpi" id="kpiD">—</div><div class="kpi-label">медиана D</div></div>
</div>
<div class="grid cols-2" style="margin-top:14px"><div class="card"><h3>QC-статусы</h3><div id="statusPlot" class="plot small"></div></div><div class="card"><h3>Распределение фрактальной размерности</h3><div id="overviewDPlot" class="plot small"></div></div></div>
<div class="grid cols-2" style="margin-top:14px"><div class="card"><h3>Площадь области и доля застройки</h3><div id="areaCoveragePlot" class="plot"></div></div><div class="card"><h3>Наиболее выраженные выбросы</h3><div id="outlierPlot" class="plot"></div></div></div>
</section>

<section id="explore" class="tab">
<div class="page-title"><h2>Связи и рейтинги</h2><div class="note">Лассо и прямоугольное выделение работают как фильтр</div></div>
<div class="card"><div class="controls">
<label>Ось X<select id="xMetric" class="ctrl"></select></label><label>Ось Y<select id="yMetric" class="ctrl"></select></label><label>Размер маркера<select id="sizeMetric" class="ctrl"><option value="none">Постоянный</option></select></label><label>Цвет<select id="colorMode" class="ctrl"><option value="cluster">Кластер</option><option value="quality">QC</option><option value="metric">Численный показатель</option></select></label>
<label>Показатель цвета<select id="colorMetric" class="ctrl"></select></label><label>Шкала X<select id="xScale" class="ctrl"><option>linear</option><option>log</option></select></label><label>Шкала Y<select id="yScale" class="ctrl"><option>linear</option><option>log</option></select></label><label>Подписи<select id="labelMode" class="ctrl"><option value="hover">Только при наведении</option><option value="all">Все города</option><option value="outliers">Только выбросы</option></select></label>
<label>Минимум X<input id="xMin" class="ctrl" type="number" step="any" placeholder="auto"></label><label>Максимум X<input id="xMax" class="ctrl" type="number" step="any" placeholder="auto"></label><label>Минимум Y<input id="yMin" class="ctrl" type="number" step="any" placeholder="auto"></label><label>Максимум Y<input id="yMax" class="ctrl" type="number" step="any" placeholder="auto"></label>
</div><div id="scatterStats" class="selection-box"></div><div id="scatterPlot" class="plot tall"></div></div>
<div class="card" style="margin-top:14px"><div class="controls"><label>Рейтинговый показатель<select id="rankMetric" class="ctrl"></select></label><label>Порядок<select id="rankOrder" class="ctrl"><option value="desc">По убыванию</option><option value="asc">По возрастанию</option></select></label><label>Показывать<input id="rankN" class="ctrl" type="number" value="30" min="1"></label><label>Нормировка<select id="rankNorm" class="ctrl"><option value="raw">Исходные значения</option><option value="percentile">Процентиль</option><option value="zscore">z-score</option></select></label></div><div id="rankPlot" class="plot tall"></div></div>
</section>

<section id="corr" class="tab">
<div class="page-title"><h2>Корреляции</h2><div class="note">Щелчок по ячейке открывает соответствующий scatter plot</div></div>
<div class="grid cols-2"><div class="card"><h3>Признаки</h3><select id="corrMetrics" class="metric-list" multiple></select><div class="buttons"><button class="btn" id="corrCoreBtn">Основные</button><button class="btn" id="corrAllBtn">Все</button><button class="btn" id="corrNoneBtn">Снять</button></div><label>Коэффициент<select id="corrMethod" class="ctrl"><option value="spearman">Спирмен</option><option value="pearson">Пирсон</option></select></label></div><div class="card"><h3>Диагностика</h3><p class="muted">Корреляции пересчитываются только по текущей выборке и попарно доступным значениям. Число наблюдений показывается при наведении.</p><div id="corrTopPairs"></div></div></div>
<div class="card" style="margin-top:14px"><div id="corrPlot" class="plot tall"></div></div>
</section>

<section id="pca" class="tab">
<div class="page-title"><h2>PCA и кластеры</h2><div class="note">Используется результат статистического этапа текущего прогона</div></div>
<div class="controls"><label>Ось X<select id="pcX" class="ctrl"></select></label><label>Ось Y<select id="pcY" class="ctrl"></select></label><label>Цвет<select id="pcaColor" class="ctrl"><option value="cluster">Кластер</option><option value="quality">QC</option><option value="outlier">Outlier score</option></select></label></div>
<div class="grid cols-2"><div class="card"><div id="pcaPlot" class="plot"></div></div><div class="card"><div id="pcaVariancePlot" class="plot"></div></div></div>
<div class="grid cols-2" style="margin-top:14px"><div class="card"><h3>Нагрузки выбранных компонент</h3><div id="loadingsTable"></div></div><div class="card"><h3>Параллельные координаты основных показателей</h3><div id="parallelPlot" class="plot tall"></div></div></div>
</section>

<section id="curves" class="tab">
<div class="page-title"><h2>Масштабные кривые</h2><div class="note">Рекомендуется выбирать не более 12 городов</div></div>
<div class="card"><div class="controls"><label>Кривая<select id="curveType" class="ctrl"><option value="box">Box-counting: N(ε)</option><option value="lacunarity">Лакунарность Λ(ε)</option><option value="beta0">β₀(r)</option><option value="beta1">β₁(r)</option><option value="giant">Гигантская компонента</option><option value="perimeter">Нормированная граница</option><option value="multifractal">Dq(q)</option><option value="height">Чувствительность 2,5D к высоте</option></select></label><label>Ось радиуса<select id="radiusMode" class="ctrl"><option value="physical">Физическая, м</option><option value="normalized">Нормированная ρ</option></select></label><label>Шкала X<select id="curveXScale" class="ctrl"><option value="linear">linear</option><option value="log">log</option></select></label><label>Шкала Y<select id="curveYScale" class="ctrl"><option value="linear">linear</option><option value="log">log</option></select></label></div><div id="curveNotice" class="selection-box"></div><div id="curvePlot" class="plot tall"></div></div>
</section>

<section id="compare" class="tab">
<div class="page-title"><h2>Сравнение городов</h2><div class="note">Показываются первые четыре отмеченных города</div></div><div id="compareGrid" class="compare-grid"></div>
</section>

<section id="table" class="tab">
<div class="page-title"><h2>Таблица и контроль качества</h2><div class="buttons"><button class="btn primary" id="exportCsvBtn">Экспорт выбранных CSV</button></div></div>
<div class="card"><div class="table-wrap"><table id="dataTable" class="data-table"></table></div></div>
<div class="card" style="margin-top:14px"><h3>Предупреждения и отказы</h3><div id="qcList"></div></div>
</section>
<div class="footer">Автономный отчёт. Данные и Plotly встроены в HTML; изображения хранятся в каталоге assets.</div>
</main></div>
<script id="atlas-data" type="application/json">__ATLAS_DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('atlas-data').textContent);
const metricMeta=Object.fromEntries(DATA.metrics.map(m=>[m.key,m]));
const cityBySlug=Object.fromEntries(DATA.cities.map(c=>[c.slug,c]));
const state={selected:new Set(DATA.cities.map(c=>c.slug)), brush:new Set(), tab:'overview', sortKey:'name', sortAsc:true};
const qualityColors={pass:'#2f7d46',pass_with_warnings:'#b07900',fail:'#b23b3b',unknown:'#6f7c88'};
const plotConfig={responsive:true,displaylogo:false,toImageButtonOptions:{format:'svg',filename:'urban_fractal_plot'}};
function el(id){return document.getElementById(id)}
function isNum(v){return typeof v==='number'&&Number.isFinite(v)}
function fmt(v,d=4){if(v===null||v===undefined||!Number.isFinite(Number(v)))return '—';let n=Number(v);if(Math.abs(n)>=1e6||Math.abs(n)>0&&Math.abs(n)<1e-4)return n.toExponential(3);return n.toLocaleString('ru-RU',{maximumFractionDigits:d})}
function values(cities,key){return cities.map(c=>c.metrics[key]).filter(isNum)}
function median(a){if(!a.length)return null;let b=[...a].sort((x,y)=>x-y),m=Math.floor(b.length/2);return b.length%2?b[m]:(b[m-1]+b[m])/2}
function mean(a){return a.length?a.reduce((s,x)=>s+x,0)/a.length:null}
function stdev(a){if(a.length<2)return null;let m=mean(a);return Math.sqrt(a.reduce((s,x)=>s+(x-m)**2,0)/(a.length-1))}
function percentileRanks(arr){let sorted=[...arr].sort((a,b)=>a-b);return arr.map(v=>sorted.length<2?50:100*sorted.findIndex(x=>x===v)/(sorted.length-1))}
function rank(a){let idx=a.map((v,i)=>[v,i]).sort((x,y)=>x[0]-y[0]),r=new Array(a.length);for(let i=0;i<idx.length;){let j=i;while(j+1<idx.length&&idx[j+1][0]===idx[i][0])j++;let avg=(i+j)/2+1;for(let k=i;k<=j;k++)r[idx[k][1]]=avg;i=j+1}return r}
function pearson(x,y){if(x.length<3)return null;let mx=mean(x),my=mean(y),num=0,dx=0,dy=0;for(let i=0;i<x.length;i++){let a=x[i]-mx,b=y[i]-my;num+=a*b;dx+=a*a;dy+=b*b}return dx&&dy?num/Math.sqrt(dx*dy):null}
function corrPair(cities,a,b,method){let x=[],y=[];cities.forEach(c=>{let xv=c.metrics[a],yv=c.metrics[b];if(isNum(xv)&&isNum(yv)){x.push(xv);y.push(yv)}});if(method==='spearman'){x=rank(x);y=rank(y)}return {r:pearson(x,y),n:x.length}}
function selectedCities(){return DATA.cities.filter(c=>state.selected.has(c.slug))}
function visibleInSidebar(c){let q=el('citySearch').value.trim().toLowerCase(),sf=el('statusFilter').value;return(!q||c.name.toLowerCase().includes(q)||c.slug.includes(q))&&(sf==='all'||c.quality_status===sf)}
function metricLabel(k){let m=metricMeta[k];return m?m.label+(m.unit?` [${m.unit}]`:''):k}
function plotLayout(title,xTitle,yTitle){return{title:{text:title,font:{size:15}},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{color:getComputedStyle(document.body).getPropertyValue('--ink').trim()},margin:{l:65,r:25,t:50,b:65},xaxis:{title:xTitle,gridcolor:getComputedStyle(document.body).getPropertyValue('--line').trim(),zerolinecolor:getComputedStyle(document.body).getPropertyValue('--line').trim()},yaxis:{title:yTitle,gridcolor:getComputedStyle(document.body).getPropertyValue('--line').trim(),zerolinecolor:getComputedStyle(document.body).getPropertyValue('--line').trim()},hoverlabel:{namelength:-1},legend:{orientation:'h',y:-.2}}}
function populateSelect(select,includeNone=false){if(includeNone)select.innerHTML='<option value="none">Постоянный</option>';else select.innerHTML='';let last='';DATA.metrics.forEach(m=>{if(m.group!==last){let g=document.createElement('optgroup');g.label=m.group;select.appendChild(g);last=m.group}let o=document.createElement('option');o.value=m.key;o.textContent=m.label+(m.unit?` [${m.unit}]`:'');select.lastElementChild.appendChild(o)})}
function renderCityList(){let list=el('cityList');list.innerHTML='';DATA.cities.filter(visibleInSidebar).forEach(c=>{let lab=document.createElement('label');lab.className='city-item';lab.innerHTML=`<input type="checkbox" ${state.selected.has(c.slug)?'checked':''} data-slug="${c.slug}"><span>${c.name}</span><span class="status ${c.quality_status}"></span>`;lab.querySelector('input').addEventListener('change',e=>{e.target.checked?state.selected.add(c.slug):state.selected.delete(c.slug);renderAll()});list.appendChild(lab)});el('selectedCount').textContent=`Выбрано ${state.selected.size} из ${DATA.cities.length}`}
function setSelection(slugs){state.selected=new Set(slugs);renderAll()}
function renderOverview(){let cs=selectedCities();el('kpiCities').textContent=cs.length;el('kpiEligible').textContent=cs.filter(c=>c.analysis_eligible).length;el('kpiArea').textContent=fmt(median(values(cs,'plan_area_km2')),2);el('kpiD').textContent=fmt(median(values(cs,'D_build')),4);
let counts={};cs.forEach(c=>counts[c.quality_status]=(counts[c.quality_status]||0)+1);Plotly.react('statusPlot',[{type:'pie',hole:.55,labels:Object.keys(counts),values:Object.values(counts),marker:{colors:Object.keys(counts).map(k=>qualityColors[k]||qualityColors.unknown)},textinfo:'label+value'}],{...plotLayout('','',''),margin:{l:15,r:15,t:10,b:10},showlegend:false},plotConfig);
Plotly.react('overviewDPlot',[{type:'histogram',x:values(cs,'D_build'),hovertemplate:'D=%{x}<br>Городов=%{y}<extra></extra>'}],plotLayout('',metricLabel('D_build'),'Число городов'),plotConfig);
let ac=cs.filter(c=>isNum(c.metrics.plan_area_km2)&&isNum(c.metrics.foreground_fraction));Plotly.react('areaCoveragePlot',[{type:'scatter',mode:'markers',x:ac.map(c=>c.metrics.plan_area_km2),y:ac.map(c=>100*c.metrics.foreground_fraction),text:ac.map(c=>c.name),customdata:ac.map(c=>c.slug),marker:{size:10},hovertemplate:'<b>%{text}</b><br>Площадь: %{x:.2f} км²<br>Застройка: %{y:.2f}%<extra></extra>'}],plotLayout('','Площадь области, км²','Доля застройки, %'),plotConfig);
let oc=cs.filter(c=>isNum(c.outlier_score)).sort((a,b)=>b.outlier_score-a.outlier_score).slice(0,20).reverse();Plotly.react('outlierPlot',[{type:'bar',orientation:'h',y:oc.map(c=>c.name),x:oc.map(c=>c.outlier_score),text:oc.map(c=>c.outlier_feature||''),hovertemplate:'<b>%{y}</b><br>score=%{x:.3f}<br>%{text}<extra></extra>'}],plotLayout('','Outlier score',''),plotConfig)}
function renderScatter(){let cs=selectedCities(),xk=el('xMetric').value,yk=el('yMetric').value,sk=el('sizeMetric').value,cm=el('colorMode').value,ck=el('colorMetric').value;cs=cs.filter(c=>isNum(c.metrics[xk])&&isNum(c.metrics[yk]));let sizes=sk==='none'?cs.map(()=>12):cs.map(c=>c.metrics[sk]);if(sk!=='none'){let finite=sizes.filter(isNum),lo=Math.min(...finite),hi=Math.max(...finite);sizes=sizes.map(v=>isNum(v)?8+22*(hi===lo?.5:(v-lo)/(hi-lo)):8)}
let marker={size:sizes,opacity:.82,line:{width:.6,color:'#fff'}},colorLabel='';if(cm==='quality'){marker.color=cs.map(c=>qualityColors[c.quality_status]||qualityColors.unknown);colorLabel='QC'}else if(cm==='cluster'){marker.color=cs.map(c=>c.cluster===null?-1:c.cluster);marker.colorscale='Turbo';marker.showscale=true;colorLabel='Кластер'}else{marker.color=cs.map(c=>c.metrics[ck]);marker.colorscale='Viridis';marker.showscale=true;colorLabel=metricLabel(ck)}
let lm=el('labelMode').value;let texts=cs.map(c=>lm==='all'?c.name:(lm==='outliers'&&isNum(c.outlier_score)&&c.outlier_score>=3?c.name:''));let tr={type:'scatter',mode:lm==='hover'?'markers':'markers+text',x:cs.map(c=>c.metrics[xk]),y:cs.map(c=>c.metrics[yk]),text:texts,textposition:'top center',customdata:cs.map(c=>[c.slug,c.name,c.quality_status,c.cluster,c.outlier_score]),marker,hovertemplate:'<b>%{customdata[1]}</b><br>'+metricLabel(xk)+': %{x}<br>'+metricLabel(yk)+': %{y}<br>QC: %{customdata[2]}<br>Кластер: %{customdata[3]}<extra></extra>'};let lay=plotLayout('',metricLabel(xk),metricLabel(yk));lay.dragmode='lasso';lay.xaxis.type=el('xScale').value;lay.yaxis.type=el('yScale').value;let xmin=parseFloat(el('xMin').value),xmax=parseFloat(el('xMax').value),ymin=parseFloat(el('yMin').value),ymax=parseFloat(el('yMax').value);if(Number.isFinite(xmin)||Number.isFinite(xmax))lay.xaxis.range=[Number.isFinite(xmin)?xmin:null,Number.isFinite(xmax)?xmax:null];if(Number.isFinite(ymin)||Number.isFinite(ymax))lay.yaxis.range=[Number.isFinite(ymin)?ymin:null,Number.isFinite(ymax)?ymax:null];Plotly.react('scatterPlot',[tr],lay,plotConfig).then(g=>{if(g.removeAllListeners){g.removeAllListeners('plotly_selected');g.removeAllListeners('plotly_deselect')}g.on('plotly_selected',ev=>{state.brush=new Set((ev?.points||[]).map(p=>p.customdata[0]));el('brushInfo').textContent=state.brush.size?`Выделено: ${state.brush.size}`:'Нет выделения'});g.on('plotly_deselect',()=>{state.brush.clear();el('brushInfo').textContent='Нет выделения'})});let pair=corrPair(cs,xk,yk,'spearman');el('scatterStats').innerHTML=`N = <b>${pair.n}</b>; ρ Спирмена = <b>${fmt(pair.r,3)}</b>; цвет: ${colorLabel}`}
function renderRanking(){let cs=selectedCities(),k=el('rankMetric').value,n=Math.max(1,parseInt(el('rankN').value)||30),asc=el('rankOrder').value==='asc',norm=el('rankNorm').value;let rows=cs.filter(c=>isNum(c.metrics[k])).map(c=>({c,v:c.metrics[k]}));let raw=rows.map(r=>r.v);if(norm==='percentile'){let p=percentileRanks(raw);rows.forEach((r,i)=>r.display=p[i])}else if(norm==='zscore'){let m=mean(raw),s=stdev(raw)||1;rows.forEach(r=>r.display=(r.v-m)/s)}else rows.forEach(r=>r.display=r.v);rows.sort((a,b)=>asc?a.display-b.display:b.display-a.display);rows=rows.slice(0,n).reverse();Plotly.react('rankPlot',[{type:'bar',orientation:'h',y:rows.map(r=>r.c.name),x:rows.map(r=>r.display),customdata:rows.map(r=>r.v),hovertemplate:'<b>%{y}</b><br>Отображаемое: %{x:.4g}<br>Исходное: %{customdata:.4g}<extra></extra>'}],plotLayout('',norm==='raw'?metricLabel(k):norm==='percentile'?'Процентиль':'z-score',''),plotConfig)}
function renderCorrelations(){let cs=selectedCities(),keys=[...el('corrMetrics').selectedOptions].map(o=>o.value);if(keys.length<2){el('corrTopPairs').innerHTML='<p class="muted">Выберите не менее двух признаков.</p>';Plotly.purge('corrPlot');return}let method=el('corrMethod').value,z=[],nmat=[],pairs=[];for(let i=0;i<keys.length;i++){let zr=[],nr=[];for(let j=0;j<keys.length;j++){let p=corrPair(cs,keys[i],keys[j],method);zr.push(p.r);nr.push(p.n);if(i<j&&p.r!==null)pairs.push({a:keys[i],b:keys[j],r:p.r,n:p.n})}z.push(zr);nmat.push(nr)}pairs.sort((a,b)=>Math.abs(b.r)-Math.abs(a.r));el('corrTopPairs').innerHTML=pairs.slice(0,10).map(p=>`<div>${metricMeta[p.a].label} ↔ ${metricMeta[p.b].label}: <b>${fmt(p.r,3)}</b> (N=${p.n})</div>`).join('');let labels=keys.map(k=>metricMeta[k].label);Plotly.react('corrPlot',[{type:'heatmap',z,x:labels,y:labels,zmin:-1,zmax:1,colorscale:'RdBu',reversescale:true,customdata:nmat,hovertemplate:'%{y}<br>%{x}<br>r=%{z:.3f}; N=%{customdata}<extra></extra>'}],{...plotLayout('', '', ''),margin:{l:190,r:25,t:25,b:190},xaxis:{tickangle:-45},yaxis:{autorange:'reversed'}},plotConfig).then(g=>{if(g.removeAllListeners)g.removeAllListeners('plotly_click');g.on('plotly_click',ev=>{let p=ev.points[0],a=keys[p.pointNumber[1]],b=keys[p.pointNumber[0]];el('xMetric').value=a;el('yMetric').value=b;activateTab('explore');renderScatter()})})}
function renderPCA(){let cs=selectedCities().filter(c=>Object.keys(c.pca).length),xk=el('pcX').value,yk=el('pcY').value,cm=el('pcaColor').value;cs=cs.filter(c=>isNum(c.pca[xk])&&isNum(c.pca[yk]));let marker={size:13,opacity:.85,line:{width:.7,color:'#fff'}};if(cm==='cluster'){marker.color=cs.map(c=>c.cluster===null?-1:c.cluster);marker.colorscale='Turbo';marker.showscale=true}else if(cm==='quality')marker.color=cs.map(c=>qualityColors[c.quality_status]||qualityColors.unknown);else{marker.color=cs.map(c=>c.outlier_score);marker.colorscale='Magma';marker.showscale=true}Plotly.react('pcaPlot',[{type:'scatter',mode:'markers+text',x:cs.map(c=>c.pca[xk]),y:cs.map(c=>c.pca[yk]),text:cs.map(c=>c.name),textposition:'top center',customdata:cs.map(c=>[c.quality_status,c.cluster,c.morphotype]),marker,hovertemplate:'<b>%{text}</b><br>'+xk+': %{x:.3f}<br>'+yk+': %{y:.3f}<br>Кластер: %{customdata[1]}<br>%{customdata[2]}<extra></extra>'}],plotLayout('',xk,yk),plotConfig);
let pv=DATA.pca_variance;let pcLabels=pv.map((r,i)=>r.component||r.PC||`PC${i+1}`),varKey=pv.length?Object.keys(pv[0]).find(k=>k.toLowerCase().includes('explained_variance_ratio')):null,cumKey=pv.length?Object.keys(pv[0]).find(k=>k.toLowerCase().includes('cumulative')):null;Plotly.react('pcaVariancePlot',varKey?[{type:'bar',x:pcLabels,y:pv.map(r=>100*r[varKey]),name:'Дисперсия'},{type:'scatter',mode:'lines+markers',x:pcLabels,y:pv.map(r=>cumKey?100*r[cumKey]:null),name:'Накопленная'}]:[],plotLayout('','Компонента','Дисперсия, %'),plotConfig);
renderLoadings(xk,yk);renderParallel()}
function renderLoadings(xk,yk){let rows=DATA.pca_loadings;if(!rows.length){el('loadingsTable').innerHTML='<p class="muted">Нагрузки отсутствуют.</p>';return}let featureKey=Object.keys(rows[0]).find(k=>['feature','metric','variable'].includes(k.toLowerCase()))||Object.keys(rows[0])[0];let arr=rows.filter(r=>isNum(r[xk])||isNum(r[yk])).sort((a,b)=>Math.max(Math.abs(b[xk]||0),Math.abs(b[yk]||0))-Math.max(Math.abs(a[xk]||0),Math.abs(a[yk]||0))).slice(0,15);el('loadingsTable').innerHTML='<table class="data-table"><tr><th>Признак</th><th>'+xk+'</th><th>'+yk+'</th></tr>'+arr.map(r=>`<tr><td>${r[featureKey]}</td><td>${fmt(r[xk],4)}</td><td>${fmt(r[yk],4)}</td></tr>`).join('')+'</table>'}
function renderParallel(){let cs=selectedCities(),keys=['D_build','lacunarity_mean','foreground_fraction','beta0_density_km2','beta1_density_km2','archipelago_index_harmonized','giant_component_radius_norm'].filter(k=>metricMeta[k]);let dims=keys.map(k=>({label:metricMeta[k].label,values:cs.map(c=>c.metrics[k])}));Plotly.react('parallelPlot',[{type:'parcoords',line:{color:cs.map(c=>c.cluster||0),colorscale:'Turbo',showscale:true},dimensions:dims}],{paper_bgcolor:'rgba(0,0,0,0)',font:{color:getComputedStyle(document.body).getPropertyValue('--ink').trim()},margin:{l:50,r:50,t:25,b:30}},plotConfig)}
function renderCurves(){let cs=selectedCities().slice(0,12),type=el('curveType').value,rmode=el('radiusMode').value,traces=[],xt='',yt='',defaultX='linear',defaultY='linear';cs.forEach(c=>{let rows=[];if(type==='box'){rows=DATA.curves[c.slug].box;traces.push({type:'scatter',mode:'lines+markers',name:c.name,x:rows.map(r=>r.scale_m),y:rows.map(r=>r.count_mean??r.count),hovertemplate:c.name+'<br>ε=%{x} м<br>N=%{y}<extra></extra>'});xt='Масштаб ε, м';yt='N(ε)';defaultX='log';defaultY='log'}else if(type==='lacunarity'){rows=DATA.curves[c.slug].lacunarity;traces.push({type:'scatter',mode:'lines+markers',name:c.name,x:rows.map(r=>r.window_size_m),y:rows.map(r=>r.lacunarity)});xt='Размер окна, м';yt='Λ';defaultX='log'}else if(['beta0','beta1','giant','perimeter'].includes(type)){rows=DATA.curves[c.slug].topology;let xkey=rmode==='normalized'?'radius_relative_to_characteristic_length':'radius_m',ykey={beta0:'beta0',beta1:'beta1',giant:'giant_fraction',perimeter:'perimeter_per_characteristic_length'}[type];traces.push({type:'scatter',mode:'lines+markers',name:c.name,x:rows.map(r=>r[xkey]),y:rows.map(r=>r[ykey])});xt=rmode==='normalized'?'Нормированный радиус ρ':'Радиус r, м';yt={beta0:'β₀',beta1:'β₁',giant:'Доля крупнейшей компоненты',perimeter:'P/L'}[type]}else if(type==='multifractal'){rows=DATA.curves[c.slug].multifractal;traces.push({type:'scatter',mode:'lines+markers',name:c.name,x:rows.map(r=>r.q),y:rows.map(r=>r.Dq),line:{dash:rows.some(r=>r.atlas_eligible===false)?'dot':'solid'}});xt='q';yt='Dq'}else if(type==='height'){rows=DATA.curves[c.slug].height;traces.push({type:'scatter',mode:'lines+markers',name:c.name,x:rows.map(r=>r.default_height_m),y:rows.map(r=>r.envelope_area_m2/1e6)});xt='Высота по умолчанию, м';yt='Площадь оболочки, км²'}});el('curveNotice').innerHTML=`Показано ${cs.length} из ${state.selected.size} выбранных городов${state.selected.size>12?'; остальные скрыты для читаемости':''}.`;let lay=plotLayout('',xt,yt);lay.xaxis.type=el('curveXScale').value||defaultX;lay.yaxis.type=el('curveYScale').value||defaultY;if(type==='box'){lay.xaxis.type=el('curveXScale').value==='linear'?'linear':'log';lay.yaxis.type=el('curveYScale').value==='linear'?'linear':'log'}Plotly.react('curvePlot',traces,lay,plotConfig)}
function renderCompare(){let cs=selectedCities().slice(0,4),grid=el('compareGrid');if(!cs.length){grid.innerHTML='<div class="card muted">Не выбран ни один город.</div>';return}grid.innerHTML=cs.map(c=>{let img=c.assets['building_mask.png']||c.assets['analysis_domain_mask.png'];let report=c.assets['auto_report.html'];let keys=['D_build','lacunarity_mean','plan_area_km2','foreground_fraction','beta0_density_km2','beta1_density_km2','archipelago_index_harmonized','spanning_radius_lr_norm'];return `<div class="card city-card"><h3>${c.name} <span class="badge">${c.quality_status}</span></h3>${img?`<img src="${img}" alt="${c.name}">`:''}<table>${keys.filter(k=>metricMeta[k]).map(k=>`<tr><td>${metricMeta[k].label}</td><td>${fmt(c.metrics[k])}</td></tr>`).join('')}</table><div class="buttons">${report?`<a class="btn" href="${report}" target="_blank">Полный отчёт</a>`:''}</div>${c.warnings.length?`<p class="warning"><b>Предупреждения:</b><br>${c.warnings.join('<br>')}</p>`:''}${c.failures.length?`<p class="failure"><b>Отказы:</b><br>${c.failures.join('<br>')}</p>`:''}</div>`}).join('')}
function renderTable(){let cs=selectedCities(),keys=DATA.core_table_keys;let sorted=[...cs].sort((a,b)=>{let av=state.sortKey==='name'?a.name:a.metrics[state.sortKey],bv=state.sortKey==='name'?b.name:b.metrics[state.sortKey];if(av===null)return 1;if(bv===null)return -1;if(typeof av==='string')return state.sortAsc?av.localeCompare(bv):bv.localeCompare(av);return state.sortAsc?av-bv:bv-av});let table=el('dataTable');table.innerHTML='<thead><tr><th data-key="name">Город</th><th>QC</th><th>Кластер</th>'+keys.map(k=>`<th data-key="${k}">${metricMeta[k]?.label||k}</th>`).join('')+'</tr></thead><tbody>'+sorted.map(c=>`<tr><td>${c.name}</td><td>${c.quality_status}</td><td>${c.cluster??'—'}</td>${keys.map(k=>`<td>${fmt(c.metrics[k])}</td>`).join('')}</tr>`).join('')+'</tbody>';table.querySelectorAll('th[data-key]').forEach(th=>th.addEventListener('click',()=>{let k=th.dataset.key;if(state.sortKey===k)state.sortAsc=!state.sortAsc;else{state.sortKey=k;state.sortAsc=true}renderTable()}));el('qcList').innerHTML=cs.filter(c=>c.warnings.length||c.failures.length||c.quality_status!=='pass').map(c=>`<div class="qc-row"><b>${c.name}</b> — <span class="badge">${c.quality_status}</span>${c.failures.length?`<div class="failure">${c.failures.join('; ')}</div>`:''}${c.warnings.length?`<div class="warning">${c.warnings.join('; ')}</div>`:''}</div>`).join('')||'<p class="muted">Для выбранных городов предупреждений нет.</p>'}
function exportCsv(){let cs=selectedCities(),keys=DATA.core_table_keys;let rows=[['slug','city','quality_status','cluster',...keys],...cs.map(c=>[c.slug,c.name,c.quality_status,c.cluster,...keys.map(k=>c.metrics[k])])];let csv=rows.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\n');downloadBlob(csv,'urban_fractal_selected.csv','text/csv;charset=utf-8')}
function downloadBlob(text,name,type){let a=document.createElement('a');a.href=URL.createObjectURL(new Blob([text],{type}));a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)}
function saveState(){let out={selected:[...state.selected],tab:state.tab,controls:{}};document.querySelectorAll('select,input[type=number]').forEach(x=>{if(x.id)out.controls[x.id]=x.value});downloadBlob(JSON.stringify(out,null,2),'urban_fractal_atlas_state.json','application/json')}
function loadState(file){let r=new FileReader();r.onload=()=>{try{let s=JSON.parse(r.result);if(Array.isArray(s.selected))state.selected=new Set(s.selected.filter(x=>cityBySlug[x]));Object.entries(s.controls||{}).forEach(([id,v])=>{if(el(id))el(id).value=v});activateTab(s.tab||'overview');renderAll()}catch(e){alert('Не удалось прочитать состояние: '+e.message)}};r.readAsText(file)}
function renderCurrentTab(){({overview:renderOverview,explore:()=>{renderScatter();renderRanking()},corr:renderCorrelations,pca:renderPCA,curves:renderCurves,compare:renderCompare,table:renderTable}[state.tab]||renderOverview)()}
function activateTab(id){state.tab=id;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.id===id));document.querySelectorAll('.tab-btn').forEach(x=>x.classList.toggle('active',x.dataset.tab===id));renderCurrentTab();setTimeout(()=>window.dispatchEvent(new Event('resize')),50)}
function renderAll(){renderCityList();renderCurrentTab()}
function init(){el('metaText').textContent=`${DATA.meta.city_count} городов; версия ${DATA.meta.software_versions.join(', ')||'—'}; растр ${DATA.meta.pixel_sizes_m.join(', ')||'—'} м`;['xMetric','yMetric','colorMetric','rankMetric'].forEach(id=>populateSelect(el(id)));populateSelect(el('sizeMetric'),true);el('xMetric').value='D_build';el('yMetric').value=metricMeta.lacunarity_mean?'lacunarity_mean':DATA.metrics[1].key;el('colorMetric').value='foreground_fraction';el('rankMetric').value='D_build';DATA.metrics.forEach(m=>{let o=document.createElement('option');o.value=m.key;o.textContent=`${m.group}: ${m.label}`;el('corrMetrics').appendChild(o)});['D_build','lacunarity_mean','plan_area_km2','foreground_fraction','beta0_density_km2','beta1_density_km2','archipelago_index_harmonized','spanning_radius_lr_norm'].forEach(k=>{let o=[...el('corrMetrics').options].find(x=>x.value===k);if(o)o.selected=true});let pcs=[...new Set(DATA.cities.flatMap(c=>Object.keys(c.pca)))].sort((a,b)=>parseInt(a.slice(2))-parseInt(b.slice(2)));pcs.forEach(pc=>{['pcX','pcY'].forEach(id=>{let o=document.createElement('option');o.value=pc;o.textContent=pc;el(id).appendChild(o)})});el('pcX').value=pcs[0]||'';el('pcY').value=pcs[1]||pcs[0]||'';
renderCityList();document.querySelectorAll('.tab-btn').forEach(b=>b.addEventListener('click',()=>activateTab(b.dataset.tab)));el('citySearch').addEventListener('input',renderCityList);el('statusFilter').addEventListener('change',renderCityList);el('allBtn').onclick=()=>setSelection(DATA.cities.filter(visibleInSidebar).map(c=>c.slug));el('noneBtn').onclick=()=>setSelection([]);el('invertBtn').onclick=()=>setSelection(DATA.cities.filter(c=>!state.selected.has(c.slug)).map(c=>c.slug));el('eligibleBtn').onclick=()=>setSelection(DATA.cities.filter(c=>c.analysis_eligible).map(c=>c.slug));el('qcBtn').onclick=()=>setSelection(DATA.cities.filter(c=>c.quality_status!=='fail').map(c=>c.slug));el('keepBrushBtn').onclick=()=>state.brush.size&&setSelection([...state.brush]);el('addBrushBtn').onclick=()=>{state.brush.forEach(x=>state.selected.add(x));renderAll()};el('removeBrushBtn').onclick=()=>{state.brush.forEach(x=>state.selected.delete(x));renderAll()};el('saveStateBtn').onclick=saveState;el('loadStateInput').onchange=e=>e.target.files[0]&&loadState(e.target.files[0]);el('themeBtn').onclick=()=>{document.body.classList.toggle('dark');el('themeBtn').textContent=document.body.classList.contains('dark')?'Светлая тема':'Тёмная тема';renderAll()};el('exportCsvBtn').onclick=exportCsv;
['xMetric','yMetric','sizeMetric','colorMode','colorMetric','xScale','yScale','labelMode','xMin','xMax','yMin','yMax'].forEach(id=>el(id).addEventListener('change',renderScatter));['rankMetric','rankOrder','rankN','rankNorm'].forEach(id=>el(id).addEventListener('change',renderRanking));['corrMetrics','corrMethod'].forEach(id=>el(id).addEventListener('change',renderCorrelations));el('corrCoreBtn').onclick=()=>{[...el('corrMetrics').options].forEach(o=>o.selected=['D_build','lacunarity_mean','plan_area_km2','foreground_fraction','beta0_density_km2','beta1_density_km2','archipelago_index_harmonized','spanning_radius_lr_norm'].includes(o.value));renderCorrelations()};el('corrAllBtn').onclick=()=>{[...el('corrMetrics').options].forEach(o=>o.selected=true);renderCorrelations()};el('corrNoneBtn').onclick=()=>{[...el('corrMetrics').options].forEach(o=>o.selected=false);renderCorrelations()};['pcX','pcY','pcaColor'].forEach(id=>el(id).addEventListener('change',renderPCA));['curveType','radiusMode','curveXScale','curveYScale'].forEach(id=>el(id).addEventListener('change',renderCurves));renderAll()}
init();
</script>
</body></html>'''


def build(
    source: Path,
    output: Path,
    copy_assets: bool = True,
    catalog_path: Path | None = None,
    names_path: Path | None = None,
) -> Path:
    source_root, results_root = normalize_results_root(source)
    output.mkdir(parents=True, exist_ok=True)
    payload = collect_payload(
        source_root,
        results_root,
        output,
        copy_assets,
        catalog_path=catalog_path,
        names_path=names_path,
    )
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("__PLOTLY_JS__", get_plotlyjs()).replace("__ATLAS_DATA__", data_json)
    index = output / "index.html"
    index.write_text(html, encoding="utf-8")
    (output / "atlas_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Каталог архива, results/ или каталог с final/")
    parser.add_argument("output", type=Path, help="Каталог создаваемого атласа")
    parser.add_argument("--no-copy-assets", action="store_true", help="Не копировать изображения и индивидуальные отчёты")
    parser.add_argument(
        "--catalog",
        type=Path,
        help="CSV-каталог городов; по умолчанию автоматически ищется configs/city_catalog_200.csv",
    )
    parser.add_argument(
        "--names-file",
        type=Path,
        help="Необязательный CSV/JSON со своими отображаемыми названиями по slug",
    )
    args = parser.parse_args()
    index = build(
        args.source,
        args.output,
        copy_assets=not args.no_copy_assets,
        catalog_path=args.catalog,
        names_path=args.names_file,
    )
    print(index)


if __name__ == "__main__":
    main()
