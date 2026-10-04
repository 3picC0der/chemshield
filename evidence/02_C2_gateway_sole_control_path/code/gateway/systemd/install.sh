#!/usr/bin/env bash
# Start the ChemShield firewall and station by themselves when the Pi boots.
#
#   sudo bash gateway/systemd/install.sh            install (or update) both services and start them
#   sudo bash gateway/systemd/install.sh remove     stop and remove them (the firewall rules stay until a reboot)
#   bash gateway/systemd/install.sh status          what is enabled, running and listening
#
# Run it on the Pi, from the repository folder. It fills in the repository path and the user
# (the one who ran sudo) in the two unit files and puts them in /etc/systemd/system.
#
# Dry run (writes the two unit files under a folder and touches nothing else):
#   CHEMSHIELD_ROOT=/tmp/x CHEMSHIELD_REPO=/path/to/repo CHEMSHIELD_USER=name bash gateway/systemd/install.sh install
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="${CHEMSHIELD_REPO:-$(cd "$HERE/../.." && pwd)}"
ROOT="${CHEMSHIELD_ROOT:-}"
UNIT_DIR="$ROOT/etc/systemd/system"
SVC_USER="${CHEMSHIELD_USER:-${SUDO_USER:-$(stat -c %U "$REPO" 2>/dev/null || stat -f %Su "$REPO")}}"
UNITS=(chemshield-firewall.service chemshield-station.service)

need_root() {
  if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then
    echo "run this with sudo: sudo bash gateway/systemd/install.sh $1" >&2
    exit 1
  fi
}

render() {
  sed -e "s#@REPO@#$REPO#g" -e "s#@USER@#$SVC_USER#g" "$HERE/$1.in" > "$UNIT_DIR/$1"
  echo "wrote $UNIT_DIR/$1"
}

show_status() {
  local u ipt=iptables
  [ "$(id -u)" -eq 0 ] || ipt="sudo -n iptables"
  for u in "${UNITS[@]}"; do
    printf '%-30s enabled: %-9s active: %s\n' "$u" "$(systemctl is-enabled "$u" 2>&1 || true)" "$(systemctl is-active "$u" 2>&1 || true)"
  done
  echo "IP forwarding:  $(sysctl -n net.ipv4.ip_forward)  (must be 0)"
  echo "INPUT policy:   $($ipt -S INPUT 2>/dev/null | head -1 || true)  (must be -P INPUT DROP)"
  echo "Listening on:"
  ss -ltn 2>/dev/null | grep -E ':(22|8000)[[:space:]]' || echo "  nothing on 22 or 8000 yet"
  echo "Station log (journalctl -u chemshield-station -f to follow it):"
  journalctl -u chemshield-station -n 5 --no-pager 2>/dev/null || true
}

case "${1:-install}" in
  install)
    need_root install
    [ -x "$REPO/.venv/bin/python" ] || { echo "no $REPO/.venv/bin/python: set the project up first (evidence/SETUP.md, A4)" >&2; exit 1; }
    [ -f "$REPO/hmi/secrets/operator.key" ] || echo "WARNING: $REPO/hmi/secrets/operator.key is missing, so the station will not start until it is copied there (evidence/SETUP.md, A5)" >&2
    [ -n "$ROOT" ] || id "$SVC_USER" >/dev/null
    mkdir -p "$UNIT_DIR"
    for u in "${UNITS[@]}"; do render "$u"; done
    if [ -n "$ROOT" ]; then echo "dry run: nothing else was touched"; exit 0; fi
    if command -v systemd-analyze >/dev/null 2>&1; then
      systemd-analyze verify "$UNIT_DIR/chemshield-firewall.service" "$UNIT_DIR/chemshield-station.service" \
        || { echo "systemd does not accept the unit files (see above); nothing was enabled" >&2; exit 1; }
    fi
    systemctl daemon-reload
    pkill -f '[h]mi.station' || true          # a station started by hand would hold port 8000
    systemctl enable chemshield-firewall.service chemshield-station.service
    systemctl restart --no-block chemshield-firewall.service
    systemctl restart chemshield-station.service
    sleep 12                                  # the station takes about 10 s to load Model A
    show_status
    ;;
  remove)
    need_root remove
    systemctl disable --now chemshield-station.service chemshield-firewall.service 2>/dev/null || true
    rm -f "$UNIT_DIR/chemshield-station.service" "$UNIT_DIR/chemshield-firewall.service"
    [ -n "$ROOT" ] || systemctl daemon-reload
    echo "removed. The firewall rules stay until the next reboot. Start the station by hand as in evidence/SETUP.md, D2."
    ;;
  status)
    show_status
    ;;
  *)
    echo "usage: $0 [install | remove | status]" >&2
    exit 2
    ;;
esac
