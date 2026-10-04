"""Draw the booth network for C2 (what can reach what).  python make_network_diagram.py"""
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
fig, ax = plt.subplots(figsize=(11, 5), dpi=150)
ax.set_xlim(0, 110)
ax.set_ylim(0, 50)
ax.axis("off")


def box(x, y, w, h, text, fc, ec="#333333", fs=10, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.5", fc=fc, ec=ec, lw=1.5))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")


box(1, 18, 21, 14, "Operator laptop\n(HMI)\nholds the operator key\nsigns every request", "#e6eefa")
box(34, 8, 36, 34, "", "#fff6e0")
ax.text(52, 39, "Raspberry Pi 5", ha="center", fontsize=11, fontweight="bold")
box(37, 29, 30, 6, "Firewall: policy DROP\nopen: SSH 22 (key only), station 8000", "#fde3e3", fs=9)
box(37, 19, 30, 7, "Station on port 8000\nGATEWAY: signature, freshness,\n20 mL, 15 s, 50 mmol, Model A", "#e3f3ea", fs=9, bold=True)
box(37, 10, 30, 6, "IP forwarding = 0\n(the Pi relays nothing)", "#eceff2", fs=9)
box(84, 18, 22, 14, "Arduino Uno\nno network address\ndose light, E-stop,\npH probe input", "#e3f3ea")
ax.annotate("", xy=(34, 25), xytext=(22, 25), arrowprops=dict(arrowstyle="->", lw=2, color="#2557a7"))
ax.text(28, 29, "Wi-Fi\nChemShield-Lab", ha="center", fontsize=9, color="#2557a7")
ax.annotate("", xy=(84, 25), xytext=(70, 25), arrowprops=dict(arrowstyle="<->", lw=2, color="#1d7a4b"))
ax.text(77, 28.5, "USB cable\n(only path)", ha="center", fontsize=9, color="#1d7a4b")
ax.text(12, 9, "Any other laptop on the Wi-Fi:\nthe scan finds only ports 22 and 8000;\nunsigned or wrong-key requests\nget HTTP 401", ha="center", va="center", fontsize=8.5, color="#b02a2a")
ax.text(55, 3, "Pump (not connected to the Uno in this prototype): separate 24 V adapter, tested on its own for Spec 7",
        ha="center", fontsize=8.5, color="#555555")
ax.set_title("C2: the only way to command the Uno is through the gateway on the Pi", fontsize=12, fontweight="bold")
fig.tight_layout()
out = os.path.join(HERE, "..", "plots", "C2_network_and_trust_boundary.png")
os.makedirs(os.path.dirname(out), exist_ok=True)
fig.savefig(out)
print("wrote", os.path.normpath(out))
