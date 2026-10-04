# Spec 5 · System Usability Scale of at least 80

| | |
|---|---|
| **Binder test ID** | ISE-AT-03 |
| **Department / type** | ISE · Specification |
| **Verdict** | **DATA PENDING.** The study kit, the HMI and the scoring script are ready; the participants' forms and the mean score are to be added by Hattan |
| **Evidence level** | Planned: 5 to 8 students on the real HMI |

| No. | Specification (full text) | Test procedure | Result / evidence |
|---|---|---|---|
| **S5** | Achieve a System Usability Scale score of at least 80 for the operator interface. | 1. Recruit 5 to 8 students who are not on the team and have never seen the HMI. | Participants: ______ |
| | | 2. Set up the HMI on the study laptop: `python -m hmi.demo` (the full HMI on a simulated tank; a purple SIMULATED band stays on screen). Before each person reset it: `python -m hmi.facilitator reset`. Follow `SUS_study_kit.md`. | Setup checked: ______ |
| | | 3. Read the script word for word, then the five tasks one at a time, with no help: (1) read the pH and the state; (2) request 10 mL of bulk base; (3) explain the alarm after the facilitator injects an upset; (4) acknowledge the decision request and halt dosing; (5) find the last three rejected commands. Record time and success. | Tasks passed per person: ______ |
| | | 4. Each person fills in the standard 10-question SUS form (answers 1 to 5). | Signed forms: ______ |
| | | 5. Score each form: `python code/sus_score.py --add P1 <10 answers>`, then `python code/sus_score.py --report` for the mean and its 95% interval. | Scores: ______. Mean: ______. |

## Verdict

**DATA PENDING.** Pass if the mean SUS score is 80 or more and no participant had an unresolved critical-task failure.

## What to add

| File | What it is |
|---|---|
| `data/sus_responses.csv` | Created by `code/sus_score.py` as the answers are entered: one row per participant with the score |
| `data/sus_forms_signed.*` | Scans of the signed forms |
| `plots/sus_scores.png` (optional) | The scores per participant |

## Files in this folder

- `SUS_study_kit.md`: the facilitator checklist, the script to read aloud, the task card, the SUS form and how to score it.
- `code/sus_score.py`: the scoring script. `code/hmi/`: the HMI that the participants use (a snapshot; `hmi/DESIGN.md` is the design it follows, `hmi/static/` is the screen).
- The HMI as a ready-to-send folder for the study laptop: `ChemShield_HMI_SUS.zip` in the project files, or this repository (the steps to install and start it are in `../SETUP.md`, Part G).

## Notes

- With n = 5 the 95% interval will be wide whatever the mean is; report the mean with its interval and n.
- If the study cannot be completed in time, ISE's satisfactory pair can use Spec 6 instead (`../EXTRA_S6_recovery_within_300s/`), which is proven in simulation.
