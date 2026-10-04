"""ICS-AT-01 (C2): from a laptop on the Pi's network, try the ways to reach the actuator side
and show that only the gateway works.

    .venv/bin/python -m hmi.c2_check --pi 10.42.0.1 --ssh-key ~/.ssh/id_ed25519_second

Needs the station running on the Pi (so port 8000 is open to find) and nmap on this laptop
(`brew install nmap`; without it a slower Python connect scan of the same ports is used). The ssh key is only for reading the Pi's routing and firewall
settings (check 7); without --ssh-key that check is skipped.

Checks, each PASS / FAIL / SKIP:
  1  port scan: only SSH (22) and the station port (8000) are open
  2  an unsigned dose is refused (HTTP 401)
  3  a dose signed with the wrong key is refused (HTTP 401)
  4  an unsigned operator action (HALT) is refused (HTTP 401)
  5  a body that is not a command is refused (HTTP 400)
  6  SSH does not offer password login
  7  on the Pi: IP forwarding is 0 and the INPUT and FORWARD policies are DROP
  8  after all that, no dose was accepted and the Uno's light never turned on

The report goes to --out (default evidence/02_C2_gateway_sole_control_path/data/c2_check_<time>/).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from hmi.common import ROOT, STATION_PORT, gateway_config, new_dose_command

EXPECTED_OPEN = {22, STATION_PORT}
# Every well-known port, plus where an actuator or a second web service could be listening:
# MQTT, OPC UA, VNC, the 8000 range, Modbus-style and EtherNet/IP ports. About 1,150 ports,
# about a minute. (--full scans all 65,535: much slower behind a DROP firewall.)
SCAN_PORTS = "1-1024,1883,1884,2222,3000,4840,5000-5002,5353,5900,8000-8100,8443,8883,9000,9100,44818,47808"


def http(url: str, body: bytes | None = None, timeout: float = 8.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw.decode(errors="replace")[:200]}


def _port_list() -> list[int]:
    ports: set[int] = set()
    for part in SCAN_PORTS.split(","):
        lo, _, hi = part.partition("-")
        ports.update(range(int(lo), int(hi or lo) + 1))
    return sorted(ports)


def scan_ports(host: str, log: list[str], full: bool = False) -> tuple[set[int], str]:
    """Open TCP ports on the host, and which scanner found them."""
    ports = _port_list()
    if shutil.which("nmap"):
        spec = "-" if full else SCAN_PORTS
        cmd = ["nmap", "-Pn", "-p", spec, "-T4", "--max-retries", "1"] + (["--min-rate", "2000"] if full else []) \
            + ["-oG", "-", host]
        log.append("$ " + " ".join(cmd))
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=3600 if full else 900).stdout
        log.append(out.strip())
        what = "all 65535 TCP ports" if full else f"{len(ports)} TCP ports"
        return {int(p) for p in re.findall(r"(\d+)/open/tcp", out)}, f"nmap, {what}"

    def probe(port: int) -> int | None:
        try:
            with socket.create_connection((host, port), timeout=0.6):
                return port
        except OSError:
            return None

    with ThreadPoolExecutor(200) as pool:
        found = {p for p in pool.map(probe, ports) if p}
    log.append(f"python connect scan of {len(ports)} ports: open = {sorted(found)}")
    return found, f"python connect scan of {len(ports)} ports (install nmap for the full scan)"


def ssh_base(user: str, host: str, key: str | None, *extra: str) -> list[str]:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new"]
    if key:
        cmd += ["-i", str(Path(key).expanduser()), "-o", "IdentitiesOnly=yes"]
    return cmd + list(extra) + [f"{user}@{host}"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.c2_check", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pi", required=True, help="the Pi's address on this network, e.g. 10.42.0.1")
    ap.add_argument("--port", type=int, default=STATION_PORT)
    ap.add_argument("--ssh-user", default="chemshield")
    ap.add_argument("--ssh-key", help="private key for reading the Pi's settings (check 7)")
    ap.add_argument("--full", action="store_true", help="scan all 65,535 ports (needs nmap; slow)")
    ap.add_argument("--out", type=Path, help="report folder")
    a = ap.parse_args(argv)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = a.out or ROOT / "evidence" / "02_C2_gateway_sole_control_path" / "data" / f"c2_check_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = f"http://{a.pi}:{a.port}"
    expected = {22, a.port}
    results: list[dict] = []
    log: list[str] = []

    def record(n: int, name: str, status: str, detail: str) -> None:
        results.append({"check": n, "name": name, "status": status, "detail": detail})
        print(f"  [{status:4s}] {n}. {name}: {detail}", flush=True)

    print(f"C2 check against {a.pi}, {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC")
    try:
        _, before = http(base + "/api/state")
    except OSError as exc:
        print(f"Cannot reach the station at {base} ({exc}). Is the Pi on and the station running?")
        return 2
    accepted_before = before.get("gateway", {}).get("counters", {}).get("ACCEPT", 0)

    # 1 ----------------------------------------------------------------------------------
    t0 = time.time()
    open_ports, how = scan_ports(a.pi, log, a.full)
    ok = open_ports == expected
    record(1, "port scan", "PASS" if ok else "FAIL",
           f"open TCP ports {sorted(open_ports)} (expected {sorted(expected)}); {how}; {time.time() - t0:.0f} s")

    # 2-5 --------------------------------------------------------------------------------
    cfg_wrong = gateway_config("this-is-not-the-operator-key")
    cmd = new_dose_command(cfg_wrong, channel_id="BASE_FINE", volume_ml=1.0, event_id="OPS-C2CHECK",
                           sequence_number=int(time.time()) % 1_000_000, source="C2CHECK")
    unsigned = {k: v for k, v in cmd.items() if k != "hmac_sha256"}
    code, body = http(base + "/api/dose", json.dumps(unsigned).encode())
    record(2, "unsigned dose", "PASS" if code == 401 else "FAIL",
           f"HTTP {code}, {body.get('reason_code', body)}")
    code, body = http(base + "/api/dose", json.dumps(cmd).encode())
    record(3, "dose signed with the wrong key", "PASS" if code == 401 else "FAIL",
           f"HTTP {code}, {body.get('reason_code', body)}")
    code, body = http(base + "/api/operator", json.dumps({"kind": "operator_action", "action": "HALT"}).encode())
    record(4, "unsigned operator action (HALT)", "PASS" if code == 401 else "FAIL", f"HTTP {code}")
    code, body = http(base + "/api/dose", b"this is not a command")
    record(5, "body that is not a command", "PASS" if code == 400 else "FAIL", f"HTTP {code}")

    # 6 ----------------------------------------------------------------------------------
    cmd6 = ssh_base(a.ssh_user, a.pi, None, "-o", "PubkeyAuthentication=no",
                    "-o", "PreferredAuthentications=password,keyboard-interactive") + ["true"]
    log.append("$ " + " ".join(cmd6))
    r6 = subprocess.run(cmd6, capture_output=True, text=True, timeout=60)
    log.append((r6.stdout + r6.stderr).strip())
    offered = re.search(r"Permission denied \(([^)]*)\)", r6.stderr)
    methods = offered.group(1) if offered else ""
    pw = r6.returncode == 0 or "password" in methods or "keyboard-interactive" in methods
    if offered:
        record(6, "SSH password login", "FAIL" if pw else "PASS", f"server offers: {methods}")
    else:
        record(6, "SSH password login", "FAIL" if r6.returncode == 0 else "SKIP",
               f"no login attempt was possible: {r6.stderr.strip()[:80]}")

    # 7 ----------------------------------------------------------------------------------
    if a.ssh_key:
        remote = ("cat /proc/sys/net/ipv4/ip_forward; sudo -n iptables -S INPUT | head -1; "
                  "sudo -n iptables -S FORWARD | head -1; ss -ltn | tail -n +2")
        r7 = subprocess.run(ssh_base(a.ssh_user, a.pi, a.ssh_key) + [remote], capture_output=True,
                            text=True, timeout=60)
        lines = r7.stdout.strip().splitlines()
        log.append("$ ssh pi: ip_forward, INPUT and FORWARD policy, listening sockets\n" + r7.stdout.strip()
                   + r7.stderr.strip())
        if r7.returncode == 0 and len(lines) >= 3:
            fwd, inp, fw = lines[0].strip(), lines[1].strip(), lines[2].strip()
            ok7 = fwd == "0" and inp == "-P INPUT DROP" and fw == "-P FORWARD DROP"
            record(7, "routing and firewall on the Pi", "PASS" if ok7 else "FAIL",
                   f"ip_forward={fwd}; {inp}; {fw}")
        else:
            record(7, "routing and firewall on the Pi", "FAIL", f"could not read: {r7.stderr.strip()[:100]}")
    else:
        record(7, "routing and firewall on the Pi", "SKIP", "no --ssh-key given")

    # 8 ----------------------------------------------------------------------------------
    _, after = http(base + "/api/state")
    accepted_after = after.get("gateway", {}).get("counters", {}).get("ACCEPT", 0)
    led = after.get("link", {}).get("led")
    pending = after.get("pending")
    ok8 = accepted_after == accepted_before and pending is None and led != "dose"
    record(8, "nothing reached the Uno", "PASS" if ok8 else "FAIL",
           f"accepted doses {accepted_before} to {accepted_after}; dose pending: {pending is not None}; Uno light: {led}")

    failed = [r for r in results if r["status"] == "FAIL"]
    verdict = "C2 PASS: only the gateway path works" if not failed else f"C2 FAIL: checks {[r['check'] for r in failed]}"
    print(f"\n{verdict}")
    report = {"test": "ICS-AT-01 (C2)", "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "target": a.pi, "station_port": a.port, "results": results, "verdict": verdict}
    (out_dir / "ICS-AT-01_c2_check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = [f"ICS-AT-01 (C2) check against {a.pi} at {report['run_utc']}", ""]
    text += [f"[{r['status']}] {r['check']}. {r['name']}: {r['detail']}" for r in results]
    text += ["", verdict, "", "---- raw output ----"] + log
    (out_dir / "ICS-AT-01_c2_check.txt").write_text("\n".join(text) + "\n", encoding="utf-8")
    print(f"report: {out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
