"""S2 evidence rows from the real audit logs: the gateway's own 20 mL cap and 15 s lockout decisions.

    python evidence/EXTRA_S2_dose_cap_and_mixing_wait/code/extract_s2_rows.py

Reads two hash-chained audit logs in this repo and writes ../data/s2_gateway_decisions.csv with
  * every DOSE_LIMIT rejection and every ACCEPT from the real rig run (2 Oct, Raspberry Pi 5)
  * the first ACCEPT and every MIXING_LOCKOUT rejection from the 3 Oct attack run (S3 folder)
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.normpath(os.path.join(HERE, "..", ".."))
LOGS = [
    ("rig 2 Oct (Pi 5, real probe)", os.path.join(EV, "06_S4_class_and_score_within_3s", "data", "rig_run_2Oct", "audit.jsonl"),
     lambda r: r["reason_code"] == "DOSE_LIMIT" or r["decision"] == "ACCEPT"),
    ("attack run 3 Oct (station on the laptop)", os.path.join(EV, "05_S3_replay_stale_rejected", "data", "laptop_run_3Oct", "ICS-AT-02_audit.jsonl"),
     lambda r: r["reason_code"] == "MIXING_LOCKOUT" or r["decision"] == "ACCEPT"),
]
FIELDS = ["log", "timestamp_utc", "command_id", "decision", "reason_code", "channel_id", "volume_ml", "message"]


def main() -> None:
    rows = []
    for name, path, keep in LOGS:
        for line in open(path, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("decision") in ("ACCEPT", "REJECT") and keep(r):
                rows.append({"log": name, **{k: r.get(k, "") for k in FIELDS[1:]}})
    out = os.path.join(HERE, "..", "data", "s2_gateway_decisions.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    counts = {}
    for r in rows:
        counts[(r["log"][:8], r["reason_code"])] = counts.get((r["log"][:8], r["reason_code"]), 0) + 1
    print(len(rows), "rows;", counts)


if __name__ == "__main__":
    main()
