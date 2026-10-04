# Attainment table: every constraint and specification

Team M016 · ChemShield · KFUPM Senior Design · Preliminary Prototype Review, 5 Oct 2026. Data as of 4 Oct 2026.

**How to read it.** `MET = x` means the requirement is satisfied and *x* is the value we measured or calculated against the limit. Each row links to its folder; open `TEST_SHEET.md` there for the full spec text, the test procedure step by step and the result. Items we have not proven say so in capitals.

**11 of the 14 items in the project list are MET.** The course asks for more than 50% (at least 8).

---

## The nine items (the PPR list)

| # | Item | Test ID | Requirement (short) | Limit | Result | What it rests on | Folder |
|---|---|---|---|---|---|---|---|
| 1 | **C1** (CHE constraint) | CHE-AT-03 | Only lab-approved dilute acid and base, at most 5 wt% | ≤ 5 wt% | **MET = 1.96 wt%** | Calculation for every bottle, the gateway only accepts the four listed bottles, approval confirmed 1 Oct. Approval scan, label photos and titration are still to attach | [01_C1_approved_dilute_reagents](01_C1_approved_dilute_reagents/) |
| 2 | **C2** (ICS constraint) | ICS-AT-01 | Every actuator command passes through the gateway, the only control path | only the gateway path works | **MET = 8 of 8 checks, in two runs** (ports 22 and 8000 only, 401 for unsigned and wrong-key requests, SSH key-only, IP forwarding 0, nothing reached the Uno) | Real rig: Raspberry Pi 5 and Uno, tested from a laptop on 4 Oct | [02_C2_gateway_sole_control_path](02_C2_gateway_sole_control_path/) |
| 3 | **C3** (ISE constraint) | ISE-AT-01 | Recovery uses at most 50 mmol of reagent | ≤ 50 mmol | **MET = 41.7 mmol** at most (600 recoveries, 0 over 50, mean 29.6) | Simulation (600 events) and software tests of the gateway's limit. A live total from the 5 L tank is still to add | [03_C3_max_50mmol_per_recovery](03_C3_max_50mmol_per_recovery/) |
| 4 | **Spec 1** (CHE) | CHE-AT-04 | pH held between 6.5 and 7.5 for 10 minutes | 600 s | **NOT YET TESTED** | The software is ready and tested; the 10-minute run on the real tank has not been done | [04_S1_ph_hold_10min](04_S1_ph_hold_10min/) |
| 5 | **Spec 3** (ICS) | ICS-AT-02 | At least 99% of replayed or stale commands rejected | ≥ 99% | **MET = 100%** (2,000 of 2,000) | The real station code attacked over HTTP, 3 Oct. A repeat against the Pi over Wi-Fi is still to do | [05_S3_replay_stale_rejected](05_S3_replay_stale_rejected/) |
| 6 | **Spec 4** (ICS) | ICS-AT-03 | Event class and risk score within 3 s | ≤ 3,000 ms | **MET = 1.65 ms** slowest of 1,000 decisions | Real hardware: Raspberry Pi 5, 3 Oct, plus live rig decisions on 2 Oct | [06_S4_class_and_score_within_3s](06_S4_class_and_score_within_3s/) |
| 7 | **Spec 5** (ISE) | ISE-AT-03 | System Usability Scale score of at least 80 | ≥ 80 | **DATA PENDING** | The HMI, the study kit and the scoring script are ready; the participants' forms and the mean are to be added (Hattan) | [07_S5_sus_at_least_80](07_S5_sus_at_least_80/) |
| 8 | **Spec 7** (CHE) | CHE-AT-01 | Pump's manufacturer-rated maximum flow at most 500 mL/min | ≤ 500 mL/min | **MET = 65 mL/min** (rated) | The pump's label and its rated 19 to 65 mL/min. The datasheet page and the three measured runs are still to attach | [08_S7_pump_max_flow](08_S7_pump_max_flow/) |
| 9 | **INT-Spec 1** (integrated) | INT-AT-01 | Safe-recovery mode within 2 s of a confirmed unsafe event | ≤ 2,000 ms | **MET = 1.1 ms** (the HMI showed it at 327 ms) | Real rig on 4 Oct (real probe, Uno, Pi, laptop HMI) and 100 simulated events | [09_INT-S1_recovery_mode_within_2s](09_INT-S1_recovery_mode_within_2s/) |

## Extra items we also have evidence for

These are not on the list of nine. Each folder name starts with `EXTRA_`.

| # | Item | Test ID | Requirement (short) | Limit | Result | What it rests on | Folder |
|---|---|---|---|---|---|---|---|
| 10 | **Spec 2** (CHE) | CHE-AT-02 | Each dose at most 20 mL, at least 15 s of mixing before the next | ≤ 20 mL, ≥ 15 s | **MET**: doses over 20 mL rejected, a second dose within 15 s rejected, accepted again at exactly 15.0 s | The gateway's own rules, shown by software tests, by the live rig on 2 Oct and by the 3 Oct attack run | [EXTRA_S2_dose_cap_and_mixing_wait](EXTRA_S2_dose_cap_and_mixing_wait/) |
| 11 | **Spec 6** (ISE) | ISE-AT-02 | At least 95% of recoveries finished within 300 s | ≥ 95% | **MET = 100%** (600 of 600; mean 95.5 s, slowest 128.7 s) | Simulation. At the real pump's 65 mL/min: 598 of 600 (99.7%) | [EXTRA_S6_recovery_within_300s](EXTRA_S6_recovery_within_300s/) |
| 12 | **INT-Spec 2** (integrated) | INT-AT-02 | pH back inside 6.0 to 8.5 within 5 min of an unsafe event | ≤ 300 s | **MET = 600 of 600**, slowest 128.7 s | Simulation. At 65 mL/min: 598 of 600 | [EXTRA_INT-S2_ph_restored_within_5min](EXTRA_INT-S2_ph_restored_within_5min/) |
| 13 | **INT-Spec 3** (integrated) | INT-AT-03 | No overshoot past pH 5.5 or 9.5 in at least 90% of scenarios | ≥ 90% | **MET = 100%** (600 of 600); closest approach 1.15 pH units from the limit | Simulation, also at 65 mL/min | [EXTRA_INT-S3_no_far_side_excursion](EXTRA_INT-S3_no_far_side_excursion/) |

## The rest of the project list

| # | Item | Requirement (short) | Result |
|---|---|---|---|
| 14 | **Spec 9** (ISE) | Reduce reagent use by at least 15% against a defined PI-controller approach | **NOT MET: not attempted.** The PI baseline to compare with has not been approved, so there is nothing to measure (`docs/ChemShield_PPR_Full_Marks_Plan.md`) |
| (none) | **Spec 8** | Deleted from the project | Not part of the count |

---

## By department

| Department | Constraint | Specifications we present | Extras |
|---|---|---|---|
| **CHE** | C1: **MET = 1.96 wt%** | Spec 7: **MET = 65 mL/min** (rated) | Spec 2: MET · Spec 1: NOT YET TESTED |
| **ICS** | C2: **MET = 8 of 8, twice** | Spec 4: **MET = 1.65 ms** | Spec 3: **MET = 100%** |
| **ISE** | C3: **MET = 41.7 mmol** | Spec 5: DATA PENDING; backup Spec 6: **MET = 100%** (simulation) | none |
| **Integrated** | | INT-Spec 1: **MET = 1.1 ms** | INT-Spec 2: MET · INT-Spec 3: MET |

## How strong is each piece of evidence

The course ranks evidence from 0 (words, sketches, calculations) to 9 (the physical prototype or a working demo at the presentation); simulation plus data counts at 6 to 7, and a calculation alone does not count (`docs/ChemShield_PPR_Full_Marks_Plan.md`, section 1).

| Kind | Items |
|---|---|
| **Real rig, real hardware, with data** | C2, Spec 4, INT-Spec 1; Spec 2 (rig records on 2 Oct) |
| **Real software on a laptop, with data** | Spec 3 (to repeat on the Pi) |
| **Simulation with data** | C3, Spec 6, INT-Spec 2, INT-Spec 3 (the pH table is a placeholder until the Aspen export) |
| **Calculation and paperwork** | C1 (becomes strong once the approval scan, label photos and titration are attached), Spec 7 (rating; becomes strong with the measured runs) |

## What is still open

| Item | What is missing | Who |
|---|---|---|
| C1 | Approval scan, bottle-label photos, titration values | Abdulkarim |
| Spec 7 | Datasheet page, the three measured 60 s runs | Abdulkarim |
| Spec 5 | Participants' SUS forms and the mean score | Hattan |
| Spec 1 | The 10-minute hold on the real tank (needs a calibrated probe) | Abdulkarim, Belal |
| C3 | A live total: one recovery on the 5 L tank with the planner's doses added by hand | Belal |
| Spec 3 | The same attack run against the Pi over Wi-Fi | Belal, Khalid |
| Probe | Two-point calibration and a quiet signal: on 4 Oct the new probe was noisy and calibrated at pH 7 only | Belal |
| Uno | It reports a lost heartbeat every few seconds to minutes; it did not affect INT-Spec 1, cause not found | Belal |

How to run the live demo and repeat any of the tests: [SETUP.md](SETUP.md). What each test proves and how: [EVIDENCE_EXPLAINED.md](EVIDENCE_EXPLAINED.md).
