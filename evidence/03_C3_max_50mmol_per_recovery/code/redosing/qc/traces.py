"""All recovery pH traces on one chart (test sheet INT-AT-02, step 6).

    python -m redosing.qc.traces INT-AT-02_batch.csv --out INT-AT-02_traces.png

Draws every event's pH against time with the 6.0 / 8.5 band and the 300 s line, so a
grader can see at a glance that every trace is inside the band before the line.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np

from .common import chem_source, load_batch, load_traces
from .style import AMB, CMP, INK, ISE, MUT, RED, clean, provenance, save, title, plt

BAND_LO, BAND_HI = 6.0, 8.5
T_SPEC = 300.0


def run(batch: str, out: str = "INT-AT-02_traces.png") -> dict:
    rows = load_batch(batch)
    traces = load_traces(batch)
    src = chem_source(rows)
    by_id = {int(r["event_id"]): r for r in rows}

    fig = plt.figure(figsize=(11.2, 6.0))
    ax = fig.add_axes([.08, .125, .89, .70]); clean(ax)

    late, out_of_band = [], []
    tmax = 0.0
    for eid, pts in sorted(traces.items()):
        t = np.array([p[0] for p in pts]); ph = np.array([p[1] for p in pts])
        tmax = max(tmax, float(t.max()))
        r = by_id[eid]
        slow = (r["recovery_time_s"] == "") or (float(r["recovery_time_s"]) > T_SPEC)
        if slow:
            late.append(eid)
        if not int(r["in_band"]):
            out_of_band.append(eid)
        ax.plot(t, ph, color=(RED if slow else ISE), lw=.55,
                alpha=(.9 if slow else .13), zorder=(4 if slow else 2))

    ax.axhspan(BAND_LO, BAND_HI, color=ISE, alpha=.10, zorder=0)
    ax.axhline(BAND_LO, color=ISE, lw=1.1, zorder=3)
    ax.axhline(BAND_HI, color=ISE, lw=1.1, zorder=3)
    ax.axvline(T_SPEC, color=AMB, lw=1.8, zorder=3)
    ax.text(T_SPEC - 4, 13.1, f"S6 / INT-S2 limit  {T_SPEC:.0f} s", fontsize=11.5,
            color=AMB, weight="bold", ha="right", va="top")
    ax.text(tmax * .995, (BAND_LO + BAND_HI) / 2, "recovery band 6.0 – 8.5",
            fontsize=11.5, color=ISE, ha="right", va="center", weight="bold")

    title(fig, "Every recovery, pH against time",
          f"{len(traces)} events · seed {rows[0].get('seed', '?')} · "
          f"{len(traces) - len(late)}/{len(traces)} inside the band before {T_SPEC:.0f} s")
    ax.set_xlabel("seconds after the unsafe event was confirmed", fontsize=12.5, color=INK)
    ax.set_ylabel("pH", fontsize=12.5, color=INK)
    ax.set_xlim(0, max(tmax * 1.02, T_SPEC * 1.06))
    ax.set_ylim(1.0, 13.4)
    provenance(fig, src, f"red = over {T_SPEC:.0f} s" if late else "no event over the limit")
    save(fig, out)

    s = dict(n=len(traces), late=late, n_late=len(late),
             out_of_band=out_of_band, n_out_of_band=len(out_of_band),
             t_max=tmax, chem_source=src, png=out)
    print(f"\ntraces, {s['n']} events   longest trace {tmax:.0f} s")
    print(f"  over {T_SPEC:.0f} s   : {len(late)}" + (f" -> {late[:20]}" if late else ""))
    print(f"  not in band : {len(out_of_band)}" + (f" -> {out_of_band[:20]}" if out_of_band else ""))
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.qc.traces")
    ap.add_argument("batch")
    ap.add_argument("--out", default="INT-AT-02_traces.png")
    a = ap.parse_args(argv)
    run(a.batch, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
