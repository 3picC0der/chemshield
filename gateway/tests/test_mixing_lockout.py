"""S2: at least 15 s of mixing between accepted doses, enforced by the gateway itself.

Before this, only the tests ever set mixing_lockout_remaining_s, so six back-to-back
10 mL doses through the HMI's /api/dose were all accepted.

    python gateway/tests/test_mixing_lockout.py      (or: pytest gateway/tests)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway" / "src"))
sys.path.insert(0, str(ROOT))

from chemshield_gateway.config import GatewayConfig  # noqa: E402
from chemshield_gateway.gateway_validator import GatewayValidator  # noqa: E402
from chemshield_gateway.security_test_runner import run_security_test  # noqa: E402
from chemshield_gateway.test_data import ManualClock, make_command  # noqa: E402

CONFIG = GatewayConfig()


def _dose(gw: GatewayValidator, i: int, **kw):
    now = datetime.now(timezone.utc)
    cmd = make_command(CONFIG, command_id=f"LOCK-{i:03d}", event_id="EVT-LOCK", timestamp_utc=now,
                       nonce=f"N-LOCK-{i:03d}", sequence_number=i, **kw)
    return gw.validate(cmd, category="lockout_test", received_at_utc=now)


def test_second_dose_waits_15_s():
    clock = ManualClock()
    gw = GatewayValidator(config=CONFIG, clock=clock)
    assert _dose(gw, 1).decision == "ACCEPT"
    r = _dose(gw, 2)
    assert (r.decision, r.reason_code) == ("REJECT", "MIXING_LOCKOUT")
    clock.advance(14.9)
    r = _dose(gw, 3)
    assert (r.decision, r.reason_code) == ("REJECT", "MIXING_LOCKOUT")
    assert 0.0 < gw.state.mixing_lockout_remaining_s <= 0.11
    clock.advance(0.1)
    assert _dose(gw, 4).decision == "ACCEPT"                    # exactly 15 s after dose 1
    assert gw.state.last_dose_accepted_at_s == clock.t


def test_hmi_six_back_to_back_doses():
    from hmi import app as hmi
    hmi.gateway.clock = ManualClock(1000.0)
    results = [hmi.api_dose(hmi.DoseRequest(**_hmi_body(10.0))) for _ in range(6)]
    assert [r["decision"] for r in results] == ["ACCEPT"] + ["REJECT"] * 5, results
    assert all(r["reason_code"] == "MIXING_LOCKOUT" for r in results[1:])
    hmi.gateway.clock.advance(15.0)
    assert hmi.api_dose(hmi.DoseRequest(**_hmi_body(10.0)))["decision"] == "ACCEPT"
    assert hmi.api_ack()["mode"] == "NORMAL"                        # ACK does not clear it
    assert hmi.api_state()["mixing_lockout_remaining_s"] == 15.0


def _hmi_body(volume_ml: float) -> dict:
    return {"reagent": "base", "volume_ml": volume_ml}


def test_attack_runner_bursts_meet_a_real_lockout():
    with tempfile.TemporaryDirectory() as d:
        s = run_security_test(Path(d), per_category=50)
    cats = {c["category"]: c for c in s["category_results"]}
    assert cats["valid"]["accepted"] == 50
    assert cats["burst_during_lockout"]["accepted"] == 0
    assert s["malicious_commands_reaching_actuator"] == 0


TESTS = [test_second_dose_waits_15_s, test_hmi_six_back_to_back_doses,
         test_attack_runner_bursts_meet_a_real_lockout]


if __name__ == "__main__":
    bad = 0
    for t in TESTS:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
        except Exception as exc:                                     # noqa: BLE001
            bad += 1
            print(f"  [FAIL] {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - bad}/{len(TESTS)} checks passed")
    sys.exit(1 if bad else 0)
