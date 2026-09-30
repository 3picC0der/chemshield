"""The station's network API. This is the only port the Pi's firewall opens besides SSH.

    POST /api/dose       a signed I1 dose request. Unsigned or badly signed = 401.
    POST /api/operator   a signed operator action (HALT, RESUME, DOSE_ADDED, ...)
    GET  /api/state      everything the HMI draws (read-only, no secrets)
    GET  /api/audit      the hash-chained log, newest first (?only=rejected)
    GET  /api/export/... audit.csv, audit.jsonl, int_s1_timing.csv, s1_hold.csv, ph_trend.csv
    GET  /api/verify     re-checks the whole hash chain

Nothing here doses without a valid signature: the laptop HMI holds the operator key.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from hmi.common import check_operator_action

from .core import Station
from .links import SimLink


def build_app(station: Station) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        station.start()
        yield
        station.stop()

    app = FastAPI(title="ChemShield station (gateway + Model A + recovery)", docs_url=None, redoc_url=None,
                  lifespan=lifespan)

    @app.get("/api/state")
    def api_state() -> dict[str, Any]:
        return station.state()

    @app.get("/api/audit")
    def api_audit(only: str = "all", limit: int = 200) -> dict[str, Any]:
        with station.lock:
            return {"records": station.audit_view(only, min(max(limit, 1), 2000)),
                    "chain": station._chain_status()}

    @app.get("/api/verify")
    def api_verify() -> dict[str, Any]:
        with station.lock:
            ok = station.audit.verify()
            return {"ok": ok, "records": len(station.audit.records),
                    "text": "CHAIN OK" if ok else "CHAIN BROKEN"}

    @app.post("/api/dose")
    async def api_dose(request: Request):
        try:
            cmd = await request.json()
        except Exception:                                   # noqa: BLE001
            cmd = None
        if not isinstance(cmd, dict):
            with station.lock:
                station.audit.append("MALFORMED", "REJECT", "SCHEMA_TYPE_ERROR", False, source="gateway",
                                     message=f"request from {request.client.host if request.client else '?'} "
                                             f"was not a JSON object")
            return JSONResponse({"decision": "REJECT", "reason_code": "SCHEMA_TYPE_ERROR"}, status_code=400)
        sender = cmd.pop("_sender", None) or f"{request.client.host if request.client else '?'}"
        with station.lock:
            out = station._submit(cmd, source="HMI", sender=str(sender)[:60])
        status = 401 if out["reason_code"] in ("INVALID_HMAC", "MISSING_SIGNATURE") else 200
        return JSONResponse(out, status_code=status)

    @app.post("/api/operator")
    async def api_operator(request: Request):
        try:
            body = await request.json()
        except Exception:                                   # noqa: BLE001
            body = None
        with station.lock:
            refused = check_operator_action(body, station.secret, station.operator_nonces)
            if refused:
                station.audit.append("OPERATOR_ACTION", "REJECT", refused, False, source="HMI",
                                     message=f"operator action refused: "
                                             f"{(body or {}).get('action', '?') if isinstance(body, dict) else '?'}")
                return JSONResponse({"ok": False, "error": refused}, status_code=401)
            return JSONResponse(_do_action(station, body["action"], body.get("args") or {}))

    def _export(text: str, name: str, media: str = "text/csv") -> PlainTextResponse:
        return PlainTextResponse(text, media_type=media,
                                 headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.get("/api/export/audit.csv")
    def export_audit_csv():
        with station.lock:
            return _export(station.audit.to_csv(), "audit.csv")

    @app.get("/api/export/audit.jsonl")
    def export_audit_jsonl():
        with station.lock:
            return _export(station.audit.to_jsonl(), "audit.jsonl", "application/x-ndjson")

    @app.get("/api/export/int_s1_timing.csv")
    def export_timing():
        with station.lock:
            return _export(station.timing_csv(), "INT-AT-01_timing.csv")

    @app.get("/api/export/s1_hold.csv")
    def export_hold():
        with station.lock:
            return _export(station.hold_csv(), "CHE-AT-04_pH_hold.csv")

    @app.get("/api/export/ph_trend.csv")
    def export_trend():
        with station.lock:
            return _export(station.trend_csv(), "ph_trend.csv")

    return app


def _do_action(station: Station, action: str, args: dict[str, Any]) -> dict[str, Any]:
    """One signed operator action, already verified. Runs under station.lock."""
    a = str(action).upper()
    if a == "HALT":
        return station.halt()
    if a == "RESUME":
        return station.resume()
    if a == "ACK":
        return station.acknowledge()
    if a == "DOSE_ADDED":
        return station.dose_added(str(args.get("command_id", "")))
    if a == "DOSE_CANCEL":
        return station.cancel_dose(str(args.get("command_id", "")))
    if a == "HMI_SHOWN":
        return station.hmi_shown(str(args.get("event_id", "")))
    if a == "AUTO_RECOVERY":
        return station.set_auto_recovery(bool(args.get("on", True)))
    if a == "HOLD_START":
        return station.hold_start()
    if a == "HOLD_STOP":
        return station.hold_stop()

    # ---- simulator controls: only exist when the pH source is the simulator
    link = station.link
    if not isinstance(link, SimLink):
        return {"ok": False, "error": "simulator controls are off: the pH comes from the probe"}
    if a == "SIM_UPSET":
        if args.get("scenario"):
            from sim import scenarios as SC
            sc = SC.named(str(args["scenario"]))
            out = link.upset(sc["vol"], sc["acid"])
            what = f"scenario {args['scenario']}: {sc['vol']:g} mL of 0.5 M {'HCl' if sc['acid'] else 'NaOH'}"
        else:
            ml = float(args.get("ml", 7.0))
            acid = bool(args.get("acid", True))
            out = link.upset(ml, acid)
            what = f"{ml:g} mL of 0.5 M {'HCl' if acid else 'NaOH'}"
        station.audit.event("SIM_UPSET", f"SIMULATOR: {what} added to the simulated tank without the "
                            f"gateway (the unsafe dose)", source="simulator")
        return {"ok": True, **out}
    if a == "SIM_SET_PH":
        out = link.set_ph(float(args.get("ph", 7.0)))
        station.audit.event("SIM_SET_PH", f"SIMULATOR: simulated tank set to pH {out['ph']}", source="simulator")
        return {"ok": True, **out}
    if a == "SIM_RESET":
        start = args.get("start_ph", link.start_ph)
        out = link.reset(float(start) if start is not None else None)
        station.audit.event("SIM_RESET", f"SIMULATOR: fresh 5 L tank, pH {out['ph']}", source="simulator")
        station.fresh_start("simulator reset")
        return {"ok": True, **out}
    if a == "SIM_AUTOPUMP":
        link.auto_pump = bool(args.get("on", True))
        station.audit.event("SIM_AUTOPUMP", f"SIMULATOR: doses added automatically "
                            f"{'on' if link.auto_pump else 'off'}", source="simulator")
        return {"ok": True, "auto_pump": link.auto_pump}
    if a == "SIM_ESCALATE":
        # Usability drill (ISE-AT-03 task T4): a real escalation takes minutes to build up.
        if station.event is None:
            return {"ok": False, "error": "start an upset first; an escalation needs an open event"}
        station.audit.event("SIM_ESCALATE", "SIMULATOR: escalation forced for a usability drill",
                            source="simulator", event_id=station.event["id"])
        station._escalate("INFEASIBLE", "(usability drill)")
        return {"ok": True, "mode": station.mode}
    if a == "SIM_UNPLUG":
        out = link.unplug(float(args.get("seconds", 8.0)))
        station.audit.event("SIM_UNPLUG", f"SIMULATOR: Uno USB 'unplugged' for {out['unplugged_for_s']:g} s",
                            source="simulator")
        return {"ok": True, **out}
    return {"ok": False, "error": f"unknown action {action}"}
