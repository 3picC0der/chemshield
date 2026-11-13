"""A browser control panel for the Uno: prime, check and calibrate the pumps and calibrate
the pH probe with buttons instead of typing commands.

It works with either sketch and shows what that sketch can do:
- `pump_bench_test`: prime and check by steps, calibrate a pump by weighing 4000 steps.
- `chemshield_uno` (the station firmware): pH calibration with buffers, pumps by mL (check
  doses, priming, correcting a pump's calibration from a weighed dose), E-stop state. The
  panel sends the heartbeat the station would, so the Uno accepts doses.

Only one program can hold the serial port: stop the station (and close any Serial Monitor)
first. On the computer the Uno is plugged into, from the repo root:

    ../chemshield/.venv/bin/python firmware/uno/bench_panel.py          (Mac)
    .venv/bin/python firmware/uno/bench_panel.py --port /dev/ttyACM0    (Pi)

then open http://127.0.0.1:8090 (it only listens on that computer). With the Uno on the Pi,
`firmware/uno/panel_on_pi.sh` on the Mac starts it there and opens it through SSH.

Every button becomes one of the sketch's own commands, run one at a time: the next run
starts only after the Uno answers. STOP sends STOP at once and drops anything queued.
Weighings go to firmware/uno/bench_logs/<date>.csv (bench) and <date>_station.csv (doses),
reloaded on a restart; a bad one can be removed (the CSV keeps it, marked "removed").
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import queue
import re
import statistics
import sys
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PUMPS = {1: ("ACID_BULK", "right, outer"), 2: ("ACID_FINE", "right, next to the tank"),
         3: ("BASE_BULK", "left, outer"), 4: ("BASE_FINE", "left, next to the tank")}
CHANNEL_PUMP = {c: p for p, (c, _) in PUMPS.items()}
PRIME_STEPS, CAL_STEPS, CHECK_STEPS = 2000, 4000, 400       # 10 turns, 20 turns, 2 turns
RUN_RATE, CHECK_RATE = 800, 200                             # full steps/s: 4 turns/s, 1 turn/s
PRIME_ML, CHECK_ML, CAL_ML = 10.0, 10.0, 20.0               # station doses (20 mL is its cap)
PAUSE_S = 5                                                 # between repeated runs
STEADY_MV = 3.0                                             # pH: 10 s within this = steady
BENCH_RAW = re.compile(r"^(STEPS [1-4] -?\d{1,6}|SECS [1-4] \d{1,3}(\.\d+)?|RATE \d{2,4}"
                       r"|ACCEL \d{2,5}|MIX \d{1,3}|STOP|INFO)$")
STATION_RAW = re.compile(r"^(MIX,\d{1,3}|STOP|STATUS|V|CAL,SHOW|PCAL,SHOW)$")
LOG_DIR = Path(__file__).resolve().parent / "bench_logs"


class Bench:
    """Owns the serial port: a reader thread logs every line, a worker sends queued jobs.
    In station mode a third thread sends the heartbeat and polls the probe voltage."""

    def __init__(self, port: str):
        import serial                                          # pyserial
        self.ser = serial.Serial(port, 115200, timeout=0.1)
        self.port = port
        self.firmware: str | None = None                       # "bench" or "station"
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self.wlock = threading.Lock()
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.ended = threading.Event()                         # the current run has ended
        self.last_end = ""
        self.primes = {p: 0 for p in PUMPS}
        self.estop: bool | None = None
        self.ph: float | None = None
        self.volts: deque = deque(maxlen=10)                   # last 10 one-second means
        self.cal_lines: list[str] = []
        self.pcal: dict[int, float] = {}
        self.seq = 1000
        self.last_ml: dict[int, float] = {}                    # station: last dose per pump
        self.refresh_at = 0.0                                  # station: ask STATUS/CAL/PCAL then
        self.weighings = self._load(self._csv_path("bench"))
        self.doses = self._load(self._csv_path("station"))
        for fn in (self._read, self._work, self._station_loop):
            threading.Thread(target=fn, daemon=True).start()
        self._log("#", f"opened {port}; the Uno restarts now")

    # ---------------------------------------------------------------- serial
    def _log(self, kind: str, text: str) -> None:
        with self.lock:
            self.lines.append(f"{datetime.now():%H:%M:%S} {kind} {text}")

    def write(self, cmd: str, log: bool = True) -> None:
        with self.wlock:
            self.ser.write((cmd + "\n").encode())
        if log:
            self._log(">", cmd)

    def _read(self) -> None:
        buf = b""
        while True:
            buf += self.ser.read(256)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                self._line(raw.decode(errors="replace").strip())

    def _line(self, line: str) -> None:
        if not line:
            return
        f = line.split(",")
        if line.startswith("READY"):
            self.firmware = "bench" if "bench" in line else "station"
            self.cal_lines, self.pcal = [], {}
            self.refresh_at = time.time() + 2.5
        if f[0] == "PH" and len(f) > 1:                        # once a second: keep, don't log
            self.ph = _num(f[1])
            return
        if f[0] == "V" and len(f) > 2:
            v = _num(f[1])
            if v is not None:
                self.volts.append(v)
            return
        if f[0] == "SPEED":
            return
        if f[0] == "STATUS" and len(f) > 1:
            self.estop = f[1] == "1"
        if line.startswith("INFO,rate") and "estop," in line:
            self.estop = line.rsplit(",", 1)[1].upper() == "PRESSED"
        if f[0] == "CAL" and len(f) > 1 and f[1] in ("FIT", "ACID", "NEUTRAL", "BASE"):
            self.cal_lines = [c for c in self.cal_lines if not c.startswith(f"CAL,{f[1]},")] + [line]
        if f[0] == "PCAL" and len(f) > 3 and f[1].isdigit():
            self.pcal[int(f[1])] = _num(f[3]) or 0.0
        self._log("<", line)
        if f[0] in ("DONE", "STOPPED", "ERROR", "ABORT", "REJECT"):
            self.last_end = line
            self.ended.set()

    def _station_loop(self) -> None:
        """Heartbeat every 0.5 s (the station stops pumps and mixer without it) and a probe
        voltage every second, but only while the station firmware is on the Uno."""
        n = 0
        while True:
            time.sleep(0.5)
            if self.firmware != "station":
                continue
            self.write("HB", log=False)
            n += 1
            if n % 2 == 0:
                self.write("V", log=False)
            if self.refresh_at and time.time() >= self.refresh_at:   # once after each restart
                self.refresh_at = 0.0
                for cmd in ("STATUS", "CAL,SHOW", "PCAL,SHOW"):
                    self.write(cmd)

    # ---------------------------------------------------------------- jobs
    def _work(self) -> None:
        while True:
            label, steps = self.jobs.get()
            self.busy, self.cancel = True, threading.Event()
            self._log("#", f"start: {label}")
            for kind, value in steps:
                if self.cancel.is_set():
                    break
                if kind == "send":
                    self.write(value)
                    time.sleep(0.2)
                elif kind == "run":                            # send, wait for its end line
                    self.ended.clear()
                    self.write(value)
                    if not self.ended.wait(130):
                        self.write("STOP")
                        self._log("#", "no answer in 130 s: sent STOP")
                        break
                    if self.last_end.startswith(("REJECT", "ABORT", "ERROR")):
                        self._log("#", "stopped here: the Uno did not finish that run")
                        break
                elif kind == "pause":
                    self.cancel.wait(value)
                elif kind == "count":
                    self.primes[value] += 1
                elif kind == "lastml":
                    self.last_ml[value[0]] = value[1]
            self._log("#", f"end: {label}")
            self.busy = False

    def running(self) -> bool:
        return self.busy or not self.jobs.empty()

    def submit(self, label: str, steps: list) -> None:
        self.jobs.put((label, steps))

    def stop(self) -> None:
        while not self.jobs.empty():
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        self.cancel.set()
        self.write("STOP")
        self.write("MIX,0" if self.firmware == "station" else "MIX 0")

    def next_seq(self) -> int:
        self.seq += 1
        return self.seq

    def plan(self, action: str, pump: int, n: float) -> tuple[str, list]:
        ch = PUMPS[pump][0]
        if self.firmware == "station":
            def dose(ml):
                return [("run", f"PUMP,{self.next_seq()},{ch},{ml:.3f}"), ("lastml", (pump, ml))]
            if action == "check":
                return f"pump {pump}: {CHECK_ML:g} mL check dose", dose(CHECK_ML)
            if action == "prime":
                steps: list = []
                for i in range(int(n)):
                    steps += dose(PRIME_ML) + [("count", pump)]
                    if i < n - 1:
                        steps.append(("pause", PAUSE_S))
                return f"prime pump {pump} x{int(n)} ({PRIME_ML:g} mL each)", steps
            if action == "cal":
                return f"pump {pump}: {CAL_ML:g} mL calibration dose", dose(CAL_ML)
            if action == "ml":
                return f"pump {pump}: {n:g} mL", dose(n)
            raise ValueError(f"{action} is not available with the station firmware")
        if action == "check":
            return f"check pump {pump} (2 turns at 1 turn/s)", [
                ("send", f"RATE {CHECK_RATE}"), ("run", f"STEPS {pump} {CHECK_STEPS}")]
        if action == "prime":
            steps = [("send", f"RATE {RUN_RATE}")]
            for i in range(int(n)):
                steps += [("run", f"STEPS {pump} {PRIME_STEPS}"), ("count", pump)]
                if i < n - 1:
                    steps.append(("pause", PAUSE_S))
            return f"prime pump {pump} x{int(n)} (10 turns each)", steps
        if action == "cal":
            return f"cal pump {pump} ({CAL_STEPS} full steps)", [
                ("send", f"RATE {RUN_RATE}"), ("run", f"STEPS {pump} {CAL_STEPS}")]
        if action == "steps":
            return f"pump {pump}: {int(n)} full steps", [
                ("send", f"RATE {RUN_RATE}"), ("run", f"STEPS {pump} {int(n)}")]
        raise ValueError(f"{action} is not available with the bench sketch")

    # ---------------------------------------------------------------- pH
    def ph_state(self) -> dict:
        v = list(self.volts)
        spread = (max(v) - min(v)) * 1000 if len(v) > 1 else None
        return {"ph": self.ph, "volts": v[-1] if v else None, "n": len(v),
                "spread_mv": None if spread is None else round(spread, 1),
                "steady": len(v) == 10 and spread is not None and spread <= STEADY_MV,
                "cal": self.cal_lines}

    def ph_cal(self, buffer_ph: float) -> None:
        self.write(f"CAL,{buffer_ph:.2f}")

    # ---------------------------------------------------------------- weighings
    @staticmethod
    def _csv_path(kind: str) -> Path:
        return LOG_DIR / f"{datetime.now():%Y-%m-%d}{'' if kind == 'bench' else '_station'}.csv"

    @staticmethod
    def _load(path: Path) -> list[dict]:
        if not path.exists():
            return []
        with path.open(newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            r["pump"] = int(r["pump"])
            for k in ("full_steps", "grams", "steps_per_ml", "ml", "old_steps_per_ml"):
                if r.get(k) not in (None, ""):
                    r[k] = float(r[k])
            r["status"] = r.get("status") or "kept"
        return rows

    def _save(self, kind: str) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        rows = self.weighings if kind == "bench" else self.doses
        fields = (["time", "pump", "channel", "full_steps", "grams", "steps_per_ml", "status"]
                  if kind == "bench" else
                  ["time", "pump", "channel", "ml", "grams", "old_steps_per_ml", "status"])
        with self._csv_path(kind).open("w", newline="") as f:
            out = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            out.writeheader()
            out.writerows(rows)

    def weigh(self, pump: int, grams: float, ml: float | None) -> None:
        now = f"{datetime.now():%Y-%m-%d %H:%M:%S}"
        if self.firmware == "station":
            ml = ml or self.last_ml.get(pump)
            if not ml:
                raise ValueError("dose this pump first: the grams are compared with its last dose")
            self.doses.append({"time": now, "pump": pump, "channel": PUMPS[pump][0], "ml": ml,
                               "grams": grams, "old_steps_per_ml": self.pcal.get(pump, 0.0),
                               "status": "kept"})
            self._save("station")
            self._log("#", f"weighed pump {pump}: {ml:g} mL asked, {grams} g delivered "
                           f"({(grams / ml - 1) * 100:+.1f} %)")
        else:
            w = {"time": now, "pump": pump, "channel": PUMPS[pump][0], "full_steps": CAL_STEPS,
                 "grams": grams, "steps_per_ml": round(CAL_STEPS / grams, 2), "status": "kept"}
            self.weighings.append(w)
            self._save("bench")
            self._log("#", f"weighed pump {pump}: {grams} g -> {w['steps_per_ml']} full steps/mL")

    def remove(self, pump: int, index: int | None) -> None:
        kind = "station" if self.firmware == "station" else "bench"
        rows = self.doses if kind == "station" else self.weighings
        kept = [w for w in rows if w["pump"] == pump and w["status"] == "kept"]
        for w in (kept if index is None else kept[index:index + 1]):
            w["status"] = "removed"
            self._log("#", f"removed pump {pump} weighing {w['grams']} g ({w['time']})")
        self._save(kind)

    def summary(self) -> dict:
        out = {}
        for p in PUMPS:
            if self.firmware == "station":
                kept = [w for w in self.doses if w["pump"] == p and w["status"] == "kept"]
                if kept:
                    ratios = [w["grams"] / w["ml"] for w in kept]
                    err = (statistics.mean(ratios) - 1) * 100
                    now = self.pcal.get(p)
                    out[p] = {"n": len(kept), "grams": [w["grams"] for w in kept],
                              "asked": [w["ml"] for w in kept], "error_pct": round(err, 2),
                              "spread_pct": round((max(ratios) - min(ratios)) * 100, 2),
                              "now": now,
                              "suggested": round(now / statistics.mean(ratios), 2) if now else None}
            else:
                kept = [w for w in self.weighings if w["pump"] == p and w["status"] == "kept"]
                vals = [w["steps_per_ml"] for w in kept]
                if vals:
                    mean = statistics.mean(vals)
                    spread = (max(vals) - min(vals)) / mean * 100 if len(vals) > 1 else 0.0
                    out[p] = {"n": len(vals), "mean": round(mean, 2), "spread_pct": round(spread, 2),
                              "grams": [w["grams"] for w in kept]}
        return out

    def apply(self, pump: int) -> str:
        """Station: store the suggested steps per mL for a pump from its kept check doses, then
        mark those doses as applied (they were measured with the old value)."""
        s = self.summary().get(pump)
        if self.firmware != "station" or not s or not s["suggested"]:
            raise ValueError("weigh at least one dose of this pump first")
        self.write(f"PCAL,{pump},{s['suggested']:.3f}")
        for w in self.doses:
            if w["pump"] == pump and w["status"] == "kept":
                w["status"] = "applied"
        self._save("station")
        self._log("#", f"pump {pump}: calibration {s['now']} -> {s['suggested']} full steps/mL")
        return f"stored {s['suggested']}"


def _num(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        return None


PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Uno panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#f6f6f4;color:#222}
h1{font-size:20px;margin:0 0 4px} .sub{color:#555;margin-bottom:12px}
.stop{background:#c62828;color:#fff;font-size:22px;font-weight:700;border:0;border-radius:10px;
 padding:14px 28px;cursor:pointer;position:sticky;top:8px;z-index:2}
.row{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;width:270px}
.card h2{font-size:16px;margin:0} .where{color:#666;font-size:13px;margin-bottom:8px}
button{font-size:14px;padding:7px 10px;margin:3px 2px;border-radius:7px;border:1px solid #aaa;
 background:#fafafa;cursor:pointer} button:disabled{opacity:.4;cursor:default}
input{width:70px;font-size:14px;padding:5px} .busy{color:#b26a00;font-weight:600}
.big{font-size:40px;font-weight:700} .ok{color:#2e7d32;font-weight:600} .warn{color:#b26a00;font-weight:600}
.bad{color:#c62828;font-weight:700} .hide{display:none}
#log{background:#111;color:#cfc;font:12px/1.4 ui-monospace,monospace;height:240px;overflow:auto;
 padding:8px;border-radius:8px;white-space:pre-wrap} table{border-collapse:collapse;font-size:13px}
td,th{border:1px solid #ddd;padding:3px 8px;text-align:right} a.w{color:#1a5fb4;text-decoration:none;margin-right:6px}
</style></head><body>
<h1>Uno panel</h1>
<div class="sub">Uno on <b id="port"></b> &middot; firmware: <b id="fw">waiting for the Uno...</b> &middot;
 E-stop: <span id="estop">?</span> &middot; status: <span id="state">idle</span></div>
<button class="stop" onclick="post('/stop')">STOP</button>

<div id="phbox" class="row hide">
 <div class="card" style="width:auto;min-width:280px"><h2>pH probe</h2>
  <div class="where">live reading (updates every second)</div>
  <div class="big" id="ph">-</div><div id="volts">-</div><div id="steady">-</div></div>
 <div class="card" style="width:auto"><h2>pH calibration</h2>
  <div class="where">1. rinse, dab dry, probe in the buffer &middot; 2. wait for <span class="ok">steady</span> &middot;
   3. press Store. Use the value printed on the bottle.</div>
  <div>buffer <input id="b1" value="4.01"> <button onclick="cal('b1')">Store</button></div>
  <div>buffer <input id="b2" value="7.00"> <button onclick="cal('b2')">Store</button></div>
  <div>buffer <input id="b3" value="10.01"> <button onclick="cal('b3')">Store</button></div>
  <div style="margin-top:6px"><button onclick="raw('CAL,SHOW')">Show stored</button>
   <button onclick="if(confirm('Clear ALL stored pH calibration points?')) post('/phclear')">Clear pH calibration</button></div>
  <pre id="calv" style="font-size:12px;margin:6px 0 0"></pre></div>
</div>

<div class="row" id="cards"></div>
<div class="row">
 <div class="card"><h2>Mixer</h2><div class="where">L298N, 0-255</div>
  <button onclick="mix(100)">On (100)</button><button onclick="mix(180)">Dose speed (180)</button>
  <button onclick="mix(0)">Off</button></div>
 <div class="card" id="infocard"><h2>Uno</h2><div class="where">settings and stored calibration</div>
  <button onclick="info()">Show</button></div>
 <div class="card" style="width:auto"><h2 id="calt">Pump calibration (weighed)</h2><div class="where" id="calh"></div>
  <table id="cal"></table></div>
</div>
<div id="log"></div>
<script>
const P={1:["ACID_BULK","right, outer"],2:["ACID_FINE","right, next to the tank"],
 3:["BASE_BULK","left, outer"],4:["BASE_FINE","left, next to the tank"]};
let since=0, fw=null;
function benchCard(p){return `<div class="card"><h2>Pump ${p}: ${P[p][0]}</h2><div class="where">${P[p][1]} &middot; primes this session: <b id="pc${p}">0</b></div>
 <button class="go" onclick="act('check',${p})">Check (2 turns)</button>
 <button class="go" onclick="act('prime',${p},1)">Prime x1</button>
 <button class="go" onclick="act('prime',${p},3)">Prime x3</button>
 <button class="go" onclick="act('prime',${p},14)">Prime x14</button><br>
 <button class="go" onclick="act('cal',${p})">Cal 4000 steps</button>
 grams <input id="g${p}" type="number" step="0.01"><button onclick="weigh(${p})">Save</button><br>
 <input id="s${p}" type="number" placeholder="steps"><button class="go" onclick="act('steps',${p},+document.getElementById('s${p}').value)">Run steps</button></div>`}
function stationCard(p){return `<div class="card"><h2>Pump ${p}: ${P[p][0]}</h2><div class="where">${P[p][1]} &middot; <span id="spm${p}"></span> &middot; primes: <b id="pc${p}">0</b></div>
 <button class="go" onclick="act('check',${p})">Dose 10 mL</button>
 <button class="go" onclick="act('cal',${p})">Dose 20 mL</button>
 <button class="go" onclick="act('prime',${p},14)">Prime x14 (10 mL each)</button><br>
 grams <input id="g${p}" type="number" step="0.01"> from the last dose (<b id="lm${p}">-</b> mL)
 <button onclick="weigh(${p})">Save</button><br>
 <input id="s${p}" type="number" placeholder="mL" step="0.1"><button class="go" onclick="act('ml',${p},+document.getElementById('s${p}').value)">Dose mL</button></div>`}
function build(){document.getElementById('cards').innerHTML=[1,2,3,4].map(fw==='station'?stationCard:benchCard).join('');
 document.getElementById('phbox').className=fw==='station'?'row':'row hide';
 document.getElementById('calt').textContent=fw==='station'?'Pump check doses (weighed)':'Pump calibration (weighed)';
 document.getElementById('calh').innerHTML=fw==='station'
  ?'tare, dose, type the grams and Save (compared with that pump\'s last dose). Apply stores the corrected steps per mL. Click a weighing to remove it.'
  :'full steps per mL = 4000 / grams &middot; click a weighing to remove it';}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
 const j=await r.json(); if(j.error) alert(j.error); else if(j.msg) alert(j.msg); poll();}
function act(a,p,n){post('/job',{action:a,pump:p,n:n||1})}
function raw(c){post('/raw',{cmd:c})}
function mix(v){raw(fw==='station'?'MIX,'+v:'MIX '+v)}
function info(){raw(fw==='station'?'PCAL,SHOW':'INFO')}
function cal(id){const v=+document.getElementById(id).value; if(!(v>=1&&v<=13)) return alert('buffer pH 1-13');
 const s=document.getElementById('steady').textContent; if(!s.startsWith('steady') && !confirm('The reading is not steady yet. Store anyway?')) return;
 post('/phcal',{ph:v});}
function weigh(p){const g=+document.getElementById('g'+p).value; if(!(g>0)) return alert('type the grams first');
 post('/weigh',{pump:p,grams:g}); document.getElementById('g'+p).value='';}
function rm(p,i){const what=i===undefined?`ALL weighings of pump ${p}`:`this weighing of pump ${p}`;
 if(confirm(`Remove ${what}? (It stays in the CSV, marked removed.)`)) post('/remove',{pump:p,index:i===undefined?null:i});}
function apply(p,v){if(confirm(`Store ${v} full steps per mL for pump ${p}?`)) post('/apply',{pump:p});}
async function poll(){const j=await (await fetch('/state?since='+since)).json();
 document.getElementById('port').textContent=j.port;
 if(j.firmware!==fw){fw=j.firmware; document.getElementById('fw').textContent=fw==='station'?'chemshield_uno (station)':fw==='bench'?'pump_bench_test (bench)':'waiting for the Uno...'; build();}
 const e=document.getElementById('estop'); e.textContent=j.estop===null?'?':j.estop?'PRESSED':'released'; e.className=j.estop?'bad':'ok';
 const s=document.getElementById('state'); s.textContent=j.busy?'RUNNING':'idle'; s.className=j.busy?'busy':'';
 document.querySelectorAll('.go').forEach(b=>b.disabled=j.busy);
 for(const p in j.primes){const el=document.getElementById('pc'+p); if(el) el.textContent=j.primes[p];}
 for(const p in j.last_ml){const el=document.getElementById('lm'+p); if(el) el.textContent=j.last_ml[p];}
 for(const p in j.pcal){const el=document.getElementById('spm'+p); if(el) el.textContent=j.pcal[p]+' steps/mL';}
 if(fw==='station'){const h=j.ph;
  document.getElementById('ph').textContent=h.ph===null?'-':'pH '+h.ph.toFixed(2);
  document.getElementById('volts').textContent=h.volts===null?'-':h.volts.toFixed(4)+' V';
  const st=document.getElementById('steady');
  if(h.steady){st.textContent='steady (10 s within '+h.spread_mv+' mV)'; st.className='ok';}
  else{st.textContent='settling: '+(h.spread_mv===null?'-':h.spread_mv+' mV over '+h.n+' s'); st.className='warn';}
  document.getElementById('calv').textContent=h.cal.join('\n');}
 let t;
 if(fw==='station'){t='<tr><th>pump</th><th>n</th><th>grams / mL asked</th><th>error</th><th>now</th><th>suggested</th><th></th></tr>';
  for(const p in j.cal){const c=j.cal[p]; t+=`<tr><td>${p}</td><td>${c.n}</td><td>${c.grams.map((g,i)=>`<a href="#" class="w" title="remove" onclick="rm(${p},${i});return false">${g}/${c.asked[i]} &times;</a>`).join(' ')}</td><td>${c.error_pct>0?'+':''}${c.error_pct}%</td><td>${c.now??'-'}</td><td>${c.suggested??'-'}</td><td><button onclick="apply(${p},${c.suggested})">Apply</button><button onclick="rm(${p})">Clear</button></td></tr>`}}
 else{t='<tr><th>pump</th><th>n</th><th>grams</th><th>steps/mL</th><th>spread</th><th></th></tr>';
  for(const p in j.cal){const c=j.cal[p]; t+=`<tr><td>${p}</td><td>${c.n}</td><td>${c.grams.map((g,i)=>`<a href="#" class="w" title="remove" onclick="rm(${p},${i});return false">${g} &times;</a>`).join(' ')}</td><td>${c.mean}</td><td>${c.spread_pct}%</td><td><button onclick="rm(${p})">Clear pump ${p}</button></td></tr>`}}
 document.getElementById('cal').innerHTML=t;
 if(j.lines.length){const l=document.getElementById('log'); l.textContent+=j.lines.join('\n')+'\n'; l.scrollTop=l.scrollHeight;}
 since=j.next;}
setInterval(poll,800); poll();
</script></body></html>"""


def make_handler(bench: Bench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):                             # keep the terminal quiet
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                body = PAGE.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path.startswith("/state"):
                m = re.search(r"since=(\d+)", self.path)
                since = int(m.group(1)) if m else 0
                with bench.lock:
                    new, nxt = bench.lines[since:], len(bench.lines)
                self._json({"port": bench.port, "firmware": bench.firmware, "busy": bench.running(),
                            "estop": bench.estop, "primes": bench.primes, "pcal": bench.pcal,
                            "last_ml": bench.last_ml,
                            "ph": bench.ph_state(), "cal": bench.summary(), "lines": new, "next": nxt})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad request"}, 400)
            try:
                return self._post(data)
            except (KeyError, ValueError, TypeError) as e:
                return self._json({"error": str(e)}, 400)

        def _post(self, data: dict):
            if self.path == "/stop":
                bench.stop()
                return self._json({"ok": True})
            if bench.firmware is None:
                return self._json({"error": "the Uno has not answered yet: wait a few seconds"}, 409)
            if self.path == "/raw":
                cmd = str(data.get("cmd", "")).strip().upper()
                pattern = STATION_RAW if bench.firmware == "station" else BENCH_RAW
                if not pattern.match(cmd):
                    return self._json({"error": f"not allowed: {cmd}"}, 400)
                if cmd.startswith(("STEPS", "SECS")) and bench.running():
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                bench.write(cmd)
                return self._json({"ok": True})
            if self.path == "/job":
                if bench.running():
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                pump, count = int(data["pump"]), float(data.get("n") or 1)
                if pump not in PUMPS:
                    raise ValueError("pump 1-4")
                if data["action"] == "prime" and not 1 <= count <= 20:
                    raise ValueError("prime 1-20 times")
                if data["action"] == "steps" and not 1 <= abs(count) <= 20000:
                    raise ValueError("steps 1-20000")
                if data["action"] == "ml" and not 0.1 <= count <= 20:
                    raise ValueError("0.1-20 mL (the station's limit per dose)")
                bench.submit(*bench.plan(str(data["action"]), pump, count))
                return self._json({"ok": True})
            if self.path == "/weigh":
                pump, grams = int(data["pump"]), float(data["grams"])
                ml = float(data["ml"]) if data.get("ml") else None
                if pump not in PUMPS or not 0.05 < grams < 200 or (ml is not None and not 0.1 <= ml <= 20):
                    raise ValueError("pump 1-4, grams above 0, mL 0.1-20")
                bench.weigh(pump, grams, ml)
                return self._json({"ok": True})
            if self.path == "/remove":
                pump = int(data["pump"])
                index = None if data.get("index") is None else int(data["index"])
                if pump not in PUMPS:
                    raise ValueError("pump 1-4")
                bench.remove(pump, index)
                return self._json({"ok": True})
            if self.path == "/apply":
                if bench.running():
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                return self._json({"ok": True, "msg": bench.apply(int(data["pump"]))})
            if self.path in ("/phcal", "/phclear"):
                if bench.firmware != "station":
                    raise ValueError("pH calibration needs the station firmware (chemshield_uno)")
                if bench.running():
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                if self.path == "/phclear":
                    bench.write("CAL,CLEAR")
                    return self._json({"ok": True})
                ph = float(data["ph"])
                if not 1 <= ph <= 13:
                    raise ValueError("buffer pH 1-13")
                bench.ph_cal(ph)
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", help="serial port (default: the first Uno found)")
    ap.add_argument("--http", type=int, default=8090, help="web page port (default 8090)")
    a = ap.parse_args()
    port = a.port or next(iter(sorted(glob.glob("/dev/cu.usbmodem*")) + sorted(glob.glob("/dev/ttyACM*"))), None)
    if not port:
        sys.exit("No Uno found: plug in its USB, or pass --port")
    try:
        bench = Bench(port)
    except Exception as exc:                                   # usually: the station holds it
        sys.exit(f"Could not open {port}: {exc}\nIs the station (or a Serial Monitor) still running?")
    server = ThreadingHTTPServer(("127.0.0.1", a.http), make_handler(bench))
    print(f"Uno panel: open http://127.0.0.1:{a.http}  (Uno on {port}; Ctrl+C quits)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        bench.stop()
        print("\nstopped")


if __name__ == "__main__":
    main()
