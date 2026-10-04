"""Reagent-per-event histogram with the 50 mmol line (test sheet ISE-AT-01, evidence).

    python -m redosing.qc.histogram ISE-AT-01_batch.csv --out ISE-AT-01_histogram.png
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .common import chem_source, fnum, load_batch
from .style import AMB, CMP, INK, ISE, MUT, RED, clean, provenance, save, title, plt

R_MAX = 50.0


def run(batch: str, out: str = "ISE-AT-01_histogram.png") -> dict:
    rows = load_batch(batch)
    x = np.array(fnum(rows, "total_mmol"), float)
    theo = np.array(fnum(rows, "upset_mmol"), float)
    src = chem_source(rows)
    over = int((x > R_MAX + 1e-9).sum())

    fig = plt.figure(figsize=(10.6, 5.6))
    ax = fig.add_axes([.085, .145, .885, .68]); clean(ax)
    title(fig, "Corrective reagent per recovery event",
          f"{len(x)} events · C3 ceiling {R_MAX:.0f} mmol · "
          f"largest {x.max():.2f} mmol · over the ceiling: {over}")

    hi = max(R_MAX * 1.04, x.max() * 1.06)
    ax.hist(x, bins=np.linspace(0, hi, 46), color=ISE, alpha=.85, zorder=3,
            label="reagent used")
    ax.axvline(R_MAX, color=AMB, lw=2.0, zorder=4)
    ax.text(R_MAX - hi * .012, ax.get_ylim()[1] * .96, f"C3 ceiling {R_MAX:.0f} mmol  ",
            fontsize=12.5, color=AMB, weight="bold", va="top", ha="right")
    ax.axvline(x.max(), color=RED, lw=1.2, ls="--", zorder=4)
    ax.text(x.max(), ax.get_ylim()[1] * .70, f"  largest\n  {x.max():.2f} mmol",
            fontsize=11, color=RED, va="top")
    ax.axvline(float(x.mean()), color=MUT, lw=1.0, ls=":", zorder=4)
    ax.text(float(x.mean()), ax.get_ylim()[1] * .40, f"  mean\n  {x.mean():.2f}",
            fontsize=11, color=MUT, va="top")
    ax.set_xlabel("corrective reagent used in the event (mmol)", fontsize=12.5, color=INK)
    ax.set_ylabel("events", fontsize=12.5, color=INK)
    ax.set_xlim(0, hi)
    ax.legend(fontsize=11.5, frameon=False, loc="upper left")
    provenance(fig, src, f"stoichiometric demand mean {theo.mean():.2f} mmol")
    save(fig, out)

    s = dict(n=len(x), max=float(x.max()), mean=float(x.mean()), min=float(x.min()),
             over_ceiling=over, theo_mean=float(theo.mean()),
             overhead_pct=100.0 * float((x - theo).mean() / theo.mean()),
             chem_source=src, png=out)
    print(f"\nreagent per event, {s['n']} events")
    print(f"  max {s['max']:.3f} mmol   mean {s['mean']:.3f}   min {s['min']:.3f}")
    print(f"  over the {R_MAX:.0f} mmol ceiling: {over}")
    print(f"  stoichiometric demand mean {s['theo_mean']:.3f} mmol "
          f"-> overhead {s['overhead_pct']:+.2f}%")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.qc.histogram")
    ap.add_argument("batch")
    ap.add_argument("--out", default="ISE-AT-01_histogram.png")
    a = ap.parse_args(argv)
    run(a.batch, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
