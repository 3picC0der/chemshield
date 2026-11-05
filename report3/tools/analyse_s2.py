"""S2 pump calibration from the weighings (Final Prototype rig, 5 Nov 2026).

Input CSV, one row per weighing:
    pump,channel,phase,commanded_ml,steps_per_ml_used,grams
phase "cal" rows were dosed with the old constant and set the new one; phase "check" rows
were dosed after the new constant was stored, so they are the real test of it.

    python analyse_s2.py s2_weighings.csv --density 0.9973 --out s2_results.csv

Delivered mL = grams / density. Full steps per mL = commanded full steps / delivered mL,
through the origin. Errors are (delivered - commanded) / commanded.
"""
from __future__ import annotations

import argparse
import csv
import sys


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("weighings")
    ap.add_argument("--density", type=float, required=True, help="g/mL of the water at room temperature")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    with open(a.weighings, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    print(f"density {a.density} g/mL")
    print("pump channel      phase  commanded  delivered mL  error %  fit full steps/mL")
    for pump in sorted({r["pump"] for r in rows}, key=int):
        group = [r for r in rows if r["pump"] == pump]
        cal = [r for r in group if r["phase"] == "cal"]
        steps = [float(r["commanded_ml"]) * float(r["steps_per_ml_used"]) for r in cal]
        ml = [float(r["grams"]) / a.density for r in cal]
        spm = sum(s * s for s in steps) / sum(s * m for s, m in zip(steps, ml)) if cal else float("nan")
        for r in group:
            delivered = float(r["grams"]) / a.density
            commanded = float(r["commanded_ml"])
            err = 100.0 * (delivered - commanded) / commanded
            print(f"{pump:>4} {r['channel']:<12} {r['phase']:<6} {commanded:>9.2f} {delivered:>13.3f} "
                  f"{err:>8.2f} {spm:>18.2f}")
            out.append({**r, "density_g_per_ml": a.density, "delivered_ml": round(delivered, 3),
                        "error_pct": round(err, 2), "fit_full_steps_per_ml": round(spm, 2)})
    checks = [r for r in out if r["phase"] == "check"]
    if checks:
        worst = max(checks, key=lambda r: abs(r["error_pct"]))
        top = max(checks, key=lambda r: r["delivered_ml"])
        print(f"after calibration: max |error| {abs(worst['error_pct']):.2f} % (pump {worst['pump']}), "
              f"max delivered {top['delivered_ml']:.3f} mL (pump {top['pump']})")
        over = [r for r in checks if float(r["commanded_ml"]) == 20.0 and r["delivered_ml"] > 20.0]
        print("20 mL cap: " + (f"{len(over)} delivery over 20.00 mL, lower the cap to 19.5 mL" if over
                               else "no check delivery over 20.00 mL"))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
