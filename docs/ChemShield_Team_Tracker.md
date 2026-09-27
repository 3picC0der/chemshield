# ChemShield PPR: Team Tracker (one page)

**Timeline:** build and test alone **Sun 27 → Tue 29 Sep, 11:59 pm** (push to the repo) → Belal integrates on the Pi and Uno in the lab **Wed 30 Sep** → final tests and filming on the integrated system **Thu 1 – Fri 2 Oct** → rehearse **Sat 3 – Sun 4** → **PPR Mon 5 Oct**.

## 1. What each member hands in by Tuesday 11:59 pm

Your understanding is almost right. The one change: **the final evidence videos and signed test sheets mostly come after integration**, because the graders need to see them running on the real Pi, Uno and pumps. By Tuesday each member hands in:

| ☐ | Hand-in | Example |
|---|---|---|
| ☐ | **Code in the repo**, in their own folder, that runs with one command written in the folder's README | `python -m sim.run --scenario nominal` |
| ☐ | **Proof it works alone:** passing unit tests + a rough 1-minute screen recording (practice, not the final video) | `pytest gateway/tests` all green |
| ☐ | **The data files their part produces** | Aspen CSV tables, 600-event batch CSV |
| ☐ | **The test sheets that don't need hardware, filled in** (see Section 3) | ICS-AT-02 dry run on a laptop |

## 2. The major components

| # | Component | Proves | Owner | Needs from someone else | How to avoid waiting |
|---|---|---|---|---|---|
| 1 | **Aspen pH tables** (CSV) | **S1** (via the simulator). Makes every simulated result (C3, S6, INT-S2, INT-S3) credible. | Abdulkarim | Nothing | Start Sunday. It feeds components 2, 3 and 7. |
| 2 | **Simulator** (live + batch) | **S1**, and with the MILP **C3**, **S6**, **INT-S2**, **INT-S3** | Hattan | Aspen tables (1) | Use a simple pH formula in the **same CSV format**, then swap in Aspen's file when it arrives. |
| 3 | **MILP redosing** | **C3**, **S6**, **INT-S2**, **INT-S3** | Hattan | Simulator state (2) | Built alongside the simulator; tested on the placeholder. |
| 4 | **Gateway + audit log + attack script** | **C2**, **S3**; also the software side of **S2** (20 mL, 15 s) and **C3** (50 mmol rule); **INT-S1** (switch to recovery) | Khalid | Model A (7) | A fake Model A that always says ACCEPTABLE. |
| 5 | **Network + firewall** | **C2** | Khalid | The Pi (only one) | Write the setup as a script and test it on a laptop or VM; Belal applies it on the Pi on Wednesday. |
| 6 | **HMI** (build) | **S5**; also the screen for every live demo | Khalid | Hattan's design; tank state (2) | Hattan sends the layout **Monday**. Use a fake tank-state feed. |
| 7 | **Model A** (dataset + training) | **S4** | Belal | Simulator (2) | Build the whole pipeline on the formula placeholder; regenerate the dataset in minutes once the real simulator lands. |
| 8 | **Uno firmware + Pi bridge** | **S2** (hardware gate), **C2** (last gate), **INT-S1** | Belal | Pumps wired (9) | Test on the Uno alone: its LED stands in for the pump, and the serial monitor shows the replies. |
| 9 | **Physical rig** (bucket, bottles, tubing, tray) + **pump calibration** | **S7**, **S2** | Abdulkarim (+ Belal for the wiring) | Lab time together | Collect the parts by Tuesday; wire, plumb and calibrate together on Wednesday. Use the datasheet flow until then. |
| 10 | **Reagent approval + wt% sheet** | **C1** | Abdulkarim | CHE supervisor | Send the request **Monday morning**. |
| 11 | **Threat model** | Supports **C2** and **S3** | Khalid | Nothing | — |
| 12 | **SUS kit** (task card + form) | **S5** | Hattan | Finished HMI (6) | Prepare the kit now; run the study Thursday on the integrated system. |

**Key:** C1 reagents ≤5 wt% · C2 gateway is the only path to the pumps · C3 ≤50 mmol per event · S1 pH 6.5–7.5 for 10 min · S2 dose ≤20 mL, ≥15 s mixing · S3 reject ≥99% replayed/stale · S4 class + risk score within 3 s · S5 SUS ≥80 · S6 ≥95% of recoveries within 300 s · S7 pump max flow ≤500 mL/min · INT-S1 recovery mode within 2 s · INT-S2 pH back to 6.0–8.5 within 5 min · INT-S3 no far-side excursion past 5.5/9.5 in ≥90%.

**Dependency chains to check daily:** Aspen tables → simulator → Model A (1 → 2 → 7), and HMI design → HMI build → SUS study (6 → 12). Everything else can be built in parallel.

## 3. Test sheets: before or after integration

| Can be done alone by Tuesday | Needs the integrated system (Wed–Fri) |
|---|---|
| **CHE-AT-03** Approved reagents (if approval arrives) | **CHE-AT-01** Pump flow, **CHE-AT-02** Dose cap and wait (pumps + balance) |
| **CHE-AT-04 Part B** Simulator vs Aspen | **CHE-AT-04 Part A** 10-minute pH hold (with the real redosing and gateway) |
| **ICS-AT-02** Replay/stale: dry run on a laptop | **ICS-AT-01** Only path, **ICS-AT-02** and **ICS-AT-03** final runs on the Pi |
| **ICS-AT-03** Model A timing: dry run on a laptop | **ISE-AT-03** SUS study (finished HMI + 5–8 students) |
| **ISE-AT-01**, **ISE-AT-02**, **INT-AT-03** batch parts (600 events) | **INT-AT-04** Whole chain first, then **INT-AT-01**, **INT-AT-02**, and the live parts of ISE-AT-01/02 |

## 4. Progress check (tick as it lands in the repo)

| Member | Code pushed | Tests pass | Data files | Practice video | Pre-integration sheets |
|---|---|---|---|---|---|
| Abdulkarim | ☐ Aspen CSVs | — | ☐ | ☐ | ☐ CHE-AT-03, ☐ CHE-AT-04 B |
| Hattan | ☐ sim, MILP, QC | ☐ | ☐ batch CSV | ☐ | ☐ ISE-AT-01/02, ☐ INT-AT-03 |
| Khalid | ☐ gateway, HMI, firewall script | ☐ | ☐ attack CSV | ☐ | ☐ ICS-AT-02 dry run |
| Belal | ☐ Model A, Uno firmware, bridge | ☐ | ☐ dataset + latency CSV | ☐ | ☐ ICS-AT-03 dry run |
