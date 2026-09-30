"""Simulator controls from a second terminal, so a SUS participant never sees them.

    .venv/bin/python -m hmi.facilitator upset medium_acid     T3: an acid upset (recovery starts)
    .venv/bin/python -m hmi.facilitator escalate              T4: OPERATOR DECISION REQUIRED now
    .venv/bin/python -m hmi.facilitator reset                 between participants: fresh tank, pH 7
    .venv/bin/python -m hmi.facilitator upset 7               7 mL of 0.5 M acid (INT-AT-01 size)
    .venv/bin/python -m hmi.facilitator upset 7 --base        ... of base
    .venv/bin/python -m hmi.facilitator set-ph 6.3
    .venv/bin/python -m hmi.facilitator unplug 8              the Uno's USB "pulled" for 8 s
    .venv/bin/python -m hmi.facilitator status

Works only when the station runs the simulated tank (python -m hmi.demo, or
python -m hmi.station --ph-source sim). Every control is written in the audit log as
"SIMULATOR: ...". Add --station http://<ip>:8000 if the station is not on this laptop.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from hmi.common import STATION_PORT, load_secret, new_operator_action


def _send(station: str, action: str, args: dict) -> dict:
    body = new_operator_action(load_secret()[0], action, args, operator="facilitator")
    req = urllib.request.Request(station.rstrip("/") + "/api/operator", data=json.dumps(body).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.facilitator", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("upset", "escalate", "reset", "set-ph", "unplug", "status"))
    ap.add_argument("value", nargs="?", default=None)
    ap.add_argument("--base", action="store_true", help="upset with base instead of acid")
    ap.add_argument("--station", default=f"http://127.0.0.1:{STATION_PORT}")
    a = ap.parse_args(argv)

    if a.command == "status":
        with urllib.request.urlopen(a.station.rstrip("/") + "/api/state", timeout=5) as r:
            s = json.loads(r.read())
        ev = s.get("event")
        print(f"{s['mode']} · pH {s['ph']['mean3']} ({s['ph']['source']})"
              + (f" · {ev['id']} {ev['elapsed_s']} s, {ev['reagent_mmol']} mmol" if ev else ""))
        return 0
    if a.command == "upset":
        v = a.value or "medium_acid"
        try:
            args = {"ml": float(v), "acid": not a.base}
        except ValueError:
            args = {"scenario": v}
        out = _send(a.station, "SIM_UPSET", args)
    elif a.command == "escalate":
        out = _send(a.station, "SIM_ESCALATE", {})
    elif a.command == "reset":
        out = _send(a.station, "SIM_RESET", {"start_ph": float(a.value or 7.0)})
    elif a.command == "set-ph":
        out = _send(a.station, "SIM_SET_PH", {"ph": float(a.value or 7.0)})
    else:
        out = _send(a.station, "SIM_UNPLUG", {"seconds": float(a.value or 8.0)})
    print(json.dumps(out))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
