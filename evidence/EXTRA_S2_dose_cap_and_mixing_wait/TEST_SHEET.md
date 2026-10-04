# EXTRA · Spec 2 · Dose cap of 20 mL and at least 15 s of mixing

| | |
|---|---|
| **Binder test ID** | CHE-AT-02 |
| **Department / type** | CHE · Specification · **EXTRA** (not in the list of nine) |
| **Verdict** | **PASS: MET** as enforced by the gateway: over-20 mL doses rejected, a second dose within 15 s rejected, accepted again at exactly 15 s |
| **Evidence level** | Software tests plus records from the real rig (2 Oct) and from the attack run (3 Oct). The wait between two hand-added doses was not timed on the rig |

| No. | Specification (full text) | Test procedure | Result / evidence |
|---|---|---|---|
| **S2** | Each corrective dose shall be ≤20 mL, with ≥15 s of mixing before another dose. | 1. Request a dose above 20 mL from the HMI. | Real rig, 2 Oct: two requests of 30 mL were **rejected as `DOSE_LIMIT`** (15:30:26 and 15:33:35 UTC). Test: 25 mL rejected. `data/s2_gateway_decisions.csv`. |
| | | 2. Request a normal dose. | Real rig, 2 Oct: two 10 mL doses of 0.005 M NaOH **accepted** by the gateway and sent to the Uno (15:32:10 and 15:34:12 UTC); the operator marked the second one added at 15:34:23 UTC. |
| | | 3. Request another dose within 15 s of an accepted one. | Attack run, 3 Oct: **403 requests rejected as `MIXING_LOCKOUT`**. Test: the second dose is rejected, and still rejected at 14.9 s. |
| | | 4. Request a dose after 15 s. | Test: accepted at **exactly 15.0 s** after the first dose. Through the HMI path: six back-to-back doses give 1 accepted and 5 rejected, then accepted again 15.1 s later. |

## Verdict

**MET.** The gateway applies both limits itself, on its own clock, whatever the sender asks. 4 automated tests passed (`data/unit_tests_gateway_s2.txt`).

## Files in this folder

- `data/s2_gateway_decisions.csv`: the audit rows behind steps 1 to 3 (2 rejected over-limit requests and 2 accepted doses on the rig; 1 accepted and 403 lockout rejections in the attack run).
- `data/unit_tests_gateway_s2.txt`: the tests behind steps 3 and 4.
- `code/`: the gateway (limits and lockout), its configuration and the test; `code/extract_s2_rows.py` made the CSV.

## Notes

- The HMI shows a countdown of the lockout, and "Dose now" is cancelled if nobody adds the dose within 120 s.
- With hand dosing the operator, not a pump, delivers the dose; the 20 mL cap is the gateway's limit on what it will approve, and the syringes are 5 mL and 20 mL.
