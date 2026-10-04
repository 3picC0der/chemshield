"""Copy the code each spec depends on into that spec's evidence folder (code/).

    python evidence/tools/refresh_code_snapshots.py

Each evidence folder has a code/ directory holding a snapshot of the source files behind that
spec, at their repo-relative paths (code/gateway/src/..., code/model_a/..., and so on), plus
code/SOURCE.md that lists them and the commit they were taken from. The live code stays where it
always was; the snapshot is there so a reviewer can read the code next to the test sheet.
Scripts that exist only for the evidence (the plot and extraction scripts) are left alone.
Re-run this after changing any listed file, then commit.
"""
from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EV = os.path.join(ROOT, "evidence")

GATEWAY = ["gateway/src/chemshield_gateway/*.py"]
STATION_TESTS = ["hmi/tests/test_station.py", "hmi/tests/helpers.py"]   # the unit tests the sheets cite
REDOSING_SIM = ["sim/*.py", "sim/README.md", "sim/tests/*.py", "sim/aspen_tables/README.md",
                "redosing/*.py", "redosing/README.md", "redosing/qc/*.py"]

MAPPING: dict[str, list[str]] = {
    "01_C1_approved_dilute_reagents": [
        "gateway/src/chemshield_gateway/config.py", "hmi/common.py"],
    "02_C2_gateway_sole_control_path": GATEWAY + [
        "gateway/firewall/*", "gateway/threat_model.md", "gateway/README.md",
        "hmi/c2_check.py", "hmi/common.py", "hmi/station/server.py", "gateway/systemd/*",
        "gateway/tests/test_firewall_template.py", "gateway/tests/test_systemd_autostart.py",
        "hmi/tests/test_c2_check.py"] + STATION_TESTS,
    "03_C3_max_50mmol_per_recovery": [
        "gateway/src/chemshield_gateway/gateway_validator.py", "gateway/src/chemshield_gateway/config.py",
        "gateway/tests/test_event_mmol.py", "hmi/station/core.py", "hmi/common.py"] + STATION_TESTS + REDOSING_SIM,
    "04_S1_ph_hold_10min": [
        "hmi/station/core.py", "hmi/station/links.py", "hmi/common.py",
        "firmware/uno/chemshield_uno/*", "firmware/uno/uno_tool.py", "firmware/uno/README.md"] + STATION_TESTS,
    "05_S3_replay_stale_rejected": GATEWAY + [
        "gateway/attack_script.py", "gateway/tests/test_event_mmol.py", "gateway/tests/test_mixing_lockout.py",
        "hmi/attack_station.py", "hmi/verify_log.py",
        "hmi/station/audit.py", "hmi/station/core.py", "hmi/common.py"] + STATION_TESTS,
    "06_S4_class_and_score_within_3s": [
        "model_a/*.py", "model_a/README.md", "model_a/tests/*.py", "model_a/artifacts/MODEL_CARD.md",
        "model_a/artifacts/evidence.json", "model_a/data/DATASET_CARD.md", "model_a/data/manifest.json",
        "gateway/src/chemshield_gateway/model_a_client.py", "gateway/src/chemshield_gateway/gateway_validator.py"] + STATION_TESTS,
    "07_S5_sus_at_least_80": [
        "hmi/__init__.py", "hmi/__main__.py", "hmi/app.py", "hmi/common.py", "hmi/demo.py", "hmi/facilitator.py",
        "hmi/static/*", "hmi/DESIGN.md", "hmi/wireframe.html", "hmi/README.md"],
    "08_S7_pump_max_flow": [],
    "09_INT-S1_recovery_mode_within_2s": [
        "hmi/station/*.py", "hmi/common.py", "hmi/int_s1_batch.py", "hmi/mock_uno.py",
        "firmware/uno/chemshield_uno/*", "firmware/uno/uno_tool.py"] + STATION_TESTS,
    "EXTRA_S2_dose_cap_and_mixing_wait": [
        "gateway/src/chemshield_gateway/gateway_validator.py", "gateway/src/chemshield_gateway/config.py",
        "gateway/tests/test_mixing_lockout.py", "hmi/station/core.py"] + STATION_TESTS,
    "EXTRA_S6_recovery_within_300s": REDOSING_SIM,
    "EXTRA_INT-S2_ph_restored_within_5min": REDOSING_SIM,
    "EXTRA_INT-S3_no_far_side_excursion": REDOSING_SIM,
}
SKIP_SUFFIX = (".pyc", ".csv", ".gz", ".joblib", ".png", ".docx")


def expand(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for pat in patterns:
        for path in sorted(glob.glob(os.path.join(ROOT, pat))):
            if os.path.isfile(path) and not path.endswith(SKIP_SUFFIX) and "__pycache__" not in path:
                rel = os.path.relpath(path, ROOT)
                if rel not in out:
                    out.append(rel)
    return out


def main() -> int:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True).stdout.strip() or "unknown"
    all_mirrored = {rel for pats in MAPPING.values() for rel in expand(pats)}
    for folder, patterns in MAPPING.items():
        code = os.path.join(EV, folder, "code")
        os.makedirs(code, exist_ok=True)
        # clear the previous mirrored copies (not the evidence-only scripts that live here)
        for rel in all_mirrored:
            old = os.path.join(code, rel)
            if os.path.isfile(old):
                os.remove(old)
        files = expand(patterns)
        for rel in files:
            dst = os.path.join(code, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), dst)
        # remove empty directories left behind
        for dirpath, dirnames, filenames in os.walk(code, topdown=False):
            if dirpath != code and not os.listdir(dirpath):
                os.rmdir(dirpath)
        own = sorted(
            os.path.relpath(os.path.join(d, f), code)
            for d, _dirs, fs in os.walk(code) for f in fs
            if f != "SOURCE.md" and os.path.relpath(os.path.join(d, f), code) not in files)
        lines = [f"# Code behind this spec (snapshot of commit `{commit}`)", ""]
        if files:
            lines += ["These files are copies of the live code at the repo-relative path shown; read them here next to",
                      "the test sheet. The running system uses the originals in the repo root.", ""]
            lines += [f"- `{rel}`" for rel in files]
        else:
            lines += ["No software is involved in this spec: it is a physical measurement.", ""]
        if own:
            lines += ["", "## Scripts that exist only for this evidence (they live in this folder)", ""]
            lines += [f"- `{rel}`" for rel in own]
        lines += ["", "Not copied here because of size: the Model A training data (`model_a/data/*.csv.gz`), the trained model",
                  "(`model_a/artifacts/model_a.joblib`) and the pH tables (`sim/aspen_tables/*.csv`). They are in the repo",
                  "at those paths. Refresh this snapshot with `python evidence/tools/refresh_code_snapshots.py`.", ""]
        with open(os.path.join(code, "SOURCE.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        print(f"{folder}: {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
