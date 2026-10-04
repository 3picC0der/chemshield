#!/usr/bin/env bash
# Puts the C2 firewall on when the Pi boots (run by chemshield-firewall.service).
#
#   1. Right away: INPUT policy DROP and IP forwarding off. The rules name wlan0, so they are
#      valid before the Wi-Fi is up.
#   2. Once wlan0 is connected (the phone's hotspot, or the Pi's own ChemShield-Lab), again:
#      NetworkManager switches IP forwarding on when it starts a hotspot.
#   3. A few seconds later, and then for a while, again whenever forwarding has come back on.
#
# The rules are the same as `bash gateway/firewall/c2_network.sh fw`. They are not saved across a
# reboot, which is why this runs at every boot.
#
# Seconds, changeable for tests: CHEMSHIELD_FW_WAIT_S (wait for the Wi-Fi), CHEMSHIELD_FW_SETTLE_S,
# CHEMSHIELD_FW_WATCH_S (keep watching forwarding), CHEMSHIELD_FW_POLL_S. CHEMSHIELD_FW_CMD
# replaces the command that applies the firewall.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FW_CMD="${CHEMSHIELD_FW_CMD:-bash $HERE/../firewall/c2_network.sh fw}"
IFACE="${CHEMSHIELD_OPERATOR_IFACE:-wlan0}"
WAIT_S="${CHEMSHIELD_FW_WAIT_S:-120}"
SETTLE_S="${CHEMSHIELD_FW_SETTLE_S:-8}"
WATCH_S="${CHEMSHIELD_FW_WATCH_S:-120}"
POLL_S="${CHEMSHIELD_FW_POLL_S:-10}"

apply() {
  echo "firewall: applying ($1)"
  $FW_CMD || echo "firewall: the apply command failed (exit $?)" >&2
}

apply "at start"

waited=0
connected=no
while [ "$waited" -lt "$WAIT_S" ]; do
  if nmcli -t -f DEVICE,STATE device 2>/dev/null | grep -q "^$IFACE:connected"; then
    connected=yes
    echo "firewall: $IFACE connected after ${waited}s"
    break
  fi
  sleep 2
  waited=$((waited + 2))
done
[ "$connected" = yes ] || echo "firewall: $IFACE did not connect within ${WAIT_S}s; the rules stay on anyway"

apply "after waiting for the Wi-Fi"
sleep "$SETTLE_S"
apply "after it settled"

end=$((SECONDS + WATCH_S))
while [ "$SECONDS" -lt "$end" ]; do
  sleep "$POLL_S"
  if [ "$(sysctl -n net.ipv4.ip_forward 2>/dev/null || echo 1)" != "0" ]; then
    apply "IP forwarding came back on"
  fi
done
echo "firewall: done"
