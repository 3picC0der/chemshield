# Uno firmware (Belal)

Two sketches for the Arduino Uno R3 with the CNC Shield V3 on top:

| Sketch | What it is for |
|---|---|
| `chemshield_uno/` | The station firmware. It reads the pH probe, runs the pump the gateway approved for exactly the approved mL, runs the mixer, shows the station's mode on the dose light and stops everything when the Pi goes quiet or the E-stop is pressed. It speaks the lines in `hmi/README.md` ("Uno lines"), the same ones `hmi/mock_uno.py` speaks. |
| `pump_bench_test/` | A bench tool: spin one pump a given number of steps or seconds from the Serial Monitor. For the first spin test and for calibration by weighing. No pH, no heartbeat, no gateway: flash `chemshield_uno` again afterwards. |

The gateway on the Pi decides which doses are allowed. The Uno is the last gate behind it:
one pump at a time, never over 20 mL (or 60 s), never with the E-stop pressed, in HALT or
without the Pi's heartbeat, and the drivers are off (D8 HIGH) whenever no pump runs.

## Wiring (Final Prototype)

| Part | Uno pin (shield label) |
|---|---|
| Pump 1 `ACID_BULK`, X slot, DRV8825 | STEP D2, DIR D5 |
| Pump 2 `ACID_FINE`, Y slot, A4988 | STEP D3, DIR D6 |
| Pump 3 `BASE_BULK`, Z slot, DRV8825 | STEP D4, DIR D7 |
| Pump 4 `BASE_FINE`, A slot, A4988 | STEP D12, DIR D13 (A-axis jumpers bridged to D12/D13) |
| Driver enable, all four | D8, active LOW (the sketch keeps it HIGH when idle) |
| pH board Po | A0 (Abort). V+ to 5V, G to GND; leave To and Do empty |
| E-stop normally-closed contact | A1 (Hold), other side to GND. The E-stop also cuts the 24 V |
| Dose light | A2 (Resume), through 220 Ω to 1 kΩ to the LED's long leg; short leg to GND |
| Mixer, L298N | ENA from D9 (X end-stop signal pin, PWM), IN1 from D10 (Y end-stop signal pin), IN2 to GND |

Never use D0 or D1: they carry the USB serial. D13 is pump 4's DIR now, so the board's "L"
light just follows that pin; it no longer copies the dose light. With A1 left open the Uno
reads the E-stop as pressed and refuses every dose (a loose wire fails safe).

Things to know about the shield (Protoneer CNC Shield V3.00, checked against a photo on 31 Oct):
- **The pin labelled E-STOP on the shield is the Uno's RESET, not an input.** Wire the
  E-stop's NC contact to **Hold** (A1) and GND, never to E-STOP: on RESET it would reboot
  the Uno, and while it reboots the drivers can switch on by themselves (see below).
- **SpnEn and SpnDir are D12 and D13**, pump 4's STEP and DIR once the A slot is bridged to
  D12/D13. Leave those two header pins empty.
- On the end-stop header the white row is the signal and the black row is GND; X+ and X-
  are both D9, Y+ and Y- both D10. The L298N's GND must also go to a black (GND) pin.
- **Microstepping.** No jumper caps under the drivers = full step (200 steps per turn).
  `MICROSTEPS` at the top of both sketches must match the caps: 1 now; set it to 4 in both
  sketches once caps for 1/4 step are fitted (on both driver types that is MS2 only). The
  pump calibration and speeds are stored in full steps, so they stay valid.
- **Direction.** If a pump runs backwards, flip its `true` to `false` in the `pumps[]` table
  (the last field, `forwardHigh`) in both sketches, or swap one coil pair on that motor.
- **At power-up and during upload** the Uno's pins float for a second or two, and the A4988
  and DRV8825 pull their own ENABLE low, so the drivers can be energised (holding torque, no
  stepping) until the sketch starts. Upload with the 24 V off. If the motors hold (feel stiff)
  while the Uno resets, a 10 kΩ resistor from D8 to 5 V keeps the drivers off.

## The light

| Light | Meaning |
|---|---|
| On, steady | A pump is running (or, with hand dosing, add the dose now) |
| Slow blink | RECOVERY: an unsafe event was confirmed, operator doses are locked |
| Fast blink | HALTED, or the E-stop is pressed |
| Off | Normal, or the Pi has been silent for 2 s (heartbeat lost) |

## The mixer

The Uno runs the mixer (PWM 180 of 255, `MIX_DOSE_PWM`) while a pump runs and for 15 s
afterwards (the system's mixing wait), and at the `MIX,<0-255>` setting the rest of the
time (0 by default). The E-stop and a lost heartbeat switch it off. If 180 is too fast or
too weak for the stirrer, change `MIX_DOSE_PWM`.

## Compile and flash

On the Mac, the Arduino IDE has arduino-cli inside it:

```bash
CLI="/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli"
"$CLI" compile --fqbn arduino:avr:uno firmware/uno/chemshield_uno
"$CLI" compile --fqbn arduino:avr:uno firmware/uno/pump_bench_test
```

`chemshield_uno` uses about 14 KB of the Uno's 32 KB and 650 bytes of its 2 KB RAM.

On the Pi (once: `sudo apt-get install -y --no-install-recommends arduino-mk arduino-core-avr
gcc-avr avr-libc avrdude`), with the station stopped (only one program can hold the serial
port):

```bash
cd firmware/uno/chemshield_uno     # or firmware/uno/pump_bench_test
make            # compile
make upload     # load it onto the Uno on /dev/ttyACM0
```

## First spin test and pump calibration (pump_bench_test)

Flash `pump_bench_test`, open the Serial Monitor at 115200 baud with "Newline", and switch
the 24 V on. Steps are full steps: 200 = one turn.

```
INFO                 settings, E-stop state and any calibration already stored
STEPS 1 200          pump 1 one turn forwards        STEPS 1 -200   one turn backwards
SECS 2 10            pump 2 for 10 s at the top speed
RATE 400             a slower top speed (default 800 full steps/s); ACCEL 800 a gentler ramp
STOP                 stop now                        MIX 150 / MIX 0   mixer on / off
ML 1 5               5 mL with the calibration stored by chemshield_uno (to check it)
```

Each run ends with `DONE,<pump>,<channel>,<full steps>,<ms>,<mL by the stored calibration>`
(or `STOPPED,...`), and the drivers are switched off.

**Calibration by weighing**, per pump, with the real tubing and a 0.01 g scale:
1. Prime the tube: `STEPS 1 2000` into a waste cup.
2. Put a clean cup on the scale, tare, hold the outlet in it: `STEPS 1 4000`.
3. Weigh. Full steps per mL = 4000 / grams (for water and these dilute solutions 1 g = 1 mL).
   Repeat three times and use the mean; they should agree within about 1 %.
4. Flash `chemshield_uno` again and store it (EEPROM, survives re-flashing):

```bash
.venv/bin/python firmware/uno/uno_tool.py pump-cal 1 --steps 4000 --grams 19.62
.venv/bin/python firmware/uno/uno_tool.py pumps                 # check all four
.venv/bin/python firmware/uno/uno_tool.py dose ACID_BULK 10     # 10 mL into a cup on the scale
```

Until a pump is weighed it uses the placeholder 200 full steps per mL (about 1 mL per turn)
and the Uno sends `WARN,PUMP_NOT_CALIBRATED,...` at start-up. `uno_tool.py pump-speed 800 1600`
changes the top speed and the acceleration (stored too); start low and raise it only if the
Uno keeps sending `PH,x` every second and the pump does not skip.

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
