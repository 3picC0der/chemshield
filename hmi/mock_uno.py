"""A pretend Uno on a virtual serial port, for testing the Pi side without the board.

    .venv/bin/python -m hmi.mock_uno                 prints the port, e.g. /dev/ttys012
    .venv/bin/python -m hmi.station --ph-source uno --serial-port /dev/ttys012

It speaks exactly the lines the real firmware must speak (hmi/README.md, "Uno lines"),
so it is also the reference for the sketch. A PUMP line "runs" the pump at 4 mL/s and
answers DONE or ABORT with the volume delivered, like the Final Prototype's Uno. Type into
its terminal to change things:
    ph 5.4        the probe now reads 5.4
    estop         press the E-stop            release     release it
    mute 5        stop talking for 5 s (like pulling the USB cable)
"""
from __future__ import annotations

import os
import select
import sys
import threading
import time

HB_TIMEOUT_S = 2.0
MAX_DOSE_ML = 20.0
CHANNELS = ("ACID_BULK", "ACID_FINE", "BASE_BULK", "BASE_FINE")   # pumps 1-4 on the CNC shield


class MockUno:
    def __init__(self, ph: float = 7.0, noise: float = 0.01, verbose: bool = True,
                 ml_per_s: float = 4.0) -> None:
        self.master, self.slave = os.openpty()
        self.port = os.ttyname(self.slave)
        self.ph = float(ph)
        self.noise = float(noise)
        self.verbose = verbose
        self.mode = "NORMAL"
        self.estop = False
        self.led_until = 0.0
        self.dose_seq: str | None = None
        self.ml_per_s = float(ml_per_s)
        self.pump: dict | None = None          # the running pump dose: seq, channel, ml, t0
        self.mix = 0
        self.mix_until = 0.0
        self.last_hb = 0.0
        self.hb_lost_reported = False
        self.mute_until = 0.0
        self.lines_in: list[str] = []
        self._stop = threading.Event()
        self._buf = b""

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[uno {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def send(self, line: str) -> None:
        if time.time() < self.mute_until:
            return
        os.write(self.master, (line + "\n").encode("ascii"))

    def led(self) -> str:
        now = time.time()
        if self.estop:
            return "all off (E-stop)"
        if now < self.led_until or self.pump:
            return "ON: dose now"
        return {"NORMAL": "off", "RECOVERY": "slow blink (locked)", "HALT": "fast blink (halted)"}.get(self.mode, "off")

    def handle(self, line: str) -> None:
        self.lines_in.append(line)
        now = time.time()
        parts = line.strip().split(",")
        head = parts[0].upper()
        if head == "HB":
            self.last_hb = now
            self.hb_lost_reported = False
        elif head == "MODE" and len(parts) >= 2:
            was, self.mode = self.mode, parts[1].upper()
            if self.mode == "HALT":
                self.led_until = 0.0
                self.end_pump(now, "HALT")
            elif self.mode == "RECOVERY" and was != "RECOVERY":
                self.end_pump(now, "RECOVERY")
            self.send(f"OK,MODE,{self.mode}")
            self.log(f"mode {self.mode}; light {self.led()}")
        elif head == "PUMP" and len(parts) >= 4:
            seq, channel = parts[1], parts[2].upper()
            try:
                ml = float(parts[3])
            except ValueError:
                ml = 0.0
            why = self.busy_reason(now)
            if channel not in CHANNELS or not ml > 0:
                self.send(f"REJECT,{seq},BAD")
            elif ml > MAX_DOSE_ML:
                self.send(f"REJECT,{seq},TOO_MUCH")
            elif why:
                self.send(f"REJECT,{seq},{why}")
            else:
                self.pump = {"seq": seq, "channel": channel, "ml": ml, "t0": now}
                self.send(f"OK,{seq}")
                self.log(f"pump {CHANNELS.index(channel) + 1} ({channel}) running for {ml:g} mL")
        elif head == "MIX" and len(parts) >= 2:
            self.mix = 0 if self.estop else max(0, min(255, int(float(parts[1]))))
            self.send(f"OK,MIX,{self.mix}")
        elif head == "DOSE" and len(parts) >= 4:
            seq, pump, run_ms = parts[1], parts[2], int(float(parts[3]))
            why = self.busy_reason(now)
            if run_ms > 60000:
                self.send(f"REJECT,{seq},TOO_LONG")
            elif why:
                self.send(f"REJECT,{seq},{why}")
            else:
                self.led_until = now + run_ms / 1000.0
                self.dose_seq = seq
                self.send(f"OK,{seq}")
                self.log(f"dose {seq} on pump {pump} for {run_ms} ms: light ON")
        elif head == "STOP":
            self.led_until = 0.0
            self.end_pump(now, "STOP")
            self.send("OK,STOP")
        elif head == "STATUS":
            self.send(f"STATUS,{int(self.estop)},{int(time.time() < self.led_until or bool(self.pump))}")

    def busy_reason(self, now: float) -> str:
        if self.estop:
            return "ESTOP"
        if self.mode == "HALT":
            return "HALTED"
        if not self.last_hb or now - self.last_hb > HB_TIMEOUT_S:
            return "NO_HB"
        if now < self.led_until or self.pump:
            return "BUSY"
        return ""

    def end_pump(self, now: float, why: str | None) -> None:
        """Stop the running pump: why None = finished (DONE), else ABORT with the reason."""
        p = self.pump
        if not p:
            return
        self.pump = None
        ml = min(p["ml"], (now - p["t0"]) * self.ml_per_s)
        if why is None:
            self.send(f"DONE,{p['seq']},{p['channel']},{ml:.3f}")
        else:
            self.send(f"ABORT,{p['seq']},{p['channel']},{ml:.3f},{why}")
        if ml > 0:
            self.mix_until = now + 15.0
        self.log(f"pump {p['channel']} {'done' if why is None else 'stopped (' + why + ')'}: {ml:.3f} mL")

    def step(self, now: float) -> None:
        if self.pump and (now - self.pump["t0"]) * self.ml_per_s >= self.pump["ml"]:
            self.end_pump(now, None)
        if self.dose_seq and now >= self.led_until:
            self.send(f"DONE,{self.dose_seq},0")
            self.dose_seq = None
        if self.last_hb and now - self.last_hb > HB_TIMEOUT_S and not self.hb_lost_reported:
            self.led_until = 0.0
            self.end_pump(now, "HB_LOST")
            self.mix = 0
            self.hb_lost_reported = True
            self.send("HB_LOST")
            self.log("HEARTBEAT LOST, STOPPED")

    def run(self) -> None:
        import random
        next_ph = time.time()
        while not self._stop.is_set():
            r, _, _ = select.select([self.master], [], [], 0.05)
            if r:
                try:
                    self._buf += os.read(self.master, 1024)
                except OSError:
                    break
                while b"\n" in self._buf:
                    raw, self._buf = self._buf.split(b"\n", 1)
                    self.handle(raw.decode("ascii", "replace"))
            now = time.time()
            self.step(now)
            if now >= next_ph:
                self.send(f"PH,{self.ph + random.gauss(0.0, self.noise):.2f}")
                next_ph += 1.0

    def start(self) -> "MockUno":
        threading.Thread(target=self.run, daemon=True, name="mock-uno").start()
        return self

    def stop(self) -> None:
        self._stop.set()


def main() -> int:
    uno = MockUno().start()
    print(f"pretend Uno on {uno.port}\n"
          f"run: .venv/bin/python -m hmi.station --ph-source uno --serial-port {uno.port}\n"
          f"type: ph <x> | estop | release | mute <s> | status", flush=True)
    for line in sys.stdin:
        w = line.strip().split()
        if not w:
            continue
        if w[0] == "ph" and len(w) > 1:
            uno.ph = float(w[1])
        elif w[0] == "estop":
            uno.estop = True
            uno.led_until = 0.0
            uno.end_pump(time.time(), "ESTOP")
            uno.mix = 0
            uno.send("STATUS,1,0")
        elif w[0] == "release":
            uno.estop = False
            uno.send("STATUS,0,0")
        elif w[0] == "mute" and len(w) > 1:
            uno.mute_until = time.time() + float(w[1])
        print(f"pH {uno.ph:.2f} · mode {uno.mode} · light {uno.led()} · E-stop {'PRESSED' if uno.estop else 'released'}",
              flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
