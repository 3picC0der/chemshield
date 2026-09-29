"""ICS-AT-03 (S4): time 1,000 dose requests through the real gateway and Model A.

    python -m model_a.latency_test --gateway-src "<Khalid's gateway>/src"
    python -m model_a.latency_test --n 1000 --out evidence/ICS/ICS-AT-03/pi_run

Every request is signed and goes through Khalid's GatewayValidator.validate() with the
real Model A plugged in (ModelAClient). Nothing is sent to the Uno: the gateway's
actuator here is its SimulatedActuator (dry run).

Decision time = from the moment the gateway receives the request until validate()
returns, with the Model A class and score in the decision and the audit record written.

Test-harness only (written on the ICS-AT-03 sheet): before each request the harness
  * gives Model A 5 fresh probe readings for the scenario (as the serial bridge would);
  * clears the gateway's 15 s mixing lockout (state.last_dose_accepted_at_s) and gives
    each request its own event id, because otherwise the lockout and the 50 mmol per-event
    limit would reject most of 1,000 back-to-back requests before Model A is called.

Scenarios: normal (small correction near pH 7), harmful (big wrong-way dose), recovery
(correct dose in an acid tank) and uncertain (USB pulled: readings 4 s old).

--timeout-check adds 3 requests with Model A frozen for 10 s: each must come back
UNCERTAIN (reason TIMEOUT) within about 100 ms, and the gateway must block it.

Writes to --out: ICS-AT-03_latency.csv, ICS-AT-03_summary.json, ICS-AT-03_histogram.png,
ICS-AT-03_machine_info.txt, model_a_decisions.csv (and ICS-AT-03_timeout_check.csv).
"""
from __future__ import annotations

import argparse
import csv
import inspect
import json
import os
import platform
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .inference import ModelAClient, ProcessContext
from .schema import CHANNELS, LABELS, UNCERTAIN

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = REPO / "evidence" / "ICS" / "ICS-AT-03" / "laptop_dry_run"
LIMIT_MS = 3000.0

SCENARIOS = {                  # weight, tank pH, (bottle, mL range), readings age
    "normal":    (0.40, 7.0, (("BASE_FINE", "ACID_FINE"), (0.5, 10.0)), 0.3),
    "harmful":   (0.30, 6.2, (("ACID_BULK",), (10.0, 20.0)), 0.3),
    "recovery":  (0.10, 3.5, (("BASE_FINE",), (2.0, 10.0)), 0.3),
    "uncertain": (0.20, 7.0, (("BASE_FINE",), (1.0, 5.0)), 4.0),
}

# gateway attributes that hold "a dose was just accepted" state; reset between requests
LOCKOUT_ATTRS = ("last_dose_accepted_at_s",)


def load_gateway(src: Path):
    if not (src / "chemshield_gateway").is_dir():
        raise SystemExit(f"Khalid's gateway package isn't at {src}/chemshield_gateway. Pass "
                         f"--gateway-src <folder that contains chemshield_gateway>.")
    sys.path.insert(0, str(src))
    from chemshield_gateway import auth, test_data
    from chemshield_gateway.config import GatewayConfig
    from chemshield_gateway.gateway_validator import GatewayValidator
    return GatewayConfig, GatewayValidator, test_data, auth


def make_signed_command(config, test_data, auth, i: int, channel_id: str, dose_ml: float) -> dict:
    """A valid signed request in whatever command format the gateway currently uses."""
    molarity, direction = CHANNELS[channel_id]
    wanted = {
        "command_id": f"LAT-{i:05d}-{uuid.uuid4().hex[:6]}",
        "event_id": f"EVT-LAT-{i:05d}",
        "timestamp_utc": datetime.now(timezone.utc),
        "nonce": uuid.uuid4().hex,
        "sequence_number": i,
        "channel_id": channel_id,
        "volume_ml": dose_ml,
        "reagent": "acid" if direction > 0 else "base",                   # gateway before 002041d
        "recovery_mmol_after_command": round(molarity * dose_ml, 4),      # gateway before 002041d
    }
    accepted = inspect.signature(test_data.unsigned_command).parameters
    cmd = test_data.unsigned_command(config, **{k: v for k, v in wanted.items() if k in accepted})
    cmd.setdefault("channel_id", channel_id)
    return auth.attach_hmac(cmd, config.hmac_secret)


def reset_gateway(validator) -> None:
    st = validator.state
    for name, value in (("mixing_lockout_remaining_s", 0.0), ("cumulative_recovery_mmol", 0.0),
                        ("mode", "NORMAL"), ("heartbeat_healthy", True)):
        if hasattr(st, name):
            setattr(st, name, value)
    for obj in (validator, st):
        for name in LOCKOUT_ATTRS:
            if hasattr(obj, name):
                setattr(obj, name, None)
    if isinstance(getattr(validator, "event_mmol_used", None), dict):
        validator.event_mmol_used.clear()


def fresh_context(tank_ph: float, age_s: float, rng) -> ProcessContext:
    ctx = ProcessContext()
    now = ctx.clock()
    for k in range(5):
        ctx.add_sample(round(tank_ph + float(rng.normal(0.0, 0.01)), 2), t=now - age_s - 4.0 + k)
    return ctx


def machine_info() -> str:
    lines = [f"recorded_utc: {datetime.now(timezone.utc).isoformat(timespec='seconds')}"]
    model_file = Path("/proc/device-tree/model")
    if model_file.exists():
        lines.append("device: " + model_file.read_text(errors="ignore").strip("\x00\n "))
    lines += [f"platform: {platform.platform()}", f"machine: {platform.machine()}",
              f"processor: {platform.processor() or 'n/a'}", f"cpus: {os.cpu_count()}",
              f"python: {sys.version.split()[0]}"]
    try:
        import sklearn
        lines.append(f"scikit-learn: {sklearn.__version__}")
    except ImportError:
        pass
    return "\n".join(lines) + "\n"


def histogram(times_ms: np.ndarray, summary: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    ax.hist(times_ms, bins=40, color="#3b6fd8", edgecolor="white")
    ax.set_xlabel("Decision time per request (ms): gateway receives it -> class, score, audit record")
    ax.set_ylabel("Requests")
    ax.set_title(f"ICS-AT-03 (S4): {summary['requests']} requests, {summary['device']}")
    ax.axvline(summary["decision_ms"]["max"], color="#c0392b", linestyle="--", linewidth=1)
    ax.text(0.98, 0.95,
            f"mean {summary['decision_ms']['mean']:.2f} ms\np99 {summary['decision_ms']['p99']:.2f} ms\n"
            f"max {summary['decision_ms']['max']:.2f} ms\nlimit {LIMIT_MS:,.0f} ms (S4)\n"
            f"unclassified: {summary['unclassified']}",
            transform=ax.transAxes, ha="right", va="top", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="#9ca3af"))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def run(n: int, gateway_src: Path, out: Path, seed: int = 261, timeout_check: bool = True,
        artifact: Path | None = None) -> dict:
    GatewayConfig, GatewayValidator, test_data, auth = load_gateway(gateway_src)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    config = GatewayConfig()
    decisions_log = out / "model_a_decisions.csv"
    if decisions_log.exists():
        decisions_log.unlink()
    client = ModelAClient(config=config, artifact_path=artifact, decision_log=decisions_log)
    if client.model is None:
        raise SystemExit(f"Model A did not load: {client.load_error}")
    validator = GatewayValidator(config=config, model_a=client)

    names = list(SCENARIOS)
    weights = np.array([SCENARIOS[s][0] for s in names])
    rows = []
    for i in range(1, n + 1):
        scenario = str(rng.choice(names, p=weights / weights.sum()))
        _w, tank_ph, (bottles, (lo, hi)), age = SCENARIOS[scenario]
        channel_id = str(rng.choice(bottles))
        dose_ml = float(np.round(rng.uniform(lo, hi), 1))
        client.context = fresh_context(tank_ph, age, rng)
        reset_gateway(validator)
        cmd = make_signed_command(config, test_data, auth, i, channel_id, dose_ml)
        received = datetime.now(timezone.utc)
        t0 = time.perf_counter()
        d = validator.validate(cmd)
        decision_ms = (time.perf_counter() - t0) * 1000.0
        decided = datetime.now(timezone.utc)
        rows.append({
            "request": i, "scenario": scenario, "command_id": cmd["command_id"], "channel_id": channel_id,
            "dose_ml": dose_ml, "tank_ph": tank_ph, "gateway_decision": d.decision,
            "gateway_reason": d.reason_code, "model_a_label": d.model_a_label,
            "model_a_score": d.model_a_score, "model_a_latency_ms": d.model_a_latency_ms,
            "gateway_latency_ms": d.latency_ms, "decision_time_ms": round(decision_ms, 4),
            "received_utc": received.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "decided_utc": decided.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        })

    with open(out / "ICS-AT-03_latency.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    times = np.array([r["decision_time_ms"] for r in rows])
    model_ms = np.array([r["model_a_latency_ms"] for r in rows])
    unclassified = sum(1 for r in rows if r["model_a_label"] not in LABELS)
    info = machine_info()
    device = next((ln.split(": ", 1)[1] for ln in info.splitlines() if ln.startswith("device: ")),
                  platform.machine() + " " + platform.system())
    summary = {
        "test": "ICS-AT-03 (S4: incident class and risk score within 3 s)",
        "device": device,
        "requests": len(rows),
        "unclassified": unclassified,
        "labels": {lab: sum(1 for r in rows if r["model_a_label"] == lab) for lab in LABELS},
        "gateway_decisions": {k: sum(1 for r in rows if r["gateway_decision"] == k) for k in ("ACCEPT", "REJECT")},
        "decision_ms": {"mean": round(float(times.mean()), 4), "p50": round(float(np.percentile(times, 50)), 4),
                        "p99": round(float(np.percentile(times, 99)), 4), "max": round(float(times.max()), 4)},
        "model_a_ms": {"mean": round(float(model_ms.mean()), 4), "p99": round(float(np.percentile(model_ms, 99)), 4),
                       "max": round(float(model_ms.max()), 4)},
        "limit_ms": LIMIT_MS,
        "model_version": client.model_version,
        "threshold": client.model.threshold,
    }
    summary["pass"] = bool(unclassified == 0 and summary["decision_ms"]["max"] < LIMIT_MS)

    if timeout_check:
        client.model.debug_delay_s = 10.0
        checks = []
        for j in range(3):
            client.context = fresh_context(7.0, 0.3, rng)
            reset_gateway(validator)
            cmd = make_signed_command(config, test_data, auth, n + 1 + j, "BASE_FINE", 1.0)
            t0 = time.perf_counter()
            d = validator.validate(cmd)
            checks.append({"request": n + 1 + j, "model_a_label": d.model_a_label,
                           "gateway_decision": d.decision, "gateway_reason": d.reason_code,
                           "decision_time_ms": round((time.perf_counter() - t0) * 1000.0, 3)})
        client.model.debug_delay_s = 0.0
        with open(out / "ICS-AT-03_timeout_check.csv", "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(checks[0]))
            w.writeheader()
            w.writerows(checks)
        summary["timeout_check"] = {
            "requests": len(checks),
            "all_uncertain_and_blocked": all(c["model_a_label"] == UNCERTAIN and c["gateway_decision"] == "REJECT"
                                             for c in checks),
            "max_decision_ms": max(c["decision_time_ms"] for c in checks),
        }
        summary["pass"] = bool(summary["pass"] and summary["timeout_check"]["all_uncertain_and_blocked"]
                               and summary["timeout_check"]["max_decision_ms"] < LIMIT_MS)

    (out / "ICS-AT-03_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "ICS-AT-03_machine_info.txt").write_text(info, encoding="utf-8")
    histogram(times, summary, out / "ICS-AT-03_histogram.png")

    print(f"ICS-AT-03 on {device}: {summary['requests']} requests, unclassified {unclassified}")
    print(f"  labels {summary['labels']}")
    dm = summary["decision_ms"]
    print(f"  decision time: mean {dm['mean']} ms, p50 {dm['p50']} ms, p99 {dm['p99']} ms, max {dm['max']} ms "
          f"(limit {LIMIT_MS:,.0f} ms)")
    if timeout_check:
        tc = summary["timeout_check"]
        print(f"  Model A frozen: all UNCERTAIN and blocked = {tc['all_uncertain_and_blocked']}, "
              f"max {tc['max_decision_ms']} ms")
    print(f"  {'PASS' if summary['pass'] else 'FAIL'}   -> {out}")
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m model_a.latency_test", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--gateway-src", type=Path,
                    default=Path(os.environ.get("CHEMSHIELD_GATEWAY_SRC", REPO / "gateway" / "src")),
                    help="folder that contains Khalid's chemshield_gateway package")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=261)
    ap.add_argument("--artifact", type=Path, default=None)
    ap.add_argument("--no-timeout-check", action="store_true")
    a = ap.parse_args(argv)
    s = run(a.n, a.gateway_src, a.out, a.seed, not a.no_timeout_check, a.artifact)
    return 0 if s["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
