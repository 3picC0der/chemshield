# S9 · Solver vs PI controller (simulation, evidence level 6)

Requirement: ≥ 15 % less reagent than a PI controller.
Method: `s9_compare.py` runs the recovery solver (rdo) and the PI controller from `sim/sim2.py` on the **same 600 simulated spills with the same noise** (seed 261/11), with the same pumps, 20 mL cap and mixing holds.

| | PI controller | ChemShield solver |
|---|---|---|
| Recovered into 6.0–8.5 | **417 / 600 (69.5 %)**; 183 gave up after 12 doses | **600 / 600 (100 %)** |
| Mean time | 231 s | **97 s** |
| Doses per event | 9.8 | **3.75** |
| Overshoot past 5.5 / 9.5 | 0 % | 0 % |
| Reagent, events both recovered (417) | 28.9 mmol | 29.8 mmol (**3 % more**) |

**Result: S9 as written is not met.** Reagent is set by the chemistry. Cancelling X mmol of spilled acid takes about X mmol of base, whichever controller doses it. The PI uses about 3 % less only because it stops at the edge of the band (about 97 % of the spill neutralised), while the solver brings the tank back to about pH 7 (about 100 %). Neither can be 15 % below what the spill needs.
**What the solver does better:** it recovers every spill (vs 69.5 %), 2.4× faster, with 2.6× fewer doses, at the same reagent use.
Files: `s9_summary.json`, `s9_per_event.csv`.
