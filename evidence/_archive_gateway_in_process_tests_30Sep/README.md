# Archive: the gateway's in-process tests (30 Sep 2026)

Khalid's first tests of the gateway, made by `python gateway/run_all.py`. They run the gateway code inside one Python process, with a simulated actuator and made-up commands, before the Raspberry Pi and the Uno were set up. They are kept for reference. **They are not the primary evidence for any specification.** Each spec's own folder has the tests on the real station and the real rig:

| Spec | Primary evidence |
|---|---|
| C2 | [02_C2_gateway_sole_control_path](../02_C2_gateway_sole_control_path/): 8 checks on the Pi, twice |
| Spec 3 | [05_S3_replay_stale_rejected](../05_S3_replay_stale_rejected/): the real station attacked over HTTP (a copy of the 14,000-command run is in its `data/in_process_gateway_test_30Sep/`) |
| INT-Spec 1 | [09_INT-S1_recovery_mode_within_2s](../09_INT-S1_recovery_mode_within_2s/): the live rig on 4 Oct |

| File | What it is |
|---|---|
| `raw/c2_gateway_only_path_results.csv` | Three cases: the gateway path is accepted and forwarded; two direct attempts to reach the actuator without the gateway are blocked. Against a simulated actuator, so it shows the logic, not the network |
| `raw/security_test_commands.csv`, `reports/security_test_summary.csv`, `raw/hash_chained_audit_log.jsonl` | 14,000 commands (14 attack types of 1,000 each, and 1,000 valid): replays and stale commands rejected 100%, valid ones accepted, none of the malicious ones forwarded, the audit chain valid |
| `raw/failsafe_results.csv` | Five fail-safe cases (cable disconnection, heartbeat loss, gateway shutdown, PLC reboot, corrupted message): dosing blocked at once, SAFE_HOLD within 1.05 s |
| `raw/int_s1_recovery_timing.csv` | 100 recovery events in three stages each, in process. Superseded by the live rig run and the 100-event run through the real station and HMI |
| `plots/` | The trust-boundary diagram, the security-test summary and the fail-safe summary |
| `reports/khalid_ics_summary.json` | All of the above in one file. The file paths written inside it are from the machine that produced it |

To make them again: `python gateway/run_all.py` (it overwrites this folder).
