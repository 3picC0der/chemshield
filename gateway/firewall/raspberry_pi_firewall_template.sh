#!/usr/bin/env bash
# ChemShield Raspberry Pi firewall template.
# WARNING: Review before running. Wrong rules can disconnect your SSH session.

set -euo pipefail

OPERATOR_IFACE="wlan0"          # replace in lab
ACTUATOR_IFACE="eth1"          # replace in lab
ACTUATOR_IP="192.168.50.2"     # replace in lab
PLC_OR_UNO_PORT="502"          # replace if using TCP Modbus/bridge; not used for USB serial
GATEWAY_USER="chemshield"      # Linux user that runs the gateway service

# 1) Disable IP forwarding so the Pi cannot act as a transparent router.
sudo sysctl -w net.ipv4.ip_forward=0
printf 'net.ipv4.ip_forward=0\n' | sudo tee /etc/sysctl.d/99-chemshield.conf >/dev/null

# 2) Default deny forwarding between interfaces.
sudo iptables -P FORWARD DROP
sudo iptables -F FORWARD
sudo iptables -A FORWARD -i "$OPERATOR_IFACE" -o "$ACTUATOR_IFACE" -j DROP
sudo iptables -A FORWARD -i "$ACTUATOR_IFACE" -o "$OPERATOR_IFACE" -j DROP

# 3) Allow inbound SSH and HTTPS to the gateway only.
sudo iptables -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport 22 -j ACCEPT
sudo iptables -A INPUT -i "$OPERATOR_IFACE" -p tcp --dport 443 -j ACCEPT

# 4) If the actuator uses TCP, allow only the gateway service user to reach it.
# For USB serial, use Linux device permissions instead of this TCP rule.
sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -p tcp --dport "$PLC_OR_UNO_PORT" -m owner --uid-owner "$GATEWAY_USER" -j ACCEPT
sudo iptables -A OUTPUT -o "$ACTUATOR_IFACE" -d "$ACTUATOR_IP" -j DROP

# 5) Show resulting settings for evidence screenshots.
sysctl net.ipv4.ip_forward
sudo iptables -S
