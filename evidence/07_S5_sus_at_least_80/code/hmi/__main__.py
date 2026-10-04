"""Run the laptop HMI.

    .venv/bin/python -m hmi --station http://<pi-ip>:8000     the real rig (Pi on its Wi-Fi)
    .venv/bin/python -m hmi.demo                               no Pi: simulated tank on this laptop

Opens http://127.0.0.1:8080 in the browser. It only listens on this laptop.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

from hmi.common import HMI_PORT, STATION_PORT


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default=os.environ.get("CHEMSHIELD_STATION", f"http://127.0.0.1:{STATION_PORT}"),
                    help="the Pi station's address, e.g. http://10.42.0.1:8000")
    ap.add_argument("--port", type=int, default=HMI_PORT, help=f"laptop port (default {HMI_PORT})")
    ap.add_argument("--operator", default=os.environ.get("CHEMSHIELD_OPERATOR", "Operator"),
                    help="name shown in the title bar and written in the audit log")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    os.environ["CHEMSHIELD_STATION"] = a.station
    os.environ["CHEMSHIELD_OPERATOR"] = a.operator

    import uvicorn
    from hmi.app import KEY_SOURCE, app
    url = f"http://127.0.0.1:{a.port}"
    print(f"ChemShield HMI on {url} -> station {a.station} (key from {KEY_SOURCE})")
    if not a.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
