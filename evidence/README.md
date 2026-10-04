# ChemShield evidence (Team M016, KFUPM Senior Design, PPR 5 Oct 2026)

One folder per constraint or specification. Each has the filled test sheet, the raw data, the plots and the code behind it, so a result can be read next to the numbers and the program that produced it.

## Start here

| Read | What it gives you |
|---|---|
| **[ATTAINMENT_TABLE.md](ATTAINMENT_TABLE.md)** | Every constraint and specification with its result: `MET = x`, or what is still open |
| **[EVIDENCE_EXPLAINED.md](EVIDENCE_EXPLAINED.md)** | For each item: what was tested, the setup, the result and how it is proven. The ICS items (C2, Spec 3, Spec 4) in depth |
| **[SETUP.md](SETUP.md)** | Build the Raspberry Pi rig, start it, reset it, rerun INT-Spec 1, and the step-by-step demo |

## The folders

The first nine are the PPR list, in order. Folders starting with `EXTRA_` are specifications that were not on that list but that we also have evidence for.

| Folder | Item | Result |
|---|---|---|
| [01_C1_approved_dilute_reagents](01_C1_approved_dilute_reagents/) | **C1** · only approved dilute reagents, at most 5 wt% | **MET = 1.96 wt%** |
| [02_C2_gateway_sole_control_path](02_C2_gateway_sole_control_path/) | **C2** · the gateway is the sole control path | **MET = 8 of 8 checks, twice** |
| [03_C3_max_50mmol_per_recovery](03_C3_max_50mmol_per_recovery/) | **C3** · at most 50 mmol of reagent per recovery | **MET = 41.7 mmol** at most |
| [04_S1_ph_hold_10min](04_S1_ph_hold_10min/) | **Spec 1** · pH 6.5 to 7.5 held for 10 minutes | NOT YET TESTED |
| [05_S3_replay_stale_rejected](05_S3_replay_stale_rejected/) | **Spec 3** · at least 99% of replayed or stale commands rejected | **MET = 100%** (2,000 of 2,000) |
| [06_S4_class_and_score_within_3s](06_S4_class_and_score_within_3s/) | **Spec 4** · event class and risk score within 3 s | **MET = 1.65 ms** |
| [07_S5_sus_at_least_80](07_S5_sus_at_least_80/) | **Spec 5** · usability score of at least 80 | DATA PENDING |
| [08_S7_pump_max_flow](08_S7_pump_max_flow/) | **Spec 7** · pump rated at most 500 mL/min | **MET = 65 mL/min** (rated) |
| [09_INT-S1_recovery_mode_within_2s](09_INT-S1_recovery_mode_within_2s/) | **INT-Spec 1** · recovery mode within 2 s | **MET = 1.1 ms** |
| [EXTRA_S2_dose_cap_and_mixing_wait](EXTRA_S2_dose_cap_and_mixing_wait/) | Spec 2 · dose at most 20 mL, 15 s mixing wait | MET |
| [EXTRA_S6_recovery_within_300s](EXTRA_S6_recovery_within_300s/) | Spec 6 · 95% of recoveries within 300 s | **MET = 100%** (simulation) |
| [EXTRA_INT-S2_ph_restored_within_5min](EXTRA_INT-S2_ph_restored_within_5min/) | INT-Spec 2 · pH back in 6.0 to 8.5 within 5 min | **MET = 600 of 600** (simulation) |
| [EXTRA_INT-S3_no_far_side_excursion](EXTRA_INT-S3_no_far_side_excursion/) | INT-Spec 3 · no overshoot past pH 5.5 or 9.5 | **MET = 100%** (simulation) |

## What is inside each folder

| Part | Contents |
|---|---|
| `TEST_SHEET.md` | The test sheet: the spec in full, the procedure step by step, the result, and the verdict |
| `data/` | The raw files: CSVs, audit logs (hash-chained), tool output, unit-test output, photos |
| `plots/` | The graphs made from the data |
| `code/` | The code behind the result, at its repository path (`code/gateway/...`, `code/model_a/...`), and `code/SOURCE.md` listing the files and the commit they were copied from. Scripts made only for the evidence sit directly in `code/` |

The running system uses the originals in the repository root (`gateway/`, `model_a/`, `redosing/`, `sim/`, `hmi/`, `firmware/`). Refresh the copies with `python evidence/tools/refresh_code_snapshots.py` after changing any of them.

## Things to know when reading

- Times are UTC. A "run" folder is named for its date: `rig_run_4Oct` is the live rig on 4 Oct 2026.
- Audit logs (`audit.jsonl`) are hash-chained; `python -m hmi.verify_log <file>` prints `CHAIN OK` or `CHAIN BROKEN`.
- The simulated results use a placeholder pH table of the baking-soda water until the Aspen export arrives; every file says `chem_source = PLACEHOLDER`.
- Items with open pieces (approval scan, datasheet page, SUS forms, the 10-minute hold, a live recovery on the 5 L tank) say so in their test sheet and in the [attainment table](ATTAINMENT_TABLE.md#what-is-still-open).
- [`_archive_gateway_in_process_tests_30Sep`](_archive_gateway_in_process_tests_30Sep/) holds the gateway's first tests, from before the rig existed. They are not the primary evidence for any item.
