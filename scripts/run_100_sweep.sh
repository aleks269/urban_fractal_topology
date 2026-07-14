#!/usr/bin/env bash
set -euo pipefail

python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --set all \
  --mode sweep \
  --resolution-sweep 10 20 50 \
  --resolution-sweep-continue-on-error \
  --continue-on-error \
  --skip-existing \
  --sweep-max-area-error 0.05 \
  --sweep-min-r2 0.98 \
  --sweep-d-cv-threshold 0.05 \
  --sweep-rc-cv-threshold 0.10

python batch_tools/collect_city_summaries.py \
  --results-root results/batch_100 \
  --mode sweep \
  --out results/batch_100/city_features_sweep.csv
