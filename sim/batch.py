"""600-event batch runner: the evidence behind C3, S6, INT-S2 and INT-S3.

    python -m sim.batch --events 600 --seed 261 --out ISE-AT-01_batch.csv

Writes two CSVs:
  <out>            one row per recovery event (the numbers for the test sheets)
  <out>_traces.csv one row per pH sample (event_id, t_s, ph) for the trace plots

Definitions used for the timing columns (test sheets ISE-AT-02 and INT-AT-02):

  recovery_time_s   seconds from EVENT_CONFIRMED to the first moment pH enters
                    6.0-8.5 and then stays inside for the rest of the event.
                    This is the test sheets' definition.
  controller_stop_s seconds from EVENT_CONFIRMED until the controller itself declares
                    the recovery finished, which is after the final mixing hold, settle
                    and triplicate read. This is the definition the Second Report
                    Installment quotes, and it is always the larger of the two.

Both are written so either definition can be checked. The pass rule on the sheets is
applied to recovery_time_s; controller_stop_s is reported alongside it.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

from . import model as Mo
from . import scenarios as SC
from . import sim2
from .engine import use_table_chemistry
from .model import P

BAND_LO, BAND_HI = P["band"]          # 6.0, 8.5
FAR_LO, FAR_HI = P["ovs"]             # 5.5, 9.5
T_SPEC = P["T_spec"]                  # 300 s
R_MAX = P["R_max"]                    # 50 mmol

COLUMNS = [
    "event_id", "scenario", "chem_source", "seed",
    "upset_dir", "upset_ml", "upset_mmol", "start_ph", "fill_L",
    "n_doses", "n_reads", "total_mmol", "max_dose_ml",
    "recovery_time_s", "controller_stop_s", "within_300s",
    "end_ph", "in_band", "far_side_peak_ph", "excursion", "outcome",
]


def _trace(row: dict) -> list[tuple[float, float]]:
    """[(t_s, ph)] from EVENT_CONFIRMED through the last dose."""
    pts = [(float(row["t0"]), float(row["ph0"]))]
    pts += [(float(s["t"]), float(s["pH_after"])) for s in row["steps"]]
    return pts


def _recovery_time(pts: list[tuple[float, float]]) -> float | None:
    """First time pH is inside the band and never leaves it again."""
    inside = [BAND_LO <= p <= BAND_HI for _t, p in pts]
    first = None
    for i in range(len(pts)):
        if inside[i] and all(inside[i:]):
            first = pts[i][0]
            break
    return first


def _far_side(pts: list[tuple[float, float]], acid_upset: bool) -> float:
    """Worst pH on the side opposite the upset, over the recovery (after the upset)."""
    seg = [p for _t, p in pts[1:]] or [pts[0][1]]
    return max(seg) if acid_upset else min(seg)


def run(events: int = 600, seed: int = 261, out: str = "ISE-AT-01_batch.csv",
        traces: bool = True, quiet: bool = False) -> dict:
    source = use_table_chemistry()
    scs = SC.population(events, seed=seed)
    rng = np.random.default_rng(seed + 1)

    rows, trace_rows = [], []
    t_start = time.time()
    for i, sc in enumerate(scs, start=1):
        truth = Mo.Truth(rng)
        r = sim2.run_event(sc, "rdo", rng, truth, P)
        pts = _trace(r)
        rec = _recovery_time(pts)
        acid = sc["n0"] > 0
        peak = _far_side(pts, acid)
        excursion = (peak > FAR_HI) if acid else (peak < FAR_LO)
        escalated = "ESCALATE" in str(r["status"])
        # an event the planner handed to the operator has no automatic recovery time
        rec_report = rec if (rec is not None and not escalated) else None

        rows.append({
            "event_id": i,
            "scenario": sc["name"],
            "chem_source": source,
            "seed": seed,
            "upset_dir": "ACID" if acid else "BASE",
            "upset_ml": round(sc["vol"], 3),
            "upset_mmol": round(abs(sc["n0"]) * 1000.0, 4),
            "start_ph": round(pts[0][1], 4),
            "fill_L": round(sc["V"], 4),
            "n_doses": r["doses"],
            "n_reads": r["reads"],
            "total_mmol": round(r["R"], 4),
            "max_dose_ml": round(max([s["v"] for s in r["steps"]], default=0.0), 3),
            "recovery_time_s": round(rec_report, 2) if rec_report is not None else "",
            "controller_stop_s": round(r["t"], 2),
            "within_300s": int(rec_report is not None and rec_report <= T_SPEC),
            "end_ph": round(r["end"], 4),
            "in_band": int(bool(r["in_band"])),
            "far_side_peak_ph": round(peak, 4),
            "excursion": int(bool(excursion)),
            "outcome": "ESCALATE" if escalated else str(r["status"]),
        })
        if traces:
            for t_s, ph_v in pts:
                trace_rows.append((i, round(t_s, 2), round(ph_v, 4)))

    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    tpath = ""
    if traces:
        tpath = os.path.splitext(out)[0] + "_traces.csv"
        with open(tpath, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["event_id", "t_s", "ph"])
            w.writerows(trace_rows)

    tot = np.array([r["total_mmol"] for r in rows], float)
    rt = np.array([r["recovery_time_s"] for r in rows if r["recovery_time_s"] != ""], float)
    cs = np.array([r["controller_stop_s"] for r in rows], float)
    n = len(rows)
    s = dict(
        events=n, seed=seed, chem_source=source, out=out, traces=tpath,
        wall_s=round(time.time() - t_start, 1),
        total_mmol_max=float(tot.max()), total_mmol_mean=float(tot.mean()),
        over_50=int((tot > R_MAX + 1e-9).sum()),
        within_300=int(sum(r["within_300s"] for r in rows)),
        pct_within_300=100.0 * sum(r["within_300s"] for r in rows) / n,
        rec_mean=float(rt.mean()), rec_max=float(rt.max()),
        stop_mean=float(cs.mean()), stop_p95=float(np.percentile(cs, 95)), stop_max=float(cs.max()),
        in_band=int(sum(r["in_band"] for r in rows)),
        excursions=int(sum(r["excursion"] for r in rows)),
        no_excursion=n - int(sum(r["excursion"] for r in rows)),
        pct_no_excursion=100.0 * (n - sum(r["excursion"] for r in rows)) / n,
        escalations=int(sum(r["outcome"] == "ESCALATE" for r in rows)),
        worst_far_side=float(max(rows, key=lambda r: abs(r["far_side_peak_ph"] - 7.0))["far_side_peak_ph"]),
    )
    s["worst_event"] = int(max(rows, key=lambda r: abs(r["far_side_peak_ph"] - 7.0))["event_id"])
    if not quiet:
        _report(s)
    return s


def _report(s: dict) -> None:
    print(f"\nChemShield batch: {s['events']} events, seed {s['seed']}, "
          f"chemistry = {s['chem_source']}  ({s['wall_s']} s)")
    print(f"  wrote {s['out']}")
    if s["traces"]:
        print(f"  wrote {s['traces']}")
    print(f"\n  C3   reagent per event      max {s['total_mmol_max']:.2f} mmol "
          f"(limit {R_MAX:.0f}), mean {s['total_mmol_mean']:.2f}, over limit: {s['over_50']}")
    print(f"  S6   within {T_SPEC:.0f} s            {s['within_300']}/{s['events']} "
          f"= {s['pct_within_300']:.1f}%   (mean {s['rec_mean']:.1f} s, max {s['rec_max']:.1f} s)")
    print(f"       controller-stop basis  mean {s['stop_mean']:.1f} s, p95 {s['stop_p95']:.1f} s, "
          f"max {s['stop_max']:.1f} s")
    print(f"  INT-S2 ended in 6.0-8.5     {s['in_band']}/{s['events']}")
    print(f"  INT-S3 no far-side excursion {s['no_excursion']}/{s['events']} "
          f"= {s['pct_no_excursion']:.1f}%   worst far-side pH {s['worst_far_side']:.3f} "
          f"(event {s['worst_event']})")
    print(f"  escalations to the operator  {s['escalations']}")
    if s["chem_source"] == "PLACEHOLDER":
        print("\n  chemistry = PLACEHOLDER: these numbers are from the report's charge-balance\n"
              "  equations, not from Aspen. Re-run once CHE delivers sim/aspen_tables/.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m sim.batch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", type=int, default=600)
    ap.add_argument("--seed", type=int, default=261)
    ap.add_argument("--out", default="ISE-AT-01_batch.csv")
    ap.add_argument("--no-traces", action="store_true")
    a = ap.parse_args(argv)
    run(events=a.events, seed=a.seed, out=a.out, traces=not a.no_traces)
    return 0


if __name__ == "__main__":
    sys.exit(main())
