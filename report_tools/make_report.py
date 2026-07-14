from __future__ import annotations

import argparse
import json
import html
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    pd = None


IMAGE_ORDER = [
    "analysis_domain_mask.png",
    "building_mask.png",
    "box_count_buildings.png",
    "lacunarity_buildings.png",
    "minkowski_profile.png",
    "betti_profile.png",
    "percolation_profile.png",
    "transport_potential_open_space_lr_contrast_1000.png",
    "transport_potential_open_space_tb_contrast_1000.png",
    "transport_potential_buildings_lr_contrast_1000.png",
    "transport_potential_buildings_tb_contrast_1000.png",
]

CSV_ORDER = [
    "box_counts_buildings.csv",
    "scaling_window_candidates_diagnostic.csv",
    "lacunarity_buildings.csv",
    "topology_minkowski_betti_profile.csv",
    "multifractal_spectrum_buildings.csv",
    "multifractal_raw_buildings.csv",
    "height_sensitivity_2_5d.csv",
    "transport_results.csv",
]


def flatten_dict(d, prefix=""):
    rows = []
    if not isinstance(d, dict):
        return [(prefix, d)]

    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            rows.extend(flatten_dict(v, key))
        else:
            rows.append((key, v))
    return rows


def safe_read_json(path: Path):
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def csv_preview_markdown(path: Path, max_rows: int = 12) -> str:
    if pd is None:
        return f"`pandas` не установлен; CSV доступен как файл: `{path.name}`\n"

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return f"Не удалось прочитать CSV `{path.name}`: `{e}`\n"

    if df.empty:
        return "_Пустая таблица._\n"

    return df.head(max_rows).to_markdown(index=False) + "\n"


def csv_preview_html(path: Path, max_rows: int = 12) -> str:
    if pd is None:
        return f"<p><code>pandas</code> не установлен; CSV доступен как файл: <code>{html.escape(path.name)}</code></p>"

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return f"<p>Не удалось прочитать CSV <code>{html.escape(path.name)}</code>: <code>{html.escape(str(e))}</code></p>"

    if df.empty:
        return "<p><em>Пустая таблица.</em></p>"

    return df.head(max_rows).to_html(index=False, border=0)


def make_markdown(results_dir: Path, city: str) -> str:
    summary = safe_read_json(results_dir / "summary.json")
    flat = flatten_dict(summary)

    lines = []
    lines.append(f"# UrbanFractal report: {city}")
    lines.append("")
    lines.append(f"Generated: `{datetime.now().isoformat(timespec='seconds')}`")
    lines.append(f"Results directory: `{results_dir}`")
    lines.append("")

    lines.append("## 1. Summary")
    lines.append("")
    if flat:
        lines.append("| Parameter | Value |")
        lines.append("|---|---:|")
        for k, v in flat:
            if isinstance(v, float):
                value = f"{v:.6g}"
            else:
                value = str(v)
            lines.append(f"| `{k}` | `{value}` |")
    else:
        lines.append("_Файл `summary.json` не найден или пуст._")
    lines.append("")

    lines.append("## 2. Figures")
    lines.append("")
    existing_images = []
    for name in IMAGE_ORDER:
        p = results_dir / name
        if p.exists():
            existing_images.append(p)

    for p in sorted(results_dir.glob("*.png")):
        if p not in existing_images:
            existing_images.append(p)

    if not existing_images:
        lines.append("_PNG-графики не найдены._")
    else:
        for p in existing_images:
            lines.append(f"### {p.name}")
            lines.append("")
            lines.append(f"![{p.name}]({p.name})")
            lines.append("")
    lines.append("")

    lines.append("## 3. Tables")
    lines.append("")
    existing_csv = []
    for name in CSV_ORDER:
        p = results_dir / name
        if p.exists():
            existing_csv.append(p)

    for p in sorted(results_dir.glob("*.csv")):
        if p not in existing_csv:
            existing_csv.append(p)

    if not existing_csv:
        lines.append("_CSV-таблицы не найдены._")
    else:
        for p in existing_csv:
            lines.append(f"### {p.name}")
            lines.append("")
            lines.append(csv_preview_markdown(p))
            lines.append("")
            lines.append(f"Full file: `{p.name}`")
            lines.append("")

    lines.append("## 4. Interpretation checklist")
    lines.append("")
    lines.append("- Проверить, что `analysis_domain_mask.png` соответствует реальной области анализа, а внешняя часть bounding box исключена.")
    lines.append("- Проверить, что `building_mask.png` корректно обрезана маской области анализа.")
    lines.append("- Проверить устойчивость box-counting по `r2`, `grid_offset_cv`, `leave_one_out_cv` и числу масштабов.")
    lines.append("- Не смешивать `giant_component_radius_m` с направленными spanning-радиусами; для межгородского сравнения использовать поля `*_recommended_m` и учитывать `spanning_reference_recommended`.")
    lines.append("- Сырые интегральные топологические индексы зависят от числа компонент, характерного размера и диапазона радиусов; для сравнения использовать нормированные индексы и одинаковый интервал радиусов.")
    lines.append("- Для multifractal учитывать только точки с `fit_pass=true`; различать footprint-area и height-weighted меры.")
    lines.append("- Для transport проверить энергетическое тождество и фактический `coarsening_factor`.")
    lines.append("- Сравнить результат при `pixel=100`, `50`, `25 м`; сильные скачки означают чувствительность к масштабу.")
    lines.append("- Для научного сравнения фиксировать источник данных, границу города, размер пикселя и диапазон масштабов.")
    lines.append("- Если высоты зданий отсутствуют, 2.5D-показатели являются модельными, а не измеренными.")
    lines.append("")

    return "\n".join(lines)


def make_html(results_dir: Path, city: str, markdown_text: str) -> str:
    summary = safe_read_json(results_dir / "summary.json")
    flat = flatten_dict(summary)

    parts = []
    parts.append("<!doctype html>")
    parts.append("<html lang='ru'>")
    parts.append("<head>")
    parts.append("<meta charset='utf-8'>")
    parts.append(f"<title>UrbanFractal report: {html.escape(city)}</title>")
    parts.append("""
<style>
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 40px;
  line-height: 1.45;
  color: #111;
}
h1, h2, h3 { margin-top: 1.4em; }
table {
  border-collapse: collapse;
  margin: 12px 0 24px 0;
  font-size: 14px;
}
th, td {
  border: 1px solid #ccc;
  padding: 6px 9px;
  text-align: left;
  vertical-align: top;
}
th { background: #f3f3f3; }
code {
  background: #f5f5f5;
  padding: 1px 4px;
  border-radius: 3px;
}
img {
  max-width: 100%;
  border: 1px solid #ddd;
  margin: 8px 0 24px 0;
}
.meta { color: #555; }
.warning {
  background: #fff7df;
  border-left: 4px solid #c58b00;
  padding: 10px 14px;
}
</style>
""")
    parts.append("</head>")
    parts.append("<body>")

    parts.append(f"<h1>UrbanFractal report: {html.escape(city)}</h1>")
    parts.append(f"<p class='meta'>Generated: <code>{datetime.now().isoformat(timespec='seconds')}</code></p>")
    parts.append(f"<p class='meta'>Results directory: <code>{html.escape(str(results_dir))}</code></p>")

    parts.append("<h2>1. Summary</h2>")
    if flat:
        parts.append("<table><thead><tr><th>Parameter</th><th>Value</th></tr></thead><tbody>")
        for k, v in flat:
            if isinstance(v, float):
                value = f"{v:.6g}"
            else:
                value = str(v)
            parts.append(f"<tr><td><code>{html.escape(str(k))}</code></td><td><code>{html.escape(value)}</code></td></tr>")
        parts.append("</tbody></table>")
    else:
        parts.append("<p><em>Файл <code>summary.json</code> не найден или пуст.</em></p>")

    parts.append("<h2>2. Figures</h2>")
    existing_images = []
    for name in IMAGE_ORDER:
        p = results_dir / name
        if p.exists():
            existing_images.append(p)
    for p in sorted(results_dir.glob("*.png")):
        if p not in existing_images:
            existing_images.append(p)

    if not existing_images:
        parts.append("<p><em>PNG-графики не найдены.</em></p>")
    else:
        for p in existing_images:
            parts.append(f"<h3>{html.escape(p.name)}</h3>")
            parts.append(f"<img src='{html.escape(p.name)}' alt='{html.escape(p.name)}'>")

    parts.append("<h2>3. Tables</h2>")
    existing_csv = []
    for name in CSV_ORDER:
        p = results_dir / name
        if p.exists():
            existing_csv.append(p)
    for p in sorted(results_dir.glob("*.csv")):
        if p not in existing_csv:
            existing_csv.append(p)

    if not existing_csv:
        parts.append("<p><em>CSV-таблицы не найдены.</em></p>")
    else:
        for p in existing_csv:
            parts.append(f"<h3>{html.escape(p.name)}</h3>")
            parts.append(csv_preview_html(p))
            parts.append(f"<p>Full file: <code>{html.escape(p.name)}</code></p>")

    parts.append("<h2>4. Interpretation checklist</h2>")
    parts.append("""
<ul>
<li>Проверить, что <code>analysis_domain_mask.png</code> соответствует реальной области анализа, а внешняя часть bounding box исключена.</li>
<li>Проверить, что <code>building_mask.png</code> корректно обрезана маской области анализа.</li>
<li>Проверить устойчивость box-counting по <code>r2</code>, <code>grid_offset_cv</code>, <code>leave_one_out_cv</code> и числу масштабов.</li>
<li>Не смешивать <code>giant_component_radius_m</code> с направленными spanning-радиусами; для межгородского сравнения использовать поля <code>*_recommended_m</code> и учитывать <code>spanning_reference_recommended</code>.</li>
<li>Сырые интегральные топологические индексы зависят от числа компонент, характерного размера и диапазона радиусов; для сравнения использовать нормированные индексы и одинаковый интервал радиусов.</li>
<li>Для multifractal учитывать только точки с <code>fit_pass=true</code>; различать footprint-area и height-weighted меры.</li>
<li>Для transport проверить энергетическое тождество и фактический <code>coarsening_factor</code>.</li>
<li>Сравнить результат при <code>pixel=100</code>, <code>50</code>, <code>25 м</code>; сильные скачки означают чувствительность к масштабу.</li>
<li>Для научного сравнения фиксировать источник данных, границу города, размер пикселя и диапазон масштабов.</li>
<li>Если высоты зданий отсутствуют, 2.5D-показатели являются модельными, а не измеренными.</li>
</ul>
""")

    parts.append("</body></html>")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", help="Path to UrbanFractal results directory")
    parser.add_argument("--city", default=None, help="City name for report title")
    parser.add_argument("--open", action="store_true", help="Open HTML report after creation on macOS")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    if not results_dir.exists():
        raise SystemExit(f"Results directory does not exist: {results_dir}")

    city = args.city or results_dir.name

    md = make_markdown(results_dir, city)
    html_text = make_html(results_dir, city, md)

    md_path = results_dir / "auto_report.md"
    html_path = results_dir / "auto_report.html"

    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")

    print("Saved:", md_path)
    print("Saved:", html_path)

    if args.open:
        import subprocess
        subprocess.run(["open", str(html_path)], check=False)


if __name__ == "__main__":
    main()