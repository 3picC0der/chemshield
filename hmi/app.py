from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "gateway" / "src"))

from chemshield_gateway.config import GatewayConfig
from chemshield_gateway.gateway_validator import GatewayValidator
from chemshield_gateway.models import ProcessState
from chemshield_gateway.test_data import make_command

app = FastAPI(title="ChemShield HMI - Khalid")
config = GatewayConfig()
state = ProcessState(ph=7.0, mode="NORMAL")
gateway = GatewayValidator(config=config, state=state)


class DoseRequest(BaseModel):
    reagent: str
    volume_ml: float
    flow_ml_min: float = 300.0
    role: str = "operator"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html>
<head>
  <title>ChemShield HMI</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 28px; background: #f7f7f7; }
    .card { background: white; padding: 18px; margin-bottom: 16px; border-radius: 12px; box-shadow: 0 1px 5px #ccc; }
    label { display: inline-block; width: 120px; }
    input, select { padding: 6px; margin: 4px; }
    button { padding: 8px 12px; margin: 5px; cursor: pointer; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border: 1px solid #ddd; padding: 6px; font-size: 14px; }
    .ok { color: green; font-weight: bold; }
    .bad { color: #b00020; font-weight: bold; }
  </style>
</head>
<body>
  <h1>ChemShield HMI — Khalid Gateway Demo</h1>
  <div class="card">
    <h2>System State</h2>
    <div id="state">Loading...</div>
    <button onclick="halt()">HALT / SAFE_HOLD</button>
    <button onclick="ack()">ACK + New Session</button>
  </div>
  <div class="card">
    <h2>Dose Request</h2>
    <label>Reagent</label><select id="reagent"><option>base</option><option>acid</option><option>none</option></select><br>
    <label>Volume mL</label><input id="volume" type="number" value="12" step="0.5"><br>
    <label>Flow mL/min</label><input id="flow" type="number" value="300"><br>
    <button onclick="sendDose()">Send to Gateway</button>
    <p id="decision"></p>
  </div>
  <div class="card">
    <h2>Audit Log</h2>
    <table><thead><tr><th>#</th><th>Command</th><th>Decision</th><th>Reason</th><th>Forwarded</th></tr></thead><tbody id="audit"></tbody></table>
  </div>
<script>
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  document.getElementById('state').innerHTML = `pH: <b>${s.ph}</b> | Mode: <b>${s.mode}</b> | Heartbeat: <b>${s.heartbeat_healthy}</b> | Lockout: <b>${s.mixing_lockout_remaining_s}s</b> | Commands: <b>${s.audit_count}</b>`;
  const audit = await (await fetch('/api/audit')).json();
  document.getElementById('audit').innerHTML = audit.records.slice(-15).reverse().map(r => `<tr><td>${r.index}</td><td>${r.command_id}</td><td>${r.decision}</td><td>${r.reason_code}</td><td>${r.forwarded_to_actuator}</td></tr>`).join('');
}
async function sendDose(){
  const body = {reagent: document.getElementById('reagent').value, volume_ml: parseFloat(document.getElementById('volume').value), flow_ml_min: parseFloat(document.getElementById('flow').value)};
  const r = await (await fetch('/api/dose', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})).json();
  const cls = r.decision === 'ACCEPT' ? 'ok' : 'bad';
  document.getElementById('decision').innerHTML = `<span class="${cls}">${r.decision}</span> | ${r.reason_code} | Model A: ${r.model_a_label} (${r.model_a_latency_ms} ms) | Forwarded: ${r.forwarded_to_actuator}`;
  refresh();
}
async function halt(){ await fetch('/api/halt', {method:'POST'}); refresh(); }
async function ack(){ await fetch('/api/ack', {method:'POST'}); refresh(); }
refresh(); setInterval(refresh, 2000);
</script>
</body>
</html>
"""


@app.get("/api/state")
def api_state() -> dict:
    return {
        "ph": gateway.state.ph,
        "mode": gateway.state.mode,
        "heartbeat_healthy": gateway.state.heartbeat_healthy,
        "mixing_lockout_remaining_s": round(gateway.lockout_remaining_s(), 1),
        "audit_count": len(gateway.audit_log.records),
    }


@app.post("/api/dose")
def api_dose(req: DoseRequest) -> dict:
    now = datetime.now(timezone.utc)
    seq = gateway.last_sequence_number + 1
    command = make_command(
        config,
        command_id=f"HMI-{uuid4().hex[:8]}",
        event_id="HMI-EVENT",
        timestamp_utc=now,
        nonce=f"HMI-NONCE-{uuid4().hex}",
        sequence_number=seq,
        user_role=req.role,
        reagent=req.reagent,
        volume_ml=req.volume_ml,
        flow_ml_min=req.flow_ml_min,
        recovery_mmol_after_command=min(50.0, gateway.state.cumulative_recovery_mmol + req.volume_ml),
    )
    result = gateway.validate(command, category="hmi_manual", received_at_utc=now)
    return result.to_dict()


@app.get("/api/audit")
def api_audit() -> dict:
    return {"records": [r.__dict__ for r in gateway.audit_log.records], "hash_chain_valid": gateway.audit_log.verify()}


@app.post("/api/halt")
def api_halt() -> dict:
    gateway.state.mode = "SAFE_HOLD"
    gateway.state.heartbeat_healthy = False
    return {"mode": gateway.state.mode}


@app.post("/api/ack")
def api_ack() -> dict:
    gateway.manual_ack_new_session()      # ACK does not cut the mixing lockout short
    return {"mode": gateway.state.mode}
