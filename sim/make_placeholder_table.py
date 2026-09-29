"""Write a stand-in pH table in the exact Aspen export format.

This is NOT Aspen output. It is generated from the charge-balance equations of the
Second Report Installment, Section 1.3 (eq. 1.1-1.3):

    [H+] - [OH-] = n / V        and       [H+][OH-] = Kw(T)

with n = net excess strong ACID. The table is written in the team's base-positive
convention (excess_mmol = -n, in mmol) so that swapping in the real Aspen CSVs
changes nothing but the numbers.

Run:  python -m sim.make_placeholder_table
"""
from __future__ import annotations
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "aspen_tables", "placeholder_ph_table.csv")
BASIS_L = 5.0
TEMPS = (20.0, 25.0, 30.0, 35.0)


def kw(temp_c: float) -> float:
    """pKw(T), quadratic through 0, 25 and 50 C (14.94, 14.00, 13.26)."""
    return 10.0 ** -(14.94 - 0.0416 * temp_c + 0.00016 * temp_c * temp_c)


def ph_of_excess(excess_mmol: float, temp_c: float) -> float:
    """Charge balance solved for [H+]. excess_mmol is base-positive, basis 5.000 L."""
    k = kw(temp_c)
    c = -(excess_mmol / 1000.0) / BASIS_L          # net excess strong ACID, mol/L
    if c > 0:
        h = 0.5 * (c + np.sqrt(c * c + 4.0 * k))
    else:
        h = k / (0.5 * (-c + np.sqrt(c * c + 4.0 * k)))
    return float(-np.log10(h))


def grid() -> np.ndarray:
    """Point spacing from the Simulation and Dataset Guide, Part 1 A3, mirrored."""
    pos = np.concatenate([
        np.arange(0.0, 0.2, 0.002),
        np.arange(0.2, 2.0, 0.05),
        np.arange(2.0, 60.0 + 1e-9, 1.0),
    ])
    pos = np.unique(np.round(pos, 6))
    return np.unique(np.concatenate([-pos[::-1], pos]))


def main() -> str:
    pts = grid()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("case,temp_c,excess_mmol,ph\n")
        for t in TEMPS:
            for e in pts:
                case = "P1" if e < 0 else "P2"          # P = placeholder, mirrors T1/T2
                fh.write(f"{case},{t:.1f},{e:.6f},{ph_of_excess(e, t):.6f}\n")
    print(f"wrote {OUT}")
    print(f"  {len(pts)} points x {len(TEMPS)} temperatures = {len(pts) * len(TEMPS)} rows")
    print(f"  excess_mmol {pts[0]:+.3f} .. {pts[-1]:+.3f} mmol on a {BASIS_L:.3f} L basis")
    print("  NOTE: placeholder, not Aspen. Replace with the CHE tables before quoting "
          "any number as chemistry-validated.")
    return OUT


if __name__ == "__main__":
    main()
