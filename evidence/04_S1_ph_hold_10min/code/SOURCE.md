# Code behind this spec (snapshot of commit `cd76385`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `hmi/station/core.py`
- `hmi/station/links.py`
- `hmi/common.py`
- `firmware/uno/chemshield_uno/Makefile`
- `firmware/uno/chemshield_uno/chemshield_uno.ino`
- `firmware/uno/uno_tool.py`
- `firmware/uno/README.md`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
