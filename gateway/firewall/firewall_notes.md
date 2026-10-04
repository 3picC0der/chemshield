# ChemShield Raspberry Pi firewall / network notes

Goal: support **C2** by making the Raspberry Pi ChemShield gateway the only authorized path to the actuator side.

## Intended network

- Operator/HMI side reaches only the Raspberry Pi gateway.
- PPR rig: the actuator side is the Uno on the Pi's USB port (serial), so it has no
  network address at all. Serial access is controlled by Linux permissions and the station.
- A networked actuator (later) would use a small private link, for example:
  - Raspberry Pi actuator-side interface: `192.168.50.1/30`
  - PLC/Uno bridge endpoint: `192.168.50.2/30`
- IP forwarding is disabled.
- The actuator network has no default route back to the operator network.
- Direct actuator writes are blocked.
- Inbound to the Pi (IPv4 and IPv6): only loopback, replies to the Pi's own connections,
  SSH (22) and the HMI (`HMI_PORT`, default 8000) from the operator interface, plus DHCP
  (UDP 67) so a laptop joining the hotspot gets an address. The INPUT policy is DROP, so
  every other port is closed.

## Before running it on the Pi

- Start the hotspot first, then run the script. NetworkManager's hotspot ("shared" mode)
  turns IP forwarding back on when it starts, so run the script again after every reboot
  or hotspot restart, and check `sysctl net.ipv4.ip_forward` shows `0`.
- `CHEMSHIELD_OPERATOR_IFACE` (default `wlan0`) if the hotspot is on another interface.
  New SSH sessions are accepted only on that interface.
- `CHEMSHIELD_HMI_PORT` (environment variable, default 8000) if the HMI moves. The script
  and the station's start command read the same variable:
  `.venv/bin/python -m hmi.station --ph-source uno --port "${CHEMSHIELD_HMI_PORT:-8000}"`.
  The station is plain HTTP on that port; nothing listens on 443.
- `CHEMSHIELD_ACTUATOR_LINK=tcp` only for a networked actuator. Then also set
  `ACTUATOR_IFACE`, `ACTUATOR_IP`, `PLC_OR_UNO_PORT` and an existing `GATEWAY_USER`. With
  the default (`usb`) that rule is skipped.

## C2 evidence collection

Use the live collector from the **separate operator laptop** after the station and C2
network are up:

```bash
.venv/bin/python -m hmi.c2_evidence --pi-ip 10.42.0.1 --ssh-user <real-pi-user>
```

It records the full TCP nmap scan, `ip_forward`, effective SSH password-auth setting,
the unsigned/wrong-key HTTP 401 rejections, the post-test station state, and the
password-only SSH refusal. It then generates the filled ICS-AT-01 test sheet under
`evidence/ICS-AT-01/live_run/`.

Also keep a short video showing the Uno light stays off while the unsigned and wrong-key
requests are rejected. That physical observation complements the machine-readable
`pending = null` / actuator-state evidence.
