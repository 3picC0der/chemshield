"""Set the Pi's clock from this laptop, and check how far apart the two clocks are.

Every request the laptop HMI sends is stamped with the laptop's clock, and the gateway on
the Pi rejects anything more than 2 s away from its own clock (STALE_TIMESTAMP or
FUTURE_TIMESTAMP). On its own hotspot the Pi has no internet time, so after a reboot its
clock can be minutes or hours off and every dose is refused. Run this on the laptop after
every Pi boot:

    .venv/bin/python -m hmi.clock_sync --pi belal@10.42.0.1                        set + check
    .venv/bin/python -m hmi.clock_sync --check --station http://10.42.0.1:8000     check only

Setting needs SSH to the Pi with passwordless sudo (the default for the first user on
Raspberry Pi OS). Checking needs only the station to be running.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

OK_S = 0.5     # well inside the gateway's 2 s window

# Runs on the Pi: say it's ready, answer one ping so the laptop can time the link, take the
# laptop's time and set the clock, then answer each line with the Pi's own time.
_REMOTE = ('echo READY; read ping; echo PONG; read t; '
           'sudo -n date -u -s "@$t" >/dev/null || { echo "SUDO_FAILED" ; exit 3; }; '
           'echo SET; while read x; do date -u +%s.%N; done')


def set_over_ssh(target: str, ssh_opts: list[str], samples: int = 5) -> float:
    """Set the Pi's clock to this laptop's UTC time. Returns the offset measured afterwards
    (Pi minus laptop, seconds)."""
    proc = subprocess.Popen(["ssh", *ssh_opts, target, _REMOTE], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    assert proc.stdin is not None and proc.stdout is not None

    def expect(word: str) -> None:
        line = proc.stdout.readline().strip()
        if line != word:
            proc.kill()
            err = (proc.stderr.read() if proc.stderr else "").strip()
            hint = (" The Pi asked for a password: sudo must work without one."
                    if line == "SUDO_FAILED" else "")
            raise RuntimeError(f"expected {word!r} from the Pi, got {line!r}.{hint} {err}".strip())

    try:
        expect("READY")
        t1 = time.time()
        proc.stdin.write("ping\n")
        proc.stdin.flush()
        expect("PONG")
        one_way = (time.time() - t1) / 2.0
        proc.stdin.write(f"{time.time() + one_way:.6f}\n")
        proc.stdin.flush()
        expect("SET")
        offsets = []
        for _ in range(samples):
            t_send = time.time()
            proc.stdin.write("t\n")
            proc.stdin.flush()
            pi_t = float(proc.stdout.readline().strip())
            t_recv = time.time()
            offsets.append(pi_t - (t_send + t_recv) / 2.0)
        return statistics.median(offsets)
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.wait(timeout=10)


def check_station(url: str, samples: int = 5) -> float:
    """Offset of the station's clock from this laptop's (seconds), read from /api/state."""
    offsets = []
    for _ in range(samples):
        t_send = time.time()
        with urllib.request.urlopen(url.rstrip("/") + "/api/state", timeout=5) as r:
            state = json.loads(r.read().decode("utf-8"))
        t_recv = time.time()
        server = datetime.fromisoformat(state["server_utc"].replace("Z", "+00:00")).timestamp()
        offsets.append(server - (t_send + t_recv) / 2.0)
    return statistics.median(offsets)


def _verdict(offset_s: float, what: str) -> int:
    ok = abs(offset_s) <= OK_S
    print(f"{what} is {offset_s * 1000:+.0f} ms from this laptop: "
          f"{'OK' if ok else 'TOO FAR (the gateway allows 2 s; run with --pi to set it)'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.clock_sync", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pi", help="SSH target to set, e.g. belal@10.42.0.1")
    ap.add_argument("--station", help="station URL to check, e.g. http://10.42.0.1:8000")
    ap.add_argument("--check", action="store_true", help="only check (needs --station)")
    ap.add_argument("--ssh-option", action="append", default=[], metavar="OPT",
                    help="extra option passed to ssh, e.g. --ssh-option=-oConnectTimeout=5")
    a = ap.parse_args(argv)
    if a.check or not a.pi:
        if not a.station:
            ap.error("give --pi to set the clock, or --check --station URL to check it")
        return _verdict(check_station(a.station), "The station's clock")
    try:
        offset = set_over_ssh(a.pi, a.ssh_option)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Could not set the Pi's clock: {exc}", file=sys.stderr)
        return 2
    rc = _verdict(offset, "The Pi's clock")
    if a.station:
        rc = max(rc, _verdict(check_station(a.station), "The station's clock"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
