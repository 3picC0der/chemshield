"""One hash-chained audit log for everything the station does, written to disk as it goes.

It is Khalid's HashChainedAuditLog (same fields, same SHA-256 chain) with three more
fields, so gateway decisions and station events (event confirmed, recovery entered,
halt, dose added, Uno link lost, ...) sit in one chain that one script can verify:

    python -m hmi.verify_log logs/<run>/audit.jsonl        -> CHAIN OK
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hmi.common import reason_group, reason_words  # also puts gateway/src on sys.path
from chemshield_gateway.audit_log import AuditRecord, HashChainedAuditLog


@dataclass
class StationRecord(AuditRecord):
    source: str = "gateway"      # gateway | model A | optimiser | station | Uno | HMI
    event_id: str = ""
    message: str = ""


CSV_COLUMNS = list(StationRecord.__dataclass_fields__)


def record_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def verify_records(records: list[dict[str, Any]]) -> tuple[bool, str]:
    """(ok, detail) for records read back from the JSONL file."""
    previous = "GENESIS"
    for rec in records:
        payload = dict(rec)
        current = payload.pop("record_hash", None)
        if payload.get("previous_hash") != previous:
            return False, f"record {rec.get('index')}: previous_hash does not match record {int(rec.get('index', 0)) - 1}"
        if record_hash(payload) != current:
            return False, f"record {rec.get('index')}: contents were changed after it was written"
        previous = current
    return True, f"{len(records)} records, chain unbroken"


class StationAuditLog(HashChainedAuditLog):
    """Append-only, hash chained, flushed to audit.jsonl after every record."""

    def __init__(self, path: Path | None = None) -> None:
        super().__init__()
        self.path = Path(path) if path else None
        self._fh = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8")
        self._append_lock = threading.RLock()
        # the gateway's validate() calls append() itself; the station sets this first so
        # the record says who sent the command and for which event
        self.context: dict[str, str] = {}

    def append(self, command_id: str, decision: str, reason_code: str, forwarded_to_actuator: bool,
               *, channel_id: str = "", volume_ml: float = 0.0, dose_mmol: float = 0.0,
               event_mmol_total: float = 0.0, model_a_label: str = "NOT_CALLED",
               model_a_score: float = 0.0, source: str | None = None, event_id: str | None = None,
               message: str | None = None) -> StationRecord:
        with self._append_lock:
            ctx = self.context
            payload = {
                "index": len(self.records) + 1,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                "command_id": command_id,
                "decision": decision,
                "reason_code": reason_code,
                "forwarded_to_actuator": forwarded_to_actuator,
                "channel_id": channel_id,
                "volume_ml": volume_ml,
                "dose_mmol": dose_mmol,
                "event_mmol_total": event_mmol_total,
                "model_a_label": model_a_label,
                "model_a_score": model_a_score,
                "previous_hash": self._last_hash,
                "source": source if source is not None else ctx.get("source", "gateway"),
                "event_id": event_id if event_id is not None else ctx.get("event_id", ""),
                "message": message if message is not None else ctx.get("message", ""),
            }
            rec = StationRecord(record_hash=record_hash(payload), **payload)
            self.records.append(rec)
            self._last_hash = rec.record_hash
            if self._fh is not None:
                self._fh.write(json.dumps(asdict(rec)) + "\n")
                self._fh.flush()
            return rec

    def event(self, kind: str, message: str, *, event_id: str = "", source: str = "station",
              decision: str = "EVENT", command_id: str = "-", **fields: Any) -> StationRecord:
        """A station event (not a command decision)."""
        return self.append(command_id, decision, kind, False, source=source, event_id=event_id,
                           message=message, **fields)

    # ------------------------------------------------------------------ views
    @staticmethod
    def view(rec: StationRecord) -> dict[str, Any]:
        d = asdict(rec)
        d["group"] = reason_group(rec.reason_code) if rec.decision in ("ACCEPT", "REJECT") else "EVENT"
        d["words"] = reason_words(rec.reason_code) if rec.decision in ("ACCEPT", "REJECT") else rec.message
        d["hash_short"] = rec.record_hash[:6] + "…" + rec.record_hash[-4:]
        return d

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS + ["group", "words"])
        w.writeheader()
        for rec in self.records:
            v = self.view(rec)
            w.writerow({k: v.get(k, "") for k in CSV_COLUMNS + ["group", "words"]})
        return buf.getvalue()

    def to_jsonl(self) -> str:
        return "".join(json.dumps(asdict(r)) + "\n" for r in self.records)
