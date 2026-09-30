# HMI: the operator screen (Belal)

The screen the operator uses at the PPR, built to Hattan's design (`DESIGN.md`,
`wireframe.html`). It shows live pH, the Model A class and score, every gateway accept or
reject with its reason, recovery mode and the audit log. S5 (the SUS study) is measured on
it, and it is where INT-S1, S2, S4, C3, S6/INT-S2, S1 and S3 are read off during the demo.

## How the three boxes connect

```
 Laptop  ───── Wi-Fi ─────▶  Raspberry Pi 5  ───── USB cable ─────▶  Arduino Uno
 the HMI                     the "station":                          reads the pH probe,
 (browser + small server     gateway (Khalid) + Model A (Belal)      lights the "dose now"
  that holds the key)        + planner (Hattan) + audit log          light, locks on command
```

- **Laptop:** runs the HMI. When you press REQUEST DOSE, the laptop signs the request with
  the operator key and sends it to the Pi. It never talks to the Uno and decides nothing.
  The HMI server only listens on the laptop itself, so nobody else on the Wi-Fi can use it.
- **Pi:** runs the station. The gateway checks every request (signature, freshness,
  20 mL, 15 s lockout, 50 mmol, Model A) and writes the audit log. The station also
  watches the pH, switches to RECOVERY on an unsafe event and runs the planner.
- **Uno:** sends `PH,7.02` once a second over the USB cable and turns its light on when a
  dose is approved. You are the pump: you add that dose with a syringe and press DOSE ADDED.

Everything the laptop sends goes through the gateway on the Pi, which is the C2 story.

## Run it

All commands from the repo folder, with the virtual environment from `model_a/README.md`.

### A. Laptop only, no Pi, no tank (SUS study, rehearsals)

```bash
.venv/bin/python -m hmi.demo
```

This opens http://127.0.0.1:8080. The pH comes from Hattan's simulated tank, and a purple
**SIMULATED pH** band stays on the screen the whole time. The gateway, Model A, planner and
audit log are the real code. The engineer panel at the bottom injects upsets, sets the pH,
pulls the "USB cable" and sends test attacks. Stop with Ctrl+C.

### B. The real rig

1. **Make the key once, on the laptop:** `.venv/bin/python -m hmi.keygen`. Copy
   `hmi/secrets/operator.key` to the same path in the repo on the Pi (for example with `scp`).
   Until you do, the screen shows a yellow "demo key" warning.
2. **On the Pi** (Uno plugged in by USB):

   ```bash
   .venv/bin/python -m hmi.station --ph-source uno --port "${CHEMSHIELD_HMI_PORT:-8000}"
   ```

   It finds the Uno by itself (`/dev/ttyACM0`); `--serial-port` picks one. This is the only
   port the firewall opens besides SSH (`gateway/firewall/raspberry_pi_firewall_template.sh`
   reads the same variable). To show the rig without the probe, use `--ph-source sim`: the
   HMI then says SIMULATED.
3. **On the laptop**, joined to the Pi's Wi-Fi:

   ```bash
   .venv/bin/python -m hmi --station http://<pi-ip>:8000 --operator "Belal"
   ```

Every run writes its evidence to `hmi/logs/<date-time>/` on the Pi: `audit.jsonl` (the
hash-chained log) and `model_a_decisions.csv`. The screen also downloads CSVs.

**No Uno yet?** `.venv/bin/python -m hmi.mock_uno` makes a pretend Uno on a virtual serial
port and prints its name; start the station with `--serial-port <that name>`. Type `ph 5.4`,
`estop`, `release` or `mute 5` into it to test the Pi side.

## What's on the screen

| Part | Shows | Evidence for |
|---|---|---|
| Banner | NORMAL / UNSAFE DOSING EVENT, RECOVERY IN PROGRESS / OPERATOR DECISION REQUIRED / HALTED, with the recovery timer (x / 300 s), event reagent (x / 50 mmol) and when pH came back into 6.0-8.5 | INT-S1, S6, INT-S2, C3; SUS tasks 3-4 |
| Tank pH | Mean of 3 readings, colour by zone, reading age (turns STALE), PROBE or SIMULATED, a 5-minute trend with 6.0/8.5 and 5.5/9.5 drawn | SUS task 1; INT-AT-02 |
| Event detail | Event class, the 3 readings that confirmed it, confirmed → RECOVERY shown in ms, Model A class, score and time | INT-S1, S4 |
| Recovery plan | The MILP's doses with status (dose now, mixing 12 s, complete), reagent vs 50 mmol, time vs 300 s, predicted pH after the plan, "why this plan" | C3, S6, INT-S2 |
| Evidence tabs | Recovery-mode timing per event (PASS under 2 s), the 10-minute pH hold (S1) with its CSV, and Model A timing per request | INT-S1, S1, S4 |
| Operator action | HALT DOSING, RESUME DOSING (the operator reset), ACKNOWLEDGE | SUS tasks 3-4; INT-AT-04 |
| Dose now | "Add 10 mL of NaOH 0.5 M bulk now, then stir", DOSE ADDED and "Not added" | S2 with hand dosing |
| Manual dose | Bottle, mL, REQUEST DOSE; the gateway's answer inline, in words, with the code | S2, C3; SUS task 2 |
| Safety state | Gateway-only path, Uno link, Uno light, mixing lockout, Model A, audit chain, E-stop | C2 |
| Audit log | Every decision and event, newest first, "rejected only" filter, counters by reason, CSV/JSONL export, chain check | S3; SUS task 5 |

Reason words: Replayed (REUSED_NONCE, DUPLICATE_COMMAND_ID, OLD_SEQUENCE), Stale
(STALE_TIMESTAMP), Over limit (DOSE_LIMIT, EVENT_MMOL_LIMIT), Mixing lockout, Model A block,
Not authorised (INVALID_HMAC and friends), Wrong state (SAFE_HOLD_ACTIVE, HEARTBEAT_LOSS,
DOSE_PENDING). The full list is `REASONS` in `common.py`.

## The test sheets, step by step on this screen

| Sheet | What you do | What you read |
|---|---|---|
| **CHE-AT-02** (S2) | Request 25 mL, then 20 mL of **NaOH 0.005 M fine** (20 mL of a 0.5 M bottle at pH 7 would be blocked by Model A). Add it, press DOSE ADDED, request again within 15 s, then after 15 s. | Over limit (DOSE_LIMIT); Accepted + Dose now; Mixing lockout with the countdown; Accepted |
| **ICS-AT-03** (S4) | Request any dose. | Event detail and the Model A timing tab: class, score, ms. The 1,000-request run is `python -m model_a.latency_test` |
| **INT-AT-01** (INT-S1) | NORMAL on screen. Add acid by syringe until pH is under 6.0 (SIM: engineer panel, 7 mL acid). | Banner turns red; Recovery-mode timing tab: confirmed, recovery mode, Uno locked, HMI showed it (ms). Uno light slow-blinks |
| **INT-AT-02 / ISE-AT-02** (INT-S2, S6) | Follow each "Dose now" box and stir; press DOSE ADDED. | Banner: "pH back in 6.0-8.5 at N s" and the recovery timer |
| **ISE-AT-01** (C3) | SIM: engineer panel, `acid_upset_max`. During the recovery request a dose past 50 mmol. | Event reagent x / 50 mmol; the extra dose: Over limit (EVENT_MMOL_LIMIT) |
| **CHE-AT-04** (S1) | Evidence → 10-minute pH hold → Start. Add any dose the HMI asks for. | Elapsed / 600 s, lowest and highest pH, PASS; download the CSV |
| **ICS-AT-02** (S3) | `python -m hmi.attack_station --station http://<pi-ip>:8000 --mode replay-now --n 1000`, then `--mode stale --age 5 --n 1000` and `--age 1 --n 100` | Audit log counters (Replayed, Stale) against the script's summary; `python -m hmi.verify_log <exported audit.jsonl>` prints CHAIN OK |
| **ICS-AT-01** (C2) | Engineer panel: "unsigned" and "wrong key"; from another laptop, `curl` a dose to the Pi | Not authorised; the station answers HTTP 401 |
| **INT-AT-04** | SIM step 4: set pH 6.3 (6.0 exactly can confirm an event from probe noise), then 20 mL HCl 0.5 M bulk. Unplug the Uno's USB during a dose. | Model A block; HALTED, "Uno link lost", doses refused until RESUME DOSING |
| **ISE-AT-03** (S5) | The five tasks: read pH; request 10 mL of bulk base; respond to the alarm (ACKNOWLEDGE); stop dosing (HALT DOSING); find the last rejected command (audit log → rejected only) | All on one screen, no tabs to hunt through |

For the batch version of INT-S1: `python -m hmi.int_s1_batch --events 100` writes
`evidence/INT/INT-AT-01/laptop_dry_run/` (confirmed → RECOVERY seen by the HMI, per event).

## Uno lines (what the firmware must speak)

USB serial, 115200 baud, one line per message ending in `\n`. This is I5 from
`docs/interfaces.md` plus `MODE`, `STOP` and `PH`. `hmi/mock_uno.py` is a working reference.

| Pi → Uno | Meaning | Uno answers |
|---|---|---|
| `HB` | heartbeat, every 0.5 s | nothing. After 2 s with no `HB`: light off, stop, send `HB_LOST` |
| `DOSE,<seq>,<pump 1-4>,<run_ms>` | dose approved: light the dose light for `run_ms` (pump 1 NaOH bulk, 2 NaOH fine, 3 HCl bulk, 4 HCl fine) | `OK,<seq>`, then `DONE,<seq>,<ms>`; or `REJECT,<seq>,<reason>` if halted, busy or E-stop |
| `STOP` | the operator pressed DOSE ADDED or cancelled: light off | `OK,STOP` |
| `MODE,NORMAL` / `MODE,RECOVERY` / `MODE,HALT` | light pattern: off / slow blink (dosing locked) / fast blink | `OK,MODE,<mode>` (the station times this for INT-S1) |
| `STATUS` | | `STATUS,<estop 0/1>,<busy 0/1>` |

| Uno → Pi, unasked | |
|---|---|
| `PH,<value>` | once a second, the calibrated probe reading (any line also counts as "alive") |
| `STATUS,1,0` | the E-stop was pressed: the station halts at once |

## Files

| File | What it is |
|---|---|
| `app.py`, `__main__.py` | The laptop HMI server (signs, forwards, serves the page) |
| `static/` | The screen: `index.html`, `hmi.css`, `hmi.js` |
| `station/core.py` | The station: event detection, recovery switch, planner loop, hand-dosing steps, S1 hold log |
| `station/links.py` | The pH source: `UnoLink` (serial) or `SimLink` (Hattan's simulator) |
| `station/server.py`, `station/__main__.py` | The station's network API and command line |
| `station/audit.py` | Khalid's hash-chained log plus source, event and message, written to disk as it goes |
| `common.py` | Key, command format, reason words: shared by both sides |
| `demo.py`, `keygen.py`, `mock_uno.py` | Laptop-only demo, key maker, pretend Uno |
| `verify_log.py`, `attack_station.py`, `int_s1_batch.py` | Evidence tools (INT-AT-04, ICS-AT-02, INT-AT-01) |
| `tests/` | `.venv/bin/python -m pytest hmi/tests gateway/tests -q` |

## Things to know

- **Model A sometimes blocks a correct recovery dose** after a big acid upset: in 24
  simulated upsets, 3 ended in OPERATOR DECISION REQUIRED because it blocked the planner's
  last bulk dose twice. The station re-reads and re-plans once before asking the operator.
  Small upsets (the 7 mL INT-AT-01 demo) recovered every time. HALT then RESUME lets the
  planner try again.
- **The event closes** when the pH has stayed inside 6.0-8.5 for 60 s (`--dwell`).
- **Hand-dose speed** (`--hand-speed`, mL/s) only sets how long the Uno's light stays on.
- The pH table is still the PLACEHOLDER until CHE's Aspen file lands; the screen says which.
