"""INT-S1 over many events: time from "unsafe event confirmed" to "RECOVERY on the HMI".

    .venv/bin/python -m hmi.int_s1_batch --events 100 --out evidence/09_INT-S1_recovery_mode_within_2s/data/laptop_dry_run

Runs a real station (simulated tank) on this computer and a headless HMI client that
polls the station the way the screen does (every 250 ms) and reports the moment it first
sees RECOVERY. For each event the tank is set to pH 4.5 (an acid upset); the station
confirms it after 3 readings, switches to recovery and tells the Uno to lock; then the
tank is set back to pH 7 and the event closes. All times are on the station's clock.

Writes INT-AT-01_batch.csv (one row per event) and INT-AT-01_summary.json.
The live check on the real rig is the timing panel on the HMI (INT-AT-01 sheet).
"""
from __future__ import annotations

import argparse
import csv
import json
import platform
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

from hmi.common import ROOT, load_secret, new_operator_action


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as r:
        return json.loads(r.read())


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3) as r:
        return json.loads(r.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.int_s1_batch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", type=int, default=100)
    ap.add_argument("--out", default=str(ROOT / "evidence" / "09_INT-S1_recovery_mode_within_2s" / "data" / "laptop_dry_run"))
    ap.add_argument("--poll", type=float, default=0.25, help="HMI poll period, s (the screen uses 0.25)")
    a = ap.parse_args(argv)

    import uvicorn
    from hmi.station.__main__ import make_station
    from hmi.station.server import build_app

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    station = make_station("sim", dwell_s=1.0, log_root=out / "station_logs")
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(build_app(station), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    base = f"http://127.0.0.1:{port}"
    secret = load_secret()[0]
    act = lambda name, args=None: _post(base + "/api/operator", new_operator_action(secret, name, args or {}))  # noqa: E731

    # the headless HMI: poll like the screen, report the first sight of each event
    seen: set[str] = set()
    stop = threading.Event()

    def hmi() -> None:
        while not stop.is_set():
            try:
                s = _get(base + "/api/state")
                ev = s.get("event")
                if ev and ev["id"] not in seen and s["mode"] in ("RECOVERY", "ESCALATE", "HALTED"):
                    seen.add(ev["id"])
                    act("HMI_SHOWN", {"event_id": ev["id"]})
            except Exception:                                  # noqa: BLE001
                pass
            time.sleep(a.poll)

    threading.Thread(target=hmi, daemon=True).start()
    act("SIM_AUTOPUMP", {"on": True})
    act("AUTO_RECOVERY", {"on": False})       # this test is about the switch, not the dosing
    time.sleep(6)
    for i in range(a.events):
        act("SIM_SET_PH", {"ph": 4.5})
        t0 = time.time()
        while time.time() - t0 < 15:
            s = _get(base + "/api/state")
            ev = s.get("event")
            if ev and ev["timing"]["confirm_to_hmi_shown_ms"] is not None:
                break
            time.sleep(0.1)
        act("SIM_SET_PH", {"ph": 7.0})
        t0 = time.time()
        while time.time() - t0 < 20 and _get(base + "/api/state")["mode"] != "NORMAL":
            time.sleep(0.2)
        print(f"event {i + 1}/{a.events}", end="\r", flush=True)
    stop.set()

    with station.lock:
        rows = [station._timing_row(e) for e in station.events]
    cols = ["event_id", "source", "confirmed_utc", "confirm_to_recovery_ms", "confirm_to_uno_locked_ms",
            "confirm_to_hmi_shown_ms", "worst_ms", "pass_2s"]
    with open(out / "INT-AT-01_batch.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
    shown = [r["confirm_to_hmi_shown_ms"] for r in rows if r["confirm_to_hmi_shown_ms"] is not None]
    rec = [r["confirm_to_recovery_ms"] for r in rows if r["confirm_to_recovery_ms"] is not None]
    summary = {
        "test": "INT-AT-01 batch (INT-S1: safe-recovery mode within 2 s of a confirmed unsafe event)",
        "events": len(rows), "measured": len(shown),
        "confirm_to_recovery_ms_max": max(rec) if rec else None,
        "confirm_to_hmi_shown_ms_mean": round(sum(shown) / len(shown), 1) if shown else None,
        "confirm_to_hmi_shown_ms_max": max(shown) if shown else None,
        "all_under_2000_ms": bool(shown) and len(shown) == len(rows) and max(shown) < 2000,
        "hmi_poll_s": a.poll, "ph_source": "SIM (simulated tank; the Uno lock ack is simulated)",
        "machine": f"{platform.node()} {platform.platform()} python {platform.python_version()}",
        "note": "Headless HMI client over HTTP on one computer. On the rig add the Wi-Fi hop and the browser paint; the HMI's timing panel measures those live.",
    }
    (out / "INT-AT-01_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("\n" + json.dumps(summary, indent=2))
    server.should_exit = True
    return 0


if __name__ == "__main__":
    sys.exit(main())
