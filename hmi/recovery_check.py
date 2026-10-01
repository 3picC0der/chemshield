"""Run the real station (simulated tank, doses added automatically) through upsets and
count how many recover on their own, and how often Model A blocked the planner's dose.

    .venv/bin/python -m hmi.recovery_check                       20 runs per upset
    .venv/bin/python -m hmi.recovery_check --seeds 40 --start 20 --out runs.csv

Upsets: 7 mL acid (INT-AT-01), 40 and 80 mL acid, 40 and 80 mL base, all 0.5 M. A run
"recovers" when the event closes by itself; "escalate" is OPERATOR DECISION REQUIRED.
"""
from __future__ import annotations

import argparse
import csv
import sys
import tempfile
import time
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

warnings.filterwarnings("ignore")

CASES = [("acid", 7.0), ("acid", 40.0), ("acid", 80.0), ("base", 40.0), ("base", 80.0)]


def one(args):
    acid_word, ml, seed = args
    warnings.filterwarnings("ignore")
    from hmi.station.core import Station
    from hmi.station.links import SimLink

    class Clock:
        t = 1000.0

        def __call__(self):
            return self.t

    clk = Clock()
    link = SimLink(start_ph=7.0, auto_pump=True, seed=seed, clock=clk)
    st = Station(link, "check-secret", log_dir=Path(tempfile.mkdtemp()), clock=clk, dwell_s=10)
    link.start()

    def run(s):
        end = clk.t + s
        while clk.t < end:
            clk.t += 0.1
            st.tick()

    run(6)
    with st.lock:
        link.upset(ml, acid=(acid_word == "acid"))
    outcome, blocks = "timeout", 0
    for _ in range(600):
        run(1)
        if st.mode == "ESCALATE":
            outcome = "escalate"
            break
        if st.events and st.events[-1]["status"] == "closed":
            outcome = "recovered"
            break
    blocks = sum(1 for d in st.decisions if d.get("reason_code") in ("MODEL_A_BLOCK", "MODEL_A_TIMEOUT"))
    harmful_seen = sum(1 for d in st.decisions if d.get("model_a_label") not in ("ACCEPTABLE_CONTEXT", "NOT_CALLED"))
    ev = st.events[-1] if st.events else {}
    return {"case": f"{acid_word}_{ml:g}mL", "seed": seed, "outcome": outcome, "model_a_blocks": blocks,
            "model_a_not_acceptable": harmful_seen, "recovery_time_s": ev.get("recovery_time_s"),
            "final_ph": round(link.tank.ph_true, 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--out", default="recovery_check.csv")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    jobs = [(w, ml, 1000 + s) for (w, ml) in CASES for s in range(a.start, a.start + a.seeds)]
    t0 = time.time()
    with ProcessPoolExecutor(a.workers) as ex:
        rows = list(ex.map(one, jobs))
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} runs in {time.time() - t0:.0f} s")
    for case in dict.fromkeys(r["case"] for r in rows):
        rs = [r for r in rows if r["case"] == case]
        rec = sum(r["outcome"] == "recovered" for r in rs)
        blk = sum(r["model_a_blocks"] for r in rs)
        print(f"  {case:12s} recovered {rec}/{len(rs)}   Model A blocks of planner doses: {blk}")


if __name__ == "__main__":
    main()
