"""A browser control panel for the pump bench sketch: prime, check and calibrate the pumps
with buttons instead of typing into the Serial Monitor.

Needs `pump_bench_test` on the Uno and the Uno on this computer's USB. Only one program can
hold the serial port, so close the Arduino Serial Monitor (and any other tool) first. From
the repo root:

    ../chemshield/.venv/bin/python firmware/uno/bench_panel.py          (Mac)
    .venv/bin/python firmware/uno/bench_panel.py --port /dev/ttyACM0    (Pi)

then open http://127.0.0.1:8090. The page only listens on this computer.

Every button becomes one of the sketch's own commands (STEPS, SECS, RATE, MIX, STOP,
INFO), sent one at a time: the next run starts only after the Uno answers DONE. STOP sends
STOP at once and drops anything still queued. Steps are FULL steps: 200 = one turn.

Calibration: put the cup on the scale and tare, press "Cal 4000 steps", read the grams and
type them into that pump's box. The page lists every weighing, the full steps per mL of
each and their spread, and appends them to firmware/uno/bench_logs/<date>.csv. Store the
mean with chemshield_uno flashed: uno_tool.py pump-cal <pump> <full steps per mL>.
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
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PUMPS = {1: ("ACID_BULK", "right, outer"), 2: ("ACID_FINE", "right, next to the tank"),
         3: ("BASE_BULK", "left, outer"), 4: ("BASE_FINE", "left, next to the tank")}
PRIME_STEPS, CAL_STEPS, CHECK_STEPS = 2000, 4000, 400       # 10 turns, 20 turns, 2 turns
RUN_RATE, CHECK_RATE = 800, 200                             # full steps/s: 4 turns/s, 1 turn/s
PAUSE_S = 5                                                 # between repeated primes
ALLOWED = re.compile(r"^(STEPS [1-4] -?\d{1,6}|SECS [1-4] \d{1,3}(\.\d+)?|RATE \d{2,4}"
                     r"|ACCEL \d{2,5}|MIX \d{1,3}|STOP|INFO)$")
LOG_DIR = Path(__file__).resolve().parent / "bench_logs"


class Bench:
    """Owns the serial port: a reader thread logs every line, a worker sends queued jobs."""

    def __init__(self, port: str):
        import serial                                          # pyserial
        self.ser = serial.Serial(port, 115200, timeout=0.1)
        self.port = port
        self.lines: list[str] = []
        self.lock = threading.Lock()
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        self.cancel = threading.Event()
        self.ended = threading.Event()                         # DONE / STOPPED / ERROR seen
        self.primes = {p: 0 for p in PUMPS}
        self.weighings: list[dict] = []
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._work, daemon=True).start()
        self._log("#", f"opened {port}; the Uno restarts now")

    def _log(self, kind: str, text: str) -> None:
        with self.lock:
            self.lines.append(f"{datetime.now():%H:%M:%S} {kind} {text}")

    def _read(self) -> None:
        buf = b""
        while True:
            buf += self.ser.read(256)
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="replace").strip()
                if not line or line.startswith("SPEED,"):
                    continue
                self._log("<", line)
                if line.startswith(("DONE,", "STOPPED,", "ERROR,")):
                    self.ended.set()

    def _send(self, cmd: str) -> None:
        self.ser.write((cmd + "\n").encode())
        self._log(">", cmd)

    def _work(self) -> None:
        while True:
            label, steps = self.jobs.get()
            self.busy, self.cancel = True, threading.Event()
            self._log("#", f"start: {label}")
            for kind, value in steps:
                if self.cancel.is_set():
                    break
                if kind == "send":
                    self._send(value)
                    time.sleep(0.2)
                elif kind == "run":                            # wait for the end of this run
                    self.ended.clear()
                    self._send(value)
                    if not self.ended.wait(130):
                        self._send("STOP")
                        self._log("#", "no answer in 130 s: sent STOP")
                        break
                elif kind == "pause":
                    self.cancel.wait(value)
                elif kind == "count":
                    self.primes[value] += 1
            self._log("#", f"end: {label}")
            self.busy = False

    def submit(self, label: str, steps: list) -> None:
        self.jobs.put((label, steps))

    def stop(self) -> None:
        while not self.jobs.empty():
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        self.cancel.set()
        self._send("STOP")
        self.ser.write(b"MIX 0\n")
        self._log(">", "MIX 0")

    def weigh(self, pump: int, grams: float) -> None:
        w = {"time": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "pump": pump,
             "channel": PUMPS[pump][0], "full_steps": CAL_STEPS, "grams": grams,
             "steps_per_ml": round(CAL_STEPS / grams, 2)}
        self.weighings.append(w)
        LOG_DIR.mkdir(exist_ok=True)
        path = LOG_DIR / f"{datetime.now():%Y-%m-%d}.csv"
        new = not path.exists()
        with path.open("a", newline="") as f:
            out = csv.DictWriter(f, fieldnames=list(w))
            if new:
                out.writeheader()
            out.writerow(w)
        self._log("#", f"weighed pump {pump}: {grams} g -> {w['steps_per_ml']} full steps/mL ({path.name})")

    def summary(self) -> dict:
        out = {}
        for p in PUMPS:
            vals = [w["steps_per_ml"] for w in self.weighings if w["pump"] == p]
            if vals:
                mean = statistics.mean(vals)
                spread = (max(vals) - min(vals)) / mean * 100 if len(vals) > 1 else 0.0
                out[p] = {"n": len(vals), "mean": round(mean, 2), "spread_pct": round(spread, 2),
                          "grams": [w["grams"] for w in self.weighings if w["pump"] == p]}
        return out


def jobs_for(action: str, pump: int, n: int) -> tuple[str, list]:
    if action == "check":
        return f"check pump {pump} (2 turns at 1 turn/s)", [
            ("send", f"RATE {CHECK_RATE}"), ("run", f"STEPS {pump} {CHECK_STEPS}")]
    if action == "prime":
        steps: list = [("send", f"RATE {RUN_RATE}")]
        for i in range(n):
            steps += [("run", f"STEPS {pump} {PRIME_STEPS}"), ("count", pump)]
            if i < n - 1:
                steps.append(("pause", PAUSE_S))
        return f"prime pump {pump} x{n} (10 turns each)", steps
    if action == "cal":
        return f"cal pump {pump} ({CAL_STEPS} full steps)", [
            ("send", f"RATE {RUN_RATE}"), ("run", f"STEPS {pump} {CAL_STEPS}")]
    if action == "steps":
        return f"pump {pump}: {n} full steps", [
            ("send", f"RATE {RUN_RATE}"), ("run", f"STEPS {pump} {n}")]
    raise ValueError(action)


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Pump bench</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#f6f6f4;color:#222}
h1{font-size:20px;margin:0 0 4px} .sub{color:#666;margin-bottom:12px}
.stop{background:#c62828;color:#fff;font-size:22px;font-weight:700;border:0;border-radius:10px;
 padding:14px 28px;cursor:pointer;position:sticky;top:8px;z-index:2}
.row{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:12px;width:260px}
.card h2{font-size:16px;margin:0} .card .where{color:#666;font-size:13px;margin-bottom:8px}
button{font-size:14px;padding:7px 10px;margin:3px 2px;border-radius:7px;border:1px solid #aaa;
 background:#fafafa;cursor:pointer} button:disabled{opacity:.4;cursor:default}
input{width:70px;font-size:14px;padding:5px} .busy{color:#b26a00;font-weight:600}
#log{background:#111;color:#cfc;font:12px/1.4 ui-monospace,monospace;height:260px;overflow:auto;
 padding:8px;border-radius:8px;white-space:pre-wrap} table{border-collapse:collapse;font-size:13px}
td,th{border:1px solid #ddd;padding:3px 8px;text-align:right}
</style></head><body>
<h1>Pump bench panel</h1>
<div class="sub">Uno on <b id="port"></b>, sketch pump_bench_test. Status: <span id="state">idle</span>.
 Steps are full steps: 200 = one turn, about 1 mL.</div>
<button class="stop" onclick="post('/stop')">STOP</button>
<div class="row" id="cards"></div>
<div class="row">
 <div class="card"><h2>Mixer</h2><div class="where">L298N, 0-255</div>
  <button onclick="raw('MIX 100')">On (100)</button><button onclick="raw('MIX 180')">Dose speed (180)</button>
  <button onclick="raw('MIX 0')">Off</button></div>
 <div class="card"><h2>Uno</h2><div class="where">settings and stored calibration</div>
  <button onclick="raw('INFO')">INFO</button></div>
 <div class="card" style="width:auto"><h2>Calibration (weighed)</h2><div class="where">full steps per mL = 4000 / grams</div>
  <table id="cal"></table></div>
</div>
<div id="log"></div>
<script>
const P={1:["ACID_BULK","right, outer"],2:["ACID_FINE","right, next to the tank"],
 3:["BASE_BULK","left, outer"],4:["BASE_FINE","left, next to the tank"]};
let since=0;
function card(p){return `<div class="card"><h2>Pump ${p}: ${P[p][0]}</h2><div class="where">${P[p][1]} &middot; primes this session: <b id="pc${p}">0</b></div>
 <button class="go" onclick="act('check',${p})">Check (2 turns)</button>
 <button class="go" onclick="act('prime',${p},1)">Prime x1</button>
 <button class="go" onclick="act('prime',${p},3)">Prime x3</button>
 <button class="go" onclick="act('prime',${p},14)" title="a full prime from dry: 14 x 10 turns, about 2 min">Prime x14</button><br>
 <button class="go" onclick="act('cal',${p})">Cal 4000 steps</button>
 grams <input id="g${p}" type="number" step="0.01"><button onclick="weigh(${p})">Save</button><br>
 <input id="s${p}" type="number" placeholder="steps"><button class="go" onclick="act('steps',${p},+document.getElementById('s${p}').value)">Run steps</button></div>`}
document.getElementById('cards').innerHTML=[1,2,3,4].map(card).join('');
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});
 const j=await r.json(); if(j.error) alert(j.error); poll();}
function act(a,p,n){post('/job',{action:a,pump:p,n:n||1})}
function raw(c){post('/raw',{cmd:c})}
function weigh(p){const g=+document.getElementById('g'+p).value; if(!(g>0)) return alert('type the grams first');
 post('/weigh',{pump:p,grams:g}); document.getElementById('g'+p).value='';}
async function poll(){const j=await (await fetch('/state?since='+since)).json();
 document.getElementById('port').textContent=j.port;
 const s=document.getElementById('state'); s.textContent=j.busy?'RUNNING':'idle'; s.className=j.busy?'busy':'';
 document.querySelectorAll('.go').forEach(b=>b.disabled=j.busy);
 for(const p in j.primes) document.getElementById('pc'+p).textContent=j.primes[p];
 let t='<tr><th>pump</th><th>n</th><th>grams</th><th>steps/mL</th><th>spread</th></tr>';
 for(const p in j.cal){const c=j.cal[p]; t+=`<tr><td>${p}</td><td>${c.n}</td><td>${c.grams.join(', ')}</td><td>${c.mean}</td><td>${c.spread_pct}%</td></tr>`}
 document.getElementById('cal').innerHTML=t;
 if(j.lines.length){const l=document.getElementById('log'); l.textContent+=j.lines.join('\\n')+'\\n'; l.scrollTop=l.scrollHeight;}
 since=j.next;}
setInterval(poll,700); poll();
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
                self._json({"port": bench.port, "busy": bench.busy or not bench.jobs.empty(),
                            "primes": bench.primes, "cal": bench.summary(), "lines": new, "next": nxt})
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad request"}, 400)
            if self.path == "/stop":
                bench.stop()
                return self._json({"ok": True})
            if self.path == "/raw":
                cmd = str(data.get("cmd", "")).strip().upper()
                if not ALLOWED.match(cmd):
                    return self._json({"error": f"not allowed: {cmd}"}, 400)
                if cmd.startswith(("STEPS", "SECS")) and (bench.busy or not bench.jobs.empty()):
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                bench.ser.write((cmd + "\n").encode())
                bench._log(">", cmd)
                return self._json({"ok": True})
            if self.path == "/job":
                if bench.busy or not bench.jobs.empty():
                    return self._json({"error": "a run is going: wait or press STOP"}, 409)
                try:
                    pump, count = int(data["pump"]), int(data.get("n") or 1)
                    if pump not in PUMPS:
                        raise ValueError("pump 1-4")
                    if data["action"] == "prime" and not 1 <= count <= 20:
                        raise ValueError("prime 1-20 times")
                    if data["action"] == "steps" and not 1 <= abs(count) <= 20000:
                        raise ValueError("steps 1-20000")
                    bench.submit(*jobs_for(str(data["action"]), pump, count))
                except (KeyError, ValueError) as e:
                    return self._json({"error": str(e)}, 400)
                return self._json({"ok": True})
            if self.path == "/weigh":
                try:
                    pump, grams = int(data["pump"]), float(data["grams"])
                    if pump not in PUMPS or not 0.5 < grams < 200:
                        raise ValueError("pump 1-4, grams 0.5-200")
                except (KeyError, ValueError) as e:
                    return self._json({"error": str(e)}, 400)
                bench.weigh(pump, grams)
                return self._json({"ok": True})
            self._json({"error": "not found"}, 404)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", help="serial port (default: the first Uno found)")
    ap.add_argument("--http", type=int, default=8090, help="web page port (default 8090)")
    a = ap.parse_args()
    port = a.port or next(iter(sorted(glob.glob("/dev/cu.usbmodem*")) + sorted(glob.glob("/dev/ttyACM*"))), None)
    if not port:
        sys.exit("No Uno found: plug in its USB, or pass --port")
    bench = Bench(port)
    server = ThreadingHTTPServer(("127.0.0.1", a.http), make_handler(bench))
    print(f"Pump bench panel: open http://127.0.0.1:{a.http}  (Uno on {port}; Ctrl+C quits)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        bench.stop()
        print("\nstopped")


if __name__ == "__main__":
    main()
