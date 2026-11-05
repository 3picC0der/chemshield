"""The same 600 events with the fixed-gain PI recovery instead of the planner (S9).

SIMULATION, NOT RIG DATA. Same seed, scenarios and 120 mL/min as run_batch_120.py; 'pi' is the
controller already in sim/sim2.py.

    python report3/simulation_NOT_rig_evidence/run_pi_compare_120.py
"""
import csv
import json
import os
import warnings

warnings.filterwarnings("ignore")
import numpy as np

import sim.model as model

model.P.update(model.make_par(dose_speed_ml_per_min=120.0))
from sim import batch, sim2
from sim import scenarios as SC
from sim.engine import use_table_chemistry

P = model.P
HERE = os.path.dirname(os.path.abspath(__file__))
source = use_table_chemistry()
EVENTS, SEED = 600, 261
out = []
for kind in ("rdo", "pi"):
    scs = SC.population(EVENTS, seed=SEED)
    rng = np.random.default_rng(SEED + 1)
    for i, sc in enumerate(scs, start=1):
        truth = model.Truth(rng)
        r = sim2.run_event(sc, kind, rng, truth, P)
        pts = batch._trace(r)
        rec = batch._recovery_time(pts)
        acid = sc["n0"] > 0
        peak = batch._far_side(pts, acid)
        excursion = (peak > batch.FAR_HI) if acid else (peak < batch.FAR_LO)
        out.append({"kind": kind, "event_id": i, "status": r.get("status"), "reagent_mmol": r.get("R"),
                    "recovery_time_s": rec, "far_side_peak_ph": round(float(peak), 3), "excursion": bool(excursion),
                    "in_band": bool(r["in_band"]), "end_ph": round(float(r["end"]), 3), "n_doses": r["doses"]})
with open(os.path.join(HERE, "pi_compare_600_at_120mL_min.csv"), "w", newline="", encoding="utf-8") as fh:
    keys = sorted({k for row in out for k in row})
    w = csv.DictWriter(fh, fieldnames=keys)
    w.writeheader()
    w.writerows(out)


def summary(kind):
    rows = [x for x in out if x["kind"] == kind]
    ok = [x for x in rows if x["in_band"]]
    total = sum(float(x["reagent_mmol"]) for x in rows)
    return {"recovered": len(ok), "total_mmol": round(total, 1), "mean_all_mmol": round(total / len(rows), 2),
            "mmol_per_success": round(total / len(ok), 2), "not_recovered": len(rows) - len(ok)}


s = {k: summary(k) for k in ("rdo", "pi")}
pi_ok = {x["event_id"] for x in out if x["kind"] == "pi" and x["in_band"]}
rdo_ok = {x["event_id"] for x in out if x["kind"] == "rdo" and x["in_band"]}
both = pi_ok & rdo_ok
mean = lambda kind: float(np.mean([float(x["reagent_mmol"]) for x in out if x["kind"] == kind and x["event_id"] in both]))
s["both_recovered"] = len(both)
s["both_mean_mmol"] = {k: round(mean(k), 2) for k in ("rdo", "pi")}
s["planner_vs_pi_on_both_pct"] = round(100 * (mean("rdo") - mean("pi")) / mean("pi"), 1)
per_success = {k: sum(float(x["reagent_mmol"]) for x in out if x["kind"] == k) / s[k]["recovered"] for k in ("rdo", "pi")}
s["saving_per_success_pct"] = round(100 * (1 - per_success["rdo"] / per_success["pi"]), 1)
s.update(chem_source=source, seed=SEED, events=EVENTS, dose_speed_ml_per_min=120.0)
with open(os.path.join(HERE, "pi_compare_600_at_120mL_min_summary.json"), "w", encoding="utf-8") as fh:
    json.dump(s, fh, indent=1)
print(json.dumps(s, indent=1))
