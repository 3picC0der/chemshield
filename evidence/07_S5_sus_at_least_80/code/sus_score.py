#!/usr/bin/env python3
"""SUS scoring for ISE-AT-03 (S5: mean SUS >= 80).

    python sus_score.py --add P1 4 2 5 1 4 2 5 1 4 2
    python sus_score.py --add P2 5 1 5 2 4 1 5 1 5 1 --tasks 5/5
    python sus_score.py --report

Ten answers per participant, in question order, each 1-5.
Odd questions score (answer - 1), even questions score (5 - answer), sum x 2.5.

Answers are appended to ../data/sus_responses.csv (the S5 evidence folder), so the raw data stays with
the evidence and the arithmetic can be rechecked by hand.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "..", "data", "sus_responses.csv")
os.makedirs(os.path.dirname(CSV), exist_ok=True)
HEAD = ["participant", "q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10",
        "sus_score", "tasks_passed", "critical_failure", "notes"]


def score(answers: list[int]) -> float:
    if len(answers) != 10 or any(a < 1 or a > 5 for a in answers):
        raise SystemExit("need exactly 10 answers, each 1-5")
    total = sum((a - 1) if i % 2 == 0 else (5 - a) for i, a in enumerate(answers))
    return total * 2.5


def load() -> list[dict]:
    if not os.path.exists(CSV):
        return []
    with open(CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def add(pid: str, answers: list[int], tasks: str, critical: bool, notes: str) -> None:
    rows = load()
    if any(r["participant"] == pid for r in rows):
        raise SystemExit(f"{pid} is already in {os.path.basename(CSV)}; "
                         f"use a different id or edit the file by hand")
    s = score(answers)
    new = dict(zip(HEAD[1:11], answers))
    new.update(participant=pid, sus_score=f"{s:.1f}", tasks_passed=tasks,
               critical_failure="yes" if critical else "no", notes=notes)
    write = not os.path.exists(CSV)
    with open(CSV, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEAD)
        if write:
            w.writeheader()
        w.writerow(new)
    print(f"{pid}: SUS {s:.1f}   (odd sum {sum(answers[i] - 1 for i in range(0, 10, 2))}, "
          f"even sum {sum(5 - answers[i] for i in range(1, 10, 2))})")


def report() -> int:
    rows = load()
    if not rows:
        print(f"no responses yet in {CSV}")
        return 1
    xs = [float(r["sus_score"]) for r in rows]
    n = len(xs)
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    # t for 95%, two-sided, small samples
    tcrit = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447,
             8: 2.365, 9: 2.306, 10: 2.262}.get(n - 1, 1.96)
    half = tcrit * sd / math.sqrt(n) if n > 1 else float("nan")
    crit = [r["participant"] for r in rows if r["critical_failure"] == "yes"]

    print(f"\nISE-AT-03 · S5 · mean SUS >= 80\n{'-' * 52}")
    for r in rows:
        print(f"  {r['participant']:6s} SUS {float(r['sus_score']):5.1f}   "
              f"tasks {r['tasks_passed'] or '-':5s} "
              f"{'CRITICAL FAILURE' if r['critical_failure'] == 'yes' else ''}")
    print(f"{'-' * 52}")
    print(f"  n = {n}   mean = {mean:.1f}   sd = {sd:.1f}")
    if n > 1:
        print(f"  95% CI = {mean - half:.1f} to {mean + half:.1f}")
    print(f"  min {min(xs):.1f}   max {max(xs):.1f}")
    ok = mean >= 80.0 and not crit
    print(f"\n  mean >= 80 : {'yes' if mean >= 80 else 'NO'}")
    print(f"  unresolved critical-task failures : "
          f"{'none' if not crit else ', '.join(crit)}")
    print(f"  S5 : {'PASS' if ok else 'FAIL'}")
    if n < 5:
        print(f"\n  note: the sheet asks for 5-8 participants; you have {n}.")
    if n > 1 and mean >= 80 and mean - half < 80:
        print("  note: the mean is above 80 but the confidence interval crosses it. "
              "Report the interval and n alongside the mean; do not call it a clean pass.")
    return 0 if ok else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--add", nargs=11, metavar="ID Q1..Q10",
                    help="participant id then 10 answers")
    ap.add_argument("--tasks", default="", help="tasks passed, e.g. 5/5")
    ap.add_argument("--critical", action="store_true",
                    help="flag an unresolved critical-task failure (T4)")
    ap.add_argument("--notes", default="")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    if a.add:
        add(a.add[0], [int(x) for x in a.add[1:]], a.tasks, a.critical, a.notes)
        return 0
    if a.report:
        return report()
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
