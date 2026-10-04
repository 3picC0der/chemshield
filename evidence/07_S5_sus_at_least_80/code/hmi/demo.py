"""Everything on one laptop, no Pi and no tank: the SUS study and rehearsals.

    .venv/bin/python -m hmi.demo

Starts the station with the SIMULATED tank on 127.0.0.1:8000 and the HMI on
127.0.0.1:8080, then opens the browser. The screen carries a purple SIMULATED pH band
the whole time. Stop with Ctrl+C.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import webbrowser

from hmi.common import HMI_PORT, STATION_PORT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.demo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start-ph", type=float, default=7.0)
    ap.add_argument("--no-auto-pump", action="store_true",
                    help="wait for 'Dose added' clicks instead of adding doses by itself")
    ap.add_argument("--dwell", type=float, default=60.0)
    ap.add_argument("--operator", default="Operator")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--station-port", type=int, default=STATION_PORT)
    ap.add_argument("--port", type=int, default=HMI_PORT)
    a = ap.parse_args(argv)

    import uvicorn
    from hmi.station.__main__ import make_station
    from hmi.station.server import build_app

    station = make_station("sim", start_ph=a.start_ph, auto_pump=not a.no_auto_pump, dwell_s=a.dwell)
    st_server = uvicorn.Server(uvicorn.Config(build_app(station), host="127.0.0.1",
                                              port=a.station_port, log_level="warning"))
    threading.Thread(target=st_server.run, daemon=True, name="station").start()
    for _ in range(100):
        if st_server.started:
            break
        time.sleep(0.1)
    print(f"station (SIMULATED tank) on http://127.0.0.1:{a.station_port}; logs in {station.log_dir}")

    os.environ["CHEMSHIELD_STATION"] = f"http://127.0.0.1:{a.station_port}"
    os.environ["CHEMSHIELD_OPERATOR"] = a.operator
    from hmi.app import app
    url = f"http://127.0.0.1:{a.port}"
    print(f"HMI on {url}  (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
