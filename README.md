# UrbanFractal Topology 0.4.1

`urban-fractal` is a boundary-aware research pipeline for finite-scale analysis of urban building morphology. It combines raster geometry, box-counting, lacunarity, digital topology under Minkowski dilation, two explicitly separated multifractal measures, approximate 2.5D building geometry and stationary two-phase transport.

The software treats the supplied city boundary as the analysis domain. Pixels of the enclosing rectangle that lie outside the boundary are excluded from every raster calculation.

## Scientific scope

The package computes morphological and model-response descriptors from building footprints and optional OSM height attributes. It does **not** infer real urban heat release, energy use or entropy production from geometry alone. Such claims require independent thermal, meteorological or energy observations.

The exact definitions, equations, normalization rules and admissibility conditions are specified in [docs/MATHEMATICAL_METHODS.md](docs/MATHEMATICAL_METHODS.md).

## Main calculations

### Boundary-aware 2D morphology

- building fraction inside the rasterized analysis boundary;
- vector/raster area consistency diagnostics;
- multi-origin box-counting exponent `D_build` on a fixed physical scale interval;
- grid-origin and leave-one-scale-out stability;
- domain-aware gliding-box lacunarity.

### Digital topology under dilation

For each dilation radius the program computes occupied area, Crofton perimeter, `beta0`, `beta1`, Euler characteristic, largest-component fraction and directional spanning.

Version 0.4.1 reports both:

- full-domain bounding-box spanning;
- largest-domain-component spanning for administrative domains with detached exclaves.

It also stores raw topology integrals and size-reduced normalized variants. Normalized per-city variants retain their own sampled interval and are diagnostic. Final atlas post-processing recomputes the principal topology integrals on the common intersection of the relative-radius coordinate \(\rho=r/\sqrt{A_\Omega}\) across quality-eligible cities.

### Multifractal measures

Two spectra are deliberately kept separate:

1. **footprint-area measure** — uniform mass per occupied raster cell;
2. **height-weighted built-form measure** — rasterized building height per occupied cell.

The binary footprint raster is a valid measure because box mass is the occupied area within the box. The height-weighted field is an alternative 2.5D measure, not a mathematical correction of the footprint measure, and it is partly model-dependent where default heights are used.

The program reports `D_q`, scaling-fit diagnostics and an uncertainty-aware check of the theoretical non-increasing order of `D_q(q)`. Poorly fitted orders remain in the files but are marked `fit_pass = false`. Negative orders are retained as diagnostics; principal atlas features require `atlas_eligible = true`, i.e. a passed fit and `q >= 0`.

### Approximate 2.5D geometry

Building footprints are extruded by height layers. Polygon unions prevent double counting of overlaps and shared internal walls. Outputs include volume, exposed roof, exposed wall area, thermal envelope, closed geometric surface, surface-to-volume ratio and closed-surface isoperimetric compactness.

### Two-phase stationary transport

With `--transport`, the program solves

```text
div(k grad u) = 0
```

on the irregular raster domain using a finite-volume scheme and harmonic interface conductivities. Open space and buildings can each be treated as the high-conductivity phase. Left–right and top–bottom calculations report conductance, resistance, dissipation, anisotropy and the energy-identity residual.

## Installation

Python 3.11 or newer is required.

```bash
cd urban_fractal_topology
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

Validated suite:

```text
31 passed
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

Pixel-centre rasterization (`all_touched=False`) is the default. `--all-touched` is retained for sensitivity testing only.

## Main output files

```text
summary.json
analysis_masks.npz
analysis_domain_mask.png
building_mask.png
box_counts_buildings.csv
scaling_window_candidates_diagnostic.csv
lacunarity_buildings.csv
topology_minkowski_betti_profile.csv
multifractal_spectrum_buildings.csv
multifractal_raw_buildings.csv
multifractal_spectrum_height_weighted.csv
multifractal_raw_height_weighted.csv
height_sensitivity_2_5d.csv
transport_results.csv
```

`analysis_masks.npz` contains the binary building mask, domain mask, pixel size and, when multifractal analysis is enabled, the rasterized building-height field.

## Batch run for 200 cities on a personal workstation

```bash
chmod +x scripts/run_all_200_25m_external.sh
bash scripts/run_all_200_25m_external.sh /Volumes/aglikflash
```

The workflow tests the package, checks/downloads the city catalog, runs the fixed 25 m analysis, rebuilds reports, audits quality and performs quality-aware post-processing. Existing results are reused only when the software version and critical method parameters match.

## Slurm execution

The unified repository includes an array-job wrapper under `slurm/`. See `slurm/README_SLURM.md`. Each array task processes one city, writes an atomic manifest and can use node-local scratch while retaining outputs on shared storage.

## Quality interpretation

A completed command is not automatically a scientifically admissible city. Atlas-level use should filter by:

- boundary source and raster area errors;
- box-counting fit, scale span and stability;
- topology radius interval and disconnected-domain status;
- multifractal per-order fit flags;
- height completeness for height-weighted and 2.5D descriptors;
- transport convergence and energy identity.

See [CORRECTIONS_V041.md](CORRECTIONS_V041.md) for the reviewed changes from 0.4.0 and [CORRECTIONS_V040.md](CORRECTIONS_V040.md) for the preceding boundary-aware corrections.

## License and data attribution

Code is released under the MIT License. OpenStreetMap-derived data remain subject to the Open Database License and require attribution to OpenStreetMap contributors.

## Citation

Until an archived release DOI is issued, cite the repository and the exact tagged software version used in the calculation. Results from versions 0.4.0 and 0.4.1 must not be silently pooled because the output schema and multifractal/topology diagnostics differ.
