# Статистическая постобработка 200 городов при 25 м

В основном массовом сценарии постобработка запускается автоматически после финального аудита. Для повторного ручного запуска:

```bash
cd /путь/к/urban_fractal_topology_25m_v040
bash scripts/postprocess_all_200_25m.sh /Volumes/aglikflash
```

Основной отчёт:

```text
/Volumes/aglikflash/urban_fractal_200_25m/results/analysis_25m/auto_analysis_report.html
```

К многомерному анализу допускаются только результаты текущей версии, прошедшие основной 2D-контроль и итоговый аудит.

Постпроцессор:

- формирует единую таблицу исправленных признаков;
- использует нормированные на площадь или характерный размер топологические показатели;
- сохраняет 2.5D-показатели как описательные и учитывает полноту высот;
- строит корреляции Спирмена;
- удаляет признаки с большим числом пропусков и нулевой дисперсией;
- удаляет сильно коррелирующие признаки перед кластеризацией;
- выполняет PCA;
- выполняет кластеризацию Уорда в пространстве PCA, объясняющем не менее 90% дисперсии;
- выбирает число кластеров по силуэту;
- оценивает устойчивость кластеров по Adjusted Rand Index при шумовом возмущении и подвыборке признаков;
- ищет робастные выбросы;
- сравнивает российскую и мировую выборки критерием Манна—Уитни с поправкой Бенджамини—Хохберга.

Номера кластеров являются исследовательскими группами, а не автоматически доказанными морфотипами.


## Topology interval harmonization (0.4.1)

The postprocessor does not cluster cities using raw topology integrals or values averaged over different city-specific radius ranges. For quality-eligible cities it converts radius to `rho = r / sqrt(A_domain)`, takes the common coverage interval, interpolates normalized profiles in `log(rho)` and computes harmonized archipelago, void and boundary-complexity descriptors. The interval is recorded in `analysis_manifest.json`.
