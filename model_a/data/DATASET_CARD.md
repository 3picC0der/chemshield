# Model A dataset card

Generated 2026-09-29T23:03:19+00:00 from commit `e108312`, seed 261. Label policy v1, feature schema fs-1.
File: `modelA_dataset.csv.gz` (sha256 `e795013d0700ebef...`).

## What it is
28974 dose requests from 3000 simulated episodes of the 5 L tank (recovery 17446, normal 9549, cumulative 1979). One row = one request: the 16 features the Pi can measure at that moment, plus the correct answer from physics.

## How it was made
- **Tank liquid:** bicarb_1mM (5.000 L distilled water + 0.420 g baking soda). The true amount of baking soda varies by x0.95-1.05 per episode (weighing, dissolving, CO2 loss).
- **The Pi's chemistry:** features use the **placeholder** pH table (not Aspen yet) through `sim.chemistry`, the same table Hattan's planner uses (`placeholder_nahco3_ph_table.csv`).
- **Episodes:** fill 4.8-5.2 L. Normal episodes start at pH 6.0-8.5. Recovery episodes add an upset of 2.0-80.0 mL of 0.5 M acid or base, bypassing the gateway.
- **Probe:** one reading per second, rounded to 0.01 like the Uno's `PH,x` line. Calibration offset sd 0.05 pH (clipped at 3 sd), noise 0.005-0.04 pH, lag 3.0-20.0 s. *These are assumptions until the probe is measured.*
- **Hand dosing:** syringe error sd 0.03 per episode + 0.02 per dose; added 2.0-8.0 s after the LED.
- **Faults** in 35% of normal/recovery episodes: stuck probe, drifting probe, USB gap (no readings), no stirring, wrong bottle.
- **Requests:** every 15-60 s. Recovery doses come from Hattan's MILP planner; the rest are fine corrections, a naive controller, wrong direction, oversize bulk doses and random doses. The same doses appear in both safe and harmful contexts.

| Request type | Rows | Harmful fraction |
|---|---|---|
| rule_controller | 9004 | 0.04 |
| random | 5855 | 0.447 |
| wrong_direction | 4004 | 0.532 |
| oversize | 3185 | 0.876 |
| fine_correction | 2943 | 0.0 |
| planner | 2004 | 0.112 |
| cumulative_bias | 1979 | 0.49 |

## The label (policy v1)
The dose is applied to the **true** tank (true baking soda, true hand-dose volume) and the settled pH is checked. HARMFUL if it (a) leaves 5.5-9.5, (b) moves an already abnormal tank (outside 6.3-8.2) more than 0.2 farther from 7, (c) crosses from below 6.3 to above 8.2 or back, or (d) takes a tank inside 6.0-8.5 outside that band. Otherwise ACCEPTABLE. The features never see the true values.

## Splits
Split by episode (60/20/20), never by row. The `cumulative` episodes (many small same-direction doses) are held out of training completely, to test on a pattern the model has never seen. Rows the Pi can't judge (stale or missing readings, lost heartbeat: 258 rows) are kept out of training and used to check that Model A answers UNCERTAIN.

## Limits
- Simulation only: the pH table is a placeholder, not Aspen; the true tank is a closed carbonate model at 25 C.
- Probe noise and lag are assumed ranges until measured on the real probe.
- Features 12 (delivery residual) and 14 (mixer ratio) are fixed at 0 and 1: no pump feedback or mixer at the PPR.
