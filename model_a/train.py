"""Train and evaluate Model A.

    python -m model_a.train                      # model_a/data/ -> model_a/artifacts/
    python -m model_a.train --data DIR --out DIR

The train/evaluate half of model_a_original_design/model_a_prototype.py, on the new
dataset:
  * split by episode (60/20/20), never by row; the cumulative-dose episodes are held out
    of training completely;
  * baselines on the same test rows: gateway only, the physics rule alone, and three
    single-stage models (logistic regression, random forest, gradient boosting);
  * Model A = physics rule OR a gradient-boosted "residual" model trained on the rows the
    physics rule lets through; its threshold is picked on the validation set (highest
    harmful recall while adding at most 2 percentage points of false blocks over physics);
  * the saved model is then run through the real Pi code path (ModelA.decide) on the test
    rows, the held-out pattern and the rows the Pi can't judge (must be UNCERTAIN).
Outputs go to model_a/artifacts/: model_a.joblib, evidence.json, MODEL_CARD.md and CSVs.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .features import build_features, default_chemistry
from .inference import ModelA
from .policy import harmful_rules, physics_screen_vec
from .schema import (
    ACCEPTABLE,
    CHANNELS,
    FEATURE_SCHEMA_VERSION,
    FEATURES,
    HARMFUL,
    LABEL_POLICY_VERSION,
    MODEL_VERSION,
    UNCERTAIN,
)
from .truth import LIQUIDS, net_base_for_ph, true_ph

HERE = Path(__file__).resolve().parent
SEED = 261
MAX_ADDED_FALSE_BLOCK = 0.02


# ------------------------------------------------------------------ helpers from the prototype
def group_split(df: pd.DataFrame, seed: int):
    rng = np.random.default_rng(seed)
    groups = np.array(sorted(df["episode_id"].unique()))
    rng.shuffle(groups)
    n = len(groups)
    tr, va = set(groups[: int(0.6 * n)]), set(groups[int(0.6 * n): int(0.8 * n)])
    te = set(groups[int(0.8 * n):])
    return (df[df.episode_id.isin(tr)].copy(), df[df.episode_id.isin(va)].copy(),
            df[df.episode_id.isin(te)].copy())


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    y = np.asarray(y, int)
    pred = np.asarray(pred, int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    return {
        "rows": int(len(y)),
        "harmful": int(tp + fn),
        "benign": int(tn + fp),
        "harmful_recall": round(float(tp / max(tp + fn, 1)), 4),
        "benign_false_block_rate": round(float(fp / max(fp + tn, 1)), 4),
        "harmful_missed": int(fn),
        "benign_blocked": int(fp),
        "precision_harmful": round(float(tp / max(tp + fp, 1)), 4),
        "accuracy": round(float((tp + tn) / max(len(y), 1)), 4),
        "confusion_matrix_[[tn,fp],[fn,tp]]": [[int(tn), int(fp)], [int(fn), int(tp)]],
    }


def choose_threshold(y, risk, target_recall: float = 0.99) -> float:
    """Single-stage models: lowest false-block rate with harmful recall >= target."""
    best = None
    for thr in np.linspace(0.01, 0.99, 197):
        pred = risk >= thr
        recall = (pred & (y == 1)).sum() / max((y == 1).sum(), 1)
        fpr = (pred & (y == 0)).sum() / max((y == 0).sum(), 1)
        if recall >= target_recall and (best is None or (fpr, -thr) < best[:2]):
            best = (fpr, -thr, float(thr))
    return best[2] if best else 0.01


def choose_hybrid_threshold(y, physics, risk, max_added: float = MAX_ADDED_FALSE_BLOCK) -> float:
    """Highest harmful recall while adding at most max_added false blocks over physics."""
    benign = y == 0
    limit = ((physics == 1) & benign).sum() / max(benign.sum(), 1) + max_added
    best = None
    for thr in np.linspace(0.01, 0.99, 197):
        block = (physics == 1) | (risk >= thr)
        recall = (block & (y == 1)).sum() / max((y == 1).sum(), 1)
        fpr = (block & benign).sum() / max(benign.sum(), 1)
        if fpr <= limit and (best is None or (-recall, fpr, -thr) < best[:3]):
            best = (-recall, fpr, -thr, float(thr))
    return best[3] if best else 0.99


@dataclass
class Candidate:
    name: str
    estimator: object


def _row_feats(row) -> dict:
    return {n: float(row[n]) for n in FEATURES}


def run_deployed(model: ModelA, df: pd.DataFrame) -> pd.DataFrame:
    """Every row through the exact Pi decision code. UNCERTAIN counts as a block."""
    out = [model.decide(_row_feats(r), []) for r in df[FEATURES].to_dict("records")]
    res = pd.DataFrame(out, index=df.index)
    res["block"] = (res["label"] != ACCEPTABLE).astype(int)
    return res


def same_dose_table(model: ModelA, liquid_name: str) -> pd.DataFrame:
    """One dose, many tanks: what the Pi decides vs what really happens (steady probe)."""
    chem = default_chemistry()
    liquid = LIQUIDS[liquid_name]
    wiggle = [-0.01, 0.01, 0.0, -0.01, 0.01]
    rows = []
    for channel_id, dose in (("BASE_BULK", 2.0), ("ACID_BULK", 2.0), ("BASE_FINE", 10.0)):
        for ph in (3.0, 4.5, 5.8, 6.3, 7.0, 7.7, 8.3, 9.0, 10.0, 11.0):
            samples = [(float(i), ph + w) for i, w in enumerate(wiggle)]
            now = 4.5
            feats, problems = build_features(samples, now, channel_id, dose, [], now, chem=chem)
            decision = model.decide(feats, problems)
            net = net_base_for_ph(ph, 5.0, liquid)
            molarity, direction = CHANNELS[channel_id]
            post = true_ph(net - direction * molarity * dose, 5.0 + dose / 1000.0, liquid)
            rules = harmful_rules(ph, post)
            rows.append({"dose": f"{dose:g} mL {channel_id}", "tank_ph": ph,
                         "predicted_post_ph": round(feats["predicted_post_ph"], 2),
                         "true_post_ph": round(post, 2), "truth": HARMFUL if rules else ACCEPTABLE,
                         "model_a": decision["label"], "score": round(decision["score"], 3),
                         "reason": decision["reason"]})
    return pd.DataFrame(rows)


def latency(model: ModelA, df: pd.DataFrame, n: int = 1000) -> dict:
    recs = df[FEATURES].head(n).to_dict("records")
    times = []
    for r in recs:
        t0 = time.perf_counter()
        model.decide(_row_feats(r), [])
        times.append((time.perf_counter() - t0) * 1000.0)
    t = np.array(times)
    return {"n": int(len(t)), "p50_ms": round(float(np.percentile(t, 50)), 4),
            "p99_ms": round(float(np.percentile(t, 99)), 4), "max_ms": round(float(t.max()), 4)}


# ------------------------------------------------------------------ main
def train(data_dir: Path, out_dir: Path, seed: int = SEED, quiet: bool = False) -> dict:
    manifest = json.loads((data_dir / "manifest.json").read_text())
    df = pd.read_csv(data_dir / manifest["csv"], keep_default_na=False, na_values=[""])
    df["label_rules"] = df["label_rules"].fillna("")
    out_dir.mkdir(parents=True, exist_ok=True)

    valid = df[df.valid == 1]
    invalid = df[df.valid == 0]
    heldout = valid[valid.episode_kind == "cumulative"]
    main = valid[valid.episode_kind != "cumulative"]
    train_df, val_df, test_df = group_split(main, seed)

    def xy(d):
        return d[FEATURES].to_numpy(float), d["harmful"].to_numpy(int)

    def phys(d):
        return physics_screen_vec(d["ph_mean_5s"].to_numpy(), d["predicted_post_ph"].to_numpy())

    X_tr, y_tr = xy(train_df)
    X_va, y_va = xy(val_df)
    X_te, y_te = xy(test_df)
    X_ho, y_ho = xy(heldout)
    p_tr, p_va, p_te, p_ho = phys(train_df), phys(val_df), phys(test_df), phys(heldout)

    ev: dict = {
        "scope": "simulation evidence for the PPR; not physical validation",
        "trained_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seed": seed,
        "dataset": {k: manifest.get(k) for k in ("rows", "valid_rows", "invalid_rows", "episodes",
                                                 "liquid", "chem_source", "csv_sha256", "git_commit",
                                                 "label_policy_version")},
        "split_rows": {"train": len(train_df), "validation": len(val_df), "test": len(test_df),
                       "held_out_cumulative": len(heldout), "invalid_fail_closed": len(invalid)},
        "harmful_fraction": {"train": round(float(y_tr.mean()), 4), "test": round(float(y_te.mean()), 4)},
        "thresholds": {}, "validation": {}, "test": {}, "held_out_cumulative": {},
    }
    ev["test"]["gateway_only"] = metrics(y_te, np.zeros_like(y_te))
    ev["test"]["physics_rule"] = metrics(y_te, p_te)
    ev["held_out_cumulative"]["physics_rule"] = metrics(y_ho, p_ho)

    candidates = [
        Candidate("logistic_regression", make_pipeline(
            StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed))),
        Candidate("random_forest", RandomForestClassifier(
            n_estimators=250, max_depth=10, min_samples_leaf=5, class_weight="balanced",
            random_state=seed, n_jobs=-1)),
        Candidate("gradient_boosting", GradientBoostingClassifier(
            n_estimators=150, learning_rate=0.05, max_depth=3, random_state=seed)),
    ]
    for c in candidates:
        c.estimator.fit(X_tr, y_tr)
        thr = choose_threshold(y_va, c.estimator.predict_proba(X_va)[:, 1])
        ev["thresholds"][c.name] = round(thr, 3)
        ev["validation"][c.name] = metrics(y_va, c.estimator.predict_proba(X_va)[:, 1] >= thr)
        ev["test"][c.name] = metrics(y_te, c.estimator.predict_proba(X_te)[:, 1] >= thr)

    # ---- Model A: physics rule OR residual model
    allowed = p_tr == 0
    if len(np.unique(y_tr[allowed])) < 2:
        raise SystemExit("The rows the physics rule allows contain only one class; nothing to learn.")
    residual = GradientBoostingClassifier(n_estimators=300, learning_rate=0.03, max_depth=3,
                                          random_state=seed)
    residual.fit(X_tr[allowed], y_tr[allowed])
    thr = choose_hybrid_threshold(y_va, p_va, residual.predict_proba(X_va)[:, 1])
    ev["thresholds"]["model_a"] = round(thr, 3)
    ev["validation"]["model_a_hybrid"] = metrics(y_va, (p_va == 1) | (residual.predict_proba(X_va)[:, 1] >= thr))
    risk_te = residual.predict_proba(X_te)[:, 1]
    hybrid_te = ((p_te == 1) | (risk_te >= thr)).astype(int)
    ev["test"]["model_a_hybrid"] = metrics(y_te, hybrid_te)
    ev["held_out_cumulative"]["model_a_hybrid"] = metrics(
        y_ho, (p_ho == 1) | (residual.predict_proba(X_ho)[:, 1] >= thr))
    ev["added_by_learned_part_on_test"] = {
        "harmful_caught": int(((hybrid_te == 1) & (p_te == 0) & (y_te == 1)).sum()),
        "benign_blocked": int(((hybrid_te == 1) & (p_te == 0) & (y_te == 0)).sum()),
    }

    ranges = {n: [float(train_df[n].min()), float(train_df[n].max())] for n in FEATURES}
    artifact = {
        "model": residual,
        "model_kind": "physics rule OR gradient-boosted residual model",
        "threshold": float(thr),
        "features": FEATURES,
        "feature_ranges": ranges,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION,
        "model_version": MODEL_VERSION,
        "sklearn_version": sklearn.__version__,
        "trained_utc": ev["trained_utc"],
        "dataset_sha256": manifest.get("csv_sha256"),
        "chem_source": manifest.get("chem_source"),
        "liquid": manifest.get("liquid"),
        "seed": seed,
    }
    art_path = out_dir / "model_a.joblib"
    joblib.dump(artifact, art_path, compress=3)

    # ---- the saved model through the real Pi decision code
    model = ModelA(art_path)
    dep_te = run_deployed(model, test_df)
    ev["test"]["model_a_deployed"] = metrics(y_te, dep_te["block"].to_numpy())
    ev["test"]["model_a_deployed"]["answers"] = dep_te["label"].value_counts().to_dict()
    by_type = {}
    for rt, d in test_df.assign(block=dep_te["block"].to_numpy()).groupby("request_type"):
        harmful = d["harmful"] == 1
        by_type[rt] = {"rows": int(len(d)), "harmful": int(harmful.sum()),
                       "harmful_caught": int((d["block"][harmful] == 1).sum()),
                       "benign": int((~harmful).sum()),
                       "benign_blocked": int((d["block"][~harmful] == 1).sum())}
    ev["test_by_request_type"] = by_type
    dep_ho = run_deployed(model, heldout)
    ev["held_out_cumulative"]["model_a_deployed"] = metrics(y_ho, dep_ho["block"].to_numpy())
    if len(invalid):
        dep_inv = run_deployed(model, invalid)
        ev["fail_closed"] = {"rows": int(len(invalid)),
                             "uncertain": int((dep_inv["label"] == UNCERTAIN).sum()),
                             "reasons": dep_inv["reason"].value_counts().to_dict()}
    ev["host_latency_decide"] = latency(model, test_df)
    ev["platform"] = {"python": sys.version.split()[0], "sklearn": sklearn.__version__}

    same = same_dose_table(model, manifest.get("liquid", "bicarb_1mM"))
    same.to_csv(out_dir / "same_dose_different_tank.csv", index=False)
    pd.DataFrame({"feature": FEATURES, "importance": residual.feature_importances_}) \
        .sort_values("importance", ascending=False).to_csv(out_dir / "feature_importance.csv", index=False)
    preds = test_df[["episode_id", "request_type", "channel_id", "dose_ml", "true_ph_before",
                     "true_ph_after", "harmful", "ph_mean_5s", "predicted_post_ph"]].copy()
    preds["physics_block"] = p_te
    preds["model_a_risk"] = np.round(risk_te, 5)
    preds["model_a_label"] = dep_te["label"].to_numpy()
    preds["model_a_reason"] = dep_te["reason"].to_numpy()
    preds.to_csv(out_dir / "test_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})

    (out_dir / "evidence.json").write_text(json.dumps(ev, indent=2), encoding="utf-8")
    (out_dir / "MODEL_CARD.md").write_text(model_card(ev, same, residual), encoding="utf-8")
    if not quiet:
        _print(ev, out_dir)
    return ev


def model_card(ev: dict, same: pd.DataFrame, residual) -> str:
    t = ev["test"]
    rows = []
    for name, label in (("gateway_only", "Gateway only"), ("physics_rule", "Physics rule alone"),
                        ("logistic_regression", "Logistic regression"), ("random_forest", "Random forest"),
                        ("gradient_boosting", "Gradient boosting"),
                        ("model_a_hybrid", "**Model A** (physics rule + learned part)"),
                        ("model_a_deployed", "**Model A as it runs on the Pi** (UNCERTAIN counts as a block)")):
        m = t[name]
        rows.append(f"| {label} | {m['harmful_recall']:.3f} ({m['harmful_missed']} missed) | "
                    f"{m['benign_false_block_rate']:.3f} ({m['benign_blocked']} of {m['benign']}) |")
    ho = ev["held_out_cumulative"]
    fc = ev.get("fail_closed", {})
    lat = ev["host_latency_decide"]
    ds = ev["dataset"]
    same_md = "\n".join(
        f"| {r.dose} | {r.tank_ph:g} | {r.predicted_post_ph:.2f} | {r.true_post_ph:.2f} | "
        f"{r.truth.replace('_CONTEXT', '')} | {r.model_a.replace('_CONTEXT', '')} ({r.score:.2f}) |"
        for r in same.itertuples())
    top = sorted(zip(FEATURES, residual.feature_importances_), key=lambda x: -x[1])[:5]
    names = {"planner": "Planner (MILP) recovery doses", "rule_controller": "Naive controller doses",
             "fine_correction": "Small fine corrections", "wrong_direction": "Wrong direction",
             "oversize": "Oversize bulk doses", "random": "Random doses"}
    type_md = "\n".join(
        f"| {names.get(k, k)} | {v['harmful_caught']} of {v['harmful']} | {v['benign_blocked']} of {v['benign']} |"
        for k, v in ev["test_by_request_type"].items())
    return f"""# Model A model card

Trained {ev['trained_utc']}, model {MODEL_VERSION}, label policy {LABEL_POLICY_VERSION}, feature schema {FEATURE_SCHEMA_VERSION}, scikit-learn {ev['platform']['sklearn']}.
Dataset: {ds['rows']} requests ({ds['liquid']}, chemistry {ds['chem_source']}, sha256 `{str(ds['csv_sha256'])[:16]}...`).

## What it does
For each dose request that has passed the gateway's fixed checks, Model A answers ACCEPTABLE_CONTEXT, HARMFUL_CONTEXT or UNCERTAIN_CONTEXT with a risk score. HARMFUL when the physics rule flags the pH it predicts, or when the learned score is at or above **{ev['thresholds']['model_a']:.3f}** (picked on the validation set). UNCERTAIN when it can't judge: stale or missing probe data, lost Uno heartbeat, bad bottle name, a feature outside the training range, an error, or no answer within 100 ms. Only ACCEPTABLE lets a dose through. Model A can block a dose, never approve one on its own.

## Results on the held-out test episodes ({t['model_a_hybrid']['rows']} requests, {t['model_a_hybrid']['harmful']} harmful)

| System | Harmful recall | Benign false-block rate |
|---|---|---|
{chr(10).join(rows)}

The learned part caught {ev['added_by_learned_part_on_test']['harmful_caught']} harmful requests the physics rule missed, at the cost of {ev['added_by_learned_part_on_test']['benign_blocked']} extra benign blocks.

By kind of request (Model A as it runs on the Pi):

| Request | Harmful ones blocked | Good ones blocked |
|---|---|---|
{type_md}

**Never-seen pattern** (many small same-direction doses, {ho['model_a_hybrid']['rows']} requests, {ho['model_a_hybrid']['harmful']} harmful): physics rule recall {ho['physics_rule']['harmful_recall']:.3f}, Model A {ho['model_a_hybrid']['harmful_recall']:.3f} (false blocks {ho['model_a_hybrid']['benign_false_block_rate']:.3f}).

**Fail-closed check:** {fc.get('uncertain', 0)} of {fc.get('rows', 0)} requests the Pi can't judge came out UNCERTAIN.

**Speed (this computer, decision code only):** p50 {lat['p50_ms']} ms, p99 {lat['p99_ms']} ms, max {lat['max_ms']} ms over {lat['n']} requests. S4 allows 3,000 ms.

Most important inputs to the learned part: {', '.join(f'{n} ({v:.2f})' for n, v in top)}.

## Same dose, different tank (steady probe, baking-soda water)
| Dose | Tank pH | Pi predicts | Really ends at | Truth | Model A (score) |
|---|---|---|---|---|---|
{same_md}

## Limits
- Simulation evidence only. The chemistry table is {'a PLACEHOLDER, not Aspen' if ds['chem_source'] == 'PLACEHOLDER' else "CHE's Aspen export"}; probe noise and lag are assumed until measured.
- The report's goals (zero missed hazards, at most 5% false blocks) are reported as they came out, not tuned to.
- The score is a risk score, not a calibrated probability.
"""


def _print(ev: dict, out_dir: Path) -> None:
    t = ev["test"]
    print(f"Model A trained. Threshold {ev['thresholds']['model_a']:.3f}")
    for name in ("gateway_only", "physics_rule", "logistic_regression", "random_forest",
                 "gradient_boosting", "model_a_hybrid", "model_a_deployed"):
        m = t[name]
        print(f"  {name:22s} recall {m['harmful_recall']:.3f} ({m['harmful_missed']:4d} missed)   "
              f"false blocks {m['benign_false_block_rate']:.3f} ({m['benign_blocked']} of {m['benign']})")
    ho = ev["held_out_cumulative"]["model_a_hybrid"]
    print(f"  held-out cumulative    recall {ho['harmful_recall']:.3f}   false blocks {ho['benign_false_block_rate']:.3f}")
    fc = ev.get("fail_closed", {})
    print(f"  fail-closed            {fc.get('uncertain', 0)}/{fc.get('rows', 0)} UNCERTAIN")
    lat = ev["host_latency_decide"]
    print(f"  decision time          p50 {lat['p50_ms']} ms, p99 {lat['p99_ms']} ms, max {lat['max_ms']} ms")
    print(f"  wrote {out_dir}/model_a.joblib, evidence.json, MODEL_CARD.md")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m model_a.train", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--out", type=Path, default=HERE / "artifacts")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--table-dir", help="read the pH table from this folder instead of "
                    "sim/aspen_tables/ (testing only)")
    a = ap.parse_args(argv)
    if a.table_dir:
        os.environ["MODEL_A_TABLE_DIR"] = str(Path(a.table_dir).resolve())
    train(a.data, a.out, a.seed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
