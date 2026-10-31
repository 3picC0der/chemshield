// ChemShield Uno firmware, Final Prototype (CNC Shield V3, 4 stepper peristaltic pumps, mixer).
//
// The Uno is the Pi's peripheral on USB serial (115200 baud, one line per message, "\n").
// It reads the pH board, runs the pump the gateway approved for exactly the approved volume,
// runs the mixer during and after each dose, shows the station's mode on the dose light and
// stops everything if the Pi stops talking or the E-stop is pressed. The gateway on the Pi
// decides which doses are allowed; the Uno is the last gate: one pump at a time, never more
// than 20 mL, never with the E-stop pressed or without the Pi's heartbeat. The lines are the
// ones in hmi/README.md ("Uno lines"), and hmi/mock_uno.py behaves the same way.
//
// Wiring (Arduino Uno R3 + CNC Shield V3; the shield's own labels in brackets):
//   Pump 1 ACID_BULK  X slot (DRV8825)  STEP D2,  DIR D5
//   Pump 2 ACID_FINE  Y slot (A4988)    STEP D3,  DIR D6
//   Pump 3 BASE_BULK  Z slot (DRV8825)  STEP D4,  DIR D7
//   Pump 4 BASE_FINE  A slot (A4988)    STEP D12, DIR D13 (A-axis jumpers bridged to D12/D13)
//   Driver enable D8, shared, active LOW: HIGH (off) whenever no pump is running
//   pH board Po -> A0 [Abort];  V+ -> 5V, G -> GND (leave To and Do empty)
//   E-stop normally-closed contact: A1 [Hold] -> contact -> GND. The E-stop also cuts the 24 V.
//   Dose light: A2 [Resume] -> 220 ohm to 1 kohm -> LED long leg; short leg -> GND
//   Mixer (L298N): ENA <- D9 [X end-stop signal, PWM], IN1 <- D10 [Y end-stop signal], IN2 -> GND
//   Never use D0/D1 (USB serial). D13 is pump 4's DIR, so the board's "L" light follows it.
//
// Pi -> Uno
//   HB                              heartbeat, every 0.5 s. After 2 s without one: pump and
//                                   mixer stopped, light off, "HB_LOST" sent once
//   PUMP,<seq>,<CHANNEL>,<mL>       run that channel's pump for mL (ACID_BULK, ACID_FINE,
//                                   BASE_BULK, BASE_FINE) -> "OK,<seq>", then
//                                   "DONE,<seq>,<CHANNEL>,<mL delivered>" or
//                                   "ABORT,<seq>,<CHANNEL>,<mL delivered>,<STOP|ESTOP|HB_LOST|HALT|RECOVERY|TIMEOUT>";
//                                   or "REJECT,<seq>,<ESTOP|HALTED|BUSY|NO_HB|TOO_MUCH|TOO_LONG|BAD>"
//   DOSE,<seq>,<pump 1-4>,<run_ms>  hand dosing (PPR): light ON for run_ms, no pump moves ->
//                                   "OK,<seq>" then "DONE,<seq>,<ms>"; or REJECT as above
//   STOP                            stop the pump / light now -> (ABORT line) "OK,STOP"
//   MODE,<NORMAL|RECOVERY|HALT>     off / slow blink / fast blink -> "OK,MODE,<mode>". A pump
//                                   that is running when the mode changes to HALT or RECOVERY
//                                   stops (ABORT ...,HALT / ...,RECOVERY). In RECOVERY new PUMP
//                                   lines are still accepted: they are the planner's doses.
//   MIX,<0-255>                     mixer speed when no dose is running (0 = off) -> "OK,MIX,<pwm>"
//   STATUS                          -> "STATUS,<estop 0/1>,<busy 0/1>"
// Uno -> Pi, unasked
//   PH,<pH>                         once a second, the calibrated reading (mean of ~50 samples)
//   STATUS,1,0 / STATUS,0,0         the E-stop was pressed / released
//   WARN,...                        wiring or calibration warnings
// Calibration (with the station stopped; firmware/uno/uno_tool.py does this for you)
//   CAL,<buffer pH>                 the probe sits in this buffer now: store the last 10 s mean
//   CAL,SHOW | CAL,CLEAR            -> "CAL,..." lines
//   V                               -> "V,<volts>,<pH>": the last 1 s mean voltage
//   PCAL,SHOW | PCAL,CLEAR          pump calibration -> "PCAL,..." lines
//   PCAL,<pump 1-4>,<full steps per mL>          store one pump's calibration (from weighing)
//   PCAL,SPEED,<full steps/s>,<full steps/s^2>   store the top speed and the acceleration

#include <EEPROM.h>
#include <util/atomic.h>

// ------------------------------------------------------------------ settings
const uint8_t PIN_PH = A0;
const uint8_t PIN_ESTOP = A1;
const uint8_t PIN_LIGHT = A2;
const uint8_t PIN_ENABLE = 8;              // all four drivers, LOW = on
const uint8_t PIN_MIX_PWM = 9;             // L298N ENA (Timer1 PWM)
const uint8_t PIN_MIX_IN1 = 10;            // L298N IN1 (IN2 is tied to GND)
const bool ESTOP_FITTED = true;            // false = ignore A1 (only if nothing is wired there)

const unsigned long BAUD = 115200;
const unsigned long PH_PERIOD_MS = 1000;   // one PH line a second (the Pi calls the link lost after 2 s)
const unsigned long SAMPLE_MS = 20;        // 50 samples per PH line
const unsigned long HB_TIMEOUT_MS = 2000;
const unsigned long MAX_RUN_MS = 60000;    // longest light-only (DOSE) or pump run
const unsigned long ESTOP_DEBOUNCE_MS = 30;
const float VREF = 5.0;                    // the Uno's ADC reference: its own 5 V

// Without calibration: the usual PH-4502C response, 2.50 V at pH 7, -0.177 V per pH unit.
const float DEFAULT_V7 = 2.50;
const float DEFAULT_SLOPE_V_PER_PH = -0.177;

// Pumps. MICROSTEPS must match the jumper caps under the drivers: none fitted = 1 (full
// step); the planned caps = 4. Calibration and speeds are kept in FULL steps, so they stay
// valid when MICROSTEPS changes.
const uint8_t MICROSTEPS = 1;
const float MAX_DOSE_ML = 20.0;            // S2: never more than 20 mL in one dose
const float DEFAULT_STEPS_PER_ML = 200.0;  // PLACEHOLDER (about 1 mL per turn) until weighed
const float DEFAULT_RATE = 800.0;          // full steps per second at the top of the ramp
const float DEFAULT_ACCEL = 1600.0;        // full steps per second per second (0.5 s to 800)
const float START_RATE = 100.0;            // full steps per second at the start and the end
const float MAX_RATE_LIMIT = 2000.0;       // highest top speed PCAL,SPEED accepts
const unsigned long RAMP_MS = 2;           // how often the speed is updated
const unsigned long STEP_TICK_HZ = 20000;  // Timer2 interrupt; the step rate can be up to half this

// Mixer: runs at MIX_DOSE_PWM while a pump runs and for MIX_AFTER_MS afterwards (the
// system's 15 s mixing wait), and at the MIX,<pwm> setting the rest of the time.
const uint8_t MIX_DOSE_PWM = 180;
const unsigned long MIX_AFTER_MS = 15000;

struct Pump {
  const char *channel;
  uint8_t stepPin;
  uint8_t dirPin;
  bool forwardHigh;                        // DIR level that pushes liquid into the tank
};
Pump pumps[4] = {
  {"ACID_BULK", 2, 5, true},
  {"ACID_FINE", 3, 6, true},
  {"BASE_BULK", 4, 7, true},
  {"BASE_FINE", 12, 13, true},
};

// ------------------------------------------------------------------ calibration (EEPROM)
struct Cal {
  uint16_t magic;
  uint8_t have[3];      // slots: acid buffer (~4), neutral (~7), base buffer (~10)
  float volts[3];
  float ph[3];
};
const uint16_t CAL_MAGIC = 0xC5E1;
Cal cal;
float fitA = 1.0 / DEFAULT_SLOPE_V_PER_PH;          // pH = fitA * V + fitB
float fitB = 7.0 - DEFAULT_V7 / DEFAULT_SLOPE_V_PER_PH;

struct PumpCal {
  uint16_t magic;
  uint8_t have[4];      // 1 = weighed, 0 = still the placeholder
  float stepsPerMl[4];  // full steps per mL
  float rate;           // full steps per second
  float accel;          // full steps per second per second
};
const int PCAL_ADDR = 64;                  // after Cal (29 bytes at 0); pump_bench_test reads it too
const uint16_t PCAL_MAGIC = 0xC5E2;
PumpCal pcal;

// ------------------------------------------------------------------ state
enum Mode { NORMAL, RECOVERY, HALT };
Mode mode = NORMAL;

bool estop = false;
bool estopRaw = false;
unsigned long estopChangedAt = 0;

bool hbSeen = false;
bool hbLost = false;
unsigned long lastHbAt = 0;

bool dosing = false;                       // hand dose (DOSE): the light only
unsigned long doseStart = 0;
unsigned long doseRunMs = 0;
long doseSeq = 0;

bool pumping = false;                      // pump dose (PUMP)
int8_t pumpIdx = -1;
long pumpSeq = 0;
unsigned long pumpStart = 0;
unsigned long pumpLimitMs = 0;
unsigned long lastRampAt = 0;
float rampRate = 0;                        // microsteps per second right now

// Timer2 step generator (see the ISR below)
volatile bool stepRunning = false;
volatile uint8_t *volatile stepPort;
volatile uint8_t stepMask = 0;
volatile uint16_t stepAcc = 0;
volatile uint16_t stepInc = 0;
volatile uint32_t stepsDone = 0;
volatile uint32_t stepsTarget = 0;

uint8_t mixManual = 0;
int mixNow = -1;                           // what the pins show (-1 = not set yet)
unsigned long mixAfterUntil = 0;
bool mixAfter = false;

unsigned long nextSampleAt = 0;
unsigned long nextPhAt = 0;
float sumV = 0, minV = 99, maxV = -99;
uint16_t nSamples = 0;
float lastMeanV = DEFAULT_V7;
float history[10];                // the last 10 one-second means, for CAL
uint8_t historyCount = 0, historyNext = 0;
unsigned long lastRailWarnAt = 0;

char lineBuf[64];
uint8_t lineLen = 0;

// ------------------------------------------------------------------ pH helpers
float phFromVolts(float v) { return fitA * v + fitB; }

void refit() {
  fitA = 1.0 / DEFAULT_SLOPE_V_PER_PH;
  fitB = 7.0 - DEFAULT_V7 / DEFAULT_SLOPE_V_PER_PH;
  uint8_t n = 0;
  float sx = 0, sy = 0, sxx = 0, sxy = 0;
  for (uint8_t i = 0; i < 3; i++) {
    if (!cal.have[i]) continue;
    n++;
    sx += cal.volts[i];  sy += cal.ph[i];
    sxx += cal.volts[i] * cal.volts[i];  sxy += cal.volts[i] * cal.ph[i];
  }
  if (n == 1) {                                  // one buffer: keep the usual slope, move the offset
    for (uint8_t i = 0; i < 3; i++) if (cal.have[i]) fitB = cal.ph[i] - fitA * cal.volts[i];
  } else if (n >= 2) {                           // least-squares line through the buffers
    float den = n * sxx - sx * sx;
    if (fabs(den) > 1e-9) {
      fitA = (n * sxy - sx * sy) / den;
      fitB = (sy - fitA * sx) / n;
    }
  }
}

void loadCal() {
  EEPROM.get(0, cal);
  if (cal.magic != CAL_MAGIC) {
    memset(&cal, 0, sizeof(cal));
    cal.magic = CAL_MAGIC;
  }
  refit();
}

void showCal() {
  Serial.print(F("CAL,FIT,"));
  Serial.print(fitA, 4); Serial.print(','); Serial.print(fitB, 4);
  Serial.print(F(",mV_per_pH,")); Serial.println(1000.0 / fitA, 1);
  const char *names[3] = {"ACID", "NEUTRAL", "BASE"};
  for (uint8_t i = 0; i < 3; i++) {
    Serial.print(F("CAL,")); Serial.print(names[i]); Serial.print(',');
    if (cal.have[i]) { Serial.print(cal.ph[i], 2); Serial.print(','); Serial.println(cal.volts[i], 4); }
    else Serial.println(F("none"));
  }
}

void calibrate(float bufferPh) {
  if (historyCount < 5) { Serial.println(F("CAL,ERROR,wait 5 s after power-up")); return; }
  float s = 0, lo = 99, hi = -99;
  for (uint8_t i = 0; i < historyCount; i++) {
    s += history[i]; if (history[i] < lo) lo = history[i]; if (history[i] > hi) hi = history[i];
  }
  float meanV = s / historyCount;
  uint8_t slot = bufferPh < 5.5 ? 0 : (bufferPh > 8.5 ? 2 : 1);
  cal.have[slot] = 1;
  cal.volts[slot] = meanV;
  cal.ph[slot] = bufferPh;
  EEPROM.put(0, cal);
  refit();
  Serial.print(F("CAL,OK,")); Serial.print(bufferPh, 2); Serial.print(',');
  Serial.print(meanV, 4); Serial.print(F(",spread_mV,")); Serial.println((hi - lo) * 1000.0, 1);
  showCal();
}

// ------------------------------------------------------------------ pump calibration
void pcalDefaults() {
  memset(&pcal, 0, sizeof(pcal));
  pcal.magic = PCAL_MAGIC;
  for (uint8_t i = 0; i < 4; i++) pcal.stepsPerMl[i] = DEFAULT_STEPS_PER_ML;
  pcal.rate = DEFAULT_RATE;
  pcal.accel = DEFAULT_ACCEL;
}

void loadPumpCal() {
  EEPROM.get(PCAL_ADDR, pcal);
  bool ok = pcal.magic == PCAL_MAGIC && pcal.rate >= START_RATE && pcal.rate <= MAX_RATE_LIMIT
            && pcal.rate * MICROSTEPS <= STEP_TICK_HZ / 2 && pcal.accel >= 100 && pcal.accel <= 20000;
  for (uint8_t i = 0; ok && i < 4; i++) ok = pcal.stepsPerMl[i] >= 10 && pcal.stepsPerMl[i] <= 20000;
  if (!ok) pcalDefaults();
}

void showPumpCal() {
  for (uint8_t i = 0; i < 4; i++) {
    Serial.print(F("PCAL,")); Serial.print(i + 1); Serial.print(',');
    Serial.print(pumps[i].channel); Serial.print(',');
    Serial.print(pcal.stepsPerMl[i], 2);
    Serial.println(pcal.have[i] ? F(",WEIGHED") : F(",PLACEHOLDER"));
  }
  Serial.print(F("PCAL,SPEED,")); Serial.print(pcal.rate, 0); Serial.print(',');
  Serial.print(pcal.accel, 0); Serial.print(F(",MICROSTEPS,")); Serial.println(MICROSTEPS);
}

void warnUncalibrated() {
  bool any = false;
  for (uint8_t i = 0; i < 4; i++) {
    if (pcal.have[i]) continue;
    if (!any) Serial.print(F("WARN,PUMP_NOT_CALIBRATED"));
    any = true;
    Serial.print(','); Serial.print(pumps[i].channel);
  }
  if (any) Serial.println();
}

// ------------------------------------------------------------------ outputs
void setLight(bool on) { digitalWrite(PIN_LIGHT, on ? HIGH : LOW); }

void setMixer(uint8_t pwm) {
  if (pwm == mixNow) return;
  mixNow = pwm;
  digitalWrite(PIN_MIX_IN1, pwm ? HIGH : LOW);
  analogWrite(PIN_MIX_PWM, pwm);
}

void driversOff() { digitalWrite(PIN_ENABLE, HIGH); }

// Timer2, CTC mode, 20 kHz. Each tick either ends the last step pulse (so a pulse is 50 us
// high, plenty for the A4988 and DRV8825) or adds the speed to a 16-bit accumulator and
// steps when it wraps. The loop only changes the speed, so serial and pH carry on as normal.
ISR(TIMER2_COMPA_vect) {
  if (*stepPort & stepMask) { *stepPort &= ~stepMask; return; }
  if (!stepRunning) return;
  uint16_t before = stepAcc;
  stepAcc += stepInc;
  if (stepAcc < before) {
    *stepPort |= stepMask;
    if (++stepsDone >= stepsTarget) stepRunning = false;
  }
}

void setStepRate(float microstepsPerS) {
  float maxRate = STEP_TICK_HZ / 2.0;
  if (microstepsPerS > maxRate) microstepsPerS = maxRate;
  uint16_t inc = (uint16_t)(microstepsPerS * 65536.0 / STEP_TICK_HZ);
  if (inc < 1) inc = 1;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { stepInc = inc; }
}

void timer2Start() {
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    TCCR2A = (1 << WGM21);                  // CTC
    TCCR2B = (1 << CS21);                   // /8 -> 2 MHz
    OCR2A = (F_CPU / 8 / STEP_TICK_HZ) - 1; // 99 -> 20 kHz
    TCNT2 = 0;
    TIFR2 = (1 << OCF2A);
    TIMSK2 = (1 << OCIE2A);
  }
}

void timer2Stop() {
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    TIMSK2 = 0;
    stepRunning = false;
    *stepPort &= ~stepMask;                 // leave the STEP pin low
  }
}

uint32_t stepsSoFar() {
  uint32_t n;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) { n = stepsDone; }
  return n;
}

float mlFromSteps(uint8_t pump, uint32_t microsteps) {
  return microsteps / (pcal.stepsPerMl[pump] * MICROSTEPS);
}

bool estopNow() { return ESTOP_FITTED && digitalRead(PIN_ESTOP) == HIGH; }

// ------------------------------------------------------------------ doses
void reject(long seq, const __FlashStringHelper *why) {
  Serial.print(F("REJECT,")); Serial.print(seq); Serial.print(','); Serial.println(why);
}

void endDose() {                           // the hand-dose light
  if (!dosing) return;
  dosing = false;
  Serial.print(F("DONE,")); Serial.print(doseSeq); Serial.print(',');
  Serial.println(millis() - doseStart);
}

// Stop the pump now. why = NULL: it finished; otherwise the ABORT reason.
void endPump(const __FlashStringHelper *why) {
  if (!pumping) return;
  timer2Stop();
  driversOff();
  pumping = false;
  uint32_t n = stepsSoFar();
  Serial.print(why ? F("ABORT,") : F("DONE,"));
  Serial.print(pumpSeq); Serial.print(',');
  Serial.print(pumps[pumpIdx].channel); Serial.print(',');
  Serial.print(mlFromSteps(pumpIdx, n), 3);
  if (why) { Serial.print(','); Serial.print(why); }
  Serial.println();
  if (n > 0) { mixAfter = true; mixAfterUntil = millis() + MIX_AFTER_MS; }
}

void stopAll(const __FlashStringHelper *why) {
  endPump(why);
  endDose();
}

int8_t pumpFromChannel(const char *ch) {
  for (uint8_t i = 0; i < 4; i++) if (!strcmp(ch, pumps[i].channel)) return i;
  return -1;
}

bool idleCheck(long seq) {                 // the checks every new dose must pass
  if (estop || estopNow()) { reject(seq, F("ESTOP")); return false; }
  if (mode == HALT) { reject(seq, F("HALTED")); return false; }
  if (!hbSeen || hbLost) { reject(seq, F("NO_HB")); return false; }
  if (dosing || pumping) { reject(seq, F("BUSY")); return false; }
  return true;
}

void startPump(long seq, int8_t p, float ml) {
  uint32_t target = (uint32_t)(ml * pcal.stepsPerMl[p] * MICROSTEPS + 0.5);
  // the whole dose at the top speed, plus both ramps and 5 s to spare, must fit in MAX_RUN_MS
  unsigned long expectMs = (unsigned long)(1000.0 * target / (pcal.rate * MICROSTEPS)
                                           + 2000.0 * pcal.rate / pcal.accel) + 5000;
  if (target == 0) { reject(seq, F("BAD")); return; }
  if (expectMs > MAX_RUN_MS) { reject(seq, F("TOO_LONG")); return; }

  pumpIdx = p; pumpSeq = seq; pumping = true;
  pumpStart = millis(); pumpLimitMs = expectMs; lastRampAt = pumpStart;
  digitalWrite(pumps[p].dirPin, pumps[p].forwardHigh ? HIGH : LOW);
  digitalWrite(pumps[p].stepPin, LOW);
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    stepPort = portOutputRegister(digitalPinToPort(pumps[p].stepPin));
    stepMask = digitalPinToBitMask(pumps[p].stepPin);
    stepAcc = 0; stepsDone = 0; stepsTarget = target; stepRunning = true;
  }
  rampRate = START_RATE * MICROSTEPS;
  setStepRate(rampRate);
  digitalWrite(PIN_ENABLE, LOW);
  timer2Start();
  Serial.print(F("OK,")); Serial.println(seq);
}

// Speed ramp: speed up at the set acceleration, and slow down early enough to be back at
// the start speed for the last step.
void rampPump(unsigned long now) {
  if (now - lastRampAt < RAMP_MS) return;
  float dt = (now - lastRampAt) / 1000.0;
  lastRampAt = now;
  float a = pcal.accel * MICROSTEPS;
  float vTop = pcal.rate * MICROSTEPS;
  float vMin = START_RATE * MICROSTEPS;
  float left = (float)stepsTarget - stepsSoFar();
  if (left <= (rampRate * rampRate - vMin * vMin) / (2 * a)) rampRate -= a * dt;
  else rampRate += a * dt;
  if (rampRate > vTop) rampRate = vTop;
  if (rampRate < vMin) rampRate = vMin;
  setStepRate(rampRate);
}

const char *modeName(Mode m) { return m == RECOVERY ? "RECOVERY" : (m == HALT ? "HALT" : "NORMAL"); }

// ------------------------------------------------------------------ commands from the Pi
void handleLine(char *line) {
  char *parts[5];
  uint8_t n = 0;
  for (char *tok = strtok(line, ","); tok && n < 5; tok = strtok(NULL, ",")) parts[n++] = tok;
  if (n == 0) return;
  char *head = parts[0];

  if (!strcmp(head, "HB")) {
    hbSeen = true; lastHbAt = millis(); hbLost = false;
  } else if (!strcmp(head, "PUMP")) {
    long seq = n > 1 ? atol(parts[1]) : -1;
    int8_t p = n > 2 ? pumpFromChannel(parts[2]) : -1;
    float ml = n > 3 ? atof(parts[3]) : 0;
    if (n < 4 || p < 0 || !(ml > 0)) reject(seq, F("BAD"));
    else if (ml > MAX_DOSE_ML) reject(seq, F("TOO_MUCH"));
    else if (idleCheck(seq)) startPump(seq, p, ml);
  } else if (!strcmp(head, "DOSE")) {
    long seq = n > 1 ? atol(parts[1]) : -1;
    long runMs = n > 3 ? atol(parts[3]) : -1;
    if (n < 4 || runMs <= 0) reject(seq, F("BAD"));
    else if ((unsigned long)runMs > MAX_RUN_MS) reject(seq, F("TOO_LONG"));
    else if (idleCheck(seq)) {
      dosing = true; doseStart = millis(); doseRunMs = runMs; doseSeq = seq;
      Serial.print(F("OK,")); Serial.println(seq);
    }
  } else if (!strcmp(head, "STOP")) {
    stopAll(F("STOP"));
    Serial.println(F("OK,STOP"));
  } else if (!strcmp(head, "MODE") && n > 1) {
    Mode was = mode;
    if (!strcmp(parts[1], "NORMAL")) mode = NORMAL;
    else if (!strcmp(parts[1], "RECOVERY")) mode = RECOVERY;
    else if (!strcmp(parts[1], "HALT")) mode = HALT;
    else { Serial.println(F("ERROR,MODE")); return; }
    if (mode == HALT) stopAll(F("HALT"));
    else if (mode == RECOVERY && was != RECOVERY) endPump(F("RECOVERY"));
    Serial.print(F("OK,MODE,")); Serial.println(modeName(mode));
  } else if (!strcmp(head, "MIX") && n > 1) {
    int pwm = atoi(parts[1]);
    if (pwm < 0 || pwm > 255) { Serial.println(F("ERROR,MIX,0-255")); return; }
    mixManual = estop ? 0 : pwm;
    Serial.print(F("OK,MIX,")); Serial.println(mixManual);
  } else if (!strcmp(head, "STATUS")) {
    Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.print(',');
    Serial.println(dosing || pumping ? 1 : 0);
  } else if (!strcmp(head, "V")) {
    Serial.print(F("V,")); Serial.print(lastMeanV, 4); Serial.print(','); Serial.println(phFromVolts(lastMeanV), 2);
  } else if (!strcmp(head, "CAL") && n > 1) {
    if (!strcmp(parts[1], "SHOW")) showCal();
    else if (!strcmp(parts[1], "CLEAR")) {
      memset(&cal, 0, sizeof(cal)); cal.magic = CAL_MAGIC; EEPROM.put(0, cal); refit(); showCal();
    } else {
      float p = atof(parts[1]);
      if (p >= 1.0 && p <= 13.0) calibrate(p); else Serial.println(F("CAL,ERROR,buffer pH 1-13"));
    }
  } else if (!strcmp(head, "PCAL") && n > 1) {
    if (pumping) { Serial.println(F("PCAL,ERROR,a pump is running")); return; }
    if (!strcmp(parts[1], "SHOW")) {
      showPumpCal();
    } else if (!strcmp(parts[1], "CLEAR")) {
      pcalDefaults(); EEPROM.put(PCAL_ADDR, pcal); showPumpCal();
    } else if (!strcmp(parts[1], "SPEED") && n > 3) {
      float r = atof(parts[2]), a = atof(parts[3]);
      if (r < START_RATE || r > MAX_RATE_LIMIT || r * MICROSTEPS > STEP_TICK_HZ / 2 || a < 100 || a > 20000) {
        Serial.println(F("PCAL,ERROR,speed 100-2000 full steps/s, accel 100-20000"));
        return;
      }
      pcal.rate = r; pcal.accel = a; EEPROM.put(PCAL_ADDR, pcal); showPumpCal();
    } else if (n > 2) {
      int p = atoi(parts[1]);
      float spm = atof(parts[2]);
      if (p < 1 || p > 4 || spm < 10 || spm > 20000) {
        Serial.println(F("PCAL,ERROR,pump 1-4, 10-20000 full steps per mL"));
        return;
      }
      pcal.stepsPerMl[p - 1] = spm; pcal.have[p - 1] = 1; EEPROM.put(PCAL_ADDR, pcal); showPumpCal();
    }
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = 0;
      for (uint8_t i = 0; i < lineLen; i++) lineBuf[i] = toupper(lineBuf[i]);
      if (lineLen) handleLine(lineBuf);
      lineLen = 0;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;                               // too long: drop it
    }
  }
}

// ------------------------------------------------------------------ main loop
void setup() {
  digitalWrite(PIN_ENABLE, HIGH);              // drivers off before the pin becomes an output
  pinMode(PIN_ENABLE, OUTPUT);
  for (uint8_t i = 0; i < 4; i++) {
    digitalWrite(pumps[i].stepPin, LOW);
    pinMode(pumps[i].stepPin, OUTPUT);
    pinMode(pumps[i].dirPin, OUTPUT);
  }
  stepPort = portOutputRegister(digitalPinToPort(pumps[0].stepPin));
  pinMode(PIN_MIX_IN1, OUTPUT);
  pinMode(PIN_MIX_PWM, OUTPUT);
  setMixer(0);
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  setLight(false);
  Serial.begin(BAUD);
  loadCal();
  loadPumpCal();
  estopRaw = estop = estopNow();
  unsigned long now = millis();
  nextSampleAt = now;
  nextPhAt = now + PH_PERIOD_MS;
  Serial.println(F("READY,ChemShield Uno 2.0 (pumps)"));
  Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.println(F(",0"));
  warnUncalibrated();
}

void loop() {
  // Read the Pi's lines first, then the clock: a line handled here stamps millis() (HB,
  // a new dose), and a "now" taken before that could be 1 ms older, so now - stamp would
  // wrap to ~49 days and fire HB_LOST or TIMEOUT at once.
  readSerial();
  unsigned long now = millis();

  // E-stop: NC contact to GND, so pressed (or a loose wire) reads HIGH. A running pump
  // stops on the first HIGH reading; the STATUS line waits for the debounce.
  bool raw = estopNow();
  if (raw && pumping) endPump(F("ESTOP"));
  if (raw != estopRaw) { estopRaw = raw; estopChangedAt = now; }
  if (raw != estop && now - estopChangedAt >= ESTOP_DEBOUNCE_MS) {
    estop = raw;
    if (estop) { stopAll(F("ESTOP")); mixManual = 0; mixAfter = false; }
    Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.println(F(",0"));
  }

  // Heartbeat from the Pi
  if (hbSeen && !hbLost && now - lastHbAt > HB_TIMEOUT_MS) {
    hbLost = true;
    stopAll(F("HB_LOST"));
    mixManual = 0; mixAfter = false;
    Serial.println(F("HB_LOST"));
  }

  // Pump: finished, too slow, or still ramping
  if (pumping) {
    if (!stepRunning) endPump(NULL);
    else if (now - pumpStart > pumpLimitMs) endPump(F("TIMEOUT"));
    else rampPump(now);
  }

  // Hand-dose light timer
  if (dosing && now - doseStart >= doseRunMs) endDose();

  // Mixer: dose speed during a pump dose and the mixing wait after it, else the MIX setting
  if (mixAfter && (long)(now - mixAfterUntil) >= 0) mixAfter = false;
  uint8_t mix = mixManual;
  if ((pumping || mixAfter) && mix < MIX_DOSE_PWM) mix = MIX_DOSE_PWM;
  if (estop || hbLost) mix = 0;
  setMixer(mix);

  // pH: sample every 20 ms, send the trimmed mean once a second
  if ((long)(now - nextSampleAt) >= 0) {
    nextSampleAt += SAMPLE_MS;
    int adc = analogRead(PIN_PH);
    float v = adc * VREF / 1023.0;
    sumV += v; nSamples++;
    if (v < minV) minV = v;
    if (v > maxV) maxV = v;
    if ((adc < 5 || adc > 1018) && now - lastRailWarnAt > 10000) {
      lastRailWarnAt = now;
      Serial.println(F("WARN,A0_AT_RAIL,check the pH board wiring"));
    }
  }
  if ((long)(now - nextPhAt) >= 0) {
    nextPhAt += PH_PERIOD_MS;
    if (nSamples > 2) lastMeanV = (sumV - minV - maxV) / (nSamples - 2);
    else if (nSamples > 0) lastMeanV = sumV / nSamples;
    sumV = 0; nSamples = 0; minV = 99; maxV = -99;
    history[historyNext] = lastMeanV;
    historyNext = (historyNext + 1) % 10;
    if (historyCount < 10) historyCount++;
    float ph = phFromVolts(lastMeanV);
    if (ph < 0) ph = 0;
    if (ph > 14) ph = 14;
    Serial.print(F("PH,")); Serial.println(ph, 2);
  }

  // The light: a dose wins; then E-stop/halt fast blink, recovery slow blink, else off.
  // With no heartbeat from the Pi it stays off.
  bool on;
  if (hbLost) on = false;
  else if (dosing || pumping) on = true;
  else if (estop || mode == HALT) on = (now / 125) % 2;
  else if (mode == RECOVERY) on = (now / 500) % 2;
  else on = false;
  setLight(on);
}
