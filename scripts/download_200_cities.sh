#!/usr/bin/env bash
set -euo pipefail
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --set all \
  --sleep 5
