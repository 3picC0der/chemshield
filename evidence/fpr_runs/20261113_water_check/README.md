# Final Prototype: first end-to-end run, water only (13 Nov 2026)

HMI (Mac) -> gateway + Model A + station (Pi) -> Uno (chemshield_uno, 90e405d) -> pumps and mixer.
All four bottles held water; the probe sat in distilled water (pH about 6.3). Audit log copied
from the Pi (`hmi/logs/20261113-204740-uno/`); it is hash-chained (`previous_hash` / `record_hash`).

| Step | Request | Result in audit.jsonl |
|---|---|---|
| 1 | 5 mL ACID_FINE | #3 ACCEPTED (Model A 0.004), #4 DOSE_ADDED |
| 2 | 5 mL again within 15 s | #5 REJECT MIXING_LOCKOUT |
| 3 | 5 mL BASE_FINE after 15 s | #6 ACCEPTED, #7 DOSE_ADDED (#8-#11 two more accepted doses) |
| 4 | another dose within 15 s | #12 REJECT MIXING_LOCKOUT |
| 5 | 25 mL | #13 REJECT DOSE_LIMIT |
| 6 | 20 mL HCl 0.5 M bulk at pH 6.3 | #14 REJECT MODEL_A_BLOCK (physics screen PREDICTED_UNSAFE:a,b,d) |
| 7 | 10 mL BASE_FINE, E-stop pressed while pumping | #15 ACCEPTED, #16 DOSE_CANCELLED, #17 PUMP_STOPPED after 2.547 mL, #18 HALT |
| 8 | E-stop released, RESUME DOSING | #19 RESUME (#20-#23: two more press/release cycles) |
