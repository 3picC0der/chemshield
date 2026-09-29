from __future__ import annotations

import argparse
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(THIS_DIR / "src"))

from chemshield_gateway.security_test_runner import run_security_test


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ChemShield gateway attack script for S3/C2 tests.")
    parser.add_argument("--per-category", type=int, default=1000, help="Number of commands per attack category")
    args = parser.parse_args()
    output_dir = REPO_ROOT / "evidence" / "generated"
    result = run_security_test(output_dir, per_category=args.per_category)
    print("\n=== ChemShield Attack Script Summary ===")
    print(f"Total commands: {result['total_commands']}")
    print(f"Replay/stale rejection: {result['replay_stale_rejection_rate_percent']}%")
    print(f"Valid acceptance: {result['valid_command_acceptance_rate_percent']}%")
    print(f"Malicious commands reaching actuator: {result['malicious_commands_reaching_actuator']}")
    print(f"PASS/FAIL: {result['pass_fail']}")
    print(f"CSV: {result['raw_csv']}")


if __name__ == "__main__":
    main()
