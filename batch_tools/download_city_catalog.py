from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Make repository root importable when running the file directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from make_city_files.download_approved_cities import City, process_city  # noqa: E402


def read_catalog(path: Path) -> list[City]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"subset", "slug", "name", "query", "morphotype"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Catalog {path} misses required columns: {sorted(missing)}")
        cities: list[City] = []
        for row in reader:
            cities.append(
                City(
                    subset=(row.get("subset") or "").strip(),
                    slug=(row.get("slug") or "").strip(),
                    name=(row.get("name") or "").strip(),
                    query=(row.get("query") or "").strip(),
                    morphotype=(row.get("morphotype") or "").strip(),
                )
            )
    return [c for c in cities if c.subset and c.slug and c.query]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download cities from a CSV catalog using OSMnx/Overpass.")
    parser.add_argument("--catalog", default="configs/city_catalog_100.csv")
    parser.add_argument("--out", default="data/approved_cities")
    parser.add_argument("--set", dest="subset", choices=["russia", "world", "all"], default="all")
    parser.add_argument("--cities", default=None, help="Comma-separated slugs to download.")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--roads", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--sleep", type=float, default=5.0)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    cities = read_catalog(Path(args.catalog))
    if args.subset != "all":
        cities = [c for c in cities if c.subset == args.subset]
    if args.cities:
        wanted = {s.strip() for s in args.cities.split(",") if s.strip()}
        cities = [c for c in cities if c.slug in wanted]
    cities = cities[args.start:]
    if args.limit is not None:
        cities = cities[: args.limit]

    print(f"Selected cities: {len(cities)}")
    for i, city in enumerate(cities, 1):
        print(f"{i:03d}. {city.subset}/{city.slug} | {city.name} | {city.query}")
    if args.list:
        return 0

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    for city in cities:
        process_city(city, root=root, roads=args.roads, overwrite=args.overwrite, sleep_s=args.sleep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
