from __future__ import annotations

import argparse
import csv
import json
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from urban_fractal import __version__


@dataclass
class CityRecord:
    subset: str
    slug: str
    name: str
    query: str
    morphotype: str = ""


def read_city_catalog(path: Path) -> list[CityRecord]:
    """Read CSV catalog with columns: subset, slug, name, query, morphotype."""
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"subset", "slug", "name", "query"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Catalog {path} misses required columns: {sorted(missing)}")
        rows: list[CityRecord] = []
        for row in reader:
            rows.append(
                CityRecord(
                    subset=(row.get("subset") or "").strip(),
                    slug=(row.get("slug") or "").strip(),
                    name=(row.get("name") or "").strip(),
                    query=(row.get("query") or "").strip(),
                    morphotype=(row.get("morphotype") or "").strip(),
                )
            )
    return [r for r in rows if r.subset and r.slug and r.name and r.query]


def filter_cities(
    cities: list[CityRecord],
    subset: str,
    city_slugs: str | None,
    start: int,
    limit: int | None,
) -> list[CityRecord]:
    if subset != "all":
        cities = [c for c in cities if c.subset == subset]
    if city_slugs:
        selected = {s.strip() for s in city_slugs.split(",") if s.strip()}
        cities = [c for c in cities if c.slug in selected]
    cities = cities[start:]
    if limit is not None:
        cities = cities[:limit]
    return cities


def city_paths(data_root: Path, city: CityRecord) -> tuple[Path, Path]:
    city_dir = data_root / city.subset / city.slug
    return city_dir / "buildings.geojson", city_dir / "boundary.geojson"


def output_dir(results_root: Path, city: CityRecord, mode: str) -> Path:
    return results_root / mode / city.subset / city.slug


def result_is_compatible(existing: dict, args: argparse.Namespace) -> bool:
    """Return True only when an existing result matches the requested method.

    Version equality alone is insufficient: a result made with another pixel
    size, rasterization rule or disabled transport block must not be silently
    reused by the fixed 25 m final workflow.
    """
    if (existing.get("software") or {}).get("version") != __version__:
        return False
    if args.mode == "sweep":
        rows = existing.get("resolutions") or []
        got = sorted(float(r.get("pixel_size_m")) for r in rows if isinstance(r, dict) and r.get("pixel_size_m") is not None)
        want = sorted(float(x) for x in args.resolution_sweep)
        return len(got) == len(want) and all(abs(a - b) <= 1e-9 for a, b in zip(got, want))

    inp = existing.get("input") or {}
    try:
        if abs(float(inp.get("pixel_size_m")) - float(args.pixel)) > 1e-9:
            return False
    except (TypeError, ValueError):
        return False
    if bool(inp.get("all_touched")) != bool(args.all_touched):
        return False
    checks = {
        "min_scaling_points": int(args.min_scaling_points),
        "scaling_scale_min_m": float(args.scaling_min_m),
        "scaling_scale_max_m": float(args.scaling_max_m),
        "topology_max_radius_fraction": float(args.topology_max_radius_fraction),
        "topology_n_radii": int(args.topology_n_radii),
        "topology_connectivity": int(args.topology_connectivity),
        "giant_threshold": float(args.giant_threshold),
    }
    for key, wanted in checks.items():
        try:
            if abs(float(inp.get(key)) - float(wanted)) > 1e-12:
                return False
        except (TypeError, ValueError):
            return False
    if args.mode in {"topology", "final"} and inp.get("topology") is not True:
        return False
    if args.mode == "final":
        if inp.get("multifractal") is not True or inp.get("transport") is not True:
            return False
        phases = [x.strip() for x in str(args.transport_phases).split(",") if x.strip()]
        got_phases = [str(x) for x in (inp.get("transport_phases") or [])]
        if phases != got_phases:
            return False
        wanted_contrasts = [float(x.strip()) for x in str(args.transport_contrasts).split(",") if x.strip()]
        got_contrasts = [float(x) for x in (inp.get("transport_contrasts") or [])]
        if len(wanted_contrasts) != len(got_contrasts) or any(abs(a - b) > 1e-12 for a, b in zip(wanted_contrasts, got_contrasts)):
            return False
        try:
            if int(inp.get("transport_max_active_cells")) != int(args.transport_max_active_cells):
                return False
        except (TypeError, ValueError):
            return False
    return True


def build_command(args: argparse.Namespace, city: CityRecord, buildings: Path, boundary: Path, outdir: Path) -> list[str]:
    # Use module invocation so editable installs and local source trees both work.
    cmd = [
        args.python,
        "-m",
        "urban_fractal.cli",
        "--buildings",
        str(buildings),
        "--boundary",
        str(boundary),
        "--out",
        str(outdir),
        "--floor-height",
        str(args.floor_height),
        "--default-height",
        str(args.default_height),
        "--roof-factor",
        str(args.roof_factor),
        "--min-box-px",
        str(args.min_box_px),
        "--max-box-fraction",
        str(args.max_box_fraction),
        "--min-scaling-points",
        str(args.min_scaling_points),
        "--scaling-min-m",
        str(args.scaling_min_m),
        "--scaling-max-m",
        str(args.scaling_max_m),
        "--lacunarity-min-domain-fraction",
        str(args.lacunarity_min_domain_fraction),
        "--height-scenarios",
        args.height_scenarios,
    ]

    if args.mode == "quick":
        cmd += ["--pixel", str(args.pixel)]
        if args.topology:
            cmd += ["--topology"]
    elif args.mode == "topology":
        cmd += ["--pixel", str(args.pixel), "--topology"]
    elif args.mode == "sweep":
        cmd += ["--resolution-sweep", *[str(x) for x in args.resolution_sweep], "--topology"]
        if args.resolution_sweep_continue_on_error:
            cmd += ["--resolution-sweep-continue-on-error"]
        cmd += [
            "--sweep-max-area-error",
            str(args.sweep_max_area_error),
            "--sweep-min-r2",
            str(args.sweep_min_r2),
            "--sweep-d-cv-threshold",
            str(args.sweep_d_cv_threshold),
            "--sweep-rc-cv-threshold",
            str(args.sweep_rc_cv_threshold),
        ]
    elif args.mode == "final":
        cmd += ["--pixel", str(args.pixel), "--topology", "--multifractal", "--transport"]
    else:
        raise ValueError(f"Unknown mode: {args.mode}")

    if args.multifractal and "--multifractal" not in cmd:
        cmd += ["--multifractal"]
    if args.topology_radii:
        cmd += ["--topology-radii", args.topology_radii]
    if args.all_touched:
        cmd += ["--all-touched"]
    cmd += [
        "--transport-phases",
        args.transport_phases,
        "--transport-contrasts",
        args.transport_contrasts,
        "--transport-max-active-cells",
        str(args.transport_max_active_cells),
        "--topology-max-radius-fraction",
        str(args.topology_max_radius_fraction),
        "--topology-n-radii",
        str(args.topology_n_radii),
        "--topology-connectivity",
        str(args.topology_connectivity),
        "--giant-threshold",
        str(args.giant_threshold),
    ]
    return cmd


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    if rows:
        csv_path = path.with_suffix(".csv")
        fields = sorted({key for row in rows for key in row.keys()})
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run UrbanFractal analysis for a city catalog already downloaded to GeoJSON files."
    )
    parser.add_argument("--catalog", default="configs/city_catalog_100.csv", help="CSV catalog of cities.")
    parser.add_argument("--data-root", default="data/approved_cities", help="Root containing subset/slug/buildings.geojson and boundary.geojson.")
    parser.add_argument("--results-root", default="results/batch_100", help="Root for batch analysis results.")
    parser.add_argument("--set", dest="subset", choices=["russia", "world", "all"], default="all")
    parser.add_argument("--cities", default=None, help="Comma-separated slugs to run.")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--mode", choices=["quick", "topology", "sweep", "final"], default="quick")
    parser.add_argument("--pixel", type=float, default=25.0, help="Pixel size for quick/topology/final modes.")
    parser.add_argument("--resolution-sweep", type=float, nargs="+", default=[10.0, 20.0, 50.0], help="Pixel sizes for sweep mode.")
    parser.add_argument("--topology", action="store_true", help="Add topology to quick mode.")
    parser.add_argument("--multifractal", action="store_true", help="Add multifractal spectrum when supported by selected mode.")
    parser.add_argument("--resolution-sweep-continue-on-error", action="store_true")
    parser.add_argument("--sweep-max-area-error", type=float, default=0.05)
    parser.add_argument("--sweep-min-r2", type=float, default=0.98)
    parser.add_argument("--sweep-d-cv-threshold", type=float, default=0.05)
    parser.add_argument("--sweep-rc-cv-threshold", type=float, default=0.10)
    parser.add_argument("--floor-height", type=float, default=3.0)
    parser.add_argument("--default-height", type=float, default=12.0)
    parser.add_argument("--roof-factor", type=float, default=1.0)
    parser.add_argument("--min-box-px", type=int, default=2)
    parser.add_argument("--max-box-fraction", type=float, default=0.25)
    parser.add_argument("--min-scaling-points", type=int, default=6)
    parser.add_argument("--scaling-min-m", type=float, default=50.0)
    parser.add_argument("--scaling-max-m", type=float, default=3200.0)
    parser.add_argument("--lacunarity-min-domain-fraction", type=float, default=0.95)
    parser.add_argument("--height-scenarios", default="9,12,15")
    parser.add_argument("--transport-phases", default="open_space,buildings")
    parser.add_argument("--transport-contrasts", default="1000")
    parser.add_argument("--transport-max-active-cells", type=int, default=250000)
    parser.add_argument("--topology-radii", default=None)
    parser.add_argument("--topology-max-radius-fraction", type=float, default=0.25)
    parser.add_argument("--topology-n-radii", type=int, default=18)
    parser.add_argument("--topology-connectivity", type=int, choices=[1, 2], default=1)
    parser.add_argument("--giant-threshold", type=float, default=0.5)
    parser.add_argument("--all-touched", action="store_true", help="Use any-touch rasterization instead of the default pixel-center rule.")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-existing", action="store_true", help="Skip city if expected summary already exists.")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue if one city fails.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands but do not execute.")
    args = parser.parse_args(argv)

    catalog_path = Path(args.catalog)
    data_root = Path(args.data_root)
    results_root = Path(args.results_root)
    cities = filter_cities(read_city_catalog(catalog_path), args.subset, args.cities, args.start, args.limit)
    results_root.mkdir(parents=True, exist_ok=True)

    print(f"Selected cities: {len(cities)}")
    manifest_rows: list[dict] = []

    for idx, city in enumerate(cities, 1):
        buildings, boundary = city_paths(data_root, city)
        outdir = output_dir(results_root, city, args.mode)
        expected = outdir / ("resolution_sweep_summary.json" if args.mode == "sweep" else "summary.json")
        row = {
            **asdict(city),
            "index": idx,
            "mode": args.mode,
            "buildings": str(buildings),
            "boundary": str(boundary),
            "outdir": str(outdir),
            "status": "pending",
            "returncode": None,
            "duration_s": None,
        }

        print("\n" + "=" * 80)
        print(f"{idx:03d}/{len(cities):03d} {city.subset}/{city.slug} | {city.name}")
        print("=" * 80)

        if not buildings.exists() or not boundary.exists():
            row["status"] = "missing_data"
            row["error"] = "buildings.geojson or boundary.geojson not found"
            print("MISSING DATA:", buildings, boundary)
            manifest_rows.append(row)
            if not args.continue_on_error:
                write_manifest(results_root / f"batch_manifest_{args.mode}.json", manifest_rows)
                return 2
            continue

        if args.skip_existing and expected.exists():
            compatible = False
            try:
                existing = json.loads(expected.read_text(encoding="utf-8"))
                compatible = result_is_compatible(existing, args)
            except Exception:
                compatible = False
            if compatible:
                row["status"] = "skipped_existing"
                print("SKIP compatible existing result:", expected)
                manifest_rows.append(row)
                continue
            print(f"RECALCULATE incompatible result (required method/version {__version__}):", expected)

        cmd = build_command(args, city, buildings, boundary, outdir)
        row["command"] = " ".join(shlex.quote(x) for x in cmd)
        print(row["command"])

        if args.dry_run:
            row["status"] = "dry_run"
            manifest_rows.append(row)
            continue

        outdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        proc = subprocess.run(cmd, text=True, capture_output=True)
        dt = time.time() - t0
        row["duration_s"] = round(dt, 3)
        row["returncode"] = proc.returncode
        (outdir / "batch_stdout.txt").write_text(proc.stdout, encoding="utf-8")
        (outdir / "batch_stderr.txt").write_text(proc.stderr, encoding="utf-8")
        if proc.returncode == 0:
            row["status"] = "ok"
            print(f"OK in {dt:.1f} s")
        else:
            row["status"] = "error"
            row["error"] = (proc.stderr or proc.stdout)[-2000:]
            print(f"ERROR returncode={proc.returncode}")
            if not args.continue_on_error:
                manifest_rows.append(row)
                write_manifest(results_root / f"batch_manifest_{args.mode}.json", manifest_rows)
                return proc.returncode
        manifest_rows.append(row)
        write_manifest(results_root / f"batch_manifest_{args.mode}.json", manifest_rows)

    write_manifest(results_root / f"batch_manifest_{args.mode}.json", manifest_rows)
    print("\nBatch manifest written:", results_root / f"batch_manifest_{args.mode}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
