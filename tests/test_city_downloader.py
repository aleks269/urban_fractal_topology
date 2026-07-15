from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from batch_tools.download_city_catalog import read_catalog
from make_city_files import download_approved_cities as downloader


def _boundary(
    *,
    geometry,
    osm_id: int = 1,
    name: str = "Test City",
    addresstype: str = "city",
) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "name": [name],
            "display_name": [f"{name}, Test Country"],
            "osm_type": ["relation"],
            "osm_id": [osm_id],
            "addresstype": [addresstype],
            "importance": [0.8],
        },
        geometry=[geometry],
        crs="EPSG:4326",
    )


def test_read_catalog_uses_csv_as_source_of_truth(tmp_path: Path):
    catalog = tmp_path / "cities.csv"
    catalog.write_text(
        "subset,slug,name,query,morphotype\n"
        'world,test_city,Test City,"Test City, Test Country",grid\n',
        encoding="utf-8",
    )

    cities = read_catalog(catalog)

    assert len(cities) == 1
    assert cities[0].slug == "test_city"
    assert cities[0].query == "Test City, Test Country"


def test_resolver_continues_after_nonpolygon_automatic_result(monkeypatch):
    city = downloader.City(
        subset="world",
        slug="test_city",
        name="Test City",
        query="Test City, Test Country",
        morphotype="grid",
    )
    polygon = _boundary(
        geometry=box(10.0, 50.0, 10.1, 50.1),
        osm_id=123,
    )

    calls = []

    def fake_geocode(query, *, which_result=None, by_osmid=False):
        calls.append((query, which_result, by_osmid))
        if which_result is None:
            raise TypeError("automatic result is not polygonal")
        if which_result == 1:
            return polygon
        raise TypeError("no more polygonal results")

    monkeypatch.setattr(
        downloader.ox.geocoder,
        "geocode_to_gdf",
        fake_geocode,
    )
    monkeypatch.setattr(downloader.time, "sleep", lambda _: None)
    monkeypatch.setattr(downloader, "MAX_GEOCODER_RESULTS", 2)
    monkeypatch.setattr(downloader, "MAX_BOUNDARY_AREA_KM2", 10000.0)
    monkeypatch.setattr(downloader, "MAX_BOUNDARY_DIAGONAL_KM", 300.0)
    monkeypatch.setattr(downloader, "BOUNDARY_OVERRIDES", {})

    selected, report = downloader._resolve_boundary(city)

    assert selected.iloc[0]["osm_id"] == 123
    assert report["method"] == "which_result=1"
    assert report["chosen"]["osm_ref"] == "R123"
    assert calls[0][1] is None
    assert calls[1][1] == 1


def test_boundary_validation_rejects_oversized_geometry(monkeypatch):
    city = downloader.City(
        subset="world",
        slug="oversized",
        name="Oversized",
        query="Oversized, Test Country",
        morphotype="test",
    )
    boundary = _boundary(
        geometry=box(0.0, 0.0, 5.0, 5.0),
        osm_id=456,
    )

    monkeypatch.setattr(downloader, "MAX_BOUNDARY_AREA_KM2", 1000.0)
    monkeypatch.setattr(downloader, "MAX_BOUNDARY_DIAGONAL_KM", 300.0)
    monkeypatch.setattr(downloader, "BOUNDARY_OVERRIDES", {})

    with pytest.raises(RuntimeError, match="exceeds limit"):
        downloader._validate_boundary(city, boundary)


def test_exact_osm_override_is_used(monkeypatch):
    city = downloader.City(
        subset="world",
        slug="fixed_city",
        name="Fixed City",
        query="Fixed City, Test Country",
        morphotype="test",
    )
    boundary = _boundary(
        geometry=box(20.0, 40.0, 20.1, 40.1),
        osm_id=999,
    )

    def fake_geocode(query, *, which_result=None, by_osmid=False):
        assert query == "R999"
        assert by_osmid is True
        assert which_result is None
        return boundary

    monkeypatch.setattr(
        downloader.ox.geocoder,
        "geocode_to_gdf",
        fake_geocode,
    )
    monkeypatch.setattr(
        downloader,
        "BOUNDARY_OVERRIDES",
        {"fixed_city": "R999"},
    )
    monkeypatch.setattr(downloader, "MAX_BOUNDARY_AREA_KM2", 10000.0)
    monkeypatch.setattr(downloader, "MAX_BOUNDARY_DIAGONAL_KM", 300.0)

    selected, report = downloader._resolve_boundary(city)

    assert selected.iloc[0]["osm_id"] == 999
    assert report["method"] == "osm_id_override"
