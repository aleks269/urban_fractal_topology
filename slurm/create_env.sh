#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_ROOT="${UF_ENV_ROOT:-${SCRATCH:-$HOME}/.venvs/urban-fractal-v041}"
PYTHON_MODULE="${UF_PYTHON_MODULE:-}"
INSTALL_OSM="${UF_INSTALL_OSM:-0}"

if command -v module >/dev/null 2>&1 && [[ -n "$PYTHON_MODULE" ]]; then
  module load "$PYTHON_MODULE"
fi

PYTHON_BIN="${UF_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && \
       "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
      PYTHON_BIN="$(command -v "$candidate")"
      break
    fi
  done
fi

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Python >= 3.11 not found. Load a cluster Python module first, for example:" >&2
  echo "  module spider python" >&2
  echo "  module load <python-module>" >&2
  echo "Then rerun with UF_PYTHON_MODULE=<module-name> or UF_PYTHON_BIN=/path/to/python3.11." >&2
  exit 4
fi

mkdir -p "$(dirname "$ENV_ROOT")"
if [[ ! -x "$ENV_ROOT/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$ENV_ROOT"
fi

# shellcheck disable=SC1091
source "$ENV_ROOT/bin/activate"
python -m pip install --upgrade pip setuptools wheel
if [[ "$INSTALL_OSM" == "1" ]]; then
  python -m pip install -e "$PROJECT_ROOT[osm,dev]"
else
  python -m pip install -e "$PROJECT_ROOT[dev]"
fi

python - <<'PY'
import sys
import numpy, pandas, geopandas, shapely, pyproj, rasterio, scipy, skimage
import urban_fractal
print("Python:", sys.executable, sys.version.split()[0])
print("UrbanFractal:", urban_fractal.__version__)
print("Environment OK")
PY

python -m pytest -q "$PROJECT_ROOT/tests"
printf '\nEnvironment created: %s\n' "$ENV_ROOT"
printf 'Use: export UF_ENV_ROOT=%q\n' "$ENV_ROOT"
