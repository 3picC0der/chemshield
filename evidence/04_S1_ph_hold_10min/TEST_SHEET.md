# Spec 1 · pH held between 6.5 and 7.5 for 10 minutes

| | |
|---|---|
| **Binder test ID** | CHE-AT-04 |
| **Department / type** | CHE · Specification (extra: not needed for the satisfactory level) |
| **Verdict** | **NOT YET TESTED.** The software is ready and tested; the 10-minute run on the real tank has not been done |
| **Evidence level** | Planned: real rig, real probe |

| No. | Specification (full text) | Test procedure | Result / evidence |
|---|---|---|---|
| **S1** | Under defined nominal steady-state influent conditions, the neutralization process shall maintain tank pH between 6.5 and 7.5 for at least 10 min. | 1. Calibrate the probe with pH 7 and pH 4 buffers: `python firmware/uno/uno_tool.py cal 7.00`, then `cal 4.00` (station stopped). | Reads ______ in the pH 7 buffer (within 0.05). |
| | | 2. Make the tank: 4.9 L distilled water + 100 mL of baking-soda stock (4.20 g NaHCO₃ per litre). It rests near pH 8.3. Add 0.05 M HCl (about 18 mL) in small portions, stirring, until the HMI reads 6.8 to 7.2. | Start pH ______; acid added ______ mL. |
| | | 3. On the HMI: Evidence, then "10-minute pH hold", then Start. | Start time ______. |
| | | 4. If the HMI shows "Dose now" (a trim dose when the pH leaves 6.7 to 7.3), add that dose by syringe, stir, press DOSE ADDED. | Doses added ______. |
| | | 5. At 600 s read the result and download the CSV. | Lowest pH ______; highest pH ______; HMI says PASS? ______. |

## Verdict

**NOT YET TESTED.** Pass if every reading stays between 6.5 and 7.5 for the full 600 s.

## What is ready

- The hold log, its 600 s clock and the PASS rule are in the station (`code/hmi/station/core.py`), tested in software: `data/unit_test_hold_log.txt` (1 passed). That test uses a simulated tank, so it shows the logger works, not that the tank holds its pH.
- The Uno firmware that reads the probe and its two-point calibration tool are in `code/firmware/uno/`.

## Notes for the run

- The probe needs a clean two-point calibration first. On 4 Oct the new probe was noisy (the Uno warned "A0 at rail", which points to a loose plug or wire), so check the BNC plug and the three board wires before this test.
- Save the downloaded CSV as `data/S1_hold_10min.csv` and film the screen for the 10 minutes.
