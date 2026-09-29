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
    channel_id: str = ""
    volume_ml: float = 0.0
    dose_mmol: float = 0.0            # computed by the gateway: volume_ml x bottle molarity
    event_mmol_total: float = 0.0     # this event's accepted total after this decision

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProcessState:
    ph: float = 7.0
    mode: str = "NORMAL"  # NORMAL, RECOVERY, SAFE_HOLD
    heartbeat_healthy: bool = True
    mixing_lockout_remaining_s: float = 0.0  # derived by the gateway from the fields below, for display
    last_dose_accepted_at_s: float | None = None  # gateway clock reading when the last dose was accepted
    cumulative_recovery_mmol: float = 0.0  # accepted mmol so far in the latest dosed event
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
