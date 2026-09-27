# ChemShield (Team M016)

A cyber-physical safety interlock for a pH neutralization tank. Only the tank chemistry is simulated; the gateway, AI, redosing, HMI, Uno and pumps are real.

| Folder | What goes here | Owner |
|---|---|---|
| `sim/` | Tank simulator (chemistry from Aspen). Live mode for the demo, batch mode for data and the 600-event runs | Hattan (code) + Abdulkarim (chemistry, Aspen validation) |
| `model_a/` | Dataset generation, Model A training, and the inference function the gateway calls | Belal |
| `gateway/` | Command checks (firewall rules), audit log, attack script, network and firewall config | Khalid |
| `redosing/` | MILP `plan_next_dose()` and the QC charts | Hattan |
| `hmi/` | Operator web screen | Khalid (build) + Hattan (design) |
| `firmware/uno/` | Arduino Uno sketch: last safety check and pump control | Belal |
| `docs/` | `interfaces.md`: the message formats between parts. **Read this first.** | Everyone |
| `evidence/` | Test sheets, data CSVs and video links, named by test ID (e.g. `ICS-AT-02`) | Everyone |

## Rules
- Work in your own folder. Changing a format in `docs/interfaces.md` needs the other owner's OK.
- Everything must run in **SIM mode** (no hardware) at all times.
- Belal merges into `main`.
