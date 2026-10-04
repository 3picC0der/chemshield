"""Named upset scenarios and the randomised population used by the 600-event batch.

A scenario is one unauthorised reagent injection that got past the gateway (or a manual
mistake) and has been confirmed as an unsafe event. Recovery starts from there.

Design event (report Table 1 basis): 40-80 mL of 0.5 M reagent = 20-40 mmol into a
4.8-5.2 L fill. The C3 ceiling is 50 mmol of corrective reagent per event.
"""
from __future__ import annotations

import numpy as np

from .model import P

BULK_M = 0.5            # mol/L, the bulk channels (0.5 M HCl / 0.5 M NaOH)


def _make(name: str, volume_ml: float, acid: bool, V: float = 5.0, **extra) -> dict:
    """n0 = net excess strong ACID in mol (positive = acidic tank)."""
    sc = dict(id=0, name=name, V=float(V), vol=float(volume_ml), acid=bool(acid),
              n0=float(volume_ml) / 1000.0 * BULK_M * (1.0 if acid else -1.0))
    sc.update(extra)
    return sc


# ------------------------------------------------------- named demo scenarios
# Used by the live booth demo and by the ISE-AT-01 / ISE-AT-02 live steps.
NAMED = {
    "nominal":          lambda: _make("nominal", 0.0, True),
    "medium_acid":      lambda: _make("medium_acid", 60.0, True),
    "medium_base":      lambda: _make("medium_base", 60.0, False),
    "acid_upset_max":   lambda: _make("acid_upset_max", 80.0, True),
    "base_upset_max":   lambda: _make("base_upset_max", 80.0, False),
    # 110 mL of 0.5 M = 55 mmol, past the 50 mmol C3 budget: the planner must ESCALATE
    # rather than dose its way out of it.
    "beyond_budget":    lambda: _make("beyond_budget", 110.0, True),
    # a full tank, so the level interlock binds before the dose cap does
    "high_level_base":  lambda: _make("high_level_base", 70.0, False, V=5.44),
}


def named(name: str) -> dict:
    if name not in NAMED:
        raise KeyError(f"unknown scenario {name!r}. Known: {', '.join(sorted(NAMED))}")
    sc = NAMED[name]()
    sc["id"] = 1
    return sc


def list_names() -> list[str]:
    return sorted(NAMED)


# ------------------------------------------------------- randomised population
def population(n: int, seed: int = 261, acid_frac: float = 0.6,
               vol_ml: tuple[float, float] = (40.0, 80.0),
               fill_L: tuple[float, float] = (4.8, 5.2)) -> list[dict]:
    """The batch population: n confirmed unsafe events.

    Randomised over upset direction, upset size and tank fill. Pump delivery error,
    fill-volume error, probe noise and mixing time are randomised separately inside the
    truth model (model.Truth), once per event.
    """
    rng = np.random.default_rng(seed)
    out = []
    for i in range(int(n)):
        V = float(rng.uniform(*fill_L))
        acid = bool(rng.random() < acid_frac)
        v = float(rng.uniform(*vol_ml))
        sc = _make("acid_upset" if acid else "base_upset", v, acid, V=V)
        sc["id"] = i + 1
        out.append(sc)
    return out


def describe(sc: dict) -> str:
    return (f"{sc['name']}: {sc['vol']:.1f} mL of {BULK_M:g} M "
            f"{'HCl' if sc['acid'] else 'NaOH'} "
            f"({abs(sc['n0']) * 1000:.2f} mmol) into {sc['V']:.2f} L")


if __name__ == "__main__":
    print("named scenarios:")
    for k in list_names():
        print(f"  {k:18s} {describe(named(k))}")
    print(f"\nC3 budget: {P['R_max']:.0f} mmol per event")
