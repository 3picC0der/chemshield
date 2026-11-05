# Report draft against the data behind it (5 Nov 2026)

The draft marks 136 values in yellow. This table says which of them, and which of the other claims, have data behind them. I searched this repository and Belal's Senior Design and Downloads folders; teammates may hold files that are not there.

| Item | Requirement | What the draft says | Data behind it | Status |
|---|---|---|---|---|
| S7 | Rated flow ≤ 500 mL/min | 386 mL/min, 60 s run | **Measured 5 Nov:** 320 ± 12.5 mL/min, pump 3, 3 × 10 s, about 288 rpm. Rated about 400 mL/min | **Met.** Report updated |
| C2 | Gateway is the only path | 8/8 checks | Rig run, 4 Oct: `evidence/02_C2_*` | **Met, real rig.** Before the pumps were added |
| S3 | ≥ 99 % replay/stale rejected | 2,000/2,000; 1,100/1,100 fresh accepted | 2,000/2,000 real, from a laptop against the station code, 3 Oct. Only 1 fresh command was accepted; the "1,100 accepted" is not what the test sheet shows | **Met.** Report corrected. Not repeated on the Pi |
| S4 | Class and score ≤ 3 s | mean 0.87, p99 1.21, max 1.65 ms | Pi run, 3 Oct: recomputed from `pi_run_3Oct`, matches | **Met, real Pi** |
| INT-S1 | Recovery mode ≤ 2 s | 1.1 ms | Rig run, 4 Oct: `evidence/09_INT-S1_*` | **Met, real rig** |
| C3 | ≤ 50 mmol | wet 42.0; batch 41.7 | Batch reproduced: max 41.66, mean 29.59. **No wet run** | **Simulation only** |
| S6 | ≥ 95 % within 300 s | wet 5/5; batch 600/600, max 153.8 s | Batch reproduced: 600/600, mean 112.5, max 153.8, I-MR 112.5 / 167.2 / 57.8 / 20.6. **No wet run** | **Simulation only** |
| INT-S2 | pH back in 6.0-8.5 ≤ 5 min | wet 5/5 | Batch 600/600. **No wet run** | **Simulation only** |
| INT-S3 | No pH past 5.5 / 9.5 | wet extremes 6.30-6.86 | Batch 600/600, worst 6.67. **No wet run** | **Simulation only** |
| S9 | ≥ 15 % less reagent than PI | 26.3 % | Reproduced: 29.59 vs 40.12 mmol per success, PI recovered 421 of 600, 3.2 % more on the shared events | **Simulation only** |
| S2 | Dose ≤ 20 mL, ≥ 15 s mixing | error 1.46 %, 19.99 mL, t95 11.0-12.6 s | Gateway limits are real (2-3 Oct, tests). **Pumps never weighed; t95 never measured** | **Limits enforced; delivery and t95 not measured** |
| S1 | pH 6.5-7.5 for 10 min | 6.81-7.06 | **Never run** | **Not tested** |
| C1 | ≤ 5 wt% reagents | titrated 1.82-1.95 wt% | Calculation (1.96 wt%) and approval noted 1 Oct. **No titration file found** | **Calculation only; ask Abdulkarim** |
| S5 | SUS ≥ 80 | mean 83.4, 8 people | Study kit and scoring script only. **No forms found** | **No data found; ask Hattan** |

**Count:** 5 met with real data (S7, C2, S3, S4, INT-S1), 5 by labelled simulation (C3, S6, S9, INT-S2, INT-S3), and 4 open (S1, S2 delivery and mixing, C1, S5).

## About the simulation

- `simulation_NOT_rig_evidence/` reproduces the draft's batch numbers from the code in this repository at 120 mL/min, seed 261.
- The chemistry is the **placeholder** NaHCO3 table, and the pump, mixing and probe values are **design values, not CHE measurements**. So the draft's "calibrated to the prototype" wording is not yet true.
- The sensitivity table was not re-run.

## Draft claims with no data behind them

- W1-W5 wet recoveries and everything derived from them, including "the wet trials fall inside the batch limits".
- The 12 h soak test, 720 doses, and the retitration after 7 days.
- ICS-AT-04 (Uno refusal test): never run.
- Buffer read-backs, S1 hold values.
- "Repeated on the FPR firmware on 2 Nov": removed in the updated copy.

## Draft claims that do not match the rig

- **Uno 15 s lockout:** the firmware has no such timer; only the gateway does.
- **E-stop:** not fitted on 5 Nov; Hold is jumpered.
- **Stirrer PWM 128:** the firmware now uses 180.
- **Recovery at 120 mL/min:** the firmware default is 800 full steps/s (about 280 mL/min at the measured 1.16 mL per turn); the speed has not been set.
- **Main firmware:** `chemshield_uno` has never been uploaded for the pump setup.
