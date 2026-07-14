# UrbanFractal Topology v0.4.1

Version 0.4.1 is the reviewed 25 m atlas release. It unifies workstation and Slurm execution around one computational core.

The release keeps the binary footprint-area multifractal measure and adds a separate height-weighted measure; it does not treat height weighting as a replacement for the footprint measure. Multifractal estimates now carry per-order scaling-fit flags and an uncertainty-aware monotonicity diagnostic.

For topology, the release retains full-domain directional spanning and adds largest-domain-component spanning for disconnected administrative boundaries. It records which definition is recommended, the number of domain components and the largest-component area fraction. Raw topology integrals remain available. Atlas post-processing recomputes normalized topology integrals on one shared relative-radius interval across quality-eligible cities.

Validation status:

- 31 automated tests pass;
- the 25 m Zelenograd control calculation completes with topology, both multifractal measures and transport;
- output masks include the height field required for subsequent multifractal diagnostics.

Results generated with internal version 0.4.0 should be recalculated before being combined with this release.
