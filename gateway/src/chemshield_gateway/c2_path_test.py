from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv
from typing import Any

from .config import GatewayConfig
from .gateway_validator import GatewayValidator
from .simulated_actuator import SimulatedActuator
from .test_data import make_command


def run_c2_gateway_only_path_test(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    config = GatewayConfig()
    actuator = SimulatedActuator()
    gateway = GatewayValidator(config=config, actuator=actuator)
    now = datetime.now(timezone.utc)

    scenarios = []

    valid_command = make_command(
        config,
        command_id="C2-GW-VALID-001",
        event_id="C2-EVT-001",
        timestamp_utc=now,
        nonce="C2-NONCE-001",
        sequence_number=1,
    )
    via_gateway = gateway.validate(valid_command, category="authorized_gateway_path", received_at_utc=now)
    scenarios.append({
        "test_case": "authorized_gateway_path",
        "attempt": "HMI/MILP -> Gateway -> Actuator",
        "expected": "ACCEPT and forward",
        "decision": via_gateway.decision,
        "reason_code": via_gateway.reason_code,
        "forwarded_to_actuator": via_gateway.forwarded_to_actuator,
        "pass_fail": "PASS" if via_gateway.forwarded_to_actuator else "FAIL",
    })

    direct_ok = actuator.direct_write_attempt("C2-DIRECT-001")
    scenarios.append({
        "test_case": "direct_bypass_attempt",
        "attempt": "Operator laptop -> Actuator without gateway",
        "expected": "REJECT/BLOCK",
        "decision": "ACCEPT" if direct_ok else "REJECT",
        "reason_code": "BYPASS_ACCEPTED" if direct_ok else "BYPASS_BLOCKED",
        "forwarded_to_actuator": direct_ok,
        "pass_fail": "FAIL" if direct_ok else "PASS",
    })

    gateway.reboot()
    direct_during_safe_hold = actuator.direct_write_attempt("C2-DIRECT-SAFEHOLD-001")
    scenarios.append({
        "test_case": "direct_attempt_during_safe_hold",
        "attempt": "Direct actuator write while ChemShield is SAFE_HOLD",
        "expected": "REJECT/BLOCK",
        "decision": "ACCEPT" if direct_during_safe_hold else "REJECT",
        "reason_code": "BYPASS_ACCEPTED" if direct_during_safe_hold else "BYPASS_BLOCKED",
        "forwarded_to_actuator": direct_during_safe_hold,
        "pass_fail": "FAIL" if direct_during_safe_hold else "PASS",
    })

    csv_path = raw_dir / "c2_gateway_only_path_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(scenarios[0].keys()))
        writer.writeheader()
        writer.writerows(scenarios)

    return {
        "results": scenarios,
        "raw_csv": str(csv_path),
        "pass_fail": "PASS" if all(r["pass_fail"] == "PASS" for r in scenarios) else "FAIL",
        "target": "Only gateway-forwarded commands reach the actuator; direct bypass attempts fail.",
    }
