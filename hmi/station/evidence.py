"""FPR evidence: one running record of every test the HMI can show, kept across station restarts.

The station feeds it as things happen (an event closes, a command is judged, a hold log stops)
and the Demo panel and the CSV exports read it. It lives next to the run folders, in
hmi/logs/fpr_evidence.json, so the 5 recorded recovery runs, the 2,000 attack commands and
the hold log all add up even when the station is restarted between them. Each run's own
audit log (hash chained) stays the primary record; this file is the summary of them.

    recovery runs    INT-S1, INT-S2, INT-S3, C3, S6 (one row per unsafe event)
    attacks          S3 (replayed + stale), C2 (forged, unsigned, tampered)
    Model A          S4 (class + risk score within 3 s)
    dose limits      S2 (20 mL cap, 15 s mixing wait)
    hold logs        S1 (6.5-7.5 for 10 min)
    bottles          C1 (only the four approved dilute reagents, all under 5 wt%)
"""
from __future__ import annotations

import csv
import io
import json
import os
import time
from pathlib import Path
from typing import Any

from hmi.common import CHANNELS, iso_ms

INT_S1_MS = 2000.0          # recovery mode within 2 s of the event
INT_S2_S = 300.0            # pH back inside 6.0-8.5 within 5 min
FAR = (5.5, 9.5)            # INT-S3: no overshoot past these on the far side
C3_MMOL = 50.0              # reagent ceiling per recovery
S6_S = 300.0                # recovered (back in band and held) within 300 s
S4_MS = 3000.0              # Model A class + score within 3 s
S2_ML, S2_MIX_S = 20.0, 15.0

# C1: what is in each bottle. wt% = g/L / (10 x density in g/mL)
_MW = {"NaOH": 40.00, "HCl": 36.46}
_DENSITY = {("NaOH", 0.5): 1.021, ("HCl", 0.5): 1.007}

ATTACK_KINDS = ("replay", "stale", "forged", "unsigned", "tampered")


def attack_kind(sender: str) -> str | None:
    """Which attack a command belongs to, from the tag the attack tools put on it.
    None for real commands, including the genuine original that a replay attack copies."""
    s = (sender or "").lower()
    if not (s.startswith("attacker") or s.startswith("attack script") or s.startswith("security test")):
        return None
    if "original" in s or "(valid)" in s:
        return None
    for kind, keys in (("replay", ("replay", "copy")), ("stale", ("stale", " ago")),
                       ("tampered", ("tamper",)), ("unsigned", ("unsigned", "no signature")),
                       ("forged", ("forged", "wrong key"))):
        if any(k in s for k in keys):
            return kind
    return None


def bottles() -> list[dict[str, Any]]:
    out = []
    for ch, c in CHANNELS.items():
        chem = "NaOH" if ch.startswith("BASE") else "HCl"
        m = float(c["molarity"])
        rho = _DENSITY.get((chem, m), 1.0)
        wt = m * _MW[chem] / (10.0 * rho)
        out.append({"channel_id": ch, "words": c["words"], "pump": c.get("pump"), "chemical": chem,
                    "molarity": m, "wt_pct": round(wt, 3), "pass": wt <= 5.0})
    return out


def _blank_attacks() -> dict[str, dict[str, int]]:
    return {k: {"sent": 0, "blocked": 0, "reached": 0} for k in ATTACK_KINDS}


def _blank_tally() -> dict[str, Any]:
    return {"attacks": _blank_attacks(),
            "model_a": {"n": 0, "max_ms": 0.0, "sum_ms": 0.0, "over_3s": 0, "acceptable": 0, "harmful": 0},
            "s2": {"limit_rejects": 0, "max_rejected_ml": None, "lockout_rejects": 0,
                   "accepted": 0, "max_accepted_ml": None, "min_gap_s": None, "gaps": 0, "gaps_under_15s": 0}}


class EvidenceStore:
    def __init__(self, path: Path, session: str) -> None:
        self.path = Path(path)
        self.session = session
        self.data: dict[str, Any] = {"since": iso_ms(), "runs": [], "holds": [], "all": _blank_tally()}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                self.data.update(loaded)
                # files from an older version: fill anything missing
                tally = _blank_tally()
                for k, v in tally.items():
                    self.data["all"].setdefault(k, v)
                for k, v in _blank_attacks().items():
                    self.data["all"]["attacks"].setdefault(k, v)
            except (OSError, ValueError):
                self.path.rename(self.path.with_suffix(f".unreadable-{int(time.time())}.json"))
        self.sess = _blank_tally()
        self._dirty = False
        self._saved_at = 0.0
        self.save(force=True)

    # ---------------------------------------------------------------- writing
    def save(self, force: bool = False) -> None:
        if not force and (not self._dirty or time.monotonic() - self._saved_at < 2.0):
            return
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        self._dirty = False
        self._saved_at = time.monotonic()

    def reset(self) -> str:
        """Start a fresh record; the old file is kept beside it."""
        self.save(force=True)
        old = self.path.with_name(f"fpr_evidence.before-{time.strftime('%Y%m%d-%H%M%S')}.json")
        os.replace(self.path, old)
        self.data = {"since": iso_ms(), "runs": [], "holds": [], "all": _blank_tally()}
        self.sess = _blank_tally()
        self.save(force=True)
        return old.name

    def _both(self):
        return (self.data["all"], self.sess)

    def decision(self, result: dict[str, Any], sender: str, gap_s: float | None) -> None:
        """One gateway decision (the station's _submit result)."""
        kind = attack_kind(sender)
        accepted = result.get("decision") == "ACCEPT"
        code = result.get("reason_code", "")
        for t in self._both():
            if kind:
                a = t["attacks"][kind]
                a["sent"] += 1
                a["blocked"] += 0 if accepted else 1
                a["reached"] += 1 if result.get("forwarded_to_actuator") else 0
            if result.get("model_a_label", "NOT_CALLED") != "NOT_CALLED":
                m = t["model_a"]
                ms = float(result.get("model_a_latency_ms") or 0.0)
                m["n"] += 1
                m["sum_ms"] += ms
                m["max_ms"] = max(m["max_ms"], ms)
                m["over_3s"] += 1 if ms > S4_MS else 0
                m["acceptable" if result["model_a_label"] == "ACCEPTABLE_CONTEXT" else "harmful"] += 1
            if kind:
                continue                      # attack traffic does not count as S2 evidence
            s2 = t["s2"]
            vol = float(result.get("volume_ml") or 0.0)
            if code == "DOSE_LIMIT":
                s2["limit_rejects"] += 1
                s2["max_rejected_ml"] = vol if s2["max_rejected_ml"] is None else max(s2["max_rejected_ml"], vol)
            elif code == "MIXING_LOCKOUT":
                s2["lockout_rejects"] += 1
            elif accepted:
                s2["accepted"] += 1
                s2["max_accepted_ml"] = vol if s2["max_accepted_ml"] is None else max(s2["max_accepted_ml"], vol)
                if gap_s is not None:
                    s2["gaps"] += 1
                    s2["gaps_under_15s"] += 1 if gap_s < S2_MIX_S else 0
                    s2["min_gap_s"] = round(gap_s if s2["min_gap_s"] is None else min(s2["min_gap_s"], gap_s), 2)
        self._dirty = True

    def run_closed(self, row: dict[str, Any]) -> None:
        row = dict(row, session=self.session, included=True)
        self.data["runs"].append(row)
        self._dirty = True
        self.save(force=True)

    def set_included(self, key: str, included: bool, why: str) -> bool:
        for r in self.data["runs"]:
            if r.get("key") == key:
                r["included"] = bool(included)
                r["excluded_why"] = "" if included else why
                self._dirty = True
                self.save(force=True)
                return True
        return False

    def hold_stopped(self, summary: dict[str, Any]) -> None:
        keep = {k: summary.get(k) for k in ("started_utc", "stopped_utc", "elapsed_s", "n", "min", "max",
                                             "outside", "pass", "doses")}
        self.data["holds"].append(dict(keep, session=self.session))
        self._dirty = True
        self.save(force=True)

    # ---------------------------------------------------------------- reading
    def counted_runs(self) -> list[dict[str, Any]]:
        return [r for r in self.data["runs"] if r.get("included", True)]

    def scorecard(self, *, live_event: dict[str, Any] | None = None, hold: dict[str, Any] | None = None,
                  model_a_loaded: bool = True) -> list[dict[str, Any]]:
        """One row per spec: id, title, requirement, result, status (PASS / FAIL / NOT_RUN / BOOTH)."""
        runs = self.counted_runs()
        n = len(runs)
        rows: list[dict[str, Any]] = []

        def add(item, title, req, result, status, how, session=""):
            rows.append({"item": item, "title": title, "requirement": req, "result": result,
                         "status": status, "how": how, "session": session})

        def frac(key):
            ok = sum(1 for r in runs if r.get(key))
            return ok, (f"{ok}/{n} runs" if n else "no runs yet")

        # ---- C1
        b = bottles()
        worst = max(x["wt_pct"] for x in b)
        add("C1", "Approved dilute reagents only", "only approved acid/base, each ≤ 5 wt%",
            f"{len(b)} approved bottles, strongest {worst:.2f} wt%", "PASS" if all(x["pass"] for x in b) else "FAIL",
            "The gateway accepts only these 4 channels (C1 tab); bottles and lab approval at the booth.")
        # ---- C2
        at, st = self.data["all"]["attacks"], self.sess["attacks"]
        c2k = ("forged", "unsigned", "tampered")
        c2_sent = sum(at[k]["sent"] for k in c2k)
        c2_blk = sum(at[k]["blocked"] for k in c2k)
        c2_reach = sum(at[k]["reached"] for k in at)
        add("C2", "Gateway is the only path to the pumps", "no unauthenticated command reaches the pumps",
            f"{c2_blk}/{c2_sent} forged/unsigned/tampered blocked, {c2_reach} reached the pumps"
            if c2_sent else "no attack run yet",
            "NOT_RUN" if not c2_sent else ("PASS" if c2_blk == c2_sent and c2_reach == 0 else "FAIL"),
            "bash fpr.sh attack (Security monitor + S3/C2 tab); c2_check in Terminal: ports, forwarding off.",
            f"this session {sum(st[k]['blocked'] for k in c2k)}/{sum(st[k]['sent'] for k in c2k)}")
        # ---- C3
        if n:
            mx = max(float(r.get("reagent_mmol") or 0) for r in runs)
            ok, txt = frac("c3_pass")
            add("C3", "Reagent per recovery", "≤ 50 mmol per recovery event",
                f"max {mx:.2f} mmol · {txt} within 50", "PASS" if ok == n else "FAIL",
                "Recovery runs tab; banner shows 'Event reagent x / 50 mmol' live.")
        else:
            add("C3", "Reagent per recovery", "≤ 50 mmol per recovery event", "no runs yet", "NOT_RUN",
                "Recovery runs tab.")
        # ---- S1
        holds = self.data["holds"]
        best = next((h for h in reversed(holds) if h.get("pass")), holds[-1] if holds else None)
        if hold and hold.get("active"):
            add("S1", "pH held in 6.5-7.5 for 10 min", "6.5-7.5 for 10 min",
                f"running: {hold['elapsed_s']:.0f}/600 s, pH {hold['min']}-{hold['max']}"
                + (f" (earlier: {'PASS' if best and best.get('pass') else 'none passed'})" if holds else ""),
                "PASS" if best and best.get("pass") else ("FAIL" if hold.get("outside") else "RUNNING"),
                "S1 hold tab: start the 10-minute log.")
        elif best:
            add("S1", "pH held in 6.5-7.5 for 10 min", "6.5-7.5 for 10 min",
                f"{best['elapsed_s']:.0f} s logged, pH {best['min']}-{best['max']}, {best['outside']} readings outside",
                "PASS" if best.get("pass") else "FAIL", "S1 hold tab (pH log CSV).")
        else:
            add("S1", "pH held in 6.5-7.5 for 10 min", "6.5-7.5 for 10 min", "no hold logged yet", "NOT_RUN",
                "S1 hold tab: start the 10-minute log.")
        # ---- S2
        s2, s2s = self.data["all"]["s2"], self.sess["s2"]
        parts, status = [], "NOT_RUN"
        if s2["limit_rejects"]:
            parts.append(f"{s2['limit_rejects']} over-20 mL request(s) rejected")
        if s2["max_accepted_ml"] is not None:
            parts.append(f"largest dose accepted {s2['max_accepted_ml']:.2f} mL")
        if s2["min_gap_s"] is not None:
            parts.append(f"shortest wait between doses {s2['min_gap_s']:.1f} s")
        if s2["lockout_rejects"]:
            parts.append(f"{s2['lockout_rejects']} early dose(s) held back by the mixing wait")
        if parts:
            bad = (s2["max_accepted_ml"] or 0) > S2_ML or s2["gaps_under_15s"] > 0
            status = "FAIL" if bad else ("PASS" if s2["limit_rejects"] and s2["gaps"] else "PARTIAL")
        add("S2", "Dose cap and mixing time", "≤ 20 mL per dose, ≥ 15 s mixing between doses",
            "; ".join(parts) or "no doses yet", status,
            "S2 tab: 'Request 25 mL' must be rejected; every dose waits 15 s after the last one.",
            f"this session: {s2s['limit_rejects']} cap rejections, {s2s['accepted']} doses")
        # ---- S3
        s3k = ("replay", "stale")
        s3_sent = sum(at[k]["sent"] for k in s3k)
        s3_blk = sum(at[k]["blocked"] for k in s3k)
        pct = 100.0 * s3_blk / s3_sent if s3_sent else 0.0
        add("S3", "Replayed / stale commands rejected", "≥ 99 % rejected",
            f"{s3_blk}/{s3_sent} rejected ({pct:.1f} %)" if s3_sent else "no attack run yet",
            "NOT_RUN" if not s3_sent else ("PASS" if pct >= 99.0 else "FAIL"),
            "bash fpr.sh attack; the 2,000-command runs (attack_station) add to the same count.",
            f"this session {sum(st[k]['blocked'] for k in s3k)}/{sum(st[k]['sent'] for k in s3k)}")
        # ---- S4
        m, ms = self.data["all"]["model_a"], self.sess["model_a"]
        if m["n"]:
            add("S4", "Class + risk score within 3 s", "every dose classified within 3 s",
                f"{m['n']} doses classified, slowest {m['max_ms']:.1f} ms, mean {m['sum_ms'] / m['n']:.1f} ms",
                "PASS" if m["over_3s"] == 0 and model_a_loaded else "FAIL",
                "S4 tab: each dose's class, score and time; 1,000-request test: model_a.latency_test.",
                f"this session {ms['n']} doses, slowest {ms['max_ms']:.1f} ms")
        else:
            add("S4", "Class + risk score within 3 s", "every dose classified within 3 s",
                "no dose classified yet" + ("" if model_a_loaded else " (Model A NOT loaded)"),
                "NOT_RUN" if model_a_loaded else "FAIL", "S4 tab.")
        # ---- S6, INT-S1, INT-S2, INT-S3
        for item, title, req, key, val, unit, how in (
                ("S6", "Recoveries within 300 s", "≥ 95 % recovered (back in band and held) within 300 s",
                 "s6_pass", "recovery_time_s", "s", "Recovery runs tab."),
                ("INT-S1", "Recovery mode within 2 s", "safe-recovery mode within 2 s of the event",
                 "int_s1_pass", "int_s1_ms", "ms", "INT-S1 timing tab: Pi, Uno and HMI times."),
                ("INT-S2", "pH back in 6.0-8.5 within 5 min", "back inside 6.0-8.5 within 300 s",
                 "int_s2_pass", "first_in_band_s", "s", "Recovery runs tab."),
                ("INT-S3", "No overshoot past 5.5 / 9.5", "≥ 90 % of runs never pass 5.5 / 9.5 on the far side",
                 "int_s3_pass", "far_side_ph", "pH", "Recovery runs tab: highest pH after an acid spill.")):
            if not n:
                add(item, title, req, "no runs yet", "NOT_RUN", how)
                continue
            ok, txt = frac(key)
            vals = [r.get(val) for r in runs if r.get(val) is not None]
            if item == "INT-S3":
                hi = [r["far_side_ph"] for r in runs if r.get("direction") == "acid" and r.get("far_side_ph") is not None]
                lo = [r["far_side_ph"] for r in runs if r.get("direction") == "base" and r.get("far_side_ph") is not None]
                worst = (f"; highest pH after an acid spill {max(hi):.2f}" if hi else "") + \
                        (f"; lowest pH after a base spill {min(lo):.2f}" if lo else "")
                need = 0.90
            else:
                worst = f"; worst {max(vals):.0f} {unit}" if vals else ""
                need = 0.95 if item == "S6" else 1.0
            add(item, title, req, txt + worst, "PASS" if ok / n >= need else "FAIL", how)
        if live_event:
            for r in rows:
                if r["item"] in ("C3", "S6", "INT-S1", "INT-S2", "INT-S3"):
                    r["session"] = (r["session"] + " · " if r["session"] else "") + f"{live_event['id']} in progress"
        return rows

    # ---------------------------------------------------------------- CSV
    RUN_COLS = ["key", "session", "event_id", "source", "direction", "first_out_utc", "confirmed_utc",
                "confirm_ph", "readings", "spill_side_ph", "far_side_ph", "int_s1_ms", "confirm_to_recovery_ms",
                "confirm_to_uno_locked_ms", "confirm_to_hmi_shown_ms", "int_s1_pass", "first_in_band_s",
                "int_s2_pass", "int_s3_pass", "reagent_mmol", "delivered_mmol", "c3_pass", "recovery_time_s",
                "s6_pass", "doses", "dose_list", "closed_utc", "outcome", "included", "excluded_why"]

    def runs_csv(self) -> str:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=self.RUN_COLS, extrasaction="ignore")
        w.writeheader()
        for r in self.data["runs"]:
            w.writerow({k: (json.dumps(r.get(k)) if isinstance(r.get(k), (list, dict)) else r.get(k))
                        for k in self.RUN_COLS})
        return buf.getvalue()

    def scorecard_csv(self, rows: list[dict[str, Any]]) -> str:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["item", "title", "requirement", "result", "status", "how_shown", "this_session",
                     "record_since"])
        for r in rows:
            w.writerow([r["item"], r["title"], r["requirement"], r["result"], r["status"], r["how"],
                        r["session"], self.data["since"]])
        w.writerow([])
        w.writerow(["S5", "Usability (SUS >= 80)", "", "SUS forms (Hattan)", "BOOTH", "not an HMI test", "", ""])
        w.writerow(["S7", "Pump rated <= 500 mL/min", "", "KPHM400, 400 mL/min rated", "BOOTH",
                    "pump label + datasheet", "", ""])
        w.writerow(["S9", "15 % less reagent than PI", "", "", "BOOTH", "not an HMI test", "", ""])
        return buf.getvalue()
