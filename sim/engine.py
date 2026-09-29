"""Wire the Aspen pH table into the ChemShield process model.

model.py carries the equipment parameters, the truth model and the analytic charge
balance from the report. This module replaces the analytic pH, and its inverse n_of(),
with a lookup in the CHE table (sim/aspen_tables/), so the whole simulation, including
the optimiser's view of the tank, runs on Aspen's chemistry the moment those files land.
Nothing else in the simulation changes.

Import this module before running anything that calls model.ph() or model.n_of().
"""
from __future__ import annotations

import sys

from . import chemistry as ch
from . import model as Mo

_ANALYTIC_PH = Mo.ph
_ANALYTIC_N_OF = Mo.n_of
_PATCHED = False
_CHOSEN = False                          # has any caller picked a chemistry yet?
_USERS = ("sim.sim2", "sim.rdo")         # modules that import ph / n_of by name


def _table_ph(n, V, T=25.0, CT=0.0, pKa=6.35):
    """Drop-in replacement for model.ph().

    n  : net excess strong ACID, mol (the optimiser's convention)
    V  : tank fill, L
    CT : weak-acid buffer. The Aspen tables are unbuffered, so any buffered case
         (used only for fault injection, assumption B1) falls back to the analytic
         solution and is flagged by buffered_calls().
    """
    if CT and CT > 0:
        _table_ph.buffered += 1
        return _ANALYTIC_PH(n, V, T, CT, pKa)
    return ch.ph_from_excess(ch.from_optimiser_n(n), T, V)


_table_ph.buffered = 0


def _table_n_of(pH, V, T=25.0):
    """Drop-in replacement for model.n_of(): the exact inverse of _table_ph().

    excess_from_ph() returns base-positive mmol already scaled from the 5.000 L table
    basis to the fill V, so only the sign and mmol -> mol change here. Without this the
    optimiser would read every pH through the pure-water formula, whatever the tank holds.
    """
    return ch.to_optimiser_n(ch.excess_from_ph(pH, T, V))


def _point(name: str, fn) -> None:
    setattr(Mo, name, fn)
    for mod_name in _USERS:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, name):
            setattr(mod, name, fn)


def use_table_chemistry() -> str:
    """Point model.ph() and model.n_of() at the CHE table. Returns 'ASPEN' or 'PLACEHOLDER'."""
    global _PATCHED, _CHOSEN
    if not _PATCHED:
        _point("ph", _table_ph)
        _point("n_of", _table_n_of)
        _PATCHED = True
    _CHOSEN = True
    return ch.table_provenance()


def use_analytic_chemistry() -> None:
    """Restore the report's closed-form pH and its inverse (used by the known-answer tests)."""
    global _PATCHED, _CHOSEN
    _point("ph", _ANALYTIC_PH)
    _point("n_of", _ANALYTIC_N_OF)
    _PATCHED = False
    _CHOSEN = True


def ensure_table_chemistry() -> None:
    """Table chemistry, unless a caller already chose the analytic model on purpose.

    For entry points such as the I4 planner that the gateway calls directly, without
    going through sim.batch or sim.live first."""
    if not _CHOSEN:
        use_table_chemistry()


def buffered_calls() -> int:
    """How many pH evaluations fell back to the analytic buffered model."""
    return _table_ph.buffered
