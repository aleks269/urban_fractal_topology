# Corrections in v0.4.3

## Overpass downloading

- Updated the global Overpass endpoint list.
- Added per-endpoint control of OSMnx rate-limit polling.
- Disabled `/status` polling for endpoints that do not require it.
- Added an explicit project User-Agent and HTTP referer.
- Removed the Switzerland-only endpoint from the global city downloader.

## Transport solver

- Fixed the Jacobi preconditioner in the sparse transport solver.
- The `LinearOperator` now explicitly operates in `float64`.
- Prevented NumPy casting errors when SciPy initializes the operator
  with an integer test vector.
- Added a regression test using an `int8` sparse matrix.

## Operational note

GNU `timeout` accepts a single duration value with one suffix.
For example, 23 hours 30 minutes must be written as `84600s`,
not `23h30m`.
