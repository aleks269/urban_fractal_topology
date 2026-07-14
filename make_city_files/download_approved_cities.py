from __future__ import annotations
import ssl
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Рабочий NoVerifyAdapter без ошибок с SSLContext
class NoVerifyAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

    def proxy_manager_for(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().proxy_manager_for(*args, **kwargs)

requests.Session().mount('https://', NoVerifyAdapter())

# Теперь можно импортировать osmnx
import osmnx as ox


import argparse
import json
import re
import time
import traceback
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import osmnx as ox

# ------------------------------------------------------------
# OSMnx settings
# ------------------------------------------------------------

ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.timeout = 300

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.openstreetmap.ru/api",
    "https://overpass.osm.ch/api",
]


# ------------------------------------------------------------
# Approved city catalog
# Format:
# set|slug|name|query|morphotype
# ------------------------------------------------------------

CATALOG = """
russia|moscow|Moscow|Moscow, Russia|megacity_polycentric
russia|saint_petersburg|Saint Petersburg|Saint Petersburg, Russia|imperial_grid_water
russia|novosibirsk|Novosibirsk|Novosibirsk, Russia|siberian_rail_river
russia|yekaterinburg|Yekaterinburg|Yekaterinburg, Russia|ural_industrial
russia|kazan|Kazan|Kazan, Russia|historic_river_modern
russia|nizhny_novgorod|Nizhny Novgorod|Nizhny Novgorod, Russia|confluence_relief_industrial
russia|chelyabinsk|Chelyabinsk|Chelyabinsk, Russia|industrial_rail
russia|samara|Samara|Samara, Russia|volga_linear_grid
russia|omsk|Omsk|Omsk, Russia|siberian_river_rail
russia|rostov_on_don|Rostov-on-Don|Rostov-on-Don, Russia|southern_river_port
russia|ufa|Ufa|Ufa, Russia|relief_river_fragmented
russia|krasnoyarsk|Krasnoyarsk|Krasnoyarsk, Russia|yenisei_mountain_linear
russia|perm|Perm|Perm, Russia|kama_industrial_fragmented
russia|voronezh|Voronezh|Voronezh, Russia|central_russian_control
russia|volgograd|Volgograd|Volgograd, Russia|extreme_linear_volga
russia|krasnodar|Krasnodar|Krasnodar, Russia|southern_sprawl
russia|saratov|Saratov|Saratov, Russia|volga_relief_linear
russia|tyumen|Tyumen|Tyumen, Russia|fast_growth_oil_admin
russia|tolyatti|Tolyatti|Tolyatti, Russia|soviet_planned_autograd
russia|izhevsk|Izhevsk|Izhevsk, Russia|industrial_soviet

russia|veliky_novgorod|Veliky Novgorod|Veliky Novgorod, Russia|ancient_loose_lowrise
russia|pskov|Pskov|Pskov, Russia|fortress_border_river
russia|petrozavodsk|Petrozavodsk|Petrozavodsk, Russia|northern_lake_linear
russia|volkhov|Volkhov|Volkhov, Leningrad Oblast, Russia|small_industrial_river
russia|vyborg|Vyborg|Vyborg, Russia|european_fortress_bay
russia|staraya_russa|Staraya Russa|Staraya Russa, Russia|small_ancient_lowrise
russia|gatchina|Gatchina|Gatchina, Russia|palace_park_suburban
russia|kronstadt|Kronstadt|Kronstadt, Saint Petersburg, Russia|island_military_port
russia|kaliningrad|Kaliningrad|Kaliningrad, Russia|prussian_soviet_mix
russia|yaroslavl|Yaroslavl|Yaroslavl, Russia|historic_volga
russia|vladimir|Vladimir|Vladimir, Russia|ancient_soviet_periphery
russia|suzdal|Suzdal|Suzdal, Russia|small_historic_low_density
russia|kostroma|Kostroma|Kostroma, Russia|historic_regular_volga
russia|ryazan|Ryazan|Ryazan, Russia|central_historic
russia|smolensk|Smolensk|Smolensk, Russia|fortress_relief
russia|tula|Tula|Tula, Russia|historic_industrial
russia|kaluga|Kaluga|Kaluga, Russia|historic_science_industrial
russia|kolomna|Kolomna|Kolomna, Russia|small_historic_kremlin
russia|sergiev_posad|Sergiev Posad|Sergiev Posad, Russia|monastery_city
russia|yelets|Yelets|Yelets, Russia|merchant_old_relief

russia|astrakhan|Astrakhan|Astrakhan, Russia|delta_water_fragmented
russia|ulyanovsk|Ulyanovsk|Ulyanovsk, Russia|volga_high_bank
russia|rybinsk|Rybinsk|Rybinsk, Russia|reservoir_historic_industrial
russia|kirov|Kirov|Kirov, Russia|northeast_historic_industrial
russia|cheboksary|Cheboksary|Cheboksary, Russia|volga_reconstructed_bank
russia|yoshkar_ola|Yoshkar-Ola|Yoshkar-Ola, Russia|compact_regional_postmodern
russia|penza|Penza|Penza, Russia|central_valley
russia|syzran|Syzran|Syzran, Russia|linear_volga_industrial
russia|dimitrovgrad|Dimitrovgrad|Dimitrovgrad, Russia|planned_industrial_medium
russia|naberezhnye_chelny|Naberezhnye Chelny|Naberezhnye Chelny, Russia|soviet_planned_kamaz

russia|magnitogorsk|Magnitogorsk|Magnitogorsk, Russia|kombinat_city
russia|nizhny_tagil|Nizhny Tagil|Nizhny Tagil, Russia|industrial_relief
russia|kamensk_uralsky|Kamensk-Uralsky|Kamensk-Uralsky, Russia|industrial_river_breaks
russia|miass|Miass|Miass, Russia|mountain_industrial
russia|orsk|Orsk|Orsk, Russia|linear_industrial_south_ural
russia|sterlitamak|Sterlitamak|Sterlitamak, Russia|chemical_industrial
russia|salavat|Salavat|Salavat, Russia|soviet_petrochemical
russia|novotroitsk|Novotroitsk|Novotroitsk, Russia|metallurgical_monotown
russia|berezniki|Berezniki|Berezniki, Russia|chemical_technogenic_voids
russia|solikamsk|Solikamsk|Solikamsk, Russia|industrial_historic_small

russia|tomsk|Tomsk|Tomsk, Russia|university_historic_siberian
russia|kemerovo|Kemerovo|Kemerovo, Russia|coal_industrial
russia|novokuznetsk|Novokuznetsk|Novokuznetsk, Russia|large_kombinat_city
russia|barnaul|Barnaul|Barnaul, Russia|siberian_plain
russia|irkutsk|Irkutsk|Irkutsk, Russia|historic_siberian_angara
russia|ulan_ude|Ulan-Ude|Ulan-Ude, Russia|steppe_river_buddhist_siberian
russia|chita|Chita|Chita, Russia|transbaikal_rail_military
russia|khabarovsk|Khabarovsk|Khabarovsk, Russia|amur_relief_far_east
russia|vladivostok|Vladivostok|Vladivostok, Russia|bay_relief_bridges_port
russia|nakhodka|Nakhodka|Nakhodka, Russia|port_linear
russia|yuzhno_sakhalinsk|Yuzhno-Sakhalinsk|Yuzhno-Sakhalinsk, Russia|island_japanese_soviet
russia|petropavlovsk_kamchatsky|Petropavlovsk-Kamchatsky|Petropavlovsk-Kamchatsky, Russia|bay_volcanic_extreme
russia|bratsk|Bratsk|Bratsk, Russia|hydropower_reservoir_soviet
russia|angarsk|Angarsk|Angarsk, Russia|petrochemical_planned
russia|komsomolsk_on_amur|Komsomolsk-on-Amur|Komsomolsk-on-Amur, Russia|soviet_far_east_industrial

russia|murmansk|Murmansk|Murmansk, Russia|arctic_port_relief
russia|arkhangelsk|Arkhangelsk|Arkhangelsk, Russia|northern_port_delta
russia|severodvinsk|Severodvinsk|Severodvinsk, Russia|closed_shipbuilding
russia|norilsk|Norilsk|Norilsk, Russia|arctic_industrial_extreme
russia|yakutsk|Yakutsk|Yakutsk, Russia|extreme_cold_permafrost
russia|magadan|Magadan|Magadan, Russia|northern_port_relief
russia|salekhard|Salekhard|Salekhard, Russia|arctic_administrative
russia|novy_urengoy|Novy Urengoy|Novy Urengoy, Russia|gas_northern_city
russia|surgut|Surgut|Surgut, Russia|oil_fast_growth
russia|nizhnevartovsk|Nizhnevartovsk|Nizhnevartovsk, Russia|oil_late_soviet

russia|sochi|Sochi|Sochi, Russia|coastal_mountain_linear
russia|novorossiysk|Novorossiysk|Novorossiysk, Russia|port_bay_mountain
russia|anapa|Anapa|Anapa, Russia|resort_seasonal
russia|gelendzhik|Gelendzhik|Gelendzhik, Russia|bay_mountain_tourist
russia|stavropol|Stavropol|Stavropol, Russia|southern_plateau
russia|pyatigorsk|Pyatigorsk|Pyatigorsk, Russia|resort_mountain_polycentric
russia|makhachkala|Makhachkala|Makhachkala, Russia|caspian_linear_fast_growth
russia|derbent|Derbent|Derbent, Russia|ancient_linear_fortress
russia|elista|Elista|Elista, Russia|steppe_planned
russia|nalchik|Nalchik|Nalchik, Russia|foothill_regular_resort

russia|zelenograd|Zelenograd|Zelenograd, Moscow, Russia|soviet_science_satellite
russia|obninsk|Obninsk|Obninsk, Russia|science_city_planned
russia|dubna|Dubna|Dubna, Russia|science_city_canal_volga
russia|korolev|Korolyov|Korolyov, Moscow Oblast, Russia|space_industrial_science
russia|sarov|Sarov|Sarov, Russia|closed_science_industrial

world|new_york|New York|New York City, New York, USA|dense_grid_islands
world|boston|Boston|Boston, Massachusetts, USA|old_irregular_university_suburban
world|washington_dc|Washington DC|Washington, District of Columbia, USA|planned_capital_radial
world|chicago|Chicago|Chicago, Illinois, USA|grid_lake_industrial
world|detroit|Detroit|Detroit, Michigan, USA|shrinking_city_voids
world|los_angeles|Los Angeles|Los Angeles, California, USA|car_sprawl_polycentric
world|san_francisco|San Francisco Bay Area|San Francisco, California, USA|bay_relief_polycentric
world|seattle|Seattle|Seattle, Washington, USA|water_relief_tech
world|phoenix|Phoenix|Phoenix, Arizona, USA|desert_sprawl_grid
world|las_vegas|Las Vegas|Las Vegas, Nevada, USA|desert_fast_growth
world|houston|Houston|Houston, Texas, USA|car_sprawl_oil
world|new_orleans|New Orleans|New Orleans, Louisiana, USA|delta_water_lowland
world|miami|Miami|Miami, Florida, USA|coastal_lagoon_islands
world|toronto|Toronto|Toronto, Ontario, Canada|north_american_dense_suburban
world|vancouver|Vancouver|Vancouver, British Columbia, Canada|water_mountains_compact
world|mexico_city|Mexico City|Mexico City, Mexico|highland_megastructure_informal
world|guadalajara|Guadalajara|Guadalajara, Mexico|mexican_grid_sprawl
world|monterrey|Monterrey|Monterrey, Mexico|industrial_mountain
world|bogota|Bogota|Bogota, Colombia|andean_linear_dense
world|medellin|Medellin|Medellín, Colombia|valley_slope_urbanization
world|lima|Lima|Lima, Peru|desert_coastal_boundary
world|santiago|Santiago|Santiago, Chile|andean_basin
world|buenos_aires|Buenos Aires|Buenos Aires, Argentina|regular_grid_plain
world|montevideo|Montevideo|Montevideo, Uruguay|coastal_compact
world|sao_paulo|Sao Paulo|São Paulo, Brazil|huge_heterogeneous
world|rio_de_janeiro|Rio de Janeiro|Rio de Janeiro, Brazil|mountains_bays_fragmented
world|brasilia|Brasilia|Brasília, Brazil|modernist_planned_capital
world|belo_horizonte|Belo Horizonte|Belo Horizonte, Brazil|planned_grid_relief_periphery
world|recife|Recife|Recife, Brazil|water_islands_delta
world|salvador|Salvador|Salvador, Bahia, Brazil|coastal_relief_historic
world|london|London|London, England, United Kingdom|historic_multilayer_polycentric
world|paris|Paris|Paris, France|compact_core_banlieue_radial
world|berlin|Berlin|Berlin, Germany|polycentric_green_voids
world|hamburg|Hamburg|Hamburg, Germany|port_water_canals
world|ruhrgebiet|Ruhrgebiet|Ruhr, Germany|polycentric_industrial_region
world|amsterdam_randstad|Amsterdam Randstad|Amsterdam, Netherlands|water_lowland_polycentric
world|copenhagen|Copenhagen|Copenhagen, Denmark|compact_harbor_green
world|stockholm|Stockholm|Stockholm, Sweden|archipelago_island_topology
world|helsinki|Helsinki|Helsinki, Finland|northern_coastal_forest_water
world|oslo|Oslo|Oslo, Norway|fjord_relief_northern
world|vienna|Vienna|Vienna, Austria|imperial_ring_structure
world|prague|Prague|Prague, Czechia|relief_river_historic
world|warsaw|Warsaw|Warsaw, Poland|reconstruction_socialist_layers
world|budapest|Budapest|Budapest, Hungary|danube_relief_contrast
world|barcelona|Barcelona|Barcelona, Spain|eixample_grid_compact
world|madrid|Madrid|Madrid, Spain|radial_ring_dense
world|lisbon|Lisbon|Lisbon, Portugal|relief_estuary_historic
world|rome|Rome|Rome, Italy|ancient_multilayer_archaeological_voids
world|milan|Milan|Milan, Italy|compact_industrial_financial
world|venice|Venice|Venice, Italy|extreme_water_topology
world|athens|Athens|Athens, Greece|mediterranean_dense_basin
world|istanbul|Istanbul|Istanbul, Turkey|strait_water_historic
world|kyiv|Kyiv|Kyiv, Ukraine|east_european_river_relief
world|lviv|Lviv|Lviv, Ukraine|central_european_historic
world|bucharest|Bucharest|Bucharest, Romania|balkan_socialist_axes
world|tokyo|Tokyo|Tokyo, Japan|hyperdense_rail_polycentric
world|osaka|Osaka-Kobe-Kyoto|Osaka, Japan|japanese_polycentric_megalopolis
world|seoul|Seoul|Seoul, South Korea|dense_mountain_river
world|busan|Busan|Busan, South Korea|mountain_port_linear
world|beijing|Beijing|Beijing, China|rings_superblocks_planned
world|shanghai|Shanghai|Shanghai, China|river_delta_highrise
world|shenzhen|Shenzhen|Shenzhen, China|rapid_growth_highrise
world|guangzhou|Guangzhou-Foshan|Guangzhou, China|delta_polycentric
world|hong_kong|Hong Kong|Hong Kong|extreme_density_mountains_water
world|taipei|Taipei|Taipei, Taiwan|mountain_basin_rivers
world|singapore|Singapore|Singapore|island_managed_green_water
world|bangkok|Bangkok|Bangkok, Thailand|delta_lowland_canals_sprawl
world|jakarta|Jakarta|Jakarta, Indonesia|delta_megastructure
world|manila|Manila|Manila, Philippines|hyperdense_polycentric
world|kuala_lumpur|Kuala Lumpur|Kuala Lumpur, Malaysia|tropical_auto_polycentric
world|hanoi|Hanoi|Hanoi, Vietnam|lakes_historic_new_periphery
world|ho_chi_minh_city|Ho Chi Minh City|Ho Chi Minh City, Vietnam|delta_growth_sprawl
world|delhi|Delhi|Delhi, India|heterogeneous_megacity
world|mumbai|Mumbai|Mumbai, India|peninsula_hyperdense_water
world|kolkata|Kolkata|Kolkata, India|delta_plain_colonial_grid
world|bengaluru|Bengaluru|Bengaluru, India|tech_plateau_polycentric
world|chennai|Chennai|Chennai, India|coastal_plain_sprawl
world|hyderabad|Hyderabad|Hyderabad, India|tech_historic_lakes
world|dhaka|Dhaka|Dhaka, Bangladesh|extreme_density_delta
world|karachi|Karachi|Karachi, Pakistan|port_arid_megastructure
world|lahore|Lahore|Lahore, Pakistan|historic_colonial_new
world|tehran|Tehran|Tehran, Iran|mountain_gradient
world|isfahan|Isfahan|Isfahan, Iran|historic_axis_gardens_river
world|dubai|Dubai|Dubai, United Arab Emirates|linear_auto_highrise_desert
world|abu_dhabi|Abu Dhabi|Abu Dhabi, United Arab Emirates|island_planned_capital
world|riyadh|Riyadh|Riyadh, Saudi Arabia|desert_sprawl_fast_growth
world|jeddah|Jeddah|Jeddah, Saudi Arabia|port_coastal_hajj_logistics
world|cairo|Cairo|Cairo, Egypt|nile_desert_boundary_dense
world|alexandria|Alexandria|Alexandria, Egypt|linear_mediterranean
world|casablanca|Casablanca|Casablanca, Morocco|atlantic_port_metropolis
world|marrakech|Marrakech|Marrakech, Morocco|medina_new_regular
world|tunis|Tunis|Tunis, Tunisia|medina_lakes_coastal
world|lagos|Lagos|Lagos, Nigeria|lagoon_islands_informal_growth
world|accra|Accra|Accra, Ghana|coastal_west_african_sprawl
world|nairobi|Nairobi|Nairobi, Kenya|highland_african_informal
world|addis_ababa|Addis Ababa|Addis Ababa, Ethiopia|mountain_capital_fast_growth
world|johannesburg|Johannesburg|Johannesburg, South Africa|mining_auto_sprawl
world|cape_town|Cape Town|Cape Town, South Africa|mountains_ocean_port
world|sydney|Sydney|Sydney, Australia|harbor_suburban_sprawl
world|melbourne|Melbourne|Melbourne, Australia|grid_suburban_plain
"""


@dataclass
class City:
    subset: str
    slug: str
    name: str
    query: str
    morphotype: str


def parse_catalog(text: str) -> list[City]:
    cities = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 5:
            raise ValueError(f"Bad catalog line: {line}")
        cities.append(City(*parts))
    return cities


def stringify_problem_columns(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    for col in gdf.columns:
        if col == "geometry":
            continue
        if gdf[col].dtype == "object":
            gdf[col] = gdf[col].apply(
                lambda x: json.dumps(x, ensure_ascii=False)
                if isinstance(x, (list, dict, tuple, set))
                else x
            )
    return gdf


def keep_existing_columns(gdf: gpd.GeoDataFrame, cols: Iterable[str]) -> gpd.GeoDataFrame:
    cols = [c for c in cols if c in gdf.columns]
    if "geometry" not in cols:
        cols = ["geometry"] + cols
    return gdf[cols].copy()


def save_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf = stringify_problem_columns(gdf)
    gdf.to_file(path, driver="GeoJSON")


def retry_with_endpoints(func, what: str, attempts_per_endpoint: int = 2):
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        ox.settings.overpass_url = endpoint
        for attempt in range(1, attempts_per_endpoint + 1):
            try:
                print(f"  {what}: endpoint={endpoint}, attempt={attempt}")
                return func()
            except Exception as e:
                last_error = e
                print(f"  FAILED {what}: {type(e).__name__}: {e}")
                time.sleep(8)
    raise last_error


def download_boundary(city: City, out_dir: Path, overwrite: bool) -> gpd.GeoDataFrame:
    path = out_dir / "boundary.geojson"
    if path.exists() and not overwrite:
        print("  boundary exists, reading:", path)
        return gpd.read_file(path)

    print("  Downloading boundary:", city.query)
    boundary = ox.geocode_to_gdf(city.query)
    boundary = boundary[boundary.geometry.notna()].copy()
    boundary = boundary.to_crs(4326)

    if boundary.empty:
        raise RuntimeError("Empty boundary")

    # Keep only first result if geocoder returned multiple.
    boundary = boundary.iloc[[0]].copy()
    save_geojson(boundary, path)
    return boundary


def download_buildings(boundary: gpd.GeoDataFrame, out_dir: Path, overwrite: bool) -> gpd.GeoDataFrame:
    path = out_dir / "buildings.geojson"
    if path.exists() and not overwrite:
        print("  buildings exists, skipping:", path)
        return gpd.read_file(path)

    poly = boundary.to_crs(4326).geometry.iloc[0]

    def _run():
        return ox.features_from_polygon(poly, tags={"building": True})

    buildings = retry_with_endpoints(_run, "buildings")
    buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
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
    save_geojson(buildings, path)
    return buildings


def download_roads(boundary: gpd.GeoDataFrame, out_dir: Path, overwrite: bool) -> gpd.GeoDataFrame | None:
    path = out_dir / "roads.geojson"
    if path.exists() and not overwrite:
        print("  roads exists, skipping:", path)
        return gpd.read_file(path)

    poly = boundary.to_crs(4326).geometry.iloc[0]

    def _run():
        graph = ox.graph_from_polygon(poly, network_type="drive", simplify=True)
        _, edges = ox.graph_to_gdfs(graph)
        return edges.reset_index()

    roads = retry_with_endpoints(_run, "roads")
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
    save_geojson(roads, path)
    return roads


def write_manifest(city: City, out_dir: Path, status: str, error: str | None = None) -> None:
    manifest = asdict(city)
    manifest.update(
        {
            "status": status,
            "error": error,
            "boundary_file": "boundary.geojson",
            "buildings_file": "buildings.geojson",
            "roads_file": "roads.geojson",
        }
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def process_city(city: City, root: Path, roads: bool, overwrite: bool, sleep_s: float) -> None:
    out_dir = root / city.subset / city.slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 72)
    print(f"{city.subset.upper()} | {city.name} | {city.query}")
    print("=" * 72)

    try:
        boundary = download_boundary(city, out_dir, overwrite=overwrite)
        buildings = download_buildings(boundary, out_dir, overwrite=overwrite)

        if roads:
            download_roads(boundary, out_dir, overwrite=overwrite)

        print(f"  OK: {city.name}")
        print(f"  buildings: {len(buildings)}")
        write_manifest(city, out_dir, status="ok")

    except Exception as e:
        err = "".join(traceback.format_exception_only(type(e), e)).strip()
        print(f"  ERROR: {city.name}: {err}")
        write_manifest(city, out_dir, status="error", error=err)
        (out_dir / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")

    if sleep_s > 0:
        print(f"  sleeping {sleep_s} s...")
        time.sleep(sleep_s)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download boundary/buildings/roads for approved urban morphology city set."
    )
    parser.add_argument(
        "--set",
        dest="subset",
        choices=["russia", "world", "all"],
        default="russia",
        help="City subset to download.",
    )
    parser.add_argument(
        "--out",
        default="data/approved_cities",
        help="Output root directory.",
    )
    parser.add_argument(
        "--roads",
        action="store_true",
        help="Also download drive road network. Slower and more fragile.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing files.",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start index after filtering.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of cities to process.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=5.0,
        help="Sleep between cities to avoid hammering APIs.",
    )
    parser.add_argument(
        "--cities",
        default=None,
        help="Comma-separated slugs to download, e.g. zelenograd,volkhov,pskov.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Only list selected cities and exit.",
    )

    args = parser.parse_args()

    cities = parse_catalog(CATALOG)

    if args.subset != "all":
        cities = [c for c in cities if c.subset == args.subset]

    if args.cities:
        selected = {s.strip() for s in args.cities.split(",") if s.strip()}
        cities = [c for c in cities if c.slug in selected]

    cities = cities[args.start :]
    if args.limit is not None:
        cities = cities[: args.limit]

    print(f"Selected cities: {len(cities)}")
    for i, c in enumerate(cities, 1):
        print(f"{i:03d}. {c.subset}/{c.slug} | {c.name} | {c.query}")

    if args.list:
        return

    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)

    catalog_path = root / "selected_catalog.json"
    catalog_path.write_text(
        json.dumps([asdict(c) for c in cities], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("Catalog saved:", catalog_path)

    for c in cities:
        process_city(c, root=root, roads=args.roads, overwrite=args.overwrite, sleep_s=args.sleep)


if __name__ == "__main__":
    main()
