# Report 3 data: rig session, 5 Nov 2026

New data for the Third Report Installment (Term 261). Written straight after the session.

## What was measured on the rig

One test, **S7 pump flow**, on **pump 3 (BASE_BULK, Z slot, DRV8825)** with distilled water.
The pump was run for 10 s, 3 times, into a graduated cylinder read by Belal (no balance).

| Trial | Full steps | Volume in 10 s | Flow |
|---|---|---|---|
| 1 | 9,228.7 | 51 mL | 306 mL/min |
| 2 | 9,228.7 | 55 mL | 330 mL/min |
| 3 | 9,228.2 | 54 mL | 324 mL/min |
| **Mean ± SD** | | **53.3 ± 2.1 mL** | **320 ± 12.5 mL/min** |

- **Limit:** S7 is about the manufacturer's rating, at most 500 mL/min. The KPHM400 datasheet gives about 400 mL/min at 400 rpm.
- **Speed:** the bench sketch was commanded to 1333 full steps/s (400 rpm), but it reached only about **288 rpm** (960 full steps/s, from the 30 s and 10 s runs). So this is not a flow at the rated speed. The sketch's `SPEED` lines print the commanded value, so they don't show this; the step counts in `DONE` do.
- **Delivery:** 1.156 mL per turn (mean). Multiplying that by 400 rpm gives about 462 mL/min, which is a calculation and was not measured.
- **Spread:** the step counts match to within 0.5 steps, so the 4 mL gap between trials comes from the reading or the tube, not the motor.

Files: `s7_flow.csv`; raw serial log `raw/01_bench_session.log` (every line, UTC time, including the four priming runs on pump 3).

## What did not happen in this session

- The main firmware (`chemshield_uno`) was **not** uploaded: the Uno ran `pump_bench_test` throughout.
- Pumps 1, 2 and 4 never ran, so they had no liquid and no weighing.
- No S2 calibration (no PCAL stored), and no 20 mL check or 19.5 mL cap decision.
- No pH probe calibration and no pH data. The Uno was never connected to the Pi in this session.
- No acid or base was used. So there was no t95, no S1 hold, no wet recovery and no Uno refusal test.
- The hardware e-stop is not fitted; the Hold pin is jumpered.

## Other files

| Path | What it is |
|---|---|
| `REPORT_STATUS.md` | Each result in the report draft against the data behind it |
| `raw/clock_sync_1.txt` | Pi clock set from the Mac: 6 ms apart |
| `tools/uno_session.py` | Holds the serial port open and logs every line |
| `tools/analyse_s2.py` | S2 calculation, ready for when the weighings are done (not used yet) |
| `simulation_NOT_rig_evidence/` | **Simulation, not rig data.** The dry runs of the planned trials, and the 600-event batch at 120 mL/min |

## Conditions

- Rig: Uno + CNC Shield V3 at firmware branch commit a4082f6, 1/4 step, Vref as recorded on 2 Nov, 12 V fan on.
- Liquid: distilled water, room temperature not recorded.
- Network: a borrowed hotspot given the same name and password as Belal's, so the Pi joined it. The Pi was reachable, but it was not part of this measurement.
- Belal reported the drivers cool after the runs.
