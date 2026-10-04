# Model A model card

Trained 2026-10-01T07:46:47+00:00, model A-1.0-ppr, label policy v1, feature schema fs-1, scikit-learn 1.9.1.
Dataset: 25578 requests (bicarb_1mM, chemistry PLACEHOLDER, sha256 `29c314c4c6299122...`).

## What it does
For each dose request that has passed the gateway's fixed checks, Model A answers ACCEPTABLE_CONTEXT, HARMFUL_CONTEXT or UNCERTAIN_CONTEXT with a risk score. HARMFUL when the physics rule flags the pH it predicts, or when the learned score is at or above **0.205** (picked on the validation set). UNCERTAIN when it can't judge: stale or missing probe data, lost Uno heartbeat, bad bottle name, a feature outside the training range, an error, or no answer within 100 ms. Only ACCEPTABLE lets a dose through. Model A can block a dose, never approve one on its own.

## Results on the held-out test episodes (4539 requests, 1353 harmful)

| System | Harmful recall | Benign false-block rate |
|---|---|---|
| Gateway only | 0.000 (1353 missed) | 0.000 (0 of 3186) |
| Physics rule alone | 0.889 (150 missed) | 0.009 (30 of 3186) |
| Logistic regression | 0.986 (19 missed) | 0.454 (1446 of 3186) |
| Random forest | 0.976 (33 missed) | 0.077 (245 of 3186) |
| Gradient boosting | 0.985 (21 missed) | 0.133 (425 of 3186) |
| **Model A** (physics rule + learned part) | 0.958 (57 missed) | 0.030 (95 of 3186) |
| **Model A as it runs on the Pi** (UNCERTAIN counts as a block) | 0.958 (57 missed) | 0.030 (95 of 3186) |

The learned part caught 93 harmful requests the physics rule missed, at the cost of 65 extra benign blocks.

By kind of request (Model A as it runs on the Pi):

| Request | Harmful ones blocked | Good ones blocked |
|---|---|---|
| Small fine corrections | 0 of 1 | 0 of 508 |
| Oversize bulk doses | 496 of 500 | 17 of 62 |
| Planner (MILP) recovery doses | 18 of 29 | 16 of 309 |
| Random doses | 401 of 405 | 20 of 531 |
| Naive controller doses | 36 of 63 | 19 of 1321 |
| Planner doses as the Pi station sends them | 15 of 20 | 11 of 188 |
| Wrong direction | 330 of 335 | 12 of 267 |

**Never-seen pattern** (many small same-direction doses, 1941 requests, 940 harmful): physics rule recall 0.961, Model A 0.963 (false blocks 0.015).

**Fail-closed check:** 218 of 218 requests the Pi can't judge came out UNCERTAIN.

**Speed (this computer, decision code only):** p50 0.2452 ms, p99 0.3607 ms, max 0.6759 ms over 1000 requests. S4 allows 3,000 ms.

Most important inputs to the learned part: ph_std_5s (0.26), candidate_mmol (0.23), candidate_direction (0.14), ph_slope_5s (0.08), measured_predicted_residual (0.07).

## Same dose, different tank (steady probe, baking-soda water)
| Dose | Tank pH | Pi predicts | Really ends at | Truth | Model A (score) |
|---|---|---|---|---|---|
| 2 mL BASE_BULK | 3 | 3.10 | 3.10 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 2 mL BASE_BULK | 4.5 | 5.70 | 5.70 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL BASE_BULK | 5.8 | 6.21 | 6.21 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL BASE_BULK | 6.3 | 6.66 | 6.66 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL BASE_BULK | 7 | 8.61 | 8.61 | HARMFUL | HARMFUL (1.00) |
| 2 mL BASE_BULK | 7.7 | 9.50 | 9.50 | HARMFUL | HARMFUL (1.00) |
| 2 mL BASE_BULK | 8.3 | 9.61 | 9.61 | HARMFUL | HARMFUL (1.00) |
| 2 mL BASE_BULK | 9 | 9.73 | 9.73 | HARMFUL | HARMFUL (1.00) |
| 2 mL BASE_BULK | 10 | 10.24 | 10.24 | HARMFUL | HARMFUL (1.00) |
| 2 mL BASE_BULK | 11 | 11.07 | 11.07 | HARMFUL | HARMFUL (1.00) |
| 2 mL ACID_BULK | 3 | 2.92 | 2.92 | HARMFUL | HARMFUL (1.00) |
| 2 mL ACID_BULK | 4.5 | 3.66 | 3.66 | HARMFUL | HARMFUL (1.00) |
| 2 mL ACID_BULK | 5.8 | 4.87 | 4.87 | HARMFUL | HARMFUL (1.00) |
| 2 mL ACID_BULK | 6.3 | 5.92 | 5.92 | HARMFUL | HARMFUL (1.00) |
| 2 mL ACID_BULK | 7 | 6.56 | 6.56 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL ACID_BULK | 7.7 | 6.85 | 6.85 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL ACID_BULK | 8.3 | 6.95 | 6.95 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL ACID_BULK | 9 | 7.11 | 7.11 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 2 mL ACID_BULK | 10 | 9.65 | 9.65 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 2 mL ACID_BULK | 11 | 10.92 | 10.92 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 10 mL BASE_FINE | 3 | 3.01 | 3.01 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 10 mL BASE_FINE | 4.5 | 4.62 | 4.60 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 10 mL BASE_FINE | 5.8 | 5.83 | 5.82 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 10 mL BASE_FINE | 6.3 | 6.32 | 6.32 | ACCEPTABLE | ACCEPTABLE (0.00) |
| 10 mL BASE_FINE | 7 | 7.03 | 7.03 | ACCEPTABLE | ACCEPTABLE (0.00) |
| 10 mL BASE_FINE | 7.7 | 7.81 | 7.81 | ACCEPTABLE | ACCEPTABLE (0.00) |
| 10 mL BASE_FINE | 8.3 | 8.49 | 8.49 | ACCEPTABLE | ACCEPTABLE (0.01) |
| 10 mL BASE_FINE | 9 | 9.07 | 9.07 | ACCEPTABLE | ACCEPTABLE (0.02) |
| 10 mL BASE_FINE | 10 | 10.01 | 10.01 | HARMFUL | HARMFUL (1.00) |
| 10 mL BASE_FINE | 11 | 11.00 | 11.00 | HARMFUL | HARMFUL (1.00) |

## Limits
- Simulation evidence only. The chemistry table is a PLACEHOLDER, not Aspen; probe noise and lag are assumed until measured.
- The report's goals (zero missed hazards, at most 5% false blocks) are reported as they came out, not tuned to.
- The score is a risk score, not a calibrated probability.
