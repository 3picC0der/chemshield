# ChemShield · FPR Demo Plan

**FPR:** 15–16 Nov, 3–6 PM, expo style. Goal: every constraint, spec and INT-spec shown at **evidence level 9** (live on the rig) or **8** (video + data), never lower.

**The idea:** one live **"accident and recovery"** shows 6 items at once (INT-S1, INT-S2, INT-S3, C3, S6, S4). The **attack script** shows the cyber items (C2, S3). Short live steps show the rest. Statistics come from runs we record the day before; at the booth we run **one** live sample in front of the reviewers.

---

## 0. The table we show

| Item | Requirement | Result | Level | Evidence |
|---|---|---|---|---|
| **C1** | Only approved dilute acid/base, ≤ 5 wt% | 1.96 wt% max | **9** | Live: the 4 labelled bottles + approval letter |
| **C2** | Gateway is the only way to the pumps | 8/8 checks, 0 attacks reached the pumps | **9** | Live: `c2_check` + attack script |
| **C3** | ≤ 50 mmol per recovery | _(live value)_, max of runs: ___ | **9** | Live recovery + recorded runs |
| **S1** | pH 6.5–7.5 for 10 min | ___ min in band | **8 → 9** | Recorded hold + live hold tab |
| **S2** | ≤ 20 mL per dose, ≥ 15 s mixing | rejected 25 mL, rejected < 15 s | **9** | Live on the HMI |
| **S3** | ≥ 99 % replayed/stale rejected | 100 % (2,000/2,000) | **9** | Live attack + recorded 2,000 |
| **S4** | Class + risk score within 3 s | ~1–2 ms | **9** | Live: every dose shows it |
| **S5** | SUS ≥ 80 | ___ (Hattan) | **7–8** | Forms + score chart; reviewers can try the HMI |
| **S6** | ≥ 95 % recoveries within 300 s | ___ / ___ real, 600/600 sim | **9** | Live recovery + recorded runs |
| **S7** | Pump rated max ≤ 500 mL/min | 400 mL/min rated (KPHM400) | **9** | Live: the pump + its label + datasheet |
| **S9** | ≥ 15 % less reagent than a PI controller | **open** (see S9 below) | — | — |
| **INT-S1** | Recovery mode within 2 s of the event | ___ ms live | **9** | Live: HMI timing tab |
| **INT-S2** | pH back in 6.0–8.5 within 5 min | ___ s live | **9** | Live recovery + recorded runs |
| **INT-S3** | No overshoot past 5.5 / 9.5 in ≥ 90 % | ___ / ___ real, 600/600 sim | **9** | Live recovery + recorded runs |

Fill the blanks from the runs on 14 Nov.

---

## 1. Setup (every time)

All commands run in **Terminal on the Mac**. First:

```bash
cd ~/Development/Personal/chemshield-fpr
```

### 1a. Power and network
**Once, the day before:** move the Pi from your phone hotspot to its own Wi-Fi. With the Mac and the Pi on the hotspot:
```bash
ssh -i ~/.ssh/id_ed25519_second chemshield@172.20.10.2
cd ~/chemshield && nohup sudo bash gateway/firewall/c2_network.sh on '<demo-wifi-password>' >/dev/null 2>&1 &
exit
```
After that, the Pi starts **ChemShield-Lab** by itself whenever the phone hotspot is off.

**Every time:**
1. Plug in the Pi and wait about 2 min. Phone hotspot **off**.
2. Mac joins Wi-Fi **ChemShield-Lab** (the Pi's own network, password in your C2 notes).
3. Uno USB in the Pi. 24 V on. E-stop released.

### 1b. Fill the lines with reagent (once, the day before)
```bash
bash fpr.sh panel
```
The panel opens in the browser. For each pump: inlet in its reagent bottle, outlet in a waste beaker, press **Prime x14**. Then the outlets go into the tank. Close with **Ctrl+C** in Terminal.

| Pump | Bottle | Side |
|---|---|---|
| 1 | HCl 0.5 M | right, outer |
| 2 | HCl 0.005 M | right, inner |
| 3 | NaOH 0.5 M | left, outer |
| 4 | NaOH 0.005 M | left, inner |

### 1c. Make the tank (start of each session)
1. **5.000 L** distilled water + **0.420 g NaHCO₃**. Stir until dissolved.
2. Probe in the tank, mid-depth. Mixer in place.
3. `bash fpr.sh panel`, then pump 1 → **Dose mL 1.8** (brings it to about pH 7). Fine-tune with 0.5 mL doses on pump 2 (acid) or pump 4 (base) until it reads **6.9–7.1**.
4. **Ctrl+C**, then start the system (1d).

### 1d. Start the system
```bash
bash fpr.sh start
```
It turns the firewall on, starts the station, sets the Pi's clock and opens the HMI.
**Check the HMI:** green **NORMAL**, "Gateway online", pH about 7, Security monitor all 0.
Then **Evidence → 10-minute pH hold → Start the 10-minute log** (for S1).

Other commands: `bash fpr.sh status` · `bash fpr.sh stop` · `bash fpr.sh panel`

---

## 2. Spec by spec on the day

### ⭐ The main live demo: accident and recovery (≈ 4 min)
**Proves:** INT-S1, INT-S2, INT-S3, C3, S6, S4

1. Say: *"An operator spills acid into the tank."*
2. Pour **7 mL of 0.5 M HCl** into the tank by hand (syringe).
3. Point at the HMI:
   - Banner turns **red: RECOVERY**. Open **Evidence → Recovery-mode timing** to show the time: **INT-S1** (< 2 s).
   - The **Recovery plan** card shows the planned base doses. Each one is checked by Model A in about 1 ms, shown in the log: **S4**.
   - The pumps add base by themselves, with the mixer running after each dose.
   - pH climbs back into the green band: **INT-S2** (< 5 min) and **S6** (< 300 s).
   - pH never passes 9.5 on the way: **INT-S3**.
   - The banner shows **"Event reagent x / 50 mmol"**: **C3** (≤ 50).
4. Show the **recorded runs** (section 3) for the statistics: "N out of N real runs, and 600 out of 600 in simulation."

### C1: approved dilute reagents
1. Point at the 4 bottles and their labels (0.5 M and 0.005 M). 0.5 M NaOH = **1.96 wt%** < 5 %.
2. Show the lab approval (scan) and the HMI's bottle list: only these 4 exist in the system.

### C2: the gateway is the only path
1. Show the wiring: the Uno connects **only** to the Pi.
2. Run:
   ```bash
   ../chemshield/.venv/bin/python -m hmi.c2_check --pi 10.42.0.1 --ssh-key ~/.ssh/id_ed25519_second
   ```
   **8/8 PASS** (only ports 22 and 8000 open, unsigned/forged commands refused, IP forwarding off).
3. Run the forged + unsigned attacks (next item). Nothing moves.

### S3 (and C2): network attacks
1. Terminal next to the HMI:
   ```bash
   bash fpr.sh attack
   ```
2. Five bursts: forged, unsigned, tampered (1 → 20 mL), stale, replayed. The HMI's **Security monitor** turns red ("ATTACK DETECTED") and the counters jump. The Terminal prints **"150/150 attack commands blocked, 0 reached the pumps"**.
3. Show the recorded **2,000 / 2,000 = 100 %** (section 3).

### S2: dose cap and mixing time
1. HMI → Manual dose → **NaOH 0.005 M fine, 25 mL** → **Rejected: over limit**.
2. **5 mL** → accepted, pump runs, mixer runs.
3. Immediately another 5 mL → **Rejected: mixing wait**. After 15 s → accepted.

### S4: classification within 3 s
Every dose in the log shows **Model A ACCEPTABLE/HARMFUL · score**, and the **Evidence → Model A timing** tab shows the time (about 1–2 ms). Plus the recorded 1,000-decision test on the Pi.

### S1: pH held 6.5–7.5 for 10 minutes
1. Show the recorded 10-minute hold (video + chart) from section 3.
2. Live: **Evidence → 10-minute pH hold** tab. Start the log at setup (1d) so it has already run its 10 minutes when reviewers arrive. It shows elapsed time, lowest and highest pH, and a CSV download.

### S7: pump flow rating
Point at a pump: **Kamoer KPHM400**, label + datasheet: **400 mL/min rated** (< 500). The measured top speed (about 320 mL/min) is in the recorded data.

### S5: usability (SUS ≥ 80)
Show the SUS score chart and the forms (Hattan). Offer the reviewer the HMI: *"Try requesting a dose."*

### S9: 15 % less reagent than a PI controller
**Open item.** No PI baseline has been run. Decide before the FPR:
(a) mark it **Not met**, or
(b) run a simulation comparison (planner vs a PI controller, same 600 upsets), which is **level 6**.

---

## 3. Record the day before (14 Nov)

Film each run on a phone (the HMI and the tank in one shot). After each run, tell Claude to save the logs.

| What | How | Gives |
|---|---|---|
| **5 recovery runs** | Section 2 ⭐, 5 times (7 mL acid each); wait for NORMAL between runs | INT-S1/2/3, C3, S6: "5/5" + videos |
| **10-min hold** | After a recovery: **Evidence → 10-minute pH hold → Start**, leave it 10 min, screenshot it and **Download the pH log (CSV)** | S1 |
| **2,000 attacks** | `../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode replay-now --n 1000`, then the same with `--mode stale --age 5 --n 1000` | S3: 2,000/2,000 |
| **1,000 Model A timings** | on the Pi: `cd ~/chemshield && .venv/bin/python -m model_a.latency_test --n 1000` | S4 |
| **C2 check** | the `c2_check` command above, with `--out evidence/fpr_runs/c2` | C2 |
| **Photos** | bottles + labels, pump label, wiring (Uno to Pi only) | C1, S7, C2 |

---

## 4. If something goes wrong at the booth
- **HMI says offline:** `bash fpr.sh status`, then `bash fpr.sh start`.
- **pH drifts out of band by itself:** the system recovers on its own, so let it.
- **A pump or the mixer misbehaves:** press the **E-stop** (everything stops, HMI shows HALTED). Release, then press **RESUME DOSING**.
- **The live demo fails:** show the recorded video and data for that item (level 8).
