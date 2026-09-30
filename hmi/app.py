"""The laptop HMI: the operator's screen, served only to this laptop (127.0.0.1).

    .venv/bin/python -m hmi --station http://<pi-ip>:8000      # the real rig
    .venv/bin/python -m hmi.demo                                # everything on this laptop

This server holds the operator key. The browser asks it for a dose; it builds the I1
request, signs it (HMAC-SHA256), and sends it over the Wi-Fi to the gateway on the Pi.
It never talks to the Uno and it decides nothing: the gateway and Model A on the Pi do.
Because it listens on 127.0.0.1 only, nobody else on the Wi-Fi can use it to sign.

(Khalid's first HMI ran the gateway inside the web server and signed any request that
reached /api/dose, so anyone on the Wi-Fi could dose through it. This replaces it.)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from hmi.common import (
    CHANNELS,
    STATION_PORT,
    gateway_config,
    load_secret,
    new_dose_command,
    new_operator_action,
    next_sequence,
)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
STATION = os.environ.get("CHEMSHIELD_STATION", f"http://127.0.0.1:{STATION_PORT}").rstrip("/")
OPERATOR = os.environ.get("CHEMSHIELD_OPERATOR", "Operator")
HAND_SPEED_ML_S = float(os.environ.get("CHEMSHIELD_HAND_SPEED", "2.0"))

SECRET, KEY_SOURCE = load_secret()
CONFIG = gateway_config(SECRET)

app = FastAPI(title="ChemShield HMI (laptop)", docs_url=None, redoc_url=None)
_last: dict[str, Any] = {"state": None, "signed": None}   # last station state; last signed command


def _station(path: str, body: dict[str, Any] | None = None, timeout: float = 3.0) -> tuple[int, Any]:
    url = STATION + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            return r.status, (json.loads(raw) if "json" in ctype else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"error": raw.decode("utf-8", "replace")}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {"error": f"cannot reach the station at {STATION}: {getattr(e, 'reason', e)}"}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/static/{name}")
def static(name: str) -> Response:
    path = (STATIC / name).resolve()
    if path.parent != STATIC.resolve() or not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, headers={"Cache-Control": "no-store"})


@app.get("/api/state")
def state() -> JSONResponse:
    code, s = _station("/api/state", timeout=2.0)
    if code != 200 or not isinstance(s, dict):
        err = s.get("error", str(s)) if isinstance(s, dict) else str(s)
        return JSONResponse({"station_ok": False, "station": STATION, "error": err})
    _last["state"] = s
    s["station_ok"] = True
    s["station"] = STATION
    s["hmi"] = {"operator": OPERATOR, "key_source": KEY_SOURCE, "channels": CHANNELS,
                "has_last_signed": _last["signed"] is not None}
    return JSONResponse(s)


@app.get("/api/audit")
def audit(only: str = "all", limit: int = 200) -> JSONResponse:
    code, s = _station(f"/api/audit?only={'rejected' if only == 'rejected' else 'all'}&limit={int(limit)}")
    return JSONResponse(s, status_code=200 if code == 200 else 502)


@app.get("/api/verify")
def verify() -> JSONResponse:
    code, s = _station("/api/verify")
    return JSONResponse(s, status_code=200 if code == 200 else 502)


@app.get("/api/export/{name}")
def export(name: str) -> Response:
    allowed = {"audit.csv", "audit.jsonl", "int_s1_timing.csv", "s1_hold.csv", "ph_trend.csv"}
    if name not in allowed:
        return JSONResponse({"error": "unknown export"}, status_code=404)
    code, body = _station(f"/api/export/{name}", timeout=10.0)
    if code != 200:
        return JSONResponse(body if isinstance(body, dict) else {"error": "export failed"}, status_code=502)
    data = body if isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    return Response(data, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _event_id_for_dose() -> str:
    eid = (_last["state"] or {}).get("dose_event_id", "OPS")
    if str(eid).startswith("E-"):
        return eid                            # doses during recovery count against the event
    return f"OPS-{uuid.uuid4().hex[:8]}"      # a normal-operation dose is its own event


def _last_seq() -> int:
    return int(((_last["state"] or {}).get("gateway") or {}).get("last_sequence_number", 0))


@app.post("/api/dose")
async def dose(request: Request) -> JSONResponse:
    req = await request.json()
    channel = str(req.get("channel_id", ""))
    try:
        volume = float(req.get("volume_ml"))
    except (TypeError, ValueError):
        return JSONResponse({"decision": "NOT_SENT", "words": "Type the dose in mL (a number)."}, status_code=400)
    if channel not in CHANNELS:
        return JSONResponse({"decision": "NOT_SENT", "words": "Pick a bottle."}, status_code=400)
    if _last["state"] is None:
        code, s = _station("/api/state")
        if code == 200:
            _last["state"] = s
    out: dict[str, Any] = {}
    for attempt in range(2):
        cmd = new_dose_command(CONFIG, channel_id=channel, volume_ml=volume, event_id=_event_id_for_dose(),
                               sequence_number=next_sequence(_last_seq()), source="HMI",
                               flow_ml_min=HAND_SPEED_ML_S * 60)
        _last["signed"] = dict(cmd)
        code, out = _station("/api/dose", dict(cmd, _sender=f"operator {OPERATOR} (laptop HMI)"))
        if code == 0:
            return JSONResponse({"decision": "NOT_SENT", "words": out.get("error", "station unreachable")},
                                status_code=502)
        if out.get("reason_code") == "OLD_SEQUENCE" and attempt == 0:
            # the Pi's recovery loop sent a command a moment ago: refresh and retry once
            c2, s = _station("/api/state")
            if c2 == 200:
                _last["state"] = s
            continue
        break
    return JSONResponse(out)


@app.post("/api/action")
async def action(request: Request) -> JSONResponse:
    req = await request.json()
    name = str(req.get("action", "")).upper()
    body = new_operator_action(SECRET, name, req.get("args") or {}, operator=OPERATOR)
    code, out = _station("/api/operator", body)
    if code == 0:
        return JSONResponse({"ok": False, "error": out.get("error")}, status_code=502)
    return JSONResponse(out)


# ------------------------------------------------------------------ security test panel
# These deliberately send bad commands so the gateway can be seen rejecting them live
# (S3 and C2 at the booth). They go to the same gateway as everything else.
@app.post("/api/test/{kind}")
async def security_test(kind: str) -> JSONResponse:
    if kind == "replay":
        if _last["signed"] is None:
            return JSONResponse({"decision": "NOT_SENT", "words": "Send one dose first, then replay it."})
        code, out = _station("/api/dose", dict(_last["signed"], _sender="security test: exact copy of the last command"))
    elif kind == "stale":
        cmd = new_dose_command(CONFIG, channel_id="BASE_FINE", volume_ml=1.0, event_id=_event_id_for_dose(),
                               sequence_number=next_sequence(_last_seq()), source="TEST", age_s=5.0)
        code, out = _station("/api/dose", dict(cmd, _sender="security test: signed command dated 5 s ago"))
    elif kind == "unsigned":
        cmd = new_dose_command(CONFIG, channel_id="BASE_BULK", volume_ml=10.0, event_id=_event_id_for_dose(),
                               sequence_number=next_sequence(_last_seq()), source="TEST")
        cmd.pop("hmac_sha256")
        code, out = _station("/api/dose", dict(cmd, _sender="security test: no signature"))
    elif kind == "forged":
        wrong = gateway_config("not-the-operator-key")
        cmd = new_dose_command(wrong, channel_id="BASE_BULK", volume_ml=10.0, event_id=_event_id_for_dose(),
                               sequence_number=next_sequence(_last_seq()), source="TEST")
        code, out = _station("/api/dose", dict(cmd, _sender="security test: signed with a wrong key"))
    else:
        return JSONResponse({"error": "unknown test"}, status_code=404)
    if code == 0:
        return JSONResponse({"decision": "NOT_SENT", "words": out.get("error")}, status_code=502)
    out["http_status"] = code
    return JSONResponse(out)
