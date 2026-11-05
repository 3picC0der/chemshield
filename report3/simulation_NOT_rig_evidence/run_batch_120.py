"""600-event batch on the real planner at the 120 mL/min the signed dose commands state.

SIMULATION, NOT RIG DATA: chemistry is the placeholder NaHCO3 table, not Aspen, and the pump,
mixing and probe numbers are the design values, not values measured on the rig.

    python report3/simulation_NOT_rig_evidence/run_batch_120.py
"""
import json
import os
import warnings

warnings.filterwarnings("ignore")
import sim.model as model

model.P.update(model.make_par(dose_speed_ml_per_min=120.0))
from sim import batch

HERE = os.path.dirname(os.path.abspath(__file__))
s = batch.run(events=600, seed=261, out=os.path.join(HERE, "batch_600_at_120mL_min.csv"), traces=False)
s["out"] = os.path.basename(s["out"])
s["dose_speed_ml_per_min"] = 120.0
with open(os.path.join(HERE, "batch_600_at_120mL_min_summary.json"), "w", encoding="utf-8") as fh:
    json.dump(s, fh, indent=1)
