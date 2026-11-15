# ChemShield · ICS Attack Manual (FPR, 16 Nov)

How to prove the cyber-security items live at the booth, step by step.

| Item | Requirement | Proved by |
|---|---|---|
| **C2** | The gateway is the only way to reach the pumps: no unauthenticated command gets through | Test 1 (intrusion check) + Test 2 (forged, unsigned, tampered) |
| **S3** | ≥ 99 % of replayed or stale commands rejected | Test 2 (stale, replay) + Test 5 (2,000 commands) |
| **S4** | Every dose request gets a class and a risk score within 3 s | Test 3 (stealth attack) + Test 6 (1,000 timings) + the HMI log |

Recorded results from 15 Nov (already saved in `evidence/fpr_runs/20261115_*`):
C2 90/90 blocked · S3 2,060/2,060 rejected (100 %) · S4 slowest 2.3 ms live, 1.6 ms over 1,000 runs on the Pi · stealth attack 3/3 blocked by the AI Dose Guard.

---

## 0. Setup (every time)

**Hardware:** Pi on **its own charger** (not the shared multi-port one). Uno USB into the Pi. 24 V on. E-stop released. Mixer in the tank, probe mid-depth.

**Network (booth = the Pi's own Wi-Fi):**
1. Turn the **phone hotspot OFF**. The Pi switches to its own Wi-Fi, **ChemShield-Lab**, by itself in about 1 to 2 min. No need to unplug or restart it.
2. On the Mac, join Wi-Fi **ChemShield-Lab** (password in your C2 notes).
3. Open Terminal:
   ```bash
   cd ~/Development/Personal/chemshield-fpr
   ```
4. Start everything (firewall + station + HMI):
   ```bash
   bash fpr.sh start
   ```
5. Check the HMI (it opens in the browser): green **NORMAL**, **Gateway online**, pH about 7, Security monitor all 0.

On ChemShield-Lab you **don't** write `PI=...`. The commands are the same as on the hotspot, just without `PI=172.20.10.2`. All the commands below assume ChemShield-Lab (Pi = `10.42.0.1`). On the hotspot, put `PI=172.20.10.2` in front of `bash fpr.sh ...`, and use `172.20.10.2` instead of `10.42.0.1`.

**Layout:** the HMI on one half of the screen, Terminal on the other half, so reviewers see the attack being sent and the HMI counting it at the same time.

---

## Test 1 · Intrusion check (C2)

**Say:** *"An intruder is on our network. Let's see every way they could try to reach the pumps."*

```bash
../chemshield/.venv/bin/python -m hmi.c2_check --pi 10.42.0.1 --ssh-key ~/.ssh/id_ed25519_second --out evidence/fpr_runs/c2_booth
```

**What it tries:**
1. Port scan: only SSH (22) and the station (8000) are open
2. A dose with no signature → refused
3. A dose signed with the wrong key → refused
4. An unsigned HALT command → refused
5. Garbage that isn't a command → refused
6. SSH with a password → not offered (key only)
7. On the Pi: IP forwarding off, firewall drops everything else

**Pass:** every line says **PASS**. Also point at the wiring: the Uno is plugged **only** into the Pi.

---

## Test 2 · The five network attacks (C2 + S3), the main booth demo

**Say:** *"Now the intruder sends commands to the pumps, five different ways."*

```bash
bash fpr.sh attack
```

| Attack | What the intruder does | Gateway answer | Proves |
|---|---|---|---|
| forged | signs with their own key | Not authorised | C2 |
| unsigned | sends with no signature | Not authorised | C2 |
| tampered | catches a real 1 mL command and changes it to 20 mL | Not authorised (signature broken) | C2 |
| stale | sends a real command captured 5 s ago | Stale | S3 |
| replay | re-sends one real command 30 times | Replayed | S3 |

**Watch on the HMI:** the Security monitor turns red, **ATTACK DETECTED**, and each counter climbs.
**Pass:** Terminal ends with **"150/150 attack commands blocked (100.0 %), 0 reached the pumps"**.

One attack only, or more commands:
```bash
bash fpr.sh attack --only replay --n 100
```
(`--only` can be `forged`, `unsigned`, `tampered`, `stale` or `replay`.)

The replay attack first sends **one genuine** 1 mL dose of the weak 0.005 M base, the "captured" command. Pump 4 and the mixer may run once. That's correct: the real one is allowed, the copies are not.

---

## Test 3 · Stealth attack: only the AI can catch it (S4, C2 defence in depth)

**Say:** *"What if the attacker steals the operator's key? Then every command is correctly signed, fresh, under 20 mL and waits for the mixing time. Every rule check passes. What gives it away is the chemistry, and that's what our AI Dose Guard judges."*

```bash
bash fpr.sh stealth
```

| Scenario | Dose | Would push pH to |
|---|---|---|
| base overdose | 12 mL NaOH 0.5 M | about 10.6 |
| acid overdose | 12 mL HCl 0.5 M | about 3.5 |
| quiet base push | 6 mL NaOH 0.5 M ("looks routine") | about 10 |

**Watch:** Terminal prints *"signature OK, fresh, under cap, after mixing wait → BLOCKED by AI Dose Guard (HARMFUL, risk 1.00)"* for each one. On the HMI, the dose log shows **"Blocked by AI Dose Guard"**, and the Security monitor's AI Dose Guard row counts them. The S4 tab shows the class, risk score and time (about 2 ms) for each.
**Pass:** *"3 stealth commands sent, 3 blocked by the AI Dose Guard, 0 reached a pump"*.

**Contrast to show:** on the HMI, request a normal **0.3 mL NaOH 0.5 M bulk**. The AI Dose Guard calls it ACCEPTABLE and it goes through. So the AI isn't blocking everything, only the dangerous doses.

Safety: before sending, the script checks each dose with the same AI model on the Mac. If the model would not block it, the script doesn't send it, so it can't put a real dose in the tank. Run it only when the HMI shows NORMAL (it waits for that by itself).

---

## Test 4 · Single attacks from the HMI (no Terminal)

**Engineer panel** (bottom of the HMI) → **Security tests (S3, C2)**. Each button sends one bad command:
- **Exact copy** of the last command → Replayed (S3)
- **5 s old** command → Stale (S3)
- **No signature** → Not authorised (C2)
- **Wrong key** → Not authorised (C2)

Good for a reviewer to press themselves.

---

## Test 5 · Statistics: 2,000 commands (S3)

Recorded on 15 Nov. Re-run only if a reviewer asks, since it takes about 2.5 min.

```bash
../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode replay-now --n 1000
```
```bash
../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode stale --age 5 --n 1000
```
**Pass:** each ends with *"replayed/stale rejected: 1000/1000 = 100.00 % (S3 needs ≥ 99 %)"* and *"forwarded to the Uno: 0"*.

**Capture now, replay later** (an attacker who records traffic and plays it back):
```bash
../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode valid --n 20 --save /tmp/captured.jsonl
```
Wait 5 s, then:
```bash
../chemshield/.venv/bin/python -m hmi.attack_station --station http://10.42.0.1:8000 --mode replay --file /tmp/captured.jsonl
```
In the first step one genuine command is accepted and the rest are held back by the mixing wait, which is correct. In the second step **all 20 are rejected**.

---

## Test 6 · AI Dose Guard timing, 1,000 requests (S4)

Recorded on 15 Nov (slowest 1.6 ms, limit 3,000 ms). To re-run on the Pi:
```bash
ssh -i ~/.ssh/id_ed25519_second chemshield@10.42.0.1 'cd ~/chemshield && .venv/bin/python -m model_a.latency_test --n 1000 --gateway-src gateway/src --out evidence/fpr_runs/s4_booth 2>/dev/null | tail -4'
```
**Pass:** *"max ... ms (limit 3,000 ms)"* and **PASS**. Live, every dose in the HMI's S4 tab shows its class, score and time.

---

## Don'ts

- Don't run Tests 2, 3 or 5 **during a recovery run or the S1 10-minute hold**. The replay originals run pump 4 briefly, and the stealth attack waits for NORMAL anyway.
- Don't touch the probe or its cable during the hold or a run. One knock reads as a spike.
- Keep the HMI tab **in front** and the Mac awake during recovery runs, since INT-S1 times how fast the HMI shows RECOVERY.

---

## Switching networks and turning the Pi off

- **Hotspot → ChemShield-Lab:** just turn the hotspot off. The Pi switches by itself in 1 to 2 min. Then join ChemShield-Lab on the Mac and run `bash fpr.sh start`.
- **ChemShield-Lab → hotspot:** turn the hotspot on and restart the Pi (below), and it joins the hotspot on boot. Then use `PI=172.20.10.2 bash fpr.sh start`.
- **Turn the Pi off safely** (never just pull the plug while it runs, since that can corrupt the SD card):
  ```bash
  bash fpr.sh poweroff
  ```
  Wait about 20 s until the green light stops blinking, then unplug. On the hotspot: `PI=172.20.10.2 bash fpr.sh poweroff`.

**Claude on the Mac:** while the Mac is on ChemShield-Lab it has no internet. If you want Claude during the booth, plug your phone into the Mac with USB and turn on Personal Hotspot. The Mac then gets internet over the cable while its Wi-Fi stays on ChemShield-Lab.

---

## If something goes wrong

| Problem | Fix |
|---|---|
| HMI says offline / station not answering | `bash fpr.sh status`, then `bash fpr.sh start` |
| `fpr.sh` can't reach the Pi | Is the Mac on ChemShield-Lab? Wait 2 min after the hotspot went off. |
| Stealth script says "station not ready" | Wait for NORMAL on the HMI and run it again |
| A pump or mixer misbehaves | Press the **E-stop** (HMI shows HALTED). Release, then **RESUME DOSING**. |
| A live test fails | Show the recorded evidence (the CSVs and terminal outputs in `evidence/fpr_runs/20261115_*`) |
