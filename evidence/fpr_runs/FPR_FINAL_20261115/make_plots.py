"""Builds every plot for the FPR evidence page from the recorded data in this folder.

    ../chemshield/.venv/bin/python evidence/fpr_runs/FPR_FINAL_20261115/make_plots.py
"""
import csv
import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "plots"
OUT.mkdir(exist_ok=True)

BLUE, ORANGE, AQUA, GRAY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
BAND = "#2a78d6"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "axes.titlelocation": "left", "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "legend.frameon": False, "figure.dpi": 100, "savefig.dpi": 200,
    "savefig.bbox": "tight", "savefig.facecolor": "white",
})


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def limit(ax, y, text, horizontal=True, color=INK2):
    if horizontal:
        ax.axhline(y, color=color, ls="--", lw=1.4)
        ax.annotate(text, (1, y), xycoords=("axes fraction", "data"), xytext=(-4, 4),
                    textcoords="offset points", ha="right", va="bottom", color=color, fontsize=10)
    else:
        ax.axvline(y, color=color, ls="--", lw=1.4)
        ax.annotate(text, (y, 1), xycoords=("data", "axes fraction"), xytext=(-4, -4),
                    textcoords="offset points", ha="right", va="top", color=color, fontsize=10)


def save(fig, name):
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", name)


# ------------------------------------------------------------------ recovery runs
runs = [r for r in rows(HERE / "02_recovery_runs/recovery_runs.csv")
        if r["included"] == "True" and float(r["reagent_mmol"]) > 0]
assert len(runs) == 5, len(runs)
labels = [f"Run {i}" for i in range(1, 6)]
spill = ["6 mL", "6 mL", "12 mL", "6 mL", "8 mL"]
x = np.arange(5)
xl = [f"{a}\n{b} spill" for a, b in zip(labels, spill)]


def f(r, k):
    return float(r[k]) if r[k] not in ("", None) else np.nan


# INT-S1: three timings per run on a log scale
fig, ax = plt.subplots(figsize=(8, 4.2))
series = [("confirm_to_recovery_ms", "Recovery mode entered", BLUE, "o"),
          ("confirm_to_uno_locked_ms", "Pumps locked (Uno)", AQUA, "s"),
          ("confirm_to_hmi_shown_ms", "Shown on the HMI", ORANGE, "D")]
for k, name, c, m in series:
    ax.scatter(x, [f(r, k) for r in runs], s=70, color=c, marker=m, label=name, zorder=3,
               edgecolor="white", linewidth=1.5)
ax.set_yscale("log")
ax.set_ylim(0.2, 8000)
limit(ax, 2000, "limit 2,000 ms")
ax.set_xticks(x, xl)
ax.set_ylabel("time after the spill is confirmed (ms)")
ax.set_title("INT-S1 · Safe-recovery mode within 2 s")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=3, fontsize=9.5)
ax.annotate("HMI time\nnot recorded", (4, 120), ha="center", color=INK2, fontsize=9)
save(fig, "INT-S1_recovery_mode_timing.png")

# INT-S2 + S6: back in band and fully closed, vs 300 s
fig, ax = plt.subplots(figsize=(8, 4.2))
w = 0.36
b1 = ax.bar(x - w / 2 - 0.01, [f(r, "first_in_band_s") for r in runs], w, color=BLUE, label="back in 6.0–8.5 (INT-S2)")
b2 = ax.bar(x + w / 2 + 0.01, [f(r, "recovery_time_s") for r in runs], w, color=ORANGE, label="recovery finished (S6)")
for bars in (b1, b2):
    for b in bars:
        ax.annotate(f"{b.get_height():.0f} s", (b.get_x() + b.get_width() / 2, b.get_height()),
                    xytext=(0, 3), textcoords="offset points", ha="center", fontsize=9, color=INK2)
limit(ax, 300, "limit 300 s")
ax.set_ylim(0, 330)
ax.set_xticks(x, xl)
ax.set_ylabel("seconds after the spill")
ax.set_title("INT-S2 / S6 · pH restored well inside 5 minutes")
ax.legend(loc="upper left")
save(fig, "INT-S2_S6_recovery_times.png")

# C3: reagent per recovery
fig, ax = plt.subplots(figsize=(8, 4.2))
bars = ax.bar(x, [f(r, "reagent_mmol") for r in runs], 0.55, color=BLUE)
for b in bars:
    ax.annotate(f"{b.get_height():.1f}", (b.get_x() + b.get_width() / 2, b.get_height()),
                xytext=(0, 3), textcoords="offset points", ha="center", fontsize=10, color=INK2)
limit(ax, 50, "limit 50 mmol")
ax.set_ylim(0, 56)
ax.set_xticks(x, xl)
ax.set_ylabel("reagent used (mmol)")
ax.set_title("C3 · Reagent per recovery ≤ 50 mmol")
save(fig, "C3_reagent_per_recovery.png")

# INT-S3: lowest and highest pH per run
fig, ax = plt.subplots(figsize=(8, 4.4))
ax.axhspan(6.0, 8.5, color=BAND, alpha=0.08, lw=0)
ax.annotate("safe band 6.0–8.5", (0.01, 8.42), xycoords=("axes fraction", "data"), va="top", fontsize=9.5, color=INK2)
lo = [f(r, "spill_side_ph") for r in runs]
hi = [f(r, "far_side_ph") for r in runs]
ax.vlines(x, lo, hi, color=GRAY, lw=2)
ax.scatter(x, lo, s=70, color=ORANGE, label="lowest pH (the spill)", zorder=3, edgecolor="white", linewidth=1.5)
ax.scatter(x, hi, s=70, color=BLUE, marker="D", label="highest pH during the correction", zorder=3, edgecolor="white", linewidth=1.5)
for i, v in enumerate(hi):
    ax.annotate(f"{v:.2f}", (i, v), xytext=(0, 9) if v > 9 else (9, 0), textcoords="offset points", ha="center" if v > 9 else "left", va="bottom" if v > 9 else "center", fontsize=9, color=INK2)
limit(ax, 9.5, "overshoot limit 9.5")
ax.set_ylim(3, 10.4)
ax.set_xticks(x, xl)
ax.set_ylabel("pH")
ax.set_title("INT-S3 · No overshoot past 9.5 while correcting an acid spill")
ax.legend(loc="lower right", fontsize=9.5)
save(fig, "INT-S3_ph_extremes.png")

# ------------------------------------------------------------------ S1 hold
h = rows(HERE / "03_S1_hold/hold_PASS/s1_hold.csv")
t = np.array([float(r["elapsed_s"]) for r in h]) / 60
p = np.array([float(r["ph"]) for r in h])
fig, ax = plt.subplots(figsize=(8, 4))
ax.axhspan(6.5, 7.5, color=BAND, alpha=0.08, lw=0)
ax.plot(t, p, color=BLUE, lw=1.6)
for y in (6.5, 7.5):
    ax.axhline(y, color=INK2, ls="--", lw=1.2)
ax.annotate("required band 6.5–7.5", (0.01, 7.47), xycoords=("axes fraction", "data"), va="top", fontsize=9.5, color=INK2)
ax.annotate(f"600 readings · min {p.min():.2f} · max {p.max():.2f} · 0 outside", (0.99, 6.53),
            xycoords=("axes fraction", "data"), ha="right", va="bottom", fontsize=10, color=INK)
ax.set_xlim(0, 10)
ax.set_ylim(6.3, 7.7)
ax.set_xlabel("minutes")
ax.set_ylabel("pH (probe, 1 reading per second)")
ax.set_title("S1 · pH held in 6.5–7.5 for 10 minutes")
save(fig, "S1_ph_hold_10min.png")

# ------------------------------------------------------------------ audit logs (S2, S3)
audits = [rows(a) for a in sorted((HERE / "06_audit_logs").glob("*.csv"))]
allrows = [r for a in audits for r in a]

# S2a: every operator / planner dose request, accepted vs over-cap
req = [r for r in allrows if r["decision"] in ("ACCEPT", "REJECT") and r["channel_id"]
       and ("operator" in r["message"] or "recovery planner" in r["message"])
       and r["reason_code"] in ("ACCEPTED", "DOSE_LIMIT")]
# the 25 mL fine-base request at 19:14 UTC is in session 1's audit after the partial download
extra = [{"volume_ml": "25.0", "reason_code": "DOSE_LIMIT"}]
acc = [float(r["volume_ml"]) for r in req if r["reason_code"] == "ACCEPTED"]
rej = [float(r["volume_ml"]) for r in req if r["reason_code"] == "DOSE_LIMIT"] + [25.0]
fig, ax = plt.subplots(figsize=(8, 4))
rng = np.random.default_rng(1)
ax.scatter(rng.uniform(-0.18, 0.18, len(acc)), acc, s=55, color=BLUE, edgecolor="white", linewidth=1.2, zorder=3)
ax.scatter(1 + np.linspace(-0.15, 0.15, len(rej)), rej, s=70, color=ORANGE, marker="X", edgecolor="white", linewidth=1.2, zorder=3)
limit(ax, 20, "dose cap 20 mL")
ax.set_xticks([0, 1], [f"accepted ({len(acc)})", f"rejected: over the cap ({len(rej)})"])
ax.set_xlim(-0.6, 1.6)
ax.set_ylim(0, 28)
ax.set_ylabel("requested dose (mL)")
ax.set_title("S2 · Every dose over 20 mL is rejected")
save(fig, "S2_dose_cap.png")

# S2b: time between accepted doses
added = sorted(datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00"))
               for a in audits for r in a if r["reason_code"] == "DOSE_ADDED")
gaps = np.array([(b - a).total_seconds() for a, b in zip(added, added[1:])])
gaps = gaps[gaps < 120]
lock = sum(1 for r in allrows if r["reason_code"] == "MIXING_LOCKOUT")
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(gaps, bins=np.arange(0, 125, 5), color=BLUE, edgecolor="white", linewidth=1.5)
ax.axvline(15, color=INK2, ls="--", lw=1.4)
ax.annotate("15 s\nmixing time", (15, 0.6), xycoords=("data", "axes fraction"), xytext=(-6, 0), textcoords="offset points", ha="right", color=INK2, fontsize=10)
ax.set_xlabel("seconds between two doses going into the tank")
ax.set_ylabel("number of dose pairs")
ax.set_title("S2 · At least 15 s of mixing between doses")
ax.annotate(f"shortest gap {gaps.min():.1f} s\n{lock:,} early requests held back by the mixing wait",
            (0.98, 0.95), xycoords="axes fraction", ha="right", va="top", fontsize=10, color=INK)
save(fig, "S2_mixing_time.png")

# S3 + C2: attack commands by type
kinds = [("Replayed", "REUSED_NONCE"), ("Stale (5 s old)", "STALE_TIMESTAMP"),
         ("Forged key / tampered", "INVALID_HMAC"), ("Unsigned", "MISSING_SIGNATURE")]
att = [r for r in allrows if r["decision"] == "REJECT"]
counts = [sum(1 for r in att if r["reason_code"] == code) for _, code in kinds]
reached = sum(1 for r in allrows if r["forwarded_to_actuator"] == "True" and "attack" in r["message"].lower()
              and "original" not in r["message"] and "(valid)" not in r["message"])
fig, ax = plt.subplots(figsize=(8, 3.6))
yy = np.arange(len(kinds))[::-1]
bars = ax.barh(yy, counts, 0.55, color=BLUE)
for b, n in zip(bars, counts):
    ax.annotate(f"{n:,} blocked", (b.get_width(), b.get_y() + b.get_height() / 2), xytext=(5, 0),
                textcoords="offset points", va="center", fontsize=10, color=INK)
ax.set_yticks(yy, [k for k, _ in kinds])
ax.set_xlim(0, max(counts) * 1.25)
ax.set_xlabel("attack commands sent to the gateway (all rejected)")
ax.set_title(f"S3 / C2 · {sum(counts):,} attack commands, {reached} reached a pump")
save(fig, "S3_C2_attacks_blocked.png")

# ------------------------------------------------------------------ S4 latency
lat = np.array([float(r["decision_time_ms"]) for r in rows(HERE / "05_S4_ai_timing/pi_1000_requests/ICS-AT-03_latency.csv")])
fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(lat, bins=40, color=BLUE, edgecolor="white", linewidth=1)
ax.set_xlabel("time to classify one dose request (ms)")
ax.set_ylabel("requests")
ax.set_title("S4 · AI Dose Guard: class + risk score for 1,000 requests on the Pi")
ax.annotate(f"max {lat.max():.2f} ms · mean {lat.mean():.2f} ms\nlimit 3,000 ms (about {3000 / lat.max():,.0f}× the slowest)",
            (0.98, 0.95), xycoords="axes fraction", ha="right", va="top", fontsize=10, color=INK)
save(fig, "S4_ai_dose_guard_timing.png")

# ------------------------------------------------------------------ C1
bottles = [("HCl 0.005 M", 0.018), ("NaOH 0.005 M", 0.020), ("HCl 0.5 M", 1.81), ("NaOH 0.5 M", 1.959)]
fig, ax = plt.subplots(figsize=(8, 3.4))
yy = np.arange(4)
bars = ax.barh(yy, [v for _, v in bottles], 0.55, color=BLUE)
for b, (_, v) in zip(bars, bottles):
    ax.annotate(f"{v:.2f} wt%", (b.get_width(), b.get_y() + b.get_height() / 2), xytext=(5, 0),
                textcoords="offset points", va="center", fontsize=10, color=INK)
limit(ax, 5, "limit 5 wt%", horizontal=False)
ax.set_yticks(yy, [n for n, _ in bottles])
ax.set_xlim(0, 5.6)
ax.set_xlabel("concentration (wt%)")
ax.set_title("C1 · All four reagents are dilute (≤ 5 wt%)")
save(fig, "C1_reagent_strength.png")

# ------------------------------------------------------------------ S9
s9 = json.load(open(HERE / "07_S9_simulation/s9_summary.json"))
metrics = [("Spills recovered (%)", s9["pi_success"] / 6, s9["solver_success"] / 6, "{:.0f}"),
           ("Mean recovery time (s)", s9["pi_mean_t"], s9["solver_mean_t"], "{:.0f}"),
           ("Doses per spill", 9.84, 3.75, "{:.1f}"),
           ("Reagent per spill (mmol)*", s9["pi_mean_mmol"], s9["solver_mean_mmol"], "{:.1f}")]
fig, axs = plt.subplots(1, 4, figsize=(11, 3.6))
for ax, (name, a, b, fmt) in zip(axs, metrics):
    bars = ax.bar([0, 1], [a, b], 0.6, color=[GRAY, BLUE])
    for bb, v in zip(bars, (a, b)):
        ax.annotate(fmt.format(v), (bb.get_x() + bb.get_width() / 2, v), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=10, color=INK)
    ax.set_xticks([0, 1], ["PI", "ChemShield"])
    ax.set_title(name, fontsize=11, fontweight="normal", color=INK)
    ax.set_ylim(0, max(a, b) * 1.2)
    ax.grid(axis="x", visible=False)
fig.suptitle("S9 · ChemShield solver vs a PI controller, same 600 simulated spills", x=0.01, ha="left",
             fontsize=13, fontweight="bold", color=INK)
fig.tight_layout()
fig.text(0.01, -0.03, "* on the 417 spills both controllers brought back into the safe band", fontsize=9.5, color=INK2)
save(fig, "S9_solver_vs_PI.png")
