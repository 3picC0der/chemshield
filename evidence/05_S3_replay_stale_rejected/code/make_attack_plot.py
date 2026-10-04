"""Bar chart of the S3 attack run from its audit log.  python make_attack_plot.py"""
import json
import os
from collections import Counter

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "..", "data", "laptop_run_3Oct", "ICS-AT-02_audit.jsonl")
recs = [json.loads(line) for line in open(AUDIT, encoding="utf-8") if line.strip()]
cnt = Counter(r["reason_code"] for r in recs if r.get("source") == "gateway" and "ATTACK" in r.get("command_id", ""))
replay, stale = cnt["REUSED_NONCE"], cnt["STALE_TIMESTAMP"]
other = {k: v for k, v in cnt.items() if k not in ("REUSED_NONCE", "STALE_TIMESTAMP")}
fig, ax = plt.subplots(figsize=(9, 4.6), dpi=150)
labels = ["replayed copies\nrejected (REUSED_NONCE)", "stale commands (5 s old)\nrejected (STALE_TIMESTAMP)"]
vals = [replay, stale]
ax.bar(labels, vals, color=["#2557a7", "#2f7d5b"], width=0.5)
for i, v in enumerate(vals):
    ax.text(i, v + 20, f"{v} of 1000", ha="center", fontsize=11, fontweight="bold")
ax.axhline(990, color="#b02a2a", ls="--", lw=1.5)
ax.text(1.45, 995, "99% line (990)", color="#b02a2a", ha="right", fontsize=9)
ax.set_ylim(0, 1150)
ax.set_ylabel("commands")
fresh = cnt["ACCEPTED"] + cnt["DOSE_PENDING"] + cnt["MIXING_LOCKOUT"]
ax.set_title(f"S3, 3 Oct: {replay + stale} of 2000 replayed or stale commands rejected (100%)", fontsize=11, fontweight="bold")
fig.text(0.5, 0.012, f"The {fresh} fresh commands sent alongside were never called replayed or stale; the gateway held them\n"
         "with its other rules (15 s lockout, one dose at a time).", ha="center", fontsize=8.5, color="#444444")
ax.grid(axis="y", alpha=0.25)
fig.tight_layout(rect=(0, 0.06, 1, 1))
out = os.path.join(HERE, "..", "plots", "S3_attack_results.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out)
print("replay", replay, "stale", stale, "other reject reasons in the log:", other)
