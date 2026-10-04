"""Auto-start on the Pi: the two services render correctly and the boot firewall script applies
the rules in the right order.

Nothing here touches the host. The unit files are written to a temporary folder (the installer's
dry run), and nmcli, sysctl, sudo, iptables and the firewall command are stubs that only record
their arguments.

    python -m pytest gateway/tests/test_systemd_autostart.py
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SYSTEMD = ROOT / "gateway" / "systemd"
INSTALL = SYSTEMD / "install.sh"
BOOT_FW = SYSTEMD / "boot_firewall.sh"
C2_NETWORK = ROOT / "gateway" / "firewall" / "c2_network.sh"


def _stub(folder: Path, name: str, body: str) -> None:
    path = folder / name
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


def _env(stubs: Path, **extra: str) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items()
            if not k.startswith("CHEMSHIELD_") and k not in ("USER", "LOGNAME", "SUDO_USER")}
    return {**base, "PATH": f"{stubs}{os.pathsep}{base.get('PATH', '')}", **extra}


def _fake_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    (repo / ".venv" / "bin").mkdir(parents=True)
    _stub(repo / ".venv" / "bin", "python", "exit 0")
    (repo / "hmi" / "secrets").mkdir(parents=True)
    (repo / "hmi" / "secrets" / "operator.key").write_text("not a real key\n")
    return repo


def test_scripts_parse():
    for script in (INSTALL, BOOT_FW):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_dry_run_install_renders_both_units():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo, root = _fake_repo(tmp), tmp / "root"
        out = subprocess.run(["bash", str(INSTALL), "install"], check=True, capture_output=True, text=True,
                             env=_env(tmp, CHEMSHIELD_ROOT=str(root), CHEMSHIELD_REPO=str(repo),
                                      CHEMSHIELD_USER="pi-user"))
        assert "dry run" in out.stdout
        units = root / "etc" / "systemd" / "system"
        station = (units / "chemshield-station.service").read_text()
        firewall = (units / "chemshield-firewall.service").read_text()
        for text in (station, firewall):
            assert "@REPO@" not in text and "@USER@" not in text
            for section in ("[Unit]", "[Service]", "[Install]"):
                assert section in text
            assert "WantedBy=multi-user.target" in text
        # the station runs as the Pi's user, from the repository, and not without the operator key
        assert "User=pi-user" in station
        assert f"WorkingDirectory={repo}" in station
        assert f"ExecStart={repo}/.venv/bin/python -W ignore -m hmi.station --ph-source uno" in station
        assert f"ConditionPathExists={repo}/hmi/secrets/operator.key" in station
        assert "Restart=on-failure" in station
        # the firewall runs as root once per boot, and says whose home the evidence log goes to
        assert "Type=oneshot" in firewall and "RemainAfterExit=yes" in firewall
        assert f"ExecStart=/bin/bash {repo}/gateway/systemd/boot_firewall.sh" in firewall
        assert "Environment=SUDO_USER=pi-user" in firewall
        assert "User=" not in firewall.replace("SUDO_USER=", "")
        # nothing outside the unit folder was written
        assert sorted(p.name for p in root.rglob("*") if p.is_file()) == [
            "chemshield-firewall.service", "chemshield-station.service"]


def test_install_stops_if_the_project_is_not_set_up():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        (tmp / "repo").mkdir()
        res = subprocess.run(["bash", str(INSTALL), "install"], capture_output=True, text=True,
                             env=_env(tmp, CHEMSHIELD_ROOT=str(tmp / "root"), CHEMSHIELD_REPO=str(tmp / "repo"),
                                      CHEMSHIELD_USER="pi-user"))
        assert res.returncode == 1
        assert ".venv/bin/python" in res.stderr
        assert not (tmp / "root").exists()


def test_install_warns_when_the_operator_key_is_missing():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        repo = _fake_repo(tmp)
        (repo / "hmi" / "secrets" / "operator.key").unlink()
        res = subprocess.run(["bash", str(INSTALL), "install"], capture_output=True, text=True,
                             env=_env(tmp, CHEMSHIELD_ROOT=str(tmp / "root"), CHEMSHIELD_REPO=str(repo),
                                      CHEMSHIELD_USER="pi-user"))
        assert res.returncode == 0
        assert "operator.key is missing" in res.stderr


def _run_boot_firewall(nmcli: str, forwarding: str, **timing: str) -> tuple[list[str], str]:
    """Run boot_firewall.sh with stubs. Returns (how many times and when the firewall was applied, output)."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        log = tmp / "applied.log"
        _stub(tmp, "apply_firewall", f'echo applied >> "{log}"')
        _stub(tmp, "nmcli", f'echo "{nmcli}"')
        _stub(tmp, "sysctl", f'echo "{forwarding}"')
        env = _env(tmp, CHEMSHIELD_FW_CMD=str(tmp / "apply_firewall"), CHEMSHIELD_FW_WAIT_S="2",
                   CHEMSHIELD_FW_SETTLE_S="1", CHEMSHIELD_FW_WATCH_S="1", CHEMSHIELD_FW_POLL_S="1", **timing)
        res = subprocess.run(["bash", str(BOOT_FW)], check=True, capture_output=True, text=True, env=env, timeout=60)
        calls = log.read_text().splitlines() if log.exists() else []
        return calls, res.stdout + res.stderr


def test_boot_firewall_applies_at_start_after_the_wifi_and_after_it_settles():
    calls, out = _run_boot_firewall("wlan0:connected", "0")
    assert len(calls) == 3, out
    assert out.index("at start") < out.index("after waiting for the Wi-Fi") < out.index("after it settled")
    assert "wlan0 connected" in out


def test_boot_firewall_stays_on_when_the_wifi_never_connects():
    calls, out = _run_boot_firewall("wlan0:disconnected", "0")
    assert len(calls) == 3, out
    assert "did not connect" in out and "rules stay on" in out


def test_boot_firewall_reapplies_when_forwarding_comes_back_on():
    calls, out = _run_boot_firewall("wlan0:connected", "1")
    assert len(calls) >= 4, out
    assert "IP forwarding came back on" in out


def test_firewall_command_is_the_one_used_by_hand():
    text = BOOT_FW.read_text()
    assert 'c2_network.sh fw' in text


def test_c2_network_fw_works_without_a_USER_variable():
    """systemd sets no $USER for a root service; the unit sets SUDO_USER and the script must cope."""
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        calls = tmp / "calls.log"
        for name in ("sudo", "sysctl", "iptables", "ip6tables"):
            _stub(tmp, name, f'echo "{name} $*" >> "{calls}"')
        _stub(tmp, "tee", "cat >/dev/null")
        _stub(tmp, "getent", f'echo "pi-user:x:1000:1000::{tmp}:/bin/bash"')
        res = subprocess.run(["bash", str(C2_NETWORK), "fw"], capture_output=True, text=True,
                             env=_env(tmp, SUDO_USER="pi-user", CHEMSHIELD_C2_LOG=str(tmp / "c2_evidence.txt")))
        assert res.returncode == 0, res.stderr
        assert "sudo iptables -P INPUT DROP" in calls.read_text()
