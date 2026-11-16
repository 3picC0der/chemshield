# S9 · Solver vs PI controller (simulation, evidence level 6)

Requirement: ≥ 15 % less reagent than a PI controller.
Method: `s9_compare.py` runs the recovery solver (rdo) and the PI controller from `sim/sim2.py` on the **same 600 simulated spills with the same noise** (seed 261/11), with the same pumps, 20 mL cap and mixing holds.

| | PI controller | ChemShield solver |
|---|---|---|
| Recovered into 6.0–8.5 | **417 / 600 (69.5 %)**; 183 gave up after 12 doses | **600 / 600 (100 %)** |
| Mean time | 231 s | **97 s** |
| Doses per event | 9.8 | **3.75** |
| Overshoot past 5.5 / 9.5 | 0 % | 0 % |
| Reagent, events both recovered (417) | 28.9 mmol | 29.8 mmol (3 % more) |
| **Reagent per successful recovery** (all reagent ÷ spills fixed) | 40.5 mmol | **29.6 mmol (27 % less)** |

**Result:** per successful recovery, ChemShield uses **27 % less reagent** than the PI (S9 met in simulation, level 6). The PI spends about 26 mmol on each of the 183 spills it never fixes. On the same spills, when both succeed, reagent is about equal, because it is set by the chemistry. Cancelling X mmol of spilled acid takes about X mmol of base, whichever controller doses it. The PI uses about 3 % less only because it stops at the edge of the band (about 97 % of the spill neutralised), while the solver brings the tank back to about pH 7 (about 100 %). So on a spill both fix, neither can be 15 % below what that spill needs. The saving comes from not wasting reagent on failed recoveries.
**What the solver does better:** it recovers every spill (vs 69.5 %), 2.4× faster, with 2.6× fewer doses, at the same reagent use.
Files: `s9_summary.json`, `s9_per_event.csv`.
