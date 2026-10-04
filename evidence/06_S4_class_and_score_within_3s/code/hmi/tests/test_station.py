"""HMI and station checks, one per test-sheet behaviour. Run from the repo folder:

    .venv/bin/python -m pytest hmi/tests -q

The station tests use a hand-moved clock and the simulated tank, so they run in seconds.
The last two start the real servers (station + laptop HMI) and go through HTTP.
"""
from __future__ import annotations

import json
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")

from hmi.common import (  # noqa: E402
    gateway_config,
    new_dose_command,
    new_operator_action,
    next_sequence,
)
from hmi.station.audit import verify_records  # noqa: E402
from hmi.station.core import Station  # noqa: E402
from hmi.station.links import SimLink  # noqa: E402

SECRET = "test-secret-for-hmi-tests"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def make(start_ph: float = 7.0, auto_pump: bool = True, dwell_s: float = 5.0, seed: int = 261):
    clk = Clock()
    link = SimLink(start_ph=start_ph, auto_pump=auto_pump, seed=seed, clock=clk)
    st = Station(link, SECRET, log_dir=Path(tempfile.mkdtemp()), clock=clk, dwell_s=dwell_s)
    link.start()

    def run(seconds: float) -> None:
        end = clk.t + seconds
        while clk.t < end:
            clk.t += 0.1
            st.tick()

    run(6)
    return st, link, clk, run


def dose(st: Station, channel: str, ml: float, event_id: str | None = None, secret: str = SECRET):
    eid = event_id or (st.event["id"] if st.event else f"OPS-{int(st.clock() * 10)}")
    cmd = new_dose_command(gateway_config(secret), channel_id=channel, volume_ml=ml, event_id=eid,
                           sequence_number=next_sequence(st.gateway.last_sequence_number))
    with st.lock:
        return st._submit(cmd, source="HMI", sender="test"), cmd


# ------------------------------------------------------------------ CHE-AT-02 (S2)
def test_dose_cap_lockout_and_one_dose_at_a_time():
    st, link, clk, run = make(auto_pump=False)
    r, _ = dose(st, "BASE_FINE", 25)
    assert (r["decision"], r["reason_code"]) == ("REJECT", "DOSE_LIMIT")
    r, cmd = dose(st, "BASE_FINE", 20)
    assert r["decision"] == "ACCEPT" and st.pending and link.dose_on        # the dose light is on
    r2, _ = dose(st, "BASE_FINE", 5)
    assert r2["reason_code"] == "DOSE_PENDING"                               # one dose at a time
    with st.lock:
        assert st.dose_added(cmd["command_id"])["ok"]
    assert not link.dose_on
    run(5)
    r3, _ = dose(st, "BASE_FINE", 5)
    assert r3["reason_code"] == "MIXING_LOCKOUT"                             # inside 15 s
    run(11)
    r4, _ = dose(st, "BASE_FINE", 5)
    assert r4["decision"] == "ACCEPT"                                        # after 15 s


# ------------------------------------------------------------------ ICS-AT-03 (S4)
def test_model_a_classifies_and_blocks_an_unsafe_dose():
    st, link, clk, run = make()
    with st.lock:
        link.set_ph(6.3)            # INT-AT-04 step 4 (6.3, not 6.0: at 6.0 noise can confirm an event)
    run(6)
    assert st.mode == "NORMAL"
    r, _ = dose(st, "ACID_BULK", 20)
    assert r["decision"] == "REJECT" and r["reason_code"] == "MODEL_A_BLOCK"
    assert r["model_a_label"] == "HARMFUL_CONTEXT" and 0.0 <= r["model_a_score"] <= 1.0
    assert r["model_a_latency_ms"] < 3000


# ------------------------------------------------------------------ ICS-AT-01 / ICS-AT-02
def test_unsigned_forged_replayed_and_stale_commands_are_rejected():
    st, link, clk, run = make()
    unsigned = new_dose_command(gateway_config(SECRET), channel_id="BASE_FINE", volume_ml=1, event_id="OPS-x",
                                sequence_number=next_sequence(0))
    unsigned.pop("hmac_sha256")
    with st.lock:
        assert st._submit(unsigned, source="HMI", sender="t")["reason_code"] == "MISSING_SIGNATURE"
    assert dose(st, "BASE_FINE", 1, secret="wrong-key")[0]["reason_code"] == "INVALID_HMAC"
    r, cmd = dose(st, "BASE_FINE", 1)
    assert r["decision"] == "ACCEPT"
    with st.lock:
        assert st._submit(dict(cmd), source="HMI", sender="t")["group"] == "REPLAY"
    stale = new_dose_command(gateway_config(SECRET), channel_id="BASE_FINE", volume_ml=1, event_id="OPS-y",
                             sequence_number=next_sequence(st.gateway.last_sequence_number), age_s=5)
    with st.lock:
        assert st._submit(stale, source="HMI", sender="t")["reason_code"] == "STALE_TIMESTAMP"
    assert st.counters["REPLAY"] == 1 and st.counters["STALE"] == 1


def test_a_copy_of_a_rejected_command_is_still_a_replay():
    st, link, clk, run = make()
    r, cmd = dose(st, "BASE_FINE", 25)                 # rejected (over the cap)
    with st.lock:
        again = st._submit(dict(cmd), source="HMI", sender="t")
    assert r["reason_code"] == "DOSE_LIMIT" and again["reason_code"] == "REUSED_NONCE"


# ------------------------------------------------------------------ INT-AT-01 (INT-S1)
def test_unsafe_event_switches_to_recovery_and_locks_the_uno():
    st, link, clk, run = make()
    with st.lock:
        link.upset(7.0, acid=True)                     # acid by syringe, past the gateway
    for _ in range(200):
        run(0.1)
        if st.events:
            break
    assert st.events and st.events[0]["direction"] == "acid" and st.mode == "RECOVERY"
    ev = st.events[0]
    assert ev["t_recovery"] - ev["t_confirm"] < 2.0
    assert link.last_mode_ack and link.last_mode_ack["mode"] in ("RECOVERY", "NORMAL")
    assert any(r.reason_code == "RECOVERY_ENTERED" for r in st.audit.records)
    with st.lock:
        assert st.hmi_shown(ev["id"])["ok"]
    row = st._timing_row(ev)
    assert row["confirm_to_hmi_shown_ms"] is not None and row["pass_2s"]


# ------------------------------------------------------------------ INT-AT-02, ISE-AT-01/02
def test_recovery_restores_ph_within_300_s_and_50_mmol():
    st, link, clk, run = make(dwell_s=10)
    with st.lock:
        link.upset(40.0, acid=True)                    # 20 mmol of acid
    for _ in range(400):
        run(1)
        if st.events and st.events[-1]["status"] == "closed":
            break
    ev = st.events[-1]
    assert ev["status"] == "closed" and st.mode == "NORMAL"
    assert ev["recovery_time_s"] < 300
    assert st.gateway.event_mmol_used[ev["id"]] <= 50.0
    assert all(d["sender"].startswith("recovery planner") for d in ev["doses"])


def test_manual_dose_past_50_mmol_is_rejected_during_recovery():
    st, link, clk, run = make()
    with st.lock:
        link.upset(40.0, acid=True)
    for _ in range(200):
        run(0.1)
        if st.event is not None:
            break
    assert st.event is not None
    with st.lock:
        st.set_auto_recovery(False)
        if st.pending:
            st._cancel_pending("test")
        st.gateway.event_mmol_used[st.event["id"]] = 45.0
    run(16)
    r, _ = dose(st, "BASE_BULK", 12, event_id=st.event["id"])       # 6 mmol -> 51
    assert r["reason_code"] == "EVENT_MMOL_LIMIT"


# ------------------------------------------------------------------ SUS task 4, INT-AT-04
def test_halt_blocks_every_dose_until_resume():
    st, link, clk, run = make()
    with st.lock:
        st.halt()
    assert link.mode == "HALT"
    assert dose(st, "BASE_FINE", 1)[0]["reason_code"] == "SAFE_HOLD_ACTIVE"
    with st.lock:
        assert st.resume()["ok"]
    run(1)
    assert dose(st, "BASE_FINE", 1)[0]["decision"] == "ACCEPT"


def test_lost_uno_link_halts_and_needs_an_operator_reset():
    st, link, clk, run = make()
    with st.lock:
        link.unplug(4.0)
    run(3)
    assert st.mode == "HALTED" and "link lost" in st.mode_reason
    assert dose(st, "BASE_FINE", 1)[0]["decision"] == "REJECT"
    run(4)                                             # cable back in
    assert st.mode == "HALTED"                         # no self-restart
    with st.lock:
        assert st.resume()["ok"]


# ------------------------------------------------------------------ CHE-AT-04 (S1)
def test_ten_minute_hold_log():
    st, link, clk, run = make()
    with st.lock:
        st.hold_start()
    run(601)
    s = st.state()["hold"]
    assert not s["active"] and s["pass"] and 6.5 <= s["min"] <= s["max"] <= 7.5
    assert st.hold_csv().count("\n") > 500


# ------------------------------------------------------------------ INT-AT-04 step 9
def test_audit_chain_verifies_and_detects_tampering():
    st, link, clk, run = make()
    dose(st, "BASE_FINE", 25)
    dose(st, "BASE_FINE", 2)
    recs = [json.loads(x) for x in st.audit.to_jsonl().splitlines()]
    assert verify_records(recs)[0]
    assert (st.log_dir / "audit.jsonl").read_text().count("\n") == len(recs)     # written as it goes
    recs[2]["volume_ml"] = 1.0
    assert not verify_records(recs)[0]


# ------------------------------------------------------------------ over HTTP
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _req(url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


@pytest.fixture(scope="module")
def servers():
    import os

    import uvicorn

    from hmi.station.server import build_app
    os.environ["CHEMSHIELD_HMAC_SECRET"] = SECRET
    link = SimLink(start_ph=7.0)
    station = Station(link, SECRET, log_dir=Path(tempfile.mkdtemp()), dwell_s=5)
    sp, hp = _free_port(), _free_port()
    s1 = uvicorn.Server(uvicorn.Config(build_app(station), host="127.0.0.1", port=sp, log_level="warning"))
    threading.Thread(target=s1.run, daemon=True).start()
    os.environ["CHEMSHIELD_STATION"] = f"http://127.0.0.1:{sp}"
    import importlib

    import hmi.app
    importlib.reload(hmi.app)
    s2 = uvicorn.Server(uvicorn.Config(hmi.app.app, host="127.0.0.1", port=hp, log_level="warning"))
    threading.Thread(target=s2.run, daemon=True).start()
    while not (s1.started and s2.started):
        time.sleep(0.05)
    time.sleep(6)                                      # a few probe readings for Model A
    yield f"http://127.0.0.1:{sp}", f"http://127.0.0.1:{hp}", station
    s1.should_exit = s2.should_exit = True


def test_station_refuses_unsigned_http_requests(servers):
    station_url, _hmi, _st = servers
    code, out = _req(station_url + "/api/dose", {"channel_id": "BASE_BULK", "volume_ml": 10})
    assert code == 401 and out["decision"] == "REJECT"
    code, out = _req(station_url + "/api/operator", {"kind": "operator_action", "action": "HALT"})
    assert code == 401


def test_laptop_hmi_signs_and_the_gateway_decides(servers):
    station_url, hmi_url, st = servers
    code, out = _req(hmi_url + "/api/dose", {"channel_id": "BASE_FINE", "volume_ml": 25})
    assert code == 200 and out["reason_code"] == "DOSE_LIMIT" and out["group"] == "LIMIT"
    code, out = _req(hmi_url + "/api/dose", {"channel_id": "BASE_FINE", "volume_ml": 3})
    assert out["decision"] == "ACCEPT", out
    code, rep = _req(hmi_url + "/api/test/replay", {})
    assert rep["group"] in ("REPLAY", "STALE") and rep["decision"] == "REJECT"
    code, s = _req(hmi_url + "/api/state")
    assert s["station_ok"] and s["ph"]["source"] == "SIM" and s["gateway"]["chain_ok"]["ok"]
    code, a = _req(hmi_url + "/api/action", {"action": "HALT"})
    assert a["ok"] and st.mode == "HALTED"
    code, a = _req(hmi_url + "/api/action", {"action": "RESUME"})
    assert a["ok"] and st.mode == "NORMAL"
    op = new_operator_action(SECRET, "HALT")
    assert _req(station_url + "/api/operator", op)[0] == 200
    assert _req(station_url + "/api/operator", op)[0] == 401          # the same action replayed


# ------------------------------------------------------------------ ISE-AT-03 facilitator drill
def test_sus_drill_escalate_then_reset():
    from hmi.station.server import _do_action
    st, link, clk, run = make()
    with st.lock:
        assert _do_action(st, "SIM_ESCALATE", {})["ok"] is False        # needs an open event
        _do_action(st, "SIM_UPSET", {"scenario": "medium_acid"})
    for _ in range(100):
        run(0.1)
        if st.event is not None:
            break
    with st.lock:
        assert _do_action(st, "SIM_ESCALATE", {})["mode"] == "ESCALATE"
        st.acknowledge()
        st.halt()                                                        # SUS task T4
        assert st.mode == "HALTED"
        _do_action(st, "SIM_RESET", {"start_ph": 7.0})
    assert st.mode == "NORMAL" and st.event is None and st.gstate.mode == "NORMAL"
    run(5)
    assert dose(st, "BASE_FINE", 2)[0]["decision"] == "ACCEPT"
