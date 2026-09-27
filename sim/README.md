# Simulator — Hattan + Abdulkarim
Start from Hattan's existing MILP SIL plant model. Chemistry = lookup in Aspen's titration tables (Abdulkarim exports them to `sim/aspen_tables/`).
- Live mode: publishes an I2 state every second, and applies accepted doses.
- Batch mode: runs N episodes fast and writes CSVs (600 recovery events; the Model A dataset).
Evidence: Aspen vs simulator overlay plot (CHE), S1 10-min hold log.
