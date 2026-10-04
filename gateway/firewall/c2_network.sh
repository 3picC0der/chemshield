#!/usr/bin/env bash
# C2 network mode for the PPR rig (ICS-AT-01): the Pi hosts its own Wi-Fi with no internet,
# and the firewall leaves only SSH (22) and the station (8000) open.
#
#   sudo bash gateway/firewall/c2_network.sh on <wifi-password>   Pi's own Wi-Fi + firewall
#   sudo bash gateway/firewall/c2_network.sh fw                   firewall only (run again after a reboot)
#   sudo bash gateway/firewall/c2_network.sh off                  firewall open, back to the phone hotspot
#   bash gateway/firewall/c2_network.sh status                    what is on now
#
# After "on" the Pi's Wi-Fi comes up by itself whenever the phone hotspot is not around
# (its profile has the lowest priority), but the firewall rules are lost at every reboot:
# run "fw" once the Wi-Fi is up. NetworkManager turns IP forwarding back on when it
# starts the Wi-Fi, so "fw" is what puts it back to 0.
#
# Start the station first, so port 8000 shows as open. Run "on" from an SSH session with
# nohup, because the session drops when the Wi-Fi switches:
#   nohup sudo bash gateway/firewall/c2_network.sh on <wifi-password> >/dev/null 2>&1 &
# Then join the laptop to the "ChemShield-Lab" Wi-Fi; the Pi is 10.42.0.1. The evidence
# (IP forwarding, rule list, addresses) is appended to ~/c2_evidence.txt.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SSID="${CHEMSHIELD_SSID:-ChemShield-Lab}"
AP_CON="chemshield-ap"
USER_HOME="$(getent passwd "${SUDO_USER:-$USER}" | cut -d: -f6)"
LOG="${CHEMSHIELD_C2_LOG:-$USER_HOME/c2_evidence.txt}"

case "${1:-}" in
  on)
    PASS="${2:?give the Wi-Fi password (8 characters or more)}"
    {
      echo "== $(date -u '+%Y-%m-%d %H:%M:%S UTC') C2 network on"
      nmcli connection delete "$AP_CON" >/dev/null 2>&1 || true
      nmcli device wifi hotspot ifname wlan0 con-name "$AP_CON" ssid "$SSID" password "$PASS"
      # the phone hotspot wins whenever it is in range; this one comes up when it is not
      nmcli connection modify "$AP_CON" connection.autoconnect yes connection.autoconnect-priority -100
      nmcli -t -f NAME,TYPE connection show | awk -F: -v ap="$AP_CON" '$2 ~ /wireless/ && $1 != ap {print $1}' |
        while read -r con; do nmcli connection modify "$con" connection.autoconnect-priority 10 || true; done
      sleep 4
      CHEMSHIELD_OPERATOR_IFACE=wlan0 bash "$HERE/raspberry_pi_firewall_template.sh"
      sleep 8          # NetworkManager can still be starting the Wi-Fi; apply it again to be sure
      CHEMSHIELD_OPERATOR_IFACE=wlan0 bash "$HERE/raspberry_pi_firewall_template.sh"
      ip -4 -brief address show wlan0
    } >> "$LOG" 2>&1
    ;;
  fw)
    {
      echo "== $(date -u '+%Y-%m-%d %H:%M:%S UTC') firewall only"
      CHEMSHIELD_OPERATOR_IFACE=wlan0 bash "$HERE/raspberry_pi_firewall_template.sh"
    } >> "$LOG" 2>&1
    sysctl net.ipv4.ip_forward
    ;;
  off)
    {
      echo "== $(date -u '+%Y-%m-%d %H:%M:%S UTC') C2 network off"
      for ipt in iptables ip6tables; do
        "$ipt" -P INPUT ACCEPT
        "$ipt" -F INPUT
      done
      nmcli connection down "$AP_CON" || true
      PHONE="$(nmcli -t -f NAME,TYPE connection show | awk -F: -v ap="$AP_CON" '$2 ~ /wireless/ && $1 != ap {print $1; exit}')"
      if [ -n "$PHONE" ]; then
        nmcli connection up "$PHONE" || echo "turn the phone hotspot on, then: sudo nmcli connection up \"$PHONE\""
      fi
    } >> "$LOG" 2>&1
    ;;
  status)
    nmcli -t -f DEVICE,STATE,CONNECTION device status | grep '^wlan0' || true
    sysctl net.ipv4.ip_forward
    sudo iptables -S INPUT
    ;;
  *)
    echo "usage: $0 on <wifi-password> | fw | off | status" >&2
    exit 2
    ;;
esac
