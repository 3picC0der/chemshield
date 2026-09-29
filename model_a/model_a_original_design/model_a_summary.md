# Model A prototype evidence

Generated examples: 12000 across 3000 independent runs.

Selected model: `residual_context_model` with validation-selected threshold 0.350.

## Held-out test results

- Nominal physics harmful recall: 0.969
- Nominal physics benign false-block rate: 0.106
- Hybrid harmful-context recall: 0.979
- Hybrid benign false-block rate: 0.128
- Additional harmful cases blocked by Model A: 18
- Additional benign cases blocked by Model A: 14

## Interpretation

These results prove that the software experiment and evidence pipeline runs. They do not validate the physical plant. The simulator deliberately includes hidden sensor and delivery uncertainty so that the learned model can use prior residuals. Replace those distributions with measured or Aspen-calibrated values before making performance claims.
