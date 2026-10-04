# ICS-AT-01 — C2 gateway-only path

**Constraint C2:** All actuator commands must pass through the ChemShield gateway as the
sole authorized control path during testing and demonstration.

## Acceptance criteria

The live run passes only when all of the following are measured on the real Raspberry Pi
rig:

1. The Pi hosts `ChemShield-Lab` with the C2 firewall enabled.
2. A full TCP scan from the separate operator laptop exposes **only 22/tcp and 8000/tcp**.
3. `net.ipv4.ip_forward = 0` on the Pi.
4. The HMI's **unsigned** and **wrong-key** dose tests are both rejected with gateway
   **HTTP 401** and do not create an accepted/pending dose.
5. Password login is disabled in the Pi's effective SSH configuration and a password-only
   login attempt to the **real existing Pi account** is refused.
6. The Uno remains reachable only over the Pi's USB serial link; during the bypass tests
   no bad command creates a pending actuator command and the Uno light stays off.

This is the same pass condition used by the PPR evidence sheet. The PPR plan previously
used `chemshield@10.42.0.1` for the password test. That can give a false-looking success
when the account does not exist, so the collector tests the actual Pi account instead.

## Run C2

From the repo on the Pi, start the station and then enable the isolated C2 network:

```bash
.venv/bin/python -m hmi.station --ph-source uno --port 8000
# In another Pi shell:
nohup sudo bash gateway/firewall/c2_network.sh on '<wifi-password>' >/dev/null 2>&1 &
```

Join the operator laptop to **ChemShield-Lab**. Start the laptop HMI:

```bash
.venv/bin/python -m hmi --station http://10.42.0.1:8000 --operator "Khalid"
```

Then run the evidence collector on the laptop. Use the real Pi SSH username (the same
account that works with `hmi.clock_sync`):

```bash
.venv/bin/python -m hmi.c2_evidence --pi-ip 10.42.0.1 --ssh-user belal
```

For the live booth demo, `--quick` uses the top 1000 TCP ports. For the signed test
sheet, run without `--quick` so all TCP ports are scanned.

## Generated evidence

A successful run writes:

- `live_run/ICS-AT-01_test_sheet.md` — automatically filled test sheet and PASS/FAIL.
- `live_run/ICS-AT-01_summary.json` — machine-readable values and every scored check.
- `live_run/ICS-AT-01_raw.txt` — raw nmap output, Pi network/SSH settings and API replies.

Do **not** mark C2 PASS manually. Commit the generated files only after the real rig run
returns PASS.

## Required visual evidence

Keep the generated text files and also capture:

- screenshot: full nmap result showing only 22 and 8000;
- screenshot: `net.ipv4.ip_forward = 0` and Pi firewall evidence;
- screenshot or short clip: unsigned request → HTTP 401;
- screenshot or short clip: wrong-key request → HTTP 401;
- screenshot or short clip: password-only SSH refused for the real Pi account;
- one continuous video showing the Uno light remains off during the bypass attempts.

The automated collector proves the machine-observable checks; the video is the reviewer-
friendly evidence for the physical light.
