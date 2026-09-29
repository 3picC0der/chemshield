"""Model A tests. Run either way:

    python -m model_a.tests.test_model_a
    python -m pytest model_a/tests

Tests marked "needs the trained model" are skipped until `python -m model_a.train` has
written model_a/artifacts/model_a.joblib.
"""
from __future__ import annotations

import math
import time
import unittest
import warnings

import numpy as np

from model_a.features import build_features, default_chemistry, predict_post_ph, window_stats
from model_a.inference import DEFAULT_ARTIFACT, ModelAClient, ProcessContext
from model_a.policy import harmful_rules, physics_screen_vec
from model_a.schema import (
    ACCEPTABLE,
    FEATURES,
    FIXED_FEATURES,
    HARMFUL,
    LABELS,
    UNCERTAIN,
)
from model_a.truth import BICARB_1MM, PURE_WATER, net_base_for_ph, true_ph

warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")


def close(a, b, tol):
    assert abs(a - b) <= tol, f"{a} vs {b} (tol {tol})"


def steady(ph, now=100.0, n=5):
    return [(now - (n - 1) + i - 0.3, ph + w) for i, w in enumerate([-0.01, 0.01, 0.0, -0.01, 0.01][:n])]


# ------------------------------------------------------------------ chemistry
def test_truth_known_answers():
    close(true_ph(0.0, 5.0, PURE_WATER), 7.00, 0.01)
    close(true_ph(-10.0, 5.0, PURE_WATER), 2.70, 0.01)     # Guide P8: 10 mmol HCl in 5 L
    close(true_ph(-0.5, 5.0, PURE_WATER), 4.00, 0.01)
    close(true_ph(10.0, 5.0, PURE_WATER), 11.30, 0.01)
    close(true_ph(0.0, 5.0, BICARB_1MM), 8.30, 0.02)      # 0.420 g baking soda in 5 L
    close(true_ph(-1.0, 5.0, BICARB_1MM), 6.95, 0.02)
    close(true_ph(-3.5, 5.0, BICARB_1MM), 5.98, 0.02)
    close(true_ph(1.0, 5.0, BICARB_1MM), 9.61, 0.02)
    for ph in (3.0, 6.5, 7.0, 8.0, 10.0):
        close(true_ph(net_base_for_ph(ph, 5.1, BICARB_1MM), 5.1, BICARB_1MM), ph, 1e-6)


def test_prediction_round_trip_on_the_loaded_table():
    chem = default_chemistry()
    for ph in (3.0, 5.0, 6.5, 7.0, 8.0, 9.0, 11.0):
        # a vanishingly small dose must leave the pH where it was
        close(predict_post_ph(chem, ph, "BASE_FINE", 1e-9, 5.0), ph, 0.02)
    lo = predict_post_ph(chem, 7.0, "ACID_BULK", 20.0, 5.0)
    hi = predict_post_ph(chem, 7.0, "BASE_BULK", 20.0, 5.0)
    assert lo < 3.5 and hi > 10.5, (lo, hi)


# ------------------------------------------------------------------ features
def test_window_stats_on_a_ramp():
    samples = [(float(t), 7.0 + 0.1 * t) for t in range(5)]
    mean, slope, curv, std, age, problem = window_stats(samples, 4.5)
    assert problem == ""
    close(mean, 7.2, 1e-9)
    close(slope, 0.1, 1e-9)
    close(curv, 0.0, 1e-9)
    close(std, float(np.std([7.0, 7.1, 7.2, 7.3, 7.4])), 1e-9)
    close(age, 0.5, 1e-9)
    assert window_stats(samples[:4], 4.5)[-1] == "INSUFFICIENT_DATA"
    spread = [(0.0, 7.0), (2.0, 7.0), (4.0, 7.0), (6.0, 7.0), (8.0, 7.0)]      # 8 s span
    assert window_stats(spread, 8.5)[-1] == "INSUFFICIENT_DATA"


def test_feature_problems_fail_closed():
    s = steady(7.0)
    ok, problems = build_features(s, 100.0, "BASE_FINE", 5.0, [], 99.7)
    assert problems == [], problems
    assert all(math.isfinite(ok[n]) for n in FEATURES)
    for name, value in FIXED_FEATURES.items():
        assert ok[name] == value
    assert build_features(s, 100.0, None, 5.0, [], 99.7)[1][0] == "BAD_CHANNEL"
    assert build_features(s, 100.0, "acid", 5.0, [], 99.7)[1][0] == "BAD_CHANNEL"
    assert "BAD_DOSE" in build_features(s, 100.0, "BASE_FINE", 25.0, [], 99.7)[1]
    assert build_features(s, 103.0, "BASE_FINE", 5.0, [], 99.7)[1][0] == "STALE_SAMPLE"
    assert build_features(s, 100.0, "BASE_FINE", 5.0, [], 97.0)[1] == ["HEARTBEAT_LOST"]
    assert build_features(s, 100.0, "BASE_FINE", 5.0, [], None)[1] == ["HEARTBEAT_LOST"]
    assert build_features([], 100.0, "BASE_FINE", 5.0, [], 99.7)[1][0] == "INSUFFICIENT_DATA"


def test_dose_log_features():
    log = [{"t": 10.0, "channel_id": "ACID_BULK", "dose_ml": 2.0, "predicted_post_ph": 6.9},
           {"t": 60.0, "channel_id": "BASE_FINE", "dose_ml": 10.0, "predicted_post_ph": 7.1}]
    f, problems = build_features(steady(7.3), 100.0, "BASE_FINE", 5.0, log, 99.7)
    assert problems == []
    close(f["cumulative_signed_mmol"], 2.0 * 0.5 - 10.0 * 0.005, 1e-9)     # acid positive
    close(f["cumulative_abs_mmol"], 1.0 + 0.05, 1e-9)
    close(f["measured_predicted_residual"], 7.3 - 7.1, 1e-9)
    close(f["level_margin_l"], 5.5 - (5.0 + 0.012), 1e-9)
    assert f["candidate_direction"] == -1.0
    close(f["candidate_mmol"], 0.025, 1e-12)
    # the first dose is now older than 10 minutes: out of the cumulative window
    f2, _ = build_features(steady(7.3, now=650.0), 650.0, "BASE_FINE", 5.0, log, 649.7)
    close(f2["cumulative_abs_mmol"], 0.05, 1e-9)


# ------------------------------------------------------------------ label policy
def test_label_rules():
    assert harmful_rules(7.0, 7.2) == ""
    assert harmful_rules(7.0, 9.0) == "d"                 # leaves 6.0-8.5 from inside it
    assert harmful_rules(7.0, 10.0) == "a,d"
    assert harmful_rules(2.5, 3.0) == ""                  # partial recovery is fine
    assert harmful_rules(2.5, 2.0) == "a,b"               # deeper into acid
    assert harmful_rules(3.0, 9.0) == "c"                 # overshoot to the far side
    assert harmful_rules(3.0, 10.0) == "a,c"
    assert harmful_rules(8.3, 6.95) == ""
    rng = np.random.default_rng(1)
    cur, post = rng.uniform(1, 13, 2000), rng.uniform(1, 13, 2000)
    vec = physics_screen_vec(cur, post)
    assert all(int(bool(harmful_rules(c, p))) == v for c, p, v in zip(cur, post, vec))


# ------------------------------------------------------------------ the gateway call
def _client(**kw) -> ModelAClient:
    if not DEFAULT_ARTIFACT.exists():
        raise unittest.SkipTest("needs the trained model: run `python -m model_a.train`")
    return ModelAClient(**kw)


def test_missing_model_file_is_uncertain_not_a_crash():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        client = ModelAClient(artifact_path="/nonexistent/model_a.joblib")
    out = client.predict({"command_id": "c1", "channel_id": "BASE_FINE", "dose_ml": 5.0}, None)
    assert out["label"] == UNCERTAIN and out["score"] == 1.0 and out["reason"] == "MODEL_UNAVAILABLE"
    assert set(out) >= {"label", "score", "model_version", "latency_ms"}


def test_i3_answers():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(6.2 + (0.01 if i % 2 else -0.01), t=now - 4.2 + i)
    harmful = client.predict({"command_id": "h1", "channel_id": "ACID_BULK", "dose_ml": 20.0}, None)
    assert harmful["label"] == HARMFUL, harmful
    assert harmful["latency_ms"] < 100.0
    small = client.predict({"command_id": "a1", "channel_id": "BASE_FINE", "dose_ml": 1.0}, None)
    assert small["label"] in LABELS
    for out in (harmful, small):
        assert isinstance(out["score"], float) and 0.0 <= out["score"] <= 1.0
        assert out["model_version"] == client.model_version


def test_recovery_dose_is_accepted():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(3.5, t=now - 4.2 + i)
    out = client.predict({"command_id": "r1", "channel_id": "BASE_FINE", "dose_ml": 5.0}, None)
    assert out["label"] == ACCEPTABLE, out


def test_stale_probe_and_legacy_command_are_uncertain():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(7.0, t=now - 9.0 + i)            # USB pulled 5 s ago
    out = client.predict({"command_id": "s1", "channel_id": "BASE_FINE", "dose_ml": 5.0}, None)
    assert out["label"] == UNCERTAIN and out["reason"] == "STALE_SAMPLE", out
    for i in range(5):
        ctx.add_sample(7.0, t=ctx.clock() - 4.0 + i)
    legacy = {"command_id": "k1", "reagent": "base", "volume_ml": 5.0}     # no bottle name
    out = client.predict(legacy, None)
    assert out["label"] == UNCERTAIN and out["reason"] == "BAD_CHANNEL", out


def test_timeout_gives_uncertain_within_the_deadline():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(7.0, t=now - 4.2 + i)
    client.model.debug_delay_s = 0.5
    t0 = time.perf_counter()
    out = client.predict({"command_id": "t1", "channel_id": "BASE_FINE", "dose_ml": 1.0}, None)
    waited = (time.perf_counter() - t0) * 1000.0
    client.model.debug_delay_s = 0.0
    assert out["label"] == UNCERTAIN and out["reason"] == "TIMEOUT", out
    assert waited < 300.0, waited
    again = client.predict({"command_id": "t2", "channel_id": "BASE_FINE", "dose_ml": 1.0}, None)
    assert again["reason"] != "TIMEOUT", again             # a fresh worker takes over


def test_far_outside_training_is_uncertain():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(7.0, t=now - 4.2 + i)
    for j in range(12):                                 # 120 mmol of acid in 10 minutes
        ctx.record_dose("ACID_BULK", 20.0, 7.0, t=now - 300.0 + j)
        ctx.record_dose("BASE_BULK", 20.0, 7.0, t=now - 299.0 + j)
    out = client.predict({"command_id": "o1", "channel_id": "BASE_FINE", "dose_ml": 1.0}, None)
    assert out["label"] == UNCERTAIN and out["reason"].startswith("OUT_OF_RANGE"), out


def test_dose_added_feeds_the_dose_log():
    ctx = ProcessContext()
    client = _client(context=ctx)
    now = ctx.clock()
    for i in range(5):
        ctx.add_sample(3.5, t=now - 4.2 + i)
    client.predict({"command_id": "d1", "channel_id": "BASE_BULK", "dose_ml": 2.0}, None)
    assert client.dose_added("d1")
    assert not client.dose_added("never-seen")
    log = ctx.snapshot()["dose_log"]
    assert len(log) == 1 and log[0]["channel_id"] == "BASE_BULK" and log[0]["predicted_post_ph"] is not None


# ------------------------------------------------------------------ the generator
def test_generator_smoke():
    from model_a import generate as G

    chem = default_chemistry()
    liquid = "bicarb_1mM" if chem.ph_from_excess(0.0, 25.0, 5.0) > 7.8 else "pure_water"
    G._worker_init()
    rows = []
    for ep in G.sample_episodes(6, seed=7, liquid=liquid):
        rows += G.run_episode(ep)
    assert rows
    for r in rows:
        assert set(FEATURES) <= set(r)
        assert r["harmful"] in (0, 1) and r["valid"] in (0, 1)
        assert r["channel_id"] in ("ACID_BULK", "ACID_FINE", "BASE_BULK", "BASE_FINE")
        assert 0.0 < r["dose_ml"] <= 20.0


# ------------------------------------------------------------------ plain runner
def _run() -> int:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = skipped = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except unittest.SkipTest as exc:
            skipped += 1
            print(f"  SKIP  {name}: {exc}")
        except Exception as exc:                      # noqa: BLE001
            failed += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed - skipped}/{len(tests)} passed, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
