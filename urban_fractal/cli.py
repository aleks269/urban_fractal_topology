from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import AnalysisConfig, analyze_city, analyze_resolution_sweep


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="urban-fractal",
        description="Compute multiscale fractal, lacunarity and compactness metrics for urban building morphology.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--city", help="Place name for OSM download, e.g. 'Saint Petersburg, Russia'. Requires osmnx.")
    src.add_argument("--buildings", help="Local vector file with building footprints: GeoJSON/GPKG/SHP.")
    p.add_argument("--boundary", help="Optional local vector file with city boundary.")
    p.add_argument("--out", default="results", help="Output directory.")
    p.add_argument("--pixel", type=float, default=25.0, help="Raster pixel size in meters for 2D analysis.")
    p.add_argument("--resolution-sweep", type=float, nargs="+", help="Run the same city at several raster pixel sizes in meters, e.g. --resolution-sweep 2 5 10 20 50.")
    p.add_argument("--resolution-sweep-continue-on-error", action="store_true", help="Do not abort the whole resolution sweep if one pixel size fails.")
    p.add_argument("--sweep-max-area-error", type=float, default=0.05, help="Maximum relative raster/vector building-area error for a sweep run to pass quality filtering.")
    p.add_argument("--sweep-min-r2", type=float, default=0.98, help="Minimum box-counting fit R² for a sweep run to pass quality filtering.")
    p.add_argument("--sweep-d-cv-threshold", type=float, default=0.05, help="Maximum coefficient of variation of D_build inside a stable resolution window.")
    p.add_argument("--sweep-rc-cv-threshold", type=float, default=0.10, help="Maximum coefficient of variation of rc_m inside a stable resolution window when topology is enabled.")
    p.add_argument("--floor-height", type=float, default=3.0, help="Meters per floor when only building:levels is available.")
    p.add_argument("--default-height", type=float, default=12.0, help="Default building height in meters when height/levels are absent.")
    p.add_argument("--roof-factor", type=float, default=1.0, help="Multiplier for roof area relative to footprint area.")
    p.add_argument("--buffer", type=float, default=0.0, help="Fallback boundary buffer around buildings, meters.")
    p.add_argument("--min-box-px", type=int, default=2, help="Smallest box size in pixels for box-counting.")
    p.add_argument("--max-box-fraction", type=float, default=0.25, help="Largest box size as fraction of min raster side.")
    p.add_argument("--min-scaling-points", type=int, default=4, help="Minimum points in automatically selected scaling window.")
    p.add_argument("--multifractal", action="store_true", help="Also compute a simple D_q spectrum for footprints.")
    p.add_argument("--topology", action="store_true", help="Compute multiscale Minkowski, Betti and percolation profiles for the building mask.")
    p.add_argument("--topology-radii", help="Comma-separated dilation radii in pixels, e.g. '0,1,2,4,8,16'. Overrides automatic radii.")
    p.add_argument("--topology-max-radius-fraction", type=float, default=0.05, help="Maximum topology dilation radius as fraction of min raster side.")
    p.add_argument("--topology-n-radii", type=int, default=18, help="Number of approximately logarithmic dilation radii for topology profiles.")
    p.add_argument("--topology-connectivity", type=int, choices=[1, 2], default=1, help="Connected-component rule: 1=4-neighbour, 2=8-neighbour.")
    p.add_argument("--giant-threshold", type=float, default=0.5, help="Largest-component fraction threshold for percolation radius rc.")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    topology_radii = None
    if args.topology_radii:
        topology_radii = tuple(int(x.strip()) for x in args.topology_radii.split(",") if x.strip())

    cfg = AnalysisConfig(
        city_name=args.city,
        buildings_path=args.buildings,
        boundary_path=args.boundary,
        output_dir=args.out,
        pixel_size_m=args.pixel,
        floor_height_m=args.floor_height,
        default_height_m=args.default_height,
        roof_factor=args.roof_factor,
        buffer_m=args.buffer,
        min_box_px=args.min_box_px,
        max_box_fraction=args.max_box_fraction,
        min_scaling_points=args.min_scaling_points,
        multifractal=args.multifractal,
        topology=args.topology,
        topology_radii_px=topology_radii,
        topology_max_radius_fraction=args.topology_max_radius_fraction,
        topology_n_radii=args.topology_n_radii,
        topology_connectivity=args.topology_connectivity,
        giant_threshold=args.giant_threshold,
    )
    if args.resolution_sweep:
        result = analyze_resolution_sweep(
            cfg,
            args.resolution_sweep,
            continue_on_error=args.resolution_sweep_continue_on_error,
            max_area_error_rel=args.sweep_max_area_error,
            min_r2=args.sweep_min_r2,
            d_cv_threshold=args.sweep_d_cv_threshold,
            rc_cv_threshold=args.sweep_rc_cv_threshold,
        )
    else:
        result = analyze_city(cfg)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nResults written to: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()
