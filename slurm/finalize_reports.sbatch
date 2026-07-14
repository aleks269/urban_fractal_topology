#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${RUN_ROOT:?RUN_ROOT is required}"
: "${VENV_DIR:?VENV_DIR is required}"

if command -v module >/dev/null 2>&1 && [[ -n "${UF_PYTHON_MODULE:-}" ]]; then
  module load "$UF_PYTHON_MODULE"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"
export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

cd "$PROJECT_ROOT"
RESULTS_ROOT="$RUN_ROOT/results"
AUDIT_ROOT="$RUN_ROOT/audit"
CATALOG="$PROJECT_ROOT/configs/city_catalog_200.csv"
DATA_ROOT="$RUN_ROOT/data/approved_cities"
mkdir -p "$RESULTS_ROOT" "$AUDIT_ROOT" "$RUN_ROOT/logs"

python batch_tools/collect_city_summaries.py \
  --results-root "$RESULTS_ROOT" \
  --mode final \
  --out "$RESULTS_ROOT/city_features_final_25m.csv"

python report_tools/make_all_reports.py --root "$RESULTS_ROOT"

python batch_tools/audit_200_25m.py \
  --catalog "$CATALOG" \
  --data-root "$DATA_ROOT" \
  --results-root "$RESULTS_ROOT" \
  --mode final \
  --out "$AUDIT_ROOT/audit_final_25m.csv" \
  --max-area-error 0.05 \
  --max-boundary-area-error 0.03 \
  --min-fractal-r2 0.95 \
  --min-fractal-points 6 \
  --max-fractal-offset-cv 0.05 \
  --max-fractal-loo-cv 0.05 \
  --max-energy-error 1e-5

python report_tools/postprocess_200_25m.py \
  --run-root "$RUN_ROOT" \
  --project-root "$PROJECT_ROOT"

cat > "$RUN_ROOT/RUN_COMPLETE.txt" <<EOF
Completed: $(date '+%Y-%m-%dT%H:%M:%S%z')
Project: $PROJECT_ROOT
Data: $DATA_ROOT
Results: $RESULTS_ROOT
Summary CSV: $RESULTS_ROOT/city_features_final_25m.csv
Global HTML report: $RESULTS_ROOT/all_results_index.html
Statistical analysis report: $RESULTS_ROOT/analysis_25m/auto_analysis_report.html
Final audit CSV: $AUDIT_ROOT/audit_final_25m.csv
Final audit JSON: $AUDIT_ROOT/audit_final_25m.json
EOF

printf '\nFinalization complete.\n'
printf 'Audit: %s\n' "$AUDIT_ROOT/audit_final_25m.csv"
printf 'Report: %s\n' "$RESULTS_ROOT/all_results_index.html"
printf 'Statistical report: %s\n' "$RESULTS_ROOT/analysis_25m/auto_analysis_report.html"
