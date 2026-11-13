#!/usr/bin/env bash
# Run on the Mac: start the Uno panel on the Pi and open it in the Mac's browser.
# The Uno is on the Pi's USB; the panel listens only on the Pi itself, so the page reaches
# the Mac through an SSH tunnel (port 22 is open in the C2 firewall). The station must be
# stopped first, because only one program can hold the Uno's serial port.
#
#   bash firmware/uno/panel_on_pi.sh                      Pi on the phone hotspot (172.20.10.2)
#   PI=10.42.0.1 bash firmware/uno/panel_on_pi.sh         Pi on its own ChemShield-Lab Wi-Fi
#
# Ctrl+C here quits the panel (and stops any pump it is running).
set -euo pipefail
PI="${PI:-172.20.10.2}"
KEY="${KEY:-$HOME/.ssh/id_ed25519_second}"
PORT="${PANEL_PORT:-8090}"

if ssh -i "$KEY" -o ConnectTimeout=8 "chemshield@$PI" 'pgrep -f "hmi.station" >/dev/null'; then
  echo "The station is running on the Pi and holds the Uno's port. Stop it first, then run this again."
  exit 1
fi
( sleep 5; open "http://127.0.0.1:$PORT" ) &
exec ssh -t -i "$KEY" -L "$PORT:127.0.0.1:$PORT" "chemshield@$PI" \
  "cd ~/chemshield && .venv/bin/python firmware/uno/bench_panel.py --port /dev/ttyACM0 --http $PORT"
