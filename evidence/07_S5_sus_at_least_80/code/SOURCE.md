# Code behind this spec (snapshot of commit `cd76385`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `hmi/__init__.py`
- `hmi/__main__.py`
- `hmi/app.py`
- `hmi/common.py`
- `hmi/demo.py`
- `hmi/facilitator.py`
- `hmi/static/hmi.css`
- `hmi/static/hmi.js`
- `hmi/static/index.html`
- `hmi/DESIGN.md`
- `hmi/wireframe.html`
- `hmi/README.md`

## Scripts that exist only for this evidence (they live in this folder)

- `sus_score.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
