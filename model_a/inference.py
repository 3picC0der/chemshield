"""Model A on the Pi: the call Khalid's gateway makes for every dose request (I3).

    from model_a.inference import ModelAClient, ProcessContext

    context = ProcessContext()                    # shared with the serial bridge and the loop
    model_a = ModelAClient(context=context)       # loads the model once, then one warm-up call
    gateway = GatewayValidator(model_a=model_a)   # drop-in for Khalid's FakeModelAClient

    # serial bridge, for every line from the Uno:
    context.mark_uno_alive()                      # any line counts as a heartbeat
    context.add_sample(7.02)                      # for each `PH,7.02` line
    # control loop, when an accepted dose has been added to the tank:
    model_a.dose_added(command_id)

predict(command, state) returns the I3 answer:
    {"label": "HARMFUL_CONTEXT", "score": 0.93, "model_version": "A-1.0-ppr",
     "latency_ms": 2.1, "reason": "MODEL_RISK", "threshold": 0.35}
"label", "score", "model_version" and "latency_ms" are the I3 contract; "reason" and
"threshold" are extra. Anything that goes wrong (missing bottle name, stale or missing
probe data, a feature outside the training range, a missing model file, an error, or no
answer within 100 ms) gives UNCERTAIN_CONTEXT with score 1.0. Model A never raises into
the gateway.
"""
from __future__ import annotations

import csv
import math
import queue
import threading
import time
import warnings
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .features import build_features
from .policy import physics_screen
from .schema import (
    ACCEPTABLE,
    DEADLINE_MS,
    FEATURE_SCHEMA_VERSION,
    FEATURES,
    HARMFUL,
    MAX_HEARTBEAT_AGE_S,
    MAX_SAMPLE_AGE_S,
    MODEL_VERSION,
    TEMP_C,
    UNCERTAIN,
    V_NOMINAL_L,
)

HERE = Path(__file__).resolve().parent
DEFAULT_ARTIFACT = HERE / "artifacts" / "model_a.joblib"
RANGE_MARGIN = 0.10   # a live feature may exceed the training range by 10% of that range


class ModelA:
    """The trained model plus the physics screen and the fail-closed rules."""

    def __init__(self, artifact_path: str | Path = DEFAULT_ARTIFACT, chem=None):
        import joblib
        import sklearn

        art = joblib.load(artifact_path)
        if list(art["features"]) != FEATURES or art.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError(f"{artifact_path}: feature schema does not match this code; retrain "
                             f"with `python -m model_a.train`")
        if art.get("sklearn_version") != sklearn.__version__:
            warnings.warn(f"Model A was trained with scikit-learn {art.get('sklearn_version')} but "
                          f"this is {sklearn.__version__}. Retrain on this machine with "
                          f"`python -m model_a.train` if anything looks off.", stacklevel=2)
        self.model = art["model"]
        self.threshold = float(art["threshold"])
        self.version = str(art.get("model_version", MODEL_VERSION))
        lo = np.array([art["feature_ranges"][n][0] for n in FEATURES], float)
        hi = np.array([art["feature_ranges"][n][1] for n in FEATURES], float)
        pad = RANGE_MARGIN * (hi - lo) + 1e-9
        self.lo, self.hi = lo - pad, hi + pad
        self.chem = chem
        self.debug_delay_s = 0.0          # test hook: simulate a frozen model (ICS-AT-03 timeout step)
        self.model.predict_proba(((self.lo + self.hi) / 2.0).reshape(1, -1))   # warm-up

    def decide(self, feats: dict, problems: list[str]) -> dict:
        """label, score and reason for one set of features."""
        if self.debug_delay_s:
            time.sleep(self.debug_delay_s)
        if problems:
            return {"label": UNCERTAIN, "score": 1.0, "reason": problems[0]}
        x = np.array([feats[n] for n in FEATURES], float)
        if not np.all(np.isfinite(x)):
            return {"label": UNCERTAIN, "score": 1.0, "reason": "BAD_FEATURE"}
        # second line of defence, in case a caller built the features without the checks
        if feats["sample_age_s"] > MAX_SAMPLE_AGE_S:
            return {"label": UNCERTAIN, "score": 1.0, "reason": "STALE_SAMPLE"}
        if feats["heartbeat_age_s"] > MAX_HEARTBEAT_AGE_S:
            return {"label": UNCERTAIN, "score": 1.0, "reason": "HEARTBEAT_LOST"}
        rules = physics_screen(feats)
        if rules:
            return {"label": HARMFUL, "score": 1.0, "reason": f"PREDICTED_UNSAFE:{rules}"}
        outside = np.flatnonzero((x < self.lo) | (x > self.hi))
        if outside.size:
            return {"label": UNCERTAIN, "score": 1.0, "reason": f"OUT_OF_RANGE:{FEATURES[outside[0]]}"}
        risk = float(self.model.predict_proba(x.reshape(1, -1))[0, 1])
        if risk >= self.threshold:
            return {"label": HARMFUL, "score": risk, "reason": "MODEL_RISK"}
        return {"label": ACCEPTABLE, "score": risk, "reason": "OK"}


class ProcessContext:
    """What the Pi knows about the tank, shared by the serial bridge, the loop and Model A.

    Times come from time.monotonic(), so a clock change on the Pi (for example when it
    gets network time) can't make readings look stale.
    """

    def __init__(self, volume_start_L: float = V_NOMINAL_L, temp_c: float = TEMP_C,
                 clock=time.monotonic, max_samples: int = 120):
        self.clock = clock
        self.temp_c = float(temp_c)
        self._lock = threading.Lock()
        self._samples: deque[tuple[float, float]] = deque(maxlen=max_samples)
        self._dose_log: list[dict] = []
        self._last_uno_t: float | None = None
        self._volume_start_L = float(volume_start_L)

    def add_sample(self, ph: float, t: float | None = None) -> None:
        """One probe reading (a `PH,x` line from the Uno). It also counts as a heartbeat."""
        t = self.clock() if t is None else t
        with self._lock:
            self._samples.append((t, float(ph)))
            self._last_uno_t = t

    def mark_uno_alive(self, t: float | None = None) -> None:
        """Any line from the Uno (OK, DONE, STATUS, ...) proves the link is alive."""
        with self._lock:
            self._last_uno_t = self.clock() if t is None else t

    def record_dose(self, channel_id: str, dose_ml: float, predicted_post_ph: float | None = None,
                    t: float | None = None) -> None:
        with self._lock:
            self._dose_log.append({"t": self.clock() if t is None else t, "channel_id": channel_id,
                                   "dose_ml": float(dose_ml), "predicted_post_ph": predicted_post_ph})

    def reset_tank(self, volume_L: float = V_NOMINAL_L) -> None:
        """Fresh tank: forget the dose log (the probe history stays)."""
        with self._lock:
            self._dose_log.clear()
            self._volume_start_L = float(volume_L)

    def snapshot(self) -> dict:
        with self._lock:
            return {"now": self.clock(), "samples": list(self._samples), "dose_log": list(self._dose_log),
                    "last_uno_t": self._last_uno_t, "volume_start_L": self._volume_start_L,
                    "temp_c": self.temp_c}


class _DeadlineRunner:
    """Runs the model on a worker thread so a hung call can be abandoned after the deadline."""

    def __init__(self) -> None:
        self._start()

    def _start(self) -> None:
        self._q: queue.SimpleQueue = queue.SimpleQueue()
        threading.Thread(target=self._loop, args=(self._q,), daemon=True, name="model-a").start()

    @staticmethod
    def _loop(q: queue.SimpleQueue) -> None:
        while True:
            fn, args, box, done = q.get()
            try:
                box["value"] = fn(*args)
            except BaseException as exc:     # noqa: BLE001 - reported to the caller, never raised
                box["error"] = exc
            done.set()

    def run(self, fn, args, timeout_s: float):
        box: dict = {}
        done = threading.Event()
        self._q.put((fn, args, box, done))
        if not done.wait(timeout_s):
            self._start()                    # leave the stuck worker behind (daemon thread)
            return "TIMEOUT", None
        if "error" in box:
            return "MODEL_ERROR", box["error"]
        return "OK", box["value"]


class DecisionLog:
    """model_a_decisions.csv: one row per decision, with every feature (the S4 data)."""

    COLUMNS = ["time_utc", "command_id", "channel_id", "dose_ml", "label", "score", "reason",
               "latency_ms", "model_version"] + FEATURES

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new = not self.path.exists() or self.path.stat().st_size == 0
        self._fh = open(self.path, "a", newline="", encoding="utf-8")
        self._w = csv.writer(self._fh)
        self._lock = threading.Lock()
        if new:
            self._w.writerow(self.COLUMNS)
            self._fh.flush()

    def write(self, command_id, channel_id, dose_ml, out: dict, feats: dict | None) -> None:
        feats = feats or {}
        row = [datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
               command_id, channel_id, dose_ml, out["label"], out["score"], out["reason"],
               out["latency_ms"], out["model_version"]]
        row += [_fmt(feats.get(n)) for n in FEATURES]
        with self._lock:
            self._w.writerow(row)
            self._fh.flush()


def _fmt(v):
    if v is None:
        return ""
    return round(v, 6) if isinstance(v, float) and math.isfinite(v) else v


class ModelAClient:
    """Drop-in replacement for Khalid's FakeModelAClient: predict(command, state) -> I3."""

    def __init__(self, config=None, context: ProcessContext | None = None,
                 artifact_path: str | Path | None = None, chem=None,
                 deadline_ms: float = DEADLINE_MS, decision_log: str | Path | None = None,
                 model: ModelA | None = None):
        self.config = config
        self.context = context or ProcessContext()
        self.deadline_s = float(deadline_ms) / 1000.0
        self.load_error = ""
        self.model = model
        if self.model is None:
            try:
                self.model = ModelA(artifact_path or DEFAULT_ARTIFACT, chem=chem)
            except Exception as exc:          # noqa: BLE001 - the gateway must keep running
                self.load_error = f"{type(exc).__name__}: {exc}"
                warnings.warn(f"Model A could not load ({self.load_error}); every request will be "
                              f"UNCERTAIN_CONTEXT until this is fixed.", stacklevel=2)
        self._runner = _DeadlineRunner()
        self._log = DecisionLog(decision_log) if decision_log else None
        self._recent: OrderedDict[str, tuple[str, float, float | None]] = OrderedDict()
        if self.model is not None:
            # The first call through the whole path is slow (the pH table loads, numpy warms
            # up), so make it now instead of on the first real request.
            now = self.context.clock()
            warm = {"now": now, "samples": [(now - 4.0 + i, 7.0) for i in range(5)], "dose_log": [],
                    "last_uno_t": now, "volume_start_L": V_NOMINAL_L, "temp_c": TEMP_C}
            try:
                self._decide(warm, "BASE_FINE", 1.0)
            except Exception as exc:          # noqa: BLE001
                self.load_error = f"warm-up failed: {type(exc).__name__}: {exc}"
                warnings.warn(f"Model A {self.load_error}", stacklevel=2)

    @property
    def model_version(self) -> str:
        return self.model.version if self.model is not None else MODEL_VERSION

    def _decide(self, snap: dict, channel_id, dose_ml):
        feats, problems = build_features(
            snap["samples"], snap["now"], channel_id, dose_ml, snap["dose_log"], snap["last_uno_t"],
            chem=self.model.chem, volume_start_L=snap["volume_start_L"], temp_c=snap["temp_c"])
        return self.model.decide(feats, problems), feats

    def predict(self, command: dict, state=None, log: bool = True) -> dict:
        """The gateway's call. `state` (Khalid's ProcessState) is accepted but not needed:
        Model A reads the probe history and dose log from the shared ProcessContext."""
        start = time.perf_counter()
        command_id = str(command.get("command_id", ""))
        channel_id = command.get("channel_id")
        dose_ml = command.get("dose_ml", command.get("volume_ml"))
        feats = None
        if self.model is None:
            decision = {"label": UNCERTAIN, "score": 1.0, "reason": "MODEL_UNAVAILABLE"}
        else:
            status, value = self._runner.run(self._decide, (self.context.snapshot(), channel_id, dose_ml),
                                             self.deadline_s)
            if status == "OK":
                decision, feats = value
            else:
                decision = {"label": UNCERTAIN, "score": 1.0, "reason": status}
        out = {
            "label": decision["label"],
            "score": round(float(decision["score"]), 6),
            "model_version": self.model_version,
            "latency_ms": round((time.perf_counter() - start) * 1000.0, 4),
            "reason": decision["reason"],
            "threshold": self.model.threshold if self.model is not None else None,
        }
        if feats is not None and command_id:
            self._recent[command_id] = (channel_id, dose_ml, feats.get("predicted_post_ph"))
            while len(self._recent) > 64:
                self._recent.popitem(last=False)
        if log and self._log is not None:
            self._log.write(command_id, channel_id, dose_ml, out, feats)
        return out

    def dose_added(self, command_id: str) -> bool:
        """Tell Model A that an accepted dose went into the tank (for features 10, 11, 13, 15).

        Uses the bottle, volume and predicted pH from Model A's own decision on that command.
        Returns False if Model A never saw the command.
        """
        known = self._recent.get(str(command_id))
        if known is None:
            return False
        channel_id, dose_ml, predicted = known
        self.context.record_dose(channel_id, float(dose_ml), predicted)
        return True
