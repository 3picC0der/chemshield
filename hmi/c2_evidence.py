#!/usr/bin/env python3
"""Collect and score the live ICS-AT-01 / C2 evidence from the operator laptop.

C2: All actuator commands must pass through the ChemShield gateway as the sole
authorized control path during testing and demonstration.

Prerequisites:
  * Raspberry Pi station running on port 8000.
  * Laptop HMI running on http://127.0.0.1:8080 and pointed at the Pi station.
  * Laptop joined to ChemShield-Lab.
  * Key-based SSH to the real Pi account works (the same setup used by clock_sync.py).
  * nmap and ssh are installed on the laptop.

Example:
  python -m hmi.c2_evidence --pi-ip 10.42.0.1 --ssh-user belal

Outputs are written to evidence/ICS-AT-01/live_run by default:
  ICS-AT-01_raw.txt
  ICS-AT-01_summary.json
  ICS-AT-01_test_sheet.md

The script never sends a valid dose. It sends only the HMI's deliberate unsigned and
wrong-key test requests; both must be rejected with HTTP 401 by the Pi station.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


EXPECTED_TCP_PORTS = {22, 8000}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run(cmd: list[str], timeout: int = 120) -> dict[str, Any]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "cmd": cmd,
            "returncode": p.returncode,
            "stdout": p.stdout,
            "stderr": p.stderr,
        }
    except FileNotFoundError:
        return {"cmd": cmd, "returncode": 127, "stdout": "", "stderr": f"{cmd[0]} not found"}
    except subprocess.TimeoutExpired as exc:
        return {
            "cmd": cmd,
            "returncode": 124,
            "stdout": exc.stdout or "",
            "stderr": (exc.stderr or "") + "\nTIMEOUT",
        }


def request_json(url: str, body: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return {"transport_status": resp.status, "json": json.loads(raw), "raw": raw}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"raw": raw}
        return {"transport_status": exc.code, "json": payload, "raw": raw}
    except Exception as exc:  # noqa: BLE001
        return {"transport_status": 0, "json": {"error": str(exc)}, "raw": str(exc)}


def parse_open_ports(nmap_text: str) -> list[int]:
    ports: list[int] = []
    for line in nmap_text.splitlines():
        m = re.match(r"\s*(\d+)/tcp\s+open\s+", line)
        if m:
            ports.append(int(m.group(1)))
    return sorted(set(ports))


def auth_methods(ssh_debug: str) -> list[str]:
    methods: list[str] = []
    for line in ssh_debug.splitlines():
        m = re.search(r"Authentications that can continue:\s*(.+)$", line, re.I)
        if m:
            methods = [x.strip().lower() for x in m.group(1).split(",") if x.strip()]
    return methods


def field(obj: dict[str, Any], *path: str) -> Any:
    cur: Any = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def main() -> int:
    ap = argparse.ArgumentParser(description="ChemShield C2 / ICS-AT-01 live evidence collector")
    ap.add_argument("--pi-ip", default="10.42.0.1")
    ap.add_argument("--station", default=None, help="Pi station URL; default http://PI:8000")
    ap.add_argument("--hmi", default="http://127.0.0.1:8080", help="Laptop HMI URL")
    ap.add_argument("--ssh-user", default="belal", help="Existing Pi account used for key-based SSH")
    ap.add_argument("--out-dir", default="evidence/ICS-AT-01/live_run")
    ap.add_argument("--quick", action="store_true", help="Use top 1000 TCP ports instead of full scan")
    args = ap.parse_args()

    station = (args.station or f"http://{args.pi_ip}:8000").rstrip("/")
    hmi = args.hmi.rstrip("/")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_sections: list[str] = []
    summary: dict[str, Any] = {
        "test_id": "ICS-AT-01",
        "constraint": "C2",
        "started_utc": utc_now(),
        "pi_ip": args.pi_ip,
        "station": station,
        "hmi": hmi,
        "ssh_user": args.ssh_user,
    }

    # 1) Confirm the Pi station is alive before testing.
    before = request_json(station + "/api/state")
    summary["station_before"] = before
    raw_sections.append("== STATION STATE BEFORE ==\n" + json.dumps(before, indent=2))

    # 2) Full TCP exposure scan from the separate laptop.
    nmap_cmd = ["nmap", "-Pn"]
    nmap_cmd += ["--top-ports", "1000"] if args.quick else ["-p-"]
    nmap_cmd.append(args.pi_ip)
    nmap = run(nmap_cmd, timeout=180)
    nmap_text = (nmap["stdout"] or "") + ("\n" + nmap["stderr"] if nmap["stderr"] else "")
    ports = parse_open_ports(nmap_text)
    summary["nmap"] = {
        "command": nmap_cmd,
        "returncode": nmap["returncode"],
        "open_tcp_ports": ports,
        "expected_tcp_ports": sorted(EXPECTED_TCP_PORTS),
        "pass": nmap["returncode"] == 0 and set(ports) == EXPECTED_TCP_PORTS,
    }
    raw_sections.append("== NMAP ==\n$ " + " ".join(nmap_cmd) + "\n" + nmap_text)

    # 3) Read Pi-local controls over the already-authorized SSH management path.
    remote = (
        "set -o pipefail; "
        "echo '--- ip_forward'; sysctl net.ipv4.ip_forward; "
        "echo '--- listening_tcp'; ss -ltn; "
        "echo '--- sshd'; "
        "(sudo sshd -T 2>/dev/null || sshd -T 2>/dev/null) | "
        "grep -Ei '^(passwordauthentication|pubkeyauthentication) '; "
        "echo '--- addresses'; ip -4 -brief address; "
        "echo '--- serial'; "
        "(ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true); "
        "echo '--- input_rules'; sudo iptables -S INPUT; "
        "echo '--- forward_rules'; sudo iptables -S FORWARD"
    )
    ssh_cfg = run(
        [
            "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            f"{args.ssh_user}@{args.pi_ip}", remote,
        ],
        timeout=30,
    )
    ssh_cfg_text = (ssh_cfg["stdout"] or "") + ("\n" + ssh_cfg["stderr"] if ssh_cfg["stderr"] else "")
    ip_forward_zero = bool(re.search(r"net\.ipv4\.ip_forward\s*=\s*0", ssh_cfg_text))
    password_auth_no = bool(re.search(r"^passwordauthentication\s+no\s*$", ssh_cfg_text, re.I | re.M))
    summary["pi_config"] = {
        "returncode": ssh_cfg["returncode"],
        "ip_forward_zero": ip_forward_zero,
        "password_auth_no": password_auth_no,
    }
    raw_sections.append("== PI CONFIG OVER KEY SSH ==\n" + ssh_cfg_text)

    # 4) Deliberately bad commands through the HMI test panel.
    bad_results: dict[str, Any] = {}
    for kind in ("unsigned", "forged"):
        r = request_json(hmi + f"/api/test/{kind}", {})
        payload = r.get("json") if isinstance(r.get("json"), dict) else {}
        passed = (
            r.get("transport_status") == 200
            and payload.get("http_status") == 401
            and payload.get("decision") == "REJECT"
        )
        bad_results[kind] = {
            "pass": passed,
            "transport_status": r.get("transport_status"),
            "gateway_http_status": payload.get("http_status"),
            "decision": payload.get("decision"),
            "reason_code": payload.get("reason_code"),
            "group": payload.get("group"),
            "response": payload,
        }
        raw_sections.append(f"== HMI TEST: {kind.upper()} ==\n" + json.dumps(r, indent=2))
    summary["bad_command_tests"] = bad_results

    # 5) Confirm no bad request left an accepted dose pending / enabled on the actuator side.
    after = request_json(station + "/api/state")
    after_state = after.get("json") if isinstance(after.get("json"), dict) else {}
    pending = after_state.get("pending")
    led_words = field(after_state, "link", "led_words")
    no_pending = pending in (None, {}, False)
    summary["station_after"] = {
        "transport_status": after.get("transport_status"),
        "pending": pending,
        "led_words": led_words,
        "no_pending_after_bad_commands": no_pending,
    }
    raw_sections.append("== STATION STATE AFTER BAD COMMANDS ==\n" + json.dumps(after, indent=2))

    # 6) Password-only SSH attempt against the SAME existing account.
    # We record the server-advertised methods from -vv output. The strong proof is the Pi's
    # sshd -T line above; this client-side attempt is the live demonstration requested by C2.
    pw_ssh = run(
        [
            "ssh", "-vv", "-o", "PubkeyAuthentication=no",
            "-o", "PreferredAuthentications=password",
            "-o", "NumberOfPasswordPrompts=0",
            "-o", "ConnectTimeout=8",
            f"{args.ssh_user}@{args.pi_ip}", "true",
        ],
        timeout=20,
    )
    pw_text = (pw_ssh["stdout"] or "") + "\n" + (pw_ssh["stderr"] or "")
    methods = auth_methods(pw_text)
    pw_refused = pw_ssh["returncode"] != 0
    password_not_offered = bool(methods) and "password" not in methods
    summary["password_ssh"] = {
        "returncode": pw_ssh["returncode"],
        "advertised_methods": methods,
        "refused": pw_refused,
        "password_not_offered": password_not_offered,
        "pass": pw_refused and password_auth_no,
    }
    raw_sections.append("== PASSWORD-ONLY SSH ATTEMPT ==\n" + pw_text)

    # Final rubric verdict. We intentionally do not infer visual LED state from a vague
    # string; instead we require no accepted pending dose after both malicious requests and
    # record led_words for the reviewer/video.
    checks = {
        "only_22_8000_open": summary["nmap"]["pass"],
        "ip_forward_is_0": ip_forward_zero,
        "unsigned_rejected_401": bad_results["unsigned"]["pass"],
        "wrong_key_rejected_401": bad_results["forged"]["pass"],
        "password_login_disabled_and_refused": summary["password_ssh"]["pass"],
        "no_bad_command_pending": no_pending,
        "station_reachable": before.get("transport_status") == 200 and after.get("transport_status") == 200,
    }
    summary["checks"] = checks
    summary["pass"] = all(checks.values())
    summary["finished_utc"] = utc_now()

    raw_path = out_dir / "ICS-AT-01_raw.txt"
    json_path = out_dir / "ICS-AT-01_summary.json"
    sheet_path = out_dir / "ICS-AT-01_test_sheet.md"

    raw_path.write_text("\n\n".join(raw_sections) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    ports_words = ", ".join(str(x) for x in ports) if ports else "none detected"
    unsigned = bad_results["unsigned"]
    forged = bad_results["forged"]
    verdict = "PASS" if summary["pass"] else "FAIL / INCOMPLETE"
    sheet = f"""# ICS-AT-01 — C2 gateway-only path

**Run:** {summary['finished_utc']}  
**Constraint:** All actuator commands must pass through the ChemShield gateway as the sole authorized control path during testing and demonstration.  
**Verdict:** **{verdict}**

| Step | Test | Achieved result / evidence |
|---|---|---|
| 1 | Pi on ChemShield-Lab with C2 firewall; laptop joined to it | Station reachable at `{station}`; Pi evidence captured over authorized key SSH. |
| 2 | `nmap -Pn {'--top-ports 1000' if args.quick else '-p-'} {args.pi_ip}` | Open TCP ports: **{ports_words}**. Required: **22, 8000 only**. {'PASS' if summary['nmap']['pass'] else 'FAIL'} |
| 3 | `sysctl net.ipv4.ip_forward` on Pi | `net.ipv4.ip_forward = {'0' if ip_forward_zero else 'NOT CONFIRMED'}`. {'PASS' if ip_forward_zero else 'FAIL'} |
| 4a | HMI engineer panel: unsigned dose | Gateway HTTP **{unsigned.get('gateway_http_status')}**, decision **{unsigned.get('decision')}**, reason `{unsigned.get('reason_code')}`. {'PASS' if unsigned['pass'] else 'FAIL'} |
| 4b | HMI engineer panel: wrong-key dose | Gateway HTTP **{forged.get('gateway_http_status')}**, decision **{forged.get('decision')}**, reason `{forged.get('reason_code')}`. {'PASS' if forged['pass'] else 'FAIL'} |
| 5 | Password-only SSH to existing Pi account `{args.ssh_user}` | Refused: **{pw_refused}**; Pi `sshd -T` says `passwordauthentication {'no' if password_auth_no else 'NOT CONFIRMED'}`. {'PASS' if summary['password_ssh']['pass'] else 'FAIL'} |
| 6 | No bypass reaches actuator side | After both bad commands: pending dose = `{pending}`; Uno light state = `{led_words}`. {'PASS' if no_pending else 'FAIL'} |
| Final | Pass if only 22/8000 open, ip_forward=0, bypasses refused, no bad command reaches actuator | **{verdict}** |

## Machine-readable evidence

- `ICS-AT-01_summary.json` — scored checks and exact values.
- `ICS-AT-01_raw.txt` — raw nmap, SSH, Pi configuration and API responses.
- This sheet is generated directly from the measurements; do not hand-edit a FAIL into PASS.

## Video / screenshot checklist

Capture one continuous clip showing: laptop on **ChemShield-Lab**, the nmap result, the
unsigned and wrong-key 401 responses in the HMI, the password-only SSH refusal, and the
Uno light staying off. Also take a screenshot of the Pi output showing
`net.ipv4.ip_forward = 0`.
"""
    sheet_path.write_text(sheet, encoding="utf-8")

    print(sheet)
    print(f"\nEvidence written to {out_dir}")
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
