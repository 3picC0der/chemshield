"""The hidden TRUE tank chemistry, used only to label the dataset.

The Pi never sees this. It predicts pH from the pH table in sim/aspen_tables/ (the same
table the planner uses). The label, on the other hand, comes from this model of what
really happens in the tank, including the baking-soda buffer and its uncertainty.

Liquid: 5.000 L of distilled water plus 0.420 g of NaHCO3 (5.0 mmol, 1.0 mmol/L), the
tank liquid chosen in the kickoff thread. Carbonate chemistry, closed system (no CO2
exchange with the air), 25 C constants:

    charge balance  [H+] + B = [OH-] + CT*(a1 + 2*a2)
    B  = net strong base (Na+ minus Cl-), mol/L
    CT = total dissolved carbonate, mol/L
    a1, a2 = fractions of CT present as HCO3- and CO3--

Sign convention follows I2 and the Aspen tables: net_base_mmol > 0 is extra base,
< 0 is extra acid.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

K1 = 10.0 ** -6.35    # H2CO3* <-> HCO3-
K2 = 10.0 ** -10.33   # HCO3- <-> CO3--
NAHCO3_G_PER_MOL = 84.007


def kw(temp_c: float = 25.0) -> float:
    """Same pKw(T) as sim/chemistry.py, so the two agree on pure water."""
    return 10.0 ** -(14.94 - 0.0416 * temp_c + 0.00016 * temp_c * temp_c)


@dataclass(frozen=True)
class Liquid:
    """What is in the tank before any acid or base is added (per litre, at v0_L)."""
    name: str
    ct_mM: float     # total carbonate, mmol/L
    alk_mM: float    # strong-base equivalent (the Na+ from NaHCO3), mmol/L
    v0_L: float = 5.0

    def scaled(self, factor: float) -> "Liquid":
        """Same liquid with factor x the baking soda (weighing / dissolving error)."""
        return Liquid(self.name, self.ct_mM * factor, self.alk_mM * factor, self.v0_L)


PURE_WATER = Liquid("pure_water", 0.0, 0.0)
BICARB_1MM = Liquid("bicarb_1mM", 1.0, 1.0)      # 0.420 g NaHCO3 in 5.000 L
LIQUIDS = {PURE_WATER.name: PURE_WATER, BICARB_1MM.name: BICARB_1MM}


def true_ph(net_base_mmol: float, volume_L: float, liquid: Liquid, temp_c: float = 25.0) -> float:
    """pH of the well-mixed tank after net_base_mmol of strong base (negative = acid)."""
    k_w = kw(temp_c)
    b = (liquid.alk_mM * liquid.v0_L + float(net_base_mmol)) * 1e-3 / float(volume_L)
    ct = liquid.ct_mM * liquid.v0_L * 1e-3 / float(volume_L)
    if ct <= 0.0:
        # pure water: [H+] - [OH-] = -b, solved in the numerically stable form
        c = -b
        root = math.sqrt(c * c + 4.0 * k_w)
        h = 0.5 * (c + root) if c >= 0.0 else k_w / (0.5 * (-c + root))
        return -math.log10(h)

    def f(ph: float) -> float:
        h = 10.0 ** -ph
        d = h * h + K1 * h + K1 * K2
        return h + b - k_w / h - ct * (K1 * h + 2.0 * K1 * K2) / d

    return brentq(f, -1.0, 15.0, xtol=1e-10)


def net_base_for_ph(target_ph: float, volume_L: float, liquid: Liquid, temp_c: float = 25.0) -> float:
    """Inverse of true_ph: how much net base (mmol) gives this pH."""
    return brentq(lambda nb: true_ph(nb, volume_L, liquid, temp_c) - target_ph, -300.0, 300.0,
                  xtol=1e-9)


def write_table(liquid: Liquid, path: str, temp_c: float = 25.0, case: str = "M") -> int:
    """Write a titration table for this liquid in the sim/aspen_tables CSV format.

    Only a stand-in for testing before CHE's Aspen table exists. Name the file with
    'placeholder' in it so sim.chemistry labels every result PLACEHOLDER.
    """
    grid = np.unique(np.round(np.concatenate([
        np.arange(-60.0, -10.0, 0.5),
        np.arange(-10.0, 10.0, 0.01),
        np.arange(10.0, 60.0 + 1e-9, 0.5),
    ]), 6))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("case,temp_c,excess_mmol,ph\n")
        for x in grid:
            fh.write(f"{case},{temp_c:.1f},{x:.6f},{true_ph(x, liquid.v0_L, liquid, temp_c):.6f}\n")
    return len(grid)


if __name__ == "__main__":
    for liq in (PURE_WATER, BICARB_1MM):
        print(f"{liq.name}: start pH {true_ph(0.0, 5.0, liq):.2f}")
        for x in (-10.0, -3.5, -1.0, 1.0):
            print(f"   {x:+6.1f} mmol -> pH {true_ph(x, 5.0, liq):.2f}")
