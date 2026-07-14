# Массовый тест UrbanFractal на 100 городах России и мира

Этот режим предназначен для первичной эксплуатационной проверки последней версии программы UrbanFractal Topology на большом наборе городов. Он не меняет научное ядро расчёта: одиночный анализ и `resolution_sweep` остаются теми же. Добавлены только каталог городов, пакетный загрузчик, пакетный запуск и сбор сводных таблиц.

## 1. Что входит в тестовый набор

Файл:

```bash
configs/city_catalog_100.csv
```

Содержит 100 городов:

- 50 городов России;
- 50 городов мира.

Поля каталога:

```text
subset, slug, name, query, morphotype
```

`subset` — группа: `russia` или `world`.

`slug` — машинное имя города для папок и фильтрации.

`name` — человекочитаемое имя.

`query` — строка геокодирования для OSMnx.

`morphotype` — предварительная морфологическая метка. Она нужна только для группировки и первичного сравнения. Это не результат классификации программы.

## 2. Рекомендуемая логика теста

Не надо сразу запускать самый тяжёлый режим на 100 городах. Правильная последовательность такая:

1. Проверить установку.
2. Вывести список городов.
3. Скачать 3–5 малых/средних городов.
4. Прогнать `quick` на 3–5 городах.
5. Прогнать `sweep` на 1–3 городах.
6. Скачать все 100 городов.
7. Прогнать `quick` на всех 100.
8. По результатам `quick` отфильтровать проблемные города.
9. Прогнать `sweep` только на городах, где данные скачались и расчёт прошёл.
10. Собрать итоговую таблицу.

## 3. Установка

Из корня проекта:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[osm,dev]'
python -m pytest -q
```

На Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[osm,dev]"
python -m pytest -q
```

## 4. Посмотреть список 100 городов

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --list
```

Только российские города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --set russia \
  --list
```

Только мировые города:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --set world \
  --list
```

## 5. Скачать тестовые города

Для начала лучше скачать несколько небольших или средних городов:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --out data/approved_cities \
  --cities zelenograd,pskov,veliky_novgorod,helsinki,prague \
  --sleep 5
```

Результат появится в структуре:

```text
data/approved_cities/
├── russia/
│   ├── zelenograd/
│   │   ├── boundary.geojson
│   │   ├── buildings.geojson
│   │   └── manifest.json
│   └── pskov/
└── world/
    ├── helsinki/
    └── prague/
```

Если нужен дорожный слой:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --out data/approved_cities \
  --cities zelenograd,helsinki \
  --roads \
  --sleep 5
```

В текущем расчётном ядре дороги пока не используются. Их скачивание нужно только для будущих расширений.

## 6. Скачать все 100 городов

```bash
bash scripts/download_100_cities.sh
```

Или явно:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_100.csv \
  --out data/approved_cities \
  --set all \
  --sleep 5
```

`--sleep 5` нужен, чтобы не перегружать Overpass API. Для больших городов скачивание может быть долгим. Возможны ошибки геокодирования, таймауты Overpass и неполные данные OSM. Это нормальная часть массового теста.

## 7. Быстрый расчёт quick

Режим `quick` нужен для первичной проверки 100 городов. Он считает один город при одном размере пикселя без тяжёлого `resolution_sweep`.

Рекомендуемый первый запуск:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode quick \
  --pixel 50 \
  --continue-on-error \
  --skip-existing
```

Что означает:

- `--mode quick` — одиночный расчёт;
- `--pixel 50` — грубый пиксель 50 м для первичного массового теста;
- `--continue-on-error` — не останавливать весь пакет из-за одного города;
- `--skip-existing` — не пересчитывать уже готовые города.

Готовый shell-скрипт:

```bash
bash scripts/run_100_quick.sh
```

## 8. Топологический одиночный расчёт

Для проверки топологии без sweep:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode topology \
  --pixel 25 \
  --cities zelenograd,helsinki,prague \
  --continue-on-error
```

Этот режим полезен после quick, но до тяжёлого sweep.

## 9. Resolution sweep

Это главный методически полезный режим. Для массового теста рекомендуемый набор разрешений:

```text
10 м, 20 м, 50 м
```

Команда:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode sweep \
  --resolution-sweep 10 20 50 \
  --resolution-sweep-continue-on-error \
  --continue-on-error \
  --skip-existing \
  --sweep-max-area-error 0.05 \
  --sweep-min-r2 0.98 \
  --sweep-d-cv-threshold 0.05 \
  --sweep-rc-cv-threshold 0.10
```

Готовый shell-скрипт:

```bash
bash scripts/run_100_sweep.sh
```

Для крупных городов 10 м может быть тяжёлым. Если расчёт слишком медленный или память резко растёт, используйте пилотный режим:

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode sweep \
  --resolution-sweep 20 50 100 \
  --resolution-sweep-continue-on-error \
  --continue-on-error
```

## 10. Финальный режим

`final` — это одиночный подробный расчёт с топологией и мультифрактальностью.

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode final \
  --pixel 10 \
  --cities zelenograd,helsinki,prague \
  --continue-on-error
```

На все 100 городов этот режим лучше не запускать первым. Его логично применять только после `quick` и `sweep`, когда уже понятны проблемные города и допустимое разрешение.

## 11. Dry-run: посмотреть команды без запуска

```bash
python batch_tools/run_city_batch.py \
  --catalog configs/city_catalog_100.csv \
  --data-root data/approved_cities \
  --results-root results/batch_100 \
  --mode quick \
  --pixel 50 \
  --limit 5 \
  --dry-run
```

Это безопасный способ проверить, какие команды будут выполнены.

## 12. Сбор сводной таблицы

Для quick:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_100 \
  --mode quick \
  --out results/batch_100/city_features_quick.csv
```

Для sweep:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_100 \
  --mode sweep \
  --out results/batch_100/city_features_sweep.csv
```

Собрать всё найденное:

```bash
python batch_tools/collect_city_summaries.py \
  --results-root results/batch_100 \
  --mode all \
  --out results/batch_100/city_features_all.csv
```

## 13. Где смотреть результаты

После quick:

```text
results/batch_100/quick/russia/zelenograd/
├── summary.json
├── building_mask.png
├── box_counting.csv
├── lacunarity.csv
├── box_count_fit.png
├── lacunarity.png
├── batch_stdout.txt
└── batch_stderr.txt
```

После sweep:

```text
results/batch_100/sweep/russia/zelenograd/
├── px_10m/
├── px_20m/
├── px_50m/
├── resolution_sweep_summary.csv
├── resolution_sweep_summary.json
├── resolution_sweep_stability.png
├── batch_stdout.txt
└── batch_stderr.txt
```

Общий журнал batch-запуска:

```text
results/batch_100/batch_manifest_quick.json
results/batch_100/batch_manifest_quick.csv
results/batch_100/batch_manifest_sweep.json
results/batch_100/batch_manifest_sweep.csv
```

## 14. Оптимальные режимы

### Проверка, что всё вообще работает

```bash
python batch_tools/download_city_catalog.py --cities zelenograd,pskov,helsinki --sleep 5
python batch_tools/run_city_batch.py --mode quick --pixel 50 --cities zelenograd,pskov,helsinki --continue-on-error
```

### Первичный массовый тест 100 городов

```bash
bash scripts/download_100_cities.sh
bash scripts/run_100_quick.sh
```

### Методически полезный тест устойчивости

```bash
bash scripts/run_100_sweep.sh
```

### Более дешёвый sweep для слабого компьютера

```bash
python batch_tools/run_city_batch.py \
  --mode sweep \
  --resolution-sweep 20 50 100 \
  --continue-on-error \
  --resolution-sweep-continue-on-error
```

### Детальный финальный расчёт выбранных городов

```bash
python batch_tools/run_city_batch.py \
  --mode final \
  --pixel 10 \
  --cities zelenograd,helsinki,stockholm,barcelona,venice \
  --continue-on-error
```

## 15. Что считать успехом пилотного запуска

Для первичного теста достаточно, если:

- данные скачались хотя бы для 70–90 городов из 100;
- quick прошёл хотя бы для 70–90 городов;
- `city_features_quick.csv` содержит сопоставимые признаки;
- в `summary.json` есть разумные значения `D_build`, `raster_diagnostics`, `surface_summary`;
- нет систематического падения на одном типе городов;
- sweep даёт хотя бы одно устойчивое окно разрешений для части городов.

Не нужно ожидать, что все 100 городов сразу пройдут идеально. Массовый городской анализ почти всегда требует очистки каталога и повторного запуска.

## 16. Основные причины ошибок

1. OSMnx не нашёл город по `query`.
2. Overpass API вернул таймаут.
3. Граница города слишком большая, а зданий слишком много.
4. OSM содержит мало зданий или плохие высотные теги.
5. Геометрия повреждена.
6. При слишком малом пикселе маска стала слишком большой.
7. `resolution_sweep` сломался на одном разрешении, но мог бы пройти на других.

Для таких случаев включены:

```bash
--continue-on-error
--resolution-sweep-continue-on-error
--skip-existing
--start
--limit
--cities
```

## 17. Важное методическое ограничение

Этот массовый режим пока проверяет только текущую программу как морфометрический калькулятор застройки. Он не проверяет полную термодинамическую гипотезу. Для полной проверки ещё нужны open-space topology, domain mask, настоящая boundary-spanning перколяция, климатические/энергетические данные и статистический слой.

На данном этапе цель другая: понять, насколько устойчиво и массово текущая программа работает на реальных городских данных России и мира.
