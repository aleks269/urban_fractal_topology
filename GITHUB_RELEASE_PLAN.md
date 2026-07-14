# Publishing UrbanFractal Topology 0.4.1

Use one repository and one source tree. The `slurm/` directory is an execution backend, not a separate fork of the scientific code.

## Local publication branch

```bash
cd /Users/aglikmac/jupyter/urban_fractal_topology-git
git status
git pull --ff-only origin main
git switch -c release/0.4.1

rsync -av --delete \
  --exclude '.git/' \
  /PATH/TO/urban_fractal_topology_25m_v041_slurm_reviewed/ \
  /Users/aglikmac/jupyter/urban_fractal_topology-git/

python -m pytest -q
find . -name '.DS_Store' -o -name '__pycache__' -o -name '.pytest_cache' -o -name '*.bak'
git status --short
git add -A
git commit -m "Release UrbanFractal Topology v0.4.1"
git push -u origin release/0.4.1
```

Open a pull request from `release/0.4.1` into `main`. Merge only after GitHub Actions passes.

## Tag and release

```bash
git switch main
git pull --ff-only origin main
git tag -a v0.4.1 -m "UrbanFractal Topology v0.4.1"
git push origin v0.4.1

gh release create v0.4.1 \
  --title "UrbanFractal Topology v0.4.1" \
  --notes-file RELEASE_NOTES_V041.md
```

Do not force-push `main`. Do not commit downloaded city GeoJSON, virtual environments, batch results, node scratch data or Slurm logs.
