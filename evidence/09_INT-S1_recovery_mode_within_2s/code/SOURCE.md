# Code behind this spec (snapshot of commit `cd76385`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `hmi/station/__init__.py`
- `hmi/station/__main__.py`
- `hmi/station/audit.py`
- `hmi/station/core.py`
- `hmi/station/links.py`
- `hmi/station/server.py`
- `hmi/common.py`
- `hmi/int_s1_batch.py`
- `hmi/mock_uno.py`
- `firmware/uno/chemshield_uno/Makefile`
- `firmware/uno/chemshield_uno/chemshield_uno.ino`
- `firmware/uno/uno_tool.py`

## Scripts that exist only for this evidence (they live in this folder)

- `make_dry_run_plot.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
