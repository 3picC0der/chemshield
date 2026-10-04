"""The station: what runs on the Pi between the laptop HMI and the Uno.

It owns Khalid's gateway (with Belal's Model A plugged in), Hattan's planner, the
unsafe-event detector and recovery switch, the hand-dosing workflow and the audit log.
The laptop only sends signed requests and reads state; every decision is made here.

States (the HMI banner):
    NORMAL     pH inside 6.0-8.5, operator doses allowed through the gateway
    RECOVERY   3 readings in a row outside 6.0-8.5 = unsafe event confirmed; the Uno is
               told to lock and the MILP issues recovery doses through the gateway
    ESCALATE   the planner or the gateway can't continue: OPERATOR DECISION REQUIRED
    HALTED     the operator pressed HALT, the E-stop was pressed or the Uno link was lost;
               every dose is refused until the operator presses RESUME
"""
from __future__ import annotations

import csv
import io
import itertools
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from hmi.common import (
    CHANNELS,
    GROUP_WORDS,
    gateway_config,
    iso_ms,
    new_dose_command,
    next_sequence,
    reason_group,
    reason_words,
)
from chemshield_gateway.auth import is_valid_hmac
from chemshield_gateway.gateway_validator import GatewayValidator
from chemshield_gateway.models import ProcessState

from .audit import StationAuditLog
from .links import Link

BAND = (6.0, 8.5)            # INT-S1 / INT-S2 band: outside it is an unsafe event
FAR = (5.5, 9.5)             # INT-S3 far-side limits
S1_BAND = (6.5, 7.5)         # S1: nominal hold band
TRIM_BAND = (6.7, 7.3)       # during the S1 hold log, suggest a trim dose outside this
CONFIRM_READINGS = 3         # readings in a row outside BAND that confirm an event
MIX_S = 15.0                 # S2 mixing hold after each dose
PENDING_TIMEOUT_S = 120.0    # a dose nobody confirms is cancelled after this
HOLD_LOG_S = 600.0           # S1: 10 minutes
TREND_S = 1800               # pH history kept for the trend and the CSV
TICK_S = 0.1
SETTLE_RANGE = 0.15          # pH: the planner waits until the last 5 readings agree this well
SETTLE_MAX_WAIT_S = 30.0     # ... or this long after the event was confirmed
MODEL_A_RETRIES = 1          # Model A blocks of the planner's dose before the operator is called
REPLAN_AFTER_BLOCK_S = 10.0

ESCALATE_WORDS = {
    "INFEASIBLE": "No safe dose is available. Automatic recovery has stopped.",
    "BUDGET": "The 50 mmol reagent limit for this event is used up.",
    "TIME": "This event has run past its time budget.",
    "STALE": "The pH reading is too old to dose on.",
    "SOLVER_FAIL": "The optimiser did not return. Automatic recovery has stopped.",
    "GATEWAY_REJECT": "The gateway refused the planner's dose.",
}

WHY_PLAN = ("The optimiser picks the least reagent that still keeps the worst case inside "
            "6.0-8.5, within the 20 mL dose cap and 15 s mixing hold (S2), the 50 mmol "
            "event ceiling (C3) and the 300 s budget (S6). It plans against probe, dosing "
            "and volume error, so a 0.1 pH reading error cannot push the tank past 5.5/9.5. "
            "Small remainders use the 0.005 M bottles because the 0.5 M ones can't meter "
            "them. Every dose still goes through the gateway and Model A.")


def _wall() -> str:
    return iso_ms()


class Station:
    def __init__(self, link: Link, secret: str, *, log_dir: Path, dwell_s: float = 60.0,
                 hand_speed_ml_s: float = 2.0, use_model_a: bool = True,
                 clock: Callable[[], float] = time.monotonic, key_source: str = "") -> None:
        self.link = link
        self.secret = secret
        self.key_source = key_source
        self.clock = clock
        self.dwell_s = float(dwell_s)
        self.hand_speed_ml_s = float(hand_speed_ml_s)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.started_wall = _wall()
        self.started_t = clock()

        self.config = gateway_config(secret)
        self.gstate = ProcessState(ph=7.0, mode="NORMAL")
        self.audit = StationAuditLog(self.log_dir / "audit.jsonl")

        # Model A (Belal): reads the same probe history the station feeds it
        self.model_a = None
        self.model_a_error = ""
        from model_a.inference import ModelAClient, ProcessContext
        self.context = ProcessContext(clock=clock)
        if use_model_a:
            self.model_a = ModelAClient(context=self.context,
                                        decision_log=self.log_dir / "model_a_decisions.csv")
            self.model_a_error = self.model_a.load_error
        self.model_a_proxy = _RememberingModelA(self.model_a or _NoModelA())
        self.gateway = GatewayValidator(config=self.config, model_a=self.model_a_proxy,
                                        audit_log=self.audit, state=self.gstate, clock=clock)

        # Hattan's planner (warm it up: the first solve loads HiGHS and the pH table)
        from redosing.planner import plan_block
        self._plan_block = plan_block
        from sim import chemistry
        from sim.engine import use_table_chemistry
        self.chem = chemistry
        self.chem_source = use_table_chemistry()
        try:
            plan_block({"ph": 4.0, "event_mmol_used": 0.0})
        except Exception:                                   # noqa: BLE001
            pass

        self.lock = threading.RLock()
        self.mode = "NORMAL"
        self.mode_reason = ""
        self.mode_since = _wall()
        self.halted_from: str | None = None
        self.alarm_acked = True
        self.auto_recovery = True
        self._event_counter = itertools.count(1)
        self.event: dict[str, Any] | None = None
        self.events: list[dict[str, Any]] = []            # closed and open, newest last
        self.pending: dict[str, Any] | None = None          # the dose waiting for the operator
        self.mixing_until: float | None = None
        self.block: list[dict[str, Any]] = []
        self.plan: dict[str, Any] | None = None
        self.next_plan_at: float | None = None
        self.next_block_at: float | None = None
        self.escalation: dict[str, Any] | None = None

        self.trend: deque[tuple[float, str, float, float]] = deque(maxlen=TREND_S)  # t, wall, ph, mean3
        self.recent: deque[tuple[float, float]] = deque(maxlen=CONFIRM_READINGS)
        self.out_since: tuple[float, str] | None = None
        self.in_band_since: tuple[float, str] | None = None
        self.link_was_alive = False
        self.hold: dict[str, Any] | None = None
        self.decisions: deque[dict[str, Any]] = deque(maxlen=12)
        self.last_hmi_decision: dict[str, Any] | None = None
        self.counters: dict[str, int] = {}
        self.operator_nonces: set[str] = set()
        self.seen_nonces: set[str] = set()
        self.seen_command_ids: set[str] = set()
        self._chain_ok = (True, "0 records")
        self._chain_checked_n = -1

        self.audit.event("STATION_START", f"station started; pH source {link.kind}; "
                         f"chemistry {self.chem_source}; Model A "
                         f"{'loaded' if self.model_a and not self.model_a_error else 'NOT loaded ' + self.model_a_error}")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ================================================================ lifecycle
    def start(self) -> None:
        self.link.start()
        self._thread = threading.Thread(target=self._run, daemon=True, name="station-tick")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.link.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as exc:                           # noqa: BLE001 - never die
                with self.lock:
                    self.audit.event("STATION_ERROR", f"{type(exc).__name__}: {exc}")
            time.sleep(TICK_S)

    # ================================================================ the loop
    def tick(self) -> None:
        with self.lock:
            now = self.clock()
            readings, uno_events = self.link.poll()
            for ev in uno_events:
                self._on_uno_event(ev)
            for t, ph in readings:
                self._on_reading(t, ph)
                self.context.add_sample(ph, t)
            alive = self.link.alive(now)
            if alive:
                self.context.mark_uno_alive(self.link.last_line_t)
            if self.link_was_alive and not alive:
                self._link_lost()
            elif alive and not self.link_was_alive:
                self.audit.event("UNO_LINK_UP", f"{self.link.kind} link is talking", source="Uno")
            self.link_was_alive = alive
            self.gstate.heartbeat_healthy = alive
            self.gateway.lockout_remaining_s()
            if readings:
                self._detect()
            if self.mode in ("RECOVERY",) and self.auto_recovery:
                self._recovery_step(now)
            self._pending_step(now)

    def _on_reading(self, t: float, ph: float) -> None:
        self.recent.append((t, ph))
        mean3 = sum(p for _, p in self.recent) / len(self.recent)
        self.trend.append((t, _wall(), ph, mean3))
        self.gstate.ph = round(mean3, 3)
        if self.hold and self.hold["active"]:
            self._hold_add(t, ph, mean3)

    def _mean3(self) -> float | None:
        if not self.recent:
            return None
        return sum(p for _, p in self.recent) / len(self.recent)

    # ---------------------------------------------------------------- detection
    def _detect(self) -> None:
        t_last, ph_last = self.recent[-1]
        outside = not (BAND[0] <= ph_last <= BAND[1])
        if outside and self.out_since is None:
            self.out_since = (t_last, _wall())
        if not outside:
            self.out_since = None

        if self.mode == "NORMAL":
            if len(self.recent) == CONFIRM_READINGS and all(not (BAND[0] <= p <= BAND[1]) for _, p in self.recent):
                lows = all(p < BAND[0] for _, p in self.recent)
                highs = all(p > BAND[1] for _, p in self.recent)
                if lows or highs:
                    self._confirm_event("acid" if lows else "base")
            return

        if self.event is None:
            return
        mean3 = self._mean3()
        inside = mean3 is not None and BAND[0] <= mean3 <= BAND[1] and len(self.recent) == CONFIRM_READINGS
        if inside:
            if self.in_band_since is None:
                self.in_band_since = (self.clock(), _wall())
                self.event["t_in_band"] = self.in_band_since[0]
                self.event["in_band_first_utc"] = self.in_band_since[1]
            elif self.clock() - self.in_band_since[0] >= self.dwell_s and self.pending is None \
                    and self.mode in ("RECOVERY", "ESCALATE"):
                self._close_event()
                return
        else:
            self.in_band_since = None
            self.event["t_in_band"] = None
        self.event["min_ph"] = min(self.event["min_ph"], mean3) if mean3 is not None else self.event["min_ph"]
        self.event["max_ph"] = max(self.event["max_ph"], mean3) if mean3 is not None else self.event["max_ph"]

    def _confirm_event(self, direction: str) -> None:
        t_confirm = self.clock()
        wall_confirm = _wall()
        eid = f"E-{next(self._event_counter):04d}"
        mean3 = self._mean3()
        ev = {
            "id": eid, "direction": direction, "status": "open",
            "cls": "Unsafe acid event (pH below 6.0)" if direction == "acid" else "Unsafe base event (pH above 8.5)",
            "first_out_utc": self.out_since[1] if self.out_since else wall_confirm,
            "confirmed_utc": wall_confirm, "t_confirm": t_confirm,
            "confirm_ph": round(mean3, 3) if mean3 is not None else None,
            "readings": [round(p, 3) for _, p in self.recent],
            "recovery_utc": None, "t_recovery": None,
            "uno_locked_utc": None, "t_uno_locked": None,
            "hmi_shown_utc": None, "t_hmi_shown": None,
            "closed_utc": None, "recovery_time_s": None, "in_band_first_utc": None,
            "doses": [], "escalations": [], "source": self.link.kind, "t_in_band": None,
            "min_ph": mean3, "max_ph": mean3,
        }
        self.audit.event("EVENT_CONFIRMED", f"{ev['cls']}: {CONFIRM_READINGS} readings in a row "
                         f"outside 6.0-8.5 ({', '.join(str(x) for x in ev['readings'])})", event_id=eid)
        # the switch itself: gateway state, the Uno lock, the planner
        if self.pending is not None:
            self._cancel_pending("an unsafe event was confirmed", notify=False)
        self.event = ev
        self.events.append(ev)
        self._set_mode("RECOVERY", ev["cls"])
        self.gstate.mode = "RECOVERY"
        self.link.send_mode("RECOVERY")
        ev["t_recovery"] = self.clock()
        ev["recovery_utc"] = _wall()
        self.alarm_acked = False
        self.block, self.plan, self.escalation = [], None, None
        self.next_plan_at = self.clock() + 1.0
        self.in_band_since = None
        ms = (ev["t_recovery"] - t_confirm) * 1000.0
        self.audit.event("RECOVERY_ENTERED", f"safe-recovery mode entered {ms:.1f} ms after the event "
                         f"was confirmed; Uno told to lock", event_id=eid)

    def _close_event(self) -> None:
        ev = self.event
        ev["status"] = "closed"
        ev["closed_utc"] = _wall()
        ev["recovery_time_s"] = round(self.in_band_since[0] - ev["t_confirm"], 1)
        used = self.gateway.event_mmol_used.get(ev["id"], 0.0)
        self.audit.event("EVENT_CLOSED", f"pH back inside 6.0-8.5 at {ev['recovery_time_s']} s and held "
                         f"{self.dwell_s:.0f} s; reagent used {used:.2f} of 50 mmol", event_id=ev["id"])
        self.event = None
        self.block, self.plan, self.escalation = [], None, None
        self.next_plan_at = None
        self.in_band_since = None
        self._set_mode("NORMAL", "event closed")
        self.gstate.mode = "NORMAL"
        self.link.send_mode("NORMAL")
        self.alarm_acked = True

    def _set_mode(self, mode: str, reason: str) -> None:
        self.mode = mode
        self.mode_reason = reason
        self.mode_since = _wall()

    # ---------------------------------------------------------------- recovery
    def _recovery_step(self, now: float) -> None:
        if self.pending is not None or not self.link.alive(now):
            return
        if self.mixing_until is not None and now < self.mixing_until:
            return
        queued = [b for b in self.block if b["status"] == "queued"]
        if queued:
            if self.next_block_at is None or now >= self.next_block_at:
                waited = now - (self.next_block_at if self.next_block_at is not None else now)
                if not self._settled() and waited < SETTLE_MAX_WAIT_S:
                    return                    # wait for the last dose to finish mixing in
                self._issue_planned(queued[0])
            return
        if self.next_plan_at is not None and now >= self.next_plan_at:
            self._replan(now)

    def _planner_state(self, now: float) -> dict[str, Any]:
        ev = self.event
        mean3 = self._mean3()
        age = (now - self.recent[-1][0]) if self.recent else 999.0
        ml_used = sum(d["ml"] for d in ev["doses"] if d.get("added_utc"))
        return {"ph": round(mean3, 4) if mean3 is not None else None, "temp_c": 25.0,
                "volume_L": 5.0 + ml_used / 1000.0,
                "event_mmol_used": self.gateway.event_mmol_used.get(ev["id"], 0.0),
                "event_ml_used": ml_used, "event_elapsed_s": now - ev["t_confirm"],
                "sample_age_s": age, "state": "RECOVERY", "source": self.link.kind}

    def _settled(self) -> bool:
        """The planner must not plan on a reading that is still moving (probe lag and
        mixing after an upset): the last 5 readings within SETTLE_RANGE pH."""
        last = [p for _, _, p, _ in list(self.trend)[-5:]]
        return len(last) == 5 and max(last) - min(last) <= SETTLE_RANGE

    def _replan(self, now: float) -> None:
        st = self._planner_state(now)
        if st["ph"] is None:
            self.next_plan_at = now + 1.0
            return
        if not self._settled() and now - self.event["t_confirm"] < SETTLE_MAX_WAIT_S \
                and not self.event["doses"]:
            self.plan = {"action": "WAIT", "status": "waiting for the pH reading to settle",
                         "planned_utc": _wall(), "ph_used": st["ph"]}
            self.next_plan_at = now + 1.0
            return
        try:
            res = self._plan_block(st)
        except Exception as exc:                               # noqa: BLE001
            res = {"action": "ESCALATE", "reason": "SOLVER_FAIL", "detail": str(exc)}
        res["planned_utc"] = _wall()
        res["ph_used"] = st["ph"]
        self.plan = res
        if res["action"] == "DOSE":
            signed = sum(CHANNELS[b["channel_id"]]["molarity"] * b["dose_ml"] *
                         (1 if b["channel_id"].startswith("BASE") else -1) for b in res["block"])
            try:
                ex_now = self.chem.excess_from_ph(st["ph"], 25.0, st["volume_L"])
                res["predicted_end_ph"] = round(self.chem.ph_from_excess(ex_now + signed, 25.0, st["volume_L"]), 2)
            except Exception:                                  # noqa: BLE001
                res["predicted_end_ph"] = None
            self.block = [{"n": i + 1, "channel_id": b["channel_id"], "words": CHANNELS[b["channel_id"]]["words"],
                           "dose_ml": b["dose_ml"], "mmol": b["mmol"], "hold_s": MIX_S, "status": "queued",
                           "command_id": None} for i, b in enumerate(res["block"])]
            self.audit.event("PLAN", f"optimiser planned {len(self.block)} dose(s), "
                             f"{res['block_mmol']:.3f} mmol, solved in {res['solve_ms']} ms, from pH {st['ph']:.2f}",
                             event_id=self.event["id"], source="optimiser")
            self.next_block_at = now
        elif res["action"] == "HOLD":
            self.next_plan_at = now + 5.0
        else:
            self._escalate(res.get("reason", "INFEASIBLE"), res.get("detail", ""))

    def _issue_planned(self, item: dict[str, Any]) -> None:
        ev = self.event
        cmd = new_dose_command(self.config, channel_id=item["channel_id"], volume_ml=item["dose_ml"],
                               event_id=ev["id"], sequence_number=next_sequence(self.gateway.last_sequence_number),
                               source="MILP", action="RECOVERY_DOSE", flow_ml_min=self.hand_speed_ml_s * 60,
                               plan_hash=f"plan:{ev['id']}:{self.plan.get('planned_utc', '')}")
        item["command_id"] = cmd["command_id"]
        item["status"] = "requested"
        out = self._submit(cmd, source="optimiser", sender="recovery planner (MILP)")
        if out["decision"] == "ACCEPT":
            item["status"] = "dose now"
            ev["model_a_retries"] = 0
            return
        code = out["reason_code"]
        if code == "MIXING_LOCKOUT":
            item["status"] = "queued"
            self.next_block_at = self.clock() + self.gateway.lockout_remaining_s() + 0.3
            return
        item["status"] = f"rejected: {code}"
        if code in ("MODEL_A_BLOCK", "MODEL_A_TIMEOUT") and ev.get("model_a_retries", 0) < MODEL_A_RETRIES:
            # Model A judged the tank as it is right now. Drop the rest of this block, take a
            # fresh settled reading and let the optimiser plan again; that new dose goes
            # through Model A again. A second block in a row escalates to the operator.
            ev["model_a_retries"] = ev.get("model_a_retries", 0) + 1
            self.block = [b for b in self.block if b["status"] != "queued"]
            self.next_plan_at = self.clock() + REPLAN_AFTER_BLOCK_S
            self.audit.event("REPLAN", f"Model A blocked the planner's dose; re-reading the tank and "
                             f"planning again in {REPLAN_AFTER_BLOCK_S:.0f} s", event_id=ev["id"],
                             source="optimiser")
            return
        self._escalate("GATEWAY_REJECT", f"{code}: {reason_words(code)}")

    def _escalate(self, reason: str, detail: str = "") -> None:
        ev = self.event
        words = ESCALATE_WORDS.get(reason, reason)
        self.escalation = {"reason": reason, "words": words, "detail": detail, "utc": _wall()}
        if ev is not None:
            ev["escalations"].append(self.escalation)
        self.block = [b for b in self.block if b["status"] != "queued"]
        self._set_mode("ESCALATE", words)
        self.alarm_acked = False
        self.audit.event("ESCALATE", f"operator decision required: {words} {detail}".strip(),
                         event_id=ev["id"] if ev else "", source="optimiser")

    # ---------------------------------------------------------------- doses
    def _submit(self, cmd: dict[str, Any], *, source: str, sender: str) -> dict[str, Any]:
        """Send one signed command through the gateway. Station checks come after the
        gateway's own replay and freshness checks so S3's counts are the gateway's."""
        received_utc = _wall()
        t0 = time.perf_counter()
        ch = str(cmd.get("channel_id", ""))
        vol = cmd.get("volume_ml", "")
        words = CHANNELS.get(ch, {}).get("words", ch)
        msg = f"{cmd.get('action', '?')} {vol} mL {words} from {sender}"
        self.audit.context = {"source": source if source != "HMI" else "gateway",
                              "event_id": str(cmd.get("event_id", "")), "message": msg}
        try:
            pre = self._station_precheck(cmd)
            if pre is not None:
                rec = self.audit.append(str(cmd.get("command_id", "")), "REJECT", pre, False,
                                        channel_id=ch, volume_ml=float(vol or 0.0))
                result = {"command_id": rec.command_id, "decision": "REJECT", "reason_code": pre,
                          "reason_detail": reason_words(pre), "forwarded_to_actuator": False,
                          "latency_ms": round((time.perf_counter() - t0) * 1000, 4),
                          "model_a_label": "NOT_CALLED", "model_a_score": 0.0, "model_a_latency_ms": 0.0,
                          "channel_id": ch, "volume_ml": float(vol or 0.0), "dose_mmol": 0.0,
                          "event_mmol_total": self.gateway.event_mmol_used.get(str(cmd.get("event_id", "")), 0.0)}
            else:
                result = self.gateway.validate(cmd, category=source).to_dict()
        finally:
            self.audit.context = {}
        decided_utc = _wall()
        result.update({
            "received_utc": received_utc, "decided_utc": decided_utc,
            "station_ms": round((time.perf_counter() - t0) * 1000, 3),
            "group": reason_group(result["reason_code"]),
            "words": reason_words(result["reason_code"]),
            "channel_words": words, "sender": sender, "event_id": cmd.get("event_id", ""),
            "mode": self.mode,
        })
        if result["model_a_label"] != "NOT_CALLED":
            i3 = self.model_a_proxy.last.get(str(cmd.get("command_id", "")), {})
            result["model_a_reason"] = i3.get("reason", "")
            result["model_a_version"] = i3.get("model_version", "")
        group = result["group"]
        self.counters[group] = self.counters.get(group, 0) + 1
        self.counters["TOTAL"] = self.counters.get("TOTAL", 0) + 1
        self.decisions.append(result)
        if result["decision"] == "ACCEPT":
            self._start_pending(cmd, result, sender)
        return result

    def _station_precheck(self, cmd: dict[str, Any]) -> str | None:
        """Station rules, checked only for commands that are signed and fresh, so unsigned
        and stale ones still get the gateway's own codes (INVALID_HMAC, STALE_TIMESTAMP)."""
        if "hmac_sha256" not in cmd:
            return "MISSING_SIGNATURE"          # ICS-AT-01 step 4: an AUTH rejection, HTTP 401
        if not is_valid_hmac(cmd, self.config.hmac_secret):
            return None
        try:
            ts = datetime.fromisoformat(str(cmd.get("timestamp_utc", "")).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if abs((datetime.now(timezone.utc) - ts).total_seconds()) > self.config.freshness_window_s:
                return None
        except (ValueError, TypeError):
            return None
        # A signed, fresh command is single-use whatever its decision. (The gateway only
        # remembers nonces of commands it accepted, so a copy of a rejected command would
        # otherwise be judged again instead of being called a replay.)
        nonce, cid = str(cmd.get("nonce", "")), str(cmd.get("command_id", ""))
        if nonce in self.seen_nonces or nonce in self.gateway.used_nonces:
            return "REUSED_NONCE"
        if cid in self.seen_command_ids or cid in self.gateway.processed_command_ids:
            return "DUPLICATE_COMMAND_ID"
        self.seen_nonces.add(nonce)
        self.seen_command_ids.add(cid)
        if cmd.get("action") not in ("DOSE", "RECOVERY_DOSE"):
            return None
        if self.pending is not None:
            return "DOSE_PENDING"
        eid = str(cmd.get("event_id", ""))
        if self.event is not None and self.mode in ("RECOVERY", "ESCALATE", "HALTED") and eid != self.event["id"]:
            return "EVENT_MISMATCH"
        if self.event is None and eid.startswith("E-"):
            return "EVENT_MISMATCH"
        return None

    def _start_pending(self, cmd: dict[str, Any], result: dict[str, Any], sender: str) -> None:
        ch = cmd["channel_id"]
        ml = float(cmd["volume_ml"])
        speed = self.hand_speed_ml_s
        if self.link.kind == "SIM":
            from sim.model import P
            speed = P["dose_speed_ml_per_min"] / 60.0
        run_ms = int(max(1.0, ml / speed) * 1000)
        seq = int(cmd["sequence_number"]) % 1_000_000
        self.pending = {
            "command_id": cmd["command_id"], "channel_id": ch, "words": CHANNELS[ch]["words"],
            "ml": ml, "mmol": round(ml * CHANNELS[ch]["molarity"], 4), "sender": sender,
            "event_id": cmd["event_id"], "accepted_utc": result["decided_utc"],
            "t_accepted": self.clock(), "run_ms": run_ms,
            "instruction": f"Add {ml:g} mL of {CHANNELS[ch]['words']} now, then stir.",
        }
        self.link.dose(seq, CHANNELS[ch]["pump"], run_ms)
        if self.event is not None and cmd["event_id"] == self.event["id"]:
            self.event["doses"].append({"command_id": cmd["command_id"], "channel_id": ch, "ml": ml,
                                        "mmol": self.pending["mmol"], "sender": sender,
                                        "accepted_utc": result["decided_utc"], "added_utc": None})

    def _pending_step(self, now: float) -> None:
        p = self.pending
        if p is None:
            return
        if self.link.kind == "SIM" and getattr(self.link, "auto_pump", False) \
                and now - p["t_accepted"] >= p["run_ms"] / 1000.0:
            self.dose_added(p["command_id"], by="simulated pump (auto)")
            return
        if now - p["t_accepted"] > PENDING_TIMEOUT_S:
            self._cancel_pending(f"nobody confirmed it within {PENDING_TIMEOUT_S:.0f} s")

    def dose_added(self, command_id: str, by: str = "operator") -> dict[str, Any]:
        p = self.pending
        if p is None or p["command_id"] != command_id:
            return {"ok": False, "error": "that dose is not waiting to be added"}
        now = self.clock()
        self.pending = None
        self.link.stop_dose()
        self.link.dose_added(p["channel_id"], p["ml"])
        if self.model_a is not None:
            self.model_a.dose_added(command_id)
        # the 15 s mixing wait counts from when the dose actually went in
        self.gstate.last_dose_accepted_at_s = self.gateway.clock()
        self.mixing_until = now + MIX_S
        added = _wall()
        if self.event is not None:
            for d in self.event["doses"]:
                if d["command_id"] == command_id:
                    d["added_utc"] = added
        for b in self.block:
            if b["command_id"] == command_id:
                b["status"] = "mixing"
                b["added_t"] = now
        self.audit.event("DOSE_ADDED", f"{p['ml']:g} mL {p['words']} added to the tank ({by}); "
                         f"15 s mixing starts", event_id=p["event_id"], source="HMI" if by == "operator" else "station",
                         command_id=command_id, channel_id=p["channel_id"], volume_ml=p["ml"])
        if self.event is not None and self.block:
            if any(b["status"] == "queued" for b in self.block):
                self.next_block_at = now + MIX_S + 0.2
            else:
                from sim.model import P
                self.next_plan_at = now + P["t_hold"]
        return {"ok": True}

    def _cancel_pending(self, why: str, notify: bool = True) -> None:
        p = self.pending
        if p is None:
            return
        self.pending = None
        self.link.stop_dose()
        for b in self.block:
            if b["command_id"] == p["command_id"]:
                b["status"] = "cancelled"
        if self.event is not None:
            self.event["doses"] = [d for d in self.event["doses"] if d["command_id"] != p["command_id"]]
            if self.mode == "RECOVERY":
                self.next_plan_at = self.clock() + 2.0
        self.audit.event("DOSE_CANCELLED", f"{p['ml']:g} mL {p['words']} was not added: {why}. "
                         f"Do not add it.", event_id=p["event_id"], command_id=p["command_id"])

    # ---------------------------------------------------------------- Uno and link
    def _on_uno_event(self, ev: dict[str, Any]) -> None:
        kind = ev.get("kind", "")
        if kind == "MODE_ACK":
            if self.event is not None and self.event["t_uno_locked"] is None and self.link.last_mode_ack \
                    and self.link.last_mode_ack.get("mode") == "RECOVERY":
                self.event["t_uno_locked"] = ev["t"]
                self.event["uno_locked_utc"] = _wall()
                ms = (ev["t"] - self.event["t_confirm"]) * 1000
                self.audit.event("UNO_LOCKED", f"Uno confirmed dosing locked {ms:.0f} ms after the event "
                                 f"was confirmed", event_id=self.event["id"], source="Uno")
        elif kind == "ESTOP":
            self.halt("E-STOP pressed on the rig", by="Uno")
        elif kind == "UNO_REJECT":
            self.audit.event("UNO_REJECT", f"Uno refused a dose: {ev.get('reason', '')} ({ev.get('line', '')})",
                             source="Uno")
        elif kind == "UNO_HEARTBEAT_LOST":
            self.audit.event("UNO_HEARTBEAT_LOST", "Uno reports it lost the Pi's heartbeat and stopped", source="Uno")

    def _link_lost(self) -> None:
        self.audit.event("UNO_LINK_LOST", "no line from the Uno for 2 s: dosing blocked", source="Uno")
        if self.pending is not None:
            self._cancel_pending("the Uno link was lost")
        if self.mode != "HALTED":
            self.halt("Uno link lost (USB unplugged or Uno silent)", by="station")

    # ================================================================ operator actions
    def halt(self, why: str = "operator pressed HALT DOSING", by: str = "operator") -> dict[str, Any]:
        if self.mode == "HALTED":
            return {"ok": True, "mode": self.mode}
        self.halted_from = self.mode
        if self.pending is not None:
            self._cancel_pending("dosing was halted")
        self.block = [b for b in self.block if b["status"] != "queued"]
        self._set_mode("HALTED", why)
        self.gstate.mode = "SAFE_HOLD"
        self.link.send_mode("HALT")
        self.alarm_acked = by == "operator"
        self.audit.event("HALT", f"dosing halted: {why}", source="HMI" if by == "operator" else by,
                         event_id=self.event["id"] if self.event else "")
        return {"ok": True, "mode": self.mode}

    def resume(self) -> dict[str, Any]:
        if self.mode != "HALTED":
            return {"ok": False, "error": "RESUME only applies when dosing is halted"}
        if not self.link.alive():
            return {"ok": False, "error": "the Uno is not talking; reconnect it first"}
        if getattr(self.link, "estop", False):
            return {"ok": False, "error": "release the E-stop first"}
        self.gateway.manual_ack_new_session()           # Khalid's operator reset
        if self.event is not None:
            self._set_mode("RECOVERY", self.event["cls"] + " (resumed)")
            self.gstate.mode = "RECOVERY"
            self.link.send_mode("RECOVERY")
            self.escalation = None
            self.next_plan_at = self.clock() + 1.0
        else:
            self._set_mode("NORMAL", "resumed by the operator")
            self.gstate.mode = "NORMAL"
            self.link.send_mode("NORMAL")
        self.alarm_acked = True
        self.audit.event("RESUME", "operator reset: doses allowed again", source="HMI",
                         event_id=self.event["id"] if self.event else "")
        return {"ok": True, "mode": self.mode}

    def acknowledge(self) -> dict[str, Any]:
        self.alarm_acked = True
        what = self.mode_reason or self.mode
        if self.mode == "ESCALATE":
            what = f"{what} The operator has taken over; automatic recovery stays stopped."
        self.audit.event("ACKNOWLEDGE", f"operator acknowledged: {what}", source="HMI",
                         event_id=self.event["id"] if self.event else "")
        return {"ok": True}

    def hmi_shown(self, event_id: str) -> dict[str, Any]:
        """The HMI reports the moment it first drew the RECOVERY banner (INT-S1's end point)."""
        ev = next((e for e in self.events if e["id"] == event_id), None)
        if ev is None or ev["t_hmi_shown"] is not None:
            return {"ok": False}
        ev["t_hmi_shown"] = self.clock()
        ev["hmi_shown_utc"] = _wall()
        ms = (ev["t_hmi_shown"] - ev["t_confirm"]) * 1000
        self.audit.event("HMI_SHOWED_RECOVERY", f"the HMI showed RECOVERY {ms:.0f} ms after the event "
                         f"was confirmed (spec: under 2000 ms)", event_id=event_id, source="HMI")
        return {"ok": True, "ms": round(ms, 1)}

    def fresh_start(self, why: str) -> None:
        """Back to NORMAL with nothing open (a new tank in the simulator, between SUS
        participants). The audit log keeps everything; an open event is marked abandoned."""
        if self.pending is not None:
            self._cancel_pending(why)
        if self.event is not None:
            self.event["status"] = "closed"
            self.event["closed_utc"] = _wall()
            self.audit.event("EVENT_ABANDONED", f"event left open by a {why}", event_id=self.event["id"])
            self.event = None
        self.block, self.plan, self.escalation = [], None, None
        self.next_plan_at = self.next_block_at = None
        self.in_band_since = None
        self.recent.clear()
        self.mixing_until = None
        self.gstate.last_dose_accepted_at_s = None
        self.gateway.manual_ack_new_session()
        self._set_mode("NORMAL", why)
        self.gstate.mode = "NORMAL"
        self.link.send_mode("NORMAL")
        self.alarm_acked = True
        self.auto_recovery = True

    def set_auto_recovery(self, on: bool) -> dict[str, Any]:
        self.auto_recovery = bool(on)
        self.audit.event("AUTO_RECOVERY", f"automatic recovery {'on' if on else 'off'}", source="HMI")
        return {"ok": True, "auto_recovery": self.auto_recovery}

    def cancel_dose(self, command_id: str) -> dict[str, Any]:
        if self.pending is None or self.pending["command_id"] != command_id:
            return {"ok": False, "error": "that dose is not waiting"}
        self._cancel_pending("the operator cancelled it")
        return {"ok": True}

    # ---------------------------------------------------------------- S1 hold log
    def hold_start(self) -> dict[str, Any]:
        self.hold = {"active": True, "started_utc": _wall(), "t0": self.clock(), "rows": [],
                     "min": None, "max": None, "outside_s1": 0, "stopped_utc": None}
        self.audit.event("HOLD_LOG_START", "10-minute pH hold log started (S1: 6.5-7.5)", source="HMI")
        return {"ok": True}

    def hold_stop(self) -> dict[str, Any]:
        h = self.hold
        if not h or not h["active"]:
            return {"ok": False, "error": "no hold log running"}
        h["active"] = False
        h["stopped_utc"] = _wall()
        s = self._hold_summary()
        self.audit.event("HOLD_LOG_STOP", f"hold log stopped at {s['elapsed_s']:.0f} s: pH {s['min']}-{s['max']}, "
                         f"{'PASS' if s['pass'] else 'not a pass'}", source="HMI")
        return {"ok": True}

    def _hold_add(self, t: float, ph: float, mean3: float) -> None:
        h = self.hold
        el = t - h["t0"]
        h["rows"].append((round(el, 1), _wall(), ph, round(mean3, 3)))
        h["min"] = ph if h["min"] is None else min(h["min"], ph)
        h["max"] = ph if h["max"] is None else max(h["max"], ph)
        if not (S1_BAND[0] <= ph <= S1_BAND[1]):
            h["outside_s1"] += 1
        if el >= HOLD_LOG_S:
            self.hold_stop()

    def _hold_summary(self) -> dict[str, Any] | None:
        h = self.hold
        if not h:
            return None
        el = (self.clock() - h["t0"]) if h["active"] else (h["rows"][-1][0] if h["rows"] else 0.0)
        s = {"active": h["active"], "started_utc": h["started_utc"], "stopped_utc": h["stopped_utc"],
             "elapsed_s": round(min(el, HOLD_LOG_S), 1), "n": len(h["rows"]),
             "min": round(h["min"], 2) if h["min"] is not None else None,
             "max": round(h["max"], 2) if h["max"] is not None else None,
             "outside": h["outside_s1"],
             "pass": bool(h["rows"]) and h["outside_s1"] == 0 and el >= HOLD_LOG_S - 1,
             "doses": sum(1 for r in self.audit.records if r.reason_code == "DOSE_ADDED"
                          and r.timestamp_utc >= h["started_utc"])}
        mean3 = self._mean3()
        s["suggestion"] = None
        if h["active"] and mean3 is not None and not (TRIM_BAND[0] <= mean3 <= TRIM_BAND[1]) \
                and self.pending is None and self.mode == "NORMAL":
            try:
                need = self.chem.excess_from_ph(7.0) - self.chem.excess_from_ph(mean3)   # base-positive mmol
                base = need > 0
                fine_ml = abs(need) / 0.005
                ch = ("BASE" if base else "ACID") + ("_FINE" if fine_ml <= 20 else "_BULK")
                ml = fine_ml if fine_ml <= 20 else min(20.0, abs(need) / 0.5)
                ml = max(0.5, round(ml, 1))
                s["suggestion"] = {"channel_id": ch, "words": CHANNELS[ch]["words"], "ml": ml,
                                   "text": f"pH {mean3:.2f} is drifting: add {ml:g} mL of {CHANNELS[ch]['words']}"}
            except Exception:                                  # noqa: BLE001
                pass
        return s

    def hold_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["elapsed_s", "time_utc", "ph", "ph_mean_of_3", "source"])
        for row in (self.hold or {}).get("rows", []):
            w.writerow(list(row) + [self.link.kind])
        return buf.getvalue()

    # ================================================================ read side
    def state(self) -> dict[str, Any]:
        with self.lock:
            now = self.clock()
            mean3 = self._mean3()
            last = self.recent[-1] if self.recent else None
            ev = self.event
            used = self.gateway.event_mmol_used.get(ev["id"], 0.0) if ev else 0.0
            trend = [(round(t - now, 1), round(p, 3)) for t, _, p, _ in self.trend if now - t <= 300]
            slope = None
            if len(self.trend) >= 6:
                slope = (self.trend[-1][3] - self.trend[-6][3]) / max(0.5, self.trend[-1][0] - self.trend[-6][0])
            s = {
                "server_utc": _wall(),
                "uptime_s": round(now - self.started_t, 1),
                "mode": self.mode, "mode_reason": self.mode_reason, "mode_since": self.mode_since,
                "alarm_acked": self.alarm_acked, "auto_recovery": self.auto_recovery,
                "ph": {
                    "mean3": round(mean3, 2) if mean3 is not None else None,
                    "last": round(last[1], 3) if last else None,
                    "age_s": round(now - last[0], 1) if last else None,
                    "slope_per_min": round(slope * 60, 2) if slope is not None else None,
                    "source": self.link.kind, "trend": trend,
                    "band": BAND, "far": FAR,
                },
                "link": self.link.info(),
                "gateway": {
                    "last_sequence_number": self.gateway.last_sequence_number,
                    "lockout_s": round(self.gateway.lockout_remaining_s(), 1),
                    "session_id": self.config.active_session_id,
                    "chain_ok": self._chain_status(),
                    "records": len(self.audit.records),
                    "counters": dict(self.counters),
                    "group_words": GROUP_WORDS,
                },
                "model_a": {"loaded": self.model_a is not None and not self.model_a_error,
                            "error": self.model_a_error,
                            "version": self.model_a.model_version if self.model_a else "none"},
                "dose_event_id": ev["id"] if ev else "OPS",
                "event": self._event_view(ev, now) if ev else None,
                "last_event": self._event_view(self.events[-1], now) if (not ev and self.events) else None,
                "event_mmol_used": round(used, 3),
                "pending": self._pending_view(now),
                "mixing_s": round(max(0.0, self.mixing_until - now), 1) if self.mixing_until else 0.0,
                "plan": self._plan_view(now),
                "escalation": self.escalation,
                "decisions": list(self.decisions)[-6:][::-1],
                "hold": self._hold_summary(),
                "timing": [self._timing_row(e) for e in self.events][-8:][::-1],
                "chem_source": self.chem_source,
                "key_source": self.key_source,
                "demo_key": "demo key" in self.key_source,
            }
            if self.link.kind == "SIM":
                from sim import scenarios as SC
                s["sim"] = {"scenarios": SC.list_names()}
            return s

    def _event_view(self, ev: dict[str, Any], now: float) -> dict[str, Any]:
        closed = ev["status"] == "closed"
        elapsed = (ev["recovery_time_s"] if closed and ev["recovery_time_s"] is not None
                   else now - ev["t_confirm"])
        used = self.gateway.event_mmol_used.get(ev["id"], 0.0)
        delivered = sum(d["mmol"] for d in ev["doses"] if d.get("added_utc"))
        dwell = (now - self.in_band_since[0]) if (self.in_band_since and not closed) else None
        back_in_band = None
        if ev.get("t_in_band") is not None:
            back_in_band = round(ev["t_in_band"] - ev["t_confirm"], 1)
        return {"id": ev["id"], "cls": ev["cls"], "direction": ev["direction"], "status": ev["status"],
                "confirmed_utc": ev["confirmed_utc"], "confirm_ph": ev["confirm_ph"],
                "readings": ev["readings"], "elapsed_s": round(elapsed, 1) if not closed else None,
                "recovery_time_s": ev["recovery_time_s"], "reagent_mmol": round(delivered, 3),
                "authorised_mmol": round(used, 3), "back_in_band_s": back_in_band,
                "doses": ev["doses"], "escalations": ev["escalations"],
                "in_band_for_s": round(dwell, 1) if dwell is not None else None, "dwell_s": self.dwell_s,
                "timing": self._timing_row(ev)}

    @staticmethod
    def _ms(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else round((b - a) * 1000.0, 1)

    def _timing_row(self, ev: dict[str, Any]) -> dict[str, Any]:
        rec = self._ms(ev["t_confirm"], ev["t_recovery"])
        uno = self._ms(ev["t_confirm"], ev["t_uno_locked"])
        hmi = self._ms(ev["t_confirm"], ev["t_hmi_shown"])
        worst = max([x for x in (rec, uno, hmi) if x is not None], default=None)
        return {"event_id": ev["id"], "source": ev["source"], "first_out_utc": ev["first_out_utc"],
                "confirmed_utc": ev["confirmed_utc"], "recovery_utc": ev["recovery_utc"],
                "uno_locked_utc": ev["uno_locked_utc"], "hmi_shown_utc": ev["hmi_shown_utc"],
                "confirm_to_recovery_ms": rec, "confirm_to_uno_locked_ms": uno,
                "confirm_to_hmi_shown_ms": hmi, "worst_ms": worst,
                "pass_2s": (worst is not None and worst < 2000.0 and hmi is not None),
                "recovery_time_s": ev["recovery_time_s"],
                "reagent_mmol": round(self.gateway.event_mmol_used.get(ev["id"], 0.0), 3)}

    def timing_csv(self) -> str:
        buf = io.StringIO()
        rows = [self._timing_row(e) for e in self.events]
        cols = ["event_id", "source", "first_out_utc", "confirmed_utc", "recovery_utc", "uno_locked_utc",
                "hmi_shown_utc", "confirm_to_recovery_ms", "confirm_to_uno_locked_ms",
                "confirm_to_hmi_shown_ms", "worst_ms", "pass_2s", "recovery_time_s", "reagent_mmol"]
        w = csv.DictWriter(buf, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})
        return buf.getvalue()

    def trend_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["time_utc", "ph", "ph_mean_of_3", "source"])
        for _t, wall, p, m in self.trend:
            w.writerow([wall, p, round(m, 3), self.link.kind])
        return buf.getvalue()

    def _pending_view(self, now: float) -> dict[str, Any] | None:
        p = self.pending
        if p is None:
            return None
        out = {k: v for k, v in p.items() if k != "t_accepted"}
        out["waiting_s"] = round(now - p["t_accepted"], 1)
        out["timeout_s"] = PENDING_TIMEOUT_S
        return out

    def _plan_view(self, now: float) -> dict[str, Any] | None:
        if self.plan is None and not self.block:
            return None
        rows = []
        for b in self.block:
            r = dict(b)
            if b["status"] == "mixing" and b.get("added_t") is not None:
                left = MIX_S - (now - b["added_t"])
                r["status"] = f"mixing {left:.0f} s" if left > 0.5 else "complete"
                if left <= 0.5:
                    b["status"] = "complete"
            r.pop("added_t", None)
            rows.append(r)
        p = self.plan or {}
        next_in = None
        if self.next_plan_at is not None and not any(b["status"] == "queued" for b in self.block):
            next_in = round(max(0.0, self.next_plan_at - now), 0)
        return {"action": p.get("action"), "reason": p.get("reason"), "status": p.get("status"),
                "solve_ms": p.get("solve_ms"), "block_mmol": p.get("block_mmol"),
                "predicted_end_ph": p.get("predicted_end_ph"), "ph_used": p.get("ph_used"),
                "planned_utc": p.get("planned_utc"), "rows": rows, "why": WHY_PLAN,
                "replan_in_s": next_in}

    def _chain_status(self) -> dict[str, Any]:
        n = len(self.audit.records)
        if n != self._chain_checked_n:
            self._chain_ok = (self.audit.verify(), f"{n} records")
            self._chain_checked_n = n
        return {"ok": self._chain_ok[0], "detail": self._chain_ok[1]}

    def audit_view(self, only: str = "all", limit: int = 200) -> list[dict[str, Any]]:
        with self.lock:
            out = []
            for rec in reversed(self.audit.records):
                if only == "rejected" and rec.decision != "REJECT":
                    continue
                out.append(self.audit.view(rec))
                if len(out) >= limit:
                    break
            return out


class _RememberingModelA:
    """Passes the gateway's call to Model A and keeps the full I3 answer (with its reason)
    for the HMI, since the gateway's decision record keeps only label, score and time."""

    def __init__(self, inner) -> None:
        self.inner = inner
        self.last: dict[str, dict[str, Any]] = {}

    def predict(self, command, state):
        out = self.inner.predict(command, state)
        self.last[str(command.get("command_id", ""))] = out
        while len(self.last) > 64:
            self.last.pop(next(iter(self.last)))
        return out


class _NoModelA:
    """Used only with --no-model-a (for debugging): every dose is UNCERTAIN, so blocked."""

    def predict(self, command, state):
        return {"label": "UNCERTAIN_CONTEXT", "score": 1.0, "model_version": "none", "latency_ms": 0.0}
