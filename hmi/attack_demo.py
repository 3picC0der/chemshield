"""FPR booth demo of the ICS attacks: run it in a Terminal next to the HMI.

Each attack sends a burst of commands at the station's gateway over the network, the way an
intruder on the network would, while the HMI's attack monitor counts them as they are blocked.
Nothing here can move a pump: every attack command is rejected before the Uno.

    .venv/bin/python -m hmi.attack_demo --station http://<pi>:8000              all five, 30 each
    .venv/bin/python -m hmi.attack_demo --station ... --only replay --n 100     one attack

  forged    signed with a key that is not the operator's        -> Not authorised (AUTH)
  unsigned  no signature at all                                  -> Not authorised (AUTH)
  tampered  a real signed 1 mL command changed to 20 mL in transit -> Not authorised (AUTH)
  stale     a real command captured 5 s ago, sent now            -> Stale
  replay    a real command, accepted once, then re-sent N times  -> Replayed

The replay attack needs one genuine command first: the script sends one 1 mL dose of the
0.005 M base (the gentlest bottle) as the "captured" original; the gateway judges it like any
operator dose. Every copy after it must be rejected.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from hmi.common import gateway_config, load_secret, new_dose_command, next_sequence, reason_group

BOLD, RED, GREEN, DIM, END = "\033[1m", "\033[31m", "\033[32m", "\033[2m", "\033[0m"
ORDER = ("forged", "unsigned", "tampered", "stale", "replay")
TITLES = {
    "forged": "FORGED commands (signed with the wrong key)",
    "unsigned": "UNSIGNED commands",
    "tampered": "TAMPERED command (1 mL changed to 20 mL in transit)",
    "stale": "STALE commands (captured 5 s ago, sent now)",
    "replay": "REPLAYED command (one real command sent again and again)",
}


def post(url: str, body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.attack_demo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="http://10.42.0.1:8000")
    ap.add_argument("--only", choices=ORDER, help="run just this attack")
    ap.add_argument("--n", type=int, default=30, help="commands per attack (default 30)")
    ap.add_argument("--gap", type=float, default=0.05, help="seconds between commands")
    ap.add_argument("--pause", type=float, default=4.0, help="seconds between attacks")
    a = ap.parse_args(argv)

    base = a.station.rstrip("/")
    url = base + "/api/dose"
    try:
        state = get(base + "/api/state")
    except OSError as e:
        print(f"Cannot reach the station at {base}: {e}")
        return 2
    good = gateway_config(load_secret()[0])
    wrong = gateway_config("an-attacker-guessed-key")
    seq = int(state["gateway"]["last_sequence_number"])

    def cmd(config, ml=1.0, age=0.0) -> dict:
        nonlocal seq
        seq = next_sequence(seq)
        return new_dose_command(config, channel_id="BASE_FINE", volume_ml=ml, event_id=f"OPS-ATK{seq % 100000}",
                                sequence_number=seq, source="ATTACK", age_s=age)

    total = Counter()
    rows = []
    for kind in ([a.only] if a.only else ORDER):
        print(f"\n{BOLD}>>> Attack: {TITLES[kind]}{END}")
        tag = f"ATTACKER ({kind})"
        results, reached = Counter(), 0
        original = None
        if kind == "replay":
            original = cmd(good)
            code, out = post(url, dict(original, _sender="captured original (genuine 1 mL dose)"))
            print(f"{DIM}    the genuine original, sent once: {out.get('decision', '?')} "
                  f"({out.get('reason_code', code)}){END}")
            time.sleep(0.5)
        for i in range(a.n):
            if kind == "forged":
                c = cmd(wrong, ml=10.0)
            elif kind == "unsigned":
                c = cmd(good, ml=10.0)
                c.pop("hmac_sha256", None)
            elif kind == "tampered":
                c = cmd(good, ml=1.0)
                c = copy.deepcopy(c)
                c["volume_ml"] = 20.0                        # changed after signing
            elif kind == "stale":
                c = cmd(good, age=5.0)
            else:
                c = original
            code, out = post(url, dict(c, _sender=tag))
            rc = out.get("reason_code") or ("INVALID_HMAC" if code == 401 else "?")
            results[rc] += 1
            reached += bool(out.get("forwarded_to_actuator"))
            sys.stdout.write(f"\r    sent {i + 1:4d}/{a.n}   last answer: {rc:<22s}")
            sys.stdout.flush()
            time.sleep(a.gap)
        blocked = sum(k for rc, k in results.items() if reason_group(rc) != "ACCEPT")
        groups = ", ".join(f"{rc} x{k}" for rc, k in results.most_common())
        verdict = f"{GREEN}ALL BLOCKED{END}" if blocked == a.n and reached == 0 else f"{RED}NOT ALL BLOCKED{END}"
        print(f"\r    {a.n} sent -> {blocked} blocked, {reached} reached the pumps   {verdict}      ")
        print(f"{DIM}    gateway answers: {groups}{END}")
        rows.append((kind, a.n, blocked, reached))
        total.update({"sent": a.n, "blocked": blocked, "reached": reached})
        if kind != (a.only or ORDER[-1]):
            time.sleep(a.pause)

    print(f"\n{BOLD}Summary{END}")
    print(f"  {'attack':10s} {'sent':>5s} {'blocked':>8s} {'reached pumps':>14s}")
    for kind, n, b, r in rows:
        print(f"  {kind:10s} {n:5d} {b:8d} {r:14d}")
    pct = 100.0 * total["blocked"] / max(total["sent"], 1)
    colour = GREEN if total["reached"] == 0 and total["blocked"] == total["sent"] else RED
    print(f"  {colour}{BOLD}{total['blocked']}/{total['sent']} attack commands blocked ({pct:.1f} %), "
          f"{total['reached']} reached the pumps{END}")
    return 0 if total["reached"] == 0 and total["blocked"] == total["sent"] else 1


if __name__ == "__main__":
    sys.exit(main())
