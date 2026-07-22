# Archived server scripts: 2026-07-17

These scripts preserve the audited server state captured on 2026-07-17.

They are retained for provenance and reproducibility only. They are not
current v0.4.4 production scripts and must not be submitted directly.

Known limitations:

- hard-coded v0.4.2 repository and run paths;
- server-specific absolute filesystem paths;
- hard-link snapshot creation with `cp -al`;
- assumptions about historical run-directory layouts;
- the Russia-100 atlas script passes the complete 200-city catalog
  instead of the generated Russia-only catalog;
- no v0.4.4 stage timing, checkpoints, resume support, or complete run
  manifest.

Replacement production scripts will be created after the v0.4.4
execution and manifest formats are stabilized.
