# Code behind this spec (snapshot of commit `a4b9a03`)

These files are copies of the live code at the repo-relative path shown; read them here next to
the test sheet. The running system uses the originals in the repo root.

- `gateway/src/chemshield_gateway/__init__.py`
- `gateway/src/chemshield_gateway/audit_log.py`
- `gateway/src/chemshield_gateway/auth.py`
- `gateway/src/chemshield_gateway/c2_path_test.py`
- `gateway/src/chemshield_gateway/config.py`
- `gateway/src/chemshield_gateway/failsafe.py`
- `gateway/src/chemshield_gateway/gateway_validator.py`
- `gateway/src/chemshield_gateway/model_a_client.py`
- `gateway/src/chemshield_gateway/models.py`
- `gateway/src/chemshield_gateway/plots.py`
- `gateway/src/chemshield_gateway/recovery_timing.py`
- `gateway/src/chemshield_gateway/security_test_runner.py`
- `gateway/src/chemshield_gateway/simulated_actuator.py`
- `gateway/src/chemshield_gateway/test_data.py`
- `gateway/attack_script.py`
- `gateway/tests/test_event_mmol.py`
- `gateway/tests/test_mixing_lockout.py`
- `hmi/attack_station.py`
- `hmi/verify_log.py`
- `hmi/station/audit.py`
- `hmi/station/core.py`
- `hmi/common.py`
- `hmi/tests/test_station.py`
- `hmi/tests/helpers.py`

## Scripts that exist only for this evidence (they live in this folder)

- `make_attack_plot.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
