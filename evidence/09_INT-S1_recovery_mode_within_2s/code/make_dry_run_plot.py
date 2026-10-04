"""Histogram of the 100-event INT-S1 dry run.  python make_dry_run_plot.py"""
import csv
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, "..", "data", "laptop_dry_run_30Sep", "INT-AT-01_batch.csv"))))
rec = [float(r["confirm_to_recovery_ms"]) for r in rows]
hmi = [float(r["confirm_to_hmi_shown_ms"]) for r in rows]
fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150, sharey=False)
ax[0].hist(rec, bins=20, color="#2557a7")
ax[0].set_title(f"confirmed to RECOVERY on the Pi\nmax {max(rec):.1f} ms of 2000 ms")
ax[1].hist(hmi, bins=20, color="#2f7d5b")
ax[1].axvline(2000, color="#b02a2a", lw=2)
ax[1].set_xlim(0, 2100)
ax[1].text(1980, ax[1].get_ylim()[1] * 0.9, "2000 ms limit", color="#b02a2a", ha="right")
ax[1].set_title(f"confirmed to RECOVERY drawn on the HMI\nmax {max(hmi):.0f} ms (HMI polls every 250 ms)")
for a in ax:
    a.set_xlabel("milliseconds"); a.set_ylabel("events"); a.grid(alpha=0.25)
fig.suptitle(f"INT-S1 dry run, {len(rows)} simulated unsafe events (30 Sep)", fontweight="bold")
fig.tight_layout()
out = os.path.join(HERE, "..", "plots", "INT-S1_dry_run_100_events.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out)
print("wrote", os.path.normpath(out))
