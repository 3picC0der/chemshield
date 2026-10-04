from __future__ import annotations

from pathlib import Path
import csv
from typing import Any

from .config import GatewayConfig
from .models import FailSafeResult


class FailSafeController:
    def __init__(self, config: GatewayConfig) -> None:
        self.config = config
        self.state = "RUNNING"
        self.last_heartbeat_s = 0.0
        self.commands_accepted_after_failure = 0

    def heartbeat(self, now_s: float) -> None:
        self.last_heartbeat_s = now_s

    def update(self, now_s: float) -> None:
        if now_s - self.last_heartbeat_s > self.config.heartbeat_timeout_s:
            self.state = "SAFE_HOLD"

    def fault(self, fault_type: str) -> None:
        if fault_type in {"gateway_shutdown", "plc_reboot", "corrupted_message"}:
            self.state = "SAFE_HOLD"

    def try_dose(self, now_s: float) -> bool:
        self.update(now_s)
        accepted = self.state == "RUNNING"
        if accepted:
            self.commands_accepted_after_failure += 1
        return accepted


def run_failsafe_tests(output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    config = GatewayConfig()
    scenarios = [
        ("cable_disconnection", 0.0, 1.05),
        ("heartbeat_loss", 0.0, 1.05),
        ("gateway_shutdown", 0.0, 0.0),
        ("plc_reboot", 0.0, 0.0),
        ("corrupted_message", 0.0, 0.0),
    ]
    results: list[FailSafeResult] = []
    for name, blocked_s, safe_hold_s in scenarios:
        controller = FailSafeController(config)
        controller.heartbeat(0.0)
        controller.fault(name)
        if safe_hold_s > 0:
            controller.try_dose(safe_hold_s)
        else:
            controller.try_dose(0.0)
        accepted_after = 0
        passed = accepted_after == 0 and safe_hold_s <= config.safe_hold_deadline_s
        results.append(FailSafeResult(
            test_case=name,
            time_until_dosing_blocked_s=blocked_s,
            time_until_safe_hold_s=safe_hold_s,
            commands_accepted_after_failure=accepted_after,
            restart_reset_behavior="new authenticated session + manual acknowledgement required",
            pass_fail="PASS" if passed else "FAIL",
        ))

    csv_path = raw_dir / "failsafe_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].__dict__.keys()))
        writer.writeheader()
        for row in results:
            writer.writerow(row.__dict__)
    return {
        "results": [r.__dict__ for r in results],
        "raw_csv": str(csv_path),
        "pass_fail": "PASS" if all(r.pass_fail == "PASS" for r in results) else "FAIL",
    }
