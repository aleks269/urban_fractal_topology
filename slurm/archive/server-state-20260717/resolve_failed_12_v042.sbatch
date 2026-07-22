#!/bin/bash

#SBATCH --job-name=uft-boundary12
#SBATCH --partition=research
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=02:00:00
#SBATCH --output=/home/aleks269/urban_fractal_logs/boundary12_%j.out
#SBATCH --error=/home/aleks269/urban_fractal_logs/boundary12_%j.err

set -uo pipefail

REPO="/home/aleks269/urban_fractal_topology"
PYTHON="$REPO/.venv/bin/python"

CATALOG="$REPO/configs/city_catalog_200.csv"
OVERRIDES="$REPO/make_city_files/boundary_osm_ids.json"

DATA_ROOT="/home/aleks269/urban_fractal_data/approved_cities"
CACHE_ROOT="/home/aleks269/urban_fractal_cache"

CITIES="athens,istanbul,tokyo,beijing,shanghai,ho_chi_minh_city,mumbai,lahore,riyadh,jeddah,johannesburg,cape_town"

cd "$REPO" || exit 2

echo "Job: ${SLURM_JOB_ID}"
echo "Started: $(date --iso-8601=seconds)"

"$PYTHON" batch_tools/download_city_catalog.py \
    --catalog "$CATALOG" \
    --out "$DATA_ROOT" \
    --set all \
    --cities "$CITIES" \
    --boundaries-only \
    --boundary-overrides "$OVERRIDES" \
    --cache-folder "$CACHE_ROOT" \
    --requests-timeout 300 \
    --sleep 1.1

STATUS=$?

echo "Exit code: $STATUS"
echo "Finished: $(date --iso-8601=seconds)"

exit "$STATUS"
