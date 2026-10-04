"""C2: the Pi firewall template must close every inbound port it does not open.

Before this the INPUT policy stayed ACCEPT, so the two ACCEPT rules blocked nothing, and
the one web port it opened (443) was not the HMI's (uvicorn, 8000). Then the DROP policy
also dropped DHCP, so a laptop joining the Pi's hotspot got no address, and step 4 named a
user that doesn't exist on the Pi, which stopped the script before its evidence printout.

The script never touches the host firewall here. Most checks read it and `bash -n` parses
it; the dry runs execute it with every command (sudo, sysctl, iptables, ...) replaced by a
stub that only records its arguments.

    python gateway/tests/test_firewall_template.py      (or: pytest gateway/tests)
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "gateway" / "firewall" / "raspberry_pi_firewall_template.sh"
HMI_README = ROOT / "hmi" / "README.md"


def _lines() -> list[str]:
    return [ln.strip() for ln in SCRIPT.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def _index(pattern: str) -> int:
    for i, ln in enumerate(_lines()):
        if re.search(pattern, ln):
            return i
    raise AssertionError(f"no line matching {pattern!r} in {SCRIPT.name}")


def test_script_parses():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_input_default_drop_after_the_accepts():
    drop = _index(r'-P INPUT DROP')
    for accept in (r'-A INPUT -i lo -j ACCEPT',
                   r'-A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT',
                   r'-A INPUT .*--dport "\$SSH_PORT" -j ACCEPT',
                   r'-A INPUT .*--dport "\$HMI_PORT" -j ACCEPT'):
        assert _index(accept) < drop, accept


def test_ipv6_gets_the_same_rules():
    assert _index(r'for ipt in iptables ip6tables') < _index(r'-P INPUT DROP')


def test_one_hmi_port_variable_shared_with_the_hmi():
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r'^SSH_PORT="22"$', text, re.M)
    assert re.search(r'^HMI_PORT="\$\{CHEMSHIELD_HMI_PORT:-8000\}"$', text, re.M)
    assert not any("443" in ln for ln in _lines()), "443 is not the HMI's port"
    assert '--port "${CHEMSHIELD_HMI_PORT:-8000}"' in HMI_README.read_text(encoding="utf-8")


def _dry_run(**env: str) -> list[str]:
    """Run the script with sudo and sysctl replaced by stubs that only record their
    arguments (every iptables call goes through sudo). Returns the recorded calls."""
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "calls.log"
        for name in ("sudo", "sysctl", "iptables", "ip6tables", "tee"):
            stub = Path(tmp) / name
            # `printf ... | sudo tee FILE`: read stdin so printf never sees a closed pipe
            stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n'
                            f'if [ "$1" = tee ] || [ "{name}" = tee ]; then cat >/dev/null; fi\n')
            stub.chmod(0o755)
        clean = {k: v for k, v in os.environ.items() if not k.startswith("CHEMSHIELD_")}
        subprocess.run(["bash", str(SCRIPT)], check=True, capture_output=True, text=True,
                       env={**clean, "PATH": f"{tmp}{os.pathsep}{clean.get('PATH', '')}", **env})
        return log.read_text(encoding="utf-8").splitlines()


def test_dry_run_usb_rig_keeps_dhcp_and_reaches_the_evidence():
    calls = _dry_run()
    dhcp = "sudo iptables -A INPUT -i wlan0 -p udp --dport 67 -j ACCEPT"
    assert dhcp in calls, "a laptop joining the hotspot must still get an address"
    assert calls.index(dhcp) < calls.index("sudo iptables -P INPUT DROP")
    assert "sudo ip6tables -P INPUT DROP" in calls
    assert not any("--uid-owner" in c for c in calls), "no TCP actuator rule on the USB rig"
    assert calls[-3:] == ["sysctl net.ipv4.ip_forward", "sudo iptables -S", "sudo ip6tables -S INPUT"]


def test_dry_run_tcp_link_keeps_the_owner_rule():
    calls = _dry_run(CHEMSHIELD_ACTUATOR_LINK="tcp", CHEMSHIELD_OPERATOR_IFACE="wlan1")
    assert any("--uid-owner chemshield" in c for c in calls)
    assert "sudo iptables -A INPUT -i wlan1 -p tcp --dport 22 -j ACCEPT" in calls


TESTS = [test_script_parses, test_input_default_drop_after_the_accepts, test_ipv6_gets_the_same_rules,
         test_one_hmi_port_variable_shared_with_the_hmi, test_dry_run_usb_rig_keeps_dhcp_and_reaches_the_evidence,
         test_dry_run_tcp_link_keeps_the_owner_rule]


if __name__ == "__main__":
    bad = 0
    for t in TESTS:
        try:
            t()
            print(f"  [PASS] {t.__name__}")
        except Exception as exc:                                     # noqa: BLE001
            bad += 1
            print(f"  [FAIL] {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(TESTS) - bad}/{len(TESTS)} checks passed")
    sys.exit(1 if bad else 0)
