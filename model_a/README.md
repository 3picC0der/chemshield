# Model A: Belal

The pre-dose **context gate** (report Section 1.3). For every dose request that passes the gateway's fixed checks, Model A answers `ACCEPTABLE_CONTEXT`, `HARMFUL_CONTEXT` or `UNCERTAIN_CONTEXT` with a risk score (interface I3). Only ACCEPTABLE lets a dose through: Model A can block a dose, never approve one on its own. It proves **S4** ("incident class and risk score within 3 s"), test sheet **ICS-AT-03**.

**How it decides:**
1. **Can it judge at all?** If not, UNCERTAIN (fail closed). That covers:
   - no bottle name;
   - stale or missing probe readings, or no line from the Uno for 2 s;
   - a feature far outside anything seen in training;
   - an error, or no answer within 100 ms.
2. **Physics rule.** Predict the pH after the dose with the planner's pH table (`sim/aspen_tables/`). If the rules below fire, HARMFUL.
3. **Learned part.** A small gradient-boosted tree model scores what the rule can't see: probe lag, calibration offset, drifting or stuck probe, many small doses, a tank that responds differently than predicted. At or above the threshold, HARMFUL.

**The label rules (policy v1):** a dose is harmful if the settled pH:
- (a) ends outside 5.5–9.5 (unless it's a partial recovery toward 7);
- (b) moves an already abnormal tank more than 0.2 farther from 7;
- (c) overshoots from one side of 6.3–8.2 to the other;
- (d) takes a tank that is inside 6.0–8.5 outside it.

## Run it

One-time setup, from the repo folder:

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

On the Pi, `python3 -m venv .venv` is fine; the code needs Python 3.10 or newer.

| Step | Command | Output |
|---|---|---|
| Dataset (about 20 s on a laptop) | `.venv/bin/python -m model_a.generate` | `model_a/data/`: dataset (CSV, gzipped), `manifest.json`, `DATASET_CARD.md` |
| Train (under a minute) | `.venv/bin/python -m model_a.train` | `model_a/artifacts/`: `model_a.joblib`, `MODEL_CARD.md`, `evidence.json`, CSVs |
| Tests | `.venv/bin/python -m model_a.tests.test_model_a` | 14 tests |
| ICS-AT-03 timing | `.venv/bin/python -m model_a.latency_test --gateway-src <folder containing chemshield_gateway>` | `evidence/ICS/ICS-AT-03/...`: latency CSV, histogram, summary, machine info |

- **The dataset needs the baking-soda pH table** in `sim/aspen_tables/`: the placeholder from the simulator fix, then CHE's Aspen export. `generate` refuses to run if the table and the tank liquid disagree. When the table changes, regenerate and retrain; it takes minutes.
- **On the Pi, retrain once** with the same two commands, so the model file matches the Pi's scikit-learn version.

## Plugging it into the gateway (Pi)

```python
from model_a.inference import ModelAClient, ProcessContext

context = ProcessContext()                               # shared by the bridge, the loop and Model A
model_a = ModelAClient(context=context, decision_log="logs/model_a_decisions.csv")
gateway = GatewayValidator(model_a=model_a)              # replaces FakeModelAClient

# serial bridge, for every line from the Uno
context.mark_uno_alive()                                 # any line counts as a heartbeat
context.add_sample(7.02)                                 # for each "PH,7.02" line

# control loop, once an accepted dose has been added to the tank
model_a.dose_added(command["command_id"])

# a fresh tank (new fill)
context.reset_tank(5.0)
```

Model A needs **`channel_id`** in each command (`ACID_BULK`, `ACID_FINE`, `BASE_BULK`, `BASE_FINE`), as in I1. Without it the answer is UNCERTAIN, because 20 mL of 0.5 M is 100 times 20 mL of 0.005 M. It also accepts `dose_ml` or the older `volume_ml`.

## Where the inputs come from

| # | Feature | At the PPR |
|---|---|---|
| 1–4 | pH mean, slope, curvature, spread of the last 5 readings | Probe → Uno A0 → `PH,x` line over USB → Pi |
| 5 | Age of the newest reading | Pi clock |
| 6–7 | Direction and mmol of the request | The request (bottle × mL) |
| 8–9 | Predicted pH after the dose, margin to 5.5/9.5 | Pi, with the planner's pH table |
| 10–11 | Signed and total mmol accepted in the last 10 min | Pi's dose log |
| 12 | Request–delivery residual | **Fixed at 0** (no pump feedback with hand dosing) |
| 13 | Measured pH minus the pH predicted for the last dose | Probe + Pi |
| 14 | Mixer speed ratio | **Fixed at 1.0** (stirred by hand) |
| 15 | Level margin to 5.5 L | Estimated from the dose log |
| 16 | Time since the Uno's last line | Pi ↔ Uno link |

## Files

| File | What it is |
|---|---|
| `schema.py` | Feature names, bottles, limits and versions shared by training and the Pi |
| `features.py` | The 16 features, the same code in training and live |
| `policy.py` | Label rules and physics screen |
| `truth.py` | The hidden true tank (baking-soda water) used only for labels |
| `generate.py` | Episodes → dataset; the probe, fault and hand-dose ranges are in `RANGES` |
| `train.py` | Split, baselines, Model A, threshold, evaluation |
| `inference.py` | `ModelAClient` (the gateway call), `ProcessContext`, decision log |
| `latency_test.py` | ICS-AT-03: 1,000 signed requests through the real gateway |
| `model_a_original_design/` | The FDR-stage design and prototype this is built from |

## Replace the assumptions when measured

In `generate.py` → `RANGES`, then regenerate and retrain:
- `probe_noise_sd`: put the probe in still water, log 60 s, and take the standard deviation.
- `probe_lag_tau_s`: add one known dose and stir. Take the time to reach 95% of the change, divided by 3.
- The baking-soda uncertainty and the hand-dose error, if CHE has better numbers.
