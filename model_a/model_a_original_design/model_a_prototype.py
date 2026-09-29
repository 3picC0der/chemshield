#!/usr/bin/env python3
"""Runnable design-stage prototype for the ChemShield Model A context gate."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


KW = 1e-14
SEED = 261

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


def excess_moles_from_ph(ph: float, volume_l: float) -> float:
    """Return signed strong-acid excess moles. Positive means acid excess."""
    return volume_l * (10.0 ** (-ph) - KW * 10.0**ph)


def ph_from_excess_moles(excess_mol: float, volume_l: float) -> float:
    """Stable pH calculation for signed strong-acid excess."""
    concentration = excess_mol / volume_l
    root = math.sqrt(concentration * concentration + 4.0 * KW)
    if concentration >= 0.0:
        hydrogen = 0.5 * (concentration + root)
    else:
        hydroxide = 0.5 * (-concentration + root)
        hydrogen = KW / hydroxide
    return -math.log10(max(hydrogen, 1e-16))


def apply_dose(
    ph: float,
    volume_l: float,
    direction: int,
    concentration_mol_l: float,
    dose_ml: float,
    delivery_gain: float = 1.0,
) -> float:
    current = excess_moles_from_ph(ph, volume_l)
    delivered_mol = direction * concentration_mol_l * dose_ml * delivery_gain / 1000.0
    return ph_from_excess_moles(current + delivered_mol, volume_l + dose_ml / 1000.0)


def harmful_policy(current_ph: float, post_ph: float) -> bool:
    """Version 0 policy used only to generate prototype ground truth."""
    outside_extreme = post_ph < 5.5 or post_ph > 9.5
    farther_while_abnormal = (
        (current_ph < 6.3 or current_ph > 8.2)
        and abs(post_ph - 7.0) > abs(current_ph - 7.0) + 0.20
    )
    far_side_overshoot = (current_ph < 6.3 and post_ph > 8.2) or (
        current_ph > 8.2 and post_ph < 6.3
    )
    return bool(outside_extreme or farther_while_abnormal or far_side_overshoot)


def _history_features(samples: np.ndarray) -> tuple[float, float, float, float]:
    times = np.arange(samples.size, dtype=float)
    slope = float(np.polyfit(times, samples, 1)[0])
    first = np.diff(samples)
    curvature = float(np.mean(np.diff(first))) if first.size >= 2 else 0.0
    return float(samples.mean()), slope, curvature, float(samples.std(ddof=0))


def generate_dataset(n_runs: int, commands_per_run: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, float | int | str]] = []

    for run_id in range(n_runs):
        volume_l = float(rng.uniform(4.8, 5.2))
        sensor_bias = float(np.clip(rng.normal(0.0, 0.18), -0.45, 0.45))
        pump_gain = float(np.clip(rng.normal(1.0, 0.13), 0.65, 1.35))
        mixer_ratio = float(rng.uniform(0.82, 1.03))
        cumulative_signed = float(rng.normal(0.0, 5.0))
        cumulative_abs = float(abs(cumulative_signed) + rng.uniform(0.0, 12.0))

        for command_index in range(commands_per_run):
            if rng.random() < 0.62:
                true_ph = float(rng.uniform(6.1, 8.4))
            else:
                true_ph = float(rng.uniform(5.55, 9.45))

            trend = float(rng.normal(0.0, 0.035))
            curvature = float(rng.normal(0.0, 0.008))
            history_true = np.array(
                [
                    true_ph - trend * (4 - index) + curvature * (4 - index) ** 2
                    for index in range(5)
                ]
            )
            noise = rng.normal(0.0, 0.025, size=5)
            history_observed = history_true + sensor_bias + noise
            ph_mean, ph_slope, ph_curve, ph_std = _history_features(history_observed)

            direction = 1 if rng.random() < 0.5 else -1
            concentration = 0.5 if rng.random() < 0.45 else 0.005
            dose_ml = float(rng.uniform(0.5, 20.0))
            requested_mmol = concentration * dose_ml

            nominal_post = apply_dose(
                ph_mean,
                volume_l,
                direction,
                concentration,
                dose_ml,
                delivery_gain=1.0,
            )
            actual_gain = float(np.clip(pump_gain + rng.normal(0.0, 0.035), 0.55, 1.45))
            true_post = apply_dose(
                true_ph,
                volume_l,
                direction,
                concentration,
                dose_ml,
                delivery_gain=actual_gain,
            )

            request_delivery_residual = float((pump_gain - 1.0) + rng.normal(0.0, 0.04))
            measured_predicted_residual = float(
                sensor_bias + 0.7 * (pump_gain - 1.0) + rng.normal(0.0, 0.06)
            )
            safety_margin = float(min(nominal_post - 5.5, 9.5 - nominal_post))
            scenario_origin = rng.choice(
                ["normal", "operator_error", "configuration_error", "injected_attack"],
                p=[0.48, 0.18, 0.14, 0.20],
            )

            harmful = harmful_policy(true_ph, true_post)
            rows.append(
                {
                    "run_id": run_id,
                    "command_index": command_index,
                    "scenario_origin": str(scenario_origin),
                    "true_current_ph": true_ph,
                    "true_post_ph": true_post,
                    "concentration_mol_l": concentration,
                    "dose_ml": dose_ml,
                    "ph_mean_5s": ph_mean,
                    "ph_slope_5s": ph_slope,
                    "ph_curvature_5s": ph_curve,
                    "ph_std_5s": ph_std,
                    "sample_age_s": float(rng.uniform(0.0, 1.5)),
                    "candidate_direction": direction,
                    "candidate_mmol": requested_mmol,
                    "predicted_post_ph": nominal_post,
                    "predicted_safety_margin": safety_margin,
                    "cumulative_signed_mmol": cumulative_signed,
                    "cumulative_abs_mmol": cumulative_abs,
                    "request_delivery_residual": request_delivery_residual,
                    "measured_predicted_residual": measured_predicted_residual,
                    "mixer_speed_ratio": mixer_ratio,
                    "level_margin_l": float(rng.uniform(0.25, 1.0)),
                    "heartbeat_age_s": float(rng.uniform(0.0, 0.85)),
                    "harmful_context": int(harmful),
                }
            )

            cumulative_signed += direction * requested_mmol
            cumulative_abs += requested_mmol

    return pd.DataFrame(rows)


def group_split(df: pd.DataFrame, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    groups = df["run_id"].unique().copy()
    rng.shuffle(groups)
    n = len(groups)
    train_groups = set(groups[: int(0.60 * n)])
    val_groups = set(groups[int(0.60 * n) : int(0.80 * n)])
    test_groups = set(groups[int(0.80 * n) :])
    return (
        df[df["run_id"].isin(train_groups)].copy(),
        df[df["run_id"].isin(val_groups)].copy(),
        df[df["run_id"].isin(test_groups)].copy(),
    )


def nominal_physics_decision(df: pd.DataFrame) -> np.ndarray:
    current = df["ph_mean_5s"].to_numpy()
    post = df["predicted_post_ph"].to_numpy()
    outside = (post < 5.5) | (post > 9.5)
    farther = ((current < 6.3) | (current > 8.2)) & (
        np.abs(post - 7.0) > np.abs(current - 7.0) + 0.20
    )
    overshoot = ((current < 6.3) & (post > 8.2)) | ((current > 8.2) & (post < 6.3))
    return (outside | farther | overshoot).astype(int)


def choose_threshold(y_true: np.ndarray, risk: np.ndarray, target_recall: float = 0.99) -> float:
    candidates = np.linspace(0.01, 0.99, 197)
    feasible: list[tuple[float, float]] = []
    for threshold in candidates:
        pred = (risk >= threshold).astype(int)
        recall = recall_score(y_true, pred, zero_division=0)
        false_positive_rate = float(((pred == 1) & (y_true == 0)).sum() / max((y_true == 0).sum(), 1))
        if recall >= target_recall:
            feasible.append((false_positive_rate, float(threshold)))
    if feasible:
        feasible.sort(key=lambda item: (item[0], -item[1]))
        return feasible[0][1]
    return 0.01


def choose_hybrid_threshold(
    y_true: np.ndarray,
    physics_block: np.ndarray,
    risk: np.ndarray,
    max_incremental_false_block: float = 0.02,
) -> float:
    """Maximize harmful recall while limiting added false blocks over physics."""
    benign = y_true == 0
    physics_fpr = float(((physics_block == 1) & benign).sum() / max(benign.sum(), 1))
    limit = physics_fpr + max_incremental_false_block
    feasible: list[tuple[float, float, float]] = []
    for threshold in np.linspace(0.01, 0.99, 197):
        decision = (physics_block == 1) | (risk >= threshold)
        recall = float(((decision == 1) & (y_true == 1)).sum() / max((y_true == 1).sum(), 1))
        false_block = float(((decision == 1) & benign).sum() / max(benign.sum(), 1))
        if false_block <= limit:
            feasible.append((-recall, false_block, float(threshold)))
    if not feasible:
        return 0.99
    feasible.sort()
    return feasible[0][2]


def metrics(y_true: np.ndarray, pred: np.ndarray) -> dict[str, object]:
    matrix = confusion_matrix(y_true, pred, labels=[0, 1])
    tn, fp, fn, tp = matrix.ravel()
    return {
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision_harmful": float(precision_score(y_true, pred, zero_division=0)),
        "recall_harmful": float(recall_score(y_true, pred, zero_division=0)),
        "f1_harmful": float(f1_score(y_true, pred, zero_division=0)),
        "benign_false_block_rate": float(fp / max(fp + tn, 1)),
        "harmful_missed": int(fn),
        "harmful_blocked": int(tp),
        "confusion_matrix_0_1": matrix.tolist(),
    }


@dataclass
class Candidate:
    name: str
    estimator: object


def benchmark_inference(model: object, X: pd.DataFrame, repeats: int = 1000) -> dict[str, float]:
    one = X.iloc[[0]]
    timings = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        model.predict_proba(one)
        timings.append((time.perf_counter_ns() - start) / 1_000_000.0)
    values = np.asarray(timings)
    return {
        "p50_ms": float(np.percentile(values, 50)),
        "p95_ms": float(np.percentile(values, 95)),
        "p99_ms": float(np.percentile(values, 99)),
        "max_ms": float(values.max()),
    }


def build_same_command_demo(model: object, threshold: float) -> pd.DataFrame:
    """Evaluate one exact command across different pH contexts."""
    rows: list[dict[str, float | int | bool]] = []
    direction = 1
    concentration = 0.005
    dose_ml = 5.0
    candidate_mmol = concentration * dose_ml
    for current_ph in (5.8, 6.3, 7.0, 7.7, 8.2, 8.7, 9.2):
        predicted_post = apply_dose(
            current_ph, 5.0, direction, concentration, dose_ml, delivery_gain=1.0
        )
        row = {
            "ph_mean_5s": current_ph,
            "ph_slope_5s": 0.0,
            "ph_curvature_5s": 0.0,
            "ph_std_5s": 0.02,
            "sample_age_s": 0.5,
            "candidate_direction": direction,
            "candidate_mmol": candidate_mmol,
            "predicted_post_ph": predicted_post,
            "predicted_safety_margin": min(predicted_post - 5.5, 9.5 - predicted_post),
            "cumulative_signed_mmol": 0.0,
            "cumulative_abs_mmol": 0.0,
            "request_delivery_residual": 0.0,
            "measured_predicted_residual": 0.0,
            "mixer_speed_ratio": 1.0,
            "level_margin_l": 0.75,
            "heartbeat_age_s": 0.2,
        }
        frame = pd.DataFrame([row], columns=FEATURES)
        risk = float(model.predict_proba(frame)[0, 1])
        physics_block = int(harmful_policy(current_ph, predicted_post))
        rows.append(
            {
                "current_ph": current_ph,
                "command": "ACID_FINE 0.005 M, 5.0 mL",
                "predicted_post_ph": predicted_post,
                "ground_truth_harmful": bool(harmful_policy(current_ph, predicted_post)),
                "nominal_physics_block": physics_block,
                "model_a_risk": risk,
                "model_a_threshold": threshold,
                "hybrid_block": int(physics_block == 1 or risk >= threshold),
            }
        )
    return pd.DataFrame(rows)


def write_summary(path: Path, evidence: dict[str, object]) -> None:
    selected = evidence["selected_model"]
    physics = evidence["test_results"]["nominal_physics_rule"]
    hybrid = evidence["test_results"]["hybrid_physics_plus_model_a"]
    content = "# Model A prototype evidence\n\n"
    content += f"Generated examples: {evidence['dataset']['rows']} across {evidence['dataset']['runs']} independent runs.\n\n"
    content += f"Selected model: `{selected}` with validation-selected threshold {evidence['thresholds'][selected]:.3f}.\n\n"
    content += "## Held-out test results\n\n"
    content += f"- Nominal physics harmful recall: {physics['recall_harmful']:.3f}\n"
    content += f"- Nominal physics benign false-block rate: {physics['benign_false_block_rate']:.3f}\n"
    content += f"- Hybrid harmful-context recall: {hybrid['recall_harmful']:.3f}\n"
    content += f"- Hybrid benign false-block rate: {hybrid['benign_false_block_rate']:.3f}\n"
    content += f"- Additional harmful cases blocked by Model A: {evidence['hybrid_increment']['additional_harmful_blocked']}\n"
    content += f"- Additional benign cases blocked by Model A: {evidence['hybrid_increment']['additional_benign_blocked']}\n\n"
    content += "## Interpretation\n\n"
    content += (
        "These results prove that the software experiment and evidence pipeline runs. "
        "They do not validate the physical plant. The simulator deliberately includes "
        "hidden sensor and delivery uncertainty so that the learned model can use prior "
        "residuals. Replace those distributions with measured or Aspen-calibrated values "
        "before making performance claims.\n"
    )
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3000)
    parser.add_argument("--commands-per-run", type=int, default=4)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    df = generate_dataset(args.runs, args.commands_per_run, args.seed)
    train, validation, test = group_split(df, args.seed)

    X_train, y_train = train[FEATURES], train["harmful_context"].to_numpy()
    X_val, y_val = validation[FEATURES], validation["harmful_context"].to_numpy()
    X_test, y_test = test[FEATURES], test["harmful_context"].to_numpy()

    candidates = [
        Candidate(
            "logistic_regression",
            make_pipeline(
                StandardScaler(),
                LogisticRegression(max_iter=2000, class_weight="balanced", random_state=args.seed),
            ),
        ),
        Candidate(
            "random_forest",
            RandomForestClassifier(
                n_estimators=250,
                max_depth=10,
                min_samples_leaf=5,
                class_weight="balanced",
                random_state=args.seed,
                n_jobs=-1,
            ),
        ),
        Candidate(
            "gradient_boosting",
            GradientBoostingClassifier(
                n_estimators=150,
                learning_rate=0.05,
                max_depth=3,
                random_state=args.seed,
            ),
        ),
    ]

    evidence: dict[str, object] = {
        "prototype_scope": "design-stage synthetic evidence; not physical validation",
        "seed": args.seed,
        "feature_schema": FEATURES,
        "dataset": {
            "rows": int(len(df)),
            "runs": int(df["run_id"].nunique()),
            "harmful_fraction": float(df["harmful_context"].mean()),
            "train_rows": int(len(train)),
            "validation_rows": int(len(validation)),
            "test_rows": int(len(test)),
        },
        "thresholds": {},
        "validation_results": {},
        "test_results": {},
    }

    gateway_pred = np.zeros_like(y_test)
    physics_pred = nominal_physics_decision(test)
    evidence["test_results"]["gateway_only"] = metrics(y_test, gateway_pred)
    evidence["test_results"]["nominal_physics_rule"] = metrics(y_test, physics_pred)

    fitted: dict[str, object] = {}
    for candidate in candidates:
        candidate.estimator.fit(X_train, y_train)
        val_risk = candidate.estimator.predict_proba(X_val)[:, 1]
        threshold = choose_threshold(y_val, val_risk)
        val_pred = (val_risk >= threshold).astype(int)
        test_risk = candidate.estimator.predict_proba(X_test)[:, 1]
        test_pred = (test_risk >= threshold).astype(int)
        evidence["thresholds"][candidate.name] = threshold
        evidence["validation_results"][candidate.name] = metrics(y_val, val_pred)
        evidence["test_results"][candidate.name] = metrics(y_test, test_pred)
        fitted[candidate.name] = candidate.estimator

    train_physics = nominal_physics_decision(train)
    validation_physics = nominal_physics_decision(validation)
    residual_training = train[train_physics == 0]
    residual_model = GradientBoostingClassifier(
        n_estimators=300,
        learning_rate=0.03,
        max_depth=3,
        random_state=args.seed,
    )
    residual_model.fit(
        residual_training[FEATURES], residual_training["harmful_context"].to_numpy()
    )
    residual_val_risk = residual_model.predict_proba(X_val)[:, 1]
    hybrid_threshold = choose_hybrid_threshold(
        y_val, validation_physics, residual_val_risk
    )
    residual_test_risk = residual_model.predict_proba(X_test)[:, 1]
    residual_test_pred = (residual_test_risk >= hybrid_threshold).astype(int)
    hybrid_test_pred = (
        (physics_pred == 1) | (residual_test_risk >= hybrid_threshold)
    ).astype(int)
    evidence["thresholds"]["residual_context_model"] = hybrid_threshold
    physics_allowed = physics_pred == 0
    evidence["test_results"]["model_a_on_physics_allowed"] = metrics(
        y_test[physics_allowed], residual_test_pred[physics_allowed]
    )
    evidence["test_results"]["hybrid_physics_plus_model_a"] = metrics(
        y_test, hybrid_test_pred
    )
    evidence["hybrid_increment"] = {
        "additional_harmful_blocked": int(
            ((hybrid_test_pred == 1) & (physics_pred == 0) & (y_test == 1)).sum()
        ),
        "additional_benign_blocked": int(
            ((hybrid_test_pred == 1) & (physics_pred == 0) & (y_test == 0)).sum()
        ),
    }
    fitted["residual_context_model"] = residual_model

    selected_name = "residual_context_model"
    selected = residual_model
    evidence["selected_model"] = selected_name
    evidence["host_inference_timing"] = benchmark_inference(selected, X_test)

    test_output = test.copy()
    for name, model in fitted.items():
        risk = model.predict_proba(X_test)[:, 1]
        test_output[f"{name}_risk"] = risk
        if name in evidence["thresholds"]:
            test_output[f"{name}_block"] = (
                risk >= evidence["thresholds"][name]
            ).astype(int)
    test_output["nominal_physics_block"] = physics_pred
    test_output["hybrid_physics_plus_model_a_block"] = hybrid_test_pred
    test_output.to_csv(args.output_dir / "test_predictions.csv", index=False)
    build_same_command_demo(residual_model, hybrid_threshold).to_csv(
        args.output_dir / "same_command_different_contexts.csv", index=False
    )

    forest = fitted["random_forest"]
    pd.DataFrame(
        {"feature": FEATURES, "importance": forest.feature_importances_}
    ).sort_values("importance", ascending=False).to_csv(
        args.output_dir / "feature_importance.csv", index=False
    )
    pd.DataFrame(
        {"feature": FEATURES, "importance": residual_model.feature_importances_}
    ).sort_values("importance", ascending=False).to_csv(
        args.output_dir / "residual_feature_importance.csv", index=False
    )

    artifact = {
        "model": selected,
        "model_name": selected_name,
        "threshold": evidence["thresholds"][selected_name],
        "features": FEATURES,
        "label_policy_version": "prototype-v0",
        "seed": args.seed,
    }
    joblib.dump(artifact, args.output_dir / "model.joblib")
    (args.output_dir / "evidence.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )
    write_summary(args.output_dir / "summary.md", evidence)

    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
