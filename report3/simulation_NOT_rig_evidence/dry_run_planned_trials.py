"""Dry runs of the base-upset trials planned on 5 Nov 2026 and never run on the rig.

SIMULATION, NOT RIG DATA. The real station, gateway, planner and Model A against a simulated
tank, to choose upset sizes that one acid pump could recover from. 'model_a_volume_L' is the
tank size Model A was told; the planner is always told the real one.

    python report3/simulation_NOT_rig_evidence/dry_run_planned_trials.py
"""
import csv
import os
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
from hmi.station.core import Station
from hmi.station.links import SimLink

HERE = os.path.dirname(os.path.abspath(__file__))
# tank L, 0.5 M NaOH mL added by hand, start pH, tank size Model A is told
CASES = [(5.0, 10, 8.3, 5.0), (5.0, 10, 7.0, 5.0), (5.0, 20, 7.0, 5.0), (5.0, 40, 7.2, 5.0),
         (2.5, 5, 7.0, 5.0), (2.5, 10, 7.0, 5.0), (2.5, 15, 7.0, 5.0), (2.5, 20, 7.0, 5.0),
         (2.5, 10, 7.0, 2.5), (2.5, 20, 7.0, 2.5), (2.0, 4, 7.0, 5.0), (2.0, 8, 7.0, 5.0)]
SEEDS = range(1, 7)


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def trial(tank_l, ml, start_ph, model_l, seed):
    clk = Clock()
    link = SimLink(start_ph=start_ph, auto_pump=True, seed=seed, clock=clk)
    s = Station(link, "check-secret", log_dir=Path(tempfile.mkdtemp()), clock=clk, dwell_s=10)
    link.start()
    tank = link.tank
    tank.excess_mmol *= tank_l / tank.volume_L
    tank.volume_L = tank_l
    planner_state = s._planner_state

    def state(now):
        st = planner_state(now)
        st["volume_L"] += tank_l - 5.0
        return st

    s._planner_state = state
    if model_l != 5.0:
        s.context.reset_tank(model_l)

    def run(seconds):
        end = clk.t + seconds
        while clk.t < end:
            clk.t += 0.1
            s.tick()

    run(6)
    with s.lock:
        link.upset(ml, acid=False)
    ph, outcome = [], "timeout"
    for _ in range(600):
        run(1)
        ph.append(float(link.tank.ph_true))
        if s.mode == "ESCALATE":
            outcome = "escalate"
            break
        if s.events and s.events[-1]["status"] == "closed":
            outcome = "recovered"
            break
    ev = s.events[-1] if s.events else {}
    doses = ev.get("doses", [])
    return {"tank_L": tank_l, "naoh_ml": ml, "start_ph": start_ph, "model_a_volume_L": model_l, "seed": seed,
            "outcome": outcome, "sim_recovery_s": ev.get("recovery_time_s"), "n_doses": len(doses),
            "channels": "+".join(sorted({str(d.get("channel_id")) for d in doses})),
            "total_acid_ml": round(sum(d.get("ml", 0) for d in doses), 2),
            "peak_ph": round(max(ph), 2), "lowest_ph": round(min(ph), 2),
            "model_a_blocks": sum(1 for x in s.decisions
                                  if x.get("reason_code") in ("MODEL_A_BLOCK", "MODEL_A_TIMEOUT"))}


rows = [trial(*case, seed) for case in CASES for seed in SEEDS]
with open(os.path.join(HERE, "dry_run_planned_trials.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print(len(rows), "rows")
