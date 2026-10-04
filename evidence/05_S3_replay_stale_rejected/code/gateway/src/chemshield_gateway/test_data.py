from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Iterator

from .auth import attach_hmac
from .config import GatewayConfig


class ManualClock:
    """A gateway clock the tests move by hand (seconds)."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


def iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def unsigned_command(
    config: GatewayConfig,
    *,
    command_id: str,
    event_id: str,
    timestamp_utc: datetime,
    nonce: str,
    sequence_number: int,
    session_id: str | None = None,
    user_role: str = "operator",
    action: str = "RECOVERY_DOSE",
    channel_id: str = "BASE_BULK",
    volume_ml: float = 12.0,
    flow_ml_min: float = 300.0,
    mixing_time_s: float = 15.0,
    recovery_plan_hash: str = "sha256:demo_recovery_plan_v1",
    client_cert_fingerprint: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "session_id": session_id or config.active_session_id,
        "command_id": command_id,
        "event_id": event_id,
        "timestamp_utc": iso(timestamp_utc),
        "nonce": nonce,
        "sequence_number": sequence_number,
        "user_role": user_role,
        "action": action,
        "channel_id": channel_id,
        "volume_ml": volume_ml,
        "flow_ml_min": flow_ml_min,
        "mixing_time_s": mixing_time_s,
        "recovery_plan_hash": recovery_plan_hash,
        "client_cert_fingerprint": client_cert_fingerprint or config.expected_client_cert_fingerprint,
    }


def make_command(config: GatewayConfig, **kwargs: Any) -> dict[str, Any]:
    return attach_hmac(unsigned_command(config, **kwargs), config.hmac_secret)


def generate_attack_categories(config: GatewayConfig, now: datetime, per_category: int = 1000) -> Iterator[tuple[str, dict[str, Any]]]:
    for i in range(1, per_category + 1):
        yield "valid", make_command(
            config,
            command_id=f"CMD-VALID-{i:04d}",
            event_id=f"EVT-NOM-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-VALID-{i:04d}",
            sequence_number=i,
            channel_id="BASE_BULK" if i % 2 else "ACID_BULK",
            volume_ml=10.0 + (i % 4),
        )

    for i in range(1, per_category + 1):
        yield "replay", make_command(
            config,
            command_id=f"CMD-VALID-{i:04d}",
            event_id=f"EVT-NOM-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-VALID-{i:04d}",
            sequence_number=i,
            channel_id="BASE_BULK" if i % 2 else "ACID_BULK",
            volume_ml=10.0 + (i % 4),
        )

    for i in range(1, per_category + 1):
        yield "stale", make_command(
            config,
            command_id=f"CMD-STALE-{i:04d}",
            event_id=f"EVT-STL-{i:04d}",
            timestamp_utc=now - timedelta(seconds=45),
            nonce=f"N-STALE-{i:04d}",
            sequence_number=per_category + i,
        )

    for i in range(1, per_category + 1):
        yield "reused_nonce", make_command(
            config,
            command_id=f"CMD-RNONCE-{i:04d}",
            event_id=f"EVT-RN-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-VALID-{i:04d}",
            sequence_number=per_category + i,
        )

    for i in range(1, per_category + 1):
        yield "out_of_order_sequence", make_command(
            config,
            command_id=f"CMD-OLDSEQ-{i:04d}",
            event_id=f"EVT-SEQ-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-OLDSEQ-{i:04d}",
            sequence_number=i,
        )

    for i in range(1, per_category + 1):
        cmd = make_command(
            config,
            command_id=f"CMD-HMAC-{i:04d}",
            event_id=f"EVT-HM-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-HMAC-{i:04d}",
            sequence_number=per_category + i,
        )
        cmd["volume_ml"] = 18.0
        yield "invalid_hmac", cmd

    for i in range(1, per_category + 1):
        cmd = unsigned_command(
            config,
            command_id=f"CMD-UNSIGNED-{i:04d}",
            event_id=f"EVT-UN-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-UNSIGNED-{i:04d}",
            sequence_number=per_category + i,
        )
        cmd["hmac_sha256"] = ""
        yield "unsigned", cmd

    for i in range(1, per_category + 1):
        yield "oversize", make_command(
            config,
            command_id=f"CMD-OVERSIZE-{i:04d}",
            event_id=f"EVT-OV-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-OVERSIZE-{i:04d}",
            sequence_number=per_category + i,
            volume_ml=25.0,
        )

    for i in range(1, per_category + 1):
        yield "wrong_role_or_session", make_command(
            config,
            command_id=f"CMD-WRONG-{i:04d}",
            event_id=f"EVT-WR-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-WRONG-{i:04d}",
            sequence_number=per_category + i,
            user_role="viewer" if i % 2 else "operator",
            session_id=config.active_session_id if i % 2 else "OLD-SESSION",
        )

    for i in range(1, per_category + 1):
        cmd = make_command(
            config,
            command_id=f"CMD-BAD-{i:04d}",
            event_id=f"EVT-BAD-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-BAD-{i:04d}",
            sequence_number=per_category + i,
        )
        if i % 2:
            cmd.pop("nonce")
        else:
            cmd["sequence_number"] = "not-an-integer"
        yield "malformed", cmd

    for i in range(1, per_category + 1):
        yield "replayed_after_reboot", make_command(
            config,
            command_id=f"CMD-VALID-{i:04d}",
            event_id=f"EVT-NOM-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-VALID-{i:04d}",
            sequence_number=per_category + i,
        )

    for i in range(1, per_category + 1):
        yield "gateway_bypass_attempt", {"command_id": f"CMD-BYPASS-{i:04d}", "attempt": "direct_actuator_write_without_gateway"}

    for i in range(1, per_category + 1):
        yield "burst_during_lockout", make_command(
            config,
            command_id=f"CMD-BURST-{i:04d}",
            event_id=f"EVT-BURST-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-BURST-{i:04d}",
            sequence_number=per_category + i,
        )

    for i in range(1, per_category + 1):
        yield "bad_certificate", make_command(
            config,
            command_id=f"CMD-CERT-{i:04d}",
            event_id=f"EVT-CERT-{i:04d}",
            timestamp_utc=now,
            nonce=f"N-CERT-{i:04d}",
            sequence_number=per_category + i,
            client_cert_fingerprint="UNTRUSTED-CERT",
        )
