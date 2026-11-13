#!/usr/bin/env bash
# FPR booth helper. Run it on the Mac, from this folder (~/Development/Personal/chemshield-fpr).
#
#   bash fpr.sh start      firewall + station on the Pi, sets the Pi's clock, opens the HMI
#   bash fpr.sh panel      stops the station and opens the Uno panel (prime / check pumps, pH)
#   bash fpr.sh attack     the five network attacks against the gateway (add --only replay etc.)
#   bash fpr.sh status     what is running and what the station sees
#   bash fpr.sh stop       stops the HMI and the station
#
# The Pi is 10.42.0.1 on its own Wi-Fi (ChemShield-Lab), the booth setup. When it is on the
# phone hotspot instead:   PI=172.20.10.2 bash fpr.sh start
set -euo pipefail
cd "$(dirname "$0")"
PI="${PI:-10.42.0.1}"
KEY="${KEY:-$HOME/.ssh/id_ed25519_second}"
PY=../chemshield/.venv/bin/python
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes -o ConnectTimeout=8 -o ServerAliveInterval=15 "chemshield@$PI")

stop_hmi() { pkill -if "m hmi --station" 2>/dev/null || true; }
stop_pi() { "${SSH[@]}" 'pkill -f "[h]mi[.]station"; pkill -f "[b]ench_panel[.]py"; sleep 1; true'; }

case "${1:-}" in
  start)
    stop_hmi
    stop_pi
    if [ "$PI" = "10.42.0.1" ]; then
      echo "Firewall on (C2)..."
      "${SSH[@]}" 'cd ~/chemshield && sudo bash gateway/firewall/c2_network.sh fw >/dev/null && echo "  firewall: on"'
    fi
    echo "Starting the station on the Pi..."
    "${SSH[@]}" '(cd ~/chemshield && exec setsid .venv/bin/python -W ignore -m hmi.station --ph-source uno) > ~/station.log 2>&1 < /dev/null & sleep 9; head -2 ~/station.log'
    echo "Setting the Pi's clock from this Mac..."
    $PY -m hmi.clock_sync --pi "chemshield@$PI" --station "http://$PI:8000" \
      --ssh-option="-i$KEY" --ssh-option=-oIdentitiesOnly=yes --ssh-option=-oBatchMode=yes
    nohup $PY -m hmi --station "http://$PI:8000" --operator "${OPERATOR:-Belal}" > /tmp/chemshield_hmi.log 2>&1 &
    sleep 4
    echo "HMI: http://127.0.0.1:8080 (it opens in the browser by itself)"
    ;;
  panel)
    stop_hmi
    stop_pi
    echo "Station stopped. Opening the Uno panel (Ctrl+C here closes it; then: bash fpr.sh start)"
    PI="$PI" KEY="$KEY" exec bash firmware/uno/panel_on_pi.sh
    ;;
  attack)
    shift
    exec $PY -m hmi.attack_demo --station "http://$PI:8000" "$@"
    ;;
  status)
    echo "Pi $PI:"
    "${SSH[@]}" 'pgrep -af "[h]mi[.]station|[b]ench_panel" | cut -c1-90 || echo "  nothing running"; cd ~/chemshield && sudo bash gateway/pi_fan.sh status 2>/dev/null | head -1'
    curl -s -m 4 "http://$PI:8000/api/state" | $PY -c 'import sys,json; s=json.load(sys.stdin); print("  station:", s["mode"], "| pH", s["ph"]["mean3"], "| Uno link", "up" if s["link"]["alive"] else "DOWN")' \
      || echo "  station: not answering"
    curl -s -m 2 -o /dev/null http://127.0.0.1:8080/ && echo "HMI: running on http://127.0.0.1:8080" || echo "HMI: not running"
    ;;
  stop)
    stop_hmi
    stop_pi
    echo "HMI and station stopped."
    ;;
  *)
    sed -n '2,12p' "$0"
    exit 2
    ;;
esac
