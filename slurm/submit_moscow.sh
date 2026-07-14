#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
RUN_ROOT="${RUN_ROOT:-${SCRATCH:-$HOME}/urban_fractal_200_25m}"
VENV_DIR="${UF_ENV_ROOT:-${SCRATCH:-$HOME}/.venvs/urban-fractal-v040}"
MOSCOW_TIME="${UF_MOSCOW_TIME:-24:00:00}"
MOSCOW_MEM="${UF_MOSCOW_MEM:-64G}"
MOSCOW_CPUS="${UF_MOSCOW_CPUS:-4}"
mkdir -p "$RUN_ROOT/logs" "$RUN_ROOT/results" "$RUN_ROOT/audit"

COMMON_EXPORT="ALL,PROJECT_ROOT=$PROJECT_ROOT,RUN_ROOT=$RUN_ROOT,VENV_DIR=$VENV_DIR"
[[ -n "${UF_PYTHON_MODULE:-}" ]] && COMMON_EXPORT+=",UF_PYTHON_MODULE=$UF_PYTHON_MODULE"
SBATCH_SITE=()
[[ -n "${UF_PARTITION:-}" ]] && SBATCH_SITE+=(--partition="$UF_PARTITION")
[[ -n "${UF_ACCOUNT:-}" ]] && SBATCH_SITE+=(--account="$UF_ACCOUNT")
[[ -n "${UF_QOS:-}" ]] && SBATCH_SITE+=(--qos="$UF_QOS")

JOB_ID="$(sbatch --parsable \
  "${SBATCH_SITE[@]}" \
  --job-name=uf25-moscow \
  --array=0-0 \
  --time="$MOSCOW_TIME" \
  --mem="$MOSCOW_MEM" \
  --cpus-per-task="$MOSCOW_CPUS" \
  --output="$RUN_ROOT/logs/moscow_%A_%a.out" \
  --error="$RUN_ROOT/logs/moscow_%A_%a.err" \
  --export="$COMMON_EXPORT" \
  "$PROJECT_ROOT/slurm/run_city_array.sbatch")"

echo "Moscow job submitted: $JOB_ID"
echo "Monitor: squeue -j $JOB_ID"
