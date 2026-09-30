"""The station's two possible pH sources, behind one interface.

UnoLink   the real rig: the Uno on the Pi's USB port. The Uno sends `PH,7.02` once a
          second; the Pi sends a heartbeat, dose and mode lines (docs in hmi/README.md).
SimLink   no hardware: Hattan's simulated tank (sim/live.py) with probe lag and noise,
          plus a stand-in for the Uno's light. The HMI labels everything from it SIM.

The station only ever calls the methods on Link, so the recovery logic, Model A and the
gateway run exactly the same code in both modes.
"""
from __future__ import annotations

import glob
import threading
import time
from collections import deque
from typing import Any, Callable

HEARTBEAT_PERIOD_S = 0.5     # I5: the Pi sends HB every 0.5 s
LINK_TIMEOUT_S = 2.0         # no line from the Uno for this long = link lost (I5 uses 2 s)

# What the Uno's light is doing, as the HMI shows it.
LED_WORDS = {
    "off": "off (normal)",
    "dose": "ON: dose now",
    "locked": "slow blink: dosing locked (recovery)",
    "halt": "fast blink: halted",
    "unknown": "unknown (no link)",
}
MODE_TO_LED = {"NORMAL": "off", "RECOVERY": "locked", "HALT": "halt"}


class Link:
    kind = "BASE"            # "SIM" or "PROBE": which pH source the HMI must label

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self._lock = threading.Lock()
        self._readings: deque[tuple[float, float]] = deque()
        self._uno_events: deque[dict[str, Any]] = deque()
        self.last_line_t: float | None = None
        self.mode = "NORMAL"
        self.dose_on = False
        self.estop = False
        self.last_mode_ack: dict[str, Any] | None = None   # {"mode", "sent_t", "ack_t"}

    # ---------------------------------------------------------------- station side
    def start(self) -> None: ...
    def close(self) -> None: ...

    def poll(self) -> tuple[list[tuple[float, float]], list[dict[str, Any]]]:
        """New (t, pH) readings and Uno events since the last poll."""
        with self._lock:
            readings, events = list(self._readings), list(self._uno_events)
            self._readings.clear()
            self._uno_events.clear()
        return readings, events

    def alive(self, now: float | None = None) -> bool:
        now = self.clock() if now is None else now
        return self.last_line_t is not None and now - self.last_line_t < LINK_TIMEOUT_S

    def line_age_s(self, now: float | None = None) -> float | None:
        now = self.clock() if now is None else now
        return None if self.last_line_t is None else max(0.0, now - self.last_line_t)

    def led(self) -> str:
        if not self.alive():
            return "unknown"
        if self.dose_on:
            return "dose"
        return MODE_TO_LED.get(self.mode, "off")

    def send_mode(self, mode: str) -> None:
        self.mode = mode
        self.last_mode_ack = {"mode": mode, "sent_t": self.clock(), "ack_t": None}
        self._write(f"MODE,{mode}")

    def dose(self, seq: int, pump: int, run_ms: int) -> None:
        """Light the dose light for this dose (with hand dosing, the light means 'dose now')."""
        self.dose_on = True
        self._write(f"DOSE,{seq},{pump},{int(run_ms)}")

    def stop_dose(self) -> None:
        self.dose_on = False
        self._write("STOP")

    def dose_added(self, channel_id: str, dose_ml: float) -> None:
        """The operator says the dose is in the tank. Only the simulator acts on it."""

    def info(self) -> dict[str, Any]:
        return {"kind": self.kind, "alive": self.alive(), "line_age_s": self.line_age_s(),
                "led": self.led(), "led_words": LED_WORDS[self.led()], "estop": self.estop,
                "mode_sent": self.mode, "mode_ack": self.last_mode_ack}

    # ---------------------------------------------------------------- helpers
    def _write(self, line: str) -> None:
        raise NotImplementedError

    def _got_line(self, t: float) -> None:
        self.last_line_t = t

    def _add_reading(self, t: float, ph: float) -> None:
        with self._lock:
            self._readings.append((t, ph))
        self._got_line(t)

    def _add_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._uno_events.append(event)


# ====================================================================== real Uno
class UnoLink(Link):
    """The Uno on USB serial (115200 baud). Needs pyserial.

    Pi -> Uno:  HB | DOSE,<seq>,<pump 1-4>,<run_ms> | STOP | MODE,<NORMAL|RECOVERY|HALT> | STATUS
    Uno -> Pi:  PH,<pH> (once a second) | OK,<seq> | OK,MODE,<mode> | OK,STOP |
                REJECT,<seq>,<reason> | DONE,<seq>,<ms_run> | STATUS,<estop 0/1>,<busy 0/1>
    """
    kind = "PROBE"

    def __init__(self, port: str = "auto", baud: int = 115200, clock=time.monotonic) -> None:
        super().__init__(clock)
        self.port = port
        self.baud = baud
        self._ser = None
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self.last_error = ""
        self.raw_tail: deque[str] = deque(maxlen=40)     # last lines, for the engineer panel

    @staticmethod
    def find_port() -> str | None:
        for pattern in ("/dev/ttyACM*", "/dev/ttyUSB*", "/dev/cu.usbmodem*", "/dev/cu.usbserial*"):
            found = sorted(glob.glob(pattern))
            if found:
                return found[0]
        return None

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="uno-link").start()
        threading.Thread(target=self._heartbeat, daemon=True, name="uno-heartbeat").start()

    def close(self) -> None:
        self._stop.set()
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:                                  # noqa: BLE001
                pass

    def _open(self):
        import serial                                          # pyserial
        port = self.find_port() if self.port == "auto" else self.port
        if not port:
            raise OSError("no Uno found on USB (looked for /dev/ttyACM*, /dev/cu.usbmodem*)")
        ser = serial.Serial(port, self.baud, timeout=0.2)
        self.port_in_use = port
        return ser

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._ser = self._open()
                self.last_error = ""
                # opening the port resets the Uno; tell it the mode again once it talks
                resent = False
                while not self._stop.is_set():
                    raw = self._ser.readline()
                    if not raw:
                        continue
                    line = raw.decode("ascii", errors="replace").strip()
                    if not line:
                        continue
                    now = self.clock()
                    self.raw_tail.append(line)
                    self._parse(line, now)
                    if not resent:
                        self._write(f"MODE,{self.mode}")
                        resent = True
            except Exception as exc:                           # noqa: BLE001 - keep retrying
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._ser = None
                time.sleep(1.0)

    def _heartbeat(self) -> None:
        while not self._stop.is_set():
            self._write("HB")
            time.sleep(HEARTBEAT_PERIOD_S)

    def _write(self, line: str) -> None:
        ser = self._ser
        if ser is None:
            return
        try:
            with self._write_lock:
                ser.write((line + "\n").encode("ascii"))
        except Exception as exc:                               # noqa: BLE001
            self.last_error = f"write failed: {exc}"

    def _parse(self, line: str, now: float) -> None:
        parts = line.split(",")
        head = parts[0].upper()
        if head == "PH" and len(parts) >= 2:
            try:
                ph = float(parts[1])
            except ValueError:
                self._got_line(now)
                return
            if 0.0 <= ph <= 14.0:
                self._add_reading(now, ph)
            else:
                self._got_line(now)
            return
        self._got_line(now)
        event: dict[str, Any] = {"t": now, "line": line}
        if head == "OK" and len(parts) >= 3 and parts[1].upper() == "MODE":
            if self.last_mode_ack and self.last_mode_ack["ack_t"] is None \
                    and parts[2].upper() == self.last_mode_ack["mode"]:
                self.last_mode_ack["ack_t"] = now
            event["kind"] = "MODE_ACK"
        elif head == "DONE":
            self.dose_on = False
            event["kind"] = "DONE"
        elif head == "REJECT":
            self.dose_on = False
            event["kind"] = "UNO_REJECT"
            event["reason"] = parts[2] if len(parts) > 2 else ""
        elif head == "STATUS" and len(parts) >= 2:
            estop = parts[1].strip() == "1"
            if estop and not self.estop:
                event["kind"] = "ESTOP"
            self.estop = estop
        elif head in ("ESTOP", "E-STOP"):
            self.estop = True
            event["kind"] = "ESTOP"
        elif head in ("HB_LOST", "HEARTBEAT_LOST"):
            event["kind"] = "UNO_HEARTBEAT_LOST"
        else:
            event["kind"] = head
        self._add_event(event)

    def info(self) -> dict[str, Any]:
        out = super().info()
        out.update({"port": getattr(self, "port_in_use", self.port), "error": self.last_error,
                    "tail": list(self.raw_tail)[-8:]})
        return out


# ====================================================================== simulator
class SimLink(Link):
    """Hattan's tank simulator standing in for the probe, and a stand-in for the Uno's light.

    Readings come out once a second through the same path as `PH,x` lines from the Uno,
    with the simulator's probe lag and noise. Nothing here decides anything.
    """
    kind = "SIM"

    def __init__(self, start_ph: float = 7.0, seed: int = 261, auto_pump: bool = True,
                 hand_speed_ml_s: float = 2.0, clock=time.monotonic) -> None:
        super().__init__(clock)
        from sim import chemistry as ch
        from sim.engine import use_table_chemistry
        from sim.live import Tank
        self.chem_source = use_table_chemistry()
        self._ch = ch
        self._Tank = Tank
        self.seed = seed
        self.start_ph = float(start_ph)
        self.auto_pump = bool(auto_pump)
        self.hand_speed_ml_s = float(hand_speed_ml_s)
        self.tank = None
        self.unplugged_until: float | None = None
        self._next_reading_t: float | None = None
        self._last_step_t: float | None = None
        self._dose_ends_t: float | None = None
        self.reset(start_ph)

    def reset(self, start_ph: float | None = None) -> dict[str, Any]:
        """A fresh 5 L tank of the baking-soda liquid, set to start_ph (the 'pH 7' setup
        step: about 1.8 mL of 0.5 M acid). start_ph None or <= 0 = the liquid as made."""
        if start_ph is not None:
            self.start_ph = float(start_ph)
        self.tank = self._Tank(volume_L=5.0, seed=self.seed)
        if self.start_ph > 0:
            self._set_excess(self._ch.excess_from_ph(self.start_ph, self.tank.temp_c, self.tank.volume_L))
        return {"ph": round(self.tank.ph_true, 3), "excess_mmol": round(self.tank.excess_mmol, 4)}

    def _set_excess(self, excess_mmol: float) -> None:
        self.tank.excess_mmol = float(excess_mmol)
        self.tank.pending = []
        self.tank.ph_read = self.tank.ph_true

    def start(self) -> None:
        now = self.clock()
        self._last_step_t = now
        self._next_reading_t = now
        self.last_line_t = now

    def poll(self):
        self._advance(self.clock())
        return super().poll()

    def _advance(self, now: float) -> None:
        if self._last_step_t is None:
            self.start()
        unplugged = self.unplugged_until is not None and now < self.unplugged_until
        if self.unplugged_until is not None and not unplugged:
            self.unplugged_until = None
            self.send_mode(self.mode)          # like the real Uno after a reconnect
        # step the tank in <= 0.25 s slices so probe lag behaves the same at any tick rate
        while self._last_step_t < now:
            dt = min(0.25, now - self._last_step_t)
            self.tank.step(dt)
            self._last_step_t += dt
        if self.dose_on and self._dose_ends_t is not None and now >= self._dose_ends_t:
            self.dose_on = False                 # the light's run time is over (I5 DONE)
            self._dose_ends_t = None
            if not unplugged:
                self._add_event({"t": now, "line": "DONE", "kind": "DONE"})
        if unplugged:
            return
        while self._next_reading_t is not None and self._next_reading_t <= now:
            ph = min(14.0, max(0.0, float(self.tank.ph_read)))
            self._add_reading(self._next_reading_t, round(ph, 3))
            self._next_reading_t += 1.0
        if self._next_reading_t is not None and self._next_reading_t < now - 5.0:
            self._next_reading_t = now

    def _write(self, line: str) -> None:
        now = self.clock()
        if self.unplugged_until is not None and now < self.unplugged_until:
            return
        if line.startswith("MODE,") and self.last_mode_ack and self.last_mode_ack["ack_t"] is None:
            self.last_mode_ack["ack_t"] = now     # the stand-in answers at once
            self._add_event({"t": now, "line": f"OK,{line}", "kind": "MODE_ACK"})

    def send_mode(self, mode: str) -> None:
        super().send_mode(mode)
        if mode == "HALT":
            self.dose_on = False

    def dose(self, seq: int, pump: int, run_ms: int) -> None:
        super().dose(seq, pump, run_ms)
        self._dose_ends_t = self.clock() + run_ms / 1000.0

    def dose_added(self, channel_id: str, dose_ml: float) -> None:
        self.tank.dose(channel_id, float(dose_ml))

    # ---------------------------------------------------------------- demo controls
    def upset(self, ml: float, acid: bool) -> dict[str, Any]:
        """Reagent that got into the tank without the gateway (the 'unsafe dose')."""
        return self.tank.upset(float(ml), bool(acid))

    def set_ph(self, ph: float) -> dict[str, Any]:
        self._set_excess(self._ch.excess_from_ph(float(ph), self.tank.temp_c, self.tank.volume_L))
        return {"ph": round(self.tank.ph_true, 3)}

    def unplug(self, seconds: float) -> dict[str, Any]:
        """Pretend the USB cable was pulled for `seconds`: no readings, no replies."""
        self.unplugged_until = self.clock() + float(seconds)
        self.dose_on = False
        return {"unplugged_for_s": float(seconds)}

    def info(self) -> dict[str, Any]:
        out = super().info()
        now = self.clock()
        out.update({"chem_source": self.chem_source, "auto_pump": self.auto_pump,
                    "start_ph": self.start_ph,
                    "true_ph": round(float(self.tank.ph_true), 3),
                    "volume_L": round(float(self.tank.volume_L), 4),
                    "unplugged_s_left": (round(self.unplugged_until - now, 1)
                                         if self.unplugged_until and now < self.unplugged_until else 0)})
        return out
