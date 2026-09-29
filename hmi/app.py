"""ChemShield HMI demo for Khalid's gateway work.

Run from repo root:
    uvicorn hmi.app:app --reload
Then open:
    http://127.0.0.1:8000
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json
from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_FILE = ROOT / "gateway" / "khalid_ics_all_in_one.py"
spec = importlib.util.spec_from_file_location("khalid_gateway", GATEWAY_FILE)
kg = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(kg)

app = FastAPI(title="ChemShield HMI - Khalid")
GATEWAY = kg.GatewayValidator()
LAST_DECISION = None
COUNTERS = {"accepted": 0, "rejected": 0, "attacks_blocked": 0}

STYLE = """
<style>
body{font-family:Arial, sans-serif; margin:30px; background:#f5f7fb; color:#172033;}
.card{background:white; padding:18px; margin:12px 0; border-radius:12px; box-shadow:0 2px 8px #ccd;}
.grid{display:grid; grid-template-columns:1fr 1fr; gap:14px;}
input,select,button{padding:10px; margin:5px; border-radius:8px; border:1px solid #bbb;}
button{background:#0b5fff; color:white; border:0; cursor:pointer;}
.badge{display:inline-block; padding:8px 12px; border-radius:18px; background:#eef; margin:4px;}
.accept{background:#d7f8df;}.reject{background:#ffe0e0;}.hold{background:#fff1c9;}
pre{background:#111827; color:#e5e7eb; padding:12px; border-radius:10px; overflow:auto;}
</style>
"""


def render_page(message: str = "") -> str:
    decision_html = "<p>No command sent yet.</p>"
    if LAST_DECISION:
        cls = "accept" if LAST_DECISION.decision == "ACCEPT" else "reject"
        decision_html = f"""
        <div class='badge {cls}'><b>{LAST_DECISION.decision}</b></div>
        <p><b>Reason:</b> {LAST_DECISION.reason_code} - {LAST_DECISION.reason_detail}</p>
        <p><b>Model A:</b> {LAST_DECISION.model_a_label} | score={LAST_DECISION.model_a_score} | latency={LAST_DECISION.model_a_latency_ms} ms</p>
        <p><b>Forwarded to actuator:</b> {LAST_DECISION.forwarded_to_actuator}</p>
        <p><b>Gateway latency:</b> {LAST_DECISION.latency_ms} ms</p>
        """

    audit_tail = GATEWAY.audit.records[-8:]
    audit_text = json.dumps(audit_tail, indent=2)
    state_class = "hold" if GATEWAY.state.mode == "SAFE_HOLD" else "accept"
    return f"""
    <html><head><title>ChemShield HMI</title>{STYLE}</head><body>
    <h1>ChemShield Operator HMI</h1>
    <p>This is Khalid's demo HMI: command form, gateway decision, Model A result, counters, and audit log.</p>
    <div class='grid'>
      <div class='card'>
        <h2>System State</h2>
        <span class='badge {state_class}'>Mode: {GATEWAY.state.mode}</span>
        <span class='badge'>pH: {GATEWAY.state.ph}</span>
        <span class='badge'>Heartbeat: {GATEWAY.state.heartbeat_healthy}</span>
        <span class='badge'>Recovery mmol: {GATEWAY.state.cumulative_recovery_mmol}</span>
        <p>{message}</p>
      </div>
      <div class='card'>
        <h2>Counters</h2>
        <span class='badge accept'>Accepted: {COUNTERS['accepted']}</span>
        <span class='badge reject'>Rejected: {COUNTERS['rejected']}</span>
        <span class='badge reject'>Attacks blocked: {COUNTERS['attacks_blocked']}</span>
      </div>
    </div>
    <div class='card'>
      <h2>Dose Request</h2>
      <form action='/dose' method='post'>
        <label>Reagent</label><select name='reagent'><option>base</option><option>acid</option></select>
        <label>Volume mL</label><input type='number' step='0.1' name='volume_ml' value='10'>
        <label>Flow mL/min</label><input type='number' step='1' name='flow_ml_min' value='300'>
        <label>Recovery mmol after command</label><input type='number' step='0.1' name='recovery_mmol' value='10'>
        <button type='submit'>Send through gateway</button>
      </form>
      <form action='/attack' method='post'><button type='submit'>Run stale/replay attack sample</button></form>
      <form action='/halt' method='post'><button type='submit'>HALT / SAFE_HOLD</button></form>
      <form action='/ack' method='post'><button type='submit'>ACK / return NORMAL</button></form>
    </div>
    <div class='card'><h2>Last Decision</h2>{decision_html}</div>
    <div class='card'><h2>Audit Log Tail</h2><pre>{audit_text}</pre></div>
    </body></html>
    """


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render_page()


@app.post("/dose", response_class=HTMLResponse)
def dose(reagent: str = Form("base"), volume_ml: float = Form(10.0), flow_ml_min: float = Form(300.0), recovery_mmol: float = Form(10.0)) -> str:
    global LAST_DECISION
    now = datetime.now(timezone.utc)
    seq = GATEWAY.last_sequence_number + 1
    cmd = kg.make_command(
        GATEWAY.config,
        command_id=f"HMI-CMD-{seq:04d}",
        event_id=f"HMI-EVT-{seq:04d}",
        timestamp_utc=now,
        nonce=f"HMI-NONCE-{seq:04d}",
        sequence_number=seq,
        reagent=reagent,
        volume_ml=volume_ml,
        flow_ml_min=flow_ml_min,
        recovery_mmol_after_command=recovery_mmol,
    )
    LAST_DECISION = GATEWAY.validate(cmd, "hmi_manual", now)
    if LAST_DECISION.decision == "ACCEPT":
        COUNTERS["accepted"] += 1
    else:
        COUNTERS["rejected"] += 1
    return render_page("Command processed through ChemShield gateway.")


@app.post("/attack", response_class=HTMLResponse)
def attack() -> str:
    global LAST_DECISION
    now = datetime.now(timezone.utc)
    stale = kg.make_command(
        GATEWAY.config,
        command_id="HMI-ATTACK-STALE",
        event_id="HMI-ATTACK-EVT",
        timestamp_utc=now.replace(year=now.year) - kg.timedelta(seconds=45),
        nonce="HMI-ATTACK-NONCE",
        sequence_number=GATEWAY.last_sequence_number + 99,
    )
    LAST_DECISION = GATEWAY.validate(stale, "hmi_attack_stale", now)
    COUNTERS["rejected"] += 1
    COUNTERS["attacks_blocked"] += 1
    return render_page("Stale attack sample sent. It should be rejected.")


@app.post("/halt", response_class=HTMLResponse)
def halt() -> str:
    GATEWAY.state.mode = "SAFE_HOLD"
    GATEWAY.state.heartbeat_healthy = False
    return render_page("System moved to SAFE_HOLD.")


@app.post("/ack", response_class=HTMLResponse)
def ack() -> str:
    GATEWAY.manual_ack()
    return render_page("Manual acknowledgement accepted. System returned to NORMAL.")
