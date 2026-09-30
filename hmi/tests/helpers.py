"""Shared by the HMI tests and the gateway tests that go through the HMI path."""
from __future__ import annotations

import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")

from hmi.common import gateway_config, new_dose_command, next_sequence  # noqa: E402
from hmi.station.core import Station  # noqa: E402
from hmi.station.links import SimLink  # noqa: E402

SECRET = "test-secret-for-hmi-tests"


class ManualClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def station_with_stand_in_model_a(dwell_s: float = 60.0):
    """A station on the simulated tank with Khalid's stand-in Model A, so a test sees only
    the gateway's own rules. Returns (station, clock, run(seconds))."""
    from chemshield_gateway.model_a_client import FakeModelAClient
    clock = ManualClock()
    link = SimLink(start_ph=7.0, auto_pump=False, clock=clock)
    st = Station(link, SECRET, log_dir=Path(tempfile.mkdtemp()), clock=clock, dwell_s=dwell_s,
                 use_model_a=False)
    st.model_a_proxy.inner = FakeModelAClient(st.config)
    link.start()

    def run(seconds: float) -> None:
        end = clock.t + seconds
        while clock.t < end:
            clock.t += 0.1
            st.tick()

    run(5)
    return st, clock, run


def hmi_dose(st: Station, channel: str, ml: float, event_id: str | None = None) -> dict:
    """What the laptop HMI does for one REQUEST DOSE: sign it, send it to the station."""
    eid = event_id or f"OPS-{int(st.clock() * 10)}"
    cmd = new_dose_command(gateway_config(SECRET), channel_id=channel, volume_ml=ml, event_id=eid,
                           sequence_number=next_sequence(st.gateway.last_sequence_number))
    with st.lock:
        return st._submit(cmd, source="HMI", sender="test")
