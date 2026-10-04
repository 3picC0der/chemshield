"""C1: weight percent of every solution the system can dose, from its molarity.

    python evidence/01_C1_approved_dilute_reagents/code/wt_percent.py

    wt% = molarity (mol/L) x molar mass (g/mol) / (10 x density (g/mL))

A litre of solution weighs density x 1000 g and holds molarity x molar mass grams of solute,
so wt% = 100 x (M x MM) / (1000 x density) = M x MM / (10 x density).
Densities are textbook values for the dilute solutions (rounded); the result only has to be
below 5, and the strongest solution is 1.96 wt%, so the rounding does not matter.

Writes ../data/wt_percent_calculation.csv and ../plots/C1_wt_percent_vs_limit.png.
"""
from __future__ import annotations

import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
LIMIT_WT = 5.0

# name, role, molarity (mol/L), molar mass (g/mol), density (g/mL)
SOLUTIONS = [
    ("HCl 0.5 M (ACID_BULK)", "acid, bulk bottle of the system", 0.5, 36.46, 1.007),
    ("HCl 0.05 M", "acid used by hand in the tests (the lab bottle)", 0.05, 36.46, 1.000),
    ("HCl 0.005 M (ACID_FINE)", "acid, fine bottle of the system", 0.005, 36.46, 1.000),
    ("NaOH 0.5 M (BASE_BULK)", "base, bulk bottle", 0.5, 40.00, 1.019),
    ("NaOH 0.005 M (BASE_FINE)", "base, fine bottle", 0.005, 40.00, 1.000),
]
# Tank liquid: 0.420 g NaHCO3 in 5.000 L of distilled water (5.000 kg), not a dosed reagent.
TANK_WT = 100 * 0.420 / (5000.0 + 0.420)


def main() -> None:
    rows = []
    for name, role, molarity, mm, rho in SOLUTIONS:
        wt = molarity * mm / (10 * rho)
        rows.append({"solution": name, "role": role, "molarity_mol_per_L": molarity, "molar_mass_g_per_mol": mm,
                     "density_g_per_mL": rho, "wt_percent": round(wt, 4), "limit_wt_percent": LIMIT_WT,
                     "within_limit": wt <= LIMIT_WT})
    rows.append({"solution": "tank liquid: 0.420 g NaHCO3 in 5 L distilled water", "role": "the water being protected",
                 "molarity_mol_per_L": 0.001, "molar_mass_g_per_mol": 84.01, "density_g_per_mL": 1.000,
                 "wt_percent": round(TANK_WT, 4), "limit_wt_percent": LIMIT_WT, "within_limit": TANK_WT <= LIMIT_WT})
    data_dir = os.path.join(HERE, "..", "data")
    plot_dir = os.path.join(HERE, "..", "plots")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(plot_dir, exist_ok=True)
    with open(os.path.join(data_dir, "wt_percent_calculation.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    fig, ax = plt.subplots(figsize=(9, 4.2), dpi=150)
    names = [r["solution"].split(" (")[0] if "tank" not in r["solution"] else "tank liquid (NaHCO3)" for r in rows]
    vals = [r["wt_percent"] for r in rows]
    bars = ax.barh(names[::-1], vals[::-1], color="#2f7d5b")
    ax.axvline(LIMIT_WT, color="#b02a2a", lw=2)
    ax.text(LIMIT_WT - 0.08, len(rows) - 0.55, "C1 limit 5 wt%", color="#b02a2a", ha="right", va="center", fontsize=10)
    for bar, v in zip(bars, vals[::-1]):
        ax.text(v + 0.06, bar.get_y() + bar.get_height() / 2, f"{v:.3g} wt%", va="center", fontsize=9)
    ax.set_xlim(0, 5.6)
    ax.set_xlabel("concentration (weight percent), calculated from molarity")
    ax.set_title("C1: every solution the system can dose is well under 5 wt%")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(plot_dir, "C1_wt_percent_vs_limit.png"))
    top = max(rows[:-1], key=lambda r: r["wt_percent"])
    print(f"strongest dosed solution: {top['solution']} = {top['wt_percent']} wt% (limit {LIMIT_WT})")


if __name__ == "__main__":
    main()
