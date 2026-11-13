# Pump calibration, final values (13 Nov 2026)

Stored in the Uno (full steps per mL), after the 10/5/20 mL check doses through chemshield_uno on the Pi (2026-11-13_check_doses.csv):

| Pump | Channel | Full steps per mL |
|---|---|---|
| 1 | ACID_BULK | 181.18 |
| 2 | ACID_FINE | 176.19 |
| 3 | BASE_BULK | 187.44 |
| 4 | BASE_FINE | 204.00 (mean of all ten pump 4 check doses, which scatter about +-1.5 %; set by hand) |

Weighed on a 0.1 g scale with water. With these values the check doses came out within about +-2-3 % at 5, 10 and 20 mL, most within 1 %: small doses read slightly low and 20 mL slightly high (start/stop ramps and backflow when the rollers stop), so one number per pump cannot be exact at every volume. status in the CSV: kept = counted, applied = measured before an Apply changed the value, removed = discarded run.

# pH probe calibration (13 Nov 2026)

Done on the Pi (the probe reading depends on the 5 V of the computer powering the Uno), with
the probe in pH 4.00, 7.00 and 9.00 buffers, through the Uno panel (CAL,<buffer pH>). Stored
in the Uno's EEPROM (`uno_tool.py show`):

| Buffer | Volts |
|---|---|
| pH 4.00 | 3.1918 |
| pH 7.00 | 2.6782 |
| pH 9.00 | 2.3455 |

Straight-line fit: pH = -5.9022 x V + 22.8298, slope -169.4 mV per pH (-171 between 4 and 7,
-166 between 7 and 9). Each point is the Uno's 10 s mean; the 10 s spread was 3-6 mV (about
0.02-0.04 pH). Raw points: 2026-11-13_ph_calibration.csv.

Both calibrations live in the Uno's EEPROM and survive unplugging and re-flashing either sketch.
Firmware on the Uno: chemshield_uno from commit 90e405d (E-stop read on its NO contact),
the version that passed the E-stop test on 13 Nov.
