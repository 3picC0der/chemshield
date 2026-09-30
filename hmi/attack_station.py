"""ICS-AT-02 over the network: replayed and stale commands sent to the real station.

Khalid's gateway/attack_script.py checks the gateway's code in one process. This sends
the same kinds of commands over the Wi-Fi to the station on the Pi, so the HMI's
rejected-command counters, the audit log and this script's summary can be compared
(ICS-AT-02 step 6). It holds the operator key, like a legitimate client would.

    .venv/bin/python -m hmi.attack_station --station http://<pi-ip>:8000 --mode valid --n 1000 --save sent.jsonl
    .venv/bin/python -m hmi.attack_station --station ... --mode replay --file sent.jsonl
    .venv/bin/python -m hmi.attack_station --station ... --mode replay-now --n 1000
    .venv/bin/python -m hmi.attack_station --station ... --mode stale --age 5 --n 1000
    .venv/bin/python -m hmi.attack_station --station ... --mode stale --age 1 --n 100

Modes:
  valid       fresh signed commands (1 mL of the 0.005 M bottle, harmless). One is accepted and
              lights the dose light; the rest wait behind it (DOSE_PENDING) or the 15 s lockout.
              None may come back REPLAY or STALE.
  replay      re-sends a saved file exactly. Sent more than 2 s after the originals, the
              gateway calls them STALE; within 2 s, REPLAY. Both are rejections.
  replay-now  sends a fresh command and an exact copy straight after it: the copy must be
              rejected as a REPLAY (REUSED_NONCE).
  stale       signed commands dated --age seconds in the past (5 -> STALE; 1 -> not stale).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from hmi.common import gateway_config, load_secret, new_dose_command, next_sequence, reason_group


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.attack_station", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="http://127.0.0.1:8000")
    ap.add_argument("--mode", choices=("valid", "replay", "replay-now", "stale"), required=True)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--age", type=float, default=5.0)
    ap.add_argument("--file", help="replay: the file saved by --mode valid --save")
    ap.add_argument("--save", help="valid: save every command sent, for a later replay")
    a = ap.parse_args(argv)

    cfg = gateway_config(load_secret()[0])
    url = a.station.rstrip("/") + "/api/dose"
    before = get(a.station.rstrip("/") + "/api/state")["gateway"]["counters"]
    seq = int(get(a.station.rstrip("/") + "/api/state")["gateway"]["last_sequence_number"])
    results: Counter = Counter()
    reached_uno = 0
    sent = []
    tag = f"attack script ({a.mode})"

    def fresh(age: float = 0.0) -> dict:
        nonlocal seq
        seq = next_sequence(seq)
        return new_dose_command(cfg, channel_id="BASE_FINE", volume_ml=1.0, event_id=f"OPS-ATK{seq % 100000}",
                                sequence_number=seq, source="ATTACK", age_s=age)

    t0 = time.time()
    if a.mode == "replay":
        if not a.file:
            ap.error("--mode replay needs --file")
        cmds = [json.loads(x) for x in open(a.file, encoding="utf-8") if x.strip()]
        for c in cmds:
            out = post(url, dict(c, _sender=tag))
            results[out.get("reason_code", "?")] += 1
            reached_uno += bool(out.get("forwarded_to_actuator"))
    else:
        for _ in range(a.n):
            if a.mode == "valid":
                c = fresh()
                sent.append(c)
                out = post(url, dict(c, _sender=tag))
            elif a.mode == "replay-now":
                c = fresh()
                post(url, dict(c, _sender="attack script (original)"))
                out = post(url, dict(c, _sender=tag))              # the exact copy
            else:
                out = post(url, dict(fresh(a.age), _sender=tag))
            results[out.get("reason_code", "?")] += 1
            reached_uno += bool(out.get("forwarded_to_actuator"))
    if a.save and sent:
        with open(a.save, "w", encoding="utf-8") as f:
            for c in sent:
                f.write(json.dumps(c) + "\n")

    n = sum(results.values())
    groups = Counter()
    for code, k in results.items():
        groups[reason_group(code)] += k
    after = get(a.station.rstrip("/") + "/api/state")["gateway"]["counters"]
    print(f"\n=== {a.mode}: {n} commands in {time.time() - t0:.1f} s ===")
    for code, k in results.most_common():
        print(f"  {code:22s} {k:5d}   ({reason_group(code)})")
    print(f"  rejected as REPLAY: {groups['REPLAY']}   as STALE: {groups['STALE']}   accepted: {groups['ACCEPT']}")
    print(f"  forwarded to the Uno: {reached_uno}")
    print("  HMI counters, change during this run: " + ", ".join(
        f"{k} +{after.get(k, 0) - before.get(k, 0)}" for k in ("REPLAY", "STALE", "ACCEPT", "TOTAL")))
    if a.mode in ("replay", "replay-now", "stale") and not (a.mode == "stale" and a.age < 2):
        bad = groups["REPLAY"] + groups["STALE"]
        print(f"  replayed/stale rejected: {bad}/{n} = {100.0 * bad / max(n, 1):.2f}%  (S3 needs >= 99%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
