"""Save one FPR rig run's evidence from the live station into the repo.

    ../chemshield/.venv/bin/python evidence/tools/save_fpr_run.py <folder name> [--station http://<pi>:8000]

Writes evidence/fpr_runs/<folder>/: audit.jsonl (hash-chained), audit.csv, int_s1_timing.csv,
s1_hold.csv, ph_trend.csv, state.json (the station's state, including last_event with the
reagent used and the recovery time) and summary.txt.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--station", default="http://10.42.0.1:8000")
    a = ap.parse_args()
    out = ROOT / "evidence" / "fpr_runs" / a.name
    out.mkdir(parents=True, exist_ok=True)
    base = a.station.rstrip("/")
    for name in ("audit.jsonl", "audit.csv", "int_s1_timing.csv", "s1_hold.csv", "ph_trend.csv"):
        try:
            (out / name).write_bytes(fetch(f"{base}/api/export/{name}"))
        except Exception as e:                                 # one missing export is not fatal
            print(f"  {name}: not saved ({e})")
    state = json.loads(fetch(f"{base}/api/state"))
    (out / "state.json").write_text(json.dumps(state, indent=2))
    le = state.get("last_event") or {}
    lines = [f"mode now: {state.get('mode')}  pH now: {state['ph'].get('mean3')}",
             f"last event: {json.dumps({k: le.get(k) for k in le if not isinstance(le.get(k), (list, dict))})}"]
    t = state.get("timing") or {}
    if t:
        lines.append(f"timing: {json.dumps(t)[:600]}")
    (out / "summary.txt").write_text("\n".join(lines) + "\n")
    print(f"saved to {out}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
