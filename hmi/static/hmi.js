// ChemShield HMI. Reads state from the laptop server (which reads the Pi) and sends
// requests there. It decides nothing: every dose goes to the gateway on the Pi.
"use strict";

const $ = (id) => document.getElementById(id);
const AI = "AI Dose Guard";  // operator-facing name of the Model A safety classifier
const esc = (x) => String(x ?? "").replace(/MODEL_A_/g, "AI_GUARD_").replace(/Model A/g, AI).replace(/[&<>"']/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const num = (x, d = 1) => (x === null || x === undefined || Number.isNaN(Number(x))) ? "—" : Number(x).toFixed(d);
const hms = (iso) => { if (!iso) return "—"; const t = new Date(iso); return t.toLocaleTimeString([], {hour12: false}); };
const hmsms = (iso) => { if (!iso) return "—"; const t = new Date(iso); return t.toLocaleTimeString([], {hour12: false}) + "." + String(t.getMilliseconds()).padStart(3, "0"); };

const CH_WORDS = {BASE_BULK: "NaOH 0.5 M bulk", BASE_FINE: "NaOH 0.005 M fine", ACID_BULK: "HCl 0.5 M bulk", ACID_FINE: "HCl 0.005 M fine"};
const GROUP_WORDS = {REPLAY: "Replayed", STALE: "Stale", LIMIT: "Over limit", LOCKOUT: "Mixing lockout",
  MODEL_A_BLOCK: "Blocked by AI Dose Guard", AUTH: "Not authorised", SCHEMA: "Malformed", STATE: "Wrong state", ACCEPT: "Accepted", OTHER: "Other"};

let S = null;               // last state
let logOnly = "all";
let evTab = "specs";
const EV_TABS = ["specs", "runs", "timing", "hold", "s2", "attacks", "s4", "c1"];
const shownEvents = new Set();
let simFilled = false;
let lastAuditKey = "";

async function api(path, body) {
  const opt = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const r = await fetch(path, opt);
  return r.json();
}
const act = (action, args) => api("/api/action", {action, args: args || {}}).then((r) => { poll(); pollAudit(true); return r; });

// ------------------------------------------------------------------ polling
async function poll() {
  let s;
  try { s = await api("/api/state"); } catch (e) { s = {station_ok: false, error: "the laptop HMI server is not running"}; }
  if (!s.station_ok) { renderOffline(s); return; }
  S = s;
  try { render(s); } catch (e) { console.error(e); }
}

async function pollAudit(force) {
  if (!S) return;
  const key = `${logOnly}:${S.gateway.records}`;
  if (!force && key === lastAuditKey) return;
  lastAuditKey = key;
  try {
    const a = await api(`/api/audit?only=${logOnly}&limit=60`);
    renderLog(a.records || []);
  } catch (e) { /* next time */ }
}

function renderOffline(s) {
  $("gw-dot").className = "dot dot-red";
  $("gw-text").textContent = "Station unreachable";
  const o = $("offline");
  o.classList.remove("hidden");
  o.textContent = `No connection to the gateway: ${s.error || "unknown error"}. Check the Pi and the Wi-Fi. Nothing can be dosed.`;
}

// ------------------------------------------------------------------ render
function render(s) {
  $("offline").classList.add("hidden");
  const alive = s.link && s.link.alive;
  $("gw-dot").className = "dot " + (alive ? "dot-green" : "dot-red");
  $("gw-text").textContent = alive ? "Gateway online" : "Gateway online · Uno link LOST";
  $("operator").textContent = (s.hmi && s.hmi.operator) || "—";

  const sim = s.ph.source === "SIM";
  $("sim-band").classList.toggle("hidden", !sim);
  $("sim-chem").textContent = sim ? `(pH table: ${s.chem_source})` : "";
  $("key-warn").classList.toggle("hidden", !s.demo_key);
  $("sim-panel").classList.toggle("hidden", !sim);

  renderBanner(s);
  renderPh(s);
  renderEventDetail(s);
  renderPlan(s);
  renderEvidence(s);
  renderActions(s);
  renderDoseNow(s);
  renderSafety(s);
  renderCounters(s);
  renderSecMon(s);
  renderEngineer(s);
  reportShown(s);
  pollAudit(false);
}

function zoneClass(ph) {
  if (ph === null || ph === undefined) return "";
  if (ph >= 6.0 && ph <= 8.5) return "t-green";
  if (ph >= 5.5 && ph <= 9.5) return "t-amber";
  return "t-red";
}

function metric(lab, val, cls, bar) {
  const b = bar === undefined ? "" : `<div class="mbar"><div style="width:${Math.min(100, Math.max(0, bar))}%"></div></div>`;
  return `<div class="metric"><div class="lab">${lab}</div><div class="val ${cls || ""}">${val}</div>${b}</div>`;
}

function renderBanner(s) {
  const b = $("banner"), title = $("banner-title"), m = $("banner-metrics");
  const ev = s.event;
  let cls = "banner-normal", t = "NORMAL", sub = "pH inside 6.0–8.5. Every dose goes through the gateway.";
  if (s.mode === "RECOVERY") { cls = "banner-recovery"; t = "⚠ UNSAFE DOSING EVENT — RECOVERY IN PROGRESS"; sub = ev ? ev.cls : ""; }
  else if (s.mode === "ESCALATE") { cls = "banner-escalate"; t = "⚠ OPERATOR DECISION REQUIRED"; sub = (s.escalation && s.escalation.words) || s.mode_reason; }
  else if (s.mode === "HALTED") { cls = "banner-halted"; t = "■ HALTED — NO DOSING"; sub = `${s.mode_reason}. Press RESUME DOSING to allow doses again.`; }
  b.className = "banner " + cls + (s.alarm_acked ? "" : " flash");
  title.innerHTML = `${esc(t)}<div class="banner-sub">${esc(sub)}</div>`;

  if (ev) {
    const el = ev.elapsed_s ?? 0;
    const tcls = el > 300 ? "t-red" : el > 240 ? "t-amber" : "";
    const reag = ev.reagent_mmol ?? 0;
    let band = "not yet";
    if (ev.back_in_band_s !== null && ev.back_in_band_s !== undefined) {
      band = `at ${num(ev.back_in_band_s, 0)} s`;
      if (ev.in_band_for_s !== null && ev.in_band_for_s !== undefined) band += ` · holding ${num(ev.in_band_for_s, 0)}/${num(ev.dwell_s, 0)} s`;
    }
    m.innerHTML = metric("Event", esc(ev.id)) +
      metric("Recovery", `${num(el, 0)} s / 300 s`, tcls, el / 3) +
      metric("Event reagent", `${num(reag, 1)} / 50 mmol`, reag > 45 ? "t-red" : "", reag * 2) +
      metric("pH back in 6.0–8.5", band);
  } else if (s.last_event) {
    const le = s.last_event;
    m.innerHTML = metric("Last event", esc(le.id)) +
      metric("Recovered in", le.recovery_time_s !== null ? `${num(le.recovery_time_s, 0)} s` : "—") +
      metric("Reagent used", `${num(le.reagent_mmol, 1)} mmol`);
  } else {
    m.innerHTML = "";
  }
}

function renderPh(s) {
  const p = s.ph;
  const v = p.mean3;
  const el = $("ph-value");
  el.textContent = v === null ? "--" : num(v, 2);
  el.className = "ph " + zoneClass(v);
  let trend = "";
  if (p.slope_per_min !== null && p.slope_per_min !== undefined) {
    trend = Math.abs(p.slope_per_min) < 0.05 ? "steady" : p.slope_per_min > 0 ? "rising" : "falling";
  }
  const age = p.age_s === null ? "no reading yet" : `reading ${num(p.age_s, 1)} s old`;
  const stale = p.age_s !== null && p.age_s > 2.5;
  $("ph-sub").innerHTML = `pH${trend ? " · " + trend : ""} · <span class="${stale ? "bad" : ""}">${stale ? "STALE: " : ""}${age}</span>`;
  const tag = $("ph-source");
  tag.textContent = p.source === "SIM" ? "SIMULATED" : "PROBE";
  tag.className = "tag " + (p.source === "SIM" ? "tag-sim" : "tag-probe");

  const pos = (x) => `${((x - 2) / 10) * 100}%`;
  $("scale-band").style.left = pos(6.0); $("scale-band").style.width = `${(2.5 / 10) * 100}%`;
  $("scale-g1").style.left = pos(5.5); $("scale-g2").style.left = pos(9.5);
  if (v !== null) $("scale-now").style.left = `calc(${pos(Math.max(2, Math.min(12, v)))} - 2px)`;
  drawTrend(p.trend || [], s.hold && s.hold.active);
}

function drawTrend(pts, hold) {
  const svgEl = $("trend");
  const W = Math.max(200, svgEl.clientWidth || 340), H = Math.max(80, svgEl.clientHeight || 130);
  svgEl.setAttribute("viewBox", `0 0 ${W} ${H}`);
  const y = (ph) => H - ((Math.max(2, Math.min(12, ph)) - 2) / 10) * H, x = (t) => W + (t / 300) * W;
  let svg = "";
  const line = (ph, color, dash, label) => {
    svg += `<line x1="0" x2="${W}" y1="${y(ph)}" y2="${y(ph)}" stroke="${color}" stroke-width="${dash ? 1 : 1.6}" ${dash ? `stroke-dasharray="${dash}"` : ""} vector-effect="non-scaling-stroke"/>`;
    const below = label === "8.5" || label === "5.5" || label === "6.5";
    svg += `<text x="${W - 4}" y="${below ? y(ph) + 11 : y(ph) - 3}" text-anchor="end" font-size="11" font-weight="bold" fill="${color}">${label}</text>`;
  };
  line(9.5, "#A83232", "4 3", "9.5"); line(8.5, "#167A5A", "", "8.5");
  line(6.0, "#167A5A", "", "6.0"); line(5.5, "#A83232", "4 3", "5.5");
  if (hold) { line(7.5, "#6C55A3", "2 2", "7.5"); line(6.5, "#6C55A3", "2 2", "6.5"); }
  if (pts.length > 1) {
    const d = pts.map(([t, ph]) => `${x(t).toFixed(1)},${y(ph).toFixed(1)}`).join(" ");
    svg += `<polyline points="${d}" fill="none" stroke="#17365D" stroke-width="2.2" vector-effect="non-scaling-stroke"/>`;
  }
  svgEl.innerHTML = svg;
}

function lastModelDecision(s) {
  return (s.decisions || []).find((d) => d.model_a_label && d.model_a_label !== "NOT_CALLED");
}

function kv(k, v, cls) { return `<div class="kv"><span class="k">${k}</span><span class="v ${cls || ""}">${v}</span></div>`; }

function renderEventDetail(s) {
  const ev = s.event;
  const d = lastModelDecision(s);
  let h = "";
  if (ev) {
    h += kv("Class", esc(ev.cls));
    h += kv("Confirmed", `${hmsms(ev.confirmed_utc)}`);
    h += kv("Readings that confirmed it", esc((ev.readings || []).join(", ")));
    const tm = ev.timing || {};
    const shown = tm.confirm_to_hmi_shown_ms;
    h += kv("Confirmed → RECOVERY shown", shown === null || shown === undefined ? "measuring…" : `${num(shown, 0)} ms`,
      shown !== null && shown !== undefined ? (shown < 2000 ? "t-green" : "t-red") : "");
    h += kv("Reagent delivered / authorised", `${num(ev.reagent_mmol, 2)} / ${num(ev.authorised_mmol, 2)} mmol`);
  } else {
    h += `<div class="note" style="margin:0 0 8px">No unsafe event. An event is confirmed when 3 readings in a row are outside 6.0–8.5; the system then switches to recovery by itself.</div>`;
  }
  if (d) {
    h += kv(`${AI} class`, esc(d.model_a_label.replace("_CONTEXT", "")), d.model_a_label === "ACCEPTABLE_CONTEXT" ? "t-green" : "t-red");
    h += kv(`${AI} risk score`, num(d.model_a_score, 2));
    h += kv(`${AI} time`, `${num(d.model_a_latency_ms, 1)} ms <span class="note" style="margin:0">(limit 3000 ms)</span>`);
    h += kv("For", `${esc(num(d.volume_ml, 1))} mL ${esc(CH_WORDS[d.channel_id] || d.channel_id)}`);
  }
  $("event-detail").innerHTML = h;
}

function renderPlan(s) {
  const p = s.plan, ev = s.event, tag = $("plan-tag");
  let h = "";
  if (s.escalation && s.mode === "ESCALATE") {
    h += `<div class="reply rej" style="margin:0 0 12px"><b>Operator decision required.</b> ${esc(s.escalation.words)}
      <span class="sm">${esc(s.escalation.detail || "")}</span>
      <span class="sm">Press ACKNOWLEDGE to take over (manual doses still go through the gateway), or HALT DOSING to stop.</span></div>`;
  }
  if (!p) {
    tag.classList.add("hidden");
    h += ev ? `<div class="note" style="margin-top:0">No doses planned for this event yet.</div>`
            : `<div class="note" style="margin-top:0">No recovery running. The optimiser plans doses only after an unsafe event is confirmed.</div>`;
    if (s.last_event) {
      const le = s.last_event;
      h += `<div class="two"><div>${kv("Last event", esc(le.id))}${kv("Recovered in", le.recovery_time_s !== null ? num(le.recovery_time_s, 0) + " s (limit 300)" : "—")}</div>
            <div>${kv("Reagent used", num(le.reagent_mmol, 2) + " mmol (limit 50)")}${kv("Doses", String((le.doses || []).length))}</div></div>`;
    }
    $("plan").innerHTML = h;
    return;
  }
  if (p.action === "WAIT") {
    tag.classList.add("hidden");
    $("plan").innerHTML = h + `<div class="note" style="margin-top:0">Waiting for the pH reading to settle before planning (the probe lags a few seconds behind the tank).</div>`;
    return;
  }
  if (p.solve_ms !== undefined && p.solve_ms !== null) {
    tag.textContent = `robust MILP · ${p.status || p.action} · ${num(p.solve_ms, 0)} ms`;
    tag.classList.remove("hidden");
  }
  h += `<table><thead><tr><th style="width:34px">#</th><th>Reagent bottle</th><th style="width:90px">Dose</th><th style="width:100px">Reagent</th><th style="width:60px">Hold</th><th style="width:130px">Status</th></tr></thead><tbody>`;
  for (const r of p.rows || []) {
    const st = String(r.status);
    const rc = st === "complete" ? "rowdone" : (st.startsWith("mixing") || st === "dose now" || st === "requested") ? "rownow" : "";
    const sc = st === "complete" ? "done" : st.startsWith("rejected") || st === "cancelled" ? "bad" : st === "queued" ? "wait" : "now2";
    h += `<tr class="${rc}"><td>${r.n}</td><td>${esc(r.words)}</td><td>${num(r.dose_ml, 2)} mL</td><td>${num(r.mmol, 3)} mmol</td><td>${num(r.hold_s, 0)} s</td><td class="${sc}">${esc(st)}</td></tr>`;
  }
  if (!(p.rows || []).length) h += `<tr><td colspan="6" class="wait">${esc(p.action === "HOLD" ? "Nothing to dose right now: the tank is close enough to the band. Re-checking." : (p.reason || p.action || ""))}</td></tr>`;
  h += `</tbody></table>`;
  const used = ev ? ev.reagent_mmol : 0, el = ev ? (ev.elapsed_s || 0) : 0;
  const pe = p.predicted_end_ph;
  const peOk = pe !== null && pe !== undefined && pe >= 5.5 && pe <= 9.5;
  h += `<div class="two">
    <div>${kv("Reagent delivered this event", num(used, 2) + " mmol")}
         ${kv("Ceiling (C3)", `50 mmol <span class="t-green">— ${num(100 - used * 2, 0)}% margin</span>`)}
         <div class="bararea"><div class="barfill" style="width:${Math.min(100, used * 2)}%;background:${used > 45 ? "#A83232" : "#167A5A"}"></div></div></div>
    <div>${kv("Elapsed / limit (S6)", `${num(el, 0)} s / 300 s`)}
         ${kv("Predicted pH after this plan", pe === null || pe === undefined ? "—" : `${num(pe, 2)} <span class="${peOk ? "t-green" : "t-red"}">— ${peOk ? "no overshoot" : "check"}</span>`)}
         <div class="bararea"><div class="barfill" style="width:${Math.min(100, el / 3)}%;background:${el > 240 ? "#B97800" : "#167A5A"}"></div></div></div></div>`;
  if (p.replan_in_s !== null && p.replan_in_s !== undefined) h += `<div class="note">Re-plans from a fresh averaged reading in ${num(p.replan_in_s, 0)} s.</div>`;
  h += `<div class="note"><b>Why this plan:</b> ${esc(p.why)}</div>`;
  $("plan").innerHTML = h;
}

// ------------------------------------------------------------------ demo panel: evidence for the reviewers
const ST_WORDS = {PASS: "PASS", FAIL: "FAIL", NOT_RUN: "not run", RUNNING: "running", PARTIAL: "partly shown", BOOTH: "at the booth"};
const st = (x) => `<span class="st st-${esc(x)}">${esc(ST_WORDS[x] || x)}</span>`;
const pf = (b) => b === null || b === undefined ? "" : b ? ` <span class="pass">✓</span>` : ` <span class="fail">✗</span>`;
const dt = (iso) => { if (!iso) return "—"; const t = new Date(iso); return t.toLocaleString([], {month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false}); };
function setHTML(id, h) { const el = $(id); if (el && el.__h !== h) { el.innerHTML = h; el.__h = h; } }
const chip = (lab, val, cls) => `<span class="chip ${cls || ""}">${lab}<b>${val}</b></span>`;
let s2Reply = "";

function renderEvidence(s) {
  const E = s.evidence;
  if (!E) return;
  $("ev-since").textContent = `· record since ${dt(E.since)} · kept across restarts`;
  renderSpecs(s, E);
  renderRuns(s, E);
  renderTiming(s);
  renderHold(s, E);
  renderS2(s, E);
  renderAttacks(s, E);
  renderS4(s, E);
  renderC1(E);
}

function renderSpecs(s, E) {
  const rows = E.scorecard || [];
  const n = (k) => rows.filter((r) => r.status === k).length;
  let h = `<div class="ev-sum">${chip("PASS", n("PASS"), "good")}${n("FAIL") ? chip("FAIL", n("FAIL"), "bad") : ""}${chip("not run yet", n("NOT_RUN") + n("RUNNING") + n("PARTIAL"))}${chip("shown at the booth", 3)}</div>`;
  h += `<table class="ev-tbl"><thead><tr><th style="width:70px">Item</th><th>Requirement</th><th>Result on this rig</th><th style="width:96px">Status</th><th style="width:30%">How it is shown</th></tr></thead><tbody>`;
  for (const r of rows) {
    h += `<tr><td class="it">${esc(r.item)}</td><td>${esc(r.title)}<span class="sub">${esc(r.requirement)}</span></td>
      <td>${esc(r.result)}${r.session ? `<span class="sub">${esc(r.session)}</span>` : ""}</td><td>${st(r.status)}</td><td class="note" style="margin:0">${esc(r.how)}</td></tr>`;
  }
  h += `<tr><td class="it">S5</td><td>Usability<span class="sub">SUS ≥ 80</span></td><td>SUS forms and score chart</td><td>${st("BOOTH")}</td><td class="note">Reviewers can try the HMI themselves.</td></tr>
    <tr><td class="it">S7</td><td>Pump flow rating<span class="sub">rated max ≤ 500 mL/min</span></td><td>Kamoer KPHM400, 400 mL/min rated</td><td>${st("BOOTH")}</td><td class="note">Pump label and datasheet.</td></tr>
    <tr><td class="it">S9</td><td>Reagent vs a PI controller<span class="sub">≥ 15 % less</span></td><td>—</td><td>${st("BOOTH")}</td><td class="note">Not an HMI test.</td></tr>`;
  h += `</tbody></table><div class="note">Results count every run since the record started, through station restarts; "this session" is since the station last started.
    <a class="linkbtn" href="/api/export/spec_scorecard.csv">Download the scorecard (CSV)</a> <a class="linkbtn" href="/api/export/recovery_runs.csv">Download all recovery runs (CSV)</a></div>`;
  setHTML("ev-specs", h);
}

function runCells(r, live) {
  const ms = r.int_s1_ms === null || r.int_s1_ms === undefined ? "—" : `${num(r.int_s1_ms, 0)} ms`;
  const fib = r.first_in_band_s === null || r.first_in_band_s === undefined ? (live ? "not yet" : "never") : `${num(r.first_in_band_s, 0)} s`;
  const rec = r.recovery_time_s === null || r.recovery_time_s === undefined ? (live ? `${num(r.elapsed_s, 0)} s so far` : esc(r.outcome)) : `${num(r.recovery_time_s, 0)} s`;
  const side = r.direction === "acid" ? "highest" : "lowest";
  return `<td>${esc(r.direction === "acid" ? "acid" : "base")} spill<span class="sub">confirmed at pH ${num(r.confirm_ph, 2)}; ${r.direction === "acid" ? "lowest" : "highest"} ${num(r.spill_side_ph, 2)}</span></td>
    <td>${ms}${live && r.confirm_to_hmi_shown_ms == null ? "" : pf(r.int_s1_pass)}<span class="sub">Pi ${num(r.confirm_to_recovery_ms, 1)} · Uno ${num(r.confirm_to_uno_locked_ms, 0)} · HMI ${num(r.confirm_to_hmi_shown_ms, 0)}</span></td>
    <td>${fib}${live && r.first_in_band_s == null ? "" : pf(r.int_s2_pass)}</td>
    <td>${num(r.far_side_ph, 2)}${pf(r.int_s3_pass)}<span class="sub">${side} pH after the spill</span></td>
    <td>${num(r.reagent_mmol, 2)} mmol${pf(r.c3_pass)}<span class="sub">${r.doses} dose${r.doses === 1 ? "" : "s"}</span></td>
    <td>${rec}${live ? "" : pf(r.s6_pass)}</td>`;
}

function renderRuns(s, E) {
  const runs = E.runs || [], counted = runs.filter((r) => r.included !== false);
  const n = counted.length, ok = (k) => counted.filter((r) => r[k]).length;
  const frac = (k) => n ? `${ok(k)}/${n}` : "—";
  const c3max = n ? Math.max(...counted.map((r) => Number(r.reagent_mmol) || 0)) : null;
  let h = `<div class="note" style="margin-top:0">One row per unsafe event on the real tank. INT-S1: recovery mode within 2 s. INT-S2: back inside 6.0–8.5 within 300 s. INT-S3: the far side (pH after an acid spill must stay ≤ 9.5, after a base spill ≥ 5.5), needed in ≥ 90 % of runs. C3: ≤ 50 mmol. S6: recovered (back in band and held ${num(s.event ? s.event.dwell_s : 60, 0)} s) within 300 s in ≥ 95 % of runs. pH values are the mean of 3 readings, as on the main screen.</div>`;
  h += `<div class="ev-sum">${chip("Runs counted", n)}${chip("INT-S1", frac("int_s1_pass"), n && ok("int_s1_pass") === n ? "good" : "")}${chip("INT-S2", frac("int_s2_pass"), n && ok("int_s2_pass") === n ? "good" : "")}${chip("INT-S3", frac("int_s3_pass"), n && ok("int_s3_pass") / n >= 0.9 ? "good" : "")}${chip("C3 max", c3max === null ? "—" : num(c3max, 2) + " mmol", c3max !== null && c3max <= 50 ? "good" : "")}${chip("S6", frac("s6_pass"), n && ok("s6_pass") / n >= 0.95 ? "good" : "")}</div>`;
  h += `<table class="ev-tbl"><thead><tr><th>Run</th><th>Spill</th><th>INT-S1 recovery mode</th><th>INT-S2 back in band</th><th>INT-S3 far side</th><th>C3 reagent</th><th>S6 recovered in</th><th style="width:70px"></th></tr></thead><tbody>`;
  if (E.live) h += `<tr class="live"><td><b>${esc(E.live.event_id)}</b><span class="sub">in progress · ${hms(E.live.confirmed_utc)}</span></td>${runCells(E.live, true)}<td></td></tr>`;
  if (!runs.length && !E.live) h += `<tr><td colspan="8" class="wait">No recovery runs yet. Spill acid into the tank: the run appears here when the event closes.</td></tr>`;
  for (const r of runs) {
    const out = r.included === false;
    h += `<tr class="${out ? "out" : ""}"><td>${esc(r.event_id)}<span class="sub">${dt(r.confirmed_utc)}${out ? " · left out: " + esc(r.excluded_why || "") : ""}</span></td>${runCells(r, false)}
      <td class="keep"><button class="xbtn" data-act="${out ? "run-in" : "run-out"}" data-key="${esc(r.key)}">${out ? "count it" : "leave out"}</button></td></tr>`;
  }
  h += `</tbody></table><div class="note">"Leave out" keeps the run in the table and the CSV but not in the statistics (a rehearsal, a spill made wrong); the reason goes in the audit log.
    <a class="linkbtn" href="/api/export/recovery_runs.csv">Download all recovery runs (CSV)</a></div>`;
  setHTML("ev-runs", h);
}

function renderTiming(s) {
  const rows = s.timing || [];
  let h = `<div class="note" style="margin-top:0">INT-S1: the system must enter safe-recovery mode within 2 s of confirming an unsafe event. Each time is measured on the Pi's clock from the moment the event was confirmed. "HMI showed it" is when this screen actually drew the red banner, so keep the HMI in front: browsers slow down tabs that are hidden. (This session's events; every run is in Recovery runs.)</div>`;
  h += `<table style="margin-top:8px"><thead><tr><th>Event</th><th>Confirmed</th><th>Recovery mode</th><th>Uno locked</th><th>HMI showed it</th><th>Result</th></tr></thead><tbody>`;
  if (!rows.length) h += `<tr><td colspan="6" class="wait">No event yet in this session.</td></tr>`;
  for (const r of rows) {
    const ms = (x) => x === null || x === undefined ? "—" : `${num(x, 0)} ms`;
    const res = r.confirm_to_hmi_shown_ms === null ? `<span class="wait">measuring</span>` : r.pass_2s ? `<span class="pass">PASS</span>` : `<span class="fail">FAIL</span>`;
    h += `<tr><td>${esc(r.event_id)} <span class="tag ${r.source === "SIM" ? "tag-sim" : "tag-probe"}">${r.source}</span></td><td>${hmsms(r.confirmed_utc)}</td><td>+${ms(r.confirm_to_recovery_ms)}</td><td>+${ms(r.confirm_to_uno_locked_ms)}</td><td>+${ms(r.confirm_to_hmi_shown_ms)}</td><td>${res}</td></tr>`;
  }
  h += `</tbody></table><div class="note"><a class="linkbtn" href="/api/export/int_s1_timing.csv">Download timing CSV</a></div>`;
  setHTML("ev-timing", h);
}

function renderHold(s, E) {
  const hd = s.hold;
  let g = `<div class="note" style="margin-top:0">S1 (CHE-AT-04): start the log, follow any dose the HMI asks for, and the pH must stay inside 6.5–7.5 for 10 minutes.</div>`;
  g += `<div class="row">${!hd || !hd.active ? `<button class="btn2" data-act="hold-start">Start the 10-minute log</button>` : `<button class="btn2" data-act="hold-stop">Stop the log</button>`}</div>`;
  if (hd) {
    const pct = Math.min(100, (hd.elapsed_s / 600) * 100);
    g += `<div class="two"><div>${kv("Elapsed", `${num(hd.elapsed_s, 0)} s / 600 s`)}${kv("Lowest pH", num(hd.min, 2))}${kv("Highest pH", num(hd.max, 2))}</div>
          <div>${kv("Readings outside 6.5–7.5", String(hd.outside), hd.outside ? "t-red" : "t-green")}${kv("Doses added", String(hd.doses))}
          ${kv("Result", hd.pass ? `<span class="pass">PASS</span>` : hd.active ? "running" : (hd.outside ? `<span class="fail">outside the band</span>` : "stopped early"))}</div></div>
          <div class="bararea"><div class="barfill" style="width:${pct}%"></div></div>`;
    if (hd.suggestion) {
      g += `<div class="reply info"><b>The HMI asks for a dose:</b> ${esc(hd.suggestion.text)}.
            <button class="btn2" data-act="use-sugg" style="margin-left:6px">Put it in the dose form</button></div>`;
    }
    g += `<div class="note"><a class="linkbtn" href="/api/export/s1_hold.csv">Download the pH log (CSV)</a></div>`;
  }
  const holds = E.holds || [];
  if (holds.length) {
    g += `<table class="ev-tbl" style="margin-top:10px"><thead><tr><th>Hold logs recorded</th><th>Logged</th><th>pH range</th><th>Outside 6.5–7.5</th><th>Result</th></tr></thead><tbody>`;
    for (const x of holds) g += `<tr><td>${dt(x.started_utc)}</td><td>${num(x.elapsed_s, 0)} s</td><td>${num(x.min, 2)} – ${num(x.max, 2)}</td><td>${x.outside}</td><td>${x.pass ? `<span class="pass">PASS</span>` : `<span class="fail">not a pass</span>`}</td></tr>`;
    g += `</tbody></table>`;
  }
  setHTML("ev-hold", g);
}

function renderS2(s, E) {
  const a = E.s2.all, se = E.s2.session;
  const lock = s.gateway.lockout_s || 0, canLock = lock >= 2 && !s.pending;
  let h = `<div class="note" style="margin-top:0">S2: no single dose over 20 mL, and at least 15 s of mixing after a dose before the next one. The gateway enforces both; the gap below is measured from when the last dose went into the tank to when the next one was accepted.</div>`;
  h += `<table class="ev-tbl" style="margin-top:8px"><thead><tr><th></th><th>All recorded</th><th>This session</th><th>Limit</th><th>Result</th></tr></thead><tbody>
    <tr><td>Requests over 20 mL rejected</td><td>${a.limit_rejects}${a.max_rejected_ml != null ? ` (up to ${num(a.max_rejected_ml, 1)} mL)` : ""}</td><td>${se.limit_rejects}</td><td>every one</td><td>${a.limit_rejects ? `<span class="pass">PASS</span>` : `<span class="wait">not tried yet</span>`}</td></tr>
    <tr><td>Largest dose accepted</td><td>${a.max_accepted_ml == null ? "—" : num(a.max_accepted_ml, 2) + " mL"} (${a.accepted} doses)</td><td>${se.max_accepted_ml == null ? "—" : num(se.max_accepted_ml, 2) + " mL"} (${se.accepted})</td><td>≤ 20 mL</td><td>${a.max_accepted_ml == null ? `<span class="wait">no dose yet</span>` : a.max_accepted_ml <= 20 ? `<span class="pass">PASS</span>` : `<span class="fail">FAIL</span>`}</td></tr>
    <tr><td>Shortest wait between doses</td><td>${a.min_gap_s == null ? "—" : num(a.min_gap_s, 1) + " s"} (${a.gaps} gaps)</td><td>${se.min_gap_s == null ? "—" : num(se.min_gap_s, 1) + " s"}</td><td>≥ 15 s</td><td>${a.min_gap_s == null ? `<span class="wait">needs 2 doses</span>` : a.gaps_under_15s === 0 ? `<span class="pass">PASS</span>` : `<span class="fail">FAIL</span>`}</td></tr>
    <tr><td>Early doses held back by the mixing wait</td><td>${a.lockout_rejects}</td><td>${se.lockout_rejects}</td><td></td><td></td></tr>
    </tbody></table>`;
  h += `<div class="row" style="margin-top:10px"><button class="btn2" data-act="s2-cap">Request 25 mL (must be rejected)</button>
    <button class="btn2" data-act="s2-lock" ${canLock ? "" : "disabled"}>Try a dose during the mixing wait${canLock ? ` (${num(lock, 0)} s left)` : ""}</button></div>
    <div class="note">${canLock ? "Sends 1 mL of NaOH 0.005 M now; the gateway must refuse it." : "The mixing-wait test is available for 15 s after each dose goes in (the recovery doses are a good moment)."} Nothing is pumped when a request is refused.</div>`;
  if (s2Reply) h += s2Reply;
  const ds = (s.decisions || []).filter((d) => ["LIMIT", "LOCKOUT", "ACCEPT"].includes(d.group) && !/attack|security test/i.test(d.sender || ""));
  if (ds.length) {
    h += `<table class="ev-tbl" style="margin-top:10px"><thead><tr><th>Received</th><th>Dose</th><th>From</th><th>Since the last dose</th><th>Gateway</th></tr></thead><tbody>`;
    for (const d of ds) h += `<tr><td>${hmsms(d.received_utc)}</td><td>${num(d.volume_ml, 2)} mL ${esc(CH_WORDS[d.channel_id] || d.channel_id)}</td><td>${esc(d.sender)}</td><td>${d.since_last_dose_s == null ? "—" : num(d.since_last_dose_s, 1) + " s"}</td><td class="${d.decision === "ACCEPT" ? "done" : "bad"}">${esc(d.decision === "ACCEPT" ? "ACCEPTED" : (GROUP_WORDS[d.group] || d.group))}</td></tr>`;
    h += `</tbody></table>`;
  }
  setHTML("ev-s2", h);
}

function renderAttacks(s, E) {
  const A = E.attacks.all, B = E.attacks.session;
  const KIND = [["replay", "Replayed (exact copy of a real command)", "S3"], ["stale", "Stale (real command, sent 5 s late)", "S3"],
    ["forged", "Forged (signed with a wrong key)", "C2"], ["unsigned", "Unsigned", "C2"], ["tampered", "Tampered (1 mL changed to 20 mL)", "C2"]];
  const sum = (T, ks, f) => ks.reduce((x, k) => x + T[k][f], 0);
  const s3s = sum(A, ["replay", "stale"], "sent"), s3b = sum(A, ["replay", "stale"], "blocked");
  const c2s = sum(A, ["forged", "unsigned", "tampered"], "sent"), c2b = sum(A, ["forged", "unsigned", "tampered"], "blocked");
  const reached = sum(A, Object.keys(A), "reached");
  let h = `<div class="note" style="margin-top:0">Every attack command goes over the network to the gateway on the Pi, like an intruder's would. S3: at least 99 % of replayed and stale commands rejected. C2: nothing without the operator's signature reaches the pumps. Run <code>bash fpr.sh attack</code> in Terminal and watch the Security monitor; the 2,000-command runs (<code>hmi.attack_station</code>) add to the same counts.</div>`;
  h += `<div class="ev-sum">${chip("S3 rejected", s3s ? `${s3b}/${s3s} (${num(100 * s3b / s3s, 1)} %)` : "—", s3s && s3b / s3s >= 0.99 ? "good" : "")}${chip("C2 blocked", c2s ? `${c2b}/${c2s}` : "—", c2s && c2b === c2s ? "good" : "")}${chip("Reached the pumps", reached, reached ? "bad" : "good")}</div>`;
  h += `<table class="ev-tbl"><thead><tr><th>Attack</th><th>Spec</th><th>Sent</th><th>Blocked</th><th>Reached the pumps</th><th>This session</th></tr></thead><tbody>`;
  for (const [k, lab, spec] of KIND) {
    const r = A[k], q = B[k];
    h += `<tr><td>${lab}</td><td>${spec}</td><td>${r.sent}</td><td>${r.blocked}${r.sent ? pf(r.blocked === r.sent) : ""}</td><td>${r.reached}</td><td>${q.blocked}/${q.sent}</td></tr>`;
  }
  h += `</tbody></table><div class="note">Counted from the gateway's own decisions; the attack tools tag their commands so real operator doses are never counted here. Every rejected command is in the audit log with its reason.</div>`;
  setHTML("ev-attacks", h);
}

function renderS4(s, E) {
  const m = E.model_a.all, ms = E.model_a.session;
  const ds = (s.decisions || []).filter((d) => d.model_a_label && d.model_a_label !== "NOT_CALLED");
  let k = `<div class="note" style="margin-top:0">S4: every dose request that reaches the AI Dose Guard gets a class (ACCEPTABLE / HARMFUL) and a risk score from the AI Dose Guard within 3 s. Times are measured on the Pi for each request.</div>`;
  k += `<div class="ev-sum">${chip("Doses classified", m.n)}${chip("Slowest", m.n ? num(m.max_ms, 1) + " ms" : "—", m.n && m.over_3s === 0 ? "good" : "")}${chip("Mean", m.n ? num(m.sum_ms / m.n, 1) + " ms" : "—")}${chip("Over 3 s", m.over_3s, m.over_3s ? "bad" : "good")}${chip("This session", `${ms.n} · slowest ${ms.n ? num(ms.max_ms, 1) : "—"} ms`)}</div>`;
  k += `<table style="margin-top:8px"><thead><tr><th>Received</th><th>Dose</th><th>Class</th><th>Score</th><th>AI Dose Guard</th><th>Gateway total</th><th>Decision</th></tr></thead><tbody>`;
  if (!ds.length) k += `<tr><td colspan="7" class="wait">Send a dose request to see its class and time.</td></tr>`;
  for (const d of ds) {
    k += `<tr><td>${hmsms(d.received_utc)}</td><td>${num(d.volume_ml, 1)} mL ${esc(CH_WORDS[d.channel_id] || d.channel_id)}</td>
      <td class="${d.model_a_label === "ACCEPTABLE_CONTEXT" ? "done" : "bad"}">${esc(d.model_a_label.replace("_CONTEXT", ""))}</td><td>${num(d.model_a_score, 2)}</td>
      <td>${num(d.model_a_latency_ms, 1)} ms</td><td>${num(d.station_ms, 1)} ms</td><td class="${d.decision === "ACCEPT" ? "done" : "bad"}">${esc(d.decision)}${d.decision === "REJECT" ? " · " + esc(d.reason_code) : ""}</td></tr>`;
  }
  k += `</tbody></table><div class="note">The 1,000-request timing run (ICS-AT-03) is <code>python -m model_a.latency_test</code>.</div>`;
  setHTML("ev-s4", k);
}

function renderC1(E) {
  let h = `<div class="note" style="margin-top:0">C1: only approved dilute acid and base, each at most 5 wt%. These four bottles are the only channels the gateway accepts; a command naming anything else is rejected as malformed.</div>`;
  h += `<table class="ev-tbl" style="margin-top:8px"><thead><tr><th>Pump</th><th>Bottle</th><th>Chemical</th><th>Strength</th><th>wt%</th><th>≤ 5 wt%</th></tr></thead><tbody>`;
  for (const b of E.bottles || []) h += `<tr><td>${b.pump}</td><td>${esc(b.words)}</td><td>${esc(b.chemical)}</td><td>${b.molarity} M</td><td>${num(b.wt_pct, 2)}</td><td>${b.pass ? `<span class="pass">PASS</span>` : `<span class="fail">FAIL</span>`}</td></tr>`;
  h += `</tbody></table><div class="note">wt% = mol/L × molar mass ÷ (10 × density). The labelled bottles and the lab approval are at the booth.</div>`;
  setHTML("ev-c1", h);
}

function renderActions(s) {
  const halted = s.mode === "HALTED";
  $("btn-halt").classList.toggle("hidden", halted);
  $("btn-resume").classList.toggle("hidden", !halted);
  $("btn-ack").disabled = !!s.alarm_acked;
  $("btn-ack").textContent = s.alarm_acked ? "ACKNOWLEDGED" : "ACKNOWLEDGE";
  $("action-note").textContent = halted
    ? "Dosing is halted. RESUME DOSING is the operator reset: the Uno must be talking and the E-stop released."
    : "HALT stops all dosing at once. Doses are allowed again only after RESUME.";
}

function renderDoseNow(s) {
  const p = s.pending, card = $("dose-now");
  card.classList.toggle("hidden", !p);
  if (!p) return;
  $("dose-instr").textContent = p.instruction || `Add ${num(p.ml, 1)} mL of ${p.words} now, then stir.`;
  const auto = s.ph.source === "SIM" && s.link.auto_pump;
  $("dose-meta").innerHTML = `Accepted by the gateway at ${hms(p.accepted_utc)} · from ${esc(p.sender)} · ${num(p.mmol, 3)} mmol · Uno light: ${esc(s.link.led_words)}.<br>` +
    (p.pump ? `The dose counts as added when the Uno reports the pump finished, with the mL it delivered. The 15 s mixing wait starts then. (Stopped after ${num(p.timeout_s, 0)} s.)`
      : auto ? "Simulator: the dose is added automatically." : `Press DOSE ADDED when it is in the tank. The 15 s mixing wait starts then. (Cancelled after ${num(p.timeout_s, 0)} s.)`);
  $("btn-added").classList.toggle("hidden", !!p.pump);
  $("btn-notadded").textContent = p.pump ? "STOP THE PUMP" : "Not added: cancel it";
  $("btn-added").dataset.cmd = p.command_id;
  $("btn-notadded").dataset.cmd = p.command_id;
}

function renderSafety(s) {
  const l = s.link, g = s.gateway;
  let h = kv("Command path", "gateway only (signed)");
  h += kv("Uno link", l.alive ? `talking (${num(l.line_age_s, 1)} s)` : "LOST: dosing blocked", l.alive ? "t-green" : "t-red");
  h += kv("Uno light", esc(l.led_words));
  h += kv("Mixing lockout", g.lockout_s > 0 ? `${num(g.lockout_s, 0)} s left` : "clear", g.lockout_s > 0 ? "t-amber" : "");
  h += kv(AI, s.model_a.loaded ? "on · can block, never approve" : `NOT LOADED (${esc(s.model_a.error)})`, s.model_a.loaded ? "" : "t-red");
  h += kv("Audit chain", g.chain_ok.ok ? `intact (${g.records})` : "BROKEN", g.chain_ok.ok ? "t-green" : "t-red");
  if (l.kind === "PROBE") h += kv("E-stop", l.estop ? "PRESSED" : "released", l.estop ? "t-red" : "");
  $("safety").innerHTML = h;
  const lock = g.lockout_s > 0 ? `Mixing: the next dose can be accepted in ${num(g.lockout_s, 0)} s.` : "";
  $("lockout").textContent = lock;
}

function renderCounters(s) {
  const c = s.gateway.counters || {};
  const order = ["ACCEPT", "REPLAY", "STALE", "LIMIT", "LOCKOUT", "MODEL_A_BLOCK", "AUTH", "SCHEMA", "STATE"];
  let h = `<span class="chip">All requests<b>${c.TOTAL || 0}</b></span>`;
  for (const k of order) {
    const n = c[k] || 0;
    if (!n && !["ACCEPT", "REPLAY", "STALE"].includes(k)) continue;
    h += `<span class="chip ${k === "ACCEPT" ? "good" : n ? "bad" : ""}">${GROUP_WORDS[k]}<b>${n}</b></span>`;
  }
  $("counters").innerHTML = h;
}

// ------------------------------------------------------------------ security monitor (FPR)
const SEC_CYBER = [["REPLAY", "Replayed"], ["STALE", "Stale"], ["AUTH", "Forged / unsigned"], ["SCHEMA", "Malformed"]];
const SEC_SAFETY = [["LIMIT", "Over 20 mL"], ["LOCKOUT", "Mixing wait"], ["MODEL_A_BLOCK", AI]];
let secPrev = null;
const secHits = [];              // [time ms, group, how many]
const secHitUntil = {};
function renderSecMon(s) {
  const c = s.gateway.counters || {};
  const now = Date.now();
  if (secPrev) {
    for (const [k] of SEC_CYBER.concat(SEC_SAFETY)) {
      const d = (c[k] || 0) - (secPrev[k] || 0);
      if (d > 0) { secHits.push([now, k, d]); secHitUntil[k] = now + 6000; }
    }
  }
  secPrev = Object.assign({}, c);
  while (secHits.length && now - secHits[0][0] > 10000) secHits.shift();
  const recent = (k) => secHits.filter((h) => h[1] === k).reduce((a, h) => a + h[2], 0);
  const tile = ([k, lab]) => {
    const n = c[k] || 0, r = recent(k);
    return `<div class="tile ${n ? "on" : ""} ${secHitUntil[k] > now ? "hit" : ""}"><div class="tl">${lab}</div>` +
      `<div class="tn">${n}</div>${r ? `<div class="td">+${r}</div>` : ""}</div>`;
  };
  // re-render only when something changed, so a running flash animation is not restarted
  const cyber = SEC_CYBER.map(tile).join(""), safety = SEC_SAFETY.map(tile).join("");
  if ($("secmon-cyber").innerHTML !== cyber) $("secmon-cyber").innerHTML = cyber;
  if ($("secmon-safety").innerHTML !== safety) $("secmon-safety").innerHTML = safety;
  const cyberRecent = SEC_CYBER.reduce((a, [k]) => a + recent(k), 0);
  const blocked = SEC_CYBER.reduce((a, [k]) => a + (c[k] || 0), 0);
  $("secmon").classList.toggle("alert", cyberRecent > 0);
  $("secmon-title").textContent = cyberRecent > 0 ? `\u26A0 ATTACK DETECTED: ${cyberRecent} commands blocked in the last 10 s`
    : "SECURITY MONITOR";
  $("secmon-sub").textContent = cyberRecent > 0 ? "Blocked by the gateway on the Pi. None reached the pumps."
    : blocked ? `${blocked} attack commands blocked so far. None reached the pumps.`
    : "Every command passes the gateway on the Pi. Rejected commands never reach the pumps.";
}

function renderEngineer(s) {
  if (s.sim && !simFilled) {
    $("sim-scenario").innerHTML = s.sim.scenarios.map((n) => `<option ${n === "acid_upset_max" ? "selected" : ""}>${esc(n)}</option>`).join("");
    simFilled = true;
  }
  if (document.activeElement !== $("sim-autopump")) $("sim-autopump").checked = !!s.link.auto_pump;
  if (document.activeElement !== $("auto-rec")) $("auto-rec").checked = !!s.auto_recovery;
  const l = s.link;
  $("link-info").innerHTML = `pH source: ${esc(l.kind)}${l.port ? " on " + esc(l.port) : ""}. Station ${esc(s.station)}. Key: ${esc(s.key_source)}.` +
    (l.error ? ` <span class="bad">${esc(l.error)}</span>` : "") +
    (l.tail && l.tail.length ? `<br>Last Uno lines: <code>${esc(l.tail.join(" | "))}</code>` : "");
}

function reportShown(s) {
  const ev = s.event;
  if (!ev || shownEvents.has(ev.id)) return;
  if (!["RECOVERY", "ESCALATE", "HALTED"].includes(s.mode)) return;
  shownEvents.add(ev.id);
  // report once the browser has painted the banner (next animation frame, then a task);
  // a hidden tab paints nothing, so then wait until the operator can actually see it
  let sent = false;
  const send = () => { if (!sent) { sent = true; api("/api/action", {action: "HMI_SHOWN", args: {event_id: ev.id}}); } };
  const afterPaint = () => requestAnimationFrame(() => setTimeout(send, 0));
  if (document.visibilityState === "visible") afterPaint();
  else document.addEventListener("visibilitychange", function once() {
    if (document.visibilityState === "visible") { document.removeEventListener("visibilitychange", once); afterPaint(); }
  });
}

function renderLog(recs) {
  let h = "";
  for (const r of recs) {
    const dec = r.decision === "REJECT" ? `<span class="rej">REJECT</span>` : r.decision === "ACCEPT" ? `<span class="acc2">ACCEPT</span>` : `<span class="evt">event</span>`;
    const reason = r.decision === "EVENT" ? `<span class="evt">${esc(r.reason_code)}</span>` :
      `<span class="${r.decision === "REJECT" ? "rej" : "acc2"}">${esc(r.decision === "REJECT" ? (GROUP_WORDS[r.group] || r.group) : "ACCEPTED")}</span>`;
    let msg = esc(r.message || "");
    if (r.decision === "REJECT") msg += `<br><span class="evt">${esc(r.reason_code)}: ${esc(r.words)}</span>`;
    if (r.model_a_label && r.model_a_label !== "NOT_CALLED") msg += `<br><span class="evt">${AI}: ${esc(r.model_a_label.replace("_CONTEXT", ""))} · ${num(r.model_a_score, 2)}</span>`;
    h += `<tr><td>${hms(r.timestamp_utc)}</td><td class="src">${esc(r.source)}</td><td class="msg">${msg}</td><td>${dec}</td><td>${reason}</td><td>${esc(r.hash_short)}</td></tr>`;
  }
  if (!recs.length) h = `<tr><td colspan="6" class="wait">${logOnly === "rejected" ? "No rejected commands yet." : "Empty."}</td></tr>`;
  $("log-body").innerHTML = h;
}

// ------------------------------------------------------------------ actions
function showReply(r) {
  const el = $("dose-reply");
  el.classList.remove("hidden");
  if (r.decision === "ACCEPT") {
    el.className = "reply acc";
    el.innerHTML = `<b>Accepted</b> by the gateway. Add the dose when the Dose now box asks.
      <span class="sm">${AI}: ${esc((r.model_a_label || "").replace("_CONTEXT", ""))} · risk ${num(r.model_a_score, 2)} · ${num(r.model_a_latency_ms, 1)} ms · ${num(r.dose_mmol, 3)} mmol</span>`;
  } else if (r.decision === "REJECT") {
    el.className = "reply rej";
    const g = GROUP_WORDS[r.group] || r.group;
    let extra = "";
    if (r.model_a_label && r.model_a_label !== "NOT_CALLED") extra = `<span class="sm">${AI}: ${esc(r.model_a_label.replace("_CONTEXT", ""))} · risk ${num(r.model_a_score, 2)} · ${num(r.model_a_latency_ms, 1)} ms${r.model_a_reason ? " · " + esc(r.model_a_reason) : ""}</span>`;
    el.innerHTML = `<b>Rejected — ${esc(g)}</b> <b class="code">(${esc(r.reason_code)})</b><br>${esc(r.words)}${extra}`;
  } else {
    el.className = "reply info";
    el.textContent = String(r.words || r.error || "Not sent.").replace(/Model A/g, AI);
  }
}

$("btn-dose").onclick = async () => {
  const btn = $("btn-dose");
  btn.disabled = true;
  try {
    const r = await api("/api/dose", {channel_id: $("dose-ch").value, volume_ml: $("dose-ml").value});
    showReply(r);
  } catch (e) { showReply({decision: "NOT_SENT", words: "Could not reach the HMI server."}); }
  btn.disabled = false;
  poll(); pollAudit(true);
};
$("btn-halt").onclick = () => act("HALT");
$("btn-resume").onclick = async () => { const r = await act("RESUME"); if (r && r.ok === false) alert(r.error); };
$("btn-ack").onclick = () => act("ACK");
$("btn-added").onclick = (e) => act("DOSE_ADDED", {command_id: e.currentTarget.dataset.cmd});
$("btn-notadded").onclick = (e) => act("DOSE_CANCEL", {command_id: e.currentTarget.dataset.cmd});
$("btn-verify").onclick = async () => {
  const r = await api("/api/verify");
  $("verify-out").innerHTML = r.ok ? `<span class="pass">CHAIN OK</span> (${r.records} records)` : `<span class="fail">CHAIN BROKEN</span>`;
};
for (const t of document.querySelectorAll("#log-tabs .tab")) {
  t.onclick = () => {
    logOnly = t.dataset.only;
    document.querySelectorAll("#log-tabs .tab").forEach((x) => x.classList.toggle("on", x === t));
    pollAudit(true);
  };
}
for (const t of document.querySelectorAll("#ev-tabs .tab")) {
  t.onclick = () => {
    evTab = t.dataset.tab;
    try { localStorage.setItem("evTab", evTab); } catch (e) { /* fine */ }
    document.querySelectorAll("#ev-tabs .tab").forEach((x) => x.classList.toggle("on", x === t));
    for (const k of EV_TABS) $("ev-" + k).classList.toggle("hidden", k !== evTab);
  };
}
// demo panel buttons (the tabs re-render, so one listener on the panel)
$("demo").addEventListener("click", async (e) => {
  const b = e.target.closest("[data-act]");
  if (!b || b.disabled) return;
  const a = b.dataset.act;
  if (a === "hold-start") act("HOLD_START");
  else if (a === "hold-stop") act("HOLD_STOP");
  else if (a === "use-sugg" && S && S.hold && S.hold.suggestion) { $("dose-ch").value = S.hold.suggestion.channel_id; $("dose-ml").value = S.hold.suggestion.ml; $("dose-ml").focus(); }
  else if (a === "run-out") {
    const why = prompt("Why leave this run out of the statistics? (goes in the audit log)", "rehearsal");
    if (why !== null) act("RUN_INCLUDE", {key: b.dataset.key, included: false, why});
  } else if (a === "run-in") act("RUN_INCLUDE", {key: b.dataset.key, included: true});
  else if (a === "s2-cap" || a === "s2-lock") {
    if (a === "s2-lock" && !(S && S.gateway.lockout_s >= 2 && !S.pending)) return;
    b.disabled = true;
    const req = a === "s2-cap" ? {channel_id: "BASE_FINE", volume_ml: 25} : {channel_id: "BASE_FINE", volume_ml: 1};
    let r;
    try { r = await api("/api/dose", req); } catch (err) { r = {decision: "NOT_SENT", words: "Could not reach the HMI server."}; }
    const g = GROUP_WORDS[r.group] || r.group || "";
    s2Reply = `<div class="reply ${r.decision === "REJECT" ? "rej" : r.decision === "ACCEPT" ? "acc" : "info"}"><b>${esc(req.volume_ml)} mL request: ${esc(r.decision === "REJECT" ? "Rejected — " + g : r.decision === "ACCEPT" ? "Accepted" : "Not sent")}</b>${r.reason_code ? ` <b class="code">(${esc(r.reason_code)})</b>` : ""}<br>${esc(r.words || "")}</div>`;
    poll(); pollAudit(true);
  }
});
$("btn-ev-reset").onclick = async () => {
  if (!confirm("Start a fresh evidence record? The current one is kept as a file on the Pi, but the Demo panel starts from zero.")) return;
  const r = await act("EVIDENCE_RESET");
  alert(r && r.ok ? `Fresh record started. The old one is kept as ${r.kept}.` : (r && r.error) || "failed");
};
// engineer panel
const simOut = (r) => { $("sim-out").textContent = r && r.ok === false ? r.error : "Done."; };
$("btn-sim-scn").onclick = () => act("SIM_UPSET", {scenario: $("sim-scenario").value}).then(simOut);
$("btn-sim-upset").onclick = () => act("SIM_UPSET", {ml: parseFloat($("sim-ml").value), acid: $("sim-acid").value === "1"}).then(simOut);
$("btn-sim-setph").onclick = () => act("SIM_SET_PH", {ph: parseFloat($("sim-ph").value)}).then(simOut);
$("btn-sim-reset").onclick = () => act("SIM_RESET", {start_ph: 7.0}).then(simOut);
$("sim-autopump").onchange = (e) => act("SIM_AUTOPUMP", {on: e.target.checked}).then(simOut);
$("btn-sim-unplug").onclick = () => act("SIM_UNPLUG", {seconds: 8}).then(simOut);
$("auto-rec").onchange = (e) => act("AUTO_RECOVERY", {on: e.target.checked});
const testOut = (r) => {
  const g = GROUP_WORDS[r.group] || r.group || "";
  $("test-out").innerHTML = r.decision ? `Gateway: <b>${esc(r.decision)}</b> ${r.reason_code ? "· " + esc(g) + " (" + esc(r.reason_code) + ")" : ""}${r.http_status ? " · HTTP " + r.http_status : ""}<br>${esc(r.words || "")}` : esc(r.words || "");
  poll(); pollAudit(true);
};
for (const k of ["replay", "stale", "unsigned", "forged"]) $("t-" + k).onclick = () => api("/api/test/" + k, {}).then(testOut);

setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString([], {hour12: false}); }, 500);
poll();
// the demo panel remembers whether it was open (per browser)
try {
  if (localStorage.getItem("demoOpen") === "1") $("demo").open = true;
  const t0 = localStorage.getItem("evTab");
  if (t0 && EV_TABS.includes(t0)) document.querySelector(`#ev-tabs .tab[data-tab="${t0}"]`).click();
  $("demo").addEventListener("toggle", () => { try { localStorage.setItem("demoOpen", $("demo").open ? "1" : "0"); } catch (e) {} });
} catch (e) { /* storage blocked: stays closed */ }
setInterval(poll, 250);
setInterval(() => pollAudit(false), 1500);
