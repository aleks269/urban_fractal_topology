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
mkdir -p "$RUN_ROOT/results" "$RUN_ROOT/logs" "$RUN_ROOT/audit"

SCRATCH_ARG=()
if [[ -n "${SLURM_TMPDIR:-}" ]]; then
  SCRATCH_ARG=(--scratch "$SLURM_TMPDIR")
fi

python slurm/run_city_task.py \
  --catalog "$PROJECT_ROOT/configs/city_catalog_200.csv" \
  --data-root "$RUN_ROOT/data/approved_cities" \
  --results-root "$RUN_ROOT/results" \
  --index "$SLURM_ARRAY_TASK_ID" \
  --python "$VENV_DIR/bin/python" \
  --skip-existing \
  "${SCRATCH_ARG[@]}"
