"""Tank chemistry for the ChemShield simulator.

The pH comes from a lookup table that CHE exports from Aspen Plus
(see aspen_tables/README.md for the file format). Until those tables arrive, a
placeholder table for the tank liquid (5.000 L distilled water + 0.420 g NaHCO3, closed
carbonate model, see make_placeholder_table.py) is used and every output is labelled
PLACEHOLDER. excess_mmol = 0 is that liquid as prepared, about pH 8.30, not pH 7.

Sign convention in this module follows the team's I2 contract and the Aspen tables:
    excess_mmol  >0 = extra strong base, <0 = extra strong acid, for a 5.000 L tank.
The optimiser in redosing/ uses the opposite (acid-positive, mol); convert with
to_optimiser_n() / from_optimiser_n() at the boundary, never by hand.
"""
from __future__ import annotations
import glob
import os
import warnings

import numpy as np
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
TABLE_DIR = os.path.join(HERE, "aspen_tables")
BASIS_L = 5.0                      # every table row is for a 5.000 L tank
_CACHE: dict | None = None


def _kw(temp_c: float) -> float:
    """pKw(T), quadratic through 0, 25 and 50 C. Used only to move between pH and the
    net strong-acid concentration when interpolating; it never overrides table pH."""
    return 10.0 ** -(14.94 - 0.0416 * temp_c + 0.00016 * temp_c * temp_c)


def _ph_of_c(c: float, temp_c: float) -> float:
    """pH from the net strong-acid concentration c = [H+] - [OH-] (mol/L)."""
    k = _kw(temp_c)
    h = 0.5 * (c + np.sqrt(c * c + 4.0 * k)) if c > 0 else k / (0.5 * (-c + np.sqrt(c * c + 4.0 * k)))
    return float(-np.log10(h))


# --------------------------------------------------------------------- loading
def _read_csv(path: str) -> list[tuple[float, float, float]]:
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        header = [c.strip().lower() for c in fh.readline().split(",")]
        need = {"temp_c", "excess_mmol", "ph"}
        missing = need - set(header)
        if missing:
            raise ValueError(f"{os.path.basename(path)}: missing column(s) {sorted(missing)}. "
                             f"Required header: case,temp_c,excess_mmol,ph")
        it, ie, ip = header.index("temp_c"), header.index("excess_mmol"), header.index("ph")
        for ln, line in enumerate(fh, start=2):
            if not line.strip():
                continue
            f = line.split(",")
            try:
                rows.append((float(f[it]), float(f[ie]), float(f[ip])))
            except (ValueError, IndexError) as exc:
                raise ValueError(f"{os.path.basename(path)} line {ln}: {exc}") from exc
    return rows


def _load(paths: list[str] | None = None) -> dict:
    """Build {temp_c: (excess_mmol asc, ph)} from every CSV in aspen_tables/, or from
    exactly the given files (the known-answer tests use this for the pure-water table)."""
    global _CACHE
    if _CACHE is not None and paths is None:
        return _CACHE
    if paths is None:
        files = sorted(p for p in glob.glob(os.path.join(TABLE_DIR, "*.csv"))
                       if not os.path.basename(p).startswith("_"))
        if not files:
            raise FileNotFoundError(
                f"No pH table in {TABLE_DIR}. Run `python -m sim.make_placeholder_table` "
                f"or drop the Aspen CSVs in (see aspen_tables/README.md).")
        real = [p for p in files if "placeholder" not in os.path.basename(p).lower()]
        use = real or files
    else:
        real = [p for p in paths if "placeholder" not in os.path.basename(p).lower()]
        use = list(paths)
    source = "ASPEN" if real and len(real) == len(use) else "PLACEHOLDER"
    if source == "PLACEHOLDER":
        warnings.warn("sim.chemistry is using the PLACEHOLDER pH table, not Aspen output. "
                      "Every result is labelled chem_source=PLACEHOLDER.", stacklevel=3)

    by_t: dict[float, list[tuple[float, float]]] = {}
    for path in use:
        for t, e, p in _read_csv(path):
            by_t.setdefault(round(float(t), 3), []).append((e, p))

    tables = {}
    for t, pts in by_t.items():
        pts = sorted(set(pts))
        e = np.array([q[0] for q in pts], float)
        p = np.array([q[1] for q in pts], float)
        keep = np.concatenate(([True], np.diff(e) > 0))       # drop duplicate abscissae
        e, p = e[keep], p[keep]
        if np.any(np.diff(p) < -1e-6):
            bad = int(np.argmin(np.diff(p)))
            raise ValueError(
                f"pH table at {t} C is not increasing in excess_mmol near "
                f"excess_mmol={e[bad]:.4f} (pH {p[bad]:.3f} -> {p[bad + 1]:.3f}). "
                f"The usual cause is a flipped sign: excess_mmol must be NEGATIVE for "
                f"extra acid. See aspen_tables/README.md.")
        # Interpolating pH directly is poor near neutral, where pH moves ~2 units over
        # 0.01 mmol and the table's grid is 0.002 mmol. Interpolate the net strong-acid
        # concentration c = [H+] - [OH-] instead: c is exactly linear in excess_mmol for a
        # strong acid/base system, so the interpolation error collapses to the table's own
        # accuracy. pH is recovered from c by the same charge balance. With a buffered
        # liquid c is no longer linear in excess, so there the accuracy rests on the
        # table's own spacing across the buffer and equivalence regions.
        h = 10.0 ** (-p)
        c = h - _kw(t) / h
        tables[t] = (e, p, c)

    _CACHE = dict(tables=tables, temps=np.array(sorted(tables)), source=source,
                  files=[os.path.basename(p) for p in use])
    return _CACHE


def reload_tables(paths: list[str] | None = None) -> dict:
    """Forget the cached tables (call after dropping new Aspen CSVs in). With paths,
    load exactly those files instead of the folder; reload_tables() goes back."""
    global _CACHE
    _CACHE = None
    return _load(paths)


def table_provenance() -> str:
    """'ASPEN' or 'PLACEHOLDER'. Goes into every evidence CSV."""
    return _load()["source"]


def table_files() -> list[str]:
    return list(_load()["files"])


# ------------------------------------------------------------------- the model
def _bracket(temps: np.ndarray, temp_c: float) -> tuple[float, float, float]:
    """The two table temperatures around temp_c and the blend weight of the upper one.
    Outside the table's range the nearest end is used on its own (w = 0)."""
    if len(temps) == 1 or temp_c <= temps[0]:
        return temps[0], temps[0], 0.0
    if temp_c >= temps[-1]:
        return temps[-1], temps[-1], 0.0
    i = int(np.searchsorted(temps, temp_c))
    t_lo, t_hi = temps[i - 1], temps[i]
    return t_lo, t_hi, (temp_c - t_lo) / (t_hi - t_lo)


def ph_from_excess(excess_mmol: float, temp_c: float = 25.0,
                   volume_L: float = BASIS_L) -> float:
    """pH of the tank.

    excess_mmol : net strong-base excess, base-positive (mmol).
    volume_L    : current fill. The table is for 5.000 L, so it is looked up at
                  excess_mmol * 5.0 / volume_L, which is the dilution correction.
    """
    d = _load()
    x = float(excess_mmol) * BASIS_L / float(volume_L)
    t_lo, t_hi, w = _bracket(d["temps"], temp_c)
    e_lo, _p_lo, c_lo = d["tables"][t_lo]
    lo = _ph_of_c(float(np.interp(x, e_lo, c_lo)), t_lo)
    if w == 0.0:
        return lo
    e_hi, _p_hi, c_hi = d["tables"][t_hi]
    hi = _ph_of_c(float(np.interp(x, e_hi, c_hi)), t_hi)
    return lo * (1.0 - w) + hi * w


def excess_from_ph(ph_value: float, temp_c: float = 25.0,
                   volume_L: float = BASIS_L) -> float:
    """Inverse lookup: the excess (base-positive mmol) that gives this pH.

    The exact inverse of ph_from_excess() at the same temperature and fill, so the
    optimiser's reading of a pH and the simulated tank agree."""
    d = _load()
    t_lo, t_hi, w = _bracket(d["temps"], temp_c)
    e, _p, c = d["tables"][t_lo]
    if w == 0.0:
        # invert in c-space for the same reason the forward lookup uses it: c is linear
        # in excess, pH is not. c descends as excess rises, so flip for np.interp.
        h = 10.0 ** (-float(ph_value))
        c_target = h - _kw(t_lo) / h
        x = float(np.interp(c_target, c[::-1], e[::-1]))
    else:
        # between two table temperatures the forward lookup blends their pH, so invert
        # that blend numerically; it is monotone in excess, so the root is unique
        lo_x = max(e[0], d["tables"][t_hi][0][0])
        hi_x = min(e[-1], d["tables"][t_hi][0][-1])
        f = lambda xx: ph_from_excess(xx, temp_c) - float(ph_value)  # noqa: E731
        if f(lo_x) >= 0.0:
            x = lo_x
        elif f(hi_x) <= 0.0:
            x = hi_x
        else:
            x = float(brentq(f, lo_x, hi_x, xtol=1e-10))
    return x * float(volume_L) / BASIS_L


# ------------------------------------------------- boundary with the optimiser
def to_optimiser_n(excess_mmol: float) -> float:
    """I2/Aspen convention (base-positive mmol) -> optimiser convention (acid-positive mol)."""
    return -float(excess_mmol) / 1000.0


def from_optimiser_n(n_mol: float) -> float:
    """Optimiser convention (acid-positive mol) -> I2/Aspen convention (base-positive mmol)."""
    return -float(n_mol) * 1000.0


if __name__ == "__main__":
    d = _load()
    print(f"source     : {d['source']}")
    print(f"files      : {', '.join(d['files'])}")
    print(f"temperatures: {', '.join(f'{t:g}' for t in d['temps'])} C")
    for t in d["temps"]:
        e, p, _c = d["tables"][t]
        print(f"  {t:g} C : {len(e)} points, excess {e[0]:+.3f} .. {e[-1]:+.3f} mmol, "
              f"pH {p[0]:.3f} .. {p[-1]:.3f}")
    print("\nspot checks at 25 C, 5.000 L:")
    for ex in (-10.0, -0.5, 0.0, 0.5, 10.0):
        print(f"  {ex:+7.3f} mmol -> pH {ph_from_excess(ex):.3f}")
