"""The optimiser must read pH through the same chemistry the tank runs on.

With table chemistry active, model.ph() is the CHE table, so model.n_of() (and the copies
rdo and sim2 imported) must be that table's inverse, not the pure-water charge balance.
These checks load a BUFFERED table on purpose: on the pure-water table the two inverses
agree, which is how the mismatch went unnoticed.

    python -m sim.tests.test_table_inverse      (or: pytest sim/tests)
"""
from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
import warnings


from .. import chemistry as ch
from .. import engine
from .. import model as Mo
from .. import rdo, sim2
from ..make_placeholder_table import grid
from ..model import C, G, P

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PH_CASES = (3.0, 5.0, 6.3, 7.0, 8.2, 9.5, 11.0)
FILLS_L = (4.8, 5.0, 5.3)


@contextlib.contextmanager
def buffered_table(CT: float = 0.002, temps=(25.0, 30.0)):
    """A table for water with a 2 mM weak-acid buffer (pKa 6.35), written in the Aspen
    format from the report's buffered charge balance, loaded in place of aspen_tables/."""
    old = ch.TABLE_DIR
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "buffered_test_table.csv"), "w", encoding="utf-8") as fh:
            fh.write("case,temp_c,excess_mmol,ph\n")
            for t in temps:
                for e in grid():
                    n = -e / 1000.0                                   # acid-positive mol
                    fh.write(f"B,{t:.1f},{e:.6f},{engine._ANALYTIC_PH(n, 5.0, t, CT):.6f}\n")
        ch.TABLE_DIR = d
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            ch.reload_tables()
            engine.use_table_chemistry()
            try:
                yield
            finally:
                ch.TABLE_DIR = old
                ch.reload_tables()


def test_n_of_is_the_table_inverse():
    with buffered_table():
        for mod in (Mo, rdo, sim2):
            for V in FILLS_L:
                for p in PH_CASES:
                    back = Mo.ph(mod.n_of(p, V), V)
                    assert abs(back - p) < 0.005, \
                        f"{mod.__name__}.n_of({p}, {V}) -> pH {back:.4f} on the buffered table"


def test_units_and_volume_scaling():
    with buffered_table():
        for V in FILLS_L:
            for p in PH_CASES:
                excess = ch.excess_from_ph(p, 25.0, V)                 # base-positive mmol in V
                assert abs(rdo.n_of(p, V) - (-excess / 1000.0)) < 1e-12
                # same concentration, bigger tank: moles scale with the fill
                assert abs(rdo.n_of(p, V) - rdo.n_of(p, 5.0) * V / 5.0) < 1e-9


def test_inverse_between_table_temperatures():
    with buffered_table():
        for p in PH_CASES:
            back = ch.ph_from_excess(ch.excess_from_ph(p, 27.5), 27.5)
            assert abs(back - p) < 1e-6, f"pH {p} at 27.5 C round-trips to {back:.6f}"


def test_planner_block_lands_in_stop_band_on_buffered_tank():
    """From pH 5 in a buffered tank, exact doses and exact reads: the MILP must reach the
    stop band without crossing it. Reading pH through pure water it moves ~1 % of the way."""
    lo, hi = P["stop"]
    with buffered_table():
        V = 5.0
        n = ch.to_optimiser_n(ch.excess_from_ph(5.0, 25.0, V))          # the true tank
        for _ in range(6):
            pH = Mo.ph(n, V)
            if lo <= pH <= hi:
                break
            s = rdo.solve(pH, V, {}, P)
            assert s["doses"], f"no dose planned at pH {pH:.3f} ({s['status']})"
            for p, v in s["doses"]:
                n -= G[p] * v / 1000.0 * C[p]
                V += v / 1000.0
                assert Mo.ph(n, V) <= hi + 1e-9, f"overshot to pH {Mo.ph(n, V):.3f}"
        assert lo <= Mo.ph(n, V) <= hi, f"still at pH {Mo.ph(n, V):.3f} after 6 blocks"


def test_planner_entry_point_uses_the_table():
    """The gateway calls redosing.planner directly, with no sim.batch or sim.live first."""
    code = ("import warnings; warnings.simplefilter('ignore')\n"
            "from redosing import planner\n"
            "from sim import engine, rdo\n"
            "planner.plan_block({'ph': 5.0})\n"
            "print(rdo.n_of is engine._table_n_of)\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert out.stdout.strip().endswith("True"), out.stdout + out.stderr


def test_analytic_path_kept_for_known_answers():
    try:
        engine.use_analytic_chemistry()
        for V in FILLS_L:
            for p in PH_CASES:
                h = 10.0 ** -p
                assert abs(rdo.n_of(p, V) - (h - Mo.Kw(25.0) / h) * V) < 1e-15
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            engine.use_table_chemistry()


TESTS = [test_n_of_is_the_table_inverse, test_units_and_volume_scaling,
         test_inverse_between_table_temperatures,
         test_planner_block_lands_in_stop_band_on_buffered_tank,
         test_planner_entry_point_uses_the_table, test_analytic_path_kept_for_known_answers]


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
