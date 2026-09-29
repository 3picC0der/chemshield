# `sim/` — tank simulator

Owner: **Hattan** (code) · **Abdulkarim** (chemistry, Aspen validation)

Only the tank chemistry is simulated. Everything else in ChemShield — gateway, Model A,
redosing, HMI, Uno, pumps — is real code and real hardware talking to this.

## Run it

```bash
# one command, no hardware, no arguments needed:
python -m sim.batch --events 600 --seed 261 --out ISE-AT-01_batch.csv

# the booth demo: 1 Hz I2 stream, MILP driving the tank by itself
python -m sim.live --scenario acid_upset_max --autopilot

# the booth demo wired to the gateway instead (I2 out, approved doses in)
python -m sim.live --udp 127.0.0.1:9101 --listen 9100

# checks
python -m sim.tests.test_known_answers
python -m sim.chemistry                 # what table is loaded, and spot checks
python -m sim.scenarios                 # the named upsets
```

Needs `numpy` and `scipy` only (`pip install -r requirements.txt`).

## What is where

| File | What it does |
|---|---|
| `chemistry.py` | pH from the Aspen lookup table. The only place chemistry lives. |
| `aspen_tables/` | CHE's exported tables. **`aspen_tables/README.md` is the file-format contract.** |
| `make_placeholder_table.py` | Writes a stand-in table in that same format so ISE could build before Aspen arrived. |
| `tank.py` → see `live.py` | Tank state, dosing, probe lag, pump error, fault injection. |
| `model.py` | Equipment parameters, the truth model, the report's closed-form pH. |
| `rdo.py` | The robust MILP itself (called through `redosing/planner.py`). |
| `sim2.py` | The event loop: one confirmed unsafe event, start to finish. |
| `engine.py` | Points the process model at the Aspen table instead of the closed form. |
| `scenarios.py` | Named upsets (`acid_upset_max`, `beyond_budget`, …) and the batch population. |
| `batch.py` | The 600-event run. Writes the evidence CSVs. |
| `live.py` | Real-time mode: publishes I2, accepts approved doses over UDP or stdin. |

## The chemistry is swappable, and it says which one it used

`chemistry.py` loads every CSV in `aspen_tables/` whose name does not start with `_`. Right
now that is `placeholder_nahco3_ph_table.csv`: the tank liquid (5.000 L distilled water +
0.420 g NaHCO3, 1 mmol/L) as a closed carbonate model — **not Aspen**. `excess_mmol = 0` is
that liquid as prepared, about **pH 8.30, not 7**. The old pure-water table is kept as
`_placeholder_pure_water_ph_table.csv` for the known-answer tests only.

With table chemistry on (`engine.use_table_chemistry()`, which the batch, the live mode and
the planner all call), both the tank's pH and the optimiser's pH -> mmol conversion
(`model.n_of`) come from this table. The report's closed forms are only used by the
known-answer tests, through `engine.use_analytic_chemistry()`.

Every CSV the batch writes carries a `chem_source` column, every figure carries it in the
footer, and `sim.chemistry.table_provenance()` returns it. It reads `PLACEHOLDER` today and
`ASPEN` the moment CHE's files land. Nothing else changes: drop the files in, delete the
placeholder, re-run the batch.

The lookup interpolates the net strong-acid concentration rather than pH directly, because
in pure water pH moves about 2 units over 0.01 mmol near neutral while the table's grid there
is 0.002 mmol. Interpolating pH would add up to 0.07 pH of error at exactly neutral; in
concentration space the error is below 1e-5 pH. The NaHCO3 liquid instead bends sharply at
its equivalence points (±5 mmol), so its table carries the 0.05 mmol steps out to ±8 mmol
(see `aspen_tables/README.md`); that keeps the lookup within 0.005 pH everywhere.

## Sign convention — the one thing that will bite you

`excess_mmol` is **base-positive**: negative means extra acid. This matches I2 in
`docs/interfaces.md` and the Aspen tables. The optimiser inside `rdo.py` uses the opposite
(acid-positive, in mol). `chemistry.to_optimiser_n()` and `from_optimiser_n()` convert.
Never do it by hand.

`chemistry.py` refuses to load a table whose pH does not increase with `excess_mmol`,
which is what a flipped sign looks like.

## Batch output

`<out>.csv` — one row per recovery event:

`event_id, scenario, chem_source, seed, upset_dir, upset_ml, upset_mmol, start_ph, fill_L,
n_doses, n_reads, total_mmol, max_dose_ml, recovery_time_s, controller_stop_s, within_300s,
end_ph, in_band, far_side_peak_ph, excursion, outcome`

`<out>_traces.csv` — `event_id, t_s, ph`, the pH trace of every event.

Two timing columns, because the test sheets and the report define recovery differently:

- `recovery_time_s` — first moment pH enters 6.0–8.5 and then stays inside. This is the
  test sheets' definition and the pass rule is applied to it.
- `controller_stop_s` — when the controller itself declares the recovery finished, after
  the final mixing hold and triplicate read. This is the definition the Second Report
  Installment quotes. Always the larger of the two.
