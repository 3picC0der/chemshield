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
- `gateway/firewall/c2_network.sh`
- `gateway/firewall/firewall_notes.md`
- `gateway/firewall/raspberry_pi_firewall_template.sh`
- `gateway/threat_model.md`
- `gateway/README.md`
- `hmi/c2_check.py`
- `hmi/common.py`
- `hmi/station/server.py`
- `gateway/systemd/README.md`
- `gateway/systemd/boot_firewall.sh`
- `gateway/systemd/chemshield-firewall.service.in`
- `gateway/systemd/chemshield-station.service.in`
- `gateway/systemd/install.sh`
- `gateway/tests/test_firewall_template.py`
- `gateway/tests/test_systemd_autostart.py`
- `hmi/tests/test_c2_check.py`
- `hmi/tests/test_station.py`
- `hmi/tests/helpers.py`

## Scripts that exist only for this evidence (they live in this folder)

- `make_network_diagram.py`

Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model
(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo
at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.
