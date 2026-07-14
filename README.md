# UrbanFractal Topology

**UrbanFractal Topology** is a research-oriented Python pipeline for finite-scale analysis of urban morphology from building footprints. It combines fractal, lacunarity, compactness, approximate 2.5D envelope, and multiscale topological descriptors in a reproducible command-line workflow.

Current version: **0.3.0**  
Status: **research prototype**

The central methodological principle is explicit scale control: all scaling quantities are treated as finite-resolution estimates, and the software reports the scale interval used instead of extrapolating urban structure below the resolution of the source data.

## Main capabilities

The pipeline currently computes:

- finite-scale 2D box-counting dimension of building footprints, `D_build`;
- gliding-box lacunarity, `Lambda(r)`;
- 2D compactness of the selected urban boundary, `C_2D`;
- approximate 2.5D building-envelope characteristics:
  - roof area;
  - wall area;
  - envelope area;
  - building volume;
  - surface amplification, `A_env / A_0`;
  - 3D compactness, `C_3D`;
- optional multifractal spectrum, `D_q`, for the building-footprint mass field;
- multiscale morphology and topology under disk dilation, `X_r = X ⊕ B_r`:
  - area profile, `A(r)`;
  - lattice perimeter profile, `P(r)`;
  - connected-component profile, `beta0(r)`;
  - hole profile, `beta1(r)`;
  - Euler characteristic, `chi(r) = beta0(r) - beta1(r)`;
  - largest-component fraction, `G(r)`;
  - critical connectivity radius, `r_c`;
  - integral archipelago, void, and boundary-complexity indices;
- resolution-sweep diagnostics for identifying grid-sensitive results;
- batch download and analysis workflows for catalogs of 100 and 200 cities.

## Scientific scope

The current implementation analyzes a **2D rasterized mask of building footprints** and an approximate **2.5D extruded building envelope**. The topological block tracks Betti numbers during morphological dilation. It is not yet a full persistent-homology analysis of a 3D point cloud, LiDAR surface, voxel model, or polygonal mesh.

The software is intended for exploratory research, comparative urban morphology, method development, and reproducible computational experiments. It should not be treated as a validated universal classifier of cities.

## Requirements

- Python 3.10 or newer;
- NumPy;
- pandas;
- GeoPandas;
- Shapely;
- pyproj;
- rasterio;
- Matplotlib;
- SciPy;
- optional: OSMnx for direct OpenStreetMap download;
- optional: pytest and Ruff for development.

## Installation

Clone the repository and create a virtual environment:

```bash
git clone https://github.com/aleks269/urban_fractal_topology.git
cd urban_fractal_topology

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Install direct OpenStreetMap download support:

```bash
python -m pip install -e '.[osm]'
```

Install development dependencies and run the tests:

```bash
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

## Quick start with local vector data

```bash
urban-fractal \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd \
  --pixel 25 \
  --default-height 15 \
  --topology \
  --multifractal
```

Supported vector formats include GeoJSON, GeoPackage, and Shapefile. The building layer should contain polygonal footprints.

The program attempts to obtain building height from one of the following fields:

```text
height
building:height
building:levels
levels
floors
этажность
```

If no usable height attribute is present, `--default-height` is used. When only the number of floors is available, height is estimated with `--floor-height`.

## Direct OpenStreetMap download

```bash
urban-fractal \
  --city "Saint Petersburg, Russia" \
  --out results/saint_petersburg_osm \
  --pixel 25 \
  --default-height 15 \
  --topology
```

This mode requires the optional `osm` dependencies and internet access. Large-city downloads through Nominatim and Overpass may fail because of geocoding ambiguity, timeouts, rate limits, or incomplete source data. For systematic studies, locally stored and manually verified extracts are preferable.

## Resolution sweep

Resolution-sweep mode repeats the same analysis at several raster pixel sizes:

```bash
urban-fractal \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd_resolution_sweep \
  --resolution-sweep 5 10 20 50 100 \
  --topology
```

The root output directory contains:

```text
results/zelenograd_resolution_sweep/
├── px_5m/
├── px_10m/
├── px_20m/
├── px_50m/
├── px_100m/
├── resolution_sweep_summary.csv
├── resolution_sweep_summary.json
└── resolution_sweep_stability.png
```

Each `px_*m` subdirectory is a complete single-resolution run. The summary compares raster size, foreground fraction, raster/vector area mismatch, `D_build`, fit quality, lacunarity, and topological descriptors.

Quality thresholds can be adjusted:

```bash
urban-fractal \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd_resolution_sweep \
  --resolution-sweep 5 10 20 50 100 \
  --topology \
  --sweep-max-area-error 0.05 \
  --sweep-min-r2 0.98 \
  --sweep-d-cv-threshold 0.05 \
  --sweep-rc-cv-threshold 0.10
```

The reported stable resolution interval is a diagnostic heuristic for rejecting obviously grid-dependent results. It is not proof of mathematical scale invariance.

## Topological analysis options

Automatic dilation radii:

```bash
urban-fractal \
  --buildings buildings.geojson \
  --boundary boundary.geojson \
  --out results/city_topology \
  --pixel 25 \
  --topology \
  --topology-max-radius-fraction 0.05 \
  --topology-n-radii 18
```

Manual radii in raster pixels:

```bash
urban-fractal \
  --buildings buildings.geojson \
  --boundary boundary.geojson \
  --out results/city_topology \
  --pixel 25 \
  --topology \
  --topology-radii 0,1,2,4,8,16,32,64
```

Connectivity conventions:

```text
--topology-connectivity 1    4-neighbour foreground connectivity
--topology-connectivity 2    8-neighbour foreground connectivity
```

The critical radius `r_c` is defined by the first dilation radius at which the largest connected component reaches the selected fraction of the built-up mask:

```bash
--giant-threshold 0.5
```

## Interpretation of topological descriptors

`beta0(r)` is the number of connected built-up components after dilation by radius `r`. Large values indicate fragmented or archipelago-like urban fabric.

`beta1(r)` is the number of holes in the dilated built-up mask. Peaks may correspond to characteristic scales of courtyards, parks, industrial voids, railway corridors, water barriers, or superblocks. Interpretation requires comparison with the source geometry.

`chi(r) = beta0(r) - beta1(r)` distinguishes component-dominated and hole-dominated scale ranges.

`G(r)` is the fraction of built pixels belonging to the largest connected component.

`r_c` is a finite-scale connectivity proxy. It depends on raster resolution, the selected boundary, connectivity convention, and the definition of the giant-component threshold.

## Output files

A normal run may produce:

```text
summary.json
box_counts_buildings.csv
scaling_window_candidates.csv
lacunarity_buildings.csv
building_mask.png
box_count_buildings.png
lacunarity_buildings.png
multifractal_spectrum_buildings.csv
```

With `--topology` enabled, additional files include:

```text
topology_minkowski_betti_profile.csv
minkowski_profile.png
betti_profile.png
percolation_profile.png
```

`summary.json` is the machine-readable city passport and should be treated as the primary output for downstream aggregation.

## Batch analysis of 100 or 200 cities

List the available 200-city catalog:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --list
```

Download a small pilot subset:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --sleep 5
```

Run a coarse pilot analysis:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode quick \
  --pixel 50 \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --continue-on-error \
  --skip-existing
```

Prepared shell scripts are available for full-catalog workflows:

```bash
bash scripts/download_200_cities.sh
bash scripts/run_200_quick.sh
bash scripts/run_200_sweep.sh
bash scripts/run_200_final_50m.sh
```

Do not start with the heaviest calculation on all 200 cities. First verify installation and data quality on a small subset, then run the coarse single-resolution mode, inspect failures, and only then start topological and resolution-sweep calculations.

Detailed instructions:

- [`docs/BATCH_100_CITIES.md`](docs/BATCH_100_CITIES.md)
- [`docs/CITY_CATALOG_200.md`](docs/CITY_CATALOG_200.md)
- [`urban_fractal_docs/QUICKSTART.md`](urban_fractal_docs/QUICKSTART.md)
- [`urban_fractal_docs/MANUAL.md`](urban_fractal_docs/MANUAL.md)

## Repository structure

```text
urban_fractal/          core Python package
batch_tools/            city download, batch execution, and aggregation tools
report_tools/           report-generation utilities
configs/                100-city and 200-city catalogs
scripts/                prepared shell workflows
examples/               example launch scripts
tests/                  automated tests
docs/                   batch-processing documentation
urban_fractal_docs/     detailed user documentation
data/zelenograd/         small example dataset
```

Downloaded city datasets, generated results, virtual environments, caches, and temporary files are excluded by `.gitignore`.

## Methodological limitations

1. `D_build` is a finite-scale 2D box-counting estimate for a rasterized footprint mask, not a universal fractal dimension of a city.
2. The selected scaling interval affects the fitted dimension and is therefore reported explicitly.
3. The approximate 2.5D model uses extruded footprints rather than detailed roofs or façade meshes:

   ```text
   roof_area = footprint_area * roof_factor
   wall_area = footprint_perimeter * height
   envelope_area = roof_area + wall_area
   ```

4. Building-height completeness strongly affects 2.5D outputs.
5. Topological descriptors depend on raster resolution, boundary selection, foreground/background connectivity, and dilation radii.
6. Administrative boundaries and OSM completeness differ between cities and can dominate cross-city comparisons.
7. Catalog morphotype labels are working metadata for grouping, not classifications inferred by the algorithm.

## Tests

Run the automated test suite from the repository root:

```bash
python -m pytest -q
```

The current tests cover:

- box-counting dimension of a filled square;
- lacunarity of a uniform mask;
- 2D and 3D compactness functions;
- synthetic end-to-end pipeline execution;
- synthetic resolution sweep;
- Betti numbers of simple components and rings;
- component merging under morphological dilation.

## License and data attribution

The source code is released under the [MIT License](LICENSE).

The MIT License applies to the software code and original documentation in this repository. It does not replace licenses attached to third-party datasets or dependencies.

OpenStreetMap-derived data are provided by **© OpenStreetMap contributors** and are subject to the **Open Database License (ODbL)**. Users are responsible for preserving the required attribution and for checking the licensing terms of any other input datasets.

## Citation

Until a versioned release and DOI are published, cite the repository and the exact software version used. A temporary software citation is:

```text
Aglikov, A. (2026). UrbanFractal Topology (Version 0.3.0) [Computer software].
GitHub repository: https://github.com/aleks269/urban_fractal_topology
```

For archival citation, a future tagged GitHub release can be deposited in Zenodo to obtain a version-specific DOI.

## Author

**Aleksandr Aglikov**  
GitHub: [`@aleks269`](https://github.com/aleks269)
