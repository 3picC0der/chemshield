# ChemShield (Team M016)

A cyber-physical safety interlock for a pH neutralization tank.

**The PPR rig:** a 5 L tank of baking-soda water with a real pH probe. The probe's board
feeds an Arduino Uno, which sends the pH to a Raspberry Pi 5 over USB and lights a
"dose now" light. The Pi runs the gateway, Model A, the redosing planner and the audit log.
The laptop shows the HMI over the Pi's Wi-Fi, and doses are added by hand with syringes.
The tank chemistry is simulated only for the batch evidence, for Model A's training data,
and when the station runs with `--ph-source sim`.

| Folder | What goes here | Owner |
|---|---|---|
| `sim/` | Tank simulator (chemistry from Aspen's pH table). Live mode, and batch mode for data and the 600-event runs | Hattan (code) + Abdulkarim (chemistry, Aspen validation) |
| `redosing/` | MILP `plan_next_dose()` and the QC charts | Hattan |
| `model_a/` | Dataset generation, Model A training, and the inference call the gateway makes | Belal |
| `gateway/` | Command checks, audit log, attack script, firewall and network notes | Khalid |
| `hmi/` | The laptop HMI and the Pi "station" (gateway + Model A + planner + recovery + Uno link) | Belal (build) + Hattan (design) |
| `firmware/uno/` | Arduino Uno sketch: pH reading, dose light, E-stop, heartbeat; calibration tool | Belal |
| `docs/` | `interfaces.md`: the message formats between the parts. **Read this first.** | Everyone |
| `evidence/` | **Start at `evidence/README.md`.** One folder per spec or constraint: test sheet, raw data, plots and a code snapshot, plus the attainment table, the explanation doc and the setup and demo guide | Everyone |

**How to run it:** `hmi/README.md` (laptop demo, the real rig, and each test sheet's steps).
Tests: `.venv/bin/python -m pytest hmi/tests gateway/tests sim/tests model_a/tests -q`.

## Rules
- Work in your own folder. Changing a format in `docs/interfaces.md` needs the other owner's OK.
- Everything must also run with no hardware (`python -m hmi.demo`, `--ph-source sim`).
- Belal merges into `main`.
