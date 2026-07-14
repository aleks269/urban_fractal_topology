# UrbanFractal Topology

> **Примечание для версии 0.4.0.** Этот файл сохранён как расширенная справка прежней версии и может содержать устаревшие имена полей (`rc_m`, открытая `compactness_3d`) и прежнее описание топологии. Нормативные определения и команды находятся в корневых `README.md`, `CORRECTIONS_V040.md` и `RUN_200_25M_EXTERNAL.md`.


`urban-fractal` — прототип Python-программы для конечномасштабного анализа городской морфологии по векторам зданий и городской границе. Программа строит бинарную маску застройки, рассчитывает фрактальные, лакунарные, компактностные, мультифрактальные и топологические признаки, а также формирует таблицы и графики для одиночных и пакетных расчётов.

Документация в этом комплекте ориентирована на рабочее использование проекта в локальном репозитории: установка, одиночные запуски, пакетная обработка каталога городов, проверка разрешения, итоговые расчёты, отчёты и диагностика ошибок.

## Основная идея программы

Входные данные — полигональный слой зданий и, желательно, полигональная граница города. Здания приводятся к метрической системе координат, очищаются, при необходимости обрезаются по границе, затем растеризуются с заданным размером пикселя. Все 2D-показатели считаются по маске застройки. 2.5D-показатели оцениваются через экструзию footprints зданий с использованием высот из атрибутов или заданной высоты по умолчанию.

Программа рассчитывает:

- 2D box-counting размерность маски застройки `D_build`;
- лакунарность `Lambda(r)` по gliding-box процедуре;
- 2D компактность городской границы `C_2D`;
- 2.5D envelope-показатели: площадь кровель, площадь стен, площадь оболочки, объём, `A_env / A_0`, `C_3D`;
- опционально мультифрактальный спектр `D_q`;
- опционально топологический профиль застройки при морфологическом расширении `X_r = X ⊕ B_r`: `A(r)`, `P(r)`, `beta0(r)`, `beta1(r)`, `chi(r)`, `G(r)`, `r_c`, интегральные индексы фрагментированности, пустотности и сложности границы.

## Предлагаемый основной сценарий

Для текущей задачи сравнения российских и мировых городов разумно считать основным не одиночный запуск `--city`, а воспроизводимый пакетный сценарий по локально сохранённым GeoJSON-данным:

1. Установить окружение и проверить тесты.
2. Скачать города из `configs/city_catalog_200.csv` в `data/approved_cities/`.
3. Выполнить быстрый контрольный расчёт `quick` на 50 м для всех городов.
4. Выполнить `resolution_sweep` на 10/20/50 м для оценки чувствительности к дискретизации.
5. Выполнить итоговый режим `final` на 50 м с топологией и мультифрактальностью.
6. Собрать сводные таблицы и HTML/Markdown-отчёты.

Это рабочее предложение для согласования. Если основной сценарий будет изменён, достаточно синхронно поправить `README.md`, `QUICKSTART.md` и раздел 4 в `MANUAL.md`.

## Минимальная установка

```bash
cd urban_fractal_topology
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

Если OSM-загрузка не нужна, можно установить только базовую часть:

```bash
python -m pip install -e '.[dev]'
```

Базовый пакет зависит от `numpy`, `pandas`, `geopandas`, `shapely`, `pyproj`, `rasterio`, `matplotlib`, `scipy`. Для скачивания данных через OSM нужен дополнительный пакет `osmnx`.

## Одиночный запуск по локальным GeoJSON

```bash
python -m urban_fractal.cli \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/test_topology/pskov_50m \
  --pixel 50 \
  --topology \
  --multifractal
```

Эквивалентно, после установки entry point:

```bash
urban-fractal \
  --buildings data/approved_cities/russia/pskov/buildings.geojson \
  --boundary data/approved_cities/russia/pskov/boundary.geojson \
  --out results/test_topology/pskov_50m \
  --pixel 50 \
  --topology \
  --multifractal
```

## Пакетный запуск 200 городов

Сначала посмотреть список городов:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --list
```

Скачать данные:

```bash
bash scripts/download_200_cities.sh
```

Быстрый контрольный расчёт:

```bash
bash scripts/run_200_quick.sh
```

Проверка устойчивости к размеру пикселя:

```bash
bash scripts/run_200_sweep.sh
```

Итоговый расчёт на 50 м:

```bash
bash scripts/run_200_final_50m.sh
```

## Основные выходные файлы одиночного расчёта

В каталоге результата появляются:

- `summary.json` — основной машинно-читаемый паспорт расчёта;
- `building_mask.png` — растровая маска застройки;
- `box_counts_buildings.csv` — box-counting таблица;
- `scaling_window_candidates.csv` — кандидаты интервала масштабирования;
- `box_count_buildings.png` — график log-log fit;
- `lacunarity_buildings.csv` — таблица лакунарности;
- `lacunarity_buildings.png` — график лакунарности;
- `topology_minkowski_betti_profile.csv` — профиль `A(r)`, `P(r)`, `beta0`, `beta1`, `chi`, `G(r)`, если включён `--topology`;
- `minkowski_profile.png`, `betti_profile.png`, `percolation_profile.png`, если включён `--topology`;
- `multifractal_spectrum_buildings.csv` и `multifractal_raw_buildings.csv`, если включён `--multifractal`.

## Подробная документация

- `QUICKSTART.md` — короткий рабочий маршрут установки и первых запусков.
- `MANUAL.md` — подробное руководство: структура проекта, скрипты, флаги, порядок выполнения, выходные файлы, диагностика.

