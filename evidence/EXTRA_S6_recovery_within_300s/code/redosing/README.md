# `redosing/` — MILP dose planning and QC charts

Owner: **Hattan**

## Run it

```bash
# I4 in one call: give it an I2 state, get a dose or an escalation
python -m redosing.planner              # worked examples, including ESCALATE cases

# the four evidence figures (after python -m sim.batch)
python -m redosing.qc.histogram ISE-AT-01_batch.csv --out ISE-AT-01_histogram.png
python -m redosing.qc.imr       ISE-AT-02_batch.csv --out ISE-AT-02_imr.png
python -m redosing.qc.traces    INT-AT-02_batch.csv --out INT-AT-02_traces.png
python -m redosing.qc.far_side  INT-AT-03_batch.csv --out INT-AT-03

# everything at once, into the per-spec folders under evidence/ (03_C3_..., EXTRA_S6_..., EXTRA_INT-S2_..., EXTRA_INT-S3_...)
python -m redosing.run_all
```

## I4: the only function the gateway needs

```python
from redosing.planner import plan_next_dose

plan_next_dose(state)   # state = one I2 message (docs/interfaces.md)
# -> {"action": "DOSE", "channel_id": "BASE_BULK", "dose_ml": 11.8}
# -> {"action": "ESCALATE", "reason": "INFEASIBLE"}
```

`plan_block(state)` returns the same decision plus the rest of the planned block, the
solve time and the reagent it would spend. The gateway may ignore everything outside the
three contract keys.

**Escalation reasons:** `INFEASIBLE` (no dose keeps the worst case safe), `BUDGET`
(the 50 mmol C3 ceiling is spent), `TIME` (abort budget), `STALE` (the reading is older
than 30 s), `SOLVER_FAIL`. There is also `{"action": "HOLD"}` for "nothing to do yet,
the tank is inside the stop band or the residual is not worth a dose cycle" — that is not
an escalation and the operator is not called.

**State keys it reads.** Required: `ph`. Optional, all defaulted, so a bare I2 message
works: `temp_c`, `volume_L`, `event_mmol_used`, `event_ml_used`, `event_elapsed_s`,
`sample_age_s`, `channels_available`, `inventory_ml`. Pass `event_mmol_used` if you want
the C3 budget enforced by the planner as well as by the gateway — it is enforced twice on
purpose.

## What the planner is

A robust mixed-integer linear program, re-solved after every accepted reading. At H = 4 it
has 34 variables, 16 of them binary, and 59 constraints, and HiGHS returns the optimum in
about 10–20 ms. It plans a block of up to four doses that are released back-to-back with a
full mixing hold after each, then re-solves from the next averaged reading.

It is a solver in the loop, not a rule. Section 4.3.1 of the Second Report Installment
has the formulation, the statistical tolerancing that sizes the robust margin, the
eleven-check verification suite and the worked example.

The pH band inverts into constant mole bounds once per reading, because pH is monotone in
net excess acid. That is what keeps the problem linear — there is no nonlinear term in the
solver, and no NLP.

## QC scripts

| Script | Sheet | Produces |
|---|---|---|
| `qc/histogram.py` | ISE-AT-01 | reagent per event with the 50 mmol line |
| `qc/imr.py` | ISE-AT-02 | I-MR control chart + Western Electric rules 1–4 |
| `qc/traces.py` | INT-AT-02 | all 600 pH traces with the band and the 300 s line |
| `qc/far_side.py` | INT-AT-03 | per-event far-side table + the worst-case trace |

The I-MR chart answers "is the process stable", which is a different question from "does
it meet S6". Both lines are drawn and they are not the same line: the control limits come
from the data, the 300 s line comes from the requirement.
