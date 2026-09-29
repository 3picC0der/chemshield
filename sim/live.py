"""Live simulator: the tank running in real time at the booth.

    python -m sim.live                                  # 1 Hz, I2 to stdout
    python -m sim.live --udp 127.0.0.1:9101             # also publish I2 over UDP
    python -m sim.live --listen 9100                    # accept commands over UDP
    python -m sim.live --scenario acid_upset_max        # start with an upset injected
    python -m sim.live --autopilot                      # the MILP drives it by itself

Publishes one I2 message per second (docs/interfaces.md):

    {"t": 1790000000.0, "ph": 3.12, "temp_c": 25.0, "level_ok": true,
     "excess_mmol": -30.4, "state": "RECOVERY", "event_mmol_used": 20.0, "source": "SIM"}

Accepts these commands as one JSON object per UDP datagram (or one per line on stdin):

    {"cmd": "dose",   "channel_id": "BASE_BULK", "dose_ml": 11.8}   an approved dose
    {"cmd": "upset",  "scenario": "acid_upset_max"}                 inject an unsafe event
    {"cmd": "upset",  "ml": 60, "acid": true}                       inject a custom event
    {"cmd": "reset"}                                                back to 5.000 L of fresh liquid
    {"cmd": "fault",  "kind": "pump_under", "value": 0.7}           inject a fault
    {"cmd": "state"}                                                reply with I2 now

Only approved doses arrive here. This module is a plant, not a gatekeeper: it applies
what it is told and never second-guesses the gateway. The 20 mL cap, the 15 s lockout
and the 50 mmol budget are enforced by the gateway and the Uno, which is the point of
the architecture.
"""
from __future__ import annotations

import argparse
import json
import queue
import socket
import sys
import threading
import time

from . import chemistry as ch
from .engine import use_table_chemistry
from .model import P
from . import scenarios as SC

CHANNEL_MOLARITY = {"BASE_BULK": 0.5, "BASE_FINE": 0.005,
                    "ACID_BULK": 0.5, "ACID_FINE": 0.005}
CHANNEL_SIGN = {"BASE_BULK": +1.0, "BASE_FINE": +1.0,     # base raises excess_mmol
                "ACID_BULK": -1.0, "ACID_FINE": -1.0}


class Tank:
    """Tank state in the I2 convention: excess_mmol is base-positive."""

    def __init__(self, volume_L: float = 5.0, temp_c: float = 25.0, seed: int = 261):
        import numpy as np
        self.rng = np.random.default_rng(seed)
        self.volume_L = float(volume_L)
        self.temp_c = float(temp_c)
        self.excess_mmol = 0.0           # the liquid as prepared (NaHCO3: pH ~8.30, not 7)
        self.state = "IDLE"
        self.event_mmol_used = 0.0
        self.event_ml_used = 0.0
        self.event_t0: float | None = None
        self.ph_read = self.ph_true      # the probe starts settled on the liquid
        self.tau_s = 4.0                 # probe + mixing lag; measure it and replace
        self.noise_pH = 0.02             # per-sample probe noise; measure and replace
        self.pump_bias = 0.0             # relative delivery error, set by a fault
        self.pending: list[tuple[float, float]] = []   # (seconds_left, mmol_per_second)
        self.band_dwell_s = 60.0         # the test sheets' "stays inside for 60 s"
        self.in_band_since: float | None = None
        self.recovery_time_s: float | None = None

    # ---------------------------------------------------------------- chemistry
    @property
    def ph_true(self) -> float:
        return ch.ph_from_excess(self.excess_mmol, self.temp_c, self.volume_L)

    def step(self, dt: float) -> None:
        # deliver any dose still running (a 20 mL dose at 300 mL/min takes 4 s)
        rest = []
        for left, rate in self.pending:
            take = min(dt, left)
            self.excess_mmol += rate * take
            if left - take > 1e-9:
                rest.append((left - take, rate))
        self.pending = rest
        # probe lag, then noise
        self.ph_read += (self.ph_true - self.ph_read) * min(1.0, dt / self.tau_s)
        self.ph_read += float(self.rng.normal(0.0, self.noise_pH))

    # ------------------------------------------------------------------ actions
    def dose(self, channel_id: str, dose_ml: float) -> dict:
        if channel_id not in CHANNEL_MOLARITY:
            return {"ok": False, "error": f"unknown channel {channel_id}"}
        ml = float(dose_ml) * (1.0 + self.pump_bias)
        mmol = CHANNEL_MOLARITY[channel_id] * ml * CHANNEL_SIGN[channel_id]
        secs = max(0.5, ml / (P["Q"] / 60.0))
        self.pending.append((secs, mmol / secs))
        self.volume_L += ml / 1000.0
        self.event_mmol_used += abs(CHANNEL_MOLARITY[channel_id] * ml)
        self.event_ml_used += ml
        return {"ok": True, "channel_id": channel_id, "dose_ml": round(dose_ml, 3),
                "delivered_ml": round(ml, 3), "mmol": round(abs(mmol), 4),
                "runtime_s": round(secs, 2),
                "event_mmol_used": round(self.event_mmol_used, 4)}

    def upset(self, ml: float, acid: bool) -> dict:
        """An unauthorised injection that bypassed the gateway."""
        mmol = 0.5 * float(ml) * (-1.0 if acid else +1.0)
        self.excess_mmol += mmol
        self.volume_L += float(ml) / 1000.0
        self.state = "RECOVERY"
        self.event_mmol_used = 0.0
        self.event_ml_used = 0.0
        self.event_t0 = time.time()
        return {"ok": True, "upset_ml": ml, "acid": acid, "upset_mmol": round(abs(mmol), 3),
                "ph": round(self.ph_true, 3)}

    def reset(self) -> dict:
        self.__init__(5.0, self.temp_c)          # noqa: PLC2801 - deliberate re-init
        return {"ok": True, "state": self.state, "ph": round(self.ph_true, 3)}

    def fault(self, kind: str, value: float) -> dict:
        if kind == "pump_under":
            self.pump_bias = float(value) - 1.0
        elif kind == "probe_noise":
            self.noise_pH = float(value)
        elif kind == "mixer_off":
            self.tau_s = float(value) if value else 40.0
        elif kind == "clear":
            self.pump_bias, self.noise_pH, self.tau_s = 0.0, 0.02, 4.0
        else:
            return {"ok": False, "error": f"unknown fault {kind}"}
        return {"ok": True, "fault": kind, "value": value}

    # -------------------------------------------------------------------- I2
    def i2(self) -> dict:
        band = P["band"]
        now = time.time()
        inside = band[0] <= self.ph_read <= band[1] and not self.pending
        if self.state == "RECOVERY":
            # leave RECOVERY only once the reading has held inside the band for the
            # full dwell, which is the definition the test sheets use for "restored"
            if inside:
                if self.in_band_since is None:
                    self.in_band_since = now
                elif now - self.in_band_since >= self.band_dwell_s:
                    self.state = "MONITOR"
                    if self.event_t0 is not None:
                        self.recovery_time_s = self.in_band_since - self.event_t0
            else:
                self.in_band_since = None
        return {"t": round(time.time(), 3),
                "ph": round(self.ph_read, 4),
                "temp_c": round(self.temp_c, 2),
                "level_ok": bool(self.volume_L <= P["V_hi"]),
                "excess_mmol": round(self.excess_mmol, 5),
                "state": self.state,
                "event_mmol_used": round(self.event_mmol_used, 4),
                "source": "SIM",
                # beyond the I2 contract, but useful and safe to ignore:
                "volume_L": round(self.volume_L, 4),
                "ph_true": round(self.ph_true, 4),
                "event_ml_used": round(self.event_ml_used, 3),
                "event_elapsed_s": (round(time.time() - self.event_t0, 2)
                                    if self.event_t0 else 0.0),
                "recovery_time_s": (round(self.recovery_time_s, 2)
                                    if self.recovery_time_s else None),
                "chem_source": ch.table_provenance()}


def _listener(port: int, q: "queue.Queue[dict]") -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    while True:
        data, _addr = s.recvfrom(4096)
        try:
            q.put(json.loads(data.decode("utf-8")))
        except Exception as exc:                          # noqa: BLE001
            print(json.dumps({"error": f"bad command: {exc}"}), flush=True)


def _stdin_reader(q: "queue.Queue[dict]") -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            q.put(json.loads(line))
        except Exception as exc:                          # noqa: BLE001
            print(json.dumps({"error": f"bad command: {exc}"}), flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sim.live", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hz", type=float, default=1.0, help="I2 publish rate (default 1)")
    ap.add_argument("--udp", default="", metavar="HOST:PORT", help="also send I2 here")
    ap.add_argument("--listen", type=int, default=0, metavar="PORT",
                    help="accept commands on this UDP port")
    ap.add_argument("--scenario", default="", help=f"one of: {', '.join(SC.list_names())}")
    ap.add_argument("--autopilot", action="store_true",
                    help="let the MILP plan and apply doses (no gateway in the loop)")
    ap.add_argument("--seconds", type=float, default=0.0, help="stop after N seconds")
    ap.add_argument("--seed", type=int, default=261)
    a = ap.parse_args(argv)

    source = use_table_chemistry()
    tank = Tank(seed=a.seed)
    print(json.dumps({"event": "start", "chem_source": source, "hz": a.hz,
                      "autopilot": bool(a.autopilot)}), flush=True)

    settle_s = P["t_detect"] + 3.0 * tank.tau_s     # probe lag before the first reading
    first_plan_at = 0.0
    if a.scenario:
        sc = SC.named(a.scenario)
        print(json.dumps({"event": "upset", **tank.upset(sc["vol"], sc["acid"]),
                          "scenario": a.scenario}), flush=True)
        first_plan_at = time.time() + settle_s

    out_sock = None
    if a.udp:
        host, _, port = a.udp.partition(":")
        out_sock = (socket.socket(socket.AF_INET, socket.SOCK_DGRAM), (host, int(port)))

    q: "queue.Queue[dict]" = queue.Queue()
    if a.listen:
        threading.Thread(target=_listener, args=(a.listen, q), daemon=True).start()
        print(json.dumps({"event": "listening", "udp_port": a.listen}), flush=True)
    if not sys.stdin.isatty():
        threading.Thread(target=_stdin_reader, args=(q,), daemon=True).start()

    plan_block = None
    if a.autopilot:
        from redosing.planner import plan_block as _pb
        plan_block = _pb

    dt = 1.0 / a.hz
    t_end = time.time() + a.seconds if a.seconds else None
    next_plan = first_plan_at
    try:
        while True:
            tank.step(dt)
            while not q.empty():
                c = q.get()
                cmd = str(c.get("cmd", "")).lower()
                if cmd == "dose":
                    r = tank.dose(c.get("channel_id", ""), c.get("dose_ml", 0.0))
                elif cmd == "upset":
                    if c.get("scenario"):
                        sc = SC.named(c["scenario"])
                        r = tank.upset(sc["vol"], sc["acid"])
                    else:
                        r = tank.upset(float(c.get("ml", 60)), bool(c.get("acid", True)))
                    next_plan = time.time() + settle_s
                elif cmd == "reset":
                    r = tank.reset()
                elif cmd == "fault":
                    r = tank.fault(str(c.get("kind", "")), float(c.get("value", 0)))
                elif cmd == "state":
                    r = {"ok": True}
                else:
                    r = {"ok": False, "error": f"unknown cmd {cmd!r}"}
                print(json.dumps({"event": "command", "cmd": cmd, **r}), flush=True)

            msg = tank.i2()
            line = json.dumps(msg)
            print(line, flush=True)
            if out_sock:
                out_sock[0].sendto(line.encode("utf-8"), out_sock[1])

            if plan_block and tank.state == "RECOVERY" and not tank.pending \
                    and time.time() >= next_plan:
                d = plan_block(msg)
                print(json.dumps({"event": "plan", **d}), flush=True)
                if d["action"] == "DOSE":
                    for step in d["block"]:
                        tank.dose(step["channel_id"], step["dose_ml"])
                    next_plan = time.time() + P["t_hold"]
                else:
                    next_plan = time.time() + 5.0

            if t_end and time.time() >= t_end:
                break
            time.sleep(dt)
    except KeyboardInterrupt:
        pass
    print(json.dumps({"event": "stop", **tank.i2()}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
