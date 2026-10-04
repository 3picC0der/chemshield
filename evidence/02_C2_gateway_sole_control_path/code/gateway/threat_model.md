# ChemShield cybersecurity threat model — Khalid

## Assets

- pH neutralization tank and dosing pumps.
- Raspberry Pi ChemShield gateway.
- Uno/PLC actuator interface.
- Operator HMI/API.
- Model A decision interface.
- Audit log and recovery event records.

## Trust boundaries

1. Operator/HMI network → Raspberry Pi gateway.
2. Raspberry Pi gateway → actuator-side network or USB serial.
3. Gateway application → Uno/PLC/pump command interface.
4. Gateway → Model A decision interface.

## Main threats and controls

| Threat | Risk | ChemShield control | Requirement supported |
|---|---|---|---|
| Direct actuator command | Pump command bypasses security checks | firewall isolation, no IP forwarding, actuator accepts only gateway path | C2 |
| Replayed command | Old valid command sent again | nonce, command ID, sequence memory, audit memory after reboot | S3 |
| Stale command | Command arrives too late for current process state | UTC timestamp freshness window ±2 s | S3 |
| Modified command | Attacker changes volume/channel after signing | HMAC-SHA256 over canonical command body | C2/S3 |
| Wrong role/session | Unauthorized user sends dosing command | active session ID and allowed role checks | C2 |
| Oversize dose | Command exceeds safe process limit | ≤20 mL and ≤50 mmol gateway checks | S2/C3 support |
| Burst dosing | Command arrives during mixing lockout | gateway state lockout check | S2 support |
| Bad context | Dose looks syntactically valid but unsafe for process | Model A interface returns label/score | S4 support |
| Gateway or heartbeat failure | System might continue dosing while blind | SAFE_HOLD and manual acknowledgement | INT-S1/support |
| Audit tampering | Evidence cannot be trusted | hash-chained audit log | C2/S3 evidence support |

## Note

The threat model alone is not enough as final evidence. It supports the tested code, firewall configuration, attack script, and HMI counters.
