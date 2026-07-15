# Changelog

All notable public changes are recorded here.

## [0.4.2] — 2026-07-15

Patch release for safe and reproducible OSM city downloads.

### Added

- Boundary-only validation mode before Overpass downloads.
- Exact OSM relation/way overrides for ambiguous city names.
- Boundary area and bounding-box diagonal validation.
- Per-city boundary-resolution reports and failed-city lists.
- Explicit cache, timeout, retry and fail-fast controls.
- Regression tests for non-polygonal Nominatim results and oversized boundaries.

### Changed

- `configs/city_catalog_200.csv` is the single city catalog used by the downloader.
- GeoJSON output is written atomically.
- Existing city outputs are trusted only after boundary validation.
- The downloader releases large GeoDataFrames after each city.

### Fixed

- A non-polygonal first Nominatim result no longer prevents ranked-result fallback.
- Failed cities now produce a non-zero command exit status.
- One failed city no longer appears as a successful catalog download.

## [0.4.1] — 2026-07-14

Reviewed release candidate for the 25 m urban atlas workflow.

### Added

- Separate footprint-area and height-weighted multifractal measures.
- Per-order multifractal fit flags and uncertainty-aware monotonicity diagnostics.
- Main-domain-component directional spanning alongside legacy full-domain spanning.
- Domain connectivity diagnostics and explicit recommended spanning reference.
- Normalized topology integrals and post-processing on a shared relative-radius interval.
- Height raster in `analysis_masks.npz` for reproducible diagnostics.
- Slurm array-job deployment in the unified distribution.
- Mathematical methods document, release validation and regression tests.

### Changed

- Atlas post-processing uses recommended spanning and normalized topology descriptors.
- Poorly fitted multifractal orders are excluded from principal comparative features.
- Footprint-area and height-weighted spectra are never pooled under the same feature names.

### Fixed

- Disconnected administrative exclaves no longer silently determine the principal spanning metric.
- Raw topology integrals are no longer treated as directly inter-city-comparable descriptors.
- Version checks in batch compatibility tests now follow the package version.

### Compatibility

The output schema differs from internal version 0.4.0. Results from 0.4.0 and 0.4.1 must not be pooled without explicit migration and recomputation of affected quantities.

## [0.4.0] — internal, not publicly released

Boundary-aware 25 m pipeline used as the baseline for the reviewed 0.4.1 corrections.

## [0.3.0] — 2026

Initial public research prototype.
