from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR / "src"))

from chemshield_gateway.config import GatewayConfig
from chemshield_gateway.gateway_validator import GatewayValidator
from chemshield_gateway.test_data import make_command


def show(name: str, result) -> None:
    print(f"{name:<28} {result.decision:<7} {result.reason_code:<22} forwarded={result.forwarded_to_actuator}")


def main() -> None:
    config = GatewayConfig()
    gateway = GatewayValidator(config=config)
    now = datetime.now(timezone.utc)

    print("\n=== ChemShield sample gateway decisions ===")
    print(f"{'Case':<28} {'Decision':<7} {'Reason':<22} Forwarded")

    valid = make_command(config, command_id="SAMPLE-VALID-001", event_id="EVT-SAMPLE", timestamp_utc=now, nonce="NONCE-SAMPLE-001", sequence_number=1)
    show("Valid command", gateway.validate(valid, category="sample", received_at_utc=now))

    replay = make_command(config, command_id="SAMPLE-VALID-001", event_id="EVT-SAMPLE", timestamp_utc=now, nonce="NONCE-SAMPLE-001", sequence_number=1)
    show("Replay same command", gateway.validate(replay, category="sample", received_at_utc=now))

    stale = make_command(config, command_id="SAMPLE-STALE-001", event_id="EVT-SAMPLE", timestamp_utc=now - timedelta(seconds=45), nonce="NONCE-SAMPLE-STALE", sequence_number=2)
    show("Stale command", gateway.validate(stale, category="sample", received_at_utc=now))

    oversize = make_command(config, command_id="SAMPLE-OVERSIZE-001", event_id="EVT-SAMPLE", timestamp_utc=now, nonce="NONCE-SAMPLE-OVERSIZE", sequence_number=2, volume_ml=25.0)
    show("Oversize 25 mL", gateway.validate(oversize, category="sample", received_at_utc=now))

    bypass_ok = gateway.actuator.direct_write_attempt("SAMPLE-BYPASS-001")
    print(f"{'Direct bypass attempt':<28} {'ACCEPT' if bypass_ok else 'REJECT':<7} {'BYPASS_BLOCKED':<22} forwarded={bypass_ok}")


if __name__ == "__main__":
    main()
