# Code behind this spec (snapshot of commit `cd76385`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `model_a/__init__.py`
- `model_a/features.py`
- `model_a/generate.py`
- `model_a/inference.py`
- `model_a/latency_test.py`
- `model_a/policy.py`
- `model_a/schema.py`
- `model_a/train.py`
- `model_a/truth.py`
- `model_a/README.md`
- `model_a/tests/__init__.py`
- `model_a/tests/test_model_a.py`
- `model_a/artifacts/MODEL_CARD.md`
- `model_a/artifacts/evidence.json`
- `model_a/data/DATASET_CARD.md`
- `model_a/data/manifest.json`
- `gateway/src/chemshield_gateway/model_a_client.py`
- `gateway/src/chemshield_gateway/gateway_validator.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
