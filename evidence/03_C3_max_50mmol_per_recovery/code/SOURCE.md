# Code behind this spec (snapshot of commit `cd76385`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `gateway/src/chemshield_gateway/gateway_validator.py`
- `gateway/src/chemshield_gateway/config.py`
- `gateway/tests/test_event_mmol.py`
- `hmi/station/core.py`
- `hmi/common.py`
- `sim/__init__.py`
- `sim/batch.py`
- `sim/chemistry.py`
- `sim/engine.py`
- `sim/live.py`
- `sim/make_placeholder_table.py`
- `sim/model.py`
- `sim/rdo.py`
- `sim/scenarios.py`
- `sim/sim2.py`
- `sim/README.md`
- `sim/tests/__init__.py`
- `sim/tests/test_dose_speed.py`
- `sim/tests/test_known_answers.py`
- `sim/tests/test_table_inverse.py`
- `sim/tests/test_tank_liquid.py`
- `sim/aspen_tables/README.md`
- `redosing/__init__.py`
- `redosing/planner.py`
- `redosing/run_all.py`
- `redosing/README.md`
- `redosing/qc/__init__.py`
- `redosing/qc/common.py`
- `redosing/qc/far_side.py`
- `redosing/qc/histogram.py`
- `redosing/qc/imr.py`
- `redosing/qc/style.py`
- `redosing/qc/traces.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
