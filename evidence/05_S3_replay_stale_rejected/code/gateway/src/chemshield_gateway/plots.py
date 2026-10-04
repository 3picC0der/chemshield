from __future__ import annotations

from pathlib import Path
from typing import Any


def plot_security_summary(security: dict[str, Any], output_dir: Path) -> str:
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    categories = [row["category"] for row in security["category_results"]]
    rejected = [row["rejected"] for row in security["category_results"]]
    accepted = [row["accepted"] for row in security["category_results"]]
    fig, ax = plt.subplots(figsize=(12, 6))
    x = range(len(categories))
    ax.bar(x, rejected, label="Rejected")
    ax.bar(x, accepted, bottom=rejected, label="Accepted")
    ax.set_xticks(list(x))
    ax.set_xticklabels(categories, rotation=45, ha="right")
    ax.set_ylabel("Commands")
    ax.set_title("ChemShield Gateway Security Test Results")
    ax.legend()
    fig.tight_layout()
    path = output_dir / "security_test_summary.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def plot_failsafe_summary(failsafe: dict[str, Any], output_dir: Path) -> str:
    import matplotlib.pyplot as plt

    output_dir.mkdir(parents=True, exist_ok=True)
    names = [r["test_case"] for r in failsafe["results"]]
    safe_hold = [r["time_until_safe_hold_s"] for r in failsafe["results"]]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(names, safe_hold)
    ax.axhline(2.0, linestyle="--", label="2 s target")
    ax.set_ylabel("Seconds")
    ax.set_title("ChemShield SAFE_HOLD Timing")
    ax.tick_params(axis="x", rotation=25)
    ax.legend()
    fig.tight_layout()
    path = output_dir / "failsafe_summary.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def draw_network_trust_boundary(output_dir: Path) -> str:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.axis("off")
    boxes = [
        (0.05, 0.55, 0.20, 0.22, "Operator Laptop / HMI\nLess-trusted network"),
        (0.38, 0.55, 0.24, 0.22, "Raspberry Pi\nChemShield Gateway\nFirewall + Validation"),
        (0.75, 0.55, 0.18, 0.22, "Uno / PLC\nActuator side"),
        (0.75, 0.18, 0.18, 0.18, "Pumps\nAcid/Base"),
    ]
    for x, y, w, h, text in boxes:
        ax.add_patch(Rectangle((x, y), w, h, fill=False, linewidth=2))
        ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=10)
    ax.annotate("HTTPS / API\nallowed", xy=(0.38, 0.66), xytext=(0.25, 0.66), arrowprops=dict(arrowstyle="->", lw=2), ha="center")
    ax.annotate("Gateway-approved\nserial/PLC command", xy=(0.75, 0.66), xytext=(0.62, 0.66), arrowprops=dict(arrowstyle="->", lw=2), ha="center")
    ax.annotate("Pump output", xy=(0.84, 0.36), xytext=(0.84, 0.55), arrowprops=dict(arrowstyle="->", lw=2), ha="center")
    ax.text(0.5, 0.40, "Trust boundary: direct operator-to-actuator path is blocked\nIP forwarding disabled; firewall default-deny; actuator accepts only gateway path", ha="center", fontsize=11)
    fig.tight_layout()
    path = output_dir / "network_trust_boundary_diagram.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)
