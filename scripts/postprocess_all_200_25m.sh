#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME_ROOT="${1:-/Volumes/aglikflash}"
RUN_ROOT="${VOLUME_ROOT}/urban_fractal_200_25m"
VENV_DIR="${URBAN_FRACTAL_VENV:-${HOME}/.venvs/urban-fractal-25m}"

if [[ ! -d "${RUN_ROOT}/results" ]]; then
  echo "ERROR: results directory not found: ${RUN_ROOT}/results" >&2
  exit 2
fi
if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "ERROR: project virtual environment not found: ${VENV_DIR}" >&2
  echo "Run the main 200-city script first." >&2
  exit 3
fi

source "${VENV_DIR}/bin/activate"
export MPLBACKEND=Agg
cd "${PROJECT_ROOT}"

# Rebuild basic per-city and global reports from all completed summary.json files.
python batch_tools/collect_city_summaries.py \
  --results-root "${RUN_ROOT}/results" \
  --mode final \
  --out "${RUN_ROOT}/results/city_features_final_25m.csv"

python report_tools/make_all_reports.py \
  --root "${RUN_ROOT}/results"

# Run quality-aware statistical processing and open the final report.
python report_tools/postprocess_200_25m.py \
  --run-root "${RUN_ROOT}" \
  --project-root "${PROJECT_ROOT}" \
  --open
