# UrbanFractal Topology 0.4.1 on a Slurm cluster

The intended HPC layout is:

```text
PROJECT_ROOT/                        source code, read mostly
RUN_ROOT/
├── data/approved_cities/            uploaded GeoJSON inputs
├── results/final/<subset>/<slug>/   per-city results
├── results/slurm_manifests/         one manifest per array task
├── audit/
└── logs/
```

## 1. Create the Python environment once

```bash
cd PROJECT_ROOT
module spider python                  # site-specific
module load <python-3.11-or-newer>    # site-specific, when required
export UF_PYTHON_MODULE='<same-module-name>'
bash slurm/create_env.sh
```

The default environment is `${SCRATCH:-$HOME}/.venvs/urban-fractal-v041`.
Override it with `UF_ENV_ROOT=/path/to/venv`.

## 2. Upload data

Upload the *contents* of the local `approved_cities/` directory into:

```text
RUN_ROOT/data/approved_cities/
```

Do not run the 200-city computation on the login node.

## 3. Submit Moscow only

```bash
export PROJECT_ROOT=/absolute/path/to/urban_fractal_topology_25m_v041
export RUN_ROOT=${SCRATCH:-$HOME}/urban_fractal_200_25m
export UF_ENV_ROOT=${SCRATCH:-$HOME}/.venvs/urban-fractal-v041
export UF_PARTITION=<partition>     # optional when the cluster has a default
export UF_ACCOUNT=<account>         # optional
export UF_QOS=<qos>                 # optional
bash slurm/submit_moscow.sh
```

Default Moscow request: 4 CPUs, 64 GB RAM, 24 h.

## 4. Submit all 200 cities as an array

```bash
export UF_MAX_CONCURRENT=4
export UF_CITY_MEM=32G
export UF_CITY_TIME=24:00:00
bash slurm/submit_all.sh
```

The array is `0-199` and maps one city to one task. A final dependent job
collects tables, builds reports, runs the audit and performs statistical
post-processing. It uses `afterany`, so the audit is still produced when some
cities fail.

## 5. Monitoring

```bash
squeue -u "$USER"
sacct -j JOB_ID --format=JobID,JobName,State,Elapsed,MaxRSS,ReqMem,ExitCode
seff JOB_ID                         # when the site provides seff
```

## 6. Resume

Submit the same command again. Compatible completed `summary.json` files are
skipped. Failed or incompatible cities are recalculated.


## 7. Version and scientific consistency

The workstation and Slurm workflows call the same installed `urban_fractal` package and the same final 25 m parameter set. Do not copy only the `slurm/` directory onto an older source tree. `summary.json` compatibility checks reject completed results from a different software version or critical method configuration.

Version 0.4.1 produces separate footprint-area and height-weighted multifractal outputs and uses recommended spanning plus normalized topology descriptors in final post-processing. Results from 0.4.0 must be recalculated before atlas-level pooling.
