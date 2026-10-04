#!/usr/bin/env bash
# ChemShield Raspberry Pi firewall template.
# WARNING: Review before running. Wrong rules can disconnect your SSH session.
#
# Run it on the Pi only (never on a laptop), after the Pi's Wi-Fi hotspot is up:
#   bash gateway/firewall/raspberry_pi_firewall_template.sh
# Run it again after every reboot and every time the hotspot restarts: NetworkManager's
# hotspot ("shared" mode) switches IP forwarding back on when it starts, and these rules
# are not saved across a reboot.

set -euo pipefail

OPERATOR_IFACE="${CHEMSHIELD_OPERATOR_IFACE:-wlan0}"   # the Pi's hotspot interface
# How the Pi reaches the actuator side. "usb" = the PPR rig (the Uno on USB serial, where
# Linux device permissions guard the port, not the firewall). "tcp" = a networked PLC/bridge.
ACTUATOR_LINK="${CHEMSHIELD_ACTUATOR_LINK:-usb}"
ACTUATOR_IFACE="eth1"          # tcp only: replace in lab
ACTUATOR_IP="192.168.50.2"     # tcp only: replace in lab
PLC_OR_UNO_PORT="502"          # tcp only: Modbus/bridge port
GATEWAY_USER="chemshield"      # tcp only: Linux user that runs the gateway service (must exist)
SSH_PORT="22"
# The port the laptop HMI reaches the gateway on. The same variable starts the Pi station
# (see hmi/README.md):
#   .venv/bin/python -m hmi.station --ph-source uno --port "${CHEMSHIELD_HMI_PORT:-8000}"
HMI_PORT="${CHEMSHIELD_HMI_PORT:-8000}"

# 1) Disable IP forwarding so the Pi cannot act as a transparent router.
sudo sysctl -w net.ipv4.ip_forward=0
printf 'net.ipv4.ip_forward=0\n' | sudo tee /etc/sysctl.d/99-chemshield.conf >/dev/null

# 2) Default deny forwarding between interfaces (IPv4 and IPv6).
for ipt in iptables ip6tables; do
  sudo "$ipt" -P FORWARD DROP
  sudo "$ipt" -F FORWARD
done
sudo iptables -A FORWARD -i "$OPERATOR_IFACE" -o "$ACTUATOR_IFACE" -j DROP
sudo iptables -A FORWARD -i "$ACTUATOR_IFACE" -o "$OPERATOR_IFACE" -j DROP

# 3) Inbound: loopback, replies to the Pi's own connections, SSH and the HMI from the
#    operator side. Everything else is dropped by the INPUT policy, set last so the
#    accept rules (including this SSH session) are in place first. Same for IPv6, which
#    also needs ICMPv6 for neighbour discovery.
#    DHCP (UDP 67) stays open on the hotspot so a laptop that joins it still gets an
#    address from the Pi. It is UDP, so a TCP nmap scan shows only SSH and the HMI port.
#    If you reach the Pi as raspberrypi.local, use its IP address from now on: mDNS
#    (udp/5353) is dropped too.
for ipt in iptables ip6tables; do
  sudo "$ipt" -P INPUT ACCEPT
  sudo "$ipt" -F INPUT
  sudo "$ipt" -A INPUT -i lo -j ACCEPT
  sudo "$ipt" -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  if [ "$ipt" = ip6tables ]; then
    sudo "$ipt" -A INPUT -p ipv6-icmp -j ACCEPT
  else
    sudo "$ipt" -A INPUT -i "$OPERATOR_IFACE" -p udp --dport 67 -j ACCEPT
  fi
  sudo "$ipt" -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport "$SSH_PORT" -j ACCEPT
  sudo "$ipt" -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport "$HMI_PORT" -j ACCEPT
  sudo "$ipt" -P INPUT DROP
done

# 4) A TCP actuator link only: allow just the gateway service user to reach it.
#    The PPR rig's Uno is on USB serial, so this is skipped there (the user above
#    would not exist, and iptables would stop the script before the evidence below).
if [ "$ACTUATOR_LINK" = "tcp" ]; then
  sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -p tcp --dport "$PLC_OR_UNO_PORT" -m owner --uid-owner "$GATEWAY_USER" -j ACCEPT
  sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -j DROP
else
  echo "Actuator link: USB serial. No TCP actuator rule; the serial port is guarded by Linux permissions."
fi

# 5) Show resulting settings for evidence screenshots.
sysctl net.ipv4.ip_forward
sudo iptables -S
sudo ip6tables -S INPUT
