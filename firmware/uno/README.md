# Uno firmware (Belal)

`chemshield_uno/chemshield_uno.ino` runs the PPR rig's Arduino Uno R3. It reads the pH probe,
lights the "dose now" light when the Pi approves a dose, shows the station's mode on the
same light, and goes dark if the Pi stops talking. It decides nothing about doses: the
gateway on the Pi does. It speaks the lines in `hmi/README.md` ("Uno lines"), the same ones
`hmi/mock_uno.py` speaks.

## Wiring

| From | To |
|---|---|
| pH board V+ | Uno 5V |
| pH board G (next to V+) | Uno GND |
| pH board Po | Uno A0 (leave To and Do empty) |
| Uno D8 | 220 Ω to 1 kΩ resistor, then the LED's long leg; the LED's short leg to GND |
| Uno D2 | E-stop normally-closed contact, other side to GND. No button: a plain wire from D2 to GND |
| Uno USB | a USB port on the Pi (it also powers the Uno) |

Never use D0 or D1: they carry the USB serial. The built-in "L" light (pin 13) copies the
dose light, so the rig works before the LED is wired. With D2 left open the Uno reads the
E-stop as pressed and refuses every dose (a loose wire fails safe).

## The light

| Light | Meaning |
|---|---|
| On, steady | A dose was approved: add it now, then press DOSE ADDED |
| Slow blink | RECOVERY: an unsafe event was confirmed, operator doses are locked |
| Fast blink | HALTED, or the E-stop is pressed |
| Off | Normal, or the Pi has been silent for 2 s (heartbeat lost) |

## Flash it from the Pi

```bash
arduino-cli core install arduino:avr                     # once
arduino-cli compile --fqbn arduino:avr:uno firmware/uno/chemshield_uno
arduino-cli upload  --fqbn arduino:avr:uno -p /dev/ttyACM0 firmware/uno/chemshield_uno
```

Stop the station first: only one program can hold the serial port.

## Calibrate the probe (every morning, and before the demo)

With the station stopped, and the probe rinsed in distilled water between buffers:

```bash
.venv/bin/python firmware/uno/uno_tool.py cal 7.00      # probe in the pH 7 buffer
.venv/bin/python firmware/uno/uno_tool.py cal 4.00      # then pH 4
.venv/bin/python firmware/uno/uno_tool.py cal 10.01     # then pH 10 (optional)
.venv/bin/python firmware/uno/uno_tool.py watch         # check: pH and volts every second
```

Use the value printed on each bottle for the room temperature. The Uno keeps the points in
its EEPROM and fits a straight line through them. On this board a healthy probe moves about
160 to 180 mV per pH unit (`cal show` prints it, as a negative number). The planner assumes the probe is within
0.03 pH, and a 0.1 to 0.2 pH error can make it overshoot, so re-check pH 7 just before the
demo. Without any calibration the Uno assumes 2.50 V at pH 7 and -0.177 V per pH.
