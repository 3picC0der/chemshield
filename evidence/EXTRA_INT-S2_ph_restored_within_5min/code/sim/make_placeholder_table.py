"""Write stand-in pH tables in the exact Aspen export format.

These are NOT Aspen output. Two tables, same grid, same temperatures:

1. placeholder_nahco3_ph_table.csv - THE TANK LIQUID, loaded by sim.chemistry.
   5.000 L distilled water + 0.420 g NaHCO3 (5.0 mmol, 1 mmol/L), closed carbonate
   system (no CO2 exchange with air), pKa1 6.35, pKa2 10.33:

       [H+] + [Na+] + b = [OH-] + [HCO3-] + 2[CO3--]      [H+][OH-] = Kw(T)

   with [Na+] = C_T = 1 mmol/L from the NaHCO3 and b = net excess strong BASE (mol/L).
   Excess 0 is the liquid as prepared, pH about 8.30, not 7.

2. _placeholder_pure_water_ph_table.csv - the earlier pure-water table, from the charge
   balance of the Second Report Installment, Section 1.3 (eq. 1.1-1.3):

       [H+] - [OH-] = n / V        and       [H+][OH-] = Kw(T)

   Its name starts with "_", so sim.chemistry does not load it. The known-answer tests
   load it on purpose to check the lookup against pure-water hand calculations.

Same temperatures and the same grid points; the NaHCO3 table adds 0.05 mmol steps from
2 to 8 mmol on each side (see grid()). Both are written in the team's base-positive convention (excess_mmol = -n, in mmol) so
that swapping in the real Aspen CSVs changes nothing but the numbers.

Run:  python -m sim.make_placeholder_table
"""
from __future__ import annotations
import os

import numpy as np
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_DIR = os.path.join(HERE, "aspen_tables")
OUT = os.path.join(TABLE_DIR, "placeholder_nahco3_ph_table.csv")
OUT_PURE_WATER = os.path.join(TABLE_DIR, "_placeholder_pure_water_ph_table.csv")
BASIS_L = 5.0
TEMPS = (20.0, 25.0, 30.0, 35.0)

NAHCO3_G = 0.420                   # g in 5.000 L
NAHCO3_G_PER_MOL = 84.007
C_T = NAHCO3_G / NAHCO3_G_PER_MOL / BASIS_L     # mol/L, 1.0 mmol/L
PKA1, PKA2 = 6.35, 10.33           # carbonic acid, held at the 25 C values at every T
NAHCO3_FINE_TO = 8.0               # mmol, 0.05 mmol steps across both equivalence points


def kw(temp_c: float) -> float:
    """pKw(T), quadratic through 0, 25 and 50 C (14.94, 14.00, 13.26)."""
    return 10.0 ** -(14.94 - 0.0416 * temp_c + 0.00016 * temp_c * temp_c)


def ph_of_excess(excess_mmol: float, temp_c: float) -> float:
    """Pure water. Charge balance solved for [H+]. excess_mmol is base-positive, basis 5.000 L."""
    k = kw(temp_c)
    c = -(excess_mmol / 1000.0) / BASIS_L          # net excess strong ACID, mol/L
    if c > 0:
        h = 0.5 * (c + np.sqrt(c * c + 4.0 * k))
    else:
        h = k / (0.5 * (-c + np.sqrt(c * c + 4.0 * k)))
    return float(-np.log10(h))


def ph_of_excess_nahco3(excess_mmol: float, temp_c: float) -> float:
    """1 mmol/L NaHCO3, closed system. excess_mmol is base-positive, basis 5.000 L."""
    k, k1, k2 = kw(temp_c), 10.0 ** -PKA1, 10.0 ** -PKA2
    b = (excess_mmol / 1000.0) / BASIS_L           # net excess strong BASE, mol/L

    def charge(ph: float) -> float:                # falls as pH rises, one root
        h = 10.0 ** -ph
        carb = C_T * (k1 * h + 2.0 * k1 * k2) / (h * h + k1 * h + k1 * k2)
        return h + C_T + b - k / h - carb

    return float(brentq(charge, -2.0, 16.0, xtol=1e-12))


def grid(fine_to: float = 2.0) -> np.ndarray:
    """Point spacing from the Simulation and Dataset Guide, Part 1 A3, mirrored.

    fine_to is where the 0.05 mmol steps end. The Guide's 2 mmol suits pure water. The
    NaHCO3 liquid bends sharply at its equivalence points (-5 and +5 mmol), where 1 mmol
    steps put the lookup up to 0.47 pH off (0.07 at pH 6.0); 0.05 mmol steps out to
    8 mmol bring that under 0.005 pH everywhere."""
    pos = np.concatenate([
        np.arange(0.0, 0.2, 0.002),
        np.arange(0.2, fine_to, 0.05),
        np.arange(fine_to, 60.0 + 1e-9, 1.0),
    ])
    pos = np.unique(np.round(pos, 6))
    return np.unique(np.concatenate([-pos[::-1], pos]))


def _write(path: str, fn, case_acid: str, case_base: str, pts: np.ndarray) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("case,temp_c,excess_mmol,ph\n")
        for t in TEMPS:
            for e in pts:
                case = case_acid if e < 0 else case_base    # mirrors T1/T2
                fh.write(f"{case},{t:.1f},{e:.6f},{fn(e, t):.6f}\n")
    print(f"wrote {path}")
    print(f"  {len(pts)} points x {len(TEMPS)} temperatures = {len(pts) * len(TEMPS)} rows")


def main() -> str:
    os.makedirs(TABLE_DIR, exist_ok=True)
    _write(OUT, ph_of_excess_nahco3, "PLACEHOLDER-NaHCO3-acid", "PLACEHOLDER-NaHCO3-base",
           grid(fine_to=NAHCO3_FINE_TO))
    print(f"  tank liquid: {BASIS_L:.3f} L water + {NAHCO3_G:.3f} g NaHCO3 "
          f"({C_T * 1000:.2f} mmol/L), closed carbonate, pKa {PKA1} / {PKA2}")
    _write(OUT_PURE_WATER, ph_of_excess, "P1", "P2", grid())
    print("  pure water, for the known-answer tests only (not loaded: name starts with _)")
    print("  NOTE: placeholders, not Aspen. Replace with the CHE tables before quoting "
          "any number as chemistry-validated.")
    return OUT


if __name__ == "__main__":
    main()
