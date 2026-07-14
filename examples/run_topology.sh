#!/usr/bin/env bash
set -euo pipefail

urban-fractal \
  --buildings data/buildings.geojson \
  --boundary data/boundary.geojson \
  --out results/topology \
  --pixel 25 \
  --default-height 15 \
  --topology \
  --topology-radii 0,1,2,4,8,16,32,64 \
  --multifractal
