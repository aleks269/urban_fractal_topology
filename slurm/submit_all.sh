#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_ROOT="${RUN_ROOT:-${SCRATCH:-$HOME}/urban_fractal_200_25m}"
VENV_DIR="${UF_ENV_ROOT:-${SCRATCH:-$HOME}/.venvs/urban-fractal-v040}"
MAX_CONCURRENT="${UF_MAX_CONCURRENT:-4}"
CITY_TIME="${UF_CITY_TIME:-24:00:00}"
CITY_MEM="${UF_CITY_MEM:-32G}"
CITY_CPUS="${UF_CITY_CPUS:-2}"
FINAL_TIME="${UF_FINAL_TIME:-08:00:00}"
FINAL_MEM="${UF_FINAL_MEM:-16G}"
FINAL_CPUS="${UF_FINAL_CPUS:-2}"

mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/results" "$RUN_ROOT/audit" "$RUN_ROOT/data/approved_cities"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Virtual environment not found: $VENV_DIR" >&2
  echo "Run first: bash $PROJECT_ROOT/slurm/create_env.sh" >&2
  exit 3
fi

if [[ ! -f "$RUN_ROOT/data/approved_cities/russia/moscow/boundary.geojson" ]]; then
  echo "Input data do not appear to be present under:" >&2
  echo "  $RUN_ROOT/data/approved_cities" >&2
  echo "Upload the approved_cities directory before submission." >&2
  exit 4
fi

COMMON_EXPORT="ALL,PROJECT_ROOT=$PROJECT_ROOT,RUN_ROOT=$RUN_ROOT,VENV_DIR=$VENV_DIR"
if [[ -n "${UF_PYTHON_MODULE:-}" ]]; then
  COMMON_EXPORT+=",UF_PYTHON_MODULE=$UF_PYTHON_MODULE"
fi

SBATCH_SITE=()
[[ -n "${UF_PARTITION:-}" ]] && SBATCH_SITE+=(--partition="$UF_PARTITION")
[[ -n "${UF_ACCOUNT:-}" ]] && SBATCH_SITE+=(--account="$UF_ACCOUNT")
[[ -n "${UF_QOS:-}" ]] && SBATCH_SITE+=(--qos="$UF_QOS")

ARRAY_JOB_ID="$(sbatch --parsable \
  "${SBATCH_SITE[@]}" \
  --job-name=uf25-city \
  --array="0-199%${MAX_CONCURRENT}" \
  --time="$CITY_TIME" \
  --mem="$CITY_MEM" \
  --cpus-per-task="$CITY_CPUS" \
  --output="$RUN_ROOT/logs/city_%A_%a.out" \
  --error="$RUN_ROOT/logs/city_%A_%a.err" \
  --export="$COMMON_EXPORT" \
  "$PROJECT_ROOT/slurm/run_city_array.sbatch")"

echo "City array submitted: $ARRAY_JOB_ID"

FINAL_JOB_ID="$(sbatch --parsable \
  "${SBATCH_SITE[@]}" \
  --job-name=uf25-finalize \
  --dependency="afterany:${ARRAY_JOB_ID}" \
  --time="$FINAL_TIME" \
  --mem="$FINAL_MEM" \
  --cpus-per-task="$FINAL_CPUS" \
  --output="$RUN_ROOT/logs/finalize_%j.out" \
  --error="$RUN_ROOT/logs/finalize_%j.err" \
  --export="$COMMON_EXPORT" \
  "$PROJECT_ROOT/slurm/finalize_reports.sbatch")"

echo "Finalizer submitted: $FINAL_JOB_ID (after any completion state of array $ARRAY_JOB_ID)"
echo "Monitor: squeue -j $ARRAY_JOB_ID,$FINAL_JOB_ID"
echo "Run root: $RUN_ROOT"
