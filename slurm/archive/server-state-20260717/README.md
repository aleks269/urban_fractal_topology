# Archived server scripts: 2026-07-17

These Slurm scripts preserve the audited server state captured on
2026-07-17.

They are retained for provenance and reproducibility only. They are not
current v0.4.4 execution scripts and must not be submitted directly.

Known limitations include:

- hard-coded v0.4.2 repository and run paths;
- absolute server-specific filesystem paths;
- hard-link snapshot creation with `cp -al`;
- assumptions about historical run directory layouts;
- the Russia-100 atlas script passes the full 200-city catalog to the
  interactive atlas generator instead of the generated Russia-only
  catalog;
- no v0.4.4 run manifest, stage timing, checkpoint, or resume support.

Replacement production scripts will be developed separately after the
v0.4.4 execution model and manifest format are stabilized.
