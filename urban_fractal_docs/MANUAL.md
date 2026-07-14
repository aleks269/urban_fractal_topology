# UrbanFractal Topology — MANUAL

Документ описывает текущую программу `urban-fractal`: назначение, установку, состав проекта, входные данные, основные режимы запуска, флаги, выходные файлы, пакетные сценарии и диагностику. Руководство написано для локального рабочего использования проекта.

## 1. Назначение программы

`urban-fractal` предназначен для расчёта конечномасштабных морфологических признаков городской застройки по полигональным данным зданий. Основной объект анализа — 2D-маска footprints зданий внутри заданной городской границы. Дополнительно строится приближённая 2.5D-модель зданий как вертикальная экструзия footprints.

Программа не вычисляет истинную 3D-фрактальную размерность города по LiDAR/mesh-данным. Текущий `D_build` — это 2D box-counting размерность бинарной маски застройки на конечном диапазоне масштабов. Это важно указывать при научной интерпретации.

## 2. Что рассчитывается

### 2.1. Геометрическая подготовка

На вход подаются:

- слой зданий `buildings`: GeoJSON, GPKG или Shapefile;
- слой городской границы `boundary`: GeoJSON, GPKG или Shapefile, опционально;
- либо строка `--city` для скачивания через OSMnx.

Программа:

1. читает векторные данные через `geopandas`;
2. оставляет только `Polygon` и `MultiPolygon`;
3. чинит геометрию через `make_valid()` и `buffer(0)`;
4. переводит данные в метрическую CRS, обычно UTM через `estimate_utm_crs()`;
5. при наличии границы обрезает здания по ней;
6. если границы нет, создаёт fallback boundary по bounding box зданий с буфером `--buffer`;
7. добавляет высоты зданий по атрибутам или по умолчанию;
8. строит бинарную растровую маску застройки.

### 2.2. Высоты зданий и 2.5D

Высота ищется в атрибутах:

```text
height
building:height
HEIGHT
Height
h
building:levels
levels
floors
этажность
```

Если найдена абсолютная высота, она используется напрямую. Если найдена этажность, высота считается как:

```text
height = levels * floor_height_m
```

Если высота и этажность отсутствуют, используется:

```text
default_height_m
```

2.5D-показатели считаются как:

```text
roof_area = footprint_area * roof_factor
wall_area = footprint_perimeter * height
envelope_area = roof_area + wall_area
volume = footprint_area * height
surface_amplification = envelope_area / plan_area
compactness_3d = 36*pi*volume^2 / envelope_area^3
surface_to_volume = envelope_area / volume
```

Поле `height_source_known_fraction` показывает долю зданий, для которых высота была получена из атрибутов, а не заменена `default_height_m`.

### 2.3. Фрактальная размерность

Расчёт ведётся по бинарной маске застройки. Для набора box sizes программа считает число непустых ячеек `N(eps)` и подбирает линейный участок в координатах:

```text
x = log(1/eps)
y = log(N(eps))
```

Результат сохраняется как:

```text
fractal_dimension_building_footprints.dimension
fractal_dimension_building_footprints.r2
fractal_dimension_building_footprints.stderr
fractal_dimension_building_footprints.scale_min
fractal_dimension_building_footprints.scale_max
fractal_dimension_building_footprints.n_points
fractal_dimension_building_footprints.method
```

Интервал масштабирования подбирается автоматически по score, учитывающему `R²`, длину окна и ошибку наклона. Это эвристический выбор конечномасштабного линейного участка, а не доказательство истинной самоподобной размерности.

### 2.4. Лакунарность

Лакунарность считается методом скользящего окна:

```text
Lambda(r) = Var(M_r) / E(M_r)^2 + 1
```

где `M_r` — масса застройки в квадратном окне размера `r`. Выходная таблица содержит:

```text
window_size_px
stride_px
mean_mass
var_mass
lacunarity
n_windows
window_size_m
```

### 2.5. Мультифрактальный спектр

Включается флагом:

```bash
--multifractal
```

В текущей версии используется фиксированный набор `q`:

```text
-5, -2, -1, 0, 1, 2, 5
```

Сохраняются:

```text
multifractal_spectrum_buildings.csv
multifractal_raw_buildings.csv
```

Для `q != 1` используется partition sum `sum p_i^q`; для `q = 1` — информационная сумма `sum p_i log p_i`.

### 2.6. Топологический профиль

Включается флагом:

```bash
--topology
```

Программа рассматривает последовательность дилатаций бинарной маски:

```text
X_r = X ⊕ B_r
```

Для каждого радиуса `r` считаются:

```text
radius_px
radius_m
area_px
area_m2
perimeter_m
beta0
beta1
chi
largest_component_px
giant_fraction
```

Здесь:

- `beta0` — число компонент связности foreground-маски;
- `beta1` — число дыр, то есть background-компонент, не касающихся границы растра;
- `chi = beta0 - beta1` — эйлерова характеристика;
- `giant_fraction` — доля крупнейшей компоненты foreground в общей площади foreground;
- `rc_m` — первый радиус, где `giant_fraction >= giant_threshold`.

Связность задаётся параметром:

```bash
--topology-connectivity 1
```

или:

```bash
--topology-connectivity 2
```

`1` соответствует 4-соседству, `2` соответствует 8-соседству.

Интегральные топологические индексы:

```text
archipelago_index = integral beta0(r) d log r
void_index = integral beta1(r) d log r
boundary_complexity_index = integral P(r) d log r
```

Интегрирование ведётся только по радиусам `r > 0`.

## 3. Состав проекта

Структура проекта из архива:

```text
urban_fractal_topology/
├── pyproject.toml
├── README.md
├── RESOLUTION_SWEEP_IMPLEMENTATION.md
├── urban_fractal/
│   ├── __init__.py
│   ├── cli.py
│   ├── geometry.py
│   ├── io.py
│   ├── metrics.py
│   ├── pipeline.py
│   ├── plots.py
│   ├── raster.py
│   └── topology.py
├── batch_tools/
│   ├── download_city_catalog.py
│   ├── run_city_batch.py
│   └── collect_city_summaries.py
├── configs/
│   ├── city_catalog_100.csv
│   └── city_catalog_200.csv
├── scripts/
│   ├── download_100_cities.sh
│   ├── download_200_cities.sh
│   ├── run_100_quick.sh
│   ├── run_100_sweep.sh
│   ├── run_200_quick.sh
│   ├── run_200_sweep.sh
│   └── run_200_final_50m.sh
├── report_tools/
│   ├── make_report.py
│   └── make_all_reports.py
├── make_city_files/
│   ├── download_approved_cities.py
│   ├── make_city_files.py
│   ├── count.py
│   └── map.py
├── examples/
│   ├── run_local.sh
│   └── run_topology.sh
├── docs/
│   ├── BATCH_100_CITIES.md
│   └── CITY_CATALOG_200.md
└── tests/
    ├── test_metrics.py
    ├── test_pipeline_synthetic.py
    ├── test_resolution_sweep.py
    └── test_topology.py
```

### 3.1. Основной пакет `urban_fractal/`

`cli.py` — командная строка. Создаёт `AnalysisConfig`, разбирает флаги, запускает либо `analyze_city()`, либо `analyze_resolution_sweep()`.

`pipeline.py` — главный pipeline. Читает данные, очищает геометрию, строит маску, вызывает расчёт метрик, сохраняет JSON/CSV/PNG.

`geometry.py` — работа с CRS, очистка полигонов, оценка высот, расчёт площадей, периметров, 2.5D envelope-показателей, генерация box sizes.

`raster.py` — растеризация геометрии зданий в бинарную маску.

`metrics.py` — box counting, подбор scaling window, лакунарность, 2D/3D compactness, мультифрактальный спектр.

`topology.py` — морфологические дилатации, lattice perimeter, Betti numbers, topological summary.

`plots.py` — построение PNG-графиков.

`io.py` — чтение/запись файлов и OSM-загрузка через `osmnx`.

### 3.2. Пакетные инструменты `batch_tools/`

`download_city_catalog.py` — скачивает города из CSV-каталога в `data/approved_cities/`.

`run_city_batch.py` — запускает `urban_fractal.cli` для набора уже скачанных городов.

`collect_city_summaries.py` — собирает `summary.json` или `resolution_sweep_summary.json` из пакетных результатов в одну CSV-таблицу.

### 3.3. Отчёты `report_tools/`

`make_report.py` — строит Markdown и HTML отчёт для одного каталога результата.

`make_all_reports.py` — строит отчёты для всех найденных результатов и общий HTML-индекс. В присланном архиве этот файл содержал синтаксическую ошибку, но вы сообщили, что уже исправили её локально.

### 3.4. Shell-скрипты `scripts/`

Скрипты задают готовые пакетные маршруты:

- `download_100_cities.sh` — скачать каталог 100 городов;
- `download_200_cities.sh` — скачать каталог 200 городов;
- `run_100_quick.sh` — быстрый расчёт 100 городов на 50 м;
- `run_100_sweep.sh` — resolution sweep 100 городов на 10/20/50 м;
- `run_200_quick.sh` — быстрый расчёт 200 городов на 50 м;
- `run_200_sweep.sh` — resolution sweep 200 городов на 10/20/50 м;
- `run_200_final_50m.sh` — итоговый расчёт 200 городов на 50 м с топологией и мультифрактальностью.

## 4. Согласуемый основной сценарий

Так как основной сценарий в проекте явно не закреплён, предлагается принять следующий.

### 4.1. Главный режим работы

Главный режим — пакетный расчёт по каталогу `configs/city_catalog_200.csv` через локально сохранённые GeoJSON:

```text
configs/city_catalog_200.csv
        ↓
batch_tools/download_city_catalog.py
        ↓
data/approved_cities/{russia|world}/{slug}/buildings.geojson
data/approved_cities/{russia|world}/{slug}/boundary.geojson
        ↓
batch_tools/run_city_batch.py --mode quick
        ↓
batch_tools/run_city_batch.py --mode sweep
        ↓
batch_tools/run_city_batch.py --mode final
        ↓
batch_tools/collect_city_summaries.py
        ↓
report_tools/make_report.py / make_all_reports.py
```

### 4.2. Почему не `--city` как основной режим

`--city` удобен для одного быстрого эксперимента, но хуже для воспроизводимости:

- результат зависит от текущей доступности Overpass/Nominatim;
- при повторном запуске данные могут измениться;
- ошибки скачивания смешиваются с ошибками расчёта;
- сложнее проверять и архивировать исходный слой зданий.

Поэтому для серии городов лучше сначала скачать и сохранить `buildings.geojson` и `boundary.geojson`, а потом считать только по локальным файлам.

### 4.3. Почему `final` на 50 м

`pixel=50` выбран как рабочий компромисс для массового расчёта 200 городов. Для крупных городов 10 м может быть тяжёлым по памяти и времени. Для первичного сравнения 50 м обычно безопаснее как пакетный baseline. При этом `resolution_sweep` 10/20/50 м нужен, чтобы проверить, насколько результат зависит от размера пикселя.

### 4.4. Рекомендуемый порядок

1. Проверить окружение и тесты.
2. Скачать 3–5 городов.
3. Выполнить одиночный расчёт для одного города.
4. Выполнить `quick` для 3–5 городов.
5. Выполнить `sweep` для 1–3 городов.
6. Скачать все 200 городов.
7. Выполнить `quick` для всех 200.
8. Просмотреть `batch_manifest_quick.csv`, исключить города с ошибками данных.
9. Выполнить `sweep` для всех успешно скачанных городов или для выбранной подвыборки.
10. Выполнить `final` на 50 м.
11. Собрать сводные CSV.
12. Построить HTML/Markdown-отчёты.

## 5. Установка

### 5.1. macOS / Linux

```bash
cd urban_fractal_topology
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

### 5.2. Windows PowerShell

```powershell
cd urban_fractal_topology
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[osm,dev]"
python -m pytest -q
```

### 5.3. Режимы установки

Только расчёт по локальным файлам:

```bash
python -m pip install -e .
```

Расчёт + тесты:

```bash
python -m pip install -e '.[dev]'
```

Расчёт + OSM-загрузка:

```bash
python -m pip install -e '.[osm]'
```

Полный рабочий режим:

```bash
python -m pip install -e '.[osm,dev]'
```

### 5.4. Проверка CLI

```bash
python -m urban_fractal.cli --help
urban-fractal --help
```

Если `urban-fractal` не найден, но `python -m urban_fractal.cli --help` работает, значит entry point не обновился. Обычно помогает:

```bash
python -m pip install -e . --force-reinstall
```

или просто использовать модульный запуск:

```bash
python -m urban_fractal.cli ...
```

## 6. Входные данные

### 6.1. Локальный слой зданий

Файл задаётся флагом:

```bash
--buildings path/to/buildings.geojson
```

Поддерживаются форматы, читаемые `geopandas.read_file()`: GeoJSON, GPKG, SHP и другие форматы GDAL/Fiona/pyogrio.

Требования:

- геометрии должны быть polygonal: `Polygon` или `MultiPolygon`;
- CRS должен быть задан;
- слой должен содержать footprints зданий;
- высоты необязательны, но полезны для 2.5D-показателей.

### 6.2. Локальная граница города

Файл задаётся флагом:

```bash
--boundary path/to/boundary.geojson
```

Если граница не задана, программа создаёт bounding box вокруг зданий. Это допустимо для технической проверки, но плохо для научного сравнения городов, потому что `plan_area_m2`, `compactness_2d` и `A_env/A0` будут зависеть от искусственной рамки.

### 6.3. OSM-режим по названию города

Флаг:

```bash
--city "Pskov, Russia"
```

Этот режим требует `osmnx` и доступа к интернету. Он удобен для разовой проверки, но не рекомендуется как основной режим для серии городов. Для массового исследования лучше использовать `download_city_catalog.py`, чтобы сначала сохранить исходные данные.

### 6.4. Каталоги городов

`configs/city_catalog_100.csv` содержит 100 городов: 50 российских и 50 мировых.

`configs/city_catalog_200.csv` содержит 200 городов: 100 российских и 100 мировых.

Поля каталога:

```text
subset,slug,name,query,morphotype
```

`subset` — группа `russia` или `world`.

`slug` — машинное имя города для папок и фильтрации.

`name` — человекочитаемое имя.

`query` — строка для геокодирования OSMnx/Nominatim.

`morphotype` — рабочая морфологическая метка. Это не результат классификации, а предварительный ярлык для группировки.

## 7. Команда `urban-fractal` / `python -m urban_fractal.cli`

CLI имеет две взаимоисключающие формы источника данных:

```bash
--city "City, Country"
```

или:

```bash
--buildings path/to/buildings.geojson
```

`--boundary` можно использовать только как дополнительный локальный файл.

### 7.1. Главные флаги CLI

| Флаг | Тип / значения | Значение по умолчанию | Назначение |
|---|---:|---:|---|
| `--city` | string | нет | Название места для OSM-загрузки. Требует `osmnx`. |
| `--buildings` | path | нет | Локальный слой зданий. Взаимоисключён с `--city`. |
| `--boundary` | path | нет | Локальная граница города. |
| `--out` | path | `results` | Каталог результата. |
| `--pixel` | float | `25.0` | Размер пикселя в метрах для одиночного расчёта. |
| `--resolution-sweep` | list[float] | нет | Запускает несколько расчётов при разных размерах пикселя. |
| `--resolution-sweep-continue-on-error` | flag | `False` | Не останавливать sweep, если один размер пикселя упал. |
| `--floor-height` | float | `3.0` | Метры на этаж при наличии `building:levels`. |
| `--default-height` | float | `12.0` | Высота здания по умолчанию при отсутствии высоты. |
| `--roof-factor` | float | `1.0` | Множитель площади кровли относительно footprint area. |
| `--buffer` | float | `0.0` | Буфер fallback boundary вокруг зданий, если нет границы. |
| `--min-box-px` | int | `2` | Минимальный размер box для box-counting в пикселях. |
| `--max-box-fraction` | float | `0.25` | Максимальный box как доля минимальной стороны растра. |
| `--min-scaling-points` | int | `4` | Минимальное число точек в scaling window. |
| `--multifractal` | flag | `False` | Включает расчёт `D_q`. |
| `--topology` | flag | `False` | Включает Minkowski/Betti/percolation-профили. |
| `--topology-radii` | string | нет | Ручной список радиусов в пикселях, например `0,1,2,4,8,16`. |
| `--topology-max-radius-fraction` | float | `0.05` | Максимальный радиус как доля минимальной стороны растра. |
| `--topology-n-radii` | int | `18` | Число автоматически выбранных радиусов. |
| `--topology-connectivity` | `1` или `2` | `1` | 4-соседство или 8-соседство. |
| `--giant-threshold` | float | `0.5` | Порог крупнейшей компоненты для `r_c`. |

### 7.2. Флаги resolution sweep

| Флаг | Значение по умолчанию | Назначение |
|---|---:|---|
| `--resolution-sweep 10 20 50` | нет | Список размеров пикселя в метрах. При наличии этого флага `--pixel` не используется как основной размер. |
| `--resolution-sweep-continue-on-error` | `False` | Продолжать sweep, если один размер пикселя дал ошибку. |
| `--sweep-max-area-error` | `0.05` | Максимальная относительная ошибка площади зданий между вектором и растром. |
| `--sweep-min-r2` | `0.98` | Минимальное `R²` box-counting fit для quality filter. |
| `--sweep-d-cv-threshold` | `0.05` | Максимальный коэффициент вариации `D_build` внутри стабильного окна. |
| `--sweep-rc-cv-threshold` | `0.10` | Максимальный коэффициент вариации `rc_m` внутри стабильного окна, если topology включена. |

### 7.3. Примеры одиночных запусков

Минимальный расчёт без топологии и мультифрактальности:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/single/pskov_quick_50m \
  --pixel 50
```

Расчёт с топологией:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/single/pskov_topology_50m \
  --pixel 50 \
  --topology
```

Расчёт с топологией и мультифрактальностью:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/single/pskov_final_50m \
  --pixel 50 \
  --topology \
  --multifractal
```

Ручные топологические радиусы:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/single/pskov_topology_manual_radii \
  --pixel 50 \
  --topology \
  --topology-radii 0,1,2,4,8,16,32,64
```

Resolution sweep:

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/single/pskov_sweep \
  --resolution-sweep 10 20 50 \
  --topology \
  --resolution-sweep-continue-on-error
```

Прямой OSM-режим:

```bash
python -m urban_fractal.cli \
  --city "Pskov, Russia" \
  --out results/osm/pskov_50m \
  --pixel 50 \
  --topology
```

## 8. `batch_tools/download_city_catalog.py`

Назначение: скачать данные городов из CSV-каталога в файловую структуру `data/approved_cities/{subset}/{slug}/`.

Базовая команда:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --set all \
  --sleep 5
```

### 8.1. Флаги

| Флаг | Значение по умолчанию | Назначение |
|---|---:|---|
| `--catalog` | `configs/city_catalog_100.csv` | CSV-каталог городов. |
| `--out` | `data/approved_cities` | Корневой каталог для скачанных данных. |
| `--set` | `all` | Поднабор: `russia`, `world`, `all`. |
| `--cities` | нет | Список slug через запятую. |
| `--start` | `0` | Индекс старта после фильтрации. |
| `--limit` | нет | Максимальное число городов. |
| `--roads` | `False` | Дополнительно скачать дорожную сеть. В текущем ядре расчёта дороги не используются. |
| `--overwrite` | `False` | Перезаписать уже существующие файлы. |
| `--sleep` | `5.0` | Пауза между городами, чтобы не перегружать API. |
| `--list` | `False` | Только вывести список выбранных городов и выйти. |

### 8.2. Примеры

Показать 200 городов:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --list
```

Скачать только российские города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --set russia \
  --out data/approved_cities \
  --sleep 5
```

Скачать 10 городов начиная с 20-го:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --start 20 \
  --limit 10 \
  --out data/approved_cities \
  --sleep 5
```

Скачать конкретные города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --cities pskov,zelenograd,venice,singapore \
  --out data/approved_cities \
  --sleep 5
```

## 9. `batch_tools/run_city_batch.py`

Назначение: запустить расчёт для набора уже скачанных городов. Скрипт не скачивает данные. Он ожидает структуру:

```text
data/approved_cities/{subset}/{slug}/buildings.geojson
data/approved_cities/{subset}/{slug}/boundary.geojson
```

### 9.1. Режимы `--mode`

`quick` — одиночный расчёт при одном размере пикселя. По умолчанию без топологии и без мультифрактальности. Можно добавить `--topology` и/или `--multifractal`.

`topology` — одиночный расчёт при одном размере пикселя с топологией.

`sweep` — серия расчётов при нескольких размерах пикселя. Внутри режима автоматически добавляется `--topology`.

`final` — одиночный расчёт при одном размере пикселя с `--topology` и `--multifractal`.

### 9.2. Флаги

| Флаг | Значение по умолчанию | Назначение |
|---|---:|---|
| `--catalog` | `configs/city_catalog_100.csv` | CSV-каталог городов. |
| `--data-root` | `data/approved_cities` | Где искать скачанные GeoJSON. |
| `--results-root` | `results/batch_100` | Корень результатов. |
| `--set` | `all` | Поднабор: `russia`, `world`, `all`. |
| `--cities` | нет | Список slug через запятую. |
| `--start` | `0` | Индекс старта после фильтрации. |
| `--limit` | нет | Максимальное число городов. |
| `--mode` | `quick` | `quick`, `topology`, `sweep`, `final`. |
| `--pixel` | `25.0` | Размер пикселя для `quick`, `topology`, `final`. |
| `--resolution-sweep` | `10.0 20.0 50.0` | Размеры пикселя для `sweep`. |
| `--topology` | `False` | Добавить топологию к `quick`. |
| `--multifractal` | `False` | Добавить мультифрактальность, если режим её сам не включает. |
| `--resolution-sweep-continue-on-error` | `False` | Продолжать sweep, если один pixel size упал. |
| `--sweep-max-area-error` | `0.05` | Фильтр качества sweep по ошибке площади. |
| `--sweep-min-r2` | `0.98` | Фильтр качества sweep по `R²`. |
| `--sweep-d-cv-threshold` | `0.05` | Порог вариации `D_build`. |
| `--sweep-rc-cv-threshold` | `0.10` | Порог вариации `rc_m`. |
| `--floor-height` | `3.0` | Метры на этаж. |
| `--default-height` | `12.0` | Высота по умолчанию. |
| `--roof-factor` | `1.0` | Множитель площади кровли. |
| `--min-box-px` | `2` | Минимальный box size. |
| `--max-box-fraction` | `0.25` | Максимальный box size как доля стороны растра. |
| `--min-scaling-points` | `4` | Минимальное число точек в fit. |
| `--topology-radii` | нет | Ручные радиусы топологии в пикселях. |
| `--topology-max-radius-fraction` | `0.05` | Максимальный радиус топологии. |
| `--topology-n-radii` | `18` | Число радиусов топологии. |
| `--topology-connectivity` | `1` | 4- или 8-соседство. |
| `--giant-threshold` | `0.5` | Порог гигантской компоненты. |
| `--python` | текущий `sys.executable` | Какой Python использовать в подпроцессах. |
| `--skip-existing` | `False` | Пропускать города, если ожидаемый результат уже есть. |
| `--continue-on-error` | `False` | Не останавливать весь batch при ошибке одного города. |
| `--dry-run` | `False` | Напечатать команды, но не запускать. |

### 9.3. Примеры batch-запуска

Проверить команды без выполнения:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode final \
  --pixel 50 \
  --cities pskov,zelenograd,venice \
  --dry-run
```

Quick для всех 200:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --set all \
  --mode quick \
  --pixel 50 \
  --continue-on-error \
  --skip-existing
```

Topology для выбранных городов:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode topology \
  --pixel 50 \
  --cities pskov,zelenograd,venice \
  --continue-on-error
```

Sweep для всех 200:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode sweep \
  --resolution-sweep 10 20 50 \
  --resolution-sweep-continue-on-error \
  --continue-on-error \
  --skip-existing
```

Final на 50 м:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_200.csv \
  --data-root data/approved_cities \
  --results-root results/batch_200 \
  --mode final \
  --pixel 50 \
  --continue-on-error \
  --skip-existing
```

## 10. `batch_tools/collect_city_summaries.py`

Назначение: собрать результаты в одну CSV-таблицу.

### 10.1. Флаги

| Флаг | Значение по умолчанию | Назначение |
|---|---:|---|
| `--results-root` | `results/batch_100` | Корень пакетных результатов. |
| `--mode` | `all` | `quick`, `topology`, `sweep`, `final`, `all`. |
| `--out` | `results/batch_100/city_features_summary.csv` | Выходной CSV. |

### 10.2. Примеры

Quick:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_200 \
  --mode quick \
  --out results/batch_200/city_features_quick.csv
```

Final:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_200 \
  --mode final \
  --out results/batch_200/city_features_final_50m.csv
```

Все режимы:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_200 \
  --mode all \
  --out results/batch_200/city_features_all.csv
```

### 10.3. Замечание по sweep

В загруженной версии `analyze_resolution_sweep()` записывает стабильность в ключ `stability`, а `collect_city_summaries.py` для `mode == "sweep"` ищет ключи `stable_window` и `global_stability`. Поэтому в этой версии агрегированный sweep CSV может не содержать подробных полей устойчивости. Надёжный способ проверки sweep — читать напрямую:

```text
results/batch_200/sweep/{subset}/{slug}/resolution_sweep_summary.json
results/batch_200/sweep/{subset}/{slug}/resolution_sweep_summary.csv
```

Если нужно агрегировать sweep в одну таблицу, логично поправить `collect_city_summaries.py`, чтобы он flatten-ил `data["stability"]`.

## 11. `report_tools/make_report.py`

Назначение: сделать `auto_report.md` и `auto_report.html` для одного каталога результата.

### 11.1. Флаги

| Аргумент | Назначение |
|---|---|
| `results_dir` | Путь к каталогу результата. Обязательный позиционный аргумент. |
| `--city` | Название города для заголовка отчёта. |
| `--open` | Открыть HTML-отчёт после создания на macOS. |

### 11.2. Пример

```bash
python report_tools/make_report.py \
  results/batch_200/final/russia/pskov \
  --city Pskov \
  --open
```

Результат:

```text
results/batch_200/final/russia/pskov/auto_report.md
results/batch_200/final/russia/pskov/auto_report.html
```

## 12. `report_tools/make_all_reports.py`

Назначение: найти все каталоги с `summary.json`, построить одиночные отчёты и общий HTML-индекс.

Флаги:

| Флаг | Значение по умолчанию | Назначение |
|---|---:|---|
| `--root` | `results` | Корень, где искать результаты. |
| `--open` | `False` | Открыть общий отчёт. |
| `--no-single` | `False` | Не пересоздавать одиночные отчёты. |

Пример:

```bash
python report_tools/make_all_reports.py \
  --root results/batch_200/final \
  --open
```

Ожидаемые выходы:

```text
all_results_summary.csv
all_results_index.html
comparison_plots/
```

В присланном архиве этот файл содержал синтаксический мусор в HTML-генераторе. Вы сообщили, что исправили эту ошибку локально; после исправления команда должна работать.

## 13. Готовые shell-скрипты

### 13.1. `scripts/download_100_cities.sh`

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --out data/approved_cities \
  --set all \
  --sleep 5
```

### 13.2. `scripts/download_200_cities.sh`

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --set all \
  --sleep 5
```

### 13.3. `scripts/run_100_quick.sh`

Запускает `quick` на 100 городах при `pixel=50`, затем собирает `city_features_quick.csv`.

### 13.4. `scripts/run_100_sweep.sh`

Запускает `sweep` на 100 городах при `resolution-sweep 10 20 50`, затем собирает `city_features_sweep.csv`.

### 13.5. `scripts/run_200_quick.sh`

Запускает `quick` на 200 городах при `pixel=50`, затем собирает `city_features_quick.csv`.

### 13.6. `scripts/run_200_sweep.sh`

Запускает `sweep` на 200 городах при `resolution-sweep 10 20 50`, затем собирает `city_features_sweep.csv`.

### 13.7. `scripts/run_200_final_50m.sh`

Запускает `final` на 200 городах при `pixel=50`, затем собирает `city_features_final_50m.csv`.

## 14. Выходные файлы одиночного расчёта

### 14.1. `summary.json`

Главный итоговый файл. Основные разделы:

```text
city_name
input
planar_boundary
building_surfaces
raster_diagnostics
derived_2_5d
fractal_dimension_building_footprints
lacunarity_building_footprints
topological_morphology_building_footprints
multifractal_spectrum_building_footprints
outputs
method_notes
```

### 14.2. Растровая диагностика

В `summary.json`:

```text
raster_diagnostics.n_rows
raster_diagnostics.n_cols
raster_diagnostics.n_pixels_total
raster_diagnostics.n_pixels_buildings
raster_diagnostics.foreground_fraction
raster_diagnostics.building_area_raster_m2
raster_diagnostics.building_area_vector_m2
raster_diagnostics.raster_area_error_rel
raster_diagnostics.all_touched
```

`raster_area_error_rel` — важный контроль. Большое значение означает, что выбранный размер пикселя слишком грубый или растеризация плохо воспроизводит векторную площадь.

### 14.3. CSV и PNG

Всегда создаются:

```text
building_mask.png
box_counts_buildings.csv
scaling_window_candidates.csv
box_count_buildings.png
lacunarity_buildings.csv
lacunarity_buildings.png
summary.json
```

Если включён `--topology`:

```text
topology_minkowski_betti_profile.csv
minkowski_profile.png
betti_profile.png
percolation_profile.png
```

Если включён `--multifractal`:

```text
multifractal_spectrum_buildings.csv
multifractal_raw_buildings.csv
```

## 15. Выходные файлы resolution sweep

Корень sweep-результата:

```text
resolution_sweep_summary.csv
resolution_sweep_summary.json
resolution_sweep_stability.png
px_10m/
px_20m/
px_50m/
```

Каждый `px_*m/` — обычный одиночный расчёт со своим `summary.json`, CSV и PNG.

`resolution_sweep_summary.csv` содержит строки по размерам пикселя. Среди важных полей:

```text
pixel_size_m
status
n_rows
n_cols
foreground_fraction
raster_area_error_rel
D_build
D_r2
D_stderr
D_scale_min_m
D_scale_max_m
lacunarity_min
lacunarity_max
lacunarity_mean
rc_m
beta0_at_zero
beta1_at_zero
archipelago_index
void_index
boundary_complexity_index
```

`resolution_sweep_summary.json` содержит раздел `stability`, где указано:

```text
stable
recommended_pixel_size_m
stable_window_pixel_sizes_m
stable_window_min_pixel_size_m
stable_window_max_pixel_size_m
n_runs_total
n_runs_ok
n_quality_runs
excluded_pixel_sizes_m
d_cv_quality_runs
rc_cv_quality_runs
thresholds
reason
notes
```

## 16. Как читать результаты

### 16.1. Первичная проверка качества

Для каждого города сначала смотреть:

1. `building_mask.png` — маска должна быть похожа на реальную структуру застройки, а не на пустой/залитый прямоугольник.
2. `summary.json → raster_diagnostics.foreground_fraction` — доля застройки не должна быть абсурдной.
3. `summary.json → raster_diagnostics.raster_area_error_rel` — большая ошибка говорит о слишком грубой растеризации или проблемных данных.
4. `box_count_buildings.png` — должен быть осмысленный log-log участок.
5. `fractal_dimension_building_footprints.r2` — низкий `R²` снижает доверие к `D_build`.
6. `height_source_known_fraction` — если близко к нулю, все 2.5D-показатели модельные.

### 16.2. Как интерпретировать `D_build`

`D_build` — это finite-scale 2D box-counting dimension застроенной маски. Для сравнения городов обязательно фиксировать:

- источник данных;
- границу города;
- размер пикселя;
- `scale_min` и `scale_max`;
- `R²` fit;
- количество точек fit.

Нельзя интерпретировать `D_build` как универсальную фрактальную размерность города вне указанного диапазона масштабов.

### 16.3. Как интерпретировать топологию

Высокое `beta0_at_zero` указывает на фрагментированную застройку при исходном разрешении.

Пик `beta1(r)` показывает характерный масштаб образования/закрытия пустот в дилатированной маске.

`rc_m` показывает радиус, при котором возникает гигантская компонента. Чем больше `rc_m`, тем более разреженной/разорванной является маска застройки в смысле данного конечномасштабного критерия.

`archipelago_index` интегрирует количество компонент по логарифму радиуса. Он чувствителен к фрагментированности.

`void_index` интегрирует число дыр. Он чувствителен к дворам, паркам, водным разрывам, промышленным пустотам, superblock-структурам и другим void-системам.

`boundary_complexity_index` интегрирует периметр дилатированной маски. Он характеризует сложность boundary-профиля, но зависит от растеризации и выбранного диапазона радиусов.

## 17. Диагностика ошибок

### 17.1. `ModuleNotFoundError: No module named 'osmnx'`

Причина: не установлена OSM-опция.

Решение:

```bash
python -m pip install -e '.[osm]'
```

или полный режим:

```bash
python -m pip install -e '.[osm,dev]'
```

Если OSM-загрузка не нужна, используйте только локальные файлы через `--buildings` и `--boundary`.

### 17.2. `GeoDataFrame has no CRS`

Причина: входной файл не содержит CRS.

Решение: назначить CRS до запуска. Если файл в WGS84, обычно это EPSG:4326. Назначение CRS без проверки координат опасно; сначала надо убедиться, что координаты действительно в долгота/широта.

### 17.3. `No building polygons after cleaning/clipping`

Возможные причины:

- слой зданий пустой;
- здания не являются `Polygon`/`MultiPolygon`;
- граница не пересекает слой зданий;
- CRS зданий и границы некорректны;
- OSM-загрузка вернула не тот объект.

Проверка:

```bash
python - <<'PY'
import geopandas as gpd
b = gpd.read_file('data/approved_cities/russia/pskov/buildings.geojson')
g = gpd.read_file('data/approved_cities/russia/pskov/boundary.geojson')
print(b.crs, len(b), b.geom_type.value_counts())
print(g.crs, len(g), g.geom_type.value_counts())
print(b.total_bounds)
print(g.total_bounds)
PY
```

### 17.4. Очень большой raster или зависание

Причина: слишком мелкий `--pixel` для крупного города.

Решение:

- увеличить `--pixel`, например с 10 м до 20/50/100 м;
- сначала запускать `quick` на 50 м;
- для крупных городов не начинать с 5 или 10 м;
- использовать `--continue-on-error` в batch;
- использовать `--skip-existing` при повторном запуске.

### 17.5. Сильная ошибка `raster_area_error_rel`

Причины:

- слишком грубый пиксель;
- мелкие здания исчезают или чрезмерно раздуваются из-за `all_touched=True`;
- неудачная граница;
- проблемы в исходных данных.

Действия:

- сравнить 20/50/100 м через `resolution_sweep`;
- посмотреть `building_mask.png`;
- проверить площадь зданий в `summary.json`;
- не использовать такой город/разрешение в финальном сравнении без пометки.

### 17.6. Низкий `D_r2`

Причина: нет хорошего log-log scaling window или маска плохо подходит для box-counting интерпретации на выбранном диапазоне масштабов.

Действия:

- посмотреть `box_count_buildings.png`;
- посмотреть `scaling_window_candidates.csv`;
- увеличить/уменьшить `--pixel`;
- изменить `--min-box-px`, `--max-box-fraction`, `--min-scaling-points` только осознанно;
- не использовать `D_build` как сильный аргумент, если fit плохой.

### 17.7. Batch остановился на одном городе

Использовать:

```bash
--continue-on-error
```

При повторном запуске добавлять:

```bash
--skip-existing
```

### 17.8. Нужно понять, что запускал batch

В каждом каталоге batch-результата сохраняются:

```text
batch_stdout.txt
batch_stderr.txt
```

В корне batch-результатов сохраняется:

```text
batch_manifest_{mode}.json
batch_manifest_{mode}.csv
```

`batch_manifest` содержит команду, статус, код возврата и время выполнения.

## 18. Проверочные команды

Проверить число скачанных городов:

```bash
find data/approved_cities -name buildings.geojson | wc -l
find data/approved_cities -name boundary.geojson | wc -l
```

Проверить число successful final-результатов:

```bash
find results/batch_200/final -name summary.json | wc -l
```

Проверить ошибки batch:

```bash
grep -n "error" results/batch_200/batch_manifest_final.csv | head -50
```

Посмотреть один `summary.json`:

```bash
cat results/batch_200/final/russia/pskov/summary.json | python -m json.tool | less
```

Быстро вытащить ключевые поля из одного summary:

```bash
python - <<'PY'
import json
from pathlib import Path
p = Path('results/batch_200/final/russia/pskov/summary.json')
d = json.loads(p.read_text())
print('D_build:', d['fractal_dimension_building_footprints']['dimension'])
print('D_r2:', d['fractal_dimension_building_footprints']['r2'])
print('raster_area_error_rel:', d['raster_diagnostics']['raster_area_error_rel'])
print('C_2D:', d['planar_boundary']['compactness_2d'])
print('A_env/A0:', d['derived_2_5d']['surface_amplification_envelope_over_plan'])
print('C_3D:', d['derived_2_5d']['compactness_3d'])
print('topology:', d.get('topological_morphology_building_footprints'))
PY
```

## 19. Практические рекомендации

Для одиночной отладки использовать маленький/средний город и `pixel=50`.

Для научной проверки масштаба использовать `resolution_sweep`, а не доверять одному `pixel`.

Для массового запуска всегда использовать `--continue-on-error` и `--skip-existing`.

Не смешивать в одной сравнительной таблице результаты, полученные при разных `pixel`, без явной пометки.

Не сравнивать 2.5D-показатели как реальные, если `height_source_known_fraction` мала. В этом случае они являются модельными оценками при `default_height_m`.

Для итоговой таблицы по 200 городам разумно хранить отдельно:

```text
city_features_quick.csv
city_features_sweep.csv
city_features_final_50m.csv
batch_manifest_quick.csv
batch_manifest_sweep.csv
batch_manifest_final.csv
```

## 20. Минимальный регламент воспроизводимого запуска

1. Зафиксировать commit/архив проекта.
2. Зафиксировать дату скачивания OSM-данных.
3. Сохранить `configs/city_catalog_200.csv`.
4. Сохранить весь каталог `data/approved_cities/`.
5. Запустить `quick` на 50 м.
6. Проверить `batch_manifest_quick.csv`.
7. Запустить `sweep` на 10/20/50 м.
8. Проверить `resolution_sweep_summary.json` по проблемным городам.
9. Запустить `final` на 50 м.
10. Собрать `city_features_final_50m.csv`.
11. Сгенерировать HTML-отчёты.
12. Заархивировать `results/`, `configs/`, версию кода и список Python-пакетов.

Список пакетов можно сохранить так:

```bash
python -m pip freeze > requirements_freeze.txt
```

## 21. Краткая карта команд

```bash
# установка
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q

# список городов
python batch_tools/download_city_catalog.py --catalog configs/city_catalog_200.csv --list

# скачать тестовые города
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --sleep 5

# одиночный расчёт
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/smoke/pskov_50m \
  --pixel 50 \
  --topology \
  --multifractal

# отчёт по одиночному результату
python report_tools/make_report.py results/smoke/pskov_50m --city Pskov --open

# скачать все 200
bash scripts/download_200_cities.sh

# quick 200
bash scripts/run_200_quick.sh

# sweep 200
bash scripts/run_200_sweep.sh

# final 200
bash scripts/run_200_final_50m.sh

# общий отчёт, если make_all_reports.py исправлен
python report_tools/make_all_reports.py --root results/batch_200/final --open
```

