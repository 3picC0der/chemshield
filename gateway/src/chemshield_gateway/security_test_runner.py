from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import csv
from pathlib import Path
import statistics
import time
from typing import Any

from .config import GatewayConfig
from .gateway_validator import GatewayValidator
from .models import ProcessState, ValidationDecision
from .simulated_actuator import SimulatedActuator
from .test_data import ManualClock, generate_attack_categories


CATEGORY_ORDER = [
    "valid",
    "replay",
    "stale",
    "reused_nonce",
    "out_of_order_sequence",
    "invalid_hmac",
    "unsigned",
    "oversize",
    "wrong_role_or_session",
    "malformed",
    "replayed_after_reboot",
    "gateway_bypass_attempt",
    "burst_during_lockout",
    "bad_certificate",
]

MALICIOUS_CATEGORIES = set(CATEGORY_ORDER) - {"valid"}


def run_security_test(output_dir: Path, per_category: int = 1000) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    config = GatewayConfig()
    actuator = SimulatedActuator()
    state = ProcessState()
    clock = ManualClock()
    gateway = GatewayValidator(config=config, actuator=actuator, state=state, clock=clock)
    now = datetime.now(timezone.utc)
    burst_i = 0

    rows: list[ValidationDecision] = []
    reboot_done = False
    for category, command in generate_attack_categories(config, now, per_category=per_category):
        if category == "replayed_after_reboot" and not reboot_done:
            gateway.reboot()
            reboot_done = True

        if category == "gateway_bypass_attempt":
            started = time.perf_counter()
            accepted = actuator.direct_write_attempt(command["command_id"])
            decision = ValidationDecision(
                command_id=command["command_id"],
                category=category,
                decision="ACCEPT" if accepted else "REJECT",
                reason_code="BYPASS_ACCEPTED" if accepted else "BYPASS_BLOCKED",
                reason_detail="direct actuator write attempted without ChemShield gateway",
                forwarded_to_actuator=accepted,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 4),
            )
        else:
            if category == "valid":
                # valid doses are paced like a real recovery: one per mixing period
                clock.advance(config.min_mixing_time_s)
            elif category == "burst_during_lockout":
                # the whole burst lands 1 s to (lockout - 1) s after the last accepted dose
                gateway.manual_ack_new_session()
                span = config.min_mixing_time_s - 2.0
                clock.t = gateway.state.last_dose_accepted_at_s + 1.0 + span * burst_i / per_category
                burst_i += 1
            elif category in {"bad_certificate"}:
                gateway.manual_ack_new_session()
                clock.advance(config.min_mixing_time_s)
            decision = gateway.validate(command, category=category, received_at_utc=now)
        rows.append(decision)

    raw_csv = raw_dir / "security_test_commands.csv"
    with raw_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].to_dict().keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())

    gateway.audit_log.write_jsonl(raw_dir / "hash_chained_audit_log.jsonl")

    by_category: dict[str, list[ValidationDecision]] = defaultdict(list)
    for row in rows:
        by_category[row.category].append(row)

    summary_rows = []
    for category in CATEGORY_ORDER:
        category_rows = by_category[category]
        total = len(category_rows)
        accepted = sum(r.decision == "ACCEPT" for r in category_rows)
        rejected = total - accepted
        forwarded = sum(r.forwarded_to_actuator for r in category_rows)
        summary_rows.append({
            "category": category,
            "total": total,
            "accepted": accepted,
            "rejected": rejected,
            "forwarded_to_actuator": forwarded,
            "rejection_rate_percent": round((rejected / total) * 100, 2) if total else 0.0,
        })

    summary_csv = reports_dir / "security_test_summary.csv"
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    replay_stale_rows = [r for r in rows if r.category in {"replay", "stale", "replayed_after_reboot"}]
    replay_stale_rejected = sum(r.decision == "REJECT" for r in replay_stale_rows)
    valid_rows = by_category["valid"]
    all_latencies = [r.latency_ms for r in rows]
    malicious_forwarded = sum(r.forwarded_to_actuator for r in rows if r.category in MALICIOUS_CATEGORIES)

    summary = {
        "total_commands": len(rows),
        "per_category": per_category,
        "replay_stale_rejection_rate_percent": round((replay_stale_rejected / len(replay_stale_rows)) * 100, 2),
        "target_replay_stale_rejection_rate_percent": 99.0,
        "valid_command_acceptance_rate_percent": round((sum(r.decision == "ACCEPT" for r in valid_rows) / len(valid_rows)) * 100, 2),
        "malicious_commands_reaching_actuator": malicious_forwarded,
        "audit_log_hash_chain_valid": gateway.audit_log.verify(),
        "median_latency_ms": round(statistics.median(all_latencies), 4),
        "p95_latency_ms": round(statistics.quantiles(all_latencies, n=100)[94], 4),
        "max_latency_ms": round(max(all_latencies), 4),
        "raw_csv": str(raw_csv),
        "summary_csv": str(summary_csv),
        "audit_jsonl": str(raw_dir / "hash_chained_audit_log.jsonl"),
        "category_results": summary_rows,
    }
    summary["pass_fail"] = "PASS" if (
        summary["replay_stale_rejection_rate_percent"] >= 99.0
        and malicious_forwarded == 0
        and summary["audit_log_hash_chain_valid"]
    ) else "FAIL"
    return summary
