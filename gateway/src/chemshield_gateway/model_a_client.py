from __future__ import annotations

import time
from typing import Any

from .config import GatewayConfig
from .models import ProcessState


class FakeModelAClient:
    """Safe stand-in for Belal's Model A.

    The interface matches the planned I3 output: label, score, model_version,
    and latency_ms. This lets Khalid test the gateway before the final model is
    integrated.
    """

    def __init__(self, config: GatewayConfig) -> None:
        self.config = config

    def predict(self, command: dict[str, Any], state: ProcessState) -> dict[str, Any]:
        start = time.perf_counter()
        volume = float(command.get("volume_ml", 0.0))
        reagent = str(command.get("reagent", "none"))
        ph = float(state.ph)

        # Simple deterministic safety logic for integration tests.
        label = "ACCEPTABLE_CONTEXT"
        score = 0.12
        if state.mode == "SAFE_HOLD" or not state.level_ok:
            label, score = "HARMFUL_CONTEXT", 0.97
        elif reagent == "base" and ph >= 9.0:
            label, score = "HARMFUL_CONTEXT", 0.91
        elif reagent == "acid" and ph <= 5.5:
            label, score = "HARMFUL_CONTEXT", 0.91
        elif volume >= 18.0 or state.mixing_lockout_remaining_s > 0:
            label, score = "UNCERTAIN_CONTEXT", 0.63

        return {
            "label": label,
            "score": score,
            "model_version": "A-STANDIN-0.1",
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 4),
        }
