from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class ValidationDecision:
    command_id: str
    category: str
    decision: str
    reason_code: str
    reason_detail: str
    forwarded_to_actuator: bool
    latency_ms: float
    model_a_label: str = "NOT_CALLED"
    model_a_score: float = 0.0
    model_a_latency_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessState:
    ph: float = 7.0
    mode: str = "NORMAL"  # NORMAL, RECOVERY, SAFE_HOLD
    heartbeat_healthy: bool = True
    mixing_lockout_remaining_s: float = 0.0
    cumulative_recovery_mmol: float = 0.0
    level_ok: bool = True


@dataclass
class RecoveryTimingResult:
    event_id: str
    current_ph: float
    counter_agent: str
    total_elapsed_s: float
    pass_2s_target: bool
    timeline: list[dict[str, Any]]


@dataclass
class FailSafeResult:
    test_case: str
    time_until_dosing_blocked_s: float
    time_until_safe_hold_s: float
    commands_accepted_after_failure: int
    restart_reset_behavior: str
    pass_fail: str
