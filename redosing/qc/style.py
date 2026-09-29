"""Shared plot style for the ISE evidence figures.

Matches the figures already accepted in the Second Report Installment (Figure 7), so the
PPR slides, the test-sheet evidence and the report all look like one set.
Sizes are chosen for a booth screen and an A4 print, not for a notebook.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

plt.rcParams.update({"font.family": "DejaVu Sans"})

ISE = "#1B7F4B"     # ISE green, the series colour
CMP = "#8A9099"     # grey, comparison / secondary series
INK = "#111318"     # text
MUT = "#4A5160"     # muted text
AMB = "#B7791F"     # amber, a requirement limit
RED = "#B22222"     # a violated limit or an out-of-control point
GRID = "#D8DDE3"
TITLE = "#17365D"

DPI = 300


def clean(ax) -> None:
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#B9C0C8")
    ax.tick_params(labelsize=11, colors=INK, length=2.5, width=.7)
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, lw=.7)


def title(fig, text: str, sub: str | None = None) -> None:
    fig.text(.5, .958, text, ha="center", fontsize=16, weight="bold", color=TITLE)
    if sub:
        fig.text(.5, .900, sub, ha="center", fontsize=11.5, color=MUT)


def provenance(fig, chem_source: str, extra: str = "") -> None:
    """Every evidence figure states where its chemistry came from."""
    tag = ("chemistry: Aspen tables" if chem_source == "ASPEN"
           else "chemistry: PLACEHOLDER (report charge balance, not Aspen)")
    fig.text(.995, .008, " · ".join(x for x in (tag, extra) if x),
             ha="right", fontsize=9, color=RED if chem_source != "ASPEN" else MUT)


def save(fig, path: str) -> str:
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    print(f"wrote {path}")
    return path
