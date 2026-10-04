"""I-MR control chart of recovery time (test sheet ISE-AT-02, step 5).

    python -m redosing.qc.imr ISE-AT-02_batch.csv --out ISE-AT-02_imr.png

An I-MR (individuals and moving-range) chart asks whether the recovery process is
*stable*, which is a different question from whether it meets S6. A point outside the
control limits means something changed; a point above 300 s means the requirement was
missed. Both lines are drawn, and they are not the same line.

Constants are the standard ones for a moving range of 2 (Montgomery, Table VI):
    d2 = 1.128, D4 = 3.267, D3 = 0.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .common import chem_source, fnum, load_batch
from .style import AMB, CMP, GRID, INK, ISE, MUT, RED, clean, provenance, save, title, plt

D2, D4, D3 = 1.128, 3.267, 0.0
T_SPEC = 300.0


def limits(x: np.ndarray) -> dict:
    mr = np.abs(np.diff(x))
    mrbar = float(mr.mean())
    xbar = float(x.mean())
    sigma = mrbar / D2
    return dict(xbar=xbar, mrbar=mrbar, sigma=sigma,
                ucl=xbar + 3 * sigma, lcl=xbar - 3 * sigma,
                mr_ucl=D4 * mrbar, mr_lcl=D3 * mrbar, mr=mr)


def western_electric(x: np.ndarray, L: dict) -> dict[str, list[int]]:
    """Rules 1-4. Returns 1-based event indices per rule."""
    s, xb = L["sigma"], L["xbar"]
    out: dict[str, list[int]] = {}
    out["1: beyond 3 sigma"] = [i + 1 for i, v in enumerate(x) if abs(v - xb) > 3 * s]
    r2 = []
    for i in range(len(x) - 2):
        w = x[i:i + 3]
        for sign in (+1, -1):
            if sum(sign * (v - xb) > 2 * s for v in w) >= 2:
                r2.append(i + 3)
                break
    out["2: 2 of 3 beyond 2 sigma"] = sorted(set(r2))
    r3 = []
    for i in range(len(x) - 4):
        w = x[i:i + 5]
        for sign in (+1, -1):
            if sum(sign * (v - xb) > s for v in w) >= 4:
                r3.append(i + 5)
                break
    out["3: 4 of 5 beyond 1 sigma"] = sorted(set(r3))
    r4 = []
    for i in range(len(x) - 7):
        w = x[i:i + 8]
        if all(v > xb for v in w) or all(v < xb for v in w):
            r4.append(i + 8)
    out["4: 8 in a row on one side"] = sorted(set(r4))
    return out


def run(batch: str, out: str, column: str = "recovery_time_s") -> dict:
    rows = load_batch(batch)
    x = np.array(fnum(rows, column), float)
    if len(x) < 25:
        print(f"warning: only {len(x)} points; Phase I normally uses 20-25 at minimum")
    L = limits(x)
    rules = western_electric(x, L)
    ooc = sorted({i for v in rules.values() for i in v})
    src = chem_source(rows)

    fig = plt.figure(figsize=(11.2, 6.4))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.35, 1], left=.075, right=.865,
                          top=.845, bottom=.105, hspace=.32)
    title(fig, "Recovery time control chart (I-MR)",
          f"{len(x)} recovery events, seed {rows[0].get('seed', '?')} · "
          f"S6 requires 95% within {T_SPEC:.0f} s")

    k = np.arange(1, len(x) + 1)

    ax = fig.add_subplot(gs[0]); clean(ax)
    ax.axhspan(L["lcl"], L["ucl"], color=ISE, alpha=.055, zorder=0)
    ax.plot(k, x, color=ISE, lw=.9, marker="o", ms=2.3, zorder=3, label="recovery time")
    for y, lab, col, ls in ((L["ucl"], f"UCL {L['ucl']:.0f} s", CMP, "--"),
                            (L["xbar"], f"mean {L['xbar']:.0f} s", MUT, "-"),
                            (L["lcl"], f"LCL {L['lcl']:.0f} s", CMP, "--")):
        ax.axhline(y, color=col, lw=.9, ls=ls, zorder=2)
        ax.text(len(x) * 1.015, y, lab, fontsize=11, color=col, va="center")
    ax.axhline(T_SPEC, color=AMB, lw=1.4, zorder=2)
    ax.text(len(x) * 1.015, T_SPEC, f"S6 limit\n{T_SPEC:.0f} s", fontsize=11.5,
            color=AMB, va="center", weight="bold")
    if ooc:
        ax.scatter([i for i in ooc], [x[i - 1] for i in ooc], s=26, color=RED,
                   zorder=4, label="out of control")
    over = [i for i in k if x[i - 1] > T_SPEC]
    if over:
        ax.scatter(over, [x[i - 1] for i in over], s=26, facecolors="none",
                   edgecolors=AMB, lw=1.2, zorder=5, label=f"over {T_SPEC:.0f} s")
    ax.set_ylabel("recovery time (s)", fontsize=12.5, color=INK)
    ax.set_xlim(0, len(x) * 1.012)
    ax.legend(fontsize=11, frameon=False, loc="upper left", ncol=3)

    ax2 = fig.add_subplot(gs[1]); clean(ax2)
    ax2.plot(k[1:], L["mr"], color=CMP, lw=.9, marker="o", ms=2.1, zorder=3)
    for y, lab in ((L["mr_ucl"], f"UCL {L['mr_ucl']:.0f} s"),
                   (L["mrbar"], f"MR {L['mrbar']:.0f} s")):
        ax2.axhline(y, color=MUT, lw=.9, ls="--", zorder=2)
        ax2.text(len(x) * 1.015, y, lab, fontsize=11, color=MUT, va="center")
    mr_ooc = [i + 2 for i, v in enumerate(L["mr"]) if v > L["mr_ucl"]]
    if mr_ooc:
        ax2.scatter(mr_ooc, [L["mr"][i - 2] for i in mr_ooc], s=26, color=RED, zorder=4)
    ax2.set_ylabel("moving range (s)", fontsize=12.5, color=INK)
    ax2.set_xlabel("recovery event, in order", fontsize=12.5, color=INK)
    ax2.set_xlim(0, len(x) * 1.012)

    provenance(fig, src, f"{column}")
    save(fig, out)

    s = dict(n=len(x), mean=L["xbar"], sigma=L["sigma"], ucl=L["ucl"], lcl=L["lcl"],
             mrbar=L["mrbar"], mr_ucl=L["mr_ucl"],
             out_of_control=ooc, n_out_of_control=len(ooc),
             mr_out_of_control=mr_ooc, over_spec=over, n_over_spec=len(over),
             within_spec=int((x <= T_SPEC).sum()),
             pct_within=100.0 * float((x <= T_SPEC).mean()),
             max=float(x.max()), min=float(x.min()), chem_source=src, rules=rules)
    print(f"\nI-MR chart, {s['n']} events   mean {s['mean']:.1f} s   sigma {s['sigma']:.1f} s")
    print(f"  control limits : LCL {s['lcl']:.1f}  UCL {s['ucl']:.1f} s")
    print(f"  MR chart       : MRbar {s['mrbar']:.1f}  UCL {s['mr_ucl']:.1f} s")
    print(f"  out of control : {s['n_out_of_control']} individuals, "
          f"{len(mr_ooc)} moving ranges")
    for rule, idx in rules.items():
        if idx:
            show = ", ".join(str(i) for i in idx[:12]) + (" ..." if len(idx) > 12 else "")
            print(f"    rule {rule}: {len(idx)} point(s) -> {show}")
    print(f"  S6             : {s['within_spec']}/{s['n']} = {s['pct_within']:.1f}% "
          f"within {T_SPEC:.0f} s   (max {s['max']:.1f} s)")
    if s["n_over_spec"]:
        print(f"  over the S6 limit: events {s['over_spec']}")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.qc.imr")
    ap.add_argument("batch")
    ap.add_argument("--out", default="ISE-AT-02_imr.png")
    ap.add_argument("--column", default="recovery_time_s")
    a = ap.parse_args(argv)
    run(a.batch, a.out, a.column)
    return 0


if __name__ == "__main__":
    sys.exit(main())
