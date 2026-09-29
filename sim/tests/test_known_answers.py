"""Known-answer tests for the chemistry table (Simulation and Dataset Guide, Part 2, P8).

These are hand calculations. They must pass with the placeholder table AND with the real
Aspen tables. Aspen includes activity effects, so it is allowed to differ by a few
hundredths of a pH unit; the tolerance below reflects that.

    python -m sim.tests.test_known_answers      (or: pytest sim/tests)
"""
from __future__ import annotations

import warnings

from ..chemistry import (BASIS_L, excess_from_ph, ph_from_excess, table_files,
                         table_provenance)

TOL_HAND = 0.05        # vs a hand calculation that ignores activity coefficients
TOL_TIGHT = 0.01       # where activity effects are negligible (very dilute)

# (name, excess_mmol base-positive, temp_c, expected pH, tolerance)
CASES = [
    ("neutral water, 0 mmol",              0.0,   25.0,  7.00, TOL_TIGHT),
    ("10 mmol HCl in 5 L  -> 2 mM H+",   -10.0,   25.0,  2.70, TOL_HAND),
    ("0.5 mmol HCl in 5 L -> 0.1 mM H+",  -0.5,   25.0,  4.00, TOL_HAND),
    ("10 mmol NaOH in 5 L -> pOH 2.70",   10.0,   25.0, 11.30, TOL_HAND),
    ("40 mmol HCl then 40 mmol NaOH",      0.0,   25.0,  7.00, TOL_TIGHT),
]

# the band edges the requirements are written on must round-trip
BAND_CASES = [5.5, 6.0, 6.3, 7.0, 8.2, 8.5, 9.5]


def check(verbose: bool = True) -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []

    for name, excess, t_c, expect, tol in CASES:
        got = ph_from_excess(excess, t_c)
        ok = abs(got - expect) <= tol
        results.append((name, ok, f"expected {expect:.2f}, got {got:.4f} "
                                  f"(tol {tol:.2f}, diff {got - expect:+.4f})"))

    for p in BAND_CASES:
        e = excess_from_ph(p)
        back = ph_from_excess(e)
        ok = abs(back - p) <= 0.01
        results.append((f"round trip at pH {p}", ok,
                        f"pH {p} -> {e:+.6f} mmol -> pH {back:.4f}"))

    # monotonicity: more base must never lower the pH
    xs = [-60, -30, -10, -1, -0.1, -0.01, 0, 0.01, 0.1, 1, 10, 30, 60]
    ph = [ph_from_excess(x) for x in xs]
    mono = all(b > a for a, b in zip(ph, ph[1:]))
    results.append(("pH increases with excess base", mono,
                    " ".join(f"{v:.2f}" for v in ph)))

    # dilution: the same moles in a bigger tank must sit closer to neutral
    a = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L)
    b = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L * 2)
    results.append(("dilution moves pH toward neutral", b > a,
                    f"5 L pH {a:.3f} -> 10 L pH {b:.3f}"))

    # temperature: pKw falls as T rises, so neutral pH falls
    n25 = ph_from_excess(0.0, 25.0)
    n35 = ph_from_excess(0.0, 35.0)
    results.append(("neutral pH falls as temperature rises", n35 < n25,
                    f"25 C {n25:.3f} -> 35 C {n35:.3f}"))

    if verbose:
        src = table_provenance()
        print(f"chemistry source : {src}")
        print(f"tables           : {', '.join(table_files())}")
        if src == "PLACEHOLDER":
            print("  (placeholder: report charge balance, not Aspen. Re-run when CHE delivers.)")
        print()
        for name, ok, detail in results:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} {detail}")
        n_ok = sum(1 for _n, ok, _d in results if ok)
        print(f"\n{n_ok}/{len(results)} checks passed")
    return results


# pytest entry points
def test_known_answers():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name, ok, detail in check(verbose=False):
            assert ok, f"{name}: {detail}"


if __name__ == "__main__":
    import sys
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = check()
    sys.exit(0 if all(ok for _n, ok, _d in res) else 1)
