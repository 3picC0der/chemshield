# ISE-AT-03 — SUS study kit (S5: mean SUS ≥ 80)

Everything needed to run the usability study. Print sections 2, 3 and 4, one set per
participant. Facilitator: **Hattan**. Note taker: **one other team member, not Khalid**
(he built it, so he will want to help, and helping invalidates the run).

**Run it Thursday 1 Oct** on the integrated HMI. 5–8 participants, ~15 minutes each.
Participants must be students who are **not on the team** and have **never seen the HMI**.

---

## 1. Facilitator checklist

Before each participant:

- [ ] `.venv/bin/python -m hmi.demo` running; tank reset to pH 7.0 and state `NORMAL`
      (`.venv/bin/python -m hmi.facilitator reset`)
- [ ] Audit log showing "all", scrolled to the top (it is append-only, so it can't be
      cleared; newest entries are on top). Before the **first** participant, put a few
      rejections in it for T5: `.venv/bin/python -m hmi.attack_station --mode replay-now --n 2`
      and `.venv/bin/python -m hmi.attack_station --mode stale --n 1`
- [ ] Browser zoom at 100%, screen at the booth resolution
- [ ] Timer ready; blank task record and SUS form printed
- [ ] Screen recording on (only with the participant's spoken permission)

Read this to everyone, word for word, so no one gets more help than anyone else:

> "This is a control screen for a chemical tank. We are testing the screen, not you — if
> something is confusing, that is a problem with our design. Please think aloud as you go.
> I will read you five short tasks. I cannot help you during a task, and that is not
> because you are doing badly. When you finish all five there is a short questionnaire."

During tasks: say nothing except "take your time" and "tell me when you think you're
done". Record time and whether they finished **without help**. If they are stuck for
**90 seconds**, mark it failed, say "let's move to the next one", and move on.

---

## 2. Task card (read one at a time)

| # | Read this to the participant | Counts as success when |
|---|---|---|
| **T1** | "Tell me the current pH of the tank, and whether the tank is in a safe state right now." | Reads the pH correctly and says the state from the banner |
| **T2** | "Request a 10 mL dose of bulk base." | Picks `NaOH 0.5 M bulk`, enters 10, presses Request, and sees the reply |
| **T3** | *(facilitator injects an acid upset)* "An alarm just went off. Tell me what happened and what the system is doing about it." | Says the pH went low / an unsafe dose happened, **and** that the system is recovering by itself |
| **T4** | *(facilitator triggers an escalation)* "The system is asking for your decision. Acknowledge it, and stop the automatic dosing." | Presses Acknowledge, then Halt Dosing |
| **T5** | "Find the last three rejected commands and tell me why each one was rejected." | Opens the log (or the rejected-only filter) and reads three reason codes |

Injections the facilitator does from a second terminal window, out of the participant's
sight (the HMI's own engineer panel has the same controls, so keep it closed):

```bash
# T3: an acid upset; the banner turns red and recovery starts by itself
.venv/bin/python -m hmi.facilitator upset medium_acid
# T4: while that recovery runs, ask for the operator's decision
.venv/bin/python -m hmi.facilitator escalate
# between participants: fresh tank at pH 7, NORMAL, nothing halted
.venv/bin/python -m hmi.facilitator reset
```

T2 note: 10 mL of the 0.5 M base at pH 7 would push the tank past 9.5, so the gateway
rejects it (Model A block) and says why. That still counts: the task is to send the
request and see the reply.

---

## 3. Task record — one per participant

Participant ID: ______  Date: ______  Facilitator: ______  Note taker: ______

Background (circle): engineering student / other · has used an industrial control screen
before: yes / no

| Task | Finished without help | Time (s) | Errors / wrong turns | What they said |
|---|---|---|---|---|
| T1 | ☐ yes ☐ no | | | |
| T2 | ☐ yes ☐ no | | | |
| T3 | ☐ yes ☐ no | | | |
| T4 | ☐ yes ☐ no | | | |
| T5 | ☐ yes ☐ no | | | |

Tasks passed: ____ / 5

**Critical-task rule:** T4 is the critical task. If a participant cannot stop automatic
dosing, that is an unresolved critical-task failure and S5 fails regardless of the score.
Write down exactly what they tried.

---

## 4. SUS questionnaire — standard wording, do not edit

Circle one number per line. 1 = strongly disagree, 5 = strongly agree.

| # | Statement | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 1 | I think that I would like to use this system frequently. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | I found the system unnecessarily complex. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | I thought the system was easy to use. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | I think that I would need the support of a technical person to be able to use this system. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | I found the various functions in this system were well integrated. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | I thought there was too much inconsistency in this system. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | I would imagine that most people would learn to use this system very quickly. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | I found the system very cumbersome to use. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | I felt very confident using the system. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | I needed to learn a lot of things before I could get going with this system. | ☐ | ☐ | ☐ | ☐ | ☐ |

Anything that confused you, in your own words:

_______________________________________________________________________________

*(Brooke 1996, reference [11] in the report. The wording is standard and must not be
changed — a reworded SUS is not a SUS and the ≥80 threshold no longer means anything.)*

---

## 5. Scoring

Odd questions (1, 3, 5, 7, 9): score = answer − 1.
Even questions (2, 4, 6, 8, 10): score = 5 − answer.
Add all ten, multiply by 2.5. Range 0–100.

Type the answers into `sus_score.py` and it does the arithmetic and the confidence
interval:

```bash
python evidence/07_S5_sus_at_least_80/code/sus_score.py --add P1 4 2 5 1 4 2 5 1 4 2
python evidence/07_S5_sus_at_least_80/code/sus_score.py --report
```

**S5 passes only if** the sample mean is ≥ 80 **and** no participant had an unresolved
critical-task failure. Report the mean with its 95% confidence interval and n — a mean of
81 from five people with a CI of 68–94 should be described as such, not as a clean pass.

For context when you write it up: 68 is the SUS average across all systems ever tested,
80 is roughly the top 10%, and with n = 5 the interval will be wide no matter what the
mean is. Say the n out loud at the booth.

---

## 6. Ethics and data

- Verbal consent, recorded on the task sheet. No names — participant IDs only.
- Screen recording only if they say yes; face and voice not recorded.
- Forms are kept by ISE until the FPR and then destroyed.
- Tell them they can stop at any point without giving a reason.
