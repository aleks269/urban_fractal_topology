# Запуск 200 городов на внешнем диске, шаг 25 м

## Команда

```bash
cd /путь/к/urban_fractal_topology_25m_v040
chmod +x scripts/run_all_200_25m_external.sh
bash scripts/run_all_200_25m_external.sh /Volumes/aglikflash
```

На macOS сценарий использует `caffeinate`, чтобы не допустить сна компьютера во время длительной работы.

## Что выполняется

Сценарий последовательно:

1. проверяет подключение и возможность записи на внешний диск;
2. создаёт или переиспользует `~/.venvs/urban-fractal-25m`;
3. устанавливает текущую версию проекта и запускает тесты;
4. скачивает границы и контуры зданий для 200 городов;
5. запускает полный расчёт на 25 м;
6. создаёт индивидуальные и общий базовый отчёты;
7. выполняет итоговый аудит качества;
8. выполняет статистическую постобработку допущенных городов.

Полный расчёт включает:

- маску реальной области анализа;
- устойчивую оценку box-counting на диапазоне 50–3200 м;
- доменно-ограниченную лакунарность;
- двойственную цифровую топологию;
- giant-component и направленную spanning-перколяцию как разные величины;
- мультифрактальный спектр с сохранением массы;
- 2.5D-оболочку без двойного учёта общих стен;
- двухфазный стационарный перенос и диссипацию в направлениях LR/TB.

## Повторный запуск

Та же команда безопасна для повторного запуска. Город пропускается только тогда, когда его `summary.json` создан текущей версией методики. Старые результаты автоматически признаются несовместимыми и пересчитываются.

Сбой одного города не останавливает всю серию. Ошибка сохраняется в пакетном манифесте и логах, а город будет обработан повторно при следующем запуске.

## Каталоги и отчёты

```text
/Volumes/aglikflash/urban_fractal_200_25m/
├── data/approved_cities/
├── results/
│   ├── final/russia/<city>/
│   ├── final/world/<city>/
│   ├── city_features_final_25m.csv
│   ├── all_results_summary.csv
│   ├── all_results_index.html
│   ├── comparison_plots/
│   └── analysis_25m/
│       ├── auto_analysis_report.html
│       ├── city_features_enriched.csv
│       ├── analysis_eligible_cities.csv
│       ├── correlations_spearman.csv
│       ├── pca_scores.csv
│       ├── clusters.csv
│       ├── cluster_stability_summary.csv
│       └── outliers.csv
├── audit/
│   ├── audit_before_calculation.csv
│   ├── audit_final_25m.csv
│   └── audit_final_25m.json
├── logs/
└── RUN_COMPLETE.txt
```

Основные отчёты:

```bash
open /Volumes/aglikflash/urban_fractal_200_25m/results/all_results_index.html
open /Volumes/aglikflash/urban_fractal_200_25m/results/analysis_25m/auto_analysis_report.html
open /Volumes/aglikflash/urban_fractal_200_25m/audit/audit_final_25m.csv
```

Текущий журнал:

```bash
tail -f /Volumes/aglikflash/urban_fractal_200_25m/logs/run_*.log
```

## Критерии итогового аудита

По умолчанию проверяются:

- версия методики 0.4.0;
- размер пикселя 25 м;
- `all_touched=False`;
- наличие исходной границы без fallback на прямоугольник;
- ошибка площади зданий не более 5%;
- ошибка площади растровой границы не более 3%;
- `R²` box-counting не ниже 0.95;
- минимум 6 масштабов;
- CV по смещениям сетки не более 5%;
- leave-one-scale-out CV не более 5%;
- наличие направленных spanning-показателей;
- наличие transport-блока;
- ошибка энергетического тождества не более `1e-5`.

Низкая полнота высот и отсутствие независимой проверки полноты OSM помечаются предупреждениями, а не скрываются.
