from __future__ import annotations

from datetime import datetime, timezone
import math
import time
from typing import Any, Callable

from .audit_log import HashChainedAuditLog
from .auth import is_valid_hmac
from .config import NO_CHANNEL, GatewayConfig
from .model_a_client import FakeModelAClient
from .models import ProcessState, ValidationDecision
from .simulated_actuator import SimulatedActuator


REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "session_id",
    "command_id",
    "event_id",
    "timestamp_utc",
    "nonce",
    "sequence_number",
    "user_role",
    "action",
    "channel_id",
    "volume_ml",
    "flow_ml_min",
    "mixing_time_s",
    "recovery_plan_hash",
    "client_cert_fingerprint",
    "hmac_sha256",
)

DOSE_ACTIONS: tuple[str, ...] = ("DOSE", "RECOVERY_DOSE")


class GatewayValidator:
    """ChemShield command gateway.

    Validation order:
    schema -> role/session -> HMAC -> timestamp -> nonce -> sequence ->
    rate/state -> 15 s lockout -> <=20 mL / <=50 mmol per event -> Model A -> certificate -> actuator.

    The mmol of a dose is computed here, volume_ml x the channel's bottle molarity, and
    added to a per-event total (event_mmol_used). Nothing the client says about mmol is used.
    """

    def __init__(
        self,
        config: GatewayConfig | None = None,
        actuator: SimulatedActuator | None = None,
        model_a: FakeModelAClient | None = None,
        audit_log: HashChainedAuditLog | None = None,
        state: ProcessState | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.config = config or GatewayConfig()
        # seconds, monotonic; the mixing lockout is timed on this. Tests pass their own.
        self.clock = clock or time.monotonic
        self.actuator = actuator or SimulatedActuator()
        self.model_a = model_a or FakeModelAClient(self.config)
        self.audit_log = audit_log or HashChainedAuditLog()
        self.state = state or ProcessState()

        self.used_nonces: set[str] = set()
        self.persisted_used_nonces: set[str] = set()
        self.processed_command_ids: set[str] = set()
        self.persisted_command_ids: set[str] = set()
        self.last_sequence_number: int = 0
        self.event_mmol_used: dict[str, float] = {}   # event_id -> accepted mmol

    def reboot(self) -> None:
        """A restart begins in SAFE_HOLD and keeps replay memory."""
        self.state.mode = "SAFE_HOLD"
        self.state.heartbeat_healthy = False
        self.used_nonces = set(self.persisted_used_nonces)
        self.processed_command_ids = set(self.persisted_command_ids)

    def manual_ack_new_session(self) -> None:
        self.state.mode = "NORMAL"
        self.state.heartbeat_healthy = True

    def lockout_remaining_s(self, now_s: float | None = None) -> float:
        """Seconds until the next dose may be accepted: min_mixing_time_s after the last
        accepted dose. Also written to state.mixing_lockout_remaining_s for display."""
        last = self.state.last_dose_accepted_at_s
        now_s = self.clock() if now_s is None else now_s
        remaining = 0.0 if last is None else max(0.0, self.config.min_mixing_time_s - (now_s - last))
        self.state.mixing_lockout_remaining_s = round(remaining, 3)
        return remaining

    def validate(self, command: dict[str, Any], *, category: str = "manual", received_at_utc: datetime | None = None) -> ValidationDecision:
        started = time.perf_counter()
        received_at_utc = received_at_utc or datetime.now(timezone.utc)
        dose_mmol = 0.0
        event_total = self.event_mmol_used.get(str(command.get("event_id", "")), 0.0)

        def finish(decision: str, code: str, detail: str, forwarded: bool = False, model: dict[str, Any] | None = None) -> ValidationDecision:
            model = model or {"label": "NOT_CALLED", "score": 0.0, "latency_ms": 0.0}
            volume = command.get("volume_ml", 0.0)
            volume = float(volume) if isinstance(volume, (int, float)) and not isinstance(volume, bool) else 0.0
            result = ValidationDecision(
                command_id=str(command.get("command_id", "MISSING")),
                category=category,
                decision=decision,
                reason_code=code,
                reason_detail=detail,
                forwarded_to_actuator=forwarded,
                latency_ms=round((time.perf_counter() - started) * 1000.0, 4),
                model_a_label=str(model.get("label", "NOT_CALLED")),
                model_a_score=float(model.get("score", 0.0)),
                model_a_latency_ms=float(model.get("latency_ms", 0.0)),
                channel_id=str(command.get("channel_id", "")),
                volume_ml=volume,
                dose_mmol=round(dose_mmol, 6),
                event_mmol_total=round(event_total, 6),
            )
            self.audit_log.append(
                result.command_id, result.decision, result.reason_code, result.forwarded_to_actuator,
                channel_id=result.channel_id, volume_ml=result.volume_ml, dose_mmol=result.dose_mmol,
                event_mmol_total=result.event_mmol_total,
                model_a_label=result.model_a_label, model_a_score=result.model_a_score,
            )
            return result

        missing = [field for field in REQUIRED_FIELDS if field not in command]
        if missing:
            return finish("REJECT", "SCHEMA_MISSING_FIELD", f"missing required field(s): {', '.join(missing)}")

        type_error = self._first_type_error(command)
        if type_error:
            return finish("REJECT", "SCHEMA_TYPE_ERROR", type_error)

        if command["user_role"] not in self.config.allowed_roles:
            return finish("REJECT", "UNAUTHORIZED_ROLE", f"role {command['user_role']} is not allowed")

        if command["session_id"] != self.config.active_session_id:
            return finish("REJECT", "INVALID_SESSION", "session ID is not active")

        if not is_valid_hmac(command, self.config.hmac_secret):
            return finish("REJECT", "INVALID_HMAC", "HMAC-SHA256 authentication tag does not match")

        try:
            timestamp = datetime.fromisoformat(str(command["timestamp_utc"]).replace("Z", "+00:00"))
        except ValueError:
            return finish("REJECT", "BAD_TIMESTAMP", "timestamp must be ISO-8601 UTC")
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        age_s = (received_at_utc.astimezone(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
        if age_s > self.config.freshness_window_s:
            return finish("REJECT", "STALE_TIMESTAMP", f"command age {age_s:.3f}s exceeds {self.config.freshness_window_s:.1f}s")
        if age_s < -self.config.max_future_skew_s:
            return finish("REJECT", "FUTURE_TIMESTAMP", "timestamp is too far in the future")

        nonce = str(command["nonce"])
        if nonce in self.used_nonces or nonce in self.persisted_used_nonces:
            return finish("REJECT", "REUSED_NONCE", "nonce has already been used")

        sequence_number = int(command["sequence_number"])
        if sequence_number <= self.last_sequence_number:
            return finish("REJECT", "OLD_SEQUENCE", f"sequence must be greater than {self.last_sequence_number}")

        command_id = str(command["command_id"])
        if command_id in self.processed_command_ids or command_id in self.persisted_command_ids:
            return finish("REJECT", "DUPLICATE_COMMAND_ID", "command ID has already been processed")

        if self.state.mode == "SAFE_HOLD":
            return finish("REJECT", "SAFE_HOLD_ACTIVE", "gateway is in SAFE_HOLD")
        if not self.state.heartbeat_healthy:
            return finish("REJECT", "HEARTBEAT_LOSS", "heartbeat from Uno/actuator is not healthy")
        now_s = self.clock()
        if self.lockout_remaining_s(now_s) > 0:
            return finish("REJECT", "MIXING_LOCKOUT", f"{self.state.mixing_lockout_remaining_s:.1f}s remains before next dose")

        dose_error = self._dose_limit_error(command)
        if dose_error:
            return finish("REJECT", "DOSE_LIMIT", dose_error)

        event_id = str(command["event_id"])
        dose_mmol = self.dose_mmol(command)
        limit = self.config.max_recovery_mmol_per_event
        if event_total + dose_mmol > limit + 1e-9:
            return finish("REJECT", "EVENT_MMOL_LIMIT",
                          f"{event_total:.3f} + {dose_mmol:.3f} mmol would exceed {limit:.0f} mmol for event {event_id}")

        model = self.model_a.predict(command, self.state)
        if model["latency_ms"] > self.config.model_a_timeout_ms:
            return finish("REJECT", "MODEL_A_TIMEOUT", "Model A response exceeded timeout", model=model)
        if model["label"] not in self.config.allowed_model_labels:
            return finish("REJECT", "MODEL_A_BLOCK", f"Model A returned {model['label']}", model=model)

        if self.config.require_client_certificate:
            fingerprint = str(command.get("client_cert_fingerprint", ""))
            if fingerprint != self.config.expected_client_cert_fingerprint:
                return finish("REJECT", "BAD_CLIENT_CERT", "client certificate fingerprint is not trusted", model=model)

        self.used_nonces.add(nonce)
        self.persisted_used_nonces.add(nonce)
        self.processed_command_ids.add(command_id)
        self.persisted_command_ids.add(command_id)
        self.last_sequence_number = sequence_number
        self.actuator.forward_from_gateway(command_id)
        if command["action"] in DOSE_ACTIONS:           # only a dose starts a mixing period
            self.state.last_dose_accepted_at_s = now_s
            self.state.mixing_lockout_remaining_s = self.config.min_mixing_time_s
        if dose_mmol > 0.0:
            event_total += dose_mmol
            self.event_mmol_used[event_id] = event_total
            self.state.cumulative_recovery_mmol = event_total

        return finish(
            "ACCEPT",
            "ACCEPTED",
            "fresh, authenticated, unique, ordered, authorized, model-approved, certificate-trusted, and within limits",
            forwarded=True,
            model=model,
        )

    def dose_mmol(self, command: dict[str, Any]) -> float:
        """mmol this command delivers: volume_ml x the channel's molarity. 0 for a HOLD."""
        if command["action"] not in DOSE_ACTIONS:
            return 0.0
        return float(command["volume_ml"]) * self.config.channel_molarity[command["channel_id"]]

    @staticmethod
    def _first_type_error(command: dict[str, Any]) -> str | None:
        string_fields = (
            "session_id", "command_id", "event_id", "timestamp_utc", "nonce", "user_role", "action",
            "channel_id", "recovery_plan_hash", "client_cert_fingerprint", "hmac_sha256",
        )
        for field in string_fields:
            if not isinstance(command.get(field), str):
                return f"field '{field}' must be a string"
        if not isinstance(command.get("schema_version"), int):
            return "field 'schema_version' must be an integer"
        if not isinstance(command.get("sequence_number"), int):
            return "field 'sequence_number' must be an integer"
        for field in ("volume_ml", "flow_ml_min", "mixing_time_s"):
            value = command.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                return f"field '{field}' must be a finite number"
        return None

    def _dose_limit_error(self, command: dict[str, Any]) -> str | None:
        if command["action"] not in {"DOSE", "RECOVERY_DOSE", "HOLD"}:
            return "action is not allowed"
        channels = self.config.channel_molarity
        if command["action"] in DOSE_ACTIONS:
            if command["channel_id"] not in channels:
                return f"channel_id must be one of {', '.join(sorted(channels))}"
            if float(command["volume_ml"]) <= 0:
                return "a dose must be more than 0 mL"
        elif command["channel_id"] not in channels and command["channel_id"] != NO_CHANNEL:
            return f"channel_id must be one of {', '.join(sorted(channels))} or {NO_CHANNEL}"
        if float(command["volume_ml"]) < 0:
            return "volume must not be negative"
        if float(command["volume_ml"]) > self.config.max_volume_ml:
            return f"volume {command['volume_ml']} mL exceeds {self.config.max_volume_ml} mL"
        if float(command["flow_ml_min"]) > self.config.max_flow_ml_min:
            return f"flow {command['flow_ml_min']} mL/min exceeds {self.config.max_flow_ml_min} mL/min"
        if command["action"] != "HOLD" and float(command["mixing_time_s"]) < self.config.min_mixing_time_s:
            return f"mixing time {command['mixing_time_s']} s is below {self.config.min_mixing_time_s} s"
        return None
