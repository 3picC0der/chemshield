"""One command: run the batch and produce every ISE and integrated evidence file.

    python -m redosing.run_all                    # 600 events, seed 261
    python -m redosing.run_all --events 100       # quick pass while developing

Writes into evidence/ISE/... and evidence/INT/..., exactly the file names the test
sheets ask for, and prints the numbers to copy onto the sheets.
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

TARGETS = [("ISE", "ISE-AT-01"), ("ISE", "ISE-AT-02"),
           ("INT", "INT-AT-02"), ("INT", "INT-AT-03")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.run_all")
    ap.add_argument("--events", type=int, default=600)
    ap.add_argument("--seed", type=int, default=261)
    a = ap.parse_args(argv)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from sim import batch as B
        from redosing.qc import far_side, histogram, imr, traces

        for dept, tid in TARGETS:
            os.makedirs(os.path.join(EV, dept, tid), exist_ok=True)

        first = os.path.join(EV, "ISE", "ISE-AT-01", "ISE-AT-01_batch.csv")
        s = B.run(events=a.events, seed=a.seed, out=first)

        # the sheets all say "use the same 600-event batch"; give each folder its own copy
        # so a grader opening one folder has everything that sheet refers to
        src_t = os.path.splitext(first)[0] + "_traces.csv"
        for dept, tid in TARGETS[1:]:
            d = os.path.join(EV, dept, tid)
            shutil.copy(first, os.path.join(d, f"{tid}_batch.csv"))
            shutil.copy(src_t, os.path.join(d, f"{tid}_batch_traces.csv"))

        p = lambda dept, tid, name: os.path.join(EV, dept, tid, name)  # noqa: E731
        h = histogram.run(p("ISE", "ISE-AT-01", "ISE-AT-01_batch.csv"),
                          p("ISE", "ISE-AT-01", "ISE-AT-01_histogram.png"))
        i = imr.run(p("ISE", "ISE-AT-02", "ISE-AT-02_batch.csv"),
                    p("ISE", "ISE-AT-02", "ISE-AT-02_imr.png"))
        t = traces.run(p("INT", "INT-AT-02", "INT-AT-02_batch.csv"),
                       p("INT", "INT-AT-02", "INT-AT-02_traces.png"))
        f = far_side.run(p("INT", "INT-AT-03", "INT-AT-03_batch.csv"),
                         p("INT", "INT-AT-03", "INT-AT-03"))

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
    out = os.path.join(EV, "ISE", "ISE_evidence_summary.json")
    with open(out, "w", encoding="utf-8") as fh:
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
