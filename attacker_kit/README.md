# ChemShield · Outsider attacker kit

A second laptop plays a **third-party attacker** who has joined the plant Wi-Fi and captured a few real dose commands off the network. It has **no ChemShield software and no keys**, only Python 3 and this folder.

## A. On the ChemShield Mac (Belal), after `bash fpr.sh start`

1. Make the "captured traffic". These are 5 real dose commands (1 mL of the weak 0.005 M base) sent through the gateway, the way the attacker would sniff them. At most one is dosed.
   ```bash
   ../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode valid --n 5 --save attacker_kit/captured.jsonl
   ```
2. Send the whole `attacker_kit` folder to the friend (AirDrop, or zip it and use a USB stick). It must contain `outsider_attack.py` and `captured.jsonl`.

## B. On the attacker's laptop (friend)

1. Join the Wi-Fi **ChemShield-Lab**. Nothing else needs to be installed except Python 3:
   - Mac: `python3 --version` in Terminal. If it asks to install the developer tools, accept.
   - Windows: install Python 3 from python.org, then use `py` instead of `python3`.
2. In a terminal, go into the `attacker_kit` folder and run:
   ```bash
   python3 outsider_attack.py --station http://10.42.0.1:8000
   ```
   One attack only: add `--only replay` (or `scan`, `tampered`, `forged`, `unsigned`, `garbage`). More commands: `--n 100`.

## What reviewers see

| Attack | What the outsider tries | Gateway answer |
|---|---|---|
| scan | looks for open doors | only 22 (SSH, key only) and 8000 (the gateway) |
| replay | re-sends the captured commands | Replayed / Stale |
| tampered | changes a captured 1 mL dose to 20 mL | Not authorised (signature broken) |
| forged | makes a new 15 mL command and signs it with their own key | Not authorised |
| unsigned | sends a new command without a signature | Not authorised |
| garbage | sends "OPEN ALL VALVES" | Malformed |

The attacker's terminal ends with **"… blocked, 0 reached a pump · ALL BLOCKED"**. At the same time, the HMI's Security monitor on the ChemShield Mac turns red and counts every attack, and the audit log records each one as coming from the attacker laptop.

Tested 16 Nov against a test copy of the station: 50/50 blocked, 0 reached a pump.
