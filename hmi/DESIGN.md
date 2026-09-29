# HMI design — specification for the build

**Design owner:** Hattan (ISE) · **Build owner:** Khalid (ICS) · **Handed over:** 28 Sep

This is the screen Khalid builds. `wireframe.html` next to this file is the same design as
a static page — open it in a browser and copy the layout; it has no live data in it.

Two things depend on this screen and neither is optional:

- **S5** is measured on it. Five strangers have to do five tasks on it without help
  (ISE-AT-03). Every one of those five tasks must be possible, or the study cannot run.
- **ISE-AT-01, ISE-AT-02, INT-AT-01 and INT-AT-02** are all filmed against readouts on this
  screen. If a number is not on screen, the video is not evidence.

---

## 1. The five things the test sheets read off this screen

Build these five first. Everything else is layout.

| # | Element | Exact wording | Read by |
|---|---|---|---|
| 1 | **State banner** | `NORMAL` / `UNSAFE EVENT — RECOVERY IN PROGRESS` / `OPERATOR DECISION REQUIRED` / `HALTED` | INT-AT-01, SUS T1, T3 |
| 2 | **Recovery timer** | `Recovery 96 s / 300 s` counting up, turns amber past 240 s, red past 300 s | ISE-AT-02 step 1, INT-AT-02 |
| 3 | **Event reagent counter** | `Event reagent: 24.3 / 50 mmol` with a bar. This is reagent **already delivered** this event, not planned. | ISE-AT-01 steps 1–3 |
| 4 | **pH value + trend chart** | big number, plus a time chart with **horizontal lines drawn at 6.0 and 8.5** and at 5.5 / 9.5 | INT-AT-02 setup, SUS T1 |
| 5 | **Rejected-command log** | time, source, **reason code**, filterable to rejections only | S3 demo, SUS T5 |

The reason codes come straight from I1 and must be shown as words, not numbers:
`REPLAY`, `STALE`, `LIMIT`, `LOCKOUT`, `MODEL_A_BLOCK`, `SCHEMA`, `RATE`, `SEQUENCE`,
`AUTH`, `STATE`.

---

## 2. Layout

Three columns under a title bar and an alert strip. 1400 px wide, designed for the booth
screen; it should still be usable at 1280.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  ChemShield — Neutralisation Tank T-101      ● gateway online   14:22:07   │
├────────────────────────────────────────────────────────────────────────────┤
│  ⚠ UNSAFE DOSING EVENT — RECOVERY IN PROGRESS                              │
│    Event E-2291 · Recovery 96 s / 300 s · Event reagent 24.3 / 50 mmol     │
├──────────────────┬──────────────────────────────┬──────────────────────────┤
│ TANK pH          │ RECOVERY PLAN                │ OPERATOR ACTION          │
│   4.63           │  (MILP, re-solved each read) │   [ HALT DOSING ]        │
│   band bar       │  table of doses + status     │   [ ACKNOWLEDGE ]        │
│   trend chart    │  totals: reagent, time,      │                          │
│   with 6.0/8.5   │  predicted far-side pH       │ MANUAL DOSE              │
│                  │                              │   channel ▾  mL [   ]    │
│ EVENT DETAIL     │  "Why this plan" note        │   [ REQUEST DOSE ]       │
│   class, score,  │                              │                          │
│   Model A label, │                              │ SAFETY STATE             │
│   latency        │                              │   5 rows of yes/no       │
├──────────────────┴──────────────────────────────┴──────────────────────────┤
│  AUDIT LOG   [ all ] [ rejected only ]        append-only, hash chained     │
└────────────────────────────────────────────────────────────────────────────┘
```

### Type sizes — please do not shrink these
Operators read this from a metre away and graders read it over someone's shoulder.

| Element | Size |
|---|---|
| pH value | 52 px bold |
| Banner headline | 22 px bold |
| Recovery timer, reagent counter | 20 px bold |
| Card headings | 13 px, letter-spaced, uppercase |
| Table and key/value text | 15 px |
| Log rows | 14 px monospace |
| Buttons | 18 px bold, at least 48 px tall |

---

## 3. What each panel shows

### Alert strip
Hidden in NORMAL. In RECOVERY it is red and holds: event ID, the classification, the
**recovery timer**, and the **event reagent counter**. These two are the numbers the
camera has to see, so they belong here, at the top, not buried in a card.

When the planner returns `ESCALATE`, the strip turns amber and reads
**`OPERATOR DECISION REQUIRED — <reason>`**, with the reason in words:

| I4 reason | Shown as |
|---|---|
| `INFEASIBLE` | "No safe dose is available. Automatic recovery has stopped." |
| `BUDGET` | "The 50 mmol reagent limit for this event is used up." |
| `TIME` | "This event has run past its time budget." |
| `STALE` | "The pH reading is too old to dose on." |
| `SOLVER_FAIL` | "The optimiser did not return. Automatic recovery has stopped." |

### Tank pH
Big number, colour by zone: green inside 6.0–8.5, amber 5.5–6.0 and 8.5–9.5, red outside.
Under it a horizontal band bar (ticks at 2, 4, 5.5, 6.0, 8.5, 9.5, 12) and a trend chart of
the last 300 s. **The 6.0 and 8.5 lines must be drawn on the chart**, not just implied by
shading — INT-AT-02's setup checklist asks for them by name.

Also show: `mean of 3 readings, ±0.1 pH` and the sample age in seconds. An operator has to
be able to see that a reading is stale.

### Event detail
Class, risk score, Model A label and **latency in ms** (that is Belal's S4 evidence, and
it lives on this screen), the rejected command that started it, and how much reagent got
in before the block.

### Recovery plan
One row per planned dose: number, channel (`NaOH 0.5 M bulk` — words, not `BASE_BULK`),
dose mL, mmol, hold s, status (complete / dosing / mixing 8 s / queued). Then totals:
reagent used vs the 50 mmol ceiling, elapsed vs the 300 s budget, and the predicted
far-side pH with "no overshoot" or a warning.

Keep the **"Why this plan"** note. It is the one place the screen explains itself, and it
is what makes SUS task T3 answerable by someone who has never seen the system.

### Operator action
`HALT DOSING` (red, always enabled) and `ACKNOWLEDGE` (outline). Both must work during an
escalation — SUS task T4 is "acknowledge it and stop automatic dosing", so those two
buttons have to be findable and pressable in that state.

**Manual dose** is a channel dropdown, a mL field and a `REQUEST DOSE` button. SUS task T2
is "request a 10 mL dose of bulk base", and ISE-AT-01 step 3 needs a manual 20 mL request
to be rejected with `LIMIT`. Send it as a normal I1 request; show the gateway's decision
and reason inline next to the button, not in a popup.

### Audit log
Newest first, with a filter toggle `all` / `rejected only`. Columns: time, source
(gateway / model A / optimiser / PLC / HMI), message, reason code, hash prefix. SUS task
T5 is "find the last three rejected commands and why" — the filter is what makes that a
10-second task instead of a scroll.

---

## 4. Where the data comes from

| Panel | Source |
|---|---|
| pH, temperature, level, state, event reagent | **I2**, once a second, from `sim.live` |
| Recovery plan table, predicted far-side pH, "why this plan" | **I4** reply from `redosing.planner.plan_block()` — it returns `block`, `block_mmol`, `solve_ms` and `z_umol` |
| Model A label, score, latency | **I3** reply |
| Manual dose request and its decision | **I1** request and the gateway's reply |
| Audit log | gateway's hash-chained log |

`sim.live` publishes I2 as one JSON object per line on stdout and, with `--udp HOST:PORT`,
as one datagram per message. Test the screen against it before anything else exists:

```bash
python -m sim.live --scenario acid_upset_max --autopilot --udp 127.0.0.1:9101
```

That gives a full 40 mmol acid upset recovering by itself in about two minutes, with the
reagent counter climbing to about 40 mmol and stopping — every element on this screen has
something to show while it runs.

---

## 5. Colour and state

| State | Banner | Meaning |
|---|---|---|
| `NORMAL` | hidden / green dot | nothing happening |
| `RECOVERY` | red | an unsafe event was confirmed, the MILP is dosing |
| `ESCALATE` | amber | the operator has to decide |
| `HALTED` | grey | the operator stopped it |

Green `#167A5A`, amber `#B97800`, red `#A83232`, ink `#111318`, muted `#5F6670`,
card border `#CBD2DA`, page `#EDEFF2`, title bar `#17365D`. Never use colour alone — every
state also has a word.

---

## 6. Things not to do

- Do not show a raw objective value, a solver gap, or `z` as if it were a safety margin.
  The report commits to this in §4.2: the HMI "never exposes a raw objective as a safety
  assurance". Show predicted far-side pH instead.
- Do not let the screen issue a dose except as an I1 request through the gateway. The HMI
  has no authority; that is the whole point of C2.
- Do not put the Model A label where it can be read as a decision. It is advisory; the
  gateway decides.
- Do not hide the reagent counter or the timer behind a tab.

---

## 7. What I need back from you, Khalid

1. A build I can run by **Thursday 1 Oct morning**, so the SUS study has a day.
   It does not need to be pretty — it needs the five elements in §1 and the five SUS
   tasks to be completable.
2. Tell me if any of the five tasks is impossible in your build, **before** Thursday. A
   task nobody can finish scores the whole study, not just that task.
3. The reason codes you actually emit, so the log column and my task card use your words.
