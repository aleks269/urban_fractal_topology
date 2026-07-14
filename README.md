# UrbanFractal Topology 0.4.0

`urban-fractal` is a boundary-aware pipeline for finite-scale analysis of urban building-footprint masks. It computes geometric, fractal, lacunarity, digital-topology, multifractal, approximate 2.5D and two-phase transport descriptors.

This version does not treat the bounding rectangle as part of the city. Every raster metric is restricted to the rasterized analysis boundary.

## Main calculations

### 2D morphology

- building fraction inside the analysis domain;
- boundary area, perimeter and boundary compactness;
- multi-origin box-counting estimate `D_build` on a fixed physical scale interval;
- grid-origin and leave-one-scale-out stability diagnostics;
- domain-aware gliding-box lacunarity;
- multifractal spectrum `D_q` with zero padding and per-scale probability normalization.

### Digital topology

The foreground and background use a dual 4/8-connectivity convention. Holes are defined relative to the irregular analysis domain.

The topology profile under dilation reports:

- `beta0(r)`, `beta1(r)` and `chi(r)`;
- Crofton perimeter and occupied area;
- largest-component fraction;
- directional left-right and top-bottom spanning indicators;
- `giant_component_radius_m`;
- `spanning_radius_lr_m` and `spanning_radius_tb_m`.

The giant-component radius is not called a percolation radius. True finite-domain percolation is represented by boundary-spanning connectivity.

### Approximate 2.5D geometry

Building footprints are extruded by height layers. Polygon unions are used so overlapping footprints and shared internal walls are not counted as external envelope.

Separate quantities are reported for:

- roof area;
- exposed wall area;
- open thermal envelope `roof + exposed walls`;
- ground-contact area;
- closed geometric surface;
- volume;
- thermal surface-to-volume ratio;
- closed-surface isoperimetric compactness.

Unknown heights use the configured default only as a model assumption. The output records height completeness by feature count and by footprint area and writes sensitivity scenarios to `height_sensitivity_2_5d.csv`.

### Two-phase stationary transport

With `--transport`, the program solves

```text
div(k grad u) = 0
```

on the irregular raster domain using harmonic interface conductivities. It evaluates both phase interpretations:

- open space as the conducting phase;
- buildings as the conducting phase.

For left-right and top-bottom excitation it reports conductance, resistance, fixed-potential dissipation, fixed-unit-flux dissipation, relative conductance, anisotropy and the energy-identity error. If a large domain is explicitly coarsened, the actual transport pixel size and coarsening factor are recorded.

## Installation

Python 3.11 or newer is required.

```bash
cd urban_fractal_topology_25m_v040
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

## Single-city run

```bash
python -m urban_fractal.cli \
  --buildings data/zelenograd/buildings.geojson \
  --boundary data/zelenograd/boundary.geojson \
  --out results/zelenograd_25m \
  --pixel 25 \
  --min-scaling-points 6 \
  --scaling-min-m 50 \
  --scaling-max-m 3200 \
  --topology \
  --multifractal \
  --transport
```

Pixel-centre rasterization (`all_touched=False`) is the default. The legacy `--all-touched` option remains available only for sensitivity tests.

## Main output files

```text
summary.json
analysis_masks.npz
analysis_domain_mask.png
building_mask.png
box_counts_buildings.csv
scaling_window_candidates_diagnostic.csv
box_count_buildings.png
lacunarity_buildings.csv
lacunarity_buildings.png
topology_minkowski_betti_profile.csv
minkowski_profile.png
betti_profile.png
percolation_profile.png
multifractal_spectrum_buildings.csv
multifractal_raw_buildings.csv
height_sensitivity_2_5d.csv
transport_results.csv
transport_potential_*.png
```

## Batch run for 200 cities at 25 m

```bash
chmod +x scripts/run_all_200_25m_external.sh
bash scripts/run_all_200_25m_external.sh /Volumes/aglikflash
```

The script:

1. creates or reuses `~/.venvs/urban-fractal-25m`;
2. runs the complete test suite;
3. downloads the 200-city catalog;
4. runs boundary-aware `final` analysis at 25 m;
5. rebuilds per-city and global reports;
6. runs the quality audit;
7. runs quality-aware statistical post-processing.

Existing results are skipped only when their `software.version` matches the current version. Results from older methodologies are recalculated.

The main outputs are:

```text
/Volumes/aglikflash/urban_fractal_200_25m/results/all_results_index.html
/Volumes/aglikflash/urban_fractal_200_25m/results/analysis_25m/auto_analysis_report.html
/Volumes/aglikflash/urban_fractal_200_25m/audit/audit_final_25m.csv
```

## Quality interpretation

A completed run is not automatically a scientifically admissible city. The audit checks method version, boundary availability, raster area agreement, box-counting fit and stability, directional spanning fields, transport presence and the energy identity.

The program cannot infer independent OSM completeness from OSM alone. It records this limitation explicitly. The 2.5D block remains model-dependent when height tags are incomplete. Water, vegetation, roads and independent thermal or energy observations are not created from building-boundary input and must be supplied separately for empirical urban-dissipation studies.

See `CORRECTIONS_V040.md` for the implemented corrections and validation results.

## Slurm cluster execution

Prepared Slurm array, environment, finalization and Moscow-only scripts are in
`slurm/`. See `slurm/README_SLURM.md`.
