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
| Mixer, L298N | ENA from D9 (X end-stop signal pin, PWM; ENA jumper removed), IN1 from D10 (Y end-stop signal pin), IN2 to GND; 12V terminal from the 24 V supply (see "The mixer") |

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
- **Microstepping: fit one cap per driver.** With no cap a driver runs full step (200 steps
  per turn), and on the bench (31 Oct) the pumps resonated around 1 turn/s: they jittered
  and lost steps (8 of 10 turns), while 0.5 and 2 turns/s were clean. With one cap on the
  middle pair under the driver (A4988 MS2, DRV8825 M1) = 1/4 step, 0.5, 1 and 2 turns/s all
  counted exactly (5/5, 10/10, 20/20). The last field of each `pumps[]` entry (`microsteps`,
  1 or 4) must match that driver's cap, in both sketches. The pump calibration and speeds are
  stored in full steps, so they stay valid when a cap is added.
- **Current.** At the 27 Oct settings (A4988 0.80 V, DRV8825 0.50 V) and full step the pumps
  rocked in place; at 1.10 V (A4988) they turned, and the caps fixed the resonance. But all
  four drivers share one enable pin (D8): whenever any pump runs, all four motors and drivers
  carry current, even the three that stand still. On 31 Oct, about 130 s of bench tests in
  4 minutes at about 1.3 A on every driver made a heatsink very hot, with a smell. On 2 Nov,
  at about 1.1 A (DRV8825 0.56 V) pump 1 jittered and lost about 2 of 5 turns at 0.5 rps
  and was rough up to 2 rps; small doses never reach the 4 rps top speed, so that matters.
  At about 1.3 A it was smooth at every speed. Set now (sense resistors R100):
  X 0.66 V and Z 0.656 V (DRV8825, I = 2 x Vref), Y 1.04 V and A 1.076 V (A4988,
  I = Vref / 0.8). With runs of about 20 s and 20 s pauses the DRV8825 heatsinks got warm
  (finger-comfortable) and the A4988s stayed cool. Keep bench runs short (about 10-20 s,
  then a pause). Real doses are about 5 s with at least 15 s off (the mixing wait). Both sketches switch the
  drivers off (D8 HIGH) after every run; during a reset or upload they float on for 1-2 s
  (see below).
- **Direction.** If a pump runs backwards, flip its `true` to `false` in the `pumps[]` table
  (the `forwardHigh` field) in both sketches, or swap one coil pair on that motor.
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

**Supply.** The L298N's 12V terminal is fed straight from the 24 V supply (after the 3 A
fuse); there is no step-down. The board bought as a step-down turned out to be a step-up
(minimum 23.7 V). The L298N's 5V-EN jumper stays on. The mixer is a 12 V motor (5840-31ZY
worm gear, 400 rpm), so both sketches cap the PWM at `MIX_PWM_MAX` = 128 of 255 (50 %,
about 11 V average after the L298N's drop of about 2 V). Every mixer request is clamped to
it, and `OK,MIX,<pwm>` reports the value actually used. If a real 24 V to 12 V step-down
(LM2596 or XL4015) is fitted later, the cap can go back up to 255.

The Uno runs the mixer (PWM 90 of 255, `MIX_DOSE_PWM`, about 7-8 V average) while a pump
runs and for 15 s afterwards (the system's mixing wait), and at the `MIX,<0-255>` setting
the rest of the time (0 by default). The E-stop and a lost heartbeat switch it off. If 90 is
too fast or too weak for the stirrer, change `MIX_DOSE_PWM` (at most `MIX_PWM_MAX`).

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
STOP                 stop now                        MIX 60 / MIX 0    mixer on / off (max 128)
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
