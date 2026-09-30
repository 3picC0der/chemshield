"""Make the operator key: one random secret shared by the laptop HMI and the Pi station.

    .venv/bin/python -m hmi.keygen            writes hmi/secrets/operator.key

Copy the same file to the Pi (same path in the repo there), for example:
    scp hmi/secrets/operator.key <user>@<pi-ip>:~/chemshield/hmi/secrets/operator.key
The folder is git-ignored. Never commit or share the key.
"""
from __future__ import annotations

import secrets
import sys

from hmi.common import KEY_FILE


def main() -> int:
    if KEY_FILE.exists() and "--force" not in sys.argv:
        print(f"{KEY_FILE} already exists (use --force to replace it; then copy it to the Pi again)")
        return 1
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(secrets.token_hex(32) + "\n", encoding="utf-8")
    KEY_FILE.chmod(0o600)
    print(f"wrote {KEY_FILE}. Copy this file to the Pi at the same path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
