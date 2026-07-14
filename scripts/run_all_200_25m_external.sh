#!/usr/bin/env bash
set -Eeuo pipefail

# Keep macOS awake for a long download/calculation run.
if [[ "${URBAN_FRACTAL_CAFFEINATED:-0}" != "1" ]] && command -v caffeinate >/dev/null 2>&1; then
  export URBAN_FRACTAL_CAFFEINATED=1
  exec caffeinate -dimsu "$0" "$@"
fi

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VOLUME_ROOT="${1:-/Volumes/aglikflash}"
RUN_ROOT="${VOLUME_ROOT}/urban_fractal_200_25m"
DATA_ROOT="${RUN_ROOT}/data/approved_cities"
RESULTS_ROOT="${RUN_ROOT}/results"
LOG_ROOT="${RUN_ROOT}/logs"
AUDIT_ROOT="${RUN_ROOT}/audit"
VENV_DIR="${URBAN_FRACTAL_VENV:-${HOME}/.venvs/urban-fractal-25m}"
CATALOG="${PROJECT_ROOT}/configs/city_catalog_200.csv"

if [[ ! -d "${VOLUME_ROOT}" ]]; then
  echo "ERROR: volume is not mounted: ${VOLUME_ROOT}" >&2
  exit 2
fi

mkdir -p "${RUN_ROOT}" "${DATA_ROOT}" "${RESULTS_ROOT}" "${LOG_ROOT}" "${AUDIT_ROOT}"
if ! touch "${RUN_ROOT}/.write_test" 2>/dev/null; then
  echo "ERROR: volume is not writable: ${VOLUME_ROOT}" >&2
  exit 3
fi
rm -f "${RUN_ROOT}/.write_test"

STAMP="$(date '+%Y%m%d_%H%M%S')"
MASTER_LOG="${LOG_ROOT}/run_${STAMP}.log"
exec > >(tee -a "${MASTER_LOG}") 2>&1

on_error() {
  local rc=$?
  echo
  echo "FAILED with exit code ${rc}. See log: ${MASTER_LOG}"
  exit "${rc}"
}
trap on_error ERR

export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg

printf '\nUrbanFractal 200 cities / 25 m\n'
printf 'Project: %s\n' "${PROJECT_ROOT}"
printf 'External run root: %s\n' "${RUN_ROOT}"
printf 'Data: %s\n' "${DATA_ROOT}"
printf 'Results: %s\n' "${RESULTS_ROOT}"
printf 'Log: %s\n\n' "${MASTER_LOG}"
df -h "${VOLUME_ROOT}" || true

cd "${PROJECT_ROOT}"

PYTHON_BIN="${URBAN_FRACTAL_PYTHON:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "${candidate}" >/dev/null 2>&1 && \
       "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PYTHON_BIN="$(command -v "${candidate}")"
      break
    fi
  done
fi

if [[ -z "${PYTHON_BIN}" ]] || [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "ERROR: Python >= 3.11 was not found. Install a current Homebrew Python first." >&2
  exit 4
fi

"${PYTHON_BIN}" - <<'PYCODE'
import sys
print("System Python:", sys.executable, sys.version.split()[0])
PYCODE

if [[ -x "${VENV_DIR}/bin/python" ]] && \
   ! "${VENV_DIR}/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "Recreating incompatible virtual environment: ${VENV_DIR}"
  rm -rf "${VENV_DIR}"
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment: ${VENV_DIR}"
  mkdir -p "$(dirname "${VENV_DIR}")"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1090
source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'

printf '\n[1/7] Test suite\n'
python -m pytest -q

printf '\n[2/7] Download all 200 city boundaries and building footprints\n'
python batch_tools/download_city_catalog.py \
  --catalog "${CATALOG}" \
  --out "${DATA_ROOT}" \
  --set all \
  --sleep 5

printf '\n[3/7] Audit downloaded data\n'
python batch_tools/audit_200_25m.py \
  --catalog "${CATALOG}" \
  --data-root "${DATA_ROOT}" \
  --results-root "${RESULTS_ROOT}" \
  --mode final \
  --out "${AUDIT_ROOT}/audit_before_calculation.csv"

printf '\n[4/7] Final 25 m analysis: boundary-aware metrics, topology, multifractals and transport\n'
python batch_tools/run_city_batch.py \
  --catalog "${CATALOG}" \
  --data-root "${DATA_ROOT}" \
  --results-root "${RESULTS_ROOT}" \
  --set all \
  --mode final \
  --pixel 25 \
  --continue-on-error \
  --skip-existing

printf '\n[5/7] Collect tables and generate base reports\n'
python batch_tools/collect_city_summaries.py \
  --results-root "${RESULTS_ROOT}" \
  --mode final \
  --out "${RESULTS_ROOT}/city_features_final_25m.csv"

python report_tools/make_all_reports.py \
  --root "${RESULTS_ROOT}"

printf '\n[6/7] Final quality audit\n'
python batch_tools/audit_200_25m.py \
  --catalog "${CATALOG}" \
  --data-root "${DATA_ROOT}" \
  --results-root "${RESULTS_ROOT}" \
  --mode final \
  --out "${AUDIT_ROOT}/audit_final_25m.csv" \
  --max-area-error 0.05 \
  --max-boundary-area-error 0.03 \
  --min-fractal-r2 0.95 \
  --min-fractal-points 6 \
  --max-fractal-offset-cv 0.05 \
  --max-fractal-loo-cv 0.05 \
  --max-energy-error 1e-5

printf '\n[7/7] Quality-aware statistical post-processing\n'
python report_tools/postprocess_200_25m.py \
  --run-root "${RUN_ROOT}" \
  --project-root "${PROJECT_ROOT}"

cat > "${RUN_ROOT}/RUN_COMPLETE.txt" <<EOF
Completed: $(date '+%Y-%m-%dT%H:%M:%S%z')
Project: ${PROJECT_ROOT}
Data: ${DATA_ROOT}
Results: ${RESULTS_ROOT}
Summary CSV: ${RESULTS_ROOT}/city_features_final_25m.csv
Global HTML report: ${RESULTS_ROOT}/all_results_index.html
Statistical analysis report: ${RESULTS_ROOT}/analysis_25m/auto_analysis_report.html
Final audit CSV: ${AUDIT_ROOT}/audit_final_25m.csv
Final audit JSON: ${AUDIT_ROOT}/audit_final_25m.json
Master log: ${MASTER_LOG}
EOF

printf '\nDONE\n'
printf 'Global report: %s\n' "${RESULTS_ROOT}/all_results_index.html"
printf 'Statistical report: %s\n' "${RESULTS_ROOT}/analysis_25m/auto_analysis_report.html"
printf 'Final audit: %s\n' "${AUDIT_ROOT}/audit_final_25m.csv"
printf 'Master log: %s\n' "${MASTER_LOG}"
