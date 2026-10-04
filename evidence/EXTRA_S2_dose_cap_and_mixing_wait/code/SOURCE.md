# Code behind this spec (snapshot of commit `a4b9a03`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `gateway/src/chemshield_gateway/gateway_validator.py`
- `gateway/src/chemshield_gateway/config.py`
- `gateway/tests/test_mixing_lockout.py`
- `hmi/station/core.py`
- `hmi/tests/test_station.py`
- `hmi/tests/helpers.py`

## Scripts that exist only for this evidence (they live in this folder)

- `extract_s2_rows.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
