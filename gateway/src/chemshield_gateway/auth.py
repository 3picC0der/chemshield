from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any


HMAC_FIELD = "hmac_sha256"


def canonical_payload(command: dict[str, Any]) -> str:
    """Return the deterministic JSON payload used for HMAC signing."""
    body = dict(command)
    body.pop(HMAC_FIELD, None)
    return json.dumps(body, sort_keys=True, separators=(",", ":"))


def sign_command(command: dict[str, Any], secret: str) -> str:
    payload = canonical_payload(command).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def attach_hmac(command: dict[str, Any], secret: str) -> dict[str, Any]:
    signed = dict(command)
    signed[HMAC_FIELD] = sign_command(signed, secret)
    return signed


def is_valid_hmac(command: dict[str, Any], secret: str) -> bool:
    supplied = str(command.get(HMAC_FIELD, ""))
    expected = sign_command(command, secret)
    return hmac.compare_digest(supplied, expected)
