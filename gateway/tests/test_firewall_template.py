"""C2: the Pi firewall template must close every inbound port it does not open.

Before this the INPUT policy stayed ACCEPT, so the two ACCEPT rules blocked nothing, and
the one web port it opened (443) was not the HMI's (uvicorn, 8000).

The script is never executed here: it rewrites the host firewall. These checks read it,
and `bash -n` only parses it.

    python gateway/tests/test_firewall_template.py      (or: pytest gateway/tests)
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

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


TESTS = [test_script_parses, test_input_default_drop_after_the_accepts, test_ipv6_gets_the_same_rules,
         test_one_hmi_port_variable_shared_with_the_hmi]


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
