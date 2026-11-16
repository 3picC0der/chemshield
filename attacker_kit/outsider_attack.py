#!/usr/bin/env python3
"""ChemShield FPR: attacks from an outsider's laptop (no ChemShield software, no keys).

The attacker has joined the plant Wi-Fi and has captured a few real dose commands off the
network (captured.jsonl). They do NOT have the operator's signing key. They try to make
the pumps move by:

  scan       looking for any open door on the station (TCP connect scan)
  replay     re-sending the captured commands exactly as they were
  tampered   changing a captured 1 mL dose to 20 mL before re-sending it
  forged     building a fresh command (new time, new nonce) and signing it themselves
  unsigned   sending a fresh command with the signature removed
  garbage    sending data that is not a command at all

Every one must be rejected by the ChemShield gateway, and nothing may reach a pump.

    python3 outsider_attack.py --station http://10.42.0.1:8000 --captured captured.jsonl

Needs only Python 3 (no extra packages). Works on macOS, Windows and Linux.
"""
import argparse
import copy
import json
import secrets
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse

SIG = "hmac_sha256"
PORTS = [21, 22, 23, 25, 53, 80, 102, 443, 502, 1883, 2222, 3000, 4840, 5000, 5900,
         8000, 8080, 8443, 8883, 9000, 20000, 44818, 47808]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def post(url: str, body, tag: str) -> dict:
    if isinstance(body, dict):
        body = dict(body, _sender=tag)
        data = json.dumps(body).encode()
    else:
        data = body
    req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}") | {"http": e.code}
        except ValueError:
            return {"reason_code": f"HTTP_{e.code}", "http": e.code}
    except (urllib.error.URLError, OSError) as e:
        return {"reason_code": "NO_CONNECTION", "error": str(e)}


def scan(host: str) -> list[int]:
    open_ports = []
    for p in PORTS:
        s = socket.socket()
        s.settimeout(0.6)
        try:
            if s.connect_ex((host, p)) == 0:
                open_ports.append(p)
        finally:
            s.close()
    return open_ports


def fresh(cmd: dict) -> dict:
    """A brand-new looking command: new id, time and nonce (the old signature no longer fits)."""
    c = copy.deepcopy(cmd)
    c["command_id"] = "ATK-" + uuid.uuid4().hex[:10]
    c["timestamp_utc"] = now_iso()
    c["nonce"] = uuid.uuid4().hex
    c["sequence_number"] = int(c.get("sequence_number", 0)) + 1000
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="http://10.42.0.1:8000")
    ap.add_argument("--captured", default="captured.jsonl", help="commands captured off the network")
    ap.add_argument("--n", type=int, default=20, help="commands per attack (default 20)")
    ap.add_argument("--only", choices=["scan", "replay", "tampered", "forged", "unsigned", "garbage"])
    a = ap.parse_args()
    url = a.station.rstrip("/") + "/api/dose"
    host = urlparse(a.station).hostname

    try:
        captured = [json.loads(x) for x in open(a.captured, encoding="utf-8") if x.strip()]
    except OSError:
        print(f"Can't read {a.captured}. Put captured.jsonl next to this script (or pass --captured).")
        return 2
    if not captured:
        print("captured.jsonl is empty")
        return 2

    print(f"\nOUTSIDER ATTACK on {a.station}  (no keys, {len(captured)} captured commands)\n")
    summary = []

    def burst(name: str, make, tag: str):
        if a.only and a.only != name:
            return
        answers = Counter()
        reached = 0
        for i in range(a.n):
            out = post(url, make(i), tag)
            if out.get("reason_code") == "NO_CONNECTION":
                print(f"  cannot reach the station: {out.get('error')}")
                sys.exit(3)
            answers[out.get("reason_code", "?")] += 1
            reached += bool(out.get("forwarded_to_actuator"))
            time.sleep(0.05)
        blocked = a.n - reached
        print(f"  {name:9s} {a.n:3d} sent -> {blocked:3d} blocked, {reached} reached a pump   "
              + ", ".join(f"{k} x{v}" for k, v in answers.most_common()))
        summary.append((name, a.n, blocked, reached))

    if not a.only or a.only == "scan":
        print(f"  scan      checking {len(PORTS)} common ports on {host} ...")
        op = scan(host)
        print(f"  scan      open: {op or 'none'}   (only 22 = SSH, key only, and 8000 = the gateway are expected)")

    pick = lambda i: captured[i % len(captured)]                                    # noqa: E731
    burst("replay", lambda i: pick(i), "attacker laptop: replay of captured traffic")

    def tamper(i):
        c = copy.deepcopy(pick(i))
        c["volume_ml"] = 20.0
        return c
    burst("tampered", tamper, "attacker laptop: tampered 1 mL to 20 mL")

    def forge(i):
        c = fresh(pick(i))
        c["volume_ml"] = 15.0
        c[SIG] = secrets.token_hex(32)
        return c
    burst("forged", forge, "attacker laptop: forged with own key")

    def unsigned(i):
        c = fresh(pick(i))
        c.pop(SIG, None)
        return c
    burst("unsigned", unsigned, "attacker laptop: unsigned")

    burst("garbage", lambda i: b"OPEN ALL VALVES", "attacker laptop: garbage")

    if summary:
        sent = sum(s[1] for s in summary)
        reached = sum(s[3] for s in summary)
        print(f"\n  {sent - reached}/{sent} attack commands blocked, {reached} reached a pump"
              + ("   ALL BLOCKED" if reached == 0 else "   !!"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
