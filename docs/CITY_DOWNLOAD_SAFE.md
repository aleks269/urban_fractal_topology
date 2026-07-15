# Safe city download workflow

The city catalog is stored only in `configs/city_catalog_200.csv`.

## 1. Resolve and validate boundaries

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --set all \
  --boundaries-only \
  --cache-folder data/osmnx_cache \
  --sleep 1.1
```

Do not start Overpass downloads until every selected city has a reviewed
`boundary.geojson` and `boundary_resolution.json`.

Ambiguous cities can be pinned in
`make_city_files/boundary_osm_ids.json`:

```json
{
  "example_city": "R123456"
}
```

A value can also define city-specific limits:

```json
{
  "example_city": {
    "osm_id": "R123456",
    "max_area_km2": 20000,
    "max_diagonal_km": 500
  }
}
```

## 2. Download buildings

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --set all \
  --cache-folder data/osmnx_cache \
  --sleep 5
```

For Slurm, run one city per array task. This releases Python memory after
each city and prevents one failed Overpass query from blocking the entire
catalog.

## Completion criteria

A completed city has non-empty:

- `boundary.geojson`
- `boundary_resolution.json`
- `buildings.geojson`
- `manifest.json` with status `ok`

Errors are recorded in `traceback.txt`, and the catalog command returns a
non-zero exit status when any selected city fails.
