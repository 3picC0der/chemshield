"""Label policy v1 and the physics screen.

The same four rules do two jobs:
  * labelling the dataset, applied to the hidden TRUE pH before and after a dose;
  * the physics screen inside Model A, applied to the MEASURED pH and the PREDICTED pH.

A dose is harmful when the settled pH after it:
  (a) is outside 5.5-9.5 (the far-side limits), except when the tank was already beyond
      that limit on the same side and the dose moves it toward 7 (a partial recovery
      dose is not harmful just because one dose can't finish the job);
  (b) started outside the 6.3-8.2 stop band and ends more than 0.2 farther from 7;
  (c) crosses from below 6.3 to above 8.2, or the reverse;
  (d) started inside the 6.0-8.5 recovery band and ends outside it, i.e. the dose itself
      would create the unsafe event that INT-S1 reacts to.
(a)-(c) are the report's prototype-v0 rules; (d) was added for the PPR (label policy v1).
"""
from __future__ import annotations

import numpy as np

from .schema import BAND_HI, BAND_LO, FAR_HI, FAR_LO, STOP_HI, STOP_LO


def harmful_rules(current_ph: float, post_ph: float) -> str:
    """Which rules a dose breaks, as 'a,d' style text. Empty string = acceptable."""
    fired = []
    partial_recovery = ((current_ph < FAR_LO and post_ph < FAR_LO) or (current_ph > FAR_HI and post_ph > FAR_HI)) \
        and abs(post_ph - 7.0) <= abs(current_ph - 7.0)
    if (post_ph < FAR_LO or post_ph > FAR_HI) and not partial_recovery:
        fired.append("a")
    if (current_ph < STOP_LO or current_ph > STOP_HI) and \
            abs(post_ph - 7.0) > abs(current_ph - 7.0) + 0.20:
        fired.append("b")
    if (current_ph < STOP_LO and post_ph > STOP_HI) or (current_ph > STOP_HI and post_ph < STOP_LO):
        fired.append("c")
    if BAND_LO <= current_ph <= BAND_HI and not (BAND_LO <= post_ph <= BAND_HI):
        fired.append("d")
    return ",".join(fired)


def is_harmful(current_ph: float, post_ph: float) -> bool:
    return bool(harmful_rules(current_ph, post_ph))


def physics_screen(features: dict) -> str:
    """The rules applied to what the Pi can see: measured pH -> predicted pH."""
    return harmful_rules(float(features["ph_mean_5s"]), float(features["predicted_post_ph"]))


def physics_screen_vec(current: np.ndarray, post: np.ndarray) -> np.ndarray:
    """Vectorised physics screen for training and evaluation: 1 = blocked."""
    current = np.asarray(current, float)
    post = np.asarray(post, float)
    partial = (((current < FAR_LO) & (post < FAR_LO)) | ((current > FAR_HI) & (post > FAR_HI))) \
        & (np.abs(post - 7.0) <= np.abs(current - 7.0))
    a = ((post < FAR_LO) | (post > FAR_HI)) & ~partial
    b = ((current < STOP_LO) | (current > STOP_HI)) & (np.abs(post - 7.0) > np.abs(current - 7.0) + 0.20)
    c = ((current < STOP_LO) & (post > STOP_HI)) | ((current > STOP_HI) & (post < STOP_LO))
    d = (current >= BAND_LO) & (current <= BAND_HI) & ~((post >= BAND_LO) & (post <= BAND_HI))
    return (a | b | c | d).astype(int)
