"""hmi.c2_check against a station on this computer (no Pi, no nmap, no SSH).

The checks that talk to the station must pass; the port scan and the SSH checks need the Pi
and are covered by the live ICS-AT-01 run.
"""
from __future__ import annotations

import json
import os
import socket
import tempfile
import threading
import time
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")

from hmi import c2_check  # noqa: E402
from hmi.station.core import Station  # noqa: E402
from hmi.station.links import SimLink  # noqa: E402

SECRET = "test-secret-for-c2-check"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def station_port():
    import uvicorn

    from hmi.station.server import build_app
    os.environ["CHEMSHIELD_HMAC_SECRET"] = SECRET
    station = Station(SimLink(start_ph=7.0), SECRET, log_dir=Path(tempfile.mkdtemp()), dwell_s=5)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(station), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    time.sleep(3)
    yield port
    server.should_exit = True


def test_station_checks_pass_and_the_report_is_written(station_port, tmp_path, monkeypatch):
    monkeypatch.setattr(c2_check, "scan_ports", lambda host, log: ({22, station_port}, "stub"))
    c2_check.main(["--pi", "127.0.0.1", "--port", str(station_port), "--out", str(tmp_path)])
    report = json.loads((tmp_path / "ICS-AT-01_c2_check.json").read_text(encoding="utf-8"))
    status = {r["check"]: r["status"] for r in report["results"]}
    assert [status[n] for n in (1, 2, 3, 4, 5, 7, 8)] == ["PASS", "PASS", "PASS", "PASS", "PASS", "SKIP", "PASS"], status
    assert "ICS-AT-01" in (tmp_path / "ICS-AT-01_c2_check.txt").read_text(encoding="utf-8")


def test_an_extra_open_port_fails_the_scan(station_port, tmp_path, monkeypatch):
    monkeypatch.setattr(c2_check, "scan_ports", lambda host, log: ({22, station_port, 502}, "stub"))
    rc = c2_check.main(["--pi", "127.0.0.1", "--port", str(station_port), "--out", str(tmp_path)])
    report = json.loads((tmp_path / "ICS-AT-01_c2_check.json").read_text(encoding="utf-8"))
    assert report["results"][0]["status"] == "FAIL" and rc == 1
