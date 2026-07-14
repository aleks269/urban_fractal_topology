#!/usr/bin/env bash
set -euo pipefail
urban-fractal \
  --buildings data/buildings.geojson \
  --boundary data/boundary.geojson \
  --out results/example \
  --pixel 25 \
  --default-height 15 \
  --multifractal
