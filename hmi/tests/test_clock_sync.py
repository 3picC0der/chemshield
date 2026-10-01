"""hmi.clock_sync: the laptop sets the Pi's clock over SSH and checks the station's clock.

No Pi and no real clock change here: `ssh` runs the remote script locally, and `sudo` and
`date` are stubs (the `sudo` stub only records what it was asked to do).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from hmi import clock_sync
from hmi.common import iso_ms


def _stub(dir_: Path, name: str, body: str) -> None:
    p = dir_ / name
    p.write_text("#!/bin/sh\n" + body)
    p.chmod(0o755)


def test_set_over_ssh_sends_the_laptop_time_and_measures_the_offset(tmp_path, monkeypatch):
    calls = tmp_path / "sudo.log"
    _stub(tmp_path, "ssh", 'for last; do :; done\nexec bash -c "$last"\n')     # run the remote script here
    _stub(tmp_path, "sudo", f'echo "$*" >> "{calls}"\n')                       # record, never run
    _stub(tmp_path, "date", f'"{sys.executable}" -c "import time; print(f\'{{time.time():.6f}}\')"\n')
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")

    offset = clock_sync.set_over_ssh("belal@pi", [])

    assert abs(offset) < 0.5
    sent = calls.read_text().split()
    assert sent[:4] == ["-n", "date", "-u", "-s"], sent
    assert abs(float(sent[4].lstrip("@")) - time.time()) < 5.0


def test_set_over_ssh_explains_a_sudo_password_prompt(tmp_path, monkeypatch):
    _stub(tmp_path, "ssh", 'for last; do :; done\nexec bash -c "$last"\n')
    _stub(tmp_path, "sudo", 'echo "sudo: a password is required" >&2\nexit 1\n')
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    try:
        clock_sync.set_over_ssh("belal@pi", [])
    except RuntimeError as exc:
        assert "without one" in str(exc)
    else:
        raise AssertionError("a failed sudo must be reported")


def test_check_station_reads_the_offset_from_api_state():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                              # noqa: N802
            body = json.dumps({"server_utc": iso_ms(time.time() + 3.0)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):                                  # quiet
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        offset = clock_sync.check_station(f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
    assert 2.5 < offset < 3.5
    assert clock_sync._verdict(offset, "The station's clock") == 1
    assert clock_sync._verdict(0.05, "The station's clock") == 0
