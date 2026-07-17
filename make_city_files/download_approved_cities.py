from __future__ import annotations

import gc
import json
import math
import os
import re
import time
import traceback
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import geopandas as gpd
import osmnx as ox
import pandas as pd


ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.requests_timeout = 300
ox.settings.http_user_agent = (
    "urban-fractal-topology/0.4.2 "
    "(https://github.com/aleks269/urban_fractal_topology)"
)
ox.settings.http_referer = (
    "https://github.com/aleks269/urban_fractal_topology"
)

if os.environ.get("URBAN_FRACTAL_SSL_NO_VERIFY") == "1":
    print(
        "WARNING: TLS certificate verification is disabled by "
        "URBAN_FRACTAL_SSL_NO_VERIFY=1"
    )
    ox.settings.requests_kwargs = {
        **ox.settings.requests_kwargs,
        "verify": False,
    }

# Base endpoint and whether OSMnx should poll its /status endpoint.
# VK Maps and Private.coffee publicly operate without rate limiting.
OVERPASS_ENDPOINTS = (
    ("https://maps.mail.ru/osm/tools/overpass/api", False),
    ("https://overpass.private.coffee/api", False),
    ("https://overpass-api.de/api", True),
)

DEFAULT_MAX_BOUNDARY_AREA_KM2 = float(
    os.environ.get("URBAN_FRACTAL_MAX_BOUNDARY_AREA_KM2", "10000")
)
DEFAULT_MAX_BOUNDARY_DIAGONAL_KM = float(
    os.environ.get("URBAN_FRACTAL_MAX_BOUNDARY_DIAGONAL_KM", "300")
)
DEFAULT_MAX_GEOCODER_RESULTS = int(
    os.environ.get("URBAN_FRACTAL_MAX_GEOCODER_RESULTS", "8")
)
DEFAULT_ATTEMPTS_PER_ENDPOINT = int(
    os.environ.get("URBAN_FRACTAL_ATTEMPTS_PER_ENDPOINT", "2")
)
DEFAULT_BOUNDARY_OVERRIDES_PATH = Path(
    os.environ.get(
        "URBAN_FRACTAL_BOUNDARY_OVERRIDES",
        str(Path(__file__).with_name("boundary_osm_ids.json")),
    )
)

MAX_BOUNDARY_AREA_KM2 = DEFAULT_MAX_BOUNDARY_AREA_KM2
MAX_BOUNDARY_DIAGONAL_KM = DEFAULT_MAX_BOUNDARY_DIAGONAL_KM
MAX_GEOCODER_RESULTS = DEFAULT_MAX_GEOCODER_RESULTS
ATTEMPTS_PER_ENDPOINT = DEFAULT_ATTEMPTS_PER_ENDPOINT
BOUNDARY_OVERRIDES_PATH = DEFAULT_BOUNDARY_OVERRIDES_PATH
BOUNDARY_OVERRIDES: dict[str, object] = {}


@dataclass(frozen=True)
class City:
    subset: str
    slug: str
    name: str
    query: str
    morphotype: str


def configure_downloader(
    *,
    boundary_overrides: Path | None = None,
    max_boundary_area_km2: float | None = None,
    max_boundary_diagonal_km: float | None = None,
    max_geocoder_results: int | None = None,
    attempts_per_endpoint: int | None = None,
    requests_timeout: int | None = None,
    cache_folder: Path | None = None,
) -> None:
    """Configure downloader behavior for the current process."""

    global ATTEMPTS_PER_ENDPOINT
    global BOUNDARY_OVERRIDES
    global BOUNDARY_OVERRIDES_PATH
    global MAX_BOUNDARY_AREA_KM2
    global MAX_BOUNDARY_DIAGONAL_KM
    global MAX_GEOCODER_RESULTS

    if boundary_overrides is not None:
        BOUNDARY_OVERRIDES_PATH = Path(boundary_overrides)
    BOUNDARY_OVERRIDES = _load_boundary_overrides(BOUNDARY_OVERRIDES_PATH)

    if max_boundary_area_km2 is not None:
        MAX_BOUNDARY_AREA_KM2 = float(max_boundary_area_km2)
    if max_boundary_diagonal_km is not None:
        MAX_BOUNDARY_DIAGONAL_KM = float(max_boundary_diagonal_km)
    if max_geocoder_results is not None:
        MAX_GEOCODER_RESULTS = int(max_geocoder_results)
    if attempts_per_endpoint is not None:
        ATTEMPTS_PER_ENDPOINT = int(attempts_per_endpoint)
    if requests_timeout is not None:
        ox.settings.requests_timeout = int(requests_timeout)
    if cache_folder is not None:
        ox.settings.cache_folder = Path(cache_folder)


def stringify_problem_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    for column in gdf.columns:
        if column == "geometry":
            continue
        if gdf[column].dtype == "object":
            gdf[column] = gdf[column].apply(
                lambda value: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict, tuple, set))
                else value
            )
    return gdf


def keep_existing_columns(
    gdf: gpd.GeoDataFrame,
    columns: Iterable[str],
) -> gpd.GeoDataFrame:
    selected = [column for column in columns if column in gdf.columns]
    if "geometry" not in selected:
        selected = ["geometry", *selected]
    return gdf[selected].copy()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json_atomic(path: Path, payload: object) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
    )


def save_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Write a GeoJSON atomically to avoid final partial files."""

    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = stringify_problem_columns(gdf)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.unlink(missing_ok=True)
        prepared.to_file(temporary, driver="GeoJSON")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold()
    return re.sub(r"[^a-z0-9а-я]+", " ", text).strip()


def _first_value(gdf: gpd.GeoDataFrame, column: str) -> object:
    if gdf.empty or column not in gdf.columns:
        return None
    value = gdf.iloc[0][column]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


def boundary_metrics(boundary: gpd.GeoDataFrame) -> dict[str, object]:
    if boundary.empty:
        raise RuntimeError("Empty boundary")

    boundary = boundary[boundary.geometry.notna()].copy()
    if boundary.empty:
        raise RuntimeError("Boundary has no geometry")

    if boundary.crs is None:
        boundary = boundary.set_crs(4326)
    else:
        boundary = boundary.to_crs(4326)

    geometry_types = sorted(set(boundary.geometry.geom_type.astype(str)))
    if not set(geometry_types).issubset({"Polygon", "MultiPolygon"}):
        raise RuntimeError(f"Boundary is not polygonal: {geometry_types}")

    min_lon, min_lat, max_lon, max_lat = [
        float(value) for value in boundary.total_bounds
    ]
    diagonal_km = _haversine_km(min_lat, min_lon, max_lat, max_lon)
    area_km2 = float(
        boundary.to_crs("EPSG:6933").geometry.area.sum() / 1_000_000
    )

    osm_type = _first_value(boundary, "osm_type")
    osm_id = _first_value(boundary, "osm_id")
    osm_ref = None
    if osm_type and osm_id is not None:
        prefix = {
            "relation": "R",
            "way": "W",
            "node": "N",
        }.get(str(osm_type).lower())
        if prefix:
            osm_ref = f"{prefix}{int(osm_id)}"

    return {
        "area_km2": area_km2,
        "bbox_diagonal_km": diagonal_km,
        "geometry_types": geometry_types,
        "min_lon": min_lon,
        "min_lat": min_lat,
        "max_lon": max_lon,
        "max_lat": max_lat,
        "name": _first_value(boundary, "name"),
        "display_name": _first_value(boundary, "display_name"),
        "osm_type": osm_type,
        "osm_id": int(osm_id) if osm_id is not None else None,
        "osm_ref": osm_ref,
        "class": _first_value(boundary, "class"),
        "type": _first_value(boundary, "type"),
        "addresstype": _first_value(boundary, "addresstype"),
        "importance": _first_value(boundary, "importance"),
    }


def _load_boundary_overrides(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(
            f"Boundary override file must contain a JSON object: {path}"
        )
    return payload


def _override_config(city: City) -> dict[str, object]:
    raw = BOUNDARY_OVERRIDES.get(city.slug)
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {"osm_id": raw}
    if isinstance(raw, dict):
        return dict(raw)
    raise ValueError(f"Bad boundary override for {city.slug}: {raw!r}")


def _candidate_limits(city: City) -> tuple[float, float]:
    config = _override_config(city)
    return (
        float(config.get("max_area_km2", MAX_BOUNDARY_AREA_KM2)),
        float(config.get("max_diagonal_km", MAX_BOUNDARY_DIAGONAL_KM)),
    )


def _validate_boundary(
    city: City,
    boundary: gpd.GeoDataFrame,
) -> dict[str, object]:
    metrics = boundary_metrics(boundary)
    max_area, max_diagonal = _candidate_limits(city)

    problems: list[str] = []
    if float(metrics["area_km2"]) > max_area:
        problems.append(
            f"area={metrics['area_km2']:.1f} km2 "
            f"exceeds limit={max_area:.1f} km2"
        )
    if float(metrics["bbox_diagonal_km"]) > max_diagonal:
        problems.append(
            f"bbox_diagonal={metrics['bbox_diagonal_km']:.1f} km "
            f"exceeds limit={max_diagonal:.1f} km"
        )

    if problems:
        label = metrics.get("display_name") or metrics.get("name") or "unknown"
        raise RuntimeError(
            f"Rejected boundary for {city.slug}: {label}; " + "; ".join(problems)
        )

    return metrics


def _candidate_score(city: City, metrics: dict[str, object]) -> float:
    score = 0.0
    expected = _normalize_text(city.query.split(",", 1)[0])
    candidate_name = _normalize_text(metrics.get("name"))
    display_name = _normalize_text(metrics.get("display_name"))

    if expected and candidate_name == expected:
        score += 80
    elif expected and expected in candidate_name:
        score += 55
    elif expected and expected in display_name:
        score += 35

    kind = _normalize_text(
        metrics.get("addresstype")
        or metrics.get("type")
        or metrics.get("class")
    )
    score += {
        "city": 100,
        "municipality": 90,
        "town": 80,
        "borough": 65,
        "city district": 60,
        "administrative": 45,
        "county": 30,
        "state": 25,
        "province": 20,
        "region": 10,
        "country": -100,
    }.get(kind, 0)

    osm_type = _normalize_text(metrics.get("osm_type"))
    score += {"relation": 20, "way": 10, "node": -100}.get(osm_type, 0)

    area_km2 = float(metrics["area_km2"])
    if 1 <= area_km2 <= 3000:
        score += 20
    elif area_km2 <= MAX_BOUNDARY_AREA_KM2:
        score += 5

    try:
        score += 10 * float(metrics.get("importance") or 0)
    except (TypeError, ValueError):
        pass

    return score


def _clean_boundary(boundary: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    boundary = boundary[boundary.geometry.notna()].copy()
    if boundary.empty:
        raise RuntimeError("Empty boundary")
    if boundary.crs is None:
        boundary = boundary.set_crs(4326)
    else:
        boundary = boundary.to_crs(4326)
    return boundary.iloc[[0]].copy()


def _resolve_boundary(
    city: City,
) -> tuple[gpd.GeoDataFrame, dict[str, object]]:
    override = _override_config(city)
    osm_id = override.get("osm_id")

    if osm_id:
        print(f"  Boundary override: {city.slug} -> {osm_id}")
        boundary = _clean_boundary(
            ox.geocoder.geocode_to_gdf(str(osm_id), by_osmid=True)
        )
        metrics = _validate_boundary(city, boundary)
        return boundary, {
            "method": "osm_id_override",
            "query": str(osm_id),
            "chosen": metrics,
            "candidates": [metrics],
            "rejected": [],
        }

    candidates: list[
        tuple[float, gpd.GeoDataFrame, dict[str, object], str]
    ] = []
    seen: set[tuple[object, object]] = set()
    rejected: list[dict[str, object]] = []

    def consider(boundary: gpd.GeoDataFrame, method: str) -> None:
        try:
            cleaned = _clean_boundary(boundary)
        except Exception as exc:
            rejected.append(
                {
                    "method": method,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            return

        try:
            metrics = _validate_boundary(city, cleaned)
        except Exception as exc:
            try:
                metrics = boundary_metrics(cleaned)
            except Exception:
                metrics = {}
            rejected.append(
                {
                    "method": method,
                    "error": f"{type(exc).__name__}: {exc}",
                    "metrics": metrics,
                }
            )
            return

        key = (metrics.get("osm_type"), metrics.get("osm_id"))
        if key in seen:
            return
        seen.add(key)
        candidates.append(
            (_candidate_score(city, metrics), cleaned, metrics, method)
        )

    print("  Geocoding boundary:", city.query)
    try:
        automatic = ox.geocoder.geocode_to_gdf(city.query)
        consider(automatic, "auto_polygon")
    except Exception as exc:
        rejected.append(
            {
                "method": "auto_polygon",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    automatic_metrics = candidates[0][2] if candidates else None
    automatic_kind = _normalize_text(
        (automatic_metrics or {}).get("addresstype")
        or (automatic_metrics or {}).get("type")
        or (automatic_metrics or {}).get("class")
    )
    needs_ranked_search = not candidates or automatic_kind in {
        "country",
        "region",
        "province",
        "state",
        "county",
    }

    if needs_ranked_search:
        print(
            f"  Checking up to {MAX_GEOCODER_RESULTS} ranked geocoder results"
        )
        for which_result in range(1, MAX_GEOCODER_RESULTS + 1):
            time.sleep(1.1)
            try:
                candidate = ox.geocoder.geocode_to_gdf(
                    city.query,
                    which_result=which_result,
                )
                consider(candidate, f"which_result={which_result}")
            except Exception as exc:
                rejected.append(
                    {
                        "method": f"which_result={which_result}",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    if not candidates:
        details = json.dumps(rejected, ensure_ascii=False, indent=2, default=str)
        raise RuntimeError(
            f"No acceptable boundary for {city.slug}. Candidates:\n{details}"
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    score, boundary, metrics, method = candidates[0]
    report_candidates = [
        {"score": item[0], "method": item[3], **item[2]}
        for item in candidates
    ]

    print(
        "  Boundary selected:",
        metrics.get("osm_ref"),
        metrics.get("addresstype") or metrics.get("type"),
        f"area={metrics['area_km2']:.1f} km2",
        f"diagonal={metrics['bbox_diagonal_km']:.1f} km",
        metrics.get("display_name"),
    )

    return boundary, {
        "method": method,
        "query": city.query,
        "score": score,
        "chosen": metrics,
        "candidates": report_candidates,
        "rejected": rejected,
    }


def retry_with_endpoints(
    function: Callable[[], object],
    what: str,
    attempts_per_endpoint: int | None = None,
):
    attempts = attempts_per_endpoint or ATTEMPTS_PER_ENDPOINT
    last_error: Exception | None = None

    for endpoint, use_rate_limit in OVERPASS_ENDPOINTS:
        ox.settings.overpass_url = endpoint
        ox.settings.overpass_rate_limit = use_rate_limit

        for attempt in range(1, attempts + 1):
            try:
                print(
                    f"  {what}: endpoint={endpoint}, attempt={attempt}/{attempts}"
                )
                return function()
            except Exception as exc:
                last_error = exc
                print(f"  FAILED {what}: {type(exc).__name__}: {exc}")
                gc.collect()
                time.sleep(8)

    if last_error is None:
        raise RuntimeError(f"No Overpass attempts made for {what}")
    raise last_error


def download_boundary(
    city: City,
    out_dir: Path,
    overwrite: bool,
) -> gpd.GeoDataFrame:
    path = out_dir / "boundary.geojson"
    report_path = out_dir / "boundary_resolution.json"

    if path.exists() and path.stat().st_size > 0 and not overwrite:
        print("  boundary exists, validating:", path)
        boundary = gpd.read_file(path)
        metrics = _validate_boundary(city, boundary)
        if not report_path.exists():
            _write_json_atomic(
                report_path,
                {
                    "method": "existing_file",
                    "query": city.query,
                    "chosen": metrics,
                },
            )
        return _clean_boundary(boundary)

    boundary, report = _resolve_boundary(city)
    save_geojson(boundary, path)
    _write_json_atomic(report_path, report)
    return boundary


def download_buildings(
    boundary: gpd.GeoDataFrame,
    out_dir: Path,
    overwrite: bool,
) -> int | None:
    path = out_dir / "buildings.geojson"
    if path.exists() and path.stat().st_size > 0 and not overwrite:
        print("  buildings exists, skipping:", path)
        return None

    polygon = boundary.to_crs(4326).geometry.iloc[0]

    def run():
        return ox.features.features_from_polygon(
            polygon,
            tags={"building": True},
        )

    buildings = retry_with_endpoints(run, "buildings")
    if not isinstance(buildings, gpd.GeoDataFrame):
        raise TypeError(
            f"Expected GeoDataFrame for buildings, got {type(buildings).__name__}"
        )

    buildings = buildings[
        buildings.geometry.type.isin(["Polygon", "MultiPolygon"])
    ].copy()
    buildings = buildings.to_crs(4326)

    keep = [
        "geometry",
        "building",
        "height",
        "building:levels",
        "levels",
        "num_floors",
        "roof:shape",
        "roof:height",
        "roof:material",
        "facade:material",
        "addr:street",
        "addr:housenumber",
        "name",
    ]
    buildings = keep_existing_columns(buildings, keep)
    count = len(buildings)
    save_geojson(buildings, path)
    del buildings
    gc.collect()
    return count


def download_roads(
    boundary: gpd.GeoDataFrame,
    out_dir: Path,
    overwrite: bool,
) -> int | None:
    path = out_dir / "roads.geojson"
    if path.exists() and path.stat().st_size > 0 and not overwrite:
        print("  roads exists, skipping:", path)
        return None

    polygon = boundary.to_crs(4326).geometry.iloc[0]

    def run():
        graph = ox.graph.graph_from_polygon(
            polygon,
            network_type="drive",
            simplify=True,
        )
        _, edges = ox.convert.graph_to_gdfs(graph)
        return edges.reset_index()

    roads = retry_with_endpoints(run, "roads")
    if not isinstance(roads, gpd.GeoDataFrame):
        raise TypeError(
            f"Expected GeoDataFrame for roads, got {type(roads).__name__}"
        )
    roads = roads.to_crs(4326)

    keep = [
        "geometry",
        "osmid",
        "highway",
        "name",
        "oneway",
        "lanes",
        "maxspeed",
        "bridge",
        "tunnel",
        "length",
    ]
    roads = keep_existing_columns(roads, keep)
    count = len(roads)
    save_geojson(roads, path)
    del roads
    gc.collect()
    return count


def write_manifest(
    city: City,
    out_dir: Path,
    status: str,
    error: str | None = None,
) -> None:
    manifest = asdict(city)
    manifest.update(
        {
            "status": status,
            "error": error,
            "boundary_file": "boundary.geojson",
            "boundary_resolution_file": "boundary_resolution.json",
            "buildings_file": "buildings.geojson",
            "roads_file": "roads.geojson",
        }
    )
    _write_json_atomic(out_dir / "manifest.json", manifest)


def _nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def process_city(
    city: City,
    root: Path,
    roads: bool,
    overwrite: bool,
    sleep_s: float,
    boundaries_only: bool = False,
    fail_fast: bool = False,
) -> bool:
    out_dir = root / city.subset / city.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    boundary_path = out_dir / "boundary.geojson"
    buildings_path = out_dir / "buildings.geojson"
    roads_path = out_dir / "roads.geojson"
    traceback_path = out_dir / "traceback.txt"

    complete = _nonempty(boundary_path) and (
        boundaries_only
        or (_nonempty(buildings_path) and (not roads or _nonempty(roads_path)))
    )
    if complete and not overwrite:
        download_boundary(city, out_dir, overwrite=False)
        print(f"SKIP complete: {city.subset}/{city.slug}")
        traceback_path.unlink(missing_ok=True)
        write_manifest(
            city,
            out_dir,
            status="boundary_ok" if boundaries_only else "ok",
        )
        return True

    print("\n" + "=" * 72)
    print(f"{city.subset.upper()} | {city.name} | {city.query}")
    print("=" * 72)

    try:
        boundary = download_boundary(city, out_dir, overwrite=overwrite)

        if boundaries_only:
            print(f"  BOUNDARY OK: {city.name}")
            traceback_path.unlink(missing_ok=True)
            write_manifest(city, out_dir, status="boundary_ok")
            return True

        building_count = download_buildings(
            boundary,
            out_dir,
            overwrite=overwrite,
        )
        road_count = None
        if roads:
            road_count = download_roads(
                boundary,
                out_dir,
                overwrite=overwrite,
            )

        print(f"  OK: {city.name}")
        if building_count is not None:
            print(f"  buildings: {building_count}")
        if road_count is not None:
            print(f"  roads: {road_count}")

        traceback_path.unlink(missing_ok=True)
        write_manifest(city, out_dir, status="ok")
        return True

    except Exception as exc:
        error = "".join(
            traceback.format_exception_only(type(exc), exc)
        ).strip()
        print(f"  ERROR: {city.name}: {error}")
        write_manifest(city, out_dir, status="error", error=error)
        _write_text_atomic(traceback_path, traceback.format_exc())
        if fail_fast or os.environ.get("URBAN_FRACTAL_FAIL_ON_CITY_ERROR") == "1":
            raise
        return False

    finally:
        gc.collect()
        if sleep_s > 0:
            print(f"  sleeping {sleep_s} s...")
            time.sleep(sleep_s)


configure_downloader()
