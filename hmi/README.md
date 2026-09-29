# HMI — Khalid build

This is a lightweight web HMI for the ChemShield demo.

## What it shows

- pH value and system state.
- Dose request form.
- Gateway ACCEPT/REJECT decision and reason code.
- Model A label, score, and latency.
- Attack counters / command counters.
- Audit log table.
- HALT and ACK buttons.

## Run

From the repository root:

```bash
uvicorn hmi.app:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

On the Raspberry Pi, serve it on the port the firewall opens
(`gateway/firewall/raspberry_pi_firewall_template.sh` reads the same variable):

```bash
uvicorn hmi.app:app --host 0.0.0.0 --port "${CHEMSHIELD_HMI_PORT:-8000}"
```

This HMI uses the gateway package in `gateway/src`. It is a demo HMI and can be connected later to the final simulator/Model A/Uno bridge.

## Design

The design is specified in **`DESIGN.md`** (Hattan, 28 Sep) with a static layout
reference in `wireframe.html`. Section 1 of DESIGN.md lists the five elements the test
sheets read off this screen, and section 7 is what Khalid needs back.
