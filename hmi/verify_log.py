"""Check that an exported audit log was not altered (INT-AT-04 step 9, ICS-AT-02 step 7).

    .venv/bin/python -m hmi.verify_log audit.jsonl          prints CHAIN OK or CHAIN BROKEN
    .venv/bin/python -m hmi.verify_log hmi/logs/<run>/audit.jsonl

Each record carries the SHA-256 hash of the one before it, so changing, deleting or
reordering any record breaks every hash after it. Also prints the counts by reason.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from hmi.common import reason_group
from hmi.station.audit import verify_records


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__)
        return 2
    path = Path(argv[0])
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    ok, detail = verify_records(records)
    decisions = [r for r in records if r.get("decision") in ("ACCEPT", "REJECT")]
    by_group = Counter(reason_group(r["reason_code"]) for r in decisions)
    print(f"{path}: {detail}")
    print(f"commands: {len(decisions)} (" + ", ".join(f"{k} {v}" for k, v in sorted(by_group.items())) + ")")
    print("CHAIN OK" if ok else "CHAIN BROKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
