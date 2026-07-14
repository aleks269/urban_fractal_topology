# Resolution sweep mode

This update adds a one-city / multi-resolution mode to `urban-fractal`.

## Command

```bash
urban-fractal \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd_resolution_sweep \
  --resolution-sweep 5 10 20 50 100 \
  --topology
```

The usual single-run mode still works:

```bash
urban-fractal \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd_25m \
  --pixel 25 \
  --topology
```

## What changed

### `urban_fractal/cli.py`

Added CLI options:

- `--resolution-sweep 5 10 20 50 100`
- `--resolution-sweep-continue-on-error`
- `--sweep-max-area-error`
- `--sweep-min-r2`
- `--sweep-d-cv-threshold`
- `--sweep-rc-cv-threshold`

If `--resolution-sweep` is present, the CLI calls `analyze_resolution_sweep()` instead of `analyze_city()`.

### `urban_fractal/pipeline.py`

Added raster diagnostics to every normal `summary.json`:

- `n_rows`
- `n_cols`
- `n_pixels_total`
- `n_pixels_buildings`
- `foreground_fraction`
- `building_area_raster_m2`
- `building_area_vector_m2`
- `raster_area_error_rel`
- `all_touched`

Added functions:

- `_pixel_label()`
- `_finite_cv()`
- `_extract_sweep_row()`
- `_extract_error_sweep_row()`
- `_longest_stable_window()`
- `summarize_resolution_stability()`
- `analyze_resolution_sweep()`

### `urban_fractal/plots.py`

Added:

- `plot_resolution_sweep()`

It writes `resolution_sweep_stability.png`.

### `tests/test_resolution_sweep.py`

Added a synthetic test for the sweep mode.

## Outputs

The sweep output directory contains:

```text
resolution_sweep_summary.csv
resolution_sweep_summary.json
resolution_sweep_stability.png
px_5m/summary.json
px_10m/summary.json
...
```

Each `px_*m` subfolder is a normal `analyze_city()` run.

## Stability logic

The program first filters runs by basic quality:

- status is `ok`;
- `raster_area_error_rel <= --sweep-max-area-error`;
- `D_r2 >= --sweep-min-r2`;
- `D_n_points >= --min-scaling-points`.

Then it searches for the longest contiguous pixel-size window where:

- coefficient of variation of `D_build` is below `--sweep-d-cv-threshold`;
- if topology is enabled and at least two valid `rc_m` values exist, coefficient of variation of `rc_m` is below `--sweep-rc-cv-threshold`.

This is a diagnostic heuristic. It rejects obviously grid-dependent results. It is not a proof of true scale invariance.

## Tests

Run:

```bash
python -m pytest -q
```

Validated result after the update:

```text
8 passed
```
