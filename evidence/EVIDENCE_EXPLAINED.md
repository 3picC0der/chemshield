# What was tested, with what setup, what came out, and how it is proven

This document explains every item in the [attainment table](ATTAINMENT_TABLE.md) in the same four parts: **what was tested**, **the setup**, **the result**, and **how it is proven** (which file shows it, and what else would have to be false for the result to be wrong). The three ICS items, C2, Spec 3 and Spec 4, get the most detail because they carry the security story. Each item's own folder has the filled test sheet, the raw CSVs, the plots and the code.

| Item | Section |
|---|---|
| The system in one page, and the words used below | [Start here](#the-system-in-one-page) |
| C1 | [C1: approved dilute reagents](#c1-approved-dilute-reagents) |
| C2 (ICS) | [C2: the gateway is the only way in](#c2-the-gateway-is-the-only-way-in) |
| C3 | [C3: at most 50 mmol per recovery](#c3-at-most-50-mmol-per-recovery) |
| Spec 1 | [Spec 1: pH held for 10 minutes](#spec-1-ph-held-for-10-minutes) |
| Spec 3 (ICS) | [Spec 3: replayed and stale commands are rejected](#spec-3-replayed-and-stale-commands-are-rejected) |
| Spec 4 (ICS) | [Spec 4: class and risk score within 3 s](#spec-4-class-and-risk-score-within-3-s) |
| Spec 5 | [Spec 5: usability score of at least 80](#spec-5-usability-score-of-at-least-80) |
| Spec 7 | [Spec 7: pump maximum flow](#spec-7-pump-maximum-flow) |
| INT-Spec 1 | [INT-Spec 1: recovery mode within 2 s](#int-spec-1-recovery-mode-within-2-s) |
| The 600-event simulation, used by C3 and three extras | [The 600-event simulation](#the-600-event-simulation) |
| Extras | [Spec 2](#extra-spec-2-dose-cap-and-mixing-wait), [Spec 6](#extra-spec-6-recovery-within-300-s), [INT-Spec 2](#extra-int-spec-2-ph-restored-within-5-minutes), [INT-Spec 3](#extra-int-spec-3-no-far-side-excursion) |
| Real versus simulated, and how to repeat any test | [At the end](#what-is-real-and-what-is-simulated) |

---

## The system in one page

```
 LAPTOP (the HMI)                RASPBERRY PI 5 (the station)                  ARDUINO UNO
 browser at 127.0.0.1:8080       listens on port 8000; the firewall            USB cable only, no
 holds the operator key          lets in only SSH (22) and port 8000           network address
 signs every request             ┌────────────────────────────────────┐
        │                        │ 1. GATEWAY: checks every request    │        reads the pH probe (pin A0)
        │   Wi-Fi                │ 2. MODEL A: scores every dose       │        lights the "dose now" light
        └───────────────────────▶│ 3. EVENT DETECTOR + recovery switch │───────▶ blinks slowly when locked
                                 │ 4. PLANNER: proposes recovery doses │  USB   watches the E-stop wire (pin 2)
                                 │ 5. AUDIT LOG: hash-chained          │        stops if the Pi goes quiet
                                 └────────────────────────────────────┘
```

The doses in this prototype are added **by hand with syringes**: the Uno's light is the system's command ("add the dose now"), and the operator presses DOSE ADDED afterwards. The pump is not wired to the Uno.

**The journey of one dose request.** The operator picks a bottle and an amount on the HMI. The laptop writes the request as a small JSON message, signs it with a secret key (HMAC-SHA256), and sends it over Wi-Fi to port 8000 of the Pi. The gateway applies these checks, in this order, and stops at the first one that fails (the failing check's name is the *reason code* in the log):

| # | Check | Reason code when it fails |
|---|---|---|
| 1 | The message has every field, with the right types | `SCHEMA_MISSING_FIELD`, `SCHEMA_TYPE_ERROR` |
| 2 | Allowed role and the active session | `UNAUTHORIZED_ROLE`, `INVALID_SESSION` |
| 3 | The signature matches (only a holder of the operator key can make it) | `MISSING_SIGNATURE`, `INVALID_HMAC` |
| 4 | The timestamp is within 2 s of the Pi's clock | `STALE_TIMESTAMP`, `FUTURE_TIMESTAMP` |
| 5 | The one-time number (nonce), the command ID and the sequence number are new | `REUSED_NONCE`, `DUPLICATE_COMMAND_ID`, `OLD_SEQUENCE` |
| 6 | Dosing is not halted and the Uno's heartbeat is healthy | `SAFE_HOLD_ACTIVE`, `HEARTBEAT_LOSS` |
| 7 | At least 15 s since the last accepted dose | `MIXING_LOCKOUT` |
| 8 | Dose limits: one of the four bottles, more than 0 and at most 20 mL, flow at most 500 mL/min, mixing time at least 15 s | `DOSE_LIMIT` |
| 9 | The reagent used so far in this event plus this dose is at most 50 mmol (the gateway computes it as mL × the bottle's molarity; it ignores any number the sender claims) | `EVENT_MMOL_LIMIT` |
| 10 | **Model A** gives the dose the class ACCEPTABLE, within 100 ms | `MODEL_A_BLOCK`, `MODEL_A_TIMEOUT` |
| 11 | The sender's certificate fingerprint field matches the configured one (a demo value in this prototype, not real TLS, so it adds nothing beyond the signature) | `BAD_CLIENT_CERT` |

Only a request that passes all of them is **accepted**, forwarded to the Uno, and shown to the operator as "Dose now". On top of the gateway, the station adds two rules: every signed and fresh message may be used once (a copy of a rejected message is still a replay), and only one dose can wait to be added at a time (`DOSE_PENDING`). Every decision, accepted or rejected, is appended to the **audit log**.

**Events and recovery.** The Uno sends the pH once a second. When three readings in a row are below 6.0 or above 8.5, the station confirms an **unsafe event**: it labels it (acid or base), switches the gateway to RECOVERY mode, tells the Uno to lock (the light blinks slowly), and the **planner** (a mixed-integer program) starts proposing recovery doses, each of which still goes through the gateway. The event closes when the pH has stayed inside 6.0 to 8.5 for 60 s.

### Words used below

| Word | Meaning |
|---|---|
| **HMAC signature** | A code computed from the message and a secret key. The gateway recomputes it; if it differs, the message was not made by a key holder (`INVALID_HMAC`, HTTP 401). |
| **Nonce** | A random one-time number inside each message. The same nonce twice means the message was copied. |
| **Replay** | Sending a copy of an old valid message. |
| **Stale** | A message whose timestamp is more than 2 s away from the Pi's clock. |
| **Hash chain** | Each audit record holds the SHA-256 hash of the record before it, so changing, deleting or reordering any record breaks every hash after it. `python -m hmi.verify_log` recomputes the chain and prints `CHAIN OK` or `CHAIN BROKEN`. |
| **Fail closed** | When the system cannot decide (Model A too slow, a sensor reading missing), the answer is "block". |
| **Band** | The safe pH range, 6.0 to 8.5. Outside it is an unsafe event. |

---

## C1: approved dilute reagents

**What was tested.** That every solution the system can put into the tank is lab-approved and at most 5 wt%.

**Setup.** No hardware. The gateway's configuration lists the only bottles it will accept: 0.5 M HCl, 0.005 M HCl, 0.5 M NaOH and 0.005 M NaOH. The lab's 0.05 M HCl is used by hand for setup and for the INT-Spec 1 test. The CHE supervisor's approval was confirmed by Belal on 1 Oct 2026.

**Result.** The strongest solution is 0.5 M NaOH at **1.96 wt%**, 39% of the limit. HCl 0.5 M is 1.81 wt%, the 0.05 M HCl is 0.18 wt%, and the 0.005 M solutions are about 0.02 wt%. The tank liquid (0.420 g NaHCO₃ in 5 L) is 0.008 wt%.

**How it is proven.** wt% = molarity × molar mass ÷ (10 × density), calculated by `code/wt_percent.py` for every solution and saved as `data/wt_percent_calculation.csv` with the molar mass and density used for each row; `plots/C1_wt_percent_vs_limit.png` draws them against the 5 wt% line. That the system cannot dose anything else comes from the gateway: it rejects any bottle name outside the four (`DOSE_LIMIT`, tested in `gateway/tests/test_event_mmol.py::test_bad_channels_and_volumes_rejected`).

**Still open.** A calculation alone is weak evidence. It becomes strong when the approval scan, the bottle-label photos and the titration of the 0.5 M bottles are attached in `data/` (the sheet lists the file names).

Folder: [01_C1_approved_dilute_reagents](01_C1_approved_dilute_reagents/)

---

## C2: the gateway is the only way in

**What was tested.** The constraint says every actuator command must pass through the gateway, the sole authorized control path. The test asks: is there any other way to make the dosing side act, from the network, over SSH, or by routing through the Pi?

**Setup.** The real rig: a Raspberry Pi 5 running the station, the firewall script applied (`gateway/firewall/c2_network.sh`), the Uno on its USB cable, and a laptop on the same Wi-Fi running `python -m hmi.c2_check`. It was run twice on 4 Oct 2026: once with the Pi on the phone hotspot (17:28 UTC) and once with the Pi on its own Wi-Fi network `ChemShield-Lab` at 10.42.0.1 (17:44 UTC), which is the booth setup. The check runs eight tests:

| # | Test | A pass means |
|---|---|---|
| 1 | nmap scan of 1,141 TCP ports (all well-known ports, MQTT, OPC UA, VNC, the 8000 range, the industrial-protocol ports) | The only open ports are 22 (SSH) and 8000 (the station) |
| 2 | Send an unsigned dose request to port 8000 | HTTP 401, `MISSING_SIGNATURE` |
| 3 | Send a dose signed with the wrong key | HTTP 401, `INVALID_HMAC` |
| 4 | Send an unsigned operator action (HALT) | HTTP 401 |
| 5 | Send a body that is not a command | HTTP 400 |
| 6 | Try to log in to the Pi over SSH with a password | Refused: the server offers public keys only |
| 7 | Log in with the key and read the Pi's settings | `ip_forward` = 0; INPUT policy DROP; FORWARD policy DROP |
| 8 | Compare the station's state before and after the attempts | Accepted-dose count unchanged, no dose waiting, the Uno's light does not show "dose" during the attempts |

**Result.** **8 of 8 checks passed in both runs.** Only ports 22 and 8000 were open (the other 1,139 scanned ports are filtered), every unsigned or wrong-key request got a 401, the password login was refused, IP forwarding was off, and the accepted-dose counter did not move during the attempts.

**How it is proven.**
- The raw tool output is committed beside the verdict lines: the nmap greppable output, the SSH error `Permission denied (publickey)`, and the `sysctl` and `iptables -S` output read from the Pi (`data/run1_phone_hotspot/` and `data/run2_pi_own_wifi/`, `ICS-AT-01_c2_check.txt` and `.json`). The verdicts can be checked against the raw output.
- The check is automatic and repeatable in about a minute, and the check itself is tested: it fails when an extra port is open (`hmi/tests/test_c2_check.py::test_an_extra_open_port_fails_the_scan`), and the firewall script is tested for a default-DROP policy on IPv4 and IPv6 (`gateway/tests/test_firewall_template.py`, 9 tests passed in `data/unit_tests_c2.txt`).
- The design explains why it holds, shown in `plots/C2_network_and_trust_boundary.png`: the Uno has no network address (it is a USB serial device the station process owns), the Pi does not route between networks, the one open application port only accepts signed messages, and the gateway is the code that decides what the station sends to the Uno.

**What it does not show.** It scans 1,141 ports, not all 65,535 (a full scan through the phone hotspot did not finish in 10 minutes); the DROP policy covers the rest and check 7 reads that policy. The scan is TCP only. The holder of the operator key can still request doses (by design: each one is checked), and the holder of the SSH key can log in to the Pi as an administrator. The firewall rules do not survive a reboot, so `c2_network.sh fw` is run after every start (see [SETUP.md](SETUP.md)). The three accepted doses counted in check 8 were the Pi's own planner reacting to the unplugged probe's floating reading before the checks began; the counter did not change while the attempts ran.

Folder: [02_C2_gateway_sole_control_path](02_C2_gateway_sole_control_path/)

---

## C3: at most 50 mmol per recovery

**What was tested.** That a recovery from an unsafe dosing event never uses more than 50 mmol of reagent, in the planner and in the gateway.

**Setup.** Two parts. (1) The [600-event simulation](#the-600-event-simulation) records the reagent used in each recovery. (2) Software tests check the gateway's own limit: it computes each dose's mmol from the bottle (mL × molarity), keeps a total per event, and rejects the dose that would pass 50 mmol.

**Result.** **Largest recovery: 41.664 mmol; mean 29.6 mmol; 0 of 600 events over 50 mmol; 0 escalations.** The tests pass: of eleven 10 mL doses of 0.5 M NaOH in one event (5 mmol each), the first ten (50 mmol in total) are accepted and the eleventh (which would make 55 mmol) is rejected as `EVENT_MMOL_LIMIT`; a full station recovery on a simulated tank closes in under 300 s with at most 50 mmol, and a manual dose past 50 mmol during it is rejected (8 tests, `data/unit_tests_gateway_c3.txt`).

**How it is proven.** `data/batch_600_events.csv` has the reagent used for each of the 600 events (column `total_mmol`); `plots/C3_reagent_per_event_histogram.png` shows them against the 50 mmol line. Even if the planner asked for more, the limit is enforced by the gateway, which does not trust the sender's number (`test_50_mmol_per_event_ignoring_the_clients_number`).

**Still open.** A live total from the real 5 L tank: after the unsafe dose of INT-Spec 1, add each "Dose now" by syringe and read "Event reagent x / 50 mmol" when the event closes. The 4 Oct rig run was stopped before any recovery dose was added. The simulation uses a placeholder pH table until the Aspen export.

Folder: [03_C3_max_50mmol_per_recovery](03_C3_max_50mmol_per_recovery/)

---

## Spec 1: pH held for 10 minutes

**What was tested.** Under nominal conditions the tank pH stays between 6.5 and 7.5 for at least 10 minutes. **This has not been tested on the real tank yet.**

**Setup (planned).** The 5 L tank (4.9 L distilled water plus 100 mL of baking-soda stock, 0.420 g NaHCO₃ in all), brought to pH 7 with about 18 mL of 0.05 M HCl, a calibrated probe, the station running, and the HMI's Evidence tab "10-minute pH hold" started. If the pH leaves 6.7 to 7.3 the HMI asks for a trim dose, added by hand.

**What exists.** The hold logger, its 600 s clock and the PASS rule are in the station and pass a software test on a simulated tank (`data/unit_test_hold_log.txt`). That test shows the logger works, not that the tank holds its pH.

Folder: [04_S1_ph_hold_10min](04_S1_ph_hold_10min/)

---

## Spec 3: replayed and stale commands are rejected

**What was tested.** The spec: the security layer rejects at least 99% of replayed or stale control commands. A *replay* is a copy of a command that was already sent; a *stale* command is one dated more than 2 s away from the Pi's clock.

**Setup.** The real station code (the same gateway and Model A that run on the Pi) was started on the laptop with a simulated tank on 3 Oct 2026. `python -m hmi.attack_station` then attacked it over HTTP while holding the operator key, like a legitimate client would:

| Run | What it sends |
|---|---|
| Replay | 1,000 times: a fresh signed command (1 mL of the 0.005 M bottle), immediately followed by an exact copy |
| Stale | 1,000 signed commands dated 5 s in the past |
| Control | 100 signed commands dated 1 s ago (still fresh) |

**Result.** **2,000 of 2,000 replayed or stale commands were rejected (100%; limit 99%)**: all 1,000 copies as `REUSED_NONCE`, all 1,000 old ones as `STALE_TIMESTAMP`, in 1.6 s and 0.9 s. The control's 100 commands were not called stale (the gateway rejected them for the 15 s mixing lockout instead). None of the 2,000 reached the Uno, and the one command the gateway accepted was the first, valid original, which shows valid commands still get through.

**How it is proven.** Three sources agree:
1. The attack script's own counts (`data/laptop_run_3Oct/ICS-AT-02_attack_summary.txt`).
2. The station's counters, read from `/api/state` before and after each run: Replayed +1,000, Stale +1,000.
3. The audit log: 3,103 records (3,100 commands: 1 accepted, 1,000 replays, 1,000 stale, 403 lockouts, 696 refused as a dose already waiting), and `python -m hmi.verify_log` prints `CHAIN OK`, so the records were not edited afterwards.

The mechanism is in the code: the gateway keeps every accepted nonce and command ID and the highest sequence number, and compares each timestamp with its own clock; the station also remembers every signed, fresh command whatever its decision, so a copy of a *rejected* command is a replay too (`hmi/tests/test_station.py::test_a_copy_of_a_rejected_command_is_still_a_replay`). A supplementary test from 30 Sep attacks the gateway code directly with 14 attack types of 1,000 commands each; every type is rejected 1,000 of 1,000 (`data/in_process_gateway_test_30Sep/`).

**What it does not show.** The run was on a laptop, not yet against the Pi over Wi-Fi; the same command with the Pi's address repeats it (`--station http://10.42.0.1:8000`). The laptop's and the Pi's clocks must agree within 2 s, which `python -m hmi.clock_sync` sets and checks. An attacker without the operator key never gets this far: the signature check (C2) stops them first.

Folder: [05_S3_replay_stale_rejected](05_S3_replay_stale_rejected/)

---

## Spec 4: class and risk score within 3 s

**What was tested.** For each detected abnormal event, the AI module assigns an event class and a risk score within 3 s. The AI module is **Model A**: for every dose request it returns a class (ACCEPTABLE, HARMFUL or UNCERTAIN) and a risk score from 0 to 1, and the station labels each confirmed unsafe event by its class (acid or base).

**How Model A decides.** A physics rule predicts the pH after the dose from the pH table; a small gradient-boosted model scores what the rule cannot see (a probe that lags, drifts or does not respond). It uses 16 features from the last seconds of pH readings and the dose history. Anything it cannot judge, or does not answer within 100 ms, is UNCERTAIN, and only ACCEPTABLE lets a dose through (fail closed). On simulated test data (4,539 requests) it blocks 95.8% of the harmful ones (57 of 1,353 got through, which is why the gateway's fixed limits stay in front of it) and wrongly blocks 3.0% of the good ones (95 of 3,186) (`code/model_a/artifacts/MODEL_CARD.md`). It can block a dose but never approves one on its own.

**Setup.** On the **Raspberry Pi 5 itself** (3 Oct 2026), `python -m model_a.latency_test --n 1000` sent 1,000 signed dose requests through the real gateway and Model A: a mix of normal doses, harmful doses, recovery doses and cases with a lost probe signal. The time per request runs from the gateway receiving the request to its decision with the class and score written to the audit log. It also froze Model A for three requests to check the timeout.

**Result.** **1,000 of 1,000 requests got a class and a score. Slowest decision: 1.65 ms (mean 0.87 ms, 99th percentile 1.21 ms), against a limit of 3,000 ms**, so the slowest used 0.055% of the allowed time. Labels: 529 acceptable, 277 harmful, 194 uncertain. The three frozen requests came back UNCERTAIN within 100.4 ms and were blocked. On the live rig on 2 Oct, 10 mL of 0.5 M NaOH into a tank at pH 7.8 was classed HARMFUL with risk 1.00 in 1.27 ms (it would have pushed the tank to pH 10.5), while 10 mL of 0.005 M NaOH was ACCEPTABLE with risk 0.005 in 2.23 ms.

**How it is proven.** `data/pi_run_3Oct/ICS-AT-03_latency.csv` holds one row per request (scenario, class, score, milliseconds) and `ICS-AT-03_machine_info.txt` records "Raspberry Pi 5 Model B Rev 1.1" with the Python and scikit-learn versions, so the timing is on the target hardware. `plots/S4_decision_time_histogram_raspberry_pi_5.png` shows the 1,000 decision times, all between about 0.5 and 1.7 ms, with the slowest marked by the dashed line (the 3,000 ms limit is far off the right edge of that plot). The live decisions are in `data/rig_run_2Oct/model_a_decisions.csv` (with the predicted post-dose pH), and the 17 unit tests of the features, label rules and fail-closed behaviour are in `data/unit_tests_model_a.txt`.

**What it does not show.** The accuracy figures come from simulated data, not from real harmful doses. Model A can also block a correct recovery dose after a large upset because the probe still lags: over 60 simulated runs each, the planner's recovery succeeded 60/60 for a 7 mL acid upset, 56/60 for 40 mL of acid, 59/60 for 80 mL and 58/60 for 80 mL of base; a miss ends in "operator decision required" and HALT then RESUME lets the planner retry (`hmi/README.md`).

Folder: [06_S4_class_and_score_within_3s](06_S4_class_and_score_within_3s/)

---

## Spec 5: usability score of at least 80

**What was tested (planned).** The System Usability Scale (SUS) score of the operator interface is at least 80. **The study results are not recorded here yet.**

**Setup.** 5 to 8 students who are not on the team use the real HMI on a simulated tank (`python -m hmi.demo`; a purple SIMULATED band stays on screen). The facilitator reads the script in `07_S5_sus_at_least_80/SUS_study_kit.md`, runs five tasks (read the pH and the state; request 10 mL of bulk base; explain the alarm after an injected upset; acknowledge the decision request and halt dosing; find the last three rejected commands), then each person fills in the ten-question SUS form. Each form is scored with `code/sus_score.py`: odd answers count (answer − 1), even answers count (5 − answer), the sum is multiplied by 2.5, and the mean over all participants is reported with its 95% interval.

**What exists.** The HMI, the study kit, the facilitator tool for injecting upsets between participants, and the scoring script. Pass: mean of 80 or more. If the study is not finished, ISE can present Spec 6, which is proven in simulation.

Folder: [07_S5_sus_at_least_80](07_S5_sus_at_least_80/)

---

## Spec 7: pump maximum flow

**What was tested.** The selected dosing pump's manufacturer-rated maximum flow is at most 500 mL/min. The spec is about the rating, so the rating decides it.

**Setup.** The pump is a Kamoer KCP-X-S10B, 24 V DC, 5 W peristaltic, with its own 24 V adapter. It is not wired to the Uno or the Pi in this prototype. The sheet's measurement step puts it on a balance at full speed for 60 s, three times (1 g of water is 1 mL).

**Result.** Rated flow **19 to 65 mL/min**, so the rated maximum is **65 mL/min**, 7.7 times below the limit.

**How it is proven.** The photos of the pump labels are in `data/` (the second pump in the lab, a KCP-D-B10W-UK, is also 24 V, 5 W). The rating comes from the product listings so far. **Still to attach:** the manufacturer's datasheet page and the three measured runs from 3 Oct.

Folder: [08_S7_pump_max_flow](08_S7_pump_max_flow/)

---

## INT-Spec 1: recovery mode within 2 s

**What was tested.** The integrated system enters safe-recovery mode within 2 s of confirming a successful unsafe dosing event. This is the whole chain working together: probe, Uno, Pi, gateway state, Uno lock and the HMI screen.

**Setup.** The real rig on 4 Oct 2026: the real pH probe in a pH 7 buffer standing in for the tank, the Uno on the Pi's USB, the station running with `--ph-source uno`, and the HMI on the laptop. The unsafe dose was made by hand: 0.05 M HCl added by syringe straight into the buffer, bypassing the HMI, as if a bad command had got past the gateway. The station confirms an event when three readings in a row are outside 6.0 to 8.5.

**Result.** Event E-0001 was confirmed at 14:23:54.507 UTC on readings 5.6, 5.16 and 5.19 (class "Unsafe acid event, pH below 6.0"). Then, measured from the moment of confirmation:

| Step | Time | Limit |
|---|---|---|
| Station enters RECOVERY mode | **1.1 ms** | 2,000 ms |
| The Uno confirms "dosing locked" (its light slow-blinks) | 8.1 ms | |
| The HMI draws the red banner | 326.7 ms | |

`pass_2s = True`. The same measurement repeated on 100 simulated events (30 Sep) gave 100 of 100 under 2 s end to end, with the switch to RECOVERY at most 7.1 ms and the HMI showing it in 124 ms on average and 260.6 ms at most.

**How it is proven.** All three times come from the station's own clock, so no clock agreement between the machines is involved. They are in `data/rig_run_4Oct/INT-AT-01_int_s1_timing.csv` (the row the HMI's download gives) and in the audit log `audit.jsonl`: 57 hash-chained records (the event, `RECOVERY_ENTERED`, `UNO_LOCKED`, `HMI_SHOWED_RECOVERY`, the HALT), which `hmi.verify_log` reports as `CHAIN OK`. `plots/INT-S1_rig_run_ph_trace.png` shows the probe's pH falling through the threshold, and `plots/INT-S1_dry_run_100_events.png` the 100-event batch. The switch itself is unit-tested (`data/unit_tests_int_s1.txt`, 3 tests).

**What it does not show.** The spec starts the clock at confirmation, which is the third low reading, about 2 s after the pH first crosses 6.0 (the first low reading was at 14:23:52.5). Measured from the first low reading, recovery mode took about 2.0 s. The planner's recovery doses proposed afterwards (about 8 mL of 0.5 M NaOH) were not added, because the planner assumes a 5 L tank and the stand-in was a cup of buffer; the operator pressed HALT after reading the timing. The probe had a one-point pH 7 calibration only, so the absolute pH values are approximate (the crossing time does not depend on that). The audit log also shows frequent "Uno lost the heartbeat" notices; they did not affect the result and their cause has not been found.

Folder: [09_INT-S1_recovery_mode_within_2s](09_INT-S1_recovery_mode_within_2s/)

---

## The 600-event simulation

C3 and the three simulated extras (Spec 6, INT-Spec 2, INT-Spec 3) share one run, `python -m redosing.run_all` (seed 261), so the same 600 events give all four results.

**Each event.** A confirmed unsafe event is drawn at random: acid (343 events) or base (257), 40 to 80 mL of 0.5 M reagent, into a tank of 4.8 to 5.2 L, which puts the pH at 2.1 to 2.5 or 11.5 to 11.9. The simulated tank follows a pH table of the baking-soda water (a closed carbonate model; **`chem_source = PLACEHOLDER` until the Aspen export arrives**). The controller is the same planner code the Pi runs: a robust mixed-integer program (SciPy's `milp`, which uses the HiGHS solver) that picks the next dose from the last reading, re-solved after every reading, with at most 20 mL per dose and 15 s of mixing between doses. What the controller does not know varies per event: the pump's delivery (about 1% bias, 1.2% random, plus 0.005 mL), the tank volume (0.5%) and the pH reading noise (0.033 pH per reading). The probe itself is assumed to read true; the planner reserves 0.03 pH for calibration error.

**Definitions.** *Recovery time* is the time from the confirmed event until the pH first enters 6.0 to 8.5 and stays there (`recovery_time_s`; the controller declares itself finished later, after the final mixing hold, and that time is in `controller_stop_s`). *Far-side excursion* is the highest pH reached after an acid upset, or the lowest after a base upset.

**Outputs.** `batch_600_events.csv` (one row per event), `batch_600_events_traces.csv` (every pH sample), `batch_summary_all_numbers.json`, and the plots. The batch assumes a dosing speed of 300 mL/min; the real pump is 65 mL/min and hand dosing is slower, so the same 600 events were also run at 65, 100, 150 and 300 mL/min (`EXTRA_S6.../data/dose_speed_sensitivity.csv`).

**Limits.** Simulation with data counts as evidence at the course's 6 to 7 level but is not the real tank; the placeholder pH table is the main caveat. Re-running the command regenerates every data file and plot in the four folders, and on 4 Oct a re-run on the Mac gave byte-identical files (seed 261), so the numbers can be checked by anyone.

---

## EXTRA Spec 2: dose cap and mixing wait

**What was tested.** Each dose is at most 20 mL, with at least 15 s of mixing before another dose.

**Setup.** The gateway's own rules, seen three ways: software tests; the live rig on 2 Oct (real probe, Pi, HMI); and the 3 Oct attack run.

**Result.** **MET.** On the rig, two requests of 30 mL of 0.5 M NaOH were rejected as `DOSE_LIMIT` (15:30:26 and 15:33:35 UTC) and two 10 mL doses of 0.005 M NaOH were accepted (15:32:10 and 15:34:12 UTC). In the attack run, 403 requests inside the 15 s window were rejected as `MIXING_LOCKOUT`. In the test, a second dose is rejected up to 14.9 s and accepted at exactly 15.0 s; six back-to-back doses through the HMI path give 1 accepted and 5 rejected, then an accepted one 15.1 s later.

**How it is proven.** `data/s2_gateway_decisions.csv` has the audit rows behind these numbers, `data/unit_tests_gateway_s2.txt` the 4 passing tests, and the lockout runs on the gateway's own clock, whatever the sender claims.

**What it does not show.** With hand dosing the operator, not a pump, delivers the dose, so the gateway's 20 mL limit is a limit on what it will approve, and the wait between two hand-added doses was not timed on the rig.

Folder: [EXTRA_S2_dose_cap_and_mixing_wait](EXTRA_S2_dose_cap_and_mixing_wait/)

---

## EXTRA Spec 6: recovery within 300 s

**What was tested.** At least 95% of recovery events finish within 300 s.

**Setup and result.** The [600-event simulation](#the-600-event-simulation). **600 of 600 (100%) recovered, mean 95.5 s, fastest 49.4 s, slowest 128.7 s.** At the real pump's 65 mL/min the same events give 598 of 600 within 300 s (99.67%), slowest 183.2 s; the two others never returned to the band (they stopped at pH 8.58 and 8.62).

**How it is proven.** `data/batch_600_events.csv` column `within_300s`; `plots/S6_recovery_time_control_chart.png` draws the 600 times as an individuals and moving-range control chart with every point far below the 300 s line (the chart's run rules flag 42 points as out of control, which is about the process, not the spec).

Folder: [EXTRA_S6_recovery_within_300s](EXTRA_S6_recovery_within_300s/)

---

## EXTRA INT-Spec 2: pH restored within 5 minutes

**What was tested.** The pH is back inside 6.0 to 8.5 within 5 minutes of an unsafe event.

**Setup and result.** The [600-event simulation](#the-600-event-simulation). **600 of 600 ended inside the band, the longest in 128.7 s (limit 300 s).** At 65 mL/min, 598 of 600 (the same two events as above ended at pH 8.58 and 8.62, just above 8.5).

**How it is proven.** `data/batch_600_events.csv` columns `in_band` and `recovery_time_s`; `plots/INT-S2_all_recovery_traces.png` plots all 600 pH traces with the band and the 300 s line. The live part, a recovery on the real tank, is not done.

Folder: [EXTRA_INT-S2_ph_restored_within_5min](EXTRA_INT-S2_ph_restored_within_5min/)

---

## EXTRA INT-Spec 3: no far-side excursion

**What was tested.** In at least 90% of scenarios the recovery does not overshoot past pH 5.5 (after a base upset) or 9.5 (after an acid upset).

**Setup and result.** The [600-event simulation](#the-600-event-simulation). **600 of 600 (100%) had no excursion.** The closest case was a base upset (event 303) whose lowest pH was 6.65, 1.15 pH units from 5.5; the worst acid case (event 546) peaked at 6.95, 2.55 below 9.5. At 65 mL/min still 600 of 600, closest margin 1.11.

**How it is proven.** `data/INT-S3_far_side.csv` has the far-side peak and its margin for each of the 600 events; `plots/INT-S3_worst_case.png` shows the worst case. The live part is not done, and a badly calibrated probe was not simulated, which is why the probe is calibrated before each run.

Folder: [EXTRA_INT-S3_no_far_side_excursion](EXTRA_INT-S3_no_far_side_excursion/)

---

## What is real and what is simulated

| Item | Real rig / hardware | Simulated | Paper |
|---|---|---|---|
| C1 | | | calculation, approval (scan to attach) |
| C2 | Pi 5, Uno, laptop, firewall | | |
| C3 | | 600 events; software tests of the gateway | live total to add |
| Spec 1 | | software test only | the real run is not done |
| Spec 3 | | the real station code on a laptop | repeat on the Pi to do |
| Spec 4 | Pi 5 (1,000 decisions); live rig decisions on 2 Oct | | |
| Spec 5 | | the HMI on a simulated tank, with real people | forms to add |
| Spec 7 | | | pump rating and label (runs to add) |
| INT-Spec 1 | real probe, Uno, Pi, HMI | 100 events | |
| Extra Spec 2 | live rig records on 2 Oct | attack run and tests | |
| Extra Spec 6, INT-Spec 2, INT-Spec 3 | | 600 events | live recovery not done |

## Repeat any test

All commands are run from the repository folder with the project's Python environment (`.venv/bin/python`); [SETUP.md](SETUP.md) explains how to prepare the Pi and the laptop.

| Item | Command | Where |
|---|---|---|
| C1 | `python evidence/01_C1_approved_dilute_reagents/code/wt_percent.py` | anywhere |
| C2 | `python -m hmi.c2_check --pi 10.42.0.1 --ssh-key ~/.ssh/<your-key> --out evidence/02_C2_gateway_sole_control_path/data/my_run` | laptop on the Pi's Wi-Fi |
| C3, Spec 6, INT-Spec 2, INT-Spec 3 | `python -m redosing.run_all` | anywhere (about 20 seconds on a laptop) |
| Spec 1 | HMI, Evidence, "10-minute pH hold", Start | live rig |
| Spec 3 | `python -m hmi.attack_station --station http://10.42.0.1:8000 --mode replay-now --n 1000`, then `--mode stale --age 5 --n 1000` | laptop on the Pi's Wi-Fi |
| Spec 4 | `python -m model_a.latency_test --n 1000` | on the Pi |
| Spec 5 | `python evidence/07_S5_sus_at_least_80/code/sus_score.py --report` | after the study |
| INT-Spec 1 | demo step 9 in [SETUP.md](SETUP.md#f-the-demo-scenario); the batch: `python -m hmi.int_s1_batch --events 100` | live rig; anywhere |
| Extra Spec 2 | demo steps 4 to 6 in [SETUP.md](SETUP.md#f-the-demo-scenario); tests: `pytest gateway/tests/test_mixing_lockout.py` | live rig; anywhere |
| Check an audit log | `python -m hmi.verify_log <audit.jsonl>` | anywhere |
| All software tests | `pytest hmi/tests gateway/tests sim/tests model_a/tests -q` | anywhere |
