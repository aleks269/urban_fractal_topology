from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import AnalysisConfig, analyze_city, analyze_resolution_sweep


def _csv_floats(text: str) -> tuple[float, ...]:
    values = tuple(float(x.strip()) for x in text.split(",") if x.strip())
    if not values:
        raise argparse.ArgumentTypeError("at least one numeric value is required")
    return values


def _csv_strings(text: str) -> tuple[str, ...]:
    values = tuple(x.strip() for x in text.split(",") if x.strip())
    if not values:
        raise argparse.ArgumentTypeError("at least one value is required")
    return values


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="urban-fractal",
        description="Boundary-aware urban morphology, topology, 2.5D envelope and two-phase transport analysis.",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--city", help="Place name for OSM download. Requires osmnx.")
    src.add_argument("--buildings", help="Local vector file with building footprints.")
    p.add_argument("--boundary", help="Local vector file with the analysis boundary.")
    p.add_argument("--out", default="results")
    p.add_argument("--pixel", type=float, default=25.0)
    p.add_argument("--resolution-sweep", type=float, nargs="+")
    p.add_argument("--resolution-sweep-continue-on-error", action="store_true")
    p.add_argument("--sweep-max-area-error", type=float, default=0.05)
    p.add_argument("--sweep-min-r2", type=float, default=0.95)
    p.add_argument("--sweep-d-cv-threshold", type=float, default=0.05)
    p.add_argument("--sweep-rc-cv-threshold", type=float, default=0.10)

    p.add_argument("--floor-height", type=float, default=3.0)
    p.add_argument("--default-height", type=float, default=12.0)
    p.add_argument("--height-scenarios", type=_csv_floats, default=(9.0, 12.0, 15.0))
    p.add_argument("--roof-factor", type=float, default=1.0)
    p.add_argument("--buffer", type=float, default=0.0)

    p.add_argument("--min-box-px", type=int, default=2)
    p.add_argument("--max-box-fraction", type=float, default=0.25)
    p.add_argument("--min-scaling-points", type=int, default=6)
    p.add_argument("--scaling-min-m", type=float, default=50.0)
    p.add_argument("--scaling-max-m", type=float, default=3200.0)
    p.add_argument("--lacunarity-min-domain-fraction", type=float, default=0.95)

    p.add_argument("--multifractal", action="store_true")
    p.add_argument("--topology", action="store_true")
    p.add_argument("--topology-radii", help="Comma-separated dilation radii in pixels.")
    p.add_argument("--topology-max-radius-fraction", type=float, default=0.25)
    p.add_argument("--topology-n-radii", type=int, default=18)
    p.add_argument("--topology-connectivity", type=int, choices=[1, 2], default=1)
    p.add_argument("--giant-threshold", type=float, default=0.5)

    p.add_argument("--transport", action="store_true")
    p.add_argument("--transport-phases", type=_csv_strings, default=("open_space", "buildings"))
    p.add_argument("--transport-contrasts", type=_csv_floats, default=(1000.0,))
    p.add_argument("--transport-max-active-cells", type=int, default=250_000)

    p.add_argument(
        "--all-touched",
        action="store_true",
        help="Burn all touched building pixels. Not recommended; pixel-centre inclusion is the default.",
    )
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    topology_radii = None
    if args.topology_radii:
        topology_radii = tuple(int(x.strip()) for x in args.topology_radii.split(",") if x.strip())
    bad_phases = set(args.transport_phases).difference({"open_space", "buildings"})
    if bad_phases:
        raise SystemExit(f"Unsupported transport phases: {sorted(bad_phases)}")

    cfg = AnalysisConfig(
        city_name=args.city,
        buildings_path=args.buildings,
        boundary_path=args.boundary,
        output_dir=args.out,
        pixel_size_m=args.pixel,
        floor_height_m=args.floor_height,
        default_height_m=args.default_height,
        height_scenarios_m=tuple(args.height_scenarios),
        roof_factor=args.roof_factor,
        buffer_m=args.buffer,
        min_box_px=args.min_box_px,
        max_box_fraction=args.max_box_fraction,
        min_scaling_points=args.min_scaling_points,
        scaling_scale_min_m=args.scaling_min_m,
        scaling_scale_max_m=args.scaling_max_m,
        lacunarity_min_domain_fraction=args.lacunarity_min_domain_fraction,
        multifractal=args.multifractal,
        topology=args.topology,
        topology_radii_px=topology_radii,
        topology_max_radius_fraction=args.topology_max_radius_fraction,
        topology_n_radii=args.topology_n_radii,
        topology_connectivity=args.topology_connectivity,
        giant_threshold=args.giant_threshold,
        all_touched=args.all_touched,
        transport=args.transport,
        transport_phases=tuple(args.transport_phases),
        transport_contrasts=tuple(args.transport_contrasts),
        transport_max_active_cells=args.transport_max_active_cells,
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
