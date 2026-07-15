from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from make_city_files.download_approved_cities import (  # noqa: E402
    DEFAULT_ATTEMPTS_PER_ENDPOINT,
    DEFAULT_BOUNDARY_OVERRIDES_PATH,
    DEFAULT_MAX_BOUNDARY_AREA_KM2,
    DEFAULT_MAX_BOUNDARY_DIAGONAL_KM,
    DEFAULT_MAX_GEOCODER_RESULTS,
    City,
    configure_downloader,
    process_city,
)


def read_catalog(path: Path) -> list[City]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        required = {"subset", "slug", "name", "query", "morphotype"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Catalog {path} misses required columns: {sorted(missing)}"
            )

        cities = [
            City(
                subset=(row.get("subset") or "").strip(),
                slug=(row.get("slug") or "").strip(),
                name=(row.get("name") or "").strip(),
                query=(row.get("query") or "").strip(),
                morphotype=(row.get("morphotype") or "").strip(),
            )
            for row in reader
        ]

    return [city for city in cities if city.subset and city.slug and city.query]


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve validated city boundaries and download buildings/roads "
            "from OSMnx/Overpass."
        )
    )
    parser.add_argument(
        "--catalog",
        default="configs/city_catalog_200.csv",
    )
    parser.add_argument("--out", default="data/approved_cities")
    parser.add_argument(
        "--set",
        dest="subset",
        choices=["russia", "world", "all"],
        default="all",
    )
    parser.add_argument(
        "--cities",
        default=None,
        help="Comma-separated slugs to process.",
    )
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--roads", action="store_true")
    parser.add_argument(
        "--boundaries-only",
        action="store_true",
        help="Resolve and validate boundaries without Overpass downloads.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sleep", type=float, default=5.0)
    parser.add_argument("--list", action="store_true")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first failed city.",
    )
    parser.add_argument(
        "--boundary-overrides",
        default=str(DEFAULT_BOUNDARY_OVERRIDES_PATH),
        help="JSON map from city slug to exact OSM ID or per-city limits.",
    )
    parser.add_argument(
        "--max-boundary-area-km2",
        type=float,
        default=DEFAULT_MAX_BOUNDARY_AREA_KM2,
    )
    parser.add_argument(
        "--max-boundary-diagonal-km",
        type=float,
        default=DEFAULT_MAX_BOUNDARY_DIAGONAL_KM,
    )
    parser.add_argument(
        "--max-geocoder-results",
        type=int,
        default=DEFAULT_MAX_GEOCODER_RESULTS,
    )
    parser.add_argument(
        "--attempts-per-endpoint",
        type=int,
        default=DEFAULT_ATTEMPTS_PER_ENDPOINT,
    )
    parser.add_argument("--requests-timeout", type=int, default=300)
    parser.add_argument(
        "--cache-folder",
        default=None,
        help="Explicit OSMnx cache directory.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    configure_downloader(
        boundary_overrides=Path(args.boundary_overrides),
        max_boundary_area_km2=args.max_boundary_area_km2,
        max_boundary_diagonal_km=args.max_boundary_diagonal_km,
        max_geocoder_results=args.max_geocoder_results,
        attempts_per_endpoint=args.attempts_per_endpoint,
        requests_timeout=args.requests_timeout,
        cache_folder=Path(args.cache_folder) if args.cache_folder else None,
    )

    cities = read_catalog(Path(args.catalog))
    if args.subset != "all":
        cities = [city for city in cities if city.subset == args.subset]
    if args.cities:
        requested = {
            slug.strip() for slug in args.cities.split(",") if slug.strip()
        }
        cities = [city for city in cities if city.slug in requested]
    cities = cities[args.start :]
    if args.limit is not None:
        cities = cities[: args.limit]

    print(f"Selected cities: {len(cities)}")
    for index, city in enumerate(cities, 1):
        print(
            f"{index:03d}. {city.subset}/{city.slug} | "
            f"{city.name} | {city.query}"
        )
    if args.list:
        return 0

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    _write_json(
        root / "selected_catalog.json",
        [asdict(city) for city in cities],
    )

    failures: list[str] = []
    for city in cities:
        ok = process_city(
            city,
            root=root,
            roads=args.roads,
            overwrite=args.overwrite,
            sleep_s=args.sleep,
            boundaries_only=args.boundaries_only,
            fail_fast=args.fail_fast,
        )
        if not ok:
            failures.append(city.slug)

    failure_path = root / "failed_cities.txt"
    if failures:
        failure_path.write_text(
            "".join(f"{slug}\n" for slug in failures),
            encoding="utf-8",
        )
        print(f"Failed cities: {len(failures)}")
        print("Failure list:", failure_path)
        return 1

    failure_path.unlink(missing_ok=True)
    print("All selected cities completed successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
