# Technical review of the proposed 0.4.1 patch

## Scope

Reviewed inputs:

- workstation package `urban_fractal_topology_25m_v040_corrected`;
- Slurm package `urban_fractal_topology_25m_v040_slurm_ready`;
- proposed patch containing replacements for `metrics.py`, `pipeline.py`, `raster.py` and `topology.py`.

The baseline 0.4.0 suite passed 22 tests before changes.

## Proposed Fix 1: replace the binary multifractal input with height

### What the patch changes

The patch adds a weighted rasterizer, burns `_height_m` into the analysis grid, replaces `building_mask.astype(float)` in the multifractal call and adds an exact monotonicity flag with tolerance `1e-6`.

### Review

The diagnosis is not correct. In the implemented box-moment method, summing a binary occupancy field inside a box yields the number of occupied cells and therefore a uniform footprint-area measure. It is not merely an invalid support indicator. A deterministic Sierpinski-carpet regression test gives the same theoretical Dq for all q from a binary field.

Height weighting defines another measure. It asks how built-form height mass is distributed, whereas the binary field asks how footprint area is distributed. Replacing one by the other discards a valid descriptor and changes the scientific question.

The proposed exact monotonicity threshold is also unsuitable for finite regression estimates. On the 25 m Zelenograd control, the proposed height-only change still gives a formally non-monotone estimated sequence. Thus the patch does not achieve its stated purpose.

The reviewed implementation retains both measures, propagates the slope uncertainty from tau(q) to Dq, marks regression quality per q, uses well-fitted q >= 0 values as principal atlas features, and keeps negative q as diagnostics.

## Proposed Fix 2: normalize topology integrals

### What the patch changes

The patch divides raw integrals over log radius by the sampled log-radius span, then divides beta-based quantities by the initial component count and perimeter by the characteristic length sqrt(A_domain).

### Review

The diagnosis is correct: raw integrals are driven by city size, component count and the radius interval and must not be used directly in inter-city clustering.

The proposed normalization is useful but incomplete. Two cities averaged over different radius intervals are still not directly comparable. The reviewed postprocessor transforms radius to rho = r/sqrt(A_domain), finds the common interval shared by all quality-eligible cities, interpolates the normalized profiles in log(rho), and recomputes the three principal topology integrals on that common interval.

## Proposed Fix 3: largest-component spanning

### What the patch changes

The patch moves directional side bands from the full administrative bounding box to the largest connected component of the city domain.

### Review

The identified exclave failure is real. For a disconnected administrative domain, dilation clipped to the domain cannot bridge disconnected pieces, so whole-domain directional spanning can become an administrative-boundary artifact.

However, silently replacing the definition changes the observable. The reviewed implementation reports both definitions, preserves the legacy full-domain fields, adds explicit main-component fields, records the number and area share of domain components, and declares which spanning reference is recommended.

## Packaging defects in the proposed patch

- The test file is named `test fixes v041.py` outside the normal `tests/test_*.py` pattern, so standard pytest discovery does not run it.
- The patch archive does not contain the actual version updates for both `pyproject.toml` and `urban_fractal/__init__.py`, despite describing version 0.4.1.
- An existing compatibility test was hard-coded to 0.4.0 and fails after a version bump.
- The claim that every fix can be reconstructed from saved masks/profiles is false for the proposed height measure: 0.4.0 `analysis_masks.npz` does not contain a height field. Raw city GeoJSON must be rerasterized, although no OSM redownload is required.
- The original patch does not update atlas post-processing, so its new normalized fields and spanning semantics would not reliably reach the final comparative analysis.

## Reviewed 0.4.1 result

- 31 tests pass in workstation and Slurm distributions.
- Full 25 m Zelenograd calculation completes with topology, footprint multifractal, height-weighted multifractal and transport.
- Principal q >= 0 multifractal diagnostics pass within propagated regression uncertainty for both measures.
- The all-fitted-order diagnostic fails because the negative-q branch remains unstable; negative q is therefore excluded from principal atlas features.
- Slurm scripts pass shell syntax checks and a one-city dry run produces the expected final 25 m command and manifest.

## Decision before the 200-city calculation

Do not apply the proposed patch verbatim. Use the reviewed unified 0.4.1 tree before starting the long calculation. Continue downloading city files: the downloader is independent of these changes. Do not mix completed 0.4.0 results with 0.4.1 outputs; the batch compatibility check will force recalculation.
