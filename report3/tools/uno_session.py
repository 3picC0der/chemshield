"""Hold the Uno's serial port for a whole test session and log every line.

Opening the port resets the Uno, and during a reset the drivers float on, so the port stays
open between tests instead of being reopened for each one. Commands come in through a FIFO:

    python uno_session.py --port /dev/cu.usbmodem14301 --log raw.log --fifo /path/to/uno.fifo
    echo "INFO" > /path/to/uno.fifo

Every line is written to the log as <UTC time>,<monotonic s>,<RX|TX>,<line>.
With --hb it sends HB every 0.5 s (chemshield_uno needs it; the bench sketch does not).
Stopping this program closes the port; on chemshield_uno the heartbeat then stops, so the
pump and the mixer stop within 2 s.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import select
import sys
import time


def stamp(log, direction: str, line: str) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")
    row = f"{now},{time.monotonic():.3f},{direction},{line}"
    log.write(row + "\n")
    log.flush()
    print(row, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--fifo", required=True)
    ap.add_argument("--hb", action="store_true", help="send HB every 0.5 s")
    a = ap.parse_args()

    import serial                                              # pyserial

    if not os.path.exists(a.fifo):
        os.mkfifo(a.fifo)
    fifo = os.open(a.fifo, os.O_RDWR | os.O_NONBLOCK)          # RDWR: stays open between writers
    ser = serial.Serial(a.port, 115200, timeout=0)
    buf_in = b""
    buf_cmd = b""
    next_hb = time.monotonic()
    with open(a.log, "a", encoding="utf-8") as log:
        stamp(log, "--", f"session start port={a.port} hb={a.hb}")
        try:
            while True:
                if a.hb and time.monotonic() >= next_hb:
                    ser.write(b"HB\n")                         # not logged: 2 lines a second of noise
                    next_hb += 0.5
                ready, _, _ = select.select([fifo], [], [], 0.02)
                if ready:
                    buf_cmd += os.read(fifo, 256)
                    while b"\n" in buf_cmd:
                        raw, buf_cmd = buf_cmd.split(b"\n", 1)
                        cmd = raw.decode("ascii", "replace").strip()
                        if cmd:
                            ser.write((cmd + "\n").encode("ascii"))
                            stamp(log, "TX", cmd)
                buf_in += ser.read(512)
                while b"\n" in buf_in:
                    raw, buf_in = buf_in.split(b"\n", 1)
                    line = raw.decode("ascii", "replace").strip()
                    if line:
                        stamp(log, "RX", line)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                ser.write(b"STOP\n")                           # a run must not outlive the logger
                ser.flush()
            finally:
                stamp(log, "--", "session end")
                ser.close()
                os.close(fifo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
