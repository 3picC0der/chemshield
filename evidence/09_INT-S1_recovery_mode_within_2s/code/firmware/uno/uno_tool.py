"""Talk to the ChemShield Uno directly: watch the probe and calibrate it.

Run on the Pi with the station stopped (only one program can hold the serial port):

    .venv/bin/python firmware/uno/uno_tool.py watch          pH and volts every second
    .venv/bin/python firmware/uno/uno_tool.py cal 7.00       probe in the pH 7 buffer: store it
    .venv/bin/python firmware/uno/uno_tool.py cal 4.00       ... then pH 4, then pH 10
    .venv/bin/python firmware/uno/uno_tool.py show | clear   the stored calibration

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="uno_tool.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("watch", "cal", "show", "clear"))
    ap.add_argument("buffer_ph", nargs="?", type=float, help="for cal: the buffer's pH")
    ap.add_argument("--port", help="serial port (default: find the Uno)")
    a = ap.parse_args(argv)
    ser = open_uno(a.port)
    try:
        if a.command == "watch":
            watch(ser)
        elif a.command == "cal":
            if a.buffer_ph is None:
                ap.error("cal needs the buffer pH, e.g. cal 7.00")
            time.sleep(5.0)          # the Uno needs a few seconds of readings after its reset
            return calibrate(ser, a.buffer_ph)
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
