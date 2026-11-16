# ChemShield · FPR evidence (recorded 15 Nov 2026, KFUPM)

All tests ran on the physical prototype: 5 L tank, Pi 5 gateway + AI Dose Guard (Model A), Uno + 4 pumps, laptop HMI.
Level = the FPR "strength of evidence" scale (9 = live at the booth, 8 = video + data).

## Constraints, specifications and integrated specifications

| Item | Requirement | Result (data) | Status | Level | Data (this folder) | Video link |
|---|---|---|---|---|---|---|
| **C1** | Only approved dilute acid/base, each ≤ 5 wt% | 4 approved bottles (HCl and NaOH, 0.5 M and 0.005 M); strongest 0.5 M NaOH = **1.96 wt%**. The gateway only accepts these 4 channels. | **Met** | 9 | `01_scorecard/spec_scorecard.csv` + bottle photos | |
| **C2** | The gateway is the only path to the pumps | Intrusion check on ChemShield-Lab **8/8 PASS**: only ports 22 and 8000 open, unsigned/wrong-key/unsigned-HALT/garbage refused, SSH key-only, IP forwarding 0, INPUT/FORWARD DROP, nothing reached the Uno. **180/180** forged, unsigned and tampered commands blocked, **0** reached a pump. Uno wired only to the Pi. | **Met** | 9 | `04_C2_S3_attacks/chemshield_lab_c2_check/`, `04_.../hotspot_session/attack_demo_5types.txt`, `06_audit_logs/` | |
| **C3** | ≤ 50 mmol reagent per recovery | 5/5 counted runs within 50 mmol; **max 10.08 mmol** (run 3, 12 mL spill), others 2.42–4.89 mmol | **Met** | 9 | `02_recovery_runs/recovery_runs.csv` | |
| **S1** | pH held in 6.5–7.5 for 10 min | 600 s logged, 600 readings, **pH 6.85–7.14, 0 readings outside**, no doses needed. (Attempt 1: 599/600 in band, one 1-s 6.11 reading from a bumped probe, kept for transparency.) | **Met** | 9 | `03_S1_hold/hold_PASS/s1_hold.csv` | |
| **S2** | ≤ 20 mL per dose, ≥ 15 s mixing between doses | **3/3** over-20 mL requests rejected (23 mL, 25 mL, 25 mL). Shortest gap between accepted doses **15.0 s**. Every early dose held back by the mixing wait (e.g. 5 mL at 18:40:56 rejected, MIXING_LOCKOUT). Largest accepted dose 10 mL. | **Met** | 9 | `01_scorecard/spec_scorecard.csv`, `06_audit_logs/` (DOSE_LIMIT, MIXING_LOCKOUT rows) | |
| **S3** | ≥ 99 % of replayed or stale commands rejected | **4,140 / 4,140 rejected (100 %)**: 2 × 1,000 replays, 2 × 1,000 stale (hotspot session and ChemShield-Lab session), plus the booth demo bursts. **0** forwarded to the Uno. | **Met** | 9 | `04_C2_S3_attacks/hotspot_session/replay_1000.txt`, `stale_1000.txt`, `06_audit_logs/` (REUSED_NONCE, STALE_TIMESTAMP rows) | |
| **S4** | Class + risk score for every dose within 3 s | Live: **57 doses classified, slowest 2.3 ms**. Pi test: **1,000/1,000 classified, max 1.61 ms**, mean 0.88 ms (limit 3,000 ms). Stealth attack (stolen key, every rule check passes): **3/3 blocked by the AI Dose Guard**, twice. | **Met** | 9 | `05_S4_ai_timing/pi_1000_requests/`, `04_.../hotspot_session/stealth_attack_test.txt`, `06_audit_logs/audit_session4_*` (MODEL_A_BLOCK rows) | |
| **S5** | Usability: SUS ≥ 80 | SUS forms and score from Hattan | **Open** | 7–8 | (Hattan's forms + score) | |
| **S6** | ≥ 95 % of recoveries within 300 s | **5/5 (100 %)**; recovery times 13, 20, 141, 31, 34 s; worst 141 s | **Met** | 9 | `02_recovery_runs/recovery_runs.csv` | |
| **S7** | Pump rated max ≤ 500 mL/min | Kamoer KPHM400, **400 mL/min rated** (label + datasheet) | **Met** | 8–9 | pump label video + datasheet | |
| **S9** | ≥ 15 % less reagent than a PI controller | Simulation, same 600 spills: **27 % less reagent per successful recovery** (29.6 vs 40.5 mmol per spill fixed, counting the reagent the PI uses on the 183 spills it fails). On spills both fixed, reagent is about equal (+3 %). Solver recovers 600/600 vs 417/600, in 97 s vs 231 s, with 3.75 vs 9.8 doses. | **Met in simulation** (per successful recovery) | 6 | `07_S9_simulation/` | |
| **INT-S1** | Safe-recovery mode within 2 s of the event | **5/5**: recovery mode entered **0.4–0.8 ms** after the event was confirmed, Uno pumps locked in **4.5–7.6 ms**, HMI showed RECOVERY in **0.34–0.50 s** (runs 1–4; run 5's HMI time was not captured, the HMI tab was not in front) | **Met** | 9 | `02_recovery_runs/recovery_runs.csv` (int_s1 columns), `06_audit_logs/` (RECOVERY_ENTERED, UNO_LOCKED, HMI_SHOWED_RECOVERY) | |
| **INT-S2** | pH back in 6.0–8.5 within 5 min | **5/5**; back in band after 13, 20, 42, 31, 7 s; worst **42 s** | **Met** | 9 | `02_recovery_runs/recovery_runs.csv` | |
| **INT-S3** | ≥ 90 % of runs never pass 5.5 / 9.5 on the far side | **5/5**; highest pH after an acid spill **9.49** (run 3, the 12 mL spill; limit 9.5); the other 4 peaked at 6.8–7.3 | **Met** | 9 | `02_recovery_runs/recovery_runs.csv` (far_side_ph) | |

## The 5 counted recovery runs

| Run | Spill | pH low | Recovery mode | Uno locked | HMI shown | Back in band | Closed | Reagent | Doses | Peak after |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6 mL 0.5 M HCl | 5.76 | 0.8 ms | 4.9 ms | 342 ms | 13 s | 13 s | 2.42 mmol | 1 | 6.81 |
| 2 | 6 mL 0.5 M HCl | 5.35 | 0.6 ms | 5.7 ms | 448 ms | 20 s | 20 s | 3.14 mmol | 1 | 6.79 |
| 3 | 12 mL 0.5 M HCl (two pours) | 3.69 | 0.4 ms | 4.5 ms | 496 ms | 42 s | 141 s | 10.08 mmol | 4 | 9.49 |
| 4 | 6 mL 0.5 M HCl | 4.57 | 0.6 ms | 7.6 ms | 340 ms | 31 s | 31 s | 4.89 mmol | 2 | 7.31 |
| 5 | 8 mL 0.5 M HCl | 5.84 | 0.7 ms | 6.8 ms | not captured | 7 s | 34 s | 3.86 mmol | 2 | 6.89 |

Left out of the statistics, still in `recovery_runs.csv`:
- **19:19 UTC (E-0004):** false spill. Acid hit the probe (one 2.25 reading), the tank only reached about 5.9.
- **19:25 UTC (E-0005):** not a spill. pH drifted to 8.51 after a manual buffer top-up.
- **21:12 UTC (session 20261116-000032):** no spill and no dose, a probe disturbance while moving to ChemShield-Lab. **Still marked "included" on the Pi: press "leave out" on the HMI**, so the panel shows 5/5 instead of 6/6.

`02_recovery_runs/run_notes.md` has the operator notes for every run.

## Folder

| Folder | What |
|---|---|
| `01_scorecard/` | final HMI scorecard (CSV); `earlier_snapshots/` = the evidence record backed up after runs 3 and 5 and after S1/S3 |
| `02_recovery_runs/` | every recovery event with all timings; operator notes |
| `03_S1_hold/` | the 10-minute pH log (PASS) and attempt 1 |
| `04_C2_S3_attacks/` | C2 intrusion check on ChemShield-Lab; attack outputs (2,000 + 150 + stealth) |
| `05_S4_ai_timing/` | 1,000-request AI Dose Guard timing on the Pi, histogram |
| `06_audit_logs/` | the gateway's hash-chained audit log for each station session |
| `00_rehearsal_not_counted/` | the afternoon rehearsal (before the evidence record started) |

Removed as duplicates: `audit.csv` = `audit (1).csv` (identical); `int_s1_timing (1).csv` (header only); `int_s1_timing.csv` (4 Oct, old); `recovery_runs` / `spec_scorecard` (0–2) (earlier snapshots of the final files). The Lesson-4a…4e PDFs are course handouts, not evidence, so they're not included.
Not downloaded: the full audit logs of session 1 (after 18:57 UTC) and session 2 (run 4). They're still on the Pi (`~/chemshield/hmi/logs/`).
