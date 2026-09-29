# ChemShield Raspberry Pi firewall / network notes

Goal: support **C2** by making the Raspberry Pi ChemShield gateway the only authorized path to the actuator side.

## Intended network

- Operator/HMI side reaches only the Raspberry Pi gateway.
- Raspberry Pi has a private actuator-side interface.
- Actuator side uses a small private link, for example:
  - Raspberry Pi actuator-side interface: `192.168.50.1/30`
  - PLC/Uno bridge endpoint: `192.168.50.2/30`
- IP forwarding is disabled.
- The actuator network has no default route back to the operator network.
- Direct actuator writes are blocked.
- Inbound to the Pi (IPv4 and IPv6): only loopback, replies to the Pi's own connections,
  SSH (22) and the HMI (`HMI_PORT`, default 8000) from the operator interface. The INPUT
  policy is DROP, so every other port is closed.

## Replace before lab use

- `OPERATOR_IFACE` with the real Wi-Fi/hotspot interface.
- `ACTUATOR_IFACE` with the real private interface.
- `ACTUATOR_IP` with the real PLC/Uno bridge IP.
- `CHEMSHIELD_HMI_PORT` (environment variable, default 8000) if the HMI moves. The script
  and the HMI's start command read the same variable:
  `uvicorn hmi.app:app --host 0.0.0.0 --port "${CHEMSHIELD_HMI_PORT:-8000}"`.
  The HMI is plain HTTP on that port; nothing listens on 443.
- `PLC_OR_UNO_PORT` with the real port if using TCP. For serial USB, the firewall evidence is about network isolation, while serial access is controlled by Linux permissions and the gateway service.

## Evidence to collect later

- Screenshot of `sysctl net.ipv4.ip_forward` showing `0`.
- Firewall rule list.
- `nmap` from a separate laptop showing only 22 and the HMI port open (every other port
  filtered).
- Failed direct actuator connection attempt.
