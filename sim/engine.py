"""Wire the Aspen pH table into the ChemShield process model.

model.py carries the equipment parameters, the truth model and the analytic charge
balance from the report. This module replaces the analytic pH with a lookup in the
CHE table (sim/aspen_tables/), so the whole simulation runs on Aspen's chemistry the
moment those files land. Nothing else in the simulation changes.

Import this module before running anything that calls model.ph().
"""
from __future__ import annotations

from . import chemistry as ch
from . import model as Mo

_ANALYTIC_PH = Mo.ph
_PATCHED = False


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


def use_table_chemistry() -> str:
    """Point model.ph() at the CHE table. Returns 'ASPEN' or 'PLACEHOLDER'."""
    global _PATCHED
    if not _PATCHED:
        Mo.ph = _table_ph
        import sys
        for name in ("sim.sim2", "sim.rdo"):
            mod = sys.modules.get(name)
            if mod is not None and hasattr(mod, "ph"):
                mod.ph = _table_ph
        _PATCHED = True
    return ch.table_provenance()


def use_analytic_chemistry() -> None:
    """Restore the report's closed-form pH (used by the known-answer tests)."""
    global _PATCHED
    Mo.ph = _ANALYTIC_PH
    import sys
    for name in ("sim.sim2", "sim.rdo"):
        mod = sys.modules.get(name)
        if mod is not None and hasattr(mod, "ph"):
            mod.ph = _ANALYTIC_PH
    _PATCHED = False


def buffered_calls() -> int:
    """How many pH evaluations fell back to the analytic buffered model."""
    return _table_ph.buffered
