"""The dose speed is one named setting, and everything that times a dose reads it.

    python -m sim.tests.test_dose_speed      (or: pytest sim/tests)
"""
from __future__ import annotations

import sys
import warnings

import numpy as np

from .. import model as Mo
from .. import rdo, sim2
from ..engine import use_table_chemistry
from ..live import Tank
from ..model import DOSE_SPEED_ML_PER_MIN, P, make_par


def test_one_named_setting():
    assert DOSE_SPEED_ML_PER_MIN == 300.0                       # kept until the syringe is measured
    assert P["dose_speed_ml_per_min"] == DOSE_SPEED_ML_PER_MIN
    assert "Q" not in P


def test_optimiser_time_budget_uses_it():
    par = make_par(dose_speed_ml_per_min=60.0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        use_table_chemistry()
        _c, A, _b, _lb, _ub, _i, meta = rdo.build(4.0, 5.0, {}, par)
    row = meta["names"].index("abort time")
    assert abs(A[row, rdo.idx_v(0, 0)] - 60.0 / 60.0) < 1e-12     # 1 s per mL at 60 mL/min


def test_event_clock_uses_it():
    sc = dict(id=1, name="acid_upset", V=5.0, vol=60.0, acid=True, n0=0.03)
    out = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        use_table_chemistry()
        for speed in (60.0, 300.0):
            rng = np.random.default_rng(5)
            # lam_T ~ 0: the planner's objective prices dose time, so the plan itself would
            # move with the speed; this isolates the event clock
            par = make_par(dose_speed_ml_per_min=speed, lam_T=1e-9)
            r = sim2.run_event(sc, "rdo", rng, Mo.Truth(rng), par)
            out[speed] = r
    slow, fast = out[60.0], out[300.0]
    assert [s["v"] for s in slow["steps"]] == [s["v"] for s in fast["steps"]], "plans differ"
    ml = sum(s["v"] for s in slow["steps"])
    assert abs((slow["t"] - fast["t"]) - ml * (60.0 / 60.0 - 60.0 / 300.0)) < 1e-6


def test_live_tank_uses_it():
    old = P["dose_speed_ml_per_min"]
    try:
        P["dose_speed_ml_per_min"] = 60.0
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r = Tank(seed=1).dose("BASE_BULK", 20.0)
        assert abs(r["runtime_s"] - 20.0) < 1e-9, r                 # 20 mL at 1 mL/s
    finally:
        P["dose_speed_ml_per_min"] = old


TESTS = [test_one_named_setting, test_optimiser_time_budget_uses_it, test_event_clock_uses_it,
         test_live_tank_uses_it]


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
