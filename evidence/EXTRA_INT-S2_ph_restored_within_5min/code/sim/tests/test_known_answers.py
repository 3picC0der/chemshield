"""Known-answer tests for the chemistry table (Simulation and Dataset Guide, Part 2, P8).

These are hand calculations. The tank-liquid checks must pass with the placeholder table
AND with the real Aspen tables. Aspen includes activity effects, so it is allowed to differ
by a few hundredths of a pH unit; the tolerance below reflects that.

Two sets:
  tank liquid  the table sim.chemistry loads: 5.000 L distilled water + 0.420 g NaHCO3
               (1 mmol/L), pKa1 6.35, pKa2 10.33. Excess 0 is pH 8.30, not 7.
  pure water   the report's charge balance, checked on the pure-water placeholder, which
               the loader skips (its name starts with "_") and these tests load on purpose.

    python -m sim.tests.test_known_answers      (or: pytest sim/tests)
"""
from __future__ import annotations

import contextlib
import os
import warnings

from ..chemistry import (BASIS_L, TABLE_DIR, excess_from_ph, ph_from_excess, reload_tables,
                         table_files, table_provenance)

TOL_HAND = 0.05        # vs a hand calculation that ignores activity coefficients
TOL_TIGHT = 0.01       # where activity effects are negligible (very dilute)

PURE_WATER_TABLE = os.path.join(TABLE_DIR, "_placeholder_pure_water_ph_table.csv")

# (name, excess_mmol base-positive, temp_c, expected pH, tolerance)
LIQUID_CASES = [
    # closed NaHCO3 solution: close to (pKa1 + pKa2) / 2, pulled down a little at 1 mM
    ("liquid as prepared, 0 mmol",           0.0, 25.0,  8.30, TOL_HAND),
    # 3.5 mmol H+ turns 0.7 of the 1 mM HCO3- into H2CO3: 6.35 + log(0.3 / 0.7)
    ("3.5 mmol HCl -> 6.35 + log(.3/.7)",   -3.5, 25.0,  5.98, TOL_HAND),
    # 6.35 + log(0.8 / 0.2)
    ("1 mmol HCl -> 6.35 + log(.8/.2)",     -1.0, 25.0,  6.95, TOL_HAND),
    # 2 mM H+: 1 mM used up by the bicarbonate, 1 mM left over
    ("10 mmol HCl -> 1 mM H+ left over",   -10.0, 25.0,  3.00, TOL_HAND),
    # 0.2 mM OH- turns HCO3- into CO3--, which hydrolyses back: 9.61, not 10.33 + log(.2/.8)
    ("1 mmol NaOH -> 0.2 mM CO3--",          1.0, 25.0,  9.61, TOL_HAND),
    # 2 mM OH-: 1 mM used up by the bicarbonate, 1 mM left over plus CO3-- hydrolysis
    ("10 mmol NaOH -> 1 mM OH- left over",  10.0, 25.0, 11.06, TOL_HAND),
]

PURE_WATER_CASES = [
    ("neutral water, 0 mmol",              0.0,   25.0,  7.00, TOL_TIGHT),
    ("10 mmol HCl in 5 L  -> 2 mM H+",   -10.0,   25.0,  2.70, TOL_HAND),
    ("0.5 mmol HCl in 5 L -> 0.1 mM H+",  -0.5,   25.0,  4.00, TOL_HAND),
    ("10 mmol NaOH in 5 L -> pOH 2.70",   10.0,   25.0, 11.30, TOL_HAND),
    ("40 mmol HCl then 40 mmol NaOH",      0.0,   25.0,  7.00, TOL_TIGHT),
]

# the band edges the requirements are written on must round-trip
BAND_CASES = [5.5, 6.0, 6.3, 7.0, 8.2, 8.5, 9.5]


@contextlib.contextmanager
def _pure_water_table():
    reload_tables([PURE_WATER_TABLE])
    try:
        yield
    finally:
        reload_tables()


def _cases(cases) -> list[tuple[str, bool, str]]:
    out = []
    for name, excess, t_c, expect, tol in cases:
        got = ph_from_excess(excess, t_c)
        ok = abs(got - expect) <= tol
        out.append((name, ok, f"expected {expect:.2f}, got {got:.4f} "
                              f"(tol {tol:.2f}, diff {got - expect:+.4f})"))
    return out


def check_liquid() -> list[tuple[str, bool, str]]:
    """The table sim.chemistry actually loads (placeholder today, Aspen later)."""
    results = _cases(LIQUID_CASES)

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

    # dilution: the same moles in a bigger tank must sit closer to the liquid as prepared
    a = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L)
    b = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L * 2)
    results.append(("dilution moves pH toward the liquid", b > a,
                    f"5 L pH {a:.3f} -> 10 L pH {b:.3f}"))
    return results


def check_pure_water() -> list[tuple[str, bool, str]]:
    """The report's pure-water hand calculations, on the pure-water placeholder."""
    with _pure_water_table():
        results = _cases(PURE_WATER_CASES)

        a = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L)
        b = ph_from_excess(-10.0, 25.0, volume_L=BASIS_L * 2)
        results.append(("dilution moves pH toward neutral", b > a,
                        f"5 L pH {a:.3f} -> 10 L pH {b:.3f}"))

        # temperature: pKw falls as T rises, so neutral pH falls
        n25 = ph_from_excess(0.0, 25.0)
        n35 = ph_from_excess(0.0, 35.0)
        results.append(("neutral pH falls as temperature rises", n35 < n25,
                        f"25 C {n25:.3f} -> 35 C {n35:.3f}"))
    return results


def check(verbose: bool = True) -> list[tuple[str, bool, str]]:
    liquid = check_liquid()
    src, files = table_provenance(), table_files()
    pure = check_pure_water()
    results = liquid + pure

    if verbose:
        print(f"chemistry source : {src}")
        print(f"tables           : {', '.join(files)}")
        if src == "PLACEHOLDER":
            print("  (placeholder: closed carbonate model, not Aspen. Re-run when CHE delivers.)")
        print("\ntank liquid (5.000 L water + 0.420 g NaHCO3), the loaded table:")
        for name, ok, detail in liquid:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name:38s} {detail}")
        print(f"\npure water, {os.path.basename(PURE_WATER_TABLE)}:")
        for name, ok, detail in pure:
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
