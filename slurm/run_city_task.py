from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from batch_tools.run_city_batch import (
    CityRecord,
    build_command,
    city_paths,
    output_dir,
    read_city_catalog,
    result_is_compatible,
)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def make_batch_args(python: str) -> SimpleNamespace:
    # These values exactly match the v0.4.0 final 25 m workflow.
    return SimpleNamespace(
        python=python,
        mode="final",
        pixel=25.0,
        floor_height=3.0,
        default_height=12.0,
        roof_factor=1.0,
        min_box_px=2,
        max_box_fraction=0.25,
        min_scaling_points=6,
        scaling_min_m=50.0,
        scaling_max_m=3200.0,
        lacunarity_min_domain_fraction=0.95,
        height_scenarios="9,12,15",
        topology=True,
        multifractal=True,
        topology_radii=None,
        all_touched=False,
        transport_phases="open_space,buildings",
        transport_contrasts="1000",
        transport_max_active_cells=250_000,
        topology_max_radius_fraction=0.25,
        topology_n_radii=18,
        topology_connectivity=1,
        giant_threshold=0.5,
        resolution_sweep=[10.0, 20.0, 50.0],
        resolution_sweep_continue_on_error=False,
        sweep_max_area_error=0.05,
        sweep_min_r2=0.95,
        sweep_d_cv_threshold=0.05,
        sweep_rc_cv_threshold=0.10,
    )


def select_city(catalog: Path, index: int | None, slug: str | None) -> tuple[int, CityRecord]:
    cities = read_city_catalog(catalog)
    if slug:
        for i, city in enumerate(cities):
            if city.slug == slug:
                return i, city
        raise SystemExit(f"City slug not found in catalog: {slug}")
    if index is None:
        raise SystemExit("Either --index or --slug is required")
    if not 0 <= index < len(cities):
        raise SystemExit(f"City index {index} is outside 0..{len(cities)-1}")
    return index, cities[index]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run exactly one UrbanFractal city, safely from a Slurm array task.")
    ap.add_argument("--catalog", required=True, type=Path)
    ap.add_argument("--data-root", required=True, type=Path)
    ap.add_argument("--results-root", required=True, type=Path)
    sel = ap.add_mutually_exclusive_group(required=True)
    sel.add_argument("--index", type=int, help="Zero-based row index in the catalog.")
    sel.add_argument("--slug", help="City slug from the catalog.")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--scratch", type=Path, default=None, help="Optional node-local scratch directory.")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ns = ap.parse_args()

    index, city = select_city(ns.catalog, ns.index, ns.slug)
    buildings, boundary = city_paths(ns.data_root, city)
    outdir = output_dir(ns.results_root, city, "final")
    summary = outdir / "summary.json"
    manifest = ns.results_root / "slurm_manifests" / f"{index:03d}_{city.subset}_{city.slug}.json"
    batch_args = make_batch_args(ns.python)

    record: dict = {
        "catalog_index_zero_based": index,
        "subset": city.subset,
        "slug": city.slug,
        "name": city.name,
        "query": city.query,
        "morphotype": city.morphotype,
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "hostname": os.uname().nodename,
        "status": "starting",
        "started_epoch": time.time(),
        "buildings": str(buildings),
        "boundary": str(boundary),
        "output": str(outdir),
    }
    atomic_json(manifest, record)

    if not buildings.exists() or not boundary.exists():
        record.update(status="missing_data", returncode=2)
        atomic_json(manifest, record)
        print(f"Missing input for {city.subset}/{city.slug}: {buildings} or {boundary}", file=sys.stderr)
        return 2

    if ns.skip_existing and summary.exists():
        try:
            existing = json.loads(summary.read_text(encoding="utf-8"))
            if result_is_compatible(existing, batch_args):
                record.update(status="skipped_compatible", returncode=0, finished_epoch=time.time())
                atomic_json(manifest, record)
                print(f"Compatible result already exists: {summary}")
                return 0
        except Exception as exc:  # corrupted/incomplete result must be recalculated
            print(f"Existing summary is not reusable: {exc}", file=sys.stderr)

    run_buildings = buildings
    run_boundary = boundary
    if ns.scratch is not None:
        local = ns.scratch / f"urban_fractal_{index:03d}_{city.slug}"
        local.mkdir(parents=True, exist_ok=True)
        run_buildings = local / "buildings.geojson"
        run_boundary = local / "boundary.geojson"
        shutil.copy2(buildings, run_buildings)
        shutil.copy2(boundary, run_boundary)
        record["scratch"] = str(local)
        atomic_json(manifest, record)

    cmd = build_command(batch_args, city, run_buildings, run_boundary, outdir)
    record["command"] = cmd
    atomic_json(manifest, record)
    print(f"[{index:03d}] {city.subset}/{city.slug} | {city.name}")
    print("Command:", " ".join(cmd))

    if ns.dry_run:
        record.update(status="dry_run", returncode=0, finished_epoch=time.time())
        atomic_json(manifest, record)
        return 0

    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    proc = subprocess.run(cmd, check=False)
    elapsed = time.time() - t0
    record.update(
        status="ok" if proc.returncode == 0 else "error",
        returncode=proc.returncode,
        duration_s=round(elapsed, 3),
        finished_epoch=time.time(),
        summary_exists=summary.exists(),
    )
    atomic_json(manifest, record)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
