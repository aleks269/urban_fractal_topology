from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


def flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, (list, tuple)):
            out[key] = json.dumps(v, ensure_ascii=False)
        else:
            out[key] = v
    return out


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect UrbanFractal summary.json files from batch results into one CSV.")
    parser.add_argument("--results-root", default="results/batch_100")
    parser.add_argument("--mode", choices=["quick", "topology", "sweep", "final", "all"], default="all")
    parser.add_argument("--out", default="results/batch_100/city_features_summary.csv")
    args = parser.parse_args()

    root = Path(args.results_root)
    modes = ["quick", "topology", "sweep", "final"] if args.mode == "all" else [args.mode]
    rows: list[dict[str, Any]] = []

    for mode in modes:
        mode_root = root / mode
        if not mode_root.exists():
            continue
        if mode == "sweep":
            for summary_path in mode_root.glob("*/*/resolution_sweep_summary.json"):
                data = read_json(summary_path)
                base = {
                    "mode": mode,
                    "subset": summary_path.parts[-3],
                    "slug": summary_path.parts[-2],
                    "summary_path": str(summary_path),
                }
                stable = data.get("stable_window") or {}
                global_stats = data.get("global_stability") or {}
                rows.append({**base, **flatten(stable, "stable_window"), **flatten(global_stats, "global_stability")})
        else:
            for summary_path in mode_root.glob("*/*/summary.json"):
                data = read_json(summary_path)
                base = {
                    "mode": mode,
                    "subset": summary_path.parts[-3],
                    "slug": summary_path.parts[-2],
                    "summary_path": str(summary_path),
                }
                rows.append({**base, **flatten(data)})

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({k for row in rows for k in row.keys()}) if rows else ["status"]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Rows: {len(rows)}")
    print("Written:", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
