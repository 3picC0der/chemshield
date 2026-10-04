"""The simulator runs on the tank liquid, 5.000 L distilled water + 0.420 g NaHCO3.

Excess 0 is that liquid as prepared, about pH 8.30. Nothing may quietly assume pH 7.

    python -m sim.tests.test_tank_liquid      (or: pytest sim/tests)
"""
from __future__ import annotations

import os
import sys
import warnings

from .. import chemistry as ch
from ..live import Tank

LIQUID_PH = 8.30


def test_loader_uses_the_liquid_not_pure_water():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ch.reload_tables()
        files = ch.table_files()
        assert os.path.exists(os.path.join(ch.TABLE_DIR, "_placeholder_pure_water_ph_table.csv"))
        assert not any("pure_water" in f or f == "placeholder_ph_table.csv" for f in files), files
        got = ch.ph_from_excess(0.0)
    assert abs(got - LIQUID_PH) <= 0.05, f"excess 0 -> pH {got:.3f} from {files}"


def test_live_tank_starts_on_the_liquid():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tank = Tank(seed=1)
        start = tank.i2()
        tank.upset(60.0, acid=True)
        tank.reset()
        again = tank.i2()
    for msg in (start, again):
        assert abs(msg["ph"] - msg["ph_true"]) < 1e-9, msg
        assert abs(msg["ph"] - LIQUID_PH) <= 0.05, msg


TESTS = [test_loader_uses_the_liquid_not_pure_water, test_live_tank_starts_on_the_liquid]


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
