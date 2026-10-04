from __future__ import annotations

import json
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
sys.path.insert(0, str(THIS_DIR / "src"))

from chemshield_gateway.c2_path_test import run_c2_gateway_only_path_test
from chemshield_gateway.security_test_runner import run_security_test
from chemshield_gateway.failsafe import run_failsafe_tests
from chemshield_gateway.recovery_timing import run_int_s1_timing
from chemshield_gateway.plots import plot_security_summary, plot_failsafe_summary, draw_network_trust_boundary


def main() -> None:
    evidence_dir = REPO_ROOT / "evidence" / "_archive_gateway_in_process_tests_30Sep"
    plots_dir = evidence_dir / "plots"
    reports_dir = evidence_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("\n=== ChemShield Khalid ICS Runner ===")
    print("Running C2 gateway-only path test...")
    c2 = run_c2_gateway_only_path_test(evidence_dir)

    print("Running S3/security attack test...")
    security = run_security_test(evidence_dir, per_category=1000)
    security_plot = plot_security_summary(security, plots_dir)

    print("Running fail-safe tests...")
    failsafe = run_failsafe_tests(evidence_dir)
    failsafe_plot = plot_failsafe_summary(failsafe, plots_dir)

    print("Running INT-S1 recovery timing support test...")
    int_s1 = run_int_s1_timing(evidence_dir, events_count=100)

    print("Drawing network/trust-boundary diagram...")
    network_diagram = draw_network_trust_boundary(plots_dir)

    summary = {
        "c2_gateway_only_path": c2,
        "security": security,
        "failsafe": failsafe,
        "int_s1": int_s1,
        "artifacts": {
            "security_plot": security_plot,
            "failsafe_plot": failsafe_plot,
            "network_diagram": network_diagram,
        },
    }
    summary_path = reports_dir / "khalid_ics_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\n--- Final PASS/FAIL Summary ---")
    print(f"C2 gateway-only path: {c2['pass_fail']}")
    print(f"Security test: {security['pass_fail']}")
    print(f"Replay/stale rejection: {security['replay_stale_rejection_rate_percent']}% (target >=99%)")
    print(f"Valid command acceptance: {security['valid_command_acceptance_rate_percent']}%")
    print(f"Malicious commands reaching actuator: {security['malicious_commands_reaching_actuator']}")
    print(f"Audit hash chain valid: {security['audit_log_hash_chain_valid']}")
    print(f"Fail-safe tests: {failsafe['pass_fail']}")
    print(f"INT-S1 timing support: {int_s1['pass_fail']} (max {int_s1['max_elapsed_s']} s)")
    print("\nGenerated files written to:")
    print(f"  {evidence_dir}")


if __name__ == "__main__":
    main()
