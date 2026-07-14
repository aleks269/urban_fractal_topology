from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from urban_fractal import __version__


def read_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    required = {"subset", "slug", "name", "query"}
    missing = required.difference(rows[0].keys() if rows else set())
    if missing:
        raise ValueError(f"Catalog {path} misses required columns: {sorted(missing)}")
    return rows


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def nonempty(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def as_float(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit boundary-aware 25 m UrbanFractal results.")
    parser.add_argument("--catalog", default="configs/city_catalog_200.csv")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--results-root", required=True)
    parser.add_argument("--mode", default="final")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-area-error", type=float, default=0.05)
    parser.add_argument("--max-boundary-area-error", type=float, default=0.03)
    parser.add_argument("--min-fractal-r2", type=float, default=0.95)
    parser.add_argument("--min-fractal-points", type=int, default=6)
    parser.add_argument(
        "--max-fractal-offset-cv",
        "--max-fractal-offset-std",
        dest="max_fractal_offset_cv",
        type=float,
        default=0.05,
        help="Maximum coefficient of variation of D over grid origins. The old --...-std spelling is retained as a deprecated alias.",
    )
    parser.add_argument(
        "--max-fractal-loo-cv",
        "--max-fractal-loo-std",
        dest="max_fractal_loo_cv",
        type=float,
        default=0.05,
        help="Maximum leave-one-scale-out coefficient of variation of D. The old --...-std spelling is retained as a deprecated alias.",
    )
    parser.add_argument("--max-energy-error", type=float, default=1e-5)
    args = parser.parse_args()

    catalog = read_catalog(Path(args.catalog))
    data_root = Path(args.data_root)
    results_root = Path(args.results_root)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    for city in catalog:
        subset, slug = city["subset"].strip(), city["slug"].strip()
        data_dir = data_root / subset / slug
        result_dir = results_root / args.mode / subset / slug
        summary_path = result_dir / "summary.json"
        summary = read_json(summary_path)
        data_complete = nonempty(data_dir / "boundary.geojson") and nonempty(data_dir / "buildings.geojson")
        result_complete = nonempty(summary_path) and bool(summary)

        software = summary.get("software") or {}
        inp = summary.get("input") or {}
        raster = summary.get("raster_diagnostics") or {}
        fractal = summary.get("fractal_dimension_building_footprints") or {}
        topo = summary.get("topological_morphology_building_footprints") or {}
        transport = summary.get("two_phase_transport") or {}
        surfaces = summary.get("building_surfaces") or {}
        boundary = summary.get("planar_boundary") or {}
        qc = summary.get("quality_control") or {}

        area_error = as_float(raster.get("raster_area_error_rel"))
        boundary_error = as_float(raster.get("boundary_raster_area_error_rel"))
        r2 = as_float(fractal.get("r2"))
        n_points = as_float(fractal.get("n_points"))
        offset_std = as_float(fractal.get("grid_offset_std"))
        loo_std = as_float(fractal.get("leave_one_out_std"))
        offset_cv = as_float(fractal.get("grid_offset_cv"))
        loo_cv = as_float(fractal.get("leave_one_out_cv"))
        energy_error = as_float(transport.get("max_energy_identity_relative_error"))
        pixel = as_float(inp.get("pixel_size_m"))
        version_ok = software.get("version") == __version__
        all_touched_ok = inp.get("all_touched") is False
        boundary_fallback = bool(boundary.get("fallback_used"))

        failures: list[str] = []
        warnings: list[str] = []
        if not data_complete:
            failures.append("data_missing")
        if not result_complete:
            failures.append("result_missing")
        if result_complete:
            if not version_ok:
                failures.append("method_version_incompatible")
            if pixel is None or abs(pixel - 25.0) > 1e-9:
                failures.append("pixel_not_25m")
            if not all_touched_ok:
                failures.append("all_touched_not_false")
            if area_error is None or area_error > args.max_area_error:
                failures.append("building_raster_area_error")
            if boundary_error is None or boundary_error > args.max_boundary_area_error:
                failures.append("boundary_raster_area_error")
            if r2 is None or r2 < args.min_fractal_r2:
                failures.append("fractal_r2")
            if n_points is None or n_points < args.min_fractal_points:
                failures.append("fractal_points")
            if offset_cv is None:
                offset_cv = offset_std / abs(float(fractal.get("dimension"))) if offset_std is not None and as_float(fractal.get("dimension")) not in (None, 0) else None
            if loo_cv is None:
                loo_cv = loo_std / abs(float(fractal.get("dimension"))) if loo_std is not None and as_float(fractal.get("dimension")) not in (None, 0) else None
            if offset_cv is None or offset_cv > args.max_fractal_offset_cv:
                failures.append("fractal_grid_origin_instability")
            if loo_cv is None or loo_cv > args.max_fractal_loo_cv:
                failures.append("fractal_leave_one_out_instability")
            if boundary_fallback:
                failures.append("boundary_fallback")
            if not topo or "spanning_radius_lr_m" not in topo:
                failures.append("directional_spanning_missing")
            if not transport:
                failures.append("transport_missing")
            elif energy_error is None or energy_error > args.max_energy_error:
                failures.append("transport_energy_identity")

            known_area = as_float(surfaces.get("height_source_known_area_fraction"))
            if known_area is None or known_area < 0.5:
                warnings.append("2_5d_height_completeness_low")
            domain_fraction = as_float(raster.get("domain_fraction_of_bbox"))
            if domain_fraction is not None and domain_fraction < 0.2:
                warnings.append("complex_or_sparse_boundary_in_bbox")
            overlap = as_float(surfaces.get("footprint_overlap_fraction"))
            if overlap is not None and overlap > 0.05:
                warnings.append("building_footprint_overlap_high")
            if qc.get("osm_building_completeness") == "not_assessed_without_independent_reference":
                warnings.append("osm_completeness_unassessed")

        if failures:
            quality_status = "fail"
        elif warnings:
            quality_status = "pass_with_warnings"
        else:
            quality_status = "pass"

        error_text = ""
        if not result_complete and nonempty(result_dir / "batch_stderr.txt"):
            try:
                error_text = (result_dir / "batch_stderr.txt").read_text(encoding="utf-8")[-2000:]
            except Exception:
                pass

        rows.append({
            "subset": subset,
            "slug": slug,
            "name": city.get("name", ""),
            "data_complete": data_complete,
            "result_complete": result_complete,
            "software_version": software.get("version"),
            "required_version": __version__,
            "pixel_size_m": pixel,
            "all_touched": inp.get("all_touched"),
            "boundary_fallback": boundary_fallback,
            "domain_fraction_of_bbox": raster.get("domain_fraction_of_bbox"),
            "raster_area_error_rel": area_error,
            "boundary_raster_area_error_rel": boundary_error,
            "fractal_dimension": fractal.get("dimension"),
            "fractal_r2": r2,
            "fractal_n_points": n_points,
            "fractal_grid_offset_std": offset_std,
            "fractal_grid_offset_cv": offset_cv,
            "fractal_leave_one_out_std": loo_std,
            "fractal_leave_one_out_cv": loo_cv,
            "spanning_radius_lr_m": topo.get("spanning_radius_lr_m"),
            "spanning_radius_tb_m": topo.get("spanning_radius_tb_m"),
            "height_known_area_fraction": surfaces.get("height_source_known_area_fraction"),
            "transport_present": bool(transport),
            "transport_pixel_size_m": transport.get("analysis_pixel_size_m"),
            "transport_coarsening_factor": transport.get("coarsening_factor"),
            "transport_energy_identity_error": energy_error,
            "quality_status": quality_status,
            "failure_reasons": ";".join(failures),
            "warning_reasons": ";".join(warnings),
            "data_dir": str(data_dir),
            "result_dir": str(result_dir),
            "error": error_text,
        })

    fields = list(rows[0].keys()) if rows else ["status"]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["quality_status"]] = counts.get(row["quality_status"], 0) + 1
    summary_out = out.with_suffix(".json")
    summary_out.write_text(json.dumps({
        "catalog_cities": len(rows),
        "data_complete": sum(bool(r["data_complete"]) for r in rows),
        "result_complete": sum(bool(r["result_complete"]) for r in rows),
        "quality_status_counts": counts,
        "required_software_version": __version__,
        "thresholds": {
            "max_area_error": args.max_area_error,
            "max_boundary_area_error": args.max_boundary_area_error,
            "min_fractal_r2": args.min_fractal_r2,
            "min_fractal_points": args.min_fractal_points,
            "max_fractal_offset_cv": args.max_fractal_offset_cv,
            "max_fractal_loo_cv": args.max_fractal_loo_cv,
            "max_energy_error": args.max_energy_error,
        },
        "csv": str(out),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Catalog cities: {len(rows)}")
    print(f"Data complete: {sum(bool(r['data_complete']) for r in rows)}")
    print(f"Results complete: {sum(bool(r['result_complete']) for r in rows)}")
    for key in sorted(counts):
        print(f"{key}: {counts[key]}")
    print("Audit CSV:", out)
    print("Audit JSON:", summary_out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
