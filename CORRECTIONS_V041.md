# Reviewed corrections in version 0.4.1

Version 0.4.1 was prepared after reviewing the proposed patch against the 0.4.0 implementation and running a full 25 m control calculation for Zelenograd.

## 1. Multifractal semantics and quality control

The proposed patch called the binary occupancy raster an invalid support and replaced it with building height. That premise is incorrect for the implemented box-moment method: the sum of a binary raster in a box is proportional to occupied footprint area, so it defines a valid uniform measure on occupied cells.

Version 0.4.1 therefore keeps two distinct spectra:

- footprint-area measure, based on the binary building raster;
- height-weighted built-form measure, based on cell-centre building height.

The height field is not exact volume because fractional footprint coverage inside each raster cell is not calculated. It is also model-dependent where the default building height substitutes for missing OSM height.

The theorem that exact generalized dimensions are non-increasing in q is retained as a quality principle. Numerical estimates are checked relative to propagated standard errors of Dq, not with a machine-precision threshold. The slope error of tau(q) is divided by |q-1| for q != 1.

Negative q emphasizes the least occupied boxes and is unstable for sparse finite rasters. Consequently:

- `fit_pass` records the regression criterion;
- `atlas_eligible` additionally requires q >= 0;
- the principal monotonicity check uses well-fitted q >= 0 values;
- a separate diagnostic checks all fitted orders, including negative q.

Zelenograd control result:

- principal non-negative spectra pass the uncertainty-aware check for both measures;
- the all-fitted-order check fails because the negative-q branch is not stable;
- q=-5 and q=-2 fail R² >= 0.95;
- q=-1 has an acceptable simple regression but remains diagnostic rather than an atlas feature;
- the known-height footprint-area fraction is 0.5953.

## 2. Topological integral normalization and interval harmonization

Raw integrals of beta0, beta1 and perimeter over log(r) are retained. Per-city size-reduced values divide by the logarithmic radius span and then by initial component count or characteristic domain length sqrt(A_domain).

Those per-city values are not automatically comparable when sampled intervals differ. Final atlas post-processing therefore changes variables to relative radius

`rho = r / sqrt(A_domain)`

and recomputes the mean normalized integrals over the intersection of relative-radius coverage shared by all quality-eligible cities. The common interval is written into the analysis manifest.

## 3. Spanning definitions are separated rather than silently replaced

The program calculates both full-domain bounding-box spanning and spanning relative to the largest connected component of the analysis domain.

For a disconnected administrative boundary, the full-domain quantity is retained but marked non-interpretable, while the main-component quantity becomes the recommended core-city descriptor. The output records the component count and largest-component area fraction.

## 4. Packaging and reproducibility

- package and project metadata are versioned as 0.4.1;
- workstation and Slurm workflows use one computational core;
- compatibility checks reject 0.4.0 results;
- regression tests use discoverable `tests/test_*.py` names;
- downloaded city data, environments, caches, logs and results are excluded from Git;
- `CITATION.cff`, changelog, release notes and GitHub Actions are included;
- NumPy 1.24 compatibility is retained.

## Validation

The complete suite contains 31 tests and passes. The full Zelenograd 25 m run with topology, both multifractal measures and transport completes successfully. Results from 0.4.0 and 0.4.1 must not be pooled without recalculation of affected outputs.
