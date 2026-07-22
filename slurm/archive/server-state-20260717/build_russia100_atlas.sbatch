#!/usr/bin/env bash
#SBATCH --job-name=uft-rus100-atlas
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=/home/aleks269/urban_fractal_logs/uft-rus100-atlas-%j.out
#SBATCH --error=/home/aleks269/urban_fractal_logs/uft-rus100-atlas-%j.err

set -euo pipefail

PROJECT="$HOME/urban_fractal_topology"
SOURCE_RUN="$HOME/urban_fractal_runs/full200_v042_20260715"
DATA_ROOT="$HOME/urban_fractal_data/approved_cities"

SNAPSHOT="$HOME/urban_fractal_runs/russia100_v042_20260716"
RESULTS="$SNAPSHOT/results"
AUDIT="$SNAPSHOT/audit"
ATLAS="$SNAPSHOT/interactive_atlas_russia100"

source "$PROJECT/.venv/bin/activate"

export PYTHONUNBUFFERED=1
export MPLBACKEND=Agg
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

cd "$PROJECT"

echo "============================================================"
echo "UrbanFractal Russia-100 intermediate atlas"
echo "Started: $(date --iso-8601=seconds)"
echo "Source run: $SOURCE_RUN"
echo "Snapshot: $SNAPSHOT"
echo "============================================================"

# Create a separate snapshot.
# The original full run is not modified.
rm -rf "$SNAPSHOT"

mkdir -p \
  "$RESULTS/final" \
  "$AUDIT"

# Create a hard-link snapshot of completed Russian results.
# Files are not physically duplicated when both directories
# are located on the same filesystem.
cp -al \
  "$SOURCE_RUN/results/final/russia" \
  "$RESULTS/final/russia"

RUSSIA_SUMMARIES=$(
  find "$RESULTS/final/russia" \
    -mindepth 2 -maxdepth 2 \
    -name summary.json -type f |
  wc -l
)

echo "Russian summaries in snapshot: $RUSSIA_SUMMARIES"

if [[ "$RUSSIA_SUMMARIES" -ne 100 ]]; then
    echo "ERROR: expected exactly 100 Russian summaries."
    exit 1
fi

# Create a catalog containing only the Russian subset.
python - <<'PY'
from pathlib import Path

import pandas as pd

project = Path.home() / "urban_fractal_topology"
snapshot = Path.home() / "urban_fractal_runs" / "russia100_v042_20260716"

source = project / "configs" / "city_catalog_200.csv"
target = snapshot / "city_catalog_russia100.csv"

df = pd.read_csv(source, dtype=str)

required_columns = {"slug", "subset"}
missing_columns = required_columns.difference(df.columns)

if missing_columns:
    missing_text = ", ".join(sorted(missing_columns))
    raise SystemExit(
        f"Missing required catalog columns: {missing_text}"
    )

russia = df.loc[df["subset"].eq("russia")].copy()

if len(russia) != 100:
    raise SystemExit(
        f"Expected 100 Russian cities in catalog, found {len(russia)}"
    )

russia.to_csv(target, index=False)

print(f"Russia catalog: {target}")
print(f"Rows: {len(russia)}")
print(f"First city: {russia.iloc[0]['slug']}")
print(f"Last city: {russia.iloc[-1]['slug']}")
PY

RUSSIA_CATALOG="$SNAPSHOT/city_catalog_russia100.csv"

echo
echo "=== COLLECT SUMMARIES ==="

python batch_tools/collect_city_summaries.py \
  --results-root "$RESULTS" \
  --mode final \
  --out "$RESULTS/city_features_final_25m.csv"

echo
echo "=== GENERATE INDIVIDUAL AND STATIC REPORTS ==="

python report_tools/make_all_reports.py \
  --root "$RESULTS"

echo
echo "=== AUDIT RUSSIAN BLOCK ==="

python batch_tools/audit_200_25m.py \
  --catalog "$RUSSIA_CATALOG" \
  --data-root "$DATA_ROOT" \
  --results-root "$RESULTS" \
  --mode final \
  --out "$AUDIT/audit_final_25m.csv" \
  --max-area-error 0.05 \
  --max-boundary-area-error 0.03 \
  --min-fractal-r2 0.95 \
  --min-fractal-points 6 \
  --max-fractal-offset-cv 0.05 \
  --max-fractal-loo-cv 0.05 \
  --max-energy-error 1e-5

echo
echo "=== STATISTICAL POSTPROCESSING ==="

python report_tools/postprocess_200_25m.py \
  --run-root "$SNAPSHOT" \
  --project-root "$PROJECT"

echo
echo "=== INTERACTIVE ATLAS ==="

python "$PROJECT/build_interactive_atlas_all200.py" \
  "$SNAPSHOT" \
  "$ATLAS" \
  --catalog "$PROJECT/configs/city_catalog_200.csv"

echo
echo "=== VALIDATION ==="

test -s "$ATLAS/index.html"

ATLAS_CITIES=$(
  find "$ATLAS/assets/cities" \
    -mindepth 1 -maxdepth 1 -type d 2>/dev/null |
  wc -l
)

echo "Atlas city directories: $ATLAS_CITIES"

python - <<'PY'
from pathlib import Path
import json

atlas_dir = (
    Path.home()
    / "urban_fractal_runs"
    / "russia100_v042_20260716"
    / "interactive_atlas_russia100"
)

index_path = atlas_dir / "index.html"
data_path = atlas_dir / "atlas_data.json"

if not index_path.is_file():
    raise SystemExit(
        f"ERROR: atlas file not found: {index_path}"
    )

if not data_path.is_file():
    raise SystemExit(
        f"ERROR: atlas data not found: {data_path}"
    )

data = json.loads(data_path.read_text(encoding="utf-8"))
cities = data.get("cities", [])

if len(cities) != 100:
    raise SystemExit(
        f"ERROR: expected 100 cities, found {len(cities)}"
    )

invalid = [
    city.get("slug", "<missing>")
    for city in cities
    if city.get("subset") not in (None, "", "russia")
]

if invalid:
    raise SystemExit(
        "ERROR: non-Russian cities detected: "
        + ", ".join(invalid[:20])
    )

slugs = [city.get("slug") for city in cities]

if "new_york" in slugs:
    raise SystemExit("ERROR: new_york detected")

if len(slugs) != len(set(slugs)):
    raise SystemExit("ERROR: duplicate slugs detected")

size_mib = index_path.stat().st_size / 1024 / 1024

print(f"Atlas cities: {len(cities)}")
print(f"index.html size: {size_mib:.2f} MiB")
print("Russia-only atlas validation: passed")
PY

echo
echo "=== PACKAGE ==="

tar -C "$SNAPSHOT" \
  -czf "$SNAPSHOT/interactive_atlas_russia100.tar.gz" \
  interactive_atlas_russia100

sha256sum \
  "$SNAPSHOT/interactive_atlas_russia100.tar.gz" \
  > "$SNAPSHOT/interactive_atlas_russia100.tar.gz.sha256"

echo
echo "============================================================"
echo "Completed: $(date --iso-8601=seconds)"
echo "Atlas:"
echo "  $ATLAS/index.html"
echo "Archive:"
echo "  $SNAPSHOT/interactive_atlas_russia100.tar.gz"
echo "Checksum:"
echo "  $SNAPSHOT/interactive_atlas_russia100.tar.gz.sha256"
echo "Statistical report:"
echo "  $RESULTS/analysis_25m/auto_analysis_report.html"
echo "Audit:"
echo "  $AUDIT/audit_final_25m.csv"
echo "============================================================"
