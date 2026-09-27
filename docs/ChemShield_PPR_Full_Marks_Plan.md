# ChemShield PPR Plan: Aiming for Full Marks (Team M016)

**PPR: Monday 5 Oct 2026, EXPO style.** Built from the three files in `PPR Prep/` (rubric table, PPR expectations, Testing, Evaluation and Validation guide) and Table 1 of the Second Report Installment. Setup: Uno + Raspberry Pi 5 + pumps, water only, simulated pH (see `ChemShield_MVP_Plan.md`).

---

## 0. What you bring and present on 5 Oct (the deliverable)

The PPR is **EXPO style**: you stand at a booth and graders walk up. It is a **preliminary** prototype. The rubric grades **which constraints and specs you can prove**, not whether the whole plant is built. **You are not expected to show all 4 pumps with real acid and base.**

Your booth has four things, all ready by **Sun 4 Oct**:

| # | Deliverable | What it is | Why |
|---|---|---|---|
| 1 | **Live demo station** | The **Raspberry Pi running the whole software system**: gateway, firewall, Model A, MILP redosing, HMI, and the simulator for the **full 4-channel process** (bulk and fine acid and base). It is connected to a **small physical rig**: Uno, **2 real pumps** moving **water**, E-stop, bucket, labelled bottles, tray, and a balance. The real pumps stand in for the bulk acid and bulk base channels; the other two channels run in the simulator. | Rank 9 evidence: a working prototype and a working simulation shown at the presentation. |
| 2 | **Evidence slide deck** (8–10 slides on the laptop or a second screen) | 1 title + system diagram; 1 attainment table; then **one slide per department** (CHE, ICS, ISE, integrated), each with the 1-minute videos embedded and the data plots next to them; 1 "what is simulated vs real"; 1 next steps to the FPR. | Rank 8 backup for every item, in case something fails live, and a guide for your talk. |
| 3 | **Printed attainment table + test sheet binder** | The Section 4 table with measured numbers, plus one signed test sheet per item. | Rubric row 2 is literally "Table of ALL project constraints, specifications and integrated specifications attainment". |
| 4 | **Data folder** on the laptop | The CSV behind every plot, named by test ID. | If a grader asks "show me the numbers", you open the file. |

What the grader sees: the attainment table first, then each owner demos their items live (Section 6), with the matching slide ready if anything breaks.

---

## 1. How the PPR is graded

| Rubric row (100 points each) | What full marks (Exemplary) requires | What that means for us |
|---|---|---|
| **1. Prototype progress for each department** | "More than 1 constraint and 1 specification met with a satisfactory strength of evidence" | CHE, ICS and ISE are graded separately. Each department owns one constraint, so **each department proves its constraint + 2 of its specifications.** |
| **2. Table of all constraints and specifications for the whole team** | "More than 50% met with a satisfactory or better strength of evidence" | We have 14 items (S8 is deleted), so we need **at least 8**. We target 13. |

**Strength of evidence** (expectations slide 4, ranked 0 = weakest to 9 = strongest):

| Rank | Evidence type | Counts for the prototype? |
|---|---|---|
| 0–2 | Words, sketches, calculations | No |
| 3 | Simulation or CAD alone | No ("acceptable for design, not evidence for prototype") |
| 4–5 | Picture or video of the demo | Weak |
| 6–7 | Simulation + data, or picture + data | Yes |
| 8 | **Video of the demo + data** | Strong |
| 9 | **Physical prototype or working simulation demo at the presentation** | Strongest |

**Rule for every item:** show it **live at the booth** (rank 9), and keep a **1-minute video + a data file** as backup (rank 8). A live, working simulation counts as rank 9, the same as hardware. A static Aspen result counts only as rank 3.

---

## 2. All constraints and specifications: what we claim and how

Names are copied from Table 1 of the Second Report Installment. **Tier 1** = the minimum needed for full marks (3 per department, 9 of 14 = 64%). **Tier 2** = extra margin that comes almost free once the simulator runs.

| ID | Full name (Table 1) | Dept | Owner | Tier | Proven by |
|---|---|---|---|---|---|
| **C1** | Use only laboratory-approved acid/base reagents at concentrations not exceeding 5 wt%. | CHE | Abdulkarim | 1 | Signed approval + wt% calculation + labelled reservoirs |
| **C2** | The secure gateway shall be the sole authorised path for every actuator command. | ICS | Khalid | 1 | Live bypass attempts that all fail |
| **C3** | Recovery shall use no more than 50 mmol of corrective reagent per event. | ISE | Hattan | 1 | Live recovery with mmol counter + 600-event batch |
| **S1** | Maintain pH 6.5–7.5 for 10 min under nominal operation. | CHE | Abdulkarim | 2 | Live simulator pH hold + Aspen check |
| **S2** | Each corrective dose ≤20 mL; ≥15 s mixing before another dose. | CHE | Abdulkarim (with Belal) | 1 | Real pump on a balance |
| **S3** | Reject ≥99% of replayed or stale commands. | ICS | Khalid | 1 | Live attack script with counters |
| **S4** | Assign incident class and associated risk score within 3 s. | ICS | Belal | 1 | Model A on the Pi with latency shown |
| **S5** | Mean System Usability Scale (SUS) score ≥80. | ISE | Hattan | 1 | Usability study with 5–8 students |
| **S6** | Complete ≥95% of recovery events within 300 s. | ISE | Hattan | 1 | Live recovery + 600-event batch |
| **S7** | Selected pump manufacturer maximum flow ≤500 mL/min. | CHE | Abdulkarim (with Belal) | 1 | Datasheet + measured flow on a balance |
| **S9** | Reduce reagent use by ≥15% relative to a defined PI approach. | ISE | — | **Skip** | Report as "Not met: PI baseline pending approval" |
| **INT-S1** | Enter safe recovery mode within 2 s after confirming a successful unsafe event. | Integrated | Belal | 2 | Timestamped state change, live + 100-event batch |
| **INT-S2** | Restore pH to 6.0–8.5 within 5 min after a successful unsafe event. | Integrated | Hattan | 2 | Live recovery + 600-event batch |
| **INT-S3** | No far-side excursion beyond pH 5.5/9.5 in ≥90% of validated scenarios. | Integrated | Hattan | 2 | 600-event batch count + worst-case plot |

**Per department:** CHE = C1, S2, S7 (+ S1). ICS = C2, S3, S4. ISE = C3, S5, S6. Team total if everything lands: **13 of 14 (93%)**.

**Risks:** C1 is the weakest item because it's proven with documents rather than a test, which is why CHE also has S1. Only S2 and S7 need physical pumps. If the hardware fails, S2 can still be shown in the simulator, so no department falls below the minimum.

---

## 3. What each person builds, films and shows

Each row reads: build this, then capture this evidence, and here is what it proves to the grader. **"Film"** means a ≤1-minute video. **"Data"** means a CSV or table saved next to the video, plus a filled test sheet (Section 5). **Do both for every item:** film it before the PPR (video + data is the backup, evidence rank 8), then show it live at the booth (rank 9). If the live demo fails on the day, play the video.

### Belal: AI, integration, electrical programming and wiring

| Build | Film / show | Data to save | What the evidence proves |
|---|---|---|---|
| **Model A** retrained on simulator data (using Abdulkarim's Aspen pH table), running **on the Pi** with a timeout. The HMI shows label, risk score and latency. | Film: send a dose request from the HMI; the Model A label, score and decision time appear. Show live at the booth. | Latency of 1,000 requests: CSV + histogram (average, 99th percentile, maximum). | **S4:** every command gets a class and a risk score in milliseconds, far under the 3 s limit. |
| **Uno firmware + pump wiring** (2 pumps, driver shield, 24 V supply, E-stop). The Uno enforces the 20 mL step cap, the 15 s lockout and one pump at a time, and stops if the Pi goes silent. | Film: press the E-stop mid-dose; the pump stops instantly and does not restart by itself. | Serial log of the Uno's accept and reject replies. | Supports **C2** and safety: the pumps have a last hardware gate that software can't bypass. Also makes **S2** and **S7** possible. |
| **Pi ↔ Uno bridge and full integration** (HMI → gateway → Model A → Uno → pump), with timestamps on every state change. | Film: inject an acid upset; the state banner switches to RECOVERY with the elapsed time shown. | Delay from "event confirmed" to "RECOVERY" for 100 events: CSV with the maximum. | **INT-S1:** the system enters safe recovery mode within 2 s. |
| One **integration test sheet** covering the whole chain. | Show the signed sheet. | — | Shows the grader the modules work together (the Testing guide asks for integration tests). |

### Khalid: network, gateway/firewall, threat model, HMI build

| Build | Film / show | Data to save | What the evidence proves |
|---|---|---|---|
| **Network:** Pi Wi-Fi hotspot, HTTPS, routing off, firewall allowing only ports 443 and 22. | Film: from a separate laptop, `nmap` shows only 443/22 open, and trying to reach the Uno or pumps directly fails. Repeat live at the booth. | nmap output, the firewall rule list, and a bypass test sheet (each route tried, each blocked). | **C2:** there is no way to command a pump except through the gateway. |
| **Gateway rules** (schema, role, signature, ±2 s freshness, nonce, sequence, rate, state, ≤20 mL, ≤50 mmol, 15 s lockout, Model A, certificate) + the hash-chained audit log. | Film: an unsigned request is rejected with its reason code. | Unit test results for each rule. | **C2** and **S2** (the 20 mL and 15 s rules), and **C3** (the 50 mmol rule) at the software level. |
| **Attack script** that sends replayed, stale, oversize, unsigned and burst commands. | Film: run it live; the HMI counters read 2,000 of 2,000 attacks rejected and 200 of 200 valid commands accepted. | CSV of every message with its result and reason code. | **S3:** at least 99% of replayed or stale commands are rejected. The valid commands show the gateway isn't simply blocking everything. |
| **Threat model:** one table of assets, entry points, threats, mitigation, and the test that proves each mitigation. | Show printed at the booth. | — | Backs up **C2** and **S3** by showing the tests cover the real threats. (On its own it's only rank 1, so pair it with the tests above.) |
| **HMI implementation** of Hattan's design. | Used in every live demo. | — | Makes every other live demo possible, and is what the **S5** usability study tests. |

### Hattan: QC, MILP redosing, HMI design

| Build | Film / show | Data to save | What the evidence proves |
|---|---|---|---|
| **Plant simulator + batch runner** (from your existing SIL model, using Abdulkarim's chemistry equation) and **MILP redosing** (`plan_next_dose`, which escalates when no safe dose exists). | Film: inject the largest acid upset; the MILP doses, and the mmol counter rises but stays under 50; a request that would pass 50 is rejected (LIMIT). | 600-event batch CSV: mmol per event with the maximum. | **C3:** recovery never uses more than 50 mmol, and the limit is enforced, not just observed. |
| Same simulator, with a recovery timer in the HMI. | Film: one full recovery with the timer; pH returns to 6.0–8.5. | 600-event batch: share finished within 300 s, a histogram, and an I-MR control chart. | **S6** (at least 95% within 300 s) and **INT-S2** (pH restored to 6.0–8.5 within 5 min). |
| Batch analysis of far-side excursions. | Show the worst-case pH trajectory plot. | Count of the 600 events that crossed pH 5.5 or 9.5. | **INT-S3:** at least 90% of scenarios have no far-side overshoot. |
| **HMI design** (layout, alarms, buttons) + a **SUS study kit** (5 task script, standard 10-question SUS form). | Film one participant session. Bring the completed forms. | SUS score sheet for 5–8 students, with the mean. | **S5:** the mean SUS score is at least 80, so operators can use the HMI. |
| **Attainment table** (Section 4), filled in with measured numbers. | Print it; it opens the booth demo. | — | Rubric row 2: shows the grader at a glance that more than 50% are met, and where each item's evidence is. |

### Abdulkarim: chemistry model, physical setup, Aspen

| Build | Film / show | Data to save | What the evidence proves |
|---|---|---|---|
| **Physical setup:** bucket, 4 labelled bottles, tubing, tray (water only). **Pump calibration** with Belal (mL per step). | Film: run a pump at maximum speed for 60 s into a beaker on the balance. Show the datasheet page next to it. | 3 runs: grams → mL/min, plus the datasheet value. | **S7:** the pump's maximum flow is at most 500 mL/min, by datasheet and by measurement. |
| Same rig, driven through the gateway and Uno. | Film: a 25 mL request is rejected; a 20 mL request puts about 20 g on the balance; a second dose inside 15 s is rejected; after 15 s it is accepted. Repeat live. | 5 repeats: requested vs delivered mL, and the lockout times. | **S2:** each dose is at most 20 mL and waits at least 15 s for mixing, on real hardware. |
| **Reagent approval:** request to the CHE supervisor, wt% calculation (0.5 M HCl ≈ 1.8 wt%, 0.5 M NaOH ≈ 2.0 wt%), labelled reservoirs. If the lab allows, prepare the dilute solutions under supervision. | Show: signed approval, the calculation, and a photo of the labelled reservoirs (or the prepared solutions with the preparation record). | Preparation record. | **C1:** only approved reagents at ≤5 wt% are used. |
| **Chemistry equation** (pH from the acid/base balance) inside the simulator + an **Aspen titration model**. | Show: plot of Aspen's pH curve over the simulator's pH curve. Film a 10-minute normal-operation hold; the simulator also runs live at the booth all day. | 10-minute pH log (CSV + plot) and the Aspen vs simulator data. | **S1:** pH stays in 6.5–7.5 for 10 min. The overlay proves the simulator's chemistry matches Aspen, which makes every simulated result (C3, S6, INT-S2, INT-S3) credible to the CHE reviewer. |

**About Aspen:** a filmed Aspen run on its own is only rank 5–6 evidence, so use Aspen to **validate** the simulator, not as the main demo. Aspen can't simulate cyber attacks, so the AI training scenarios come from the Python simulator, which uses Aspen's pH table.

---

## 4. The attainment table to bring (rubric row 2)

**Test ID key:** codes like `ICS-AT-01` name the signed test sheet for that item (Section 5). The first part is the owning department (CHE, ICS, ISE, or INT for integrated). "AT" means Acceptance Test, the Testing guide's term for a test that checks a constraint or specification. The number counts the tests within that department.

Use the column layout from the expectations slide, and put the **measured number** in brackets (like the slide's "Met (>1500 mAh)"). S7 is the only off-the-shelf item. Keep this table identical to Table 4 of the report.

| Constraint / Specification | Off-the-shelf | Project specific | Responsible dept | Evidence location |
|---|---|---|---|---|
| C1: Laboratory-approved acid/base reagents ≤5 wt% | | Met (1.8–2.0 wt%, approval signed) | CHE | CHE-AT-03, approval form, photo |
| C2: Gateway is the sole authorised path for every actuator command | | Met (0 of N bypass routes succeeded) | ICS | ICS-AT-01, nmap video, bypass sheet |
| C3: ≤50 mmol corrective reagent per event | | Met (max X mmol of 600 events) | ISE | ISE-AT-01, batch CSV, live demo |
| S1: pH 6.5–7.5 for 10 min, nominal operation | | Met (min/max pH over 10 min) | CHE | CHE-AT-04, pH log, Aspen overlay |
| S2: Dose ≤20 mL; ≥15 s mixing between doses | | Met (max X mL delivered; lockout X s) | CHE | CHE-AT-02, video, balance data |
| S3: Reject ≥99% of replayed or stale commands | | Met (2000/2000 rejected) | ICS | ICS-AT-02, attack CSV, video |
| S4: Incident class and risk score within 3 s | | Met (p99 X ms) | ICS | ICS-AT-03, latency CSV |
| S5: Mean SUS score ≥80 | | Met (mean X, n = X) | ISE | ISE-AT-03, SUS forms |
| S6: ≥95% of recovery events within 300 s | | Met (X% of 600) | ISE | ISE-AT-02, batch CSV, I-MR chart |
| S7: Pump manufacturer maximum flow ≤500 mL/min | Met (datasheet X; measured X mL/min) | | CHE | CHE-AT-01, video, datasheet |
| S9: ≥15% less reagent than a defined PI approach | | Not met (PI baseline pending approval) | ISE | — |
| INT-S1: Safe recovery mode within 2 s of a confirmed unsafe event | | Met (max X s over 100 events) | All | INT-AT-01, timestamp CSV |
| INT-S2: pH restored to 6.0–8.5 within 5 min | | Met (max X s of 600) | All | INT-AT-02, batch CSV |
| INT-S3: No far-side excursion past 5.5/9.5 in ≥90% of scenarios | | Met (X% of 600) | All | INT-AT-03, batch CSV, worst-case plot |

---

## 5. Test sheets (one per item)

The Testing guide expects one signed sheet per test. Test IDs: CHE-AT-01…04, ICS-AT-01…03, ISE-AT-01…03, INT-AT-01…03.

**All 14 sheets are ready** in `build-plan/test-sheets/` (one `.md` and one printable `.docx` each, plus `ChemShield_PPR_Test_Binder.docx` with all of them and `README.md` as the index). Every sheet follows the same shape:
1. Header: test ID, name, the full spec text, owner, tester, witness, date, software version.
2. One sentence on what the test proves.
3. The words used on the sheet, explained.
4. A setup checklist.
5. Steps: what you do (the exact command), expected result, actual result (numbers, not ticks), pass/fail.
6. A result box with the pass rule, then signatures.
7. The list of evidence files to save.

---

## 6. Booth demo script (about 8 minutes; each owner presents their own items)

1. **Hattan (1 min):** the attainment table. "13 of 14 met; here is the evidence for each."
2. **Khalid (2 min):** C2 (nmap and a direct pump attempt both fail), then S3 (run the attack script live; the counter reads 2000/2000 rejected).
3. **Belal (1.5 min):** S4 (a request shows the Model A label and a latency in milliseconds). A valid dose moves real water. Press the E-stop: the pump stops instantly.
4. **Abdulkarim (1.5 min):** S7 and S2 on the balance, C1 approval and reservoirs, the Aspen vs simulator overlay, S1 (point at the pH hold trend that has been running since the booth opened).
5. **Hattan (2 min):** inject an acid upset. INT-S1 (recovery within 2 s), the MILP doses, the mmol counter stays under 50 (C3), pH returns within 5 min (INT-S2, S6), then the batch plots (S6, INT-S3) and the S5 SUS result.

Say plainly: "pH is simulated and its chemistry is validated against Aspen; the pumps, safety chain and network are real; wet chemistry comes after supervisor approval."

**Booth checklist:** Pi 5 + power supply, laptop + charger, Uno rig + pumps + E-stop + 24 V supply, bucket/bottles/tray with water, balance, paper towels, extension cord, printed attainment table and test sheets, SUS forms, and all videos saved offline on the laptop.

---

## 7. How to work together: separately, then integrated

**Build separately, integrate together.** Each person builds their part on their own laptop, in parallel. The parts only fit together if everyone agrees on the **messages between them** before writing code. So the first job, **as a group (1 hour, today or tomorrow)**, is to fix these five interface contracts and put them in `docs/interfaces.md` in the shared repo:

| Interface | From → To | Agree on | Owners |
|---|---|---|---|
| **I1 Dose request** | HMI / MILP → gateway | JSON fields (the FDR slide 22 format), units, reason codes for rejection | Khalid + Hattan |
| **I2 Process state** | simulator → everyone | JSON every 1 s: pH, temperature, level, tank mmol, state, time | Hattan + Abdulkarim |
| **I3 Model A call** | gateway → Model A | the 16 features in, label + score + latency out, timeout | Belal + Khalid |
| **I4 Redosing call** | simulator state → MILP → dose request | input state, output DOSE or ESCALATE | Hattan |
| **I5 Pump command** | gateway → Uno | serial line format, replies, heartbeat | Belal + Khalid |

Each person can then test their part against **fake inputs** that follow the contract, without waiting for the others. For example, Khalid can test the gateway with a fake Model A that always answers "acceptable".

**Organizing it:**
- **One GitHub repo**, one folder per part (`gateway/`, `model_a/`, `redosing/`, `sim/`, `hmi/`, `firmware/`). Belal owns the `main` branch and merges.
- **One task board** (GitHub Projects, Trello or a shared checklist) listing every row of the Section 3 tables, with an owner and a done box.
- **15-minute check-in every day** in the group chat: what's done, what's blocked, which interface changed.
- **Three whole-team sessions in the lab:**
  1. **Integration** (around Wed 30 Sep): plug the parts together and fix the mismatches.
  2. **Evidence filming** (Fri 2 Oct): everyone films and fills in their test sheets.
  3. **Rehearsal** (Sat 3 Oct, again Sun 4 Oct).
- **Belal is the integrator**, because the Pi and the Uno bridge sit in the middle of every data flow.

### 7.1 What each person does alone, what is done together, and what has to wait

**Rule of thumb:** code is written alone against the agreed interfaces. Anything with tubing, wires, the balance or the single Pi is done in person with the other person it touches. A few things must wait for someone else's output. Until then, you use a stand-in.

**A. Alone, starting now (no waiting on anyone)**

| Person | Work on your own laptop or at home | Tested with (stand-in until the real part arrives) |
|---|---|---|
| **Belal** | Model A: `features.py`, episode generator, labelling, training script. Uno firmware (DOSE / HB / STATUS, 20 mL cap, 15 s lockout, heartbeat stop). Pi-to-Uno bridge. | A simple formula stand-in for the simulator. The Uno alone on your laptop's USB, with the serial monitor and the onboard LED in place of a pump. |
| **Khalid** | Gateway rules + unit tests, audit log, attack script, threat model, HMI build. | A fake Model A that always answers ACCEPTABLE, and a fake tank-state feed (I2). |
| **Hattan** | Simulator core, MILP redosing, batch runner, QC charts, HMI design mock-up, SUS task card. | Placeholder pH formula until the Aspen tables arrive (same file format, so it's a drop-in swap). |
| **Abdulkarim** | Aspen sensitivity tables (Guide Part 1), reagent approval request + wt% sheet, collecting the bucket, bottles, tubing and tray. | Nothing needed. |

**B. Together, in person (pairs)**

| What | Who | Why together |
|---|---|---|
| **Pump wiring + first run** | Belal (electrical: Uno, driver, 24 V supply, E-stop) **with** Abdulkarim (tubing, bottles, tray) | The pump must be wired *and* plumbed before it can run. One lab session. Khalid can join if you want a second pair of hands on the wiring. |
| **Pump calibration + CHE-AT-01** | Abdulkarim + Belal | One person runs the Uno command, the other weighs. The mL/s number goes straight into the Uno and the gateway. |
| **Network and firewall on the Pi** | Khalid + Belal | There is one Pi. Agree who has it when, and set up the hotspot and firewall together. |
| **Simulator vs Aspen check (CHE-AT-04 Part B)** | Hattan + Abdulkarim | Abdulkarim knows what Aspen should say; Hattan runs the simulator. |
| **HMI design → build handoff** | Hattan + Khalid (30 min) | Hattan explains the layout and alarms; Khalid builds it. |
| **Model A inside the gateway (I3)** | Belal + Khalid | Plug Model A into Khalid's gateway and check the 16 features arrive correctly. |

**C. Things that must happen in order**

| Order | This… | …must be done before this | Stand-in meanwhile |
|---|---|---|---|
| 1 | Interfaces agreed (all, at the meeting) | Everything else | None: do this first |
| 2 | Aspen tables (Abdulkarim) → real simulator (Hattan) | Final Model A dataset + training (Belal) → ICS-AT-03 | Belal builds and tests the whole pipeline on the formula stand-in, then regenerates the dataset in minutes |
| 3 | Real simulator + MILP (Hattan) | 600-event batch → ISE-AT-01, ISE-AT-02, INT-AT-02, INT-AT-03 | Hattan tests the MILP on the placeholder |
| 4 | Pump wired and plumbed (Belal + Abdulkarim) | Calibration (CHE-AT-01) → calibration loaded → CHE-AT-02 | Belal tests the firmware with the LED |
| 5 | Gateway + firewall on the Pi (Khalid) | ICS-AT-01, ICS-AT-02 | Khalid tests on his laptop first |
| 6 | HMI usable (Khalid, from Hattan's design) | SUS study with 5–8 students (ISE-AT-03) | None. **This is the tightest chain:** the HMI must be usable by about Thu 1 Oct so the study can run before filming. |
| 7 | Reagent approval request sent (Abdulkarim, Mon 28 Sep) | CHE-AT-03 | Waits on the supervisor, so send it first thing |
| 8 | All parts merged on the Pi (Belal) | Integration day: **INT-AT-04 first**, then INT-AT-01 and the live parts of INT-AT-02 | None |

**The two chains to watch:** Aspen tables → simulator → Model A (steps 2–3), and HMI → SUS study (step 6). If either slips, everything after it slips, so check these two at every daily check-in.

**D. Whole team:** the interface meeting, integration day (Wed 30 Sep), filming and test sheets (Fri 2 Oct), and rehearsals (Sat 3 and Sun 4 Oct). The signed test sheets are in `build-plan/test-sheets/`; each tester should not be the sheet's writer.

---

## 8. The simulator, Aspen, and why the simulation is credible

### Why Python, if Aspen already models the whole system?
Aspen Plus is the **chemistry reference**. It can't be the live demo engine, for three reasons:
1. The demo needs your **real gateway, Model A and MILP code** to control the process in real time. Aspen can't receive live commands from the Pi, and it doesn't run on the Pi.
2. Aspen doesn't simulate network attacks.
3. It runs on Windows only.

So the setup is: **Aspen proves the chemistry, and Python runs the chemistry live.**

### What is real and what is simulated
Only the **tank chemistry** is simulated. The gateway, firewall, attacks, Model A, MILP, HMI, Uno and pumps are all **real code and real hardware**, and they are tested exactly as they would run. The cyber attacks are **real messages sent over the real Wi-Fi to the real gateway**; they are not simulated. This setup is called hardware-in-the-loop, and it is a standard way to test control systems. Say this sentence at the booth.

### How to make the Python simulator credible (Abdulkarim + Hattan)
| Step | What to do | Evidence it produces |
|---|---|---|
| 1. Same equations as the report | Use the charge balance from Section 1.3 of the report (eq. 1.1–1.3). | Traceability to the approved design. |
| 2. Known-answer checks | For example, 10 mmol of HCl in 5 L gives 2 mM excess acid, so pH = 2.70. Check 5 such cases by hand calculation. | A unit test table. |
| 3. **Validate against Aspen** | Run the **same 10–20 cases in Aspen and in Python** (acid and base, bulk and fine, starting from neutral and from an upset). Plot them on one chart. Report the largest pH difference; aim for under 0.1–0.2 pH away from the steep neutral region. | **The key credibility plot.** It turns "Python simulation" into "a model validated against Aspen". |
| 4. Measured parameters | Use the **measured** pump mL per step and a **measured** mixing time (a dye or salt test in water in your bucket), not assumed values. | Shows the model reflects your actual hardware. |
| 5. State the limits | One slide: unbuffered water, dilute strong acid/base, 25 °C, and the probe is simulated until the pH kit arrives. | Honesty; the report already commits to this. |

If Aspen Plus Dynamics is available, run 2–3 **dynamic** upset-and-recovery cases in it as well, and overlay those pH-versus-time curves with Python's. That is even stronger evidence.

### Other simulation platforms (for reference)
| Platform | Can model | Suits you now? |
|---|---|---|
| **MATLAB/Simulink** (KFUPM licence) | pH process, control loops, attack injection as signals | Credible, but your code is in Python, so you would need to rebuild. Not before the PPR. |
| **AnyLogic / Arena / Simio** (ISE tools) | Discrete events, queues, operator workflow | Good for ISE workflow studies, but it can't test your real gateway or chemistry. |
| **MiniCPS**, **GRFICS** (open-source ICS security testbeds) | Simulated plant + simulated industrial network + attacks | Built for exactly this kind of research, but a week isn't enough to learn one. Worth citing, or trying before the FPR. |

**Recommendation:** keep the Python simulator for the PPR, because your real code has to be in the loop. Cite MiniCPS/GRFICS as related testbeds.

---

## 9. The Model A dataset: where it comes from and why it's credible

**No single source works on its own:**
- **Aspen** gives correct chemistry, but it has no dose commands, no attacks and no labels, and it is too slow to run thousands of episodes.
- **Public datasets** (SWaT and WADI from iTrust, HAI, Tennessee Eastman, BATADAL, and the Mississippi State ICS datasets) are real plants and real attacks, but none of them is a pH-dosing tank with your 16 features. You can't train Model A on them directly. SWaT/WADI access also needs a request form that takes days.

**Recommended approach (Belal, with Abdulkarim for the chemistry):**
1. **Generate** episodes with the Python simulator, which is **validated against Aspen** (Section 8). Include normal operation plus harmful scenarios: oversize dose, wrong direction, slow cumulative bias, dose during the mixing lockout, stale sensor, pump under-delivery.
2. **Label by physics, not by guessing.** A command is HARMFUL if the predicted pH after the dose crosses 5.5/9.5 or breaks a limit, UNCERTAIN if it falls inside a margin band or the data is stale, and ACCEPTABLE otherwise. The rule is written down, so anyone can check it.
3. **Add real-world noise:** real sensor-noise and timing patterns from **HAI** (a public dataset, which you already used at the FDR), plus **your own measured pump delivery errors** from the calibration runs.
4. **Split by episode** (whole runs, never rows), and **hold one attack type out of training entirely** to test on attacks the model has never seen.

**What makes it credible:**
| Check | How | Who |
|---|---|---|
| **Aspen agreement** | Run 30–50 generated scenarios through Aspen too. Report how often Aspen's pH gives the **same label** as the simulator's (target ≥95% agreement). | Abdulkarim |
| **Real hardware check** | Replay 20–50 scenarios on the rig with real pumps and water. Show the model's decisions are the same with real delivery data. | Belal |
| **Dataset card** | One page: how the data was made, its size, the labelling rule, the noise sources, and the limits. | Belal |
| **Honest metrics** | Harmful recall **and** benign false-block rate, with the held-out attack results. | Belal |
| **Public benchmark (optional, FPR)** | Train the same pipeline on HAI or SWaT to show the method also works on real plant data. | Belal |
