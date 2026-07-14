# UrbanFractal Topology — QUICKSTART

> **Примечание для версии 0.4.0.** Этот файл сохранён как расширенная справка прежней версии и может содержать устаревшие имена полей (`rc_m`, открытая `compactness_3d`) и прежнее описание топологии. Нормативные определения и команды находятся в корневых `README.md`, `CORRECTIONS_V040.md` и `RUN_200_25M_EXTERNAL.md`.


Этот файл задаёт короткий рабочий маршрут: поднять окружение, проверить программу, скачать несколько городов, выполнить одиночный расчёт, затем перейти к пакетной обработке.

## 1. Перейти в каталог проекта

```bash
cd urban_fractal_topology
```

Все команды ниже предполагают запуск из корня репозитория, где лежат `pyproject.toml`, `urban_fractal/`, `batch_tools/`, `configs/`, `scripts/`.

## 2. Создать и активировать виртуальное окружение

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

## 3. Установить проект

Полная установка для локального расчёта, OSM-загрузки и тестов:

```bash
python -m pip install -e '.[osm,dev]'
```

Если OSM-загрузка не нужна:

```bash
python -m pip install -e '.[dev]'
```

Если не нужны тесты:

```bash
python -m pip install -e .
```

## 4. Проверить, что CLI доступен

```bash
python -m urban_fractal.cli --help
```

Или:

```bash
urban-fractal --help
```

Проверить тесты:

```bash
python -m pytest -q
```

Ожидаемый результат для версии из архива: все тесты должны проходить.

## 5. Принять основной рабочий сценарий

Предлагаемый основной сценарий для текущей задачи:

```text
configs/city_catalog_200.csv
        ↓
скачивание GeoJSON в data/approved_cities/
        ↓
quick на 50 м для контроля данных
        ↓
resolution_sweep 10/20/50 м для проверки чувствительности к размеру пикселя
        ↓
final на 50 м: фрактальность + лакунарность + топология + мультифрактальность
        ↓
сводные CSV и HTML/Markdown отчёты
```

Причина выбора: это воспроизводимый режим. Он отделяет скачивание данных от расчёта, сохраняет исходные GeoJSON, позволяет перезапускать неудачные города и даёт одинаковую структуру результатов для 100 российских и 100 мировых городов.

## 6. Посмотреть каталог городов

100-городской каталог:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --list
```

200-городской каталог:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --list
```

Только российские города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --set russia \
  --list
```

Только мировые города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --set world \
  --list
```

## 7. Скачать несколько городов для проверки

Перед массовым запуском лучше проверить 3–5 городов:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --sleep 5
```

Результат должен иметь структуру:

```text
data/approved_cities/
├── russia/
│   ├── pskov/
│   │   ├── buildings.geojson
│   │   ├── boundary.geojson
│   │   └── manifest.json
│   └── zelenograd/
└── world/
    ├── venice/
    ├── singapore/
    └── cape_town/
```

## 8. Одиночный контрольный расчёт

Пример для Пскова:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/smoke/pskov_50m \
  --pixel 50 \
  --topology \
  --multifractal
```

Проверить результат:

```bash
ls results/smoke/pskov_50m
cat results/smoke/pskov_50m/summary.json | python -m json.tool | head -80
```

Сгенерировать отчёт по одному результату:

```bash
python report_tools/make_report.py \
  results/smoke/pskov_50m \
  --city Pskov \
  --open
```

## 9. Быстрый пакетный расчёт на нескольких городах

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode quick \
  --pixel 50 \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --continue-on-error \
  --skip-existing
```

Собрать сводную таблицу:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_200 \
  --mode quick \
  --out results/batch_200/city_features_quick_test.csv
```

## 10. Массовый запуск 200 городов

Скачать все 200 городов:

```bash
bash scripts/download_200_cities.sh
```

Быстрый контрольный расчёт:

```bash
bash scripts/run_200_quick.sh
```

Проверка разрешения:

```bash
bash scripts/run_200_sweep.sh
```

Итоговый расчёт на 50 м:

```bash
bash scripts/run_200_final_50m.sh
```

## 11. Если нужно запустить только часть городов

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --set russia \
  --start 0 \
  --limit 10 \
  --mode final \
  --pixel 50 \
  --continue-on-error \
  --skip-existing
```

Или явно по slug:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --cities pskov,zelenograd,venice \
  --mode final \
  --pixel 50 \
  --continue-on-error \
  --skip-existing
```

## 12. Где смотреть результаты

Одиночный результат:

```text
results/smoke/pskov_50m/
```

Пакетный quick:

```text
results/batch_200/quick/russia/pskov/
results/batch_200/quick/world/venice/
results/batch_200/city_features_quick.csv
results/batch_200/batch_manifest_quick.csv
```

Пакетный sweep:

```text
results/batch_200/sweep/russia/pskov/resolution_sweep_summary.json
results/batch_200/sweep/russia/pskov/resolution_sweep_summary.csv
results/batch_200/sweep/russia/pskov/resolution_sweep_stability.png
results/batch_200/sweep/russia/pskov/px_10m/
results/batch_200/sweep/russia/pskov/px_20m/
results/batch_200/sweep/russia/pskov/px_50m/
```

Пакетный final:

```text
results/batch_200/final/russia/pskov/summary.json
results/batch_200/final/world/venice/summary.json
results/batch_200/city_features_final_50m.csv
```

## 13. Минимальная диагностика после расчёта

Проверить, какие города прошли:

```bash
cat results/batch_200/batch_manifest_final.csv | head
```

Найти ошибки:

```bash
grep -n "error" results/batch_200/batch_manifest_final.csv | head -50
```

Проверить один город визуально:

```bash
open results/batch_200/final/russia/pskov/building_mask.png
open results/batch_200/final/russia/pskov/box_count_buildings.png
open results/batch_200/final/russia/pskov/betti_profile.png
```

На macOS `open` откроет файл в приложении по умолчанию. На Linux можно использовать `xdg-open`.

