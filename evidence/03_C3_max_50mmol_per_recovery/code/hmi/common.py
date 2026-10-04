"""Things the laptop HMI and the Pi station must agree on.

The laptop HMI signs; the Pi station (gateway + Model A + recovery + Uno link) decides.
Both import this file so the key, the command format and the reason words can't drift.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
GATEWAY_SRC = ROOT / "gateway" / "src"
if str(GATEWAY_SRC) not in sys.path:
    sys.path.insert(0, str(GATEWAY_SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from chemshield_gateway.auth import attach_hmac, is_valid_hmac  # noqa: E402
from chemshield_gateway.config import GatewayConfig  # noqa: E402

# ------------------------------------------------------------------ network
# The Pi station listens on the port the firewall template opens
# (gateway/firewall/raspberry_pi_firewall_template.sh reads the same variable).
STATION_PORT = int(os.environ.get("CHEMSHIELD_HMI_PORT", "8000"))
# The laptop HMI only ever listens on the laptop itself (127.0.0.1), never on the Wi-Fi.
HMI_PORT = int(os.environ.get("CHEMSHIELD_LAPTOP_PORT", "8080"))

# ------------------------------------------------------------------ the key
# The operator key is shared by the laptop HMI (which signs) and the Pi (which checks).
# Generate one with `python -m hmi.keygen`, copy the file to the Pi, and never commit it.
KEY_FILE = Path(os.environ.get("CHEMSHIELD_KEY_FILE", str(ROOT / "hmi" / "secrets" / "operator.key")))
DEMO_SECRET = GatewayConfig().hmac_secret     # Khalid's placeholder; fine on one laptop only


def load_secret() -> tuple[str, str]:
    """(secret, where it came from). Env var first, then the key file, then the placeholder."""
    env = os.environ.get("CHEMSHIELD_HMAC_SECRET", "").strip()
    if env:
        return env, "CHEMSHIELD_HMAC_SECRET"
    if KEY_FILE.exists():
        text = KEY_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text, str(KEY_FILE)
    return DEMO_SECRET, "built-in demo key (run python -m hmi.keygen before the PPR)"


def gateway_config(secret: str | None = None) -> GatewayConfig:
    """Khalid's GatewayConfig with the real key, identical on both sides."""
    return GatewayConfig(hmac_secret=secret if secret is not None else load_secret()[0])


# ------------------------------------------------------------------ bottles
# I1 channel ids. Pump numbers are I5's 1-4, in sim/model.py PUMPS order.
CHANNELS: dict[str, dict[str, Any]] = {
    "BASE_BULK": {"pump": 1, "molarity": 0.5, "words": "NaOH 0.5 M bulk", "short": "base, bulk"},
    "BASE_FINE": {"pump": 2, "molarity": 0.005, "words": "NaOH 0.005 M fine", "short": "base, fine"},
    "ACID_BULK": {"pump": 3, "molarity": 0.5, "words": "HCl 0.5 M bulk", "short": "acid, bulk"},
    "ACID_FINE": {"pump": 4, "molarity": 0.005, "words": "HCl 0.005 M fine", "short": "acid, fine"},
}

# ------------------------------------------------------------------ reason codes
# Khalid's gateway reason codes -> the group the test sheets count and the words the
# operator reads. The HMI never shows a bare code without its words.
REASONS: dict[str, tuple[str, str]] = {
    "ACCEPTED": ("ACCEPT", "Accepted by the gateway"),
    "REUSED_NONCE": ("REPLAY", "Replayed command: this one-time number was already used"),
    "DUPLICATE_COMMAND_ID": ("REPLAY", "Replayed command: this command ID was already processed"),
    "OLD_SEQUENCE": ("REPLAY", "Out-of-order command: its sequence number is too old"),
    "STALE_TIMESTAMP": ("STALE", "Stale command: sent more than 2 s ago"),
    "FUTURE_TIMESTAMP": ("STALE", "Command is dated in the future"),
    "BAD_TIMESTAMP": ("SCHEMA", "The timestamp is not a valid time"),
    "DOSE_LIMIT": ("LIMIT", "Over the dose limit (20 mL per dose)"),
    "EVENT_MMOL_LIMIT": ("LIMIT", "Would take this event over the 50 mmol reagent limit"),
    "MIXING_LOCKOUT": ("LOCKOUT", "Tank still mixing: 15 s must pass between doses"),
    "MODEL_A_BLOCK": ("MODEL_A_BLOCK", "Model A judged this dose unsafe for the tank right now"),
    "MODEL_A_TIMEOUT": ("MODEL_A_BLOCK", "Model A did not answer in time, so the dose is blocked"),
    "INVALID_HMAC": ("AUTH", "Not signed with the operator key"),
    "MISSING_SIGNATURE": ("AUTH", "Not signed: the command carries no signature"),
    "BAD_CLIENT_CERT": ("AUTH", "Sender's certificate is not trusted"),
    "UNAUTHORIZED_ROLE": ("AUTH", "This role may not send doses"),
    "INVALID_SESSION": ("AUTH", "Unknown or expired operator session"),
    "SCHEMA_MISSING_FIELD": ("SCHEMA", "The command is missing a required field"),
    "SCHEMA_TYPE_ERROR": ("SCHEMA", "A field in the command has the wrong type"),
    "SAFE_HOLD_ACTIVE": ("STATE", "Dosing is halted: press RESUME to allow doses again"),
    "HEARTBEAT_LOSS": ("STATE", "No heartbeat from the Uno: dosing is blocked"),
    "DOSE_PENDING": ("STATE", "A dose is still waiting to be added: finish or cancel it first"),
    "EVENT_MISMATCH": ("STATE", "The tank state changed while you were sending: request again"),
}
GROUP_WORDS = {
    "REPLAY": "Replayed", "STALE": "Stale", "LIMIT": "Over limit", "LOCKOUT": "Mixing lockout",
    "MODEL_A_BLOCK": "Model A block", "AUTH": "Not authorised", "SCHEMA": "Malformed",
    "STATE": "Wrong state", "ACCEPT": "Accepted",
}


def reason_group(code: str) -> str:
    return REASONS.get(code, ("OTHER", code))[0]


def reason_words(code: str) -> str:
    return REASONS.get(code, ("OTHER", code.replace("_", " ").capitalize()))[1]


# ------------------------------------------------------------------ time
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_ms(ts: datetime | float | None = None) -> str:
    if ts is None:
        ts = utc_now()
    if isinstance(ts, (int, float)):
        ts = datetime.fromtimestamp(ts, timezone.utc)
    return ts.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ------------------------------------------------------------------ commands
def new_dose_command(config: GatewayConfig, *, channel_id: str, volume_ml: float, event_id: str,
                     sequence_number: int, source: str = "HMI", action: str = "DOSE",
                     role: str = "operator", flow_ml_min: float = 120.0,
                     plan_hash: str = "manual", age_s: float = 0.0) -> dict[str, Any]:
    """A signed I1 dose request in the format Khalid's gateway checks.

    age_s > 0 back-dates the timestamp (only the security test panel does that, to show
    the gateway rejecting a stale command)."""
    ts = utc_now() - timedelta(seconds=age_s)
    command = {
        "schema_version": 1,
        "session_id": config.active_session_id,
        "command_id": f"{source}-{uuid.uuid4().hex[:10]}",
        "event_id": event_id,
        "timestamp_utc": iso_ms(ts),
        "nonce": uuid.uuid4().hex,
        "sequence_number": int(sequence_number),
        "user_role": role,
        "action": action,
        "channel_id": channel_id,
        "volume_ml": float(volume_ml),
        "flow_ml_min": float(flow_ml_min),
        "mixing_time_s": float(config.min_mixing_time_s),
        "recovery_plan_hash": plan_hash,
        "client_cert_fingerprint": config.expected_client_cert_fingerprint,
    }
    return attach_hmac(command, config.hmac_secret)


def new_operator_action(secret: str, action: str, args: dict[str, Any] | None = None,
                        operator: str = "operator") -> dict[str, Any]:
    """A signed operator action (HALT, RESUME, dose added, ...). Same HMAC as I1."""
    body = {"kind": "operator_action", "action": action, "args": args or {},
            "operator": operator, "timestamp_utc": iso_ms(), "nonce": uuid.uuid4().hex}
    return attach_hmac(body, secret)


def check_operator_action(body: dict[str, Any], secret: str, seen_nonces: set[str],
                          freshness_s: float = 5.0) -> str | None:
    """None if the action is signed, fresh and new; otherwise the reason it is refused."""
    if not isinstance(body, dict) or body.get("kind") != "operator_action":
        return "SCHEMA_MISSING_FIELD"
    if not is_valid_hmac(body, secret):
        return "INVALID_HMAC"
    try:
        ts = datetime.fromisoformat(str(body.get("timestamp_utc", "")).replace("Z", "+00:00"))
    except ValueError:
        return "BAD_TIMESTAMP"
    age = (utc_now() - ts).total_seconds()
    if age > freshness_s:
        return "STALE_TIMESTAMP"
    if age < -freshness_s:
        return "FUTURE_TIMESTAMP"
    nonce = str(body.get("nonce", ""))
    if not nonce or nonce in seen_nonces:
        return "REUSED_NONCE"
    seen_nonces.add(nonce)
    return None


def next_sequence(last_seen: int) -> int:
    """Sequence numbers are milliseconds since 1970, and always above the last one the
    station reported, so the laptop and the Pi's recovery loop never collide."""
    return max(int(time.time() * 1000), int(last_seen) + 1)
