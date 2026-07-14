#!/usr/bin/env bash
set -euo pipefail
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode sweep \
  --resolution-sweep 10 20 50 \
  --set all \
  --resolution-sweep-continue-on-error \
  --continue-on-error \
  --skip-existing

python batch_tools/collect_city_summaries.py \
  --results-root results/batch_200 \
  --mode sweep \
  --out results/batch_200/city_features_sweep.csv
