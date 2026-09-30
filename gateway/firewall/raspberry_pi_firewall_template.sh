#!/usr/bin/env bash
# ChemShield Raspberry Pi firewall template.
# WARNING: Review before running. Wrong rules can disconnect your SSH session.

set -euo pipefail

OPERATOR_IFACE="wlan0"          # replace in lab
ACTUATOR_IFACE="eth1"          # replace in lab
ACTUATOR_IP="192.168.50.2"     # replace in lab
PLC_OR_UNO_PORT="502"          # replace if using TCP Modbus/bridge; not used for USB serial
GATEWAY_USER="chemshield"      # Linux user that runs the gateway service
SSH_PORT="22"
# The port the laptop HMI reaches the gateway on. The same variable starts the Pi station
# (see hmi/README.md):
#   .venv/bin/python -m hmi.station --ph-source uno --port "${CHEMSHIELD_HMI_PORT:-8000}"
HMI_PORT="${CHEMSHIELD_HMI_PORT:-8000}"

# 1) Disable IP forwarding so the Pi cannot act as a transparent router.
sudo sysctl -w net.ipv4.ip_forward=0
printf 'net.ipv4.ip_forward=0\n' | sudo tee /etc/sysctl.d/99-chemshield.conf >/dev/null

# 2) Default deny forwarding between interfaces.
sudo iptables -P FORWARD DROP
sudo iptables -F FORWARD
sudo iptables -A FORWARD -i "$OPERATOR_IFACE" -o "$ACTUATOR_IFACE" -j DROP
sudo iptables -A FORWARD -i "$ACTUATOR_IFACE" -o "$OPERATOR_IFACE" -j DROP

# 3) Inbound: loopback, replies to the Pi's own connections, SSH and the HMI from the
#    operator side. Everything else is dropped by the INPUT policy, set last so the
#    accept rules (including this SSH session) are in place first. Same for IPv6, which
#    also needs ICMPv6 for neighbour discovery.
#    If you reach the Pi as raspberrypi.local, use its IP address from now on: mDNS
#    (udp/5353) is dropped too.
for ipt in iptables ip6tables; do
  sudo "$ipt" -P INPUT ACCEPT
  sudo "$ipt" -F INPUT
  sudo "$ipt" -A INPUT -i lo -j ACCEPT
  sudo "$ipt" -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  if [ "$ipt" = ip6tables ]; then
    sudo "$ipt" -A INPUT -p ipv6-icmp -j ACCEPT
  fi
  sudo "$ipt" -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport "$SSH_PORT" -j ACCEPT
  sudo "$ipt" -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport "$HMI_PORT" -j ACCEPT
  sudo "$ipt" -P INPUT DROP
done

# 4) If the actuator uses TCP, allow only the gateway service user to reach it.
# For USB serial, use Linux device permissions instead of this TCP rule.
sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -p tcp --dport "$PLC_OR_UNO_PORT" -m owner --uid-owner "$GATEWAY_USER" -j ACCEPT
sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -j DROP

# 5) Show resulting settings for evidence screenshots.
sysctl net.ipv4.ip_forward
sudo iptables -S
sudo ip6tables -S INPUT
