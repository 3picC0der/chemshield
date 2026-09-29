"""I4: the redosing call.  state (I2 message) -> DOSE or ESCALATE.

This is the only entry point the gateway and the HMI need. It wraps the robust
mixed-integer program in sim/rdo.py, which is re-solved at every accepted reading.

    from redosing.planner import plan_next_dose
    plan_next_dose(state)   # state = one I2 dict
    -> {"action": "DOSE", "channel_id": "BASE_BULK", "dose_ml": 11.8}
    -> {"action": "ESCALATE", "reason": "INFEASIBLE"}

The reply carries extra keys beyond the I4 contract (block, mmol, z, solve_ms,
binding). Anything outside the contract is advisory and may be ignored; the gateway
must key only on "action", "channel_id" and "dose_ml".

Units: dose_ml in mL. The tank state arrives as I2's excess_mmol, which is
BASE-POSITIVE; the optimiser works in acid-positive mol. sim.chemistry does the
conversion, never do it by hand.
"""
from __future__ import annotations

import time

from sim import rdo
from sim.engine import ensure_table_chemistry
from sim.model import C, P

# I4 channel names <-> the optimiser's pump index (sim/model.py PUMPS order)
PUMP_TO_CHANNEL = {0: "BASE_BULK", 1: "BASE_FINE", 2: "ACID_BULK", 3: "ACID_FINE"}
CHANNEL_TO_PUMP = {v: k for k, v in PUMP_TO_CHANNEL.items()}
CHANNEL_MOLARITY = {"BASE_BULK": 0.5, "BASE_FINE": 0.005,
                    "ACID_BULK": 0.5, "ACID_FINE": 0.005}

ESCALATE_REASONS = ("INFEASIBLE", "BUDGET", "TIME", "STALE", "SOLVER_FAIL")
MAX_SAMPLE_AGE_S = 30.0


def mmol_of(channel_id: str, dose_ml: float) -> float:
    """Reagent in one dose. 20 mL of 0.5 M = 10 mmol."""
    return CHANNEL_MOLARITY[channel_id] * float(dose_ml)


def _escalate(reason: str, **extra) -> dict:
    out = {"action": "ESCALATE", "reason": reason}
    out.update(extra)
    return out


def plan_block(state: dict, par: dict = P) -> dict:
    """Full planner output: the whole dose block the MILP chose, or an escalation.

    state: an I2 process-state message. Required keys: ph, excess_mmol (unused by the
    planner, which trusts only the measurement), plus the optional keys below.

    Optional keys, all defaulted so a bare I2 message works:
      temp_c            25.0
      volume_L          the nominal fill; the planner's own belief about the fill
      event_mmol_used   corrective reagent already spent this event (C3 budget)
      event_ml_used     corrective volume already spent this event (gateway cap)
      event_elapsed_s   seconds since EVENT_CONFIRMED (abort budget)
      sample_age_s      age of the pH reading; over MAX_SAMPLE_AGE_S escalates
      channels_available {channel_id: bool}
      inventory_ml      {channel_id: mL left in the bottle}
    """
    if "ph" not in state:
        return _escalate("STALE", detail="no pH in state message")
    age = float(state.get("sample_age_s", 0.0) or 0.0)
    if age > MAX_SAMPLE_AGE_S:
        return _escalate("STALE", detail=f"sample_age_s={age:.1f}")

    # plan on the tank's pH table, not the pure-water formula, even when the gateway
    # calls this directly without sim.batch or sim.live having set the chemistry up
    ensure_table_chemistry()
    ph_m = float(state["ph"])
    v_hat = float(state.get("volume_L", par["V0"]))
    temp_c = float(state.get("temp_c", par["T_C"]))

    avail_by_ch = state.get("channels_available") or {}
    inv_by_ch = state.get("inventory_ml") or {}
    avail = [1.0 if avail_by_ch.get(PUMP_TO_CHANNEL[p], True) else 0.0 for p in range(4)]
    inventory = [float(inv_by_ch.get(PUMP_TO_CHANNEL[p], 1e9)) for p in range(4)]

    ctx = dict(
        avail=avail,
        inventory=inventory,
        reserve=[float(state.get("reserve_ml", 0.0))] * 4,
        R_used=float(state.get("event_mmol_used", 0.0)),
        V_used=float(state.get("event_ml_used", 0.0)),
        t_el=float(state.get("event_elapsed_s", 0.0)),
    )

    t0 = time.perf_counter()
    s = rdo.solve(ph_m, v_hat, ctx, par, temp_c)
    solve_ms = (time.perf_counter() - t0) * 1000.0

    status = str(s.get("status", ""))
    if status == "SOLVER_FAIL":
        return _escalate("SOLVER_FAIL", solve_ms=round(solve_ms, 2))

    doses = s.get("doses") or []
    if not doses:
        if status.startswith("ESCALATE"):
            budget_left = par["R_max"] - ctx["R_used"]
            reason = "BUDGET" if budget_left <= 1e-9 else "INFEASIBLE"
            return _escalate(reason, solve_ms=round(solve_ms, 2),
                             budget_left_mmol=round(budget_left, 3))
        # HOLD / RE-READ: nothing to do now, not an escalation
        return {"action": "HOLD", "reason": status, "solve_ms": round(solve_ms, 2)}

    block = []
    for pump, ml in doses:
        ch = PUMP_TO_CHANNEL[int(pump)]
        block.append({"channel_id": ch, "dose_ml": round(float(ml), 3),
                      "mmol": round(mmol_of(ch, ml), 4)})

    planned = sum(d["mmol"] for d in block)
    if ctx["R_used"] + planned > par["R_max"] + 1e-6:      # belt and braces; the MILP
        return _escalate("BUDGET", budget_left_mmol=round(par["R_max"] - ctx["R_used"], 3))

    out = {"action": "DOSE",
           "channel_id": block[0]["channel_id"],
           "dose_ml": block[0]["dose_ml"],
           "block": block,
           "block_mmol": round(planned, 4),
           "solve_ms": round(solve_ms, 2),
           "status": status}
    z = s.get("z")
    if z is not None and z == z:
        out["z_umol"] = round(float(z), 2)
    return out


def plan_next_dose(state: dict, par: dict = P) -> dict:
    """The I4 contract exactly: one dose, or an escalation.

    Callers that release the whole block (the simulator and the live loop) should use
    plan_block() instead; this returns the same first dose either way.
    """
    r = plan_block(state, par)
    if r["action"] != "DOSE":
        return {k: v for k, v in r.items() if k in ("action", "reason")} or r
    return {"action": "DOSE", "channel_id": r["channel_id"], "dose_ml": r["dose_ml"]}


if __name__ == "__main__":
    import json
    from sim.chemistry import ph_from_excess
    from sim.engine import use_table_chemistry

    print("chemistry:", use_table_chemistry())
    demo = [
        ("acid tank, fresh event",
         {"t": 0.0, "ph": round(ph_from_excess(-30.0), 3), "temp_c": 25.0, "level_ok": True,
          "excess_mmol": -30.0, "state": "RECOVERY", "event_mmol_used": 0.0, "source": "SIM"}),
        ("nearly in band",
         {"t": 0.0, "ph": round(ph_from_excess(-2.9), 3), "temp_c": 25.0, "level_ok": True,
          "excess_mmol": -2.9, "state": "RECOVERY", "event_mmol_used": 24.0, "source": "SIM"}),
        ("budget nearly spent, big upset left",
         {"t": 0.0, "ph": round(ph_from_excess(-40.0), 3), "temp_c": 25.0, "level_ok": True,
          "excess_mmol": -40.0, "state": "RECOVERY", "event_mmol_used": 49.5, "source": "SIM"}),
        ("stale reading",
         {"t": 0.0, "ph": 3.0, "sample_age_s": 45.0, "excess_mmol": -20.0,
          "state": "RECOVERY", "event_mmol_used": 0.0, "source": "SIM"}),
    ]
    for label, st in demo:
        print(f"\n{label}\n  I2  {json.dumps(st)}")
        print(f"  I4  {json.dumps(plan_next_dose(st))}")
        full = plan_block(st)
        if full["action"] == "DOSE":
            print(f"  block {json.dumps(full['block'])}  total {full['block_mmol']} mmol "
                  f"in {full['solve_ms']} ms")
