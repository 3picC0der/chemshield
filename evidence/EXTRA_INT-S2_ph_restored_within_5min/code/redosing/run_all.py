"""One command: run the batch and produce every ISE and integrated evidence file.

    python -m redosing.run_all                    # 600 events, seed 261
    python -m redosing.run_all --events 100       # quick pass while developing

Writes the batch CSVs, the four figures and the summary JSON into the per-spec evidence
folders (evidence/03_C3_..., EXTRA_S6_..., EXTRA_INT-S2_..., EXTRA_INT-S3_...; each gets
its own copy of the batch), and prints the numbers to copy onto the test sheets.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EV = os.path.join(ROOT, "evidence")

# spec -> evidence folder. All four use the same 600-event batch.
C3 = os.path.join(EV, "03_C3_max_50mmol_per_recovery")
S6 = os.path.join(EV, "EXTRA_S6_recovery_within_300s")
INT2 = os.path.join(EV, "EXTRA_INT-S2_ph_restored_within_5min")
INT3 = os.path.join(EV, "EXTRA_INT-S3_no_far_side_excursion")
FOLDERS = [C3, S6, INT2, INT3]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.run_all")
    ap.add_argument("--events", type=int, default=600)
    ap.add_argument("--seed", type=int, default=261)
    a = ap.parse_args(argv)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from sim import batch as B
        from redosing.qc import far_side, histogram, imr, traces

        for d in FOLDERS:
            os.makedirs(os.path.join(d, "data"), exist_ok=True)
            os.makedirs(os.path.join(d, "plots"), exist_ok=True)

        first = os.path.join(C3, "data", "batch_600_events.csv")
        s = B.run(events=a.events, seed=a.seed, out=first)

        # every sheet says "use the same 600-event batch"; give each folder its own copy
        # so a reviewer who opens one folder has everything that sheet refers to
        src_t = os.path.splitext(first)[0] + "_traces.csv"
        for d in FOLDERS[1:]:
            shutil.copy(first, os.path.join(d, "data", "batch_600_events.csv"))
            shutil.copy(src_t, os.path.join(d, "data", "batch_600_events_traces.csv"))

        batch = lambda d: os.path.join(d, "data", "batch_600_events.csv")  # noqa: E731
        h = histogram.run(batch(C3), os.path.join(C3, "plots", "C3_reagent_per_event_histogram.png"))
        i = imr.run(batch(S6), os.path.join(S6, "plots", "S6_recovery_time_control_chart.png"))
        t = traces.run(batch(INT2), os.path.join(INT2, "plots", "INT-S2_all_recovery_traces.png"))
        f = far_side.run(batch(INT3), os.path.join(INT3, "data", "INT-S3"))
        # far_side writes its figure next to the table; the figure belongs in plots/
        worst = os.path.join(INT3, "data", "INT-S3_worst_case.png")
        if os.path.exists(worst):
            shutil.move(worst, os.path.join(INT3, "plots", "INT-S3_worst_case.png"))

    summary = {
        "events": s["events"], "seed": s["seed"], "chem_source": s["chem_source"],
        "C3_max_mmol": round(s["total_mmol_max"], 3),
        "C3_over_ceiling": s["over_50"],
        "S6_within_300s": f"{s['within_300']}/{s['events']}",
        "S6_pct": round(s["pct_within_300"], 2),
        "S6_mean_s": round(s["rec_mean"], 1), "S6_max_s": round(s["rec_max"], 1),
        "report_basis_mean_s": round(s["stop_mean"], 1),
        "report_basis_p95_s": round(s["stop_p95"], 1),
        "report_basis_max_s": round(s["stop_max"], 1),
        "INT_S2_in_band": f"{s['in_band']}/{s['events']}",
        "INT_S3_no_excursion": f"{f['no_excursion']}/{f['n']}",
        "INT_S3_pct": round(f["pct_no_excursion"], 2),
        "INT_S3_worst_peak_ph": f["worst_peak_ph"],
        "INT_S3_worst_event": f["worst_event"],
        "escalations": s["escalations"],
        "imr_mean_s": round(i["mean"], 1), "imr_ucl_s": round(i["ucl"], 1),
        "imr_lcl_s": round(i["lcl"], 1),
        "imr_out_of_control": i["n_out_of_control"],
        "reagent_overhead_pct": round(h["overhead_pct"], 3),
    }
    out = os.path.join(C3, "data", "batch_summary_all_numbers.json")
    for d in FOLDERS:
        with open(os.path.join(d, "data", "batch_summary_all_numbers.json"), "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)

    print("\n" + "=" * 72)
    print("NUMBERS FOR THE TEST SHEETS")
    print("=" * 72)
    for k, v in summary.items():
        print(f"  {k:26s} {v}")
    print(f"\nwrote {out}")
    if s["chem_source"] != "ASPEN":
        print("\n!! chemistry is PLACEHOLDER. Re-run this after CHE delivers")
        print("   sim/aspen_tables/, and re-print any sheet that quotes a number.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
