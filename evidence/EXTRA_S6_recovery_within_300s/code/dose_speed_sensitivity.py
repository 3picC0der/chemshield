"""How S6 and C3 change with the dosing speed (the batch assumes 300 mL/min; the pump is 65 mL/min).

    python evidence/EXTRA_S6_recovery_within_300s/code/dose_speed_sensitivity.py

Runs the same 600 events (seed 261) at four dosing speeds and writes ../data/dose_speed_sensitivity.csv.
"""
import csv
import os
import sys
import tempfile
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)
warnings.filterwarnings("ignore")

from sim import batch as B  # noqa: E402
from sim.model import P  # noqa: E402

SPEEDS = [65, 100, 150, 300]
rows = []
for speed in SPEEDS:
    P["dose_speed_ml_per_min"] = float(speed)
    with tempfile.TemporaryDirectory() as tmp:
        s = B.run(events=600, seed=261, out=os.path.join(tmp, "b.csv"), traces=False, quiet=True)
    rows.append({"dose_speed_ml_per_min": speed, "events": s["events"],
                 "within_300s": s["within_300"], "pct_within_300s": round(s["pct_within_300"], 2),
                 "recovery_max_s": round(s["rec_max"], 1), "recovery_mean_s": round(s["rec_mean"], 1),
                 "reagent_max_mmol": round(s["total_mmol_max"], 3), "events_over_50_mmol": s["over_50"],
                 "ended_in_band_6_to_8.5": s["in_band"], "escalations": s["escalations"], "chem_source": s["chem_source"]})
    print(rows[-1])
out = os.path.join(HERE, "..", "data", "dose_speed_sensitivity.csv")
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
