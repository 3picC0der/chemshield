"""Fixed names, versions and limits shared by training and the live Pi.

Everything that must be identical between the dataset generator and the gateway call
lives here, so the two can never drift apart.
"""
from __future__ import annotations

FEATURE_SCHEMA_VERSION = "fs-1"
LABEL_POLICY_VERSION = "v1"          # prototype-v0 rules (a)-(c) plus rule (d)
MODEL_VERSION = "A-1.0-ppr"

# The 16 features from report Section 1.3, in the order the model sees them.
FEATURES = [
    "ph_mean_5s",
    "ph_slope_5s",
    "ph_curvature_5s",
    "ph_std_5s",
    "sample_age_s",
    "candidate_direction",
    "candidate_mmol",
    "predicted_post_ph",
    "predicted_safety_margin",
    "cumulative_signed_mmol",
    "cumulative_abs_mmol",
    "request_delivery_residual",
    "measured_predicted_residual",
    "mixer_speed_ratio",
    "level_margin_l",
    "heartbeat_age_s",
]

# Features with no sensor at the PPR (hand dosing, hand stirring). They are the same
# constant in training and live, so the model learns to ignore them.
FIXED_FEATURES = {"request_delivery_residual": 0.0, "mixer_speed_ratio": 1.0}

# Bottle -> (molarity mol/L, direction). Direction follows the prototype: acid +1, base -1.
CHANNELS = {
    "ACID_BULK": (0.5, +1),
    "ACID_FINE": (0.005, +1),
    "BASE_BULK": (0.5, -1),
    "BASE_FINE": (0.005, -1),
}

ACCEPTABLE = "ACCEPTABLE_CONTEXT"
HARMFUL = "HARMFUL_CONTEXT"
UNCERTAIN = "UNCERTAIN_CONTEXT"
LABELS = (ACCEPTABLE, HARMFUL, UNCERTAIN)

# pH window: the last 5 probe readings (the Uno sends one per second).
WINDOW_SAMPLES = 5
WINDOW_MIN_SPAN_S = 2.0      # 5 readings bunched closer than this are not a real 5 s window
WINDOW_MAX_SPAN_S = 6.0      # ... and must all be newer than this
MAX_SAMPLE_AGE_S = 2.0       # newest reading older than this -> UNCERTAIN (stale probe)
MAX_HEARTBEAT_AGE_S = 2.0    # no line from the Uno for this long -> UNCERTAIN (I5 uses 2 s too)

DEADLINE_MS = 100.0          # I3: no answer within 100 ms -> UNCERTAIN
MAX_DOSE_ML = 20.0           # S2 cap; the gateway enforces it before Model A is called
CUMULATIVE_WINDOW_S = 600.0  # features 10, 11 and 13 look back this far in the dose log
V_NOMINAL_L = 5.0            # working fill
V_LIMIT_L = 5.5              # high-level limit used for the level margin
TEMP_C = 25.0                # no temperature sensor on the PPR rig

# Safety bands used by the label rules and the physics screen.
FAR_LO, FAR_HI = 5.5, 9.5    # INT-S3 far-side limits
STOP_LO, STOP_HI = 6.3, 8.2  # internal stop band (report / planner)
BAND_LO, BAND_HI = 6.0, 8.5  # recovery band (INT-S1 confirms an unsafe event outside it)
