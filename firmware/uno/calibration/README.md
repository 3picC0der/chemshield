# Pump calibration, final values (13 Nov 2026)

Stored in the Uno (full steps per mL), after the 10/5/20 mL check doses through chemshield_uno on the Pi (2026-11-13_check_doses.csv):

| Pump | Channel | Full steps per mL |
|---|---|---|
| 1 | ACID_BULK | 181.18 |
| 2 | ACID_FINE | 176.19 |
| 3 | BASE_BULK | 187.44 |
| 4 | BASE_FINE | 204.00 (mean of all ten pump 4 check doses, which scatter about +-1.5 %; set by hand) |

Weighed on a 0.1 g scale with water. With these values the check doses came out within about +-2-3 % at 5, 10 and 20 mL, most within 1 %: small doses read slightly low and 20 mL slightly high (start/stop ramps and backflow when the rollers stop), so one number per pump cannot be exact at every volume. status in the CSV: kept = counted, applied = measured before an Apply changed the value, removed = discarded run.
