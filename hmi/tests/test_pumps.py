"""Final Prototype: the Uno runs the pumps and reports what they delivered. Run from the repo:

    .venv/bin/python -m pytest hmi/tests/test_pumps.py -q

Most tests drive the station with a hand-moved clock and inject the Uno's answers. The last
one runs the pretend Uno (hmi/mock_uno.py) on a virtual serial port through the real
UnoLink, so the lines themselves are checked end to end.
"""
from __future__ import annotations

import re
import tempfile
import time
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")

from hmi.common import CHANNELS, ROOT  # noqa: E402
from hmi.station.core import MIX_S, Station  # noqa: E402
from hmi.station.links import SimLink, UnoLink  # noqa: E402
from hmi.tests.helpers import SECRET, ManualClock, hmi_dose  # noqa: E402

SKETCH = ROOT / "firmware" / "uno" / "chemshield_uno" / "chemshield_uno.ino"


class PumpSimLink(SimLink):
    """The simulated tank for the pH, with the Uno's pump lines recorded instead of sent."""
    pumps = True

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.sent: list[str] = []

    def _write(self, line: str) -> None:
        self.sent.append(line)
        super()._write(line)

    def uno_says(self, line: str) -> None:
        """A line from the Uno, parsed exactly as UnoLink parses it."""
        UnoLink._parse(self, line, self.clock())


def pump_station():
    from chemshield_gateway.model_a_client import FakeModelAClient
    clock = ManualClock()
    link = PumpSimLink(start_ph=7.0, auto_pump=False, clock=clock)
    st = Station(link, SECRET, log_dir=Path(tempfile.mkdtemp()), clock=clock, use_model_a=False)
    st.model_a_proxy.inner = FakeModelAClient(st.config)
    link.start()

    def run(seconds: float) -> None:
        end = clock.t + seconds
        while clock.t < end:
            clock.t += 0.1
            st.tick()

    run(5)
    return st, link, clock, run


def audit_kinds(st: Station) -> list[str]:
    return [r.reason_code for r in st.audit.records]


def last_record(st: Station, kind: str):
    return next(r for r in reversed(st.audit.records) if r.reason_code == kind)


# ------------------------------------------------------------------ protocol and wiring
def test_uno_link_reads_pump_lines_and_the_old_lines():
    link = UnoLink(port="none")
    link.dose_on = True
    link._parse("DONE,17,ACID_FINE,4.995", 1.0)
    link._parse("ABORT,18,BASE_BULK,2.5,ESTOP", 2.0)
    link._parse("DONE,19,2500", 3.0)                     # the PPR light-only answer
    link._parse("REJECT,20,TOO_MUCH", 4.0)
    _, events = link.poll()
    assert [e["kind"] for e in events] == ["PUMP_DONE", "PUMP_ABORT", "DONE", "UNO_REJECT"]
    assert (events[0]["seq"], events[0]["channel_id"], events[0]["ml"]) == (17, "ACID_FINE", 4.995)
    assert (events[1]["ml"], events[1]["reason"]) == (2.5, "ESTOP")
    assert (events[3]["seq"], events[3]["reason"]) == (20, "TOO_MUCH")
    assert not link.dose_on


def test_link_writes_pump_and_mix_lines():
    link = PumpSimLink(start_ph=7.0, auto_pump=False, clock=ManualClock())
    link.pump(7, "BASE_FINE", 12.5)
    link.mix(300)
    assert link.sent == ["PUMP,7,BASE_FINE,12.500", "MIX,255"] and link.dose_on


def test_pump_numbers_match_the_sketch_wiring():
    """CHANNELS' pump numbers must be the sketch's pump order (X, Y, Z, A on the shield)."""
    src = SKETCH.read_text()
    order = re.findall(r'\{"(ACID_BULK|ACID_FINE|BASE_BULK|BASE_FINE)",\s*(\d+),\s*(\d+)', src)
    assert [ch for ch, _, _ in order] == ["ACID_BULK", "ACID_FINE", "BASE_BULK", "BASE_FINE"]
    for i, (ch, _step, _dir) in enumerate(order):
        assert CHANNELS[ch]["pump"] == i + 1
    assert [(int(s), int(d)) for _, s, d in order] == [(2, 5), (3, 6), (4, 7), (12, 13)]
    for reason in ("STOP", "ESTOP", "HB_LOST", "HALT", "RECOVERY", "TIMEOUT", "TOO_MUCH", "NO_HB", "BUSY"):
        assert f'F("{reason}")' in src
    assert "MAX_DOSE_ML = 20.0" in src


# ------------------------------------------------------------------ the station with pumps
def test_a_pump_dose_counts_only_when_the_uno_reports_done():
    st, link, clock, run = pump_station()
    r = hmi_dose(st, "ACID_FINE", 10.0)
    assert r["decision"] == "ACCEPT"
    p = st.pending
    assert p["pump"] and link.sent[-1] == f"PUMP,{p['seq']},ACID_FINE,10.000"
    assert "Pump 2 is adding 10 mL" in p["instruction"]
    with st.lock:
        refused = st.dose_added(p["command_id"])           # DOSE ADDED from the HMI
    assert not refused["ok"] and st.pending is not None
    run(3)
    assert st.mixing_until is None                         # nothing added yet
    link.uno_says(f"DONE,{p['seq']},ACID_FINE,9.995")
    run(0.2)
    assert st.pending is None and not link.dose_on
    rec = last_record(st, "DOSE_ADDED")
    assert rec.volume_ml == pytest.approx(9.995) and rec.source == "Uno"
    assert "9.995 mL" in rec.message and "10 mL approved" in rec.message
    assert st.mixing_until == pytest.approx(clock.t + MIX_S, abs=0.2)
    assert hmi_dose(st, "ACID_FINE", 1.0)["reason_code"] == "MIXING_LOCKOUT"
    run(MIX_S + 0.5)
    assert hmi_dose(st, "ACID_FINE", 1.0)["decision"] == "ACCEPT"


def test_an_aborted_pump_dose_is_not_added_but_what_went_in_is_logged():
    st, link, clock, run = pump_station()
    hmi_dose(st, "BASE_FINE", 8.0)
    p = st.pending
    link.uno_says(f"ABORT,{p['seq']},BASE_FINE,3.250,ESTOP")
    run(0.2)
    assert st.pending is None
    kinds = audit_kinds(st)
    assert "DOSE_CANCELLED" in kinds and "DOSE_ADDED" not in kinds
    rec = last_record(st, "PUMP_STOPPED")
    assert rec.volume_ml == pytest.approx(3.25) and "ESTOP" in rec.message
    assert rec.command_id == p["command_id"]
    assert st.mixing_until is not None                     # reagent went in: mix before the next dose
    assert hmi_dose(st, "BASE_FINE", 1.0)["reason_code"] == "MIXING_LOCKOUT"


def test_a_pump_dose_the_uno_refuses_is_cancelled_at_once():
    st, link, clock, run = pump_station()
    hmi_dose(st, "BASE_BULK", 5.0)
    seq = st.pending["seq"]
    link.uno_says(f"REJECT,{seq},NO_HB")
    run(0.2)
    assert st.pending is None and "UNO_REJECT" in audit_kinds(st)
    assert st.mixing_until is None


def test_halt_stops_the_pump_and_the_late_abort_is_logged():
    st, link, clock, run = pump_station()
    hmi_dose(st, "ACID_BULK", 6.0)
    p = st.pending
    with st.lock:
        st.halt()
    assert "STOP" in link.sent and "MODE,HALT" in link.sent and st.pending is None
    link.uno_says(f"ABORT,{p['seq']},ACID_BULK,1.200,HALT")
    run(0.2)
    rec = last_record(st, "PUMP_STOPPED")
    assert rec.volume_ml == pytest.approx(1.2) and rec.command_id == p["command_id"]


def test_a_pump_that_never_reports_is_stopped():
    from hmi.station.core import PUMP_TIMEOUT_S
    st, link, clock, run = pump_station()
    hmi_dose(st, "ACID_FINE", 2.0)
    run(PUMP_TIMEOUT_S + 1)
    assert st.pending is None and link.sent[-1] == "STOP"
    assert "did not report the pump finished" in last_record(st, "DOSE_CANCELLED").message


# ------------------------------------------------------------------ end to end with the pretend Uno
def test_station_and_pretend_uno_pump_a_dose_end_to_end():
    pytest.importorskip("serial")
    from chemshield_gateway.model_a_client import FakeModelAClient
    from hmi.mock_uno import MockUno
    uno = MockUno(verbose=False, ml_per_s=10.0).start()
    link = UnoLink(port=uno.port, pumps=True)
    st = Station(link, SECRET, log_dir=Path(tempfile.mkdtemp()), use_model_a=False)
    st.model_a_proxy.inner = FakeModelAClient(st.config)
    st.start()
    try:
        def wait_for(cond, seconds: float) -> bool:
            end = time.time() + seconds
            while time.time() < end:
                if cond():
                    return True
                time.sleep(0.05)
            return False

        assert wait_for(lambda: st.link_was_alive and uno.last_hb, 5.0)
        r = hmi_dose(st, "BASE_FINE", 3.0)
        assert r["decision"] == "ACCEPT"
        assert wait_for(lambda: st.pending is None, 5.0)
        rec = last_record(st, "DOSE_ADDED")
        assert rec.volume_ml == pytest.approx(3.0) and rec.channel_id == "BASE_FINE"
        assert any(ln.startswith("PUMP,") and ",BASE_FINE,3.000" in ln for ln in uno.lines_in)

        uno.estop = True                                   # the E-stop halts the station
        uno.send("STATUS,1,0")
        assert wait_for(lambda: st.mode == "HALTED", 3.0)
    finally:
        st.stop()
        uno.stop()


def test_pretend_uno_follows_the_firmware_rules():
    """hmi/mock_uno.py is the reference for the sketch: check its pump rules directly."""
    import os
    from hmi.mock_uno import MockUno
    uno = MockUno(verbose=False, ml_per_s=2.0)
    out = os.fdopen(uno.slave, "rb", buffering=0)

    os.set_blocking(uno.slave, False)

    def said() -> list[str]:
        got = []
        while True:                                        # a terminal hands over one line per read
            try:
                chunk = out.read(4096)
            except BlockingIOError:
                chunk = None
            if not chunk:
                return got
            got += chunk.decode().split()

    uno.handle("PUMP,1,ACID_FINE,5")
    assert said() == ["REJECT,1,NO_HB"]                    # no heartbeat yet
    uno.handle("HB")
    uno.handle("PUMP,2,ACID_FINE,25")
    uno.handle("PUMP,3,NOT_A_PUMP,5")
    assert said() == ["REJECT,2,TOO_MUCH", "REJECT,3,BAD"]
    t0 = time.time()
    uno.handle("PUMP,4,ACID_FINE,5")
    uno.handle("PUMP,5,BASE_FINE,1")
    assert said() == ["OK,4", "REJECT,5,BUSY"]              # one pump at a time
    uno.pump["t0"] = t0 - 1.0                              # 1 s in at 2 mL/s
    uno.handle("MODE,RECOVERY")
    assert said() == ["ABORT,4,ACID_FINE,2.000,RECOVERY", "OK,MODE,RECOVERY"]
    uno.handle("PUMP,6,BASE_FINE,1")                       # the planner's doses still run in RECOVERY
    uno.pump["t0"] -= 1.0
    uno.step(time.time())
    assert said() == ["OK,6", "DONE,6,BASE_FINE,1.000"]
    uno.handle("PUMP,7,BASE_BULK,4")
    uno.handle("STOP")
    lines = said()
    assert lines[0] == "OK,7" and lines[1].startswith("ABORT,7,BASE_BULK,") and lines[1].endswith(",STOP")
    assert lines[2] == "OK,STOP"
    uno.handle("MODE,HALT")
    uno.handle("PUMP,8,BASE_BULK,4")
    assert said()[-1] == "REJECT,8,HALTED"
    out.close()
