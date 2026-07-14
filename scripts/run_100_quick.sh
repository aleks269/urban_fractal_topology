#!/usr/bin/env bash
set -euo pipefail

python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --set all \
  --mode quick \
  --pixel 50 \
  --continue-on-error \
  --skip-existing

python batch_tools/collect_city_summaries.py \
  --results-root results/batch_100 \
  --mode quick \
  --out results/batch_100/city_features_quick.csv
