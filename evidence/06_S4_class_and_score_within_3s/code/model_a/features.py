"""The 16 Model A features, computed the same way in training and on the Pi.

Inputs are only what the real system can see:
  * probe readings as (time, pH) pairs, stamped with the Pi's clock when each `PH,x`
    line arrives from the Uno;
  * the dose request (bottle and mL);
  * the Pi's own dose log (what the gateway accepted since the tank was filled);
  * when the Uno last sent anything (heartbeat);
  * the pH table in sim/aspen_tables/, through sim.chemistry (the planner's table).

build_features() returns the features plus a list of problems. Any problem makes Model A
answer UNCERTAIN_CONTEXT (fail closed).
"""
from __future__ import annotations

import math
import os
from typing import Iterable, Sequence

import numpy as np

from .schema import (
    CHANNELS,
    CUMULATIVE_WINDOW_S,
    FEATURES,
    FIXED_FEATURES,
    FAR_HI,
    FAR_LO,
    MAX_DOSE_ML,
    MAX_HEARTBEAT_AGE_S,
    MAX_SAMPLE_AGE_S,
    TEMP_C,
    V_LIMIT_L,
    V_NOMINAL_L,
    WINDOW_MAX_SPAN_S,
    WINDOW_MIN_SPAN_S,
    WINDOW_SAMPLES,
)


_TABLE_DIR_IN_USE: str | None = None


def default_chemistry():
    """The planner's pH table (sim/aspen_tables/ via sim.chemistry).

    Testing only: set MODEL_A_TABLE_DIR to read the table from another folder. It moves
    sim.chemistry itself, so the planner and Model A still use the same table.
    """
    global _TABLE_DIR_IN_USE
    from sim import chemistry
    folder = os.environ.get("MODEL_A_TABLE_DIR")
    if folder and folder != _TABLE_DIR_IN_USE:
        chemistry.TABLE_DIR = folder
        chemistry.reload_tables()
        _TABLE_DIR_IN_USE = folder
    return chemistry


def signed_mmol(channel_id: str, dose_ml: float) -> float:
    """Reagent in a dose, acid-positive (the prototype's direction convention)."""
    molarity, direction = CHANNELS[channel_id]
    return direction * molarity * float(dose_ml)


def window_stats(samples: Sequence[tuple[float, float]], now: float):
    """Mean, slope (pH/s), curvature (pH/s^2) and spread of the last 5 readings.

    Returns (mean, slope, curvature, std, sample_age_s, problem). problem is '' when the
    window is usable.
    """
    if not samples:
        return (math.nan,) * 4 + (math.inf, "INSUFFICIENT_DATA")
    newest_t = samples[-1][0]
    age = now - newest_t
    last = samples[-WINDOW_SAMPLES:]
    if len(last) < WINDOW_SAMPLES:
        return (math.nan,) * 4 + (age, "INSUFFICIENT_DATA")
    t = np.array([s[0] for s in last], float)
    y = np.array([s[1] for s in last], float)
    span = t[-1] - t[0]
    if span < WINDOW_MIN_SPAN_S or span > WINDOW_MAX_SPAN_S:
        return (math.nan,) * 4 + (age, "INSUFFICIENT_DATA")
    tc = t - t[-1]
    slope = float(np.polyfit(tc, y, 1)[0])
    curvature = float(2.0 * np.polyfit(tc, y, 2)[0])
    return float(y.mean()), slope, curvature, float(y.std()), float(age), ""


def predict_post_ph(chem, ph_now: float, channel_id: str, dose_ml: float,
                    volume_L: float, temp_c: float = TEMP_C) -> float:
    """What the Pi expects the settled pH to be after this dose (the planner's table)."""
    excess_now = chem.excess_from_ph(ph_now, temp_c, volume_L)        # base-positive mmol
    excess_after = excess_now - signed_mmol(channel_id, dose_ml)      # acid lowers it
    return float(chem.ph_from_excess(excess_after, temp_c, volume_L + float(dose_ml) / 1000.0))


def build_features(
    samples: Sequence[tuple[float, float]],
    now: float,
    channel_id: str | None,
    dose_ml,
    dose_log: Iterable[dict],
    last_uno_t: float | None,
    chem=None,
    volume_start_L: float = V_NOMINAL_L,
    temp_c: float = TEMP_C,
) -> tuple[dict, list[str]]:
    """The 16 features for one dose request, and the reasons it can't be judged (if any).

    dose_log: every dose the gateway accepted since the tank was filled, oldest first,
    as dicts with keys t, channel_id, dose_ml, predicted_post_ph.
    """
    problems: list[str] = []
    feats = {name: math.nan for name in FEATURES}
    feats.update(FIXED_FEATURES)

    if channel_id not in CHANNELS:
        problems.append("BAD_CHANNEL")
    try:
        dose = float(dose_ml)
    except (TypeError, ValueError):
        dose = math.nan
    if not (math.isfinite(dose) and 0.0 < dose <= MAX_DOSE_ML):
        problems.append("BAD_DOSE")

    mean, slope, curv, std, age, window_problem = window_stats(samples, now)
    feats.update(ph_mean_5s=mean, ph_slope_5s=slope, ph_curvature_5s=curv, ph_std_5s=std,
                 sample_age_s=age)
    if window_problem:
        problems.append(window_problem)
    elif age > MAX_SAMPLE_AGE_S:
        problems.append("STALE_SAMPLE")

    hb_age = math.inf if last_uno_t is None else now - last_uno_t
    feats["heartbeat_age_s"] = hb_age
    if hb_age > MAX_HEARTBEAT_AGE_S:
        problems.append("HEARTBEAT_LOST")

    log = list(dose_log)
    added_ml = sum(float(d["dose_ml"]) for d in log)
    volume_hat = volume_start_L + added_ml / 1000.0
    feats["level_margin_l"] = V_LIMIT_L - volume_hat

    recent = [d for d in log if now - float(d["t"]) <= CUMULATIVE_WINDOW_S]
    feats["cumulative_signed_mmol"] = sum(signed_mmol(d["channel_id"], d["dose_ml"]) for d in recent)
    feats["cumulative_abs_mmol"] = sum(abs(signed_mmol(d["channel_id"], d["dose_ml"])) for d in recent)

    if channel_id in CHANNELS and "BAD_DOSE" not in problems:
        molarity, direction = CHANNELS[channel_id]
        feats["candidate_direction"] = float(direction)
        feats["candidate_mmol"] = molarity * dose
        if math.isfinite(mean):
            chem = chem or default_chemistry()
            post = predict_post_ph(chem, mean, channel_id, dose, volume_hat, temp_c)
            feats["predicted_post_ph"] = post
            feats["predicted_safety_margin"] = min(post - FAR_LO, FAR_HI - post)

    last_pred = next((d.get("predicted_post_ph") for d in reversed(recent)
                      if d.get("predicted_post_ph") is not None), None)
    if last_pred is None:
        feats["measured_predicted_residual"] = 0.0
    else:
        feats["measured_predicted_residual"] = (mean - float(last_pred)) if math.isfinite(mean) else math.nan

    if not problems and not all(math.isfinite(feats[n]) for n in FEATURES):
        problems.append("BAD_FEATURE")
    return feats, problems


def as_vector(feats: dict) -> np.ndarray:
    return np.array([feats[n] for n in FEATURES], dtype=float)
