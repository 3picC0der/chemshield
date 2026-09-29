# Gateway, firewall and network — Khalid

This folder contains Khalid's ChemShield ICS implementation.

## What it proves

- **C2:** every actuator command must pass through the ChemShield gateway.
- **S3:** replayed and stale commands are rejected.
- **S2 support:** dose volume and mixing-time rules are enforced by software.
- **C3 support:** recovery-event mmol limit is checked before forwarding.
- **S4 support:** the gateway calls a Model A decision interface.
- **INT-S1 support:** the gateway records recovery-mode timing.

## Main command path

```text
HMI / Operator / MILP
        |
        v
ChemShield Gateway
(schema -> role/session -> HMAC -> timestamp -> nonce -> sequence -> state -> dose limits -> Model A)
        |
        v
Uno / PLC / Pump interface
```

A direct command to the actuator simulator is rejected. In the lab, the same idea is enforced by the Raspberry Pi firewall and by disabling IP forwarding.

## Run

From the repository root:

```bash
python gateway/run_all.py
```

Readable sample for screenshots:

```bash
python gateway/sample_view.py
```

Attack script only:

```bash
python gateway/attack_script.py --per-category 100
```

## Important

This code uses synthetic input commands for repeatable tests. The validation logic, HMAC calculation, timestamp freshness check, nonce/sequence replay protection, dose-limit check, gateway-only actuator path, audit hash chain, and timing measurements are executable logic.
