> **Moved (4 Oct):** the evidence files named below now live in one folder per spec under `evidence/`. Start at `evidence/README.md`. The old paths `evidence/ISE`, `evidence/INT` and the filled .docx sheets no longer exist.

# ISE hand-in — Hattan, 28 Sep

Section 3 of the PPR plan, the ISE rows. Everything here runs today with no hardware and
no Aspen tables, on a placeholder chemistry that is a drop-in swap.

---

## 1. What is in the repo

| Folder | What | One command |
|---|---|---|
| `sim/` | Tank simulator, live and batch, chemistry from the Aspen table | `python -m sim.batch --events 600 --seed 261 --out ISE-AT-01_batch.csv` |
| `sim/` | Booth demo: the tank recovering by itself in real time | `python -m sim.live --scenario acid_upset_max --autopilot` |
| `sim/tests/` | Known-answer chemistry checks (Guide Part 2, P8) | `python -m sim.tests.test_known_answers` → 15/15 |
| `redosing/` | I4 `plan_next_dose()`, the robust MILP | `python -m redosing.planner` |
| `redosing/qc/` | I-MR chart, reagent histogram, pH traces, far-side check | `python -m redosing.run_all` |
| `hmi/` | Design spec and wireframe for Khalid to build from | open `hmi/wireframe.html` |
| `evidence/ISE`, `evidence/INT` | Batch CSVs, figures, filled test sheets, SUS kit | — |

`python -m redosing.run_all` does the whole ISE evidence set in about a minute and prints
the numbers to copy onto the sheets.

---

## 2. The three data formats, so nobody has to guess

### 2.1 I2 and I4 — unchanged from `docs/interfaces.md`

I built to the contract as written. `sim.live` emits exactly this, once a second, as one
JSON object per line on stdout and, with `--udp HOST:PORT`, as one datagram per message:

```json
{"t": 1790000000.0, "ph": 3.12, "temp_c": 25.0, "level_ok": true,
 "excess_mmol": -30.4, "state": "RECOVERY", "event_mmol_used": 20.0, "source": "SIM"}
```

It adds five keys beyond the contract — `volume_L`, `ph_true`, `event_ml_used`,
`event_elapsed_s`, `chem_source`. They are advisory; ignore them and nothing breaks.
`ph_true` is the hidden true pH and exists so Belal can label the Model A dataset by
physics (Guide Part 4, D3) — **it must never be read by the gateway, the HMI or the
planner**, because the real plant has no such signal.

`redosing.planner.plan_next_dose(state)` takes one of those messages and returns exactly
the I4 contract:

```json
{"action": "DOSE", "channel_id": "BASE_BULK", "dose_ml": 11.8}
{"action": "ESCALATE", "reason": "INFEASIBLE"}
```

Two things worth knowing before you wire it in:

- There is a third answer, `{"action": "HOLD", "reason": "..."}`, for "nothing to do
  yet — the tank is inside the stop band, or the leftover is not worth a dose cycle". It
  is **not** an escalation and the operator must not be called. The contract does not
  mention it, so I am flagging it rather than quietly inventing it: either the gateway
  treats a HOLD as "do nothing", or we add it to `interfaces.md`. **Khalid, your call.**
- `plan_block()` returns the same decision plus the rest of the planned block. The design
  releases a block of up to four doses back-to-back with a 15 s mixing hold after each and
  no re-read inside the block. If the gateway only ever wants one dose at a time, that
  works too, it is just slower. Tell me which you want.

### 2.2 Aspen tables — CHE to ISE

The full format contract is in **`sim/aspen_tables/README.md`**. In one line: CSV,
columns `case, temp_c, excess_mmol, ph`, one row per point, on a **5.000 L basis**, with

> **`excess_mmol` negative for extra acid, positive for extra base.**

That sign is the one thing that will break everything silently, so the loader rejects any
table whose pH does not increase with `excess_mmol`.

Point spacing as in the Guide (A3): 0.002 mmol steps out to 0.2, then 0.05, then 1.0,
mirrored on the acid side.

### 2.3 Batch output — ISE to everyone

`<name>_batch.csv`, one row per recovery event:

```
event_id, scenario, chem_source, seed, upset_dir, upset_ml, upset_mmol, start_ph, fill_L,
n_doses, n_reads, total_mmol, max_dose_ml, recovery_time_s, controller_stop_s,
within_300s, end_ph, in_band, far_side_peak_ph, excursion, outcome
```

and `<name>_batch_traces.csv` with `event_id, t_s, ph`.

Every row carries `chem_source`, which reads `PLACEHOLDER` today and `ASPEN` once the CHE
tables land. Every figure carries it in the footer too. No number from this simulator can
be mistaken for an Aspen-backed one.

---

## 3. Results as of tonight — 600 events, seed 261, chemistry = PLACEHOLDER

| Requirement | Result | Threshold |
|---|---|---|
| **C3** reagent per event | max **40.67 mmol**, 0 events over | ≤ 50 mmol |
| **S6** recoveries within 300 s | **600 / 600 = 100%** (mean 199.0 s, max 258.4 s) | ≥ 95% |
| **INT-S2** ended in pH 6.0–8.5 | **600 / 600** | within 5 min |
| **INT-S3** no far-side excursion | **600 / 600 = 100%**, closest approach pH 6.85 | ≥ 90% |
| escalations to the operator | 0 | — |
| reagent vs stoichiometric demand | **−0.005%** | — |

These agree with the Second Report Installment. On the report's own definition of recovery
time (the controller's stop, after the final mixing hold and triplicate read) this run
gives mean 204.3 s, 95th percentile 241.0 s, max 268.6 s, against the report's 202.7 /
241.6 / 269.5 s — the same process, a different seed.

**These are not Aspen numbers yet.** They will be re-run and re-printed the moment
`sim/aspen_tables/` has real files in it. I expect them to move very little: the
placeholder is the report's own charge balance, and the report's numbers came from the
same equations.

---

## 4. Test sheets

| Sheet | State | Where |
|---|---|---|
| **ISE-AT-01** C3 ≤ 50 mmol | Part B (batch, steps 5–8) filled and passing. Part A live, blank. | `evidence/ISE/ISE-AT-01/` |
| **ISE-AT-02** S6 within 300 s | Steps 2–6 filled and passing. Step 1 live, blank. | `evidence/ISE/ISE-AT-02/` |
| **INT-AT-02** pH restored in 5 min | Steps 3–6 filled and passing. Steps 1–2 live, blank. | `evidence/INT/INT-AT-02/` |
| **INT-AT-03** no far-side excursion | Steps 1–4 filled and passing. Step 5 live, blank. | `evidence/INT/INT-AT-03/` |
| **ISE-AT-03** SUS ≥ 80 | Kit ready: task card, standard form, scoring script. Needs the HMI and 5–8 students. | `evidence/ISE/ISE-AT-03/` |

**No sheet has its overall PASS box ticked**, and that is deliberate. Every one of them has
a live row that needs the integrated rig, and a sheet that claims a pass it has not earned
is worse than a blank one. Each sheet carries a dated note saying exactly which rows were
filled, from which file, and that the chemistry is still the placeholder.

---

## 5. Attainment table — ISE and integrated rows

Ready to drop into the printed table. The other rows are each owner's to fill.

| Constraint / Specification | Off-the-shelf | Project specific | Dept | Evidence |
|---|---|---|---|---|
| C3: ≤50 mmol corrective reagent per event | | Met in simulation (max 40.67 mmol of 600 events) | ISE | ISE-AT-01, batch CSV, histogram, live demo |
| S5: Mean SUS score ≥80 | | Pending (study runs Thu 1 Oct, n = 5–8) | ISE | ISE-AT-03, SUS forms |
| S6: ≥95% of recovery events within 300 s | | Met in simulation (600/600 = 100%, max 258.4 s) | ISE | ISE-AT-02, batch CSV, I-MR chart |
| S9: ≥15% less reagent than a defined PI approach | | Not met (PI baseline pending approval) | ISE | — |
| INT-S2: pH restored to 6.0–8.5 within 5 min | | Met in simulation (600/600, max 258.4 s) | All | INT-AT-02, batch CSV, traces plot |
| INT-S3: No far-side excursion past 5.5/9.5 in ≥90% | | Met in simulation (600/600 = 100%) | All | INT-AT-03, far-side CSV, worst-case plot |

I have written "Met in simulation" rather than "Met". The rubric ranks a working
simulation demo at the presentation as rank 9, the same as hardware, so this does not cost
us anything — and it is what the report already commits to.

---

## 6. What I need, and by when

| # | From | What | By |
|---|---|---|---|
| 1 | **Abdulkarim** | The Aspen tables in `sim/aspen_tables/`, in the format in that folder's README. T1, T2 and T3 are enough to re-run everything; T4 (back-titration) and T5 (temperature) make it stronger. | Tue 29 |
| 2 | **Abdulkarim** | Measured pump mL/s and a measured mixing t95 from the bucket. I am using 300 mL/min and tau = 4 s, both assumed. | after calibration, Wed |
| 3 | **Khalid** | An HMI I can put in front of students. Spec and wireframe are in `hmi/`. All five SUS tasks must be completable. | **Thu 1 Oct morning** |
| 4 | **Khalid** | The gateway's real rejection reason codes, so the log column and my SUS task card use your words. | Tue 29 |
| 5 | **Khalid** | A decision on the `HOLD` action in §2.1 — treat as "do nothing", or add it to `interfaces.md`. | Tue 29 |
| 6 | **Belal** | Confirm the planner is called as `plan_next_dose(state)` on the Pi, and tell me if 10–20 ms per solve is a problem in your loop. | Wed 30 |
| 7 | **Belal** | Five minutes on integration day to film ISE-AT-01 and ISE-AT-02 live. | Wed 30 / Thu 1 |
| 8 | **Team** | Somebody who is not me to be tester and witness on the four sheets. The Testing guide says the tester should not be the sheet's writer. | Fri 2 |

### The one that worries me
Item 3. The SUS study is the only ISE item that cannot be done alone, cannot be
simulated, and cannot be rushed — it needs a working screen, five strangers and a
quiet hour. If the HMI is not usable by Thursday morning, S5 does not happen, and ISE
drops from three proven specifications to two. Everything else on my list is already done
or is a re-run that takes a minute.
