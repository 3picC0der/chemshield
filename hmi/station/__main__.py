"""Run the station (the Pi side).

On the Pi, with the Uno on USB and the real probe:
    .venv/bin/python -m hmi.station --ph-source uno

On the Pi or a laptop, with the simulated tank instead of the probe (labelled SIM everywhere):
    .venv/bin/python -m hmi.station --ph-source sim

Then open the HMI on the laptop:  .venv/bin/python -m hmi --station http://<pi-ip>:8000
Everything on one laptop, no Pi:  .venv/bin/python -m hmi.demo
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from hmi.common import ROOT, STATION_PORT, load_secret


def make_station(ph_source: str, *, port: str = "auto", start_ph: float = 7.0, auto_pump: bool = True,
                 dwell_s: float = 60.0, hand_speed_ml_s: float = 2.0, log_root: Path | None = None,
                 use_model_a: bool = True):
    from .core import Station
    from .links import SimLink, UnoLink

    secret, key_source = load_secret()
    if ph_source == "sim":
        link = SimLink(start_ph=start_ph, auto_pump=auto_pump)
    else:
        link = UnoLink(port=port)
    run = time.strftime("%Y%m%d-%H%M%S") + f"-{ph_source}"
    log_dir = (log_root or ROOT / "hmi" / "logs") / run
    station = Station(link, secret, log_dir=log_dir, dwell_s=dwell_s, hand_speed_ml_s=hand_speed_ml_s,
                      use_model_a=use_model_a, key_source=key_source)
    return station


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.station", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ph-source", choices=("uno", "sim"), default="uno",
                    help="uno = the real probe through the Uno; sim = the simulated tank")
    ap.add_argument("--serial-port", default="auto", help="Uno serial port (default: find it)")
    ap.add_argument("--host", default="0.0.0.0", help="address to listen on (default: all)")
    ap.add_argument("--port", type=int, default=STATION_PORT,
                    help=f"port (default {STATION_PORT}; the firewall opens CHEMSHIELD_HMI_PORT)")
    ap.add_argument("--start-ph", type=float, default=7.0,
                    help="simulated tank start pH (7.0 = the baking-soda liquid after the 1.8 mL "
                         "acid setup step; 0 = the liquid as made, about 8.3)")
    ap.add_argument("--no-auto-pump", action="store_true",
                    help="simulator: wait for 'Dose added' instead of adding doses by itself")
    ap.add_argument("--dwell", type=float, default=60.0,
                    help="seconds the pH must stay inside 6.0-8.5 before an event is closed")
    ap.add_argument("--hand-speed", type=float, default=2.0,
                    help="mL per second of a hand syringe push (sets how long the dose light stays on)")
    ap.add_argument("--no-model-a", action="store_true", help="debug only: run without Model A")
    a = ap.parse_args(argv)

    station = make_station(a.ph_source, port=a.serial_port, start_ph=a.start_ph,
                           auto_pump=not a.no_auto_pump, dwell_s=a.dwell,
                           hand_speed_ml_s=a.hand_speed, use_model_a=not a.no_model_a)
    print(f"ChemShield station: pH source {station.link.kind}, chemistry {station.chem_source}, "
          f"key from {station.key_source}")
    print(f"logs: {station.log_dir}")
    if station.model_a_error:
        print(f"WARNING Model A did not load: {station.model_a_error}", file=sys.stderr)
    if "demo key" in station.key_source:
        print("WARNING using the built-in demo key. Run `python -m hmi.keygen` and copy "
              "hmi/secrets/operator.key to the Pi before the PPR.", file=sys.stderr)

    import uvicorn
    from .server import build_app
    uvicorn.run(build_app(station), host=a.host, port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
