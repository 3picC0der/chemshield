from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayConfig:
    """Configuration used by Khalid's gateway tests.

    Lab values such as the real HMAC secret, Pi interface names, PLC/Uno IP,
    and protocol port must be replaced before the real hardware demo.
    """

    active_session_id: str = "S-261-KHALID-PPR"
    hmac_secret: str = "CHANGE_THIS_FOR_REAL_DEMO"
    allowed_roles: tuple[str, ...] = ("operator", "engineer", "supervisor")
    freshness_window_s: float = 2.0
    max_future_skew_s: float = 2.0

    max_volume_ml: float = 20.0
    max_flow_ml_min: float = 500.0
    min_mixing_time_s: float = 15.0
    max_recovery_mmol_per_event: float = 50.0

    heartbeat_timeout_s: float = 1.0
    safe_hold_deadline_s: float = 2.0

    require_client_certificate: bool = True
    expected_client_cert_fingerprint: str = "CERT-KHALID-DEMO"

    model_a_timeout_ms: float = 100.0
    allowed_model_labels: tuple[str, ...] = ("ACCEPTABLE_CONTEXT",)
