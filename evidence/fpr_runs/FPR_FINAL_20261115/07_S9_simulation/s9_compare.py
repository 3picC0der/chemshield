"""S9: reagent used by the recovery solver vs the PI controller, same 600 simulated spills.

    ../chemshield/.venv/bin/python -W ignore evidence/S9_sim_comparison/s9_compare.py

Both controllers run in sim/sim2.py's harness on identical scenarios and identical noise
(seeded), with the same pumps, dose cap and mixing holds. Saving is computed over the
events that both controllers brought back into 6.0-8.5.
"""
import collections, csv, json, os, sys, time
import numpy as np
sys.path.insert(0, os.getcwd())
from sim import sim2
from sim.engine import use_table_chemistry

HERE = os.path.dirname(os.path.abspath(__file__))
src = use_table_chemistry()
scs = sim2.scenarios(600, seed=261)
out = {}
for kind in ("pi", "rdo"):
    t0 = time.time(); out[kind] = sim2.bench(kind, scs, seed=11)
    s = sim2.summary(out[kind])
    print(kind, f"{time.time()-t0:.0f}s", {k: round(float(v), 2) for k, v in s.items()})
    print("  status", collections.Counter(r["status"] for r in out[kind]).most_common(5))
pi, rd = out["pi"], out["rdo"]
both = [i for i in range(len(scs)) if pi[i]["in_band"] and rd[i]["in_band"]]
Rp = np.array([pi[i]["R"] for i in both]); Rr = np.array([rd[i]["R"] for i in both])
res = dict(events=len(scs), pi_success=int(sum(r["in_band"] for r in pi)),
           solver_success=int(sum(r["in_band"] for r in rd)), paired=len(both),
           pi_mean_mmol=float(Rp.mean()), solver_mean_mmol=float(Rr.mean()),
           saving_total_pct=float(100 * (1 - Rr.sum() / Rp.sum())),
           saving_median_pct=float(np.median(100 * (1 - Rr / Rp))),
           solver_less_pct_of_events=float((Rr < Rp).mean() * 100),
           pi_far_ok=float(np.mean([r["far_ok"] for r in pi]) * 100),
           solver_far_ok=float(np.mean([r["far_ok"] for r in rd]) * 100),
           pi_mean_t=float(np.mean([r["t"] for r in pi])), solver_mean_t=float(np.mean([r["t"] for r in rd])))
print(json.dumps(res, indent=1))
json.dump(res, open(os.path.join(HERE, "s9_summary.json"), "w"), indent=1)
with open(os.path.join(HERE, "s9_per_event.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(["event", "acid_spill", "spill_ml", "pi_mmol", "pi_in_band", "pi_status", "solver_mmol", "solver_in_band", "solver_status"])
    for i, sc in enumerate(scs):
        w.writerow([sc["id"], sc["acid"], round(sc["vol"], 2), round(pi[i]["R"], 3), pi[i]["in_band"], pi[i]["status"], round(rd[i]["R"], 3), rd[i]["in_band"], rd[i]["status"]])
