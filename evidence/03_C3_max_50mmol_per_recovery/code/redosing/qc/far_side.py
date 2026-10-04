"""Far-side excursion check (test sheet INT-AT-03).

    python -m redosing.qc.far_side INT-AT-03_batch.csv --out INT-AT-03

For every event it finds the upset direction and the worst pH on the opposite side
during recovery, then counts how many events crossed pH 5.5 (after a base upset) or
pH 9.5 (after an acid upset). INT-S3 needs at least 90% with no excursion.

Writes  <out>_far_side.csv  and  <out>_worst_case.png.
"""
from __future__ import annotations

import argparse
import csv
import sys

import numpy as np

from .common import chem_source, load_batch, load_traces
from .style import AMB, GRID, INK, ISE, MUT, RED, clean, provenance, save, title, plt

FAR_LO, FAR_HI = 5.5, 9.5
BAND_LO, BAND_HI = 6.0, 8.5


def run(batch: str, out_prefix: str = "INT-AT-03") -> dict:
    rows = load_batch(batch)
    traces = load_traces(batch)
    src = chem_source(rows)

    recs = []
    for r in rows:
        eid = int(r["event_id"])
        acid = r["upset_dir"] == "ACID"
        pts = traces.get(eid, [])
        seg = [p for _t, p in pts[1:]] or [float(r["start_ph"])]
        peak = max(seg) if acid else min(seg)
        excursion = (peak > FAR_HI) if acid else (peak < FAR_LO)
        margin = (FAR_HI - peak) if acid else (peak - FAR_LO)
        recs.append(dict(event_id=eid, upset_dir=r["upset_dir"],
                         upset_mmol=r["upset_mmol"], start_ph=r["start_ph"],
                         far_side_limit=FAR_HI if acid else FAR_LO,
                         far_side_peak_ph=round(peak, 4),
                         margin_ph=round(margin, 4),
                         excursion="yes" if excursion else "no",
                         end_ph=r["end_ph"], outcome=r["outcome"]))

    csv_path = f"{out_prefix}_far_side.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(recs[0]))
        w.writeheader()
        w.writerows(recs)
    print(f"wrote {csv_path}")

    n = len(recs)
    bad = [r for r in recs if r["excursion"] == "yes"]
    worst = min(recs, key=lambda r: r["margin_ph"])          # smallest margin = closest
    pct = 100.0 * (n - len(bad)) / n

    # ---- worst-case plot: the event that came closest to a far-side limit
    wid = worst["event_id"]
    pts = traces[wid]
    t = np.array([p[0] for p in pts])
    ph = np.array([p[1] for p in pts])
    acid = worst["upset_dir"] == "ACID"

    fig = plt.figure(figsize=(10.6, 5.8))
    ax = fig.add_axes([.085, .135, .855, .70]); clean(ax)
    title(fig, "Worst-case far-side approach",
          f"event {wid} · {worst['upset_dir']} upset of {float(worst['upset_mmol']):.1f} mmol · "
          f"closest approach pH {worst['far_side_peak_ph']:.2f}, "
          f"{worst['margin_ph']:.2f} pH inside the limit")

    ax.axhspan(BAND_LO, BAND_HI, color=ISE, alpha=.085, zorder=0)
    ax.text(t.max() * .02, (BAND_LO + BAND_HI) / 2, "recovery band 6.0 – 8.5",
            fontsize=11.5, color=ISE, ha="left", va="center", weight="bold")
    for y, lab in ((FAR_LO, f"far-side limit {FAR_LO}"), (FAR_HI, f"far-side limit {FAR_HI}")):
        ax.axhline(y, color=AMB, lw=1.4, zorder=2)
        ax.text(0, y + .08, lab, fontsize=11, color=AMB, weight="bold")
    ax.plot(t, ph, color=ISE, lw=1.7, marker="o", ms=4, zorder=4, label="tank pH")
    k = int(np.argmax(ph) if acid else np.argmin(ph))
    ax.scatter([t[k]], [ph[k]], s=70, facecolors="none", edgecolors=RED, lw=1.6, zorder=5)
    ax.annotate(f"closest approach\npH {ph[k]:.2f}", (t[k], ph[k]),
                textcoords="offset points", xytext=(-14, 22 if acid else -40),
                ha="right", fontsize=12, color=RED, weight="bold")
    ax.set_xlabel("seconds after the unsafe event was confirmed", fontsize=12.5, color=INK)
    ax.set_ylabel("pH", fontsize=12.5, color=INK)
    ax.set_ylim(min(4.8, ph.min() - .4), max(10.2, ph.max() + .4))
    ax.set_xlim(-t.max() * .015, t.max() * 1.10)
    ax.legend(fontsize=11.5, frameon=False, loc="lower right")
    provenance(fig, src, f"{n} events")
    png = save(fig, f"{out_prefix}_worst_case.png")

    s = dict(n=n, excursions=len(bad), no_excursion=n - len(bad), pct_no_excursion=pct,
             worst_event=wid, worst_peak_ph=worst["far_side_peak_ph"],
             worst_margin_ph=worst["margin_ph"], worst_dir=worst["upset_dir"],
             csv=csv_path, png=png, chem_source=src,
             excursion_events=[r["event_id"] for r in bad])
    print(f"\nfar-side check, {n} events")
    print(f"  no excursion   : {s['no_excursion']}/{n} = {pct:.1f}%   "
          f"(INT-S3 needs >= 90%)")
    print(f"  excursions     : {len(bad)}" + (f" -> events {s['excursion_events'][:20]}" if bad else ""))
    print(f"  closest approach: event {wid} ({worst['upset_dir']} upset), "
          f"pH {worst['far_side_peak_ph']:.3f}, {worst['margin_ph']:.3f} pH inside the "
          f"{worst['far_side_limit']} limit")
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m redosing.qc.far_side")
    ap.add_argument("batch")
    ap.add_argument("--out", default="INT-AT-03")
    a = ap.parse_args(argv)
    run(a.batch, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
