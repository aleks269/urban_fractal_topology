# Каталог 200 городов для UrbanFractal Topology

Файл `configs/city_catalog_200.csv` содержит 200 городов:

- 100 городов России;
- 100 мировых городов.

Каталог совместим с существующими скриптами:

```bash
python batch_tools/download_city_catalog.py --catalog configs/city_catalog_200.csv --list
python batch_tools/download_city_catalog.py --catalog configs/city_catalog_200.csv --set russia --list
python batch_tools/download_city_catalog.py --catalog configs/city_catalog_200.csv --set world --list
```

## Столбцы

- `subset` — группа: `russia` или `world`;
- `slug` — машинное имя города для папок и фильтрации;
- `name` — человекочитаемое имя;
- `query` — строка геокодирования для OSMnx/Nominatim;
- `morphotype` — рабочая морфологическая метка.

## Принцип отбора

Каталог не является статистически репрезентативной выборкой всех городов мира. Это тестовый эксплуатационный набор для проверки устойчивости программы на разных типах городской морфологии.

Российская часть включает мегаполисы, исторические малые города, волжские и речные города, промышленные и моногорода, северные/арктические города, дальневосточные города, курортные и горно-прибрежные города, наукограды и спутники.

Мировая часть включает не только крупнейшие и центральные мегаполисы, но и города с разными морфологиями: регулярные сетки, исторические ядра, водные и островные структуры, пустынный sprawl, горные/долинные города, порты, плановые столицы, дельтовые города, высокоплотные азиатские города, африканские быстрорастущие города и города Океании.

## Рекомендуемый порядок запуска

Сначала проверить каталог:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --list
```

Скачать несколько городов для проверки:

```bash
python batch_tools/download_city_catalog.py \
  --catalog configs/city_catalog_200.csv \
  --out data/approved_cities \
  --cities pskov,zelenograd,venice,singapore,cape_town \
  --sleep 5
```

Быстрый расчёт:

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

После теста можно скачать все 200:

```bash
bash scripts/download_200_cities.sh
```

Первый массовый расчёт лучше делать в грубом режиме:

```bash
bash scripts/run_200_quick.sh
```

Затем запускать topology + resolution sweep:

```bash
bash scripts/run_200_sweep.sh
```

Полный расчёт с топологией и мультифрактальностью для всех 200 лучше начинать с `pixel=50`:

```bash
bash scripts/run_200_final_50m.sh
```

## Предупреждение

Наличие города в каталоге не гарантирует, что OSM/Nominatim/Overpass успешно вернут корректную административную границу и полный слой зданий. Для массового запуска обязательно использовать `--continue-on-error` и затем смотреть `batch_manifest_*.csv`.
