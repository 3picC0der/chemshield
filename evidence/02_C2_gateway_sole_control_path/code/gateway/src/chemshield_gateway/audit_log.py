from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


@dataclass
class AuditRecord:
    index: int
    timestamp_utc: str
    command_id: str
    decision: str
    reason_code: str
    forwarded_to_actuator: bool
    channel_id: str
    volume_ml: float
    dose_mmol: float
    event_mmol_total: float
    model_a_label: str
    model_a_score: float
    previous_hash: str
    record_hash: str


class HashChainedAuditLog:
    """Append-only audit log with a hash chain.

    Each record includes the previous record hash. This makes the log useful as
    demonstration evidence because changes to old records break the chain.
    """

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self._last_hash = "GENESIS"

    def append(
        self,
        command_id: str,
        decision: str,
        reason_code: str,
        forwarded_to_actuator: bool,
        *,
        channel_id: str = "",
        volume_ml: float = 0.0,
        dose_mmol: float = 0.0,
        event_mmol_total: float = 0.0,
        model_a_label: str = "NOT_CALLED",
        model_a_score: float = 0.0,
    ) -> AuditRecord:
        payload = {
            "index": len(self.records) + 1,
            "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        }
        record_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        record = AuditRecord(record_hash=record_hash, **payload)
        self.records.append(record)
        self._last_hash = record_hash
        return record

    def verify(self) -> bool:
        previous = "GENESIS"
        for record in self.records:
            payload = asdict(record)
            current_hash = payload.pop("record_hash")
            if payload["previous_hash"] != previous:
                return False
            expected = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
            if expected != current_hash:
                return False
            previous = current_hash
        return True

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for record in self.records:
                f.write(json.dumps(asdict(record)) + "\n")
