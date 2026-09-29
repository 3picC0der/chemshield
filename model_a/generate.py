"""Model A dataset: simulated tank episodes with dose requests, labelled by physics.

    python -m model_a.generate                  # 3,000 episodes -> model_a/data/
    python -m model_a.generate --episodes 200 --out /tmp/modela_check

One episode = a few minutes of the tank, one probe reading per second, with a dose
request every 15-60 s. One dataset row = one dose request at one moment.

  * Features: only what the Pi can measure, computed by model_a/features.py, the same
    function the gateway calls live, against the planner's pH table (sim/aspen_tables/).
  * Label: from the hidden TRUE tank (model_a/truth.py: baking-soda water with its
    uncertainty, the real hand-dose volume), using label policy v1 (model_a/policy.py).

Built on Hattan's simulator: the pH table via sim.chemistry, the recovery doses from
redosing.planner (the MILP), and the upset sizes of sim.scenarios. What this adds is the
1 Hz probe (lag, noise, calibration offset, faults) and the dose requests, good and bad.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .features import build_features, default_chemistry
from .policy import harmful_rules
from .schema import (
    BAND_HI,
    BAND_LO,
    CHANNELS,
    FEATURE_SCHEMA_VERSION,
    FEATURES,
    LABEL_POLICY_VERSION,
    TEMP_C,
    V_NOMINAL_L,
)
from .truth import LIQUIDS, Liquid, net_base_for_ph, true_ph

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = HERE / "data"
GENERATOR_VERSION = "gen-1"
BULK_M = 0.5

# ------------------------------------------------------------------ parameter ranges
# Written down once, copied into the manifest and the dataset card. Replace the probe
# numbers with the values measured on the real probe (noise: 60 s in still water;
# lag: time to 95% of the change after one dose, divided by 3).
RANGES = {
    "episode_kind_probs": {"normal": 0.40, "recovery": 0.50, "cumulative": 0.10},
    "fill_L": (4.8, 5.2),
    "baking_soda_factor": (0.85, 1.15),     # weighing, dissolving and CO2 loss
    "start_ph_normal": (6.0, 8.5),
    "start_ph_cumulative": (6.5, 7.8),
    "upset_ml_0.5M": (2.0, 80.0),           # log-uniform: the small demo overdose to the 80 mL design event
    "upset_acid_fraction": 0.6,
    "probe_offset_sd": 0.10,                # calibration error, clipped at +/-0.3 pH
    "probe_noise_sd": (0.005, 0.04),
    "probe_lag_tau_s": (3.0, 20.0),
    "hand_dose_bias_sd": 0.03,              # syringe reading error per episode
    "hand_dose_noise_sd": 0.02,             # per dose
    "hand_delay_s": (2.0, 8.0),             # LED on -> dose in the tank
    "request_gap_s": (15.0, 60.0),          # the gateway's 15 s lockout sets the minimum
    "fault_probability": 0.35,
    "fault_probs": {"stuck": 0.25, "drift": 0.25, "gap": 0.20, "nostir": 0.15, "wrong_bottle": 0.15},
    "drift_rate_pH_per_s": (0.002, 0.01),
    "drift_max_pH": 1.5,                    # a drifting probe settles off by at most this much
    "gap_s": (3.0, 25.0),
}
REQUEST_MIX = {
    "NORMAL": {"fine_correction": 0.30, "rule_controller": 0.15, "wrong_direction": 0.15,
               "oversize": 0.15, "random": 0.25},
    "RECOVERY": {"planner": 0.40, "rule_controller": 0.15, "wrong_direction": 0.15,
                 "oversize": 0.10, "random": 0.20},
}


@dataclass
class Episode:
    episode_id: int
    seed: int
    kind: str
    liquid: str
    baking_soda_factor: float
    duration_s: int
    fill_L: float
    start_ph: float
    probe_offset: float
    noise_sd: float
    tau_s: float
    hand_bias: float
    fault: str
    fault_t: float
    fault_param: float
    upset_t: float
    upset_ml: float
    upset_acid: bool
    first_request_t: float


def sample_episodes(n: int, seed: int, liquid: str) -> list[Episode]:
    rng = np.random.default_rng(seed)
    kinds = list(RANGES["episode_kind_probs"])
    kind_p = list(RANGES["episode_kind_probs"].values())
    faults = list(RANGES["fault_probs"])
    fault_p = list(RANGES["fault_probs"].values())
    out = []
    for i in range(n):
        kind = str(rng.choice(kinds, p=kind_p))
        duration = int(rng.uniform(180, 420) if kind == "normal"
                       else rng.uniform(240, 600) if kind == "recovery" else rng.uniform(200, 320))
        fault = "none"
        if kind != "cumulative" and rng.random() < RANGES["fault_probability"]:
            fault = str(rng.choice(faults, p=fault_p))
        if fault == "drift":
            fault_param = float(rng.uniform(*RANGES["drift_rate_pH_per_s"]) * rng.choice([-1.0, 1.0]))
        elif fault == "gap":
            fault_param = float(rng.uniform(*RANGES["gap_s"]))
        else:
            fault_param = 0.0
        upset_t = float(rng.uniform(8.0, 30.0))
        lo, hi = RANGES["upset_ml_0.5M"]
        if kind == "recovery":
            first = upset_t + float(rng.uniform(1.5, 10.0))
        else:
            first = float(rng.uniform(1.0, 4.0) if rng.random() < 0.05 else rng.uniform(6.0, 20.0))
        start = RANGES["start_ph_cumulative"] if kind == "cumulative" else RANGES["start_ph_normal"]
        out.append(Episode(
            episode_id=i + 1,
            seed=int(rng.integers(0, 2**31 - 1)),
            kind=kind,
            liquid=liquid,
            baking_soda_factor=float(rng.uniform(*RANGES["baking_soda_factor"])),
            duration_s=duration,
            fill_L=float(rng.uniform(*RANGES["fill_L"])),
            start_ph=float(rng.uniform(*start)),
            probe_offset=float(np.clip(rng.normal(0.0, RANGES["probe_offset_sd"]), -0.3, 0.3)),
            noise_sd=float(rng.uniform(*RANGES["probe_noise_sd"])),
            tau_s=float(rng.uniform(*RANGES["probe_lag_tau_s"])),
            hand_bias=float(1.0 + rng.normal(0.0, RANGES["hand_dose_bias_sd"])),
            fault=fault,
            fault_t=float(rng.uniform(20.0, max(30.0, duration - 60.0))),
            fault_param=fault_param,
            upset_t=upset_t,
            upset_ml=float(math.exp(rng.uniform(math.log(lo), math.log(hi)))),
            upset_acid=bool(rng.random() < RANGES["upset_acid_fraction"]),
            first_request_t=first,
        ))
    return out


# ------------------------------------------------------------------ dose requests
def _toward_7(ph: float) -> int:
    """Direction that moves pH toward 7: acid (+1) above 7, base (-1) below."""
    return 1 if ph > 7.0 else -1


def _channel(direction: int, bulk: bool) -> str:
    return ("ACID_" if direction > 0 else "BASE_") + ("BULK" if bulk else "FINE")


def _ml(rng, lo=0.5, hi=20.0) -> float:
    return float(np.round(rng.uniform(lo, hi), 1))


def rule_controller(ph_mean: float, chem, volume_L: float) -> tuple[str, float]:
    """A naive controller: add what the table says brings pH to 7, capped at 20 mL."""
    need = chem.excess_from_ph(7.0, TEMP_C, volume_L) - chem.excess_from_ph(ph_mean, TEMP_C, volume_L)
    direction = -1 if need > 0 else 1                     # need > 0: base needed
    mmol = abs(need)
    if mmol >= 0.25:
        return _channel(direction, True), float(np.clip(np.round(mmol / BULK_M, 1), 0.5, 20.0))
    return _channel(direction, False), float(np.clip(np.round(mmol / 0.005, 1), 0.5, 20.0))


def make_request(kind: str, ph_mean: float, rng, chem, volume_L: float, planner_state: dict | None,
                 planner) -> tuple[str, str, float]:
    ph = ph_mean if math.isfinite(ph_mean) else 7.0
    if kind == "planner" and planner is not None and planner_state is not None:
        try:
            r = planner(planner_state)
        except Exception:                                   # noqa: BLE001
            r = {"action": "ERROR"}
        if r.get("action") == "DOSE" and r.get("channel_id") in CHANNELS and float(r.get("dose_ml", 0)) > 0:
            return "planner", str(r["channel_id"]), float(min(20.0, max(0.1, float(r["dose_ml"]))))
        kind = "rule_controller"                            # HOLD / ESCALATE: fall back
    if kind == "rule_controller":
        ch, ml = rule_controller(ph, chem, volume_L)
        return kind, ch, ml
    if kind == "fine_correction":
        return kind, _channel(_toward_7(ph), False), _ml(rng)
    if kind == "wrong_direction":
        return kind, _channel(-_toward_7(ph), bool(rng.random() < 0.5)), _ml(rng)
    if kind == "oversize":
        return kind, _channel(_toward_7(ph), True), _ml(rng, 5.0, 20.0)
    ch = str(rng.choice(sorted(CHANNELS)))
    return "random", ch, _ml(rng)


# ------------------------------------------------------------------ one episode
_PLANNER = None


def _worker_init() -> None:
    """Per process: point the planner at the pH table, as the live loop does."""
    global _PLANNER
    import warnings
    warnings.filterwarnings("ignore", message=".*PLACEHOLDER.*")
    default_chemistry()                                     # honours MODEL_A_TABLE_DIR
    from sim.engine import use_table_chemistry
    use_table_chemistry()
    from redosing.planner import plan_next_dose
    _PLANNER = plan_next_dose


def run_episode(ep: Episode) -> list[dict]:
    rng = np.random.default_rng(ep.seed)
    chem = default_chemistry()
    liquid: Liquid = LIQUIDS[ep.liquid].scaled(ep.baking_soda_factor)
    volume = ep.fill_L
    net = net_base_for_ph(ep.start_ph, volume, liquid)
    ph_true = true_ph(net, volume, liquid)
    probe = ph_true
    samples: list[tuple[float, float]] = []
    dose_log: list[dict] = []
    pending: list[tuple[float, float, float]] = []          # (t_apply, net change mmol, mL)
    last_uno = None
    stuck_value = None
    slow_until = -1.0
    wrong_bottle_used = False
    gap_request_done = False
    state = "NORMAL"
    upset_done = ep.kind != "recovery"
    t_event = None
    event_mmol = 0.0
    event_ml = 0.0
    rows: list[dict] = []
    next_req = int(ep.first_request_t)

    cum_dir = 1 if rng.random() < 0.5 else -1
    cum_bulk = rng.random() < 0.7
    cum_left = int(rng.integers(4, 11)) if ep.kind == "cumulative" else 0

    for k in range(ep.duration_s + 1):
        t = float(k)
        # ---- the true tank
        if not upset_done and t >= ep.upset_t:
            mmol = BULK_M * ep.upset_ml
            net += -mmol if ep.upset_acid else mmol
            volume += ep.upset_ml / 1000.0
            ph_true = true_ph(net, volume, liquid)
            upset_done = True
            state = "RECOVERY"
        due = [p for p in pending if p[0] <= t]
        if due:
            pending = [p for p in pending if p[0] > t]
            for _t, dnet, dml in due:
                net += dnet
                volume += dml / 1000.0
                if ep.fault == "nostir" and t >= ep.fault_t:
                    slow_until = t + 60.0
            ph_true = true_ph(net, volume, liquid)
        if t_event is None and state == "RECOVERY" and not (BAND_LO <= probe <= BAND_HI):
            t_event = t

        # ---- the probe, one reading per second
        tau = ep.tau_s * (4.0 if t < slow_until else 1.0)
        probe += (ph_true - probe) * (1.0 - math.exp(-1.0 / tau))
        reading = probe + ep.probe_offset + rng.normal(0.0, ep.noise_sd)
        fault_on = ep.fault != "none" and t >= ep.fault_t
        send = True
        if fault_on and ep.fault == "drift":
            reading += float(np.clip(ep.fault_param * (t - ep.fault_t),
                                     -RANGES["drift_max_pH"], RANGES["drift_max_pH"]))
        if fault_on and ep.fault == "stuck":
            if stuck_value is None:
                stuck_value = samples[-1][1] if samples else round(reading, 2)
            reading = stuck_value
        if fault_on and ep.fault == "gap" and t < ep.fault_t + ep.fault_param:
            send = False
        if send:
            t_arr = t + float(rng.uniform(0.0, 0.05))
            samples.append((t_arr, float(np.clip(round(reading, 2), 0.0, 14.0))))
            last_uno = t_arr

        # ---- a dose request somewhere in the next second
        if ep.fault == "gap" and not gap_request_done and ep.fault_param >= 4.0 \
                and k == int(ep.fault_t + 3.0):
            next_req = k                                    # USB pulled, then someone sends a dose
            gap_request_done = True
        if k != next_req:
            continue
        now = t + float(rng.uniform(0.06, 0.98))
        v_hat = V_NOMINAL_L + sum(d["dose_ml"] for d in dose_log) / 1000.0
        window = [s[1] for s in samples[-5:]]
        ph_seen = float(np.mean(window)) if window else math.nan

        if ep.kind == "cumulative":
            if cum_left <= 0:
                break
            req_type = "cumulative_bias"
            channel = _channel(cum_dir, cum_bulk)
            dose = _ml(rng, 0.5, 3.0) if cum_bulk else _ml(rng, 5.0, 20.0)
            cum_left -= 1
        else:
            mix = REQUEST_MIX[state]
            choice = str(rng.choice(list(mix), p=list(mix.values())))
            pstate = None
            if choice == "planner":
                pstate = {"t": now, "ph": ph_seen, "temp_c": TEMP_C, "level_ok": True, "excess_mmol": 0.0,
                          "state": "RECOVERY", "event_mmol_used": event_mmol, "event_ml_used": event_ml,
                          "event_elapsed_s": (now - t_event) if t_event is not None else 0.0,
                          "sample_age_s": (now - samples[-1][0]) if samples else 99.0,
                          "volume_L": v_hat, "source": "SIM"}
            req_type, channel, dose = make_request(choice, ph_seen, rng, chem, v_hat, pstate, _PLANNER)

        feats, problems = build_features(samples, now, channel, dose, dose_log, last_uno, chem=chem)

        molarity, direction = CHANNELS[channel]
        factor = ep.hand_bias * (1.0 + rng.normal(0.0, RANGES["hand_dose_noise_sd"]))
        post_true = true_ph(net - direction * molarity * dose * factor, volume + dose * factor / 1000.0, liquid)
        rules = harmful_rules(ph_true, post_true)
        valid = not problems

        rows.append({
            "episode_id": ep.episode_id, "episode_kind": ep.kind, "liquid": ep.liquid,
            "baking_soda_factor": round(ep.baking_soda_factor, 4), "fault": ep.fault,
            "fault_active": int(fault_on), "state": state, "request_idx": len(rows), "t_s": round(now, 3),
            "request_type": req_type, "channel_id": channel, "dose_ml": dose,
            "true_ph_before": round(ph_true, 4), "true_ph_after": round(post_true, 4),
            "label_rules": rules, "harmful": int(bool(rules)), "valid": int(valid),
            "invalid_reason": problems[0] if problems else "",
            **{n: feats[n] for n in FEATURES},
        })

        if valid and not rules:
            # Model A would pass it and the operator adds it by hand a few seconds later.
            dose_log.append({"t": now, "channel_id": channel, "dose_ml": dose,
                             "predicted_post_ph": feats["predicted_post_ph"]})
            m_applied = molarity
            if ep.fault == "wrong_bottle" and fault_on and not wrong_bottle_used:
                m_applied = 0.005 if molarity == BULK_M else BULK_M       # the other bottle
                wrong_bottle_used = True
            pending.append((now + float(rng.uniform(*RANGES["hand_delay_s"])),
                            -direction * m_applied * dose * factor, dose * factor))
            if state == "RECOVERY":
                event_mmol += molarity * dose
                event_ml += dose
        next_req = k + int(rng.uniform(*RANGES["request_gap_s"]))
    return rows


# ------------------------------------------------------------------ the whole dataset
def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:                                       # noqa: BLE001
        return "unknown"


def check_chemistry(chem, liquid: Liquid, allow_mismatch: bool) -> None:
    """The planner's table and the true liquid must describe the same water."""
    table_ph = float(chem.ph_from_excess(0.0, TEMP_C, 5.0))
    liquid_ph = true_ph(0.0, 5.0, liquid)
    if abs(table_ph - liquid_ph) > 0.3 and not allow_mismatch:
        raise SystemExit(
            f"The pH table in sim/aspen_tables/ says the untouched tank is pH {table_ph:.2f}, but the "
            f"tank liquid '{liquid.name}' starts at pH {liquid_ph:.2f}. They must describe the same water.\n"
            f"Load the baking-soda table (from the simulator fix or CHE's Aspen export), or pass "
            f"--liquid pure_water to match a pure-water table, or --allow-mismatch for a deliberate test.")


def generate(episodes: int, seed: int, liquid: str, out_dir: Path, workers: int,
             allow_mismatch: bool = False, quiet: bool = False) -> dict:
    import pandas as pd

    chem = default_chemistry()
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        chem_source = chem.table_provenance()
        table_files = chem.table_files()
    check_chemistry(chem, LIQUIDS[liquid], allow_mismatch)

    eps = sample_episodes(episodes, seed, liquid)
    t0 = time.time()
    rows: list[dict] = []
    if workers <= 1:
        _worker_init()
        for ep in eps:
            rows.extend(run_episode(ep))
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init) as pool:
            for chunk in pool.map(run_episode, eps, chunksize=16):
                rows.extend(chunk)
    wall = time.time() - t0

    df = pd.DataFrame(rows)
    df.insert(3, "chem_source", chem_source)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "modelA_dataset.csv.gz"
    text = df.to_csv(index=False, float_format="%.6g")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:       # mtime=0: same data, same bytes
        gz.write(text.encode("utf-8"))
    csv_path.write_bytes(buf.getvalue())

    valid = df[df.valid == 1]
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "seed": seed,
        "episodes": episodes,
        "rows": int(len(df)),
        "valid_rows": int(len(valid)),
        "invalid_rows": int((df.valid == 0).sum()),
        "harmful_fraction_valid": round(float(valid.harmful.mean()), 4) if len(valid) else None,
        "by_episode_kind": df.episode_kind.value_counts().to_dict(),
        "by_request_type": df.request_type.value_counts().to_dict(),
        "harmful_by_request_type": valid.groupby("request_type").harmful.mean().round(3).to_dict(),
        "by_fault": df.fault.value_counts().to_dict(),
        "invalid_reasons": df[df.valid == 0].invalid_reason.value_counts().to_dict(),
        "label_rules_fired": df.label_rules.replace("", "none").value_counts().to_dict(),
        "liquid": liquid,
        "chem_source": chem_source,
        "chem_table_files": table_files,
        "label_policy_version": LABEL_POLICY_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": FEATURES,
        "ranges": RANGES,
        "request_mix": REQUEST_MIX,
        "csv": csv_path.name,
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "wall_s": round(wall, 1),
        "workers": workers,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out_dir / "DATASET_CARD.md").write_text(dataset_card(manifest), encoding="utf-8")
    if not quiet:
        print(f"Model A dataset: {manifest['rows']} requests from {episodes} episodes in {wall:.0f} s "
              f"(chemistry {chem_source}, liquid {liquid})")
        print(f"  valid {manifest['valid_rows']}, harmful fraction {manifest['harmful_fraction_valid']}, "
              f"invalid (fail-closed test) {manifest['invalid_rows']}")
        print(f"  wrote {csv_path}\n  wrote {out_dir / 'manifest.json'}\n  wrote {out_dir / 'DATASET_CARD.md'}")
    return manifest


def dataset_card(m: dict) -> str:
    r = m["ranges"]
    chem_note = ("the **placeholder** pH table (not Aspen yet)" if m["chem_source"] == "PLACEHOLDER"
                 else "CHE's **Aspen** pH table")
    kinds = ", ".join(f"{k} {v}" for k, v in m["by_episode_kind"].items())
    types = "\n".join(f"| {k} | {v} | {m['harmful_by_request_type'].get(k, '')} |"
                      for k, v in m["by_request_type"].items())
    return f"""# Model A dataset card

Generated {m['created_utc']} from commit `{m['git_commit']}`, seed {m['seed']}. Label policy {m['label_policy_version']}, feature schema {m['feature_schema_version']}.
File: `{m['csv']}` (sha256 `{m['csv_sha256'][:16]}...`).

## What it is
{m['rows']} dose requests from {m['episodes']} simulated episodes of the 5 L tank ({kinds}). One row = one request: the 16 features the Pi can measure at that moment, plus the correct answer from physics.

## How it was made
- **Tank liquid:** {m['liquid']} (5.000 L distilled water + 0.420 g baking soda). The true amount of baking soda varies by x{r['baking_soda_factor'][0]}-{r['baking_soda_factor'][1]} per episode (weighing, dissolving, CO2 loss).
- **The Pi's chemistry:** features use {chem_note} through `sim.chemistry`, the same table Hattan's planner uses (`{', '.join(m['chem_table_files'])}`).
- **Episodes:** fill {r['fill_L'][0]}-{r['fill_L'][1]} L. Normal episodes start at pH {r['start_ph_normal'][0]}-{r['start_ph_normal'][1]}. Recovery episodes add an upset of {r['upset_ml_0.5M'][0]}-{r['upset_ml_0.5M'][1]} mL of 0.5 M acid or base, bypassing the gateway.
- **Probe:** one reading per second, rounded to 0.01 like the Uno's `PH,x` line. Calibration offset sd {r['probe_offset_sd']} pH, noise {r['probe_noise_sd'][0]}-{r['probe_noise_sd'][1]} pH, lag {r['probe_lag_tau_s'][0]}-{r['probe_lag_tau_s'][1]} s. *These are assumptions until the probe is measured.*
- **Hand dosing:** syringe error sd {r['hand_dose_bias_sd']} per episode + {r['hand_dose_noise_sd']} per dose; added {r['hand_delay_s'][0]}-{r['hand_delay_s'][1]} s after the LED.
- **Faults** in {int(r['fault_probability'] * 100)}% of normal/recovery episodes: stuck probe, drifting probe, USB gap (no readings), no stirring, wrong bottle.
- **Requests:** every {r['request_gap_s'][0]:.0f}-{r['request_gap_s'][1]:.0f} s. Recovery doses come from Hattan's MILP planner; the rest are fine corrections, a naive controller, wrong direction, oversize bulk doses and random doses. The same doses appear in both safe and harmful contexts.

| Request type | Rows | Harmful fraction |
|---|---|---|
{types}

## The label (policy {m['label_policy_version']})
The dose is applied to the **true** tank (true baking soda, true hand-dose volume) and the settled pH is checked. HARMFUL if it (a) leaves 5.5-9.5, (b) moves an already abnormal tank (outside 6.3-8.2) more than 0.2 farther from 7, (c) crosses from below 6.3 to above 8.2 or back, or (d) takes a tank inside 6.0-8.5 outside that band. Otherwise ACCEPTABLE. The features never see the true values.

## Splits
Split by episode (60/20/20), never by row. The `cumulative` episodes (many small same-direction doses) are held out of training completely, to test on a pattern the model has never seen. Rows the Pi can't judge (stale or missing readings, lost heartbeat: {m['invalid_rows']} rows) are kept out of training and used to check that Model A answers UNCERTAIN.

## Limits
- Simulation only: {'the pH table is a placeholder, not Aspen' if m['chem_source'] == 'PLACEHOLDER' else 'chemistry from Aspen'}; the true tank is a closed carbonate model at 25 C.
- Probe noise and lag are assumed ranges until measured on the real probe.
- Features 12 (delivery residual) and 14 (mixer ratio) are fixed at 0 and 1: no pump feedback or mixer at the PPR.
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m model_a.generate", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--episodes", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=261)
    ap.add_argument("--liquid", default="bicarb_1mM", choices=sorted(LIQUIDS))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--allow-mismatch", action="store_true",
                    help="generate even if the pH table and the liquid disagree (testing only)")
    ap.add_argument("--table-dir", help="read the pH table from this folder instead of "
                    "sim/aspen_tables/ (testing only)")
    a = ap.parse_args(argv)
    if a.table_dir:
        os.environ["MODEL_A_TABLE_DIR"] = str(Path(a.table_dir).resolve())
    generate(a.episodes, a.seed, a.liquid, a.out, a.workers, a.allow_mismatch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
