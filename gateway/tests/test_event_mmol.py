"""C3: at most 50 mmol of corrective reagent per event, counted by the gateway itself.

Before this, the HMI sent recovery_mmol_after_command = min(50, cumulative + volume_ml):
millilitres, not mmol, capped at 50, so the gateway's "> 50" check could never fire and the
sixth 10 mL dose went through at "50". Now the command names its bottle (channel_id) and
the gateway computes volume_ml x molarity and keeps the total per event_id.

    python gateway/tests/test_event_mmol.py      (or: pytest gateway/tests)
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway" / "src"))
sys.path.insert(0, str(ROOT))

from chemshield_gateway.auth import attach_hmac  # noqa: E402
from chemshield_gateway.config import CHANNEL_MOLARITY, GatewayConfig  # noqa: E402
from chemshield_gateway.gateway_validator import GatewayValidator  # noqa: E402
from chemshield_gateway.models import ProcessState  # noqa: E402
from chemshield_gateway.test_data import ManualClock, unsigned_command  # noqa: E402

CONFIG = GatewayConfig()


class Dosing:
    """Sends signed commands to one gateway, one mixing period apart."""

    def __init__(self) -> None:
        self.clock = ManualClock()
        self.gw = GatewayValidator(config=CONFIG, clock=self.clock)
        self.i = 0

    def send(self, channel_id: str, volume_ml: float, event_id: str = "EVT-C3", **extra):
        self.i += 1
        self.clock.advance(CONFIG.min_mixing_time_s)
        now = datetime.now(timezone.utc)
        cmd = unsigned_command(CONFIG, command_id=f"C3-{self.i:03d}", event_id=event_id,
                               timestamp_utc=now, nonce=f"N-C3-{self.i:03d}", sequence_number=self.i,
                               channel_id=channel_id, volume_ml=volume_ml)
        cmd.update(extra)                       # e.g. a client's own mmol claim, signed along
        return self.gw.validate(attach_hmac(cmd, CONFIG.hmac_secret), category="c3_test",
                                received_at_utc=now)


def test_mmol_is_volume_times_molarity():
    d = Dosing()
    r = d.send("BASE_BULK", 10.0)
    assert (r.decision, r.dose_mmol, r.event_mmol_total) == ("ACCEPT", 5.0, 5.0)
    r = d.send("ACID_FINE", 12.0)          # (the Model A stand-in blocks 18 mL and up)
    assert (r.decision, r.dose_mmol, r.event_mmol_total) == ("ACCEPT", 0.06, 5.06)


def test_50_mmol_per_event_ignoring_the_clients_number():
    d = Dosing()
    # ten 10 mL doses of 0.5 M = 50 mmol, each claiming the event has used 0 mmol
    for _ in range(10):
        r = d.send("ACID_BULK", 10.0, recovery_mmol_after_command=0.0)
        assert r.decision == "ACCEPT", r
    assert r.event_mmol_total == 50.0 and d.gw.state.cumulative_recovery_mmol == 50.0
    r = d.send("ACID_BULK", 10.0, recovery_mmol_after_command=0.0)
    assert (r.decision, r.reason_code) == ("REJECT", "EVENT_MMOL_LIMIT"), r
    assert d.send("ACID_FINE", 0.5).reason_code == "EVENT_MMOL_LIMIT"      # even 0.0025 mmol
    # a new event has its own budget; the old one stays spent
    assert d.send("ACID_BULK", 10.0, event_id="EVT-C3-B").decision == "ACCEPT"
    assert d.gw.event_mmol_used == {"EVT-C3": 50.0, "EVT-C3-B": 5.0}


def test_bad_channels_and_volumes_rejected():
    d = Dosing()
    for channel, volume in (("base", 10.0), ("NONE", 10.0), ("BASE_BULK", -10.0),
                            ("BASE_BULK", 0.0), ("BASE_BULK", math.nan), ("BASE_BULK", math.inf)):
        r = d.send(channel, volume)
        assert r.decision == "REJECT" and not r.forwarded_to_actuator, (channel, volume, r)
    assert d.gw.event_mmol_used == {}


def test_audit_records_carry_channel_mmol_and_model_a():
    d = Dosing()
    d.send("BASE_FINE", 12.0)
    rec = d.gw.audit_log.records[-1]
    assert (rec.channel_id, rec.volume_ml, rec.dose_mmol, rec.event_mmol_total) == ("BASE_FINE", 12.0, 0.06, 0.06)
    assert rec.model_a_label == "ACCEPTABLE_CONTEXT" and rec.model_a_score > 0
    assert d.gw.audit_log.verify()


def test_molarity_matches_the_planner():
    from redosing.planner import CHANNEL_MOLARITY as PLANNER
    assert CHANNEL_MOLARITY == PLANNER


def test_hmi_eleven_bulk_doses():
    """Through the HMI path, during one recovery event: 10 x 5 mmol accepted, the 11th refused."""
    from hmi.tests.helpers import station_with_stand_in_model_a, hmi_dose
    st, clock, run = station_with_stand_in_model_a()
    st.set_auto_recovery(False)
    st.link.set_ph(4.0)                                         # an unsafe acid event
    run(6)
    assert st.event is not None
    out = []
    for _ in range(11):
        run(15.1)
        r = hmi_dose(st, "BASE_BULK", 10.0, event_id=st.event["id"])
        out.append(r)
        if r["decision"] == "ACCEPT":
            st.cancel_dose(r["command_id"])                     # counted by the gateway anyway
    assert [r["decision"] for r in out] == ["ACCEPT"] * 10 + ["REJECT"], [r["reason_code"] for r in out]
    assert out[-1]["reason_code"] == "EVENT_MMOL_LIMIT"
    assert st.gateway.event_mmol_used[st.event["id"]] == 50.0


TESTS = [test_mmol_is_volume_times_molarity, test_50_mmol_per_event_ignoring_the_clients_number,
         test_bad_channels_and_volumes_rejected, test_audit_records_carry_channel_mmol_and_model_a,
         test_molarity_matches_the_planner, test_hmi_eleven_bulk_doses]


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
