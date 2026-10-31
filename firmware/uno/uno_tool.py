"""Talk to the ChemShield Uno directly: watch the probe, calibrate it and the pumps.

Run on the Pi with the station stopped (only one program can hold the serial port):

    .venv/bin/python firmware/uno/uno_tool.py watch          pH and volts every second
    .venv/bin/python firmware/uno/uno_tool.py cal 7.00       probe in the pH 7 buffer: store it
    .venv/bin/python firmware/uno/uno_tool.py cal 4.00       ... then pH 4, then pH 10
    .venv/bin/python firmware/uno/uno_tool.py show | clear   the stored calibration

Pumps (Final Prototype firmware; steps are FULL steps, 200 = one turn):

    uno_tool.py pumps                              the stored steps per mL, speed, microsteps
    uno_tool.py pump-cal 1 --steps 4000 --grams 19.62   from a weighing on the bench sketch
    uno_tool.py pump-cal 1 203.9                   or type the full steps per mL directly
    uno_tool.py pump-speed 800 1600                top speed (full steps/s) and acceleration
    uno_tool.py pump-clear                         back to the placeholders
    uno_tool.py dose ACID_FINE 5                   pump 5 mL through the real firmware (check
                                                   the calibration on a scale); Ctrl+C stops it
    uno_tool.py mix 150 | mix 0                    mixer speed (0-255) while the tool runs

`cal` waits until the reading is steady (10 s within 3 mV, about 0.02 pH), then tells the
Uno which buffer the probe is in. The Uno keeps up to three points (acid, neutral, base) in
its EEPROM and fits a straight line through them; it survives unplugging and re-flashing.
Use the value printed on the buffer bottle for the room temperature (for example 6.86 or
7.00, 4.00 or 4.01, 9.18 or 10.01).
"""
from __future__ import annotations

import argparse
import glob
import sys
import time


def open_uno(port: str | None):
    import serial                                              # pyserial
    if not port:
        found = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*")) \
            + sorted(glob.glob("/dev/cu.usbmodem*"))
        if not found:
            sys.exit("No Uno found on USB. Is the cable in, and is the station stopped?")
        port = found[0]
    ser = serial.Serial(port, 115200, timeout=0.2)
    deadline = time.time() + 6.0                               # opening the port resets the Uno
    while time.time() < deadline:
        if ser.readline().decode("ascii", "replace").startswith("READY"):
            break
    print(f"Uno on {port}")
    return ser


def lines(ser, seconds: float):
    end = time.time() + seconds
    while time.time() < end:
        raw = ser.readline().decode("ascii", "replace").strip()
        if raw:
            yield raw


def send(ser, line: str) -> None:
    ser.write((line + "\n").encode("ascii"))


def volts_now(ser) -> float | None:
    send(ser, "V")
    for ln in lines(ser, 1.5):
        if ln.startswith("V,"):
            return float(ln.split(",")[1])
    return None


def watch(ser) -> None:
    print("Ctrl+C to stop")
    while True:
        v = volts_now(ser)
        ph = next((ln for ln in lines(ser, 1.0) if ln.startswith("PH,")), "PH,?")
        print(f"{time.strftime('%H:%M:%S')}  {ph.split(',')[1]:>6} pH   {v if v is not None else float('nan'):.4f} V")


def calibrate(ser, buffer_ph: float, steady_mv: float = 3.0, timeout_s: float = 180.0) -> int:
    print(f"Probe in the pH {buffer_ph:.2f} buffer. Waiting for a steady reading "
          f"(10 s within {steady_mv:.0f} mV)...")
    history: list[float] = []
    start = time.time()
    while time.time() - start < timeout_s:
        v = volts_now(ser)
        if v is None:
            continue
        history = (history + [v])[-10:]
        spread = (max(history) - min(history)) * 1000
        print(f"  {v:.4f} V   spread over {len(history)} s: {spread:.1f} mV")
        if len(history) == 10 and spread <= steady_mv:
            break
        time.sleep(0.8)
    else:
        print("Not steady yet: storing anyway. Stir, wait and repeat if the result looks off.")
    send(ser, f"CAL,{buffer_ph:.2f}")
    ok = False
    for ln in lines(ser, 2.0):
        if ln.startswith("CAL,"):
            print(ln)
            ok = ok or ln.startswith("CAL,OK")
    return 0 if ok else 1


def answer(ser, line: str, prefix: str, seconds: float = 2.0) -> bool:
    """Send one line, print the answers that start with prefix; True if no ERROR came back."""
    send(ser, line)
    ok = True
    for ln in lines(ser, seconds):
        if ln.startswith(prefix):
            print(ln)
            ok = ok and ",ERROR" not in ln and not ln.startswith("ERROR")
    return ok


def steps_per_ml(values: list[str], steps: float | None, grams: float | None, density: float) -> float:
    """Full steps per mL, typed directly or from a weighing (steps run, grams collected)."""
    if steps is not None or grams is not None:
        if not steps or not grams or steps <= 0 or grams <= 0:
            raise ValueError("give both --steps and --grams (both above 0)")
        return steps / (grams / density)
    if len(values) < 2:
        raise ValueError("pump-cal needs the pump and full steps per mL, or --steps and --grams")
    return float(values[1])


def pump_dose(ser, channel: str, ml: float) -> int:
    """One PUMP dose through the station firmware, with the heartbeat the station would send."""
    send(ser, "HB")
    time.sleep(0.3)
    send(ser, f"PUMP,1,{channel.upper()},{ml:.3f}")
    print(f"pumping {ml:g} mL on {channel.upper()} (Ctrl+C stops it)")
    result = 1
    end = time.time() + 75.0
    next_hb = time.time()
    try:
        while time.time() < end:
            if time.time() >= next_hb:
                send(ser, "HB")
                next_hb += 0.5
            raw = ser.readline().decode("ascii", "replace").strip()
            if not raw or raw.startswith("PH,"):
                continue
            print(raw)
            if raw.startswith(("DONE,", "ABORT,", "REJECT,")):
                result = 0 if raw.startswith("DONE,") else 1
                break
    except KeyboardInterrupt:
        send(ser, "STOP")
        for ln in lines(ser, 1.0):
            if ln.startswith(("ABORT,", "OK,STOP")):
                print(ln)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="uno_tool.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("watch", "cal", "show", "clear", "pumps", "pump-cal",
                                        "pump-speed", "pump-clear", "dose", "mix"))
    ap.add_argument("values", nargs="*", help="cal: buffer pH; pump-cal: pump [steps per mL]; "
                                              "pump-speed: rate accel; dose: channel mL; mix: 0-255")
    ap.add_argument("--steps", type=float, help="pump-cal: full steps the bench sketch ran")
    ap.add_argument("--grams", type=float, help="pump-cal: grams collected in that run")
    ap.add_argument("--density", type=float, default=1.0, help="pump-cal: g/mL (default 1.0)")
    ap.add_argument("--port", help="serial port (default: find the Uno)")
    a = ap.parse_args(argv)
    v = a.values
    try:
        if a.command == "cal" and len(v) != 1:
            raise ValueError("cal needs the buffer pH, e.g. cal 7.00")
        if a.command == "pump-cal":
            if not v:
                raise ValueError("pump-cal needs the pump number 1-4")
            spm = steps_per_ml(v, a.steps, a.grams, a.density)
        if a.command == "pump-speed" and len(v) != 2:
            raise ValueError("pump-speed needs the top speed and the acceleration, e.g. 800 1600")
        if a.command == "dose" and len(v) != 2:
            raise ValueError("dose needs the channel and mL, e.g. dose ACID_FINE 5")
        if a.command == "mix" and len(v) != 1:
            raise ValueError("mix needs a speed 0-255")
    except ValueError as exc:
        ap.error(str(exc))
    ser = open_uno(a.port)
    try:
        if a.command == "watch":
            watch(ser)
        elif a.command == "cal":
            time.sleep(5.0)          # the Uno needs a few seconds of readings after its reset
            return calibrate(ser, float(v[0]))
        elif a.command == "pumps":
            answer(ser, "PCAL,SHOW", "PCAL,")
        elif a.command == "pump-cal":
            print(f"pump {v[0]}: {spm:.2f} full steps per mL")
            return 0 if answer(ser, f"PCAL,{int(v[0])},{spm:.3f}", "PCAL,") else 1
        elif a.command == "pump-speed":
            return 0 if answer(ser, f"PCAL,SPEED,{float(v[0]):g},{float(v[1]):g}", "PCAL,") else 1
        elif a.command == "pump-clear":
            answer(ser, "PCAL,CLEAR", "PCAL,")
        elif a.command == "dose":
            return pump_dose(ser, v[0], float(v[1]))
        elif a.command == "mix":
            send(ser, "HB")
            answer(ser, f"MIX,{int(v[0])}", "OK,MIX")
            print("Ctrl+C to stop the mixer and quit")
            while int(v[0]) > 0:
                send(ser, "HB")           # the Uno stops the mixer when the heartbeat stops
                time.sleep(0.5)
        else:
            send(ser, f"CAL,{a.command.upper()}")
            for ln in lines(ser, 2.0):
                if ln.startswith("CAL,"):
                    print(ln)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
