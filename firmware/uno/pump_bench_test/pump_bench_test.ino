// ChemShield pump bench test: spin one pump from the Serial Monitor (115200 baud, "Newline").
//
// For the first spin test of each pump and for calibration by weighing. It is NOT the
// station firmware: no pH, no heartbeat, no gateway. Flash chemshield_uno again afterwards.
// Same wiring as chemshield_uno (CNC Shield V3): pumps 1-4 = ACID_BULK (X), ACID_FINE (Y),
// BASE_BULK (Z), BASE_FINE (A); enable D8 (LOW = on); E-stop NC on A1; mixer ENA D9, IN1 D10.
//
// Commands (commas or spaces, any case). Steps are FULL steps: 200 = one turn of the pump.
//   STEPS <pump 1-4> <n>     run n full steps (negative = backwards, to find the direction)
//   SECS <pump 1-4> <s>      run for s seconds at the top speed (ramps included), max 120 s
//   ML <pump 1-4> <mL>       run mL using the calibration stored by chemshield_uno (PCAL)
//   RATE <full steps/s>      top speed (default 800)       ACCEL <full steps/s^2> (default 1600)
//                            (a run starts at 10 full steps/s and ramps up at ACCEL; while
//                            it runs, SPEED,<s since start>,<full steps/s> comes once a second)
//   HOLD <pump 1-4> <s>      drivers on, no steps, for s seconds (max 60): both coils carry
//                            a steady current, so a meter on DC volts across 2B-2A and across
//                            1A-1B reads about I x R (roughly 2-3 V each); 0 V = that coil gets nothing
//   MIX <0-255>              mixer speed (0 = off, capped at 128) STOP stop now
//   INFO                     settings and the stored calibration
// It answers RUN,... when a run starts and DONE,<pump>,<channel>,<full steps>,<ms>,<mL by the
// stored calibration> (or STOPPED,... after STOP or the E-stop) when it ends. The drivers are
// switched off (D8 HIGH) after every run.
//
// Calibration by weighing: put the outlet in a cup on a 0.01 g scale, prime the tube first
// (STEPS 1 2000 into a waste cup), tare, run STEPS <pump> 4000, weigh. Full steps per mL =
// 4000 / grams (water and these dilute solutions: 1 g = 1 mL). Repeat 3 times, take the mean,
// and store it with chemshield_uno flashed: uno_tool.py pump-cal <pump> --steps 4000 --grams <g>.

#include <EEPROM.h>

const uint8_t PIN_ENABLE = 8;
const uint8_t PIN_ESTOP = A1;
const uint8_t PIN_MIX_PWM = 9;
const uint8_t PIN_MIX_IN1 = 10;
// The L298N runs from the 24 V supply, the mixer motor is 12 V: never more than 50 % PWM.
const uint8_t MIX_PWM_MAX = 128;
const bool ESTOP_FITTED = true;
const float START_RATE = 10.0;             // full steps/s at the start and end of a run
const long MAX_STEPS = 100000;             // 500 turns
const float MAX_SECS = 120;

// microsteps (last field) must match the cap under each driver: none = 1, middle pair = 4.
// Keep this table the same as chemshield_uno's.
struct Pump { const char *channel; uint8_t stepPin; uint8_t dirPin; bool forwardHigh; uint8_t microsteps; };
Pump pumps[4] = {
  {"ACID_BULK", 2, 5, true, 4},
  {"ACID_FINE", 3, 6, true, 4},
  {"BASE_BULK", 4, 7, true, 4},
  {"BASE_FINE", 12, 13, true, 4},
};

// chemshield_uno's pump calibration in EEPROM (read only here)
struct PumpCal { uint16_t magic; uint8_t have[4]; float stepsPerMl[4]; float rate; float accel; };
const int PCAL_ADDR = 64;
const uint16_t PCAL_MAGIC = 0xC5E2;
PumpCal pcal;
bool pcalOk = false;

float rate = 800.0, accel = 1600.0;        // full steps
bool running = false;
int8_t pump = -1;
bool timed = false;                        // SECS: run until the time is up
bool holding = false;                      // HOLD: energised, not stepping
uint32_t target = 0, done = 0;             // microsteps
unsigned long startMs = 0, runMs = 0, lastStepUs = 0, lastReportMs = 0;
float v = 0;                               // microsteps/s now

char buf[48];
uint8_t len = 0;

bool estopPressed() { return ESTOP_FITTED && digitalRead(PIN_ESTOP) == HIGH; }

void mixer(int pwm) {
  if (pwm > MIX_PWM_MAX) pwm = MIX_PWM_MAX;
  digitalWrite(PIN_MIX_IN1, pwm ? HIGH : LOW);
  analogWrite(PIN_MIX_PWM, pwm);
}

float mlFor(int8_t p, float fullSteps) {
  return pcalOk ? fullSteps / pcal.stepsPerMl[p] : -1;
}

void finish(const __FlashStringHelper *word) {
  running = false;
  holding = false;
  digitalWrite(PIN_ENABLE, HIGH);
  float full = (float)done / pumps[pump].microsteps;
  Serial.print(word); Serial.print(pump + 1); Serial.print(','); Serial.print(pumps[pump].channel);
  Serial.print(','); Serial.print(full, 1); Serial.print(','); Serial.print(millis() - startMs);
  Serial.print(','); Serial.println(mlFor(pump, full), 3);
}

void start(int8_t p, long fullSteps, float secs) {
  if (running) { Serial.println(F("ERROR,busy: STOP first")); return; }
  if (p < 0 || p > 3) { Serial.println(F("ERROR,pump 1-4")); return; }
  if (estopPressed()) { Serial.println(F("ERROR,E-stop pressed (or A1 not wired to GND through it)")); return; }
  bool back = fullSteps < 0;
  if (back) fullSteps = -fullSteps;
  timed = secs > 0;
  if (timed) { runMs = (unsigned long)(secs * 1000); target = 0xFFFFFFFF; }
  else {
    if (fullSteps == 0 || fullSteps > MAX_STEPS) { Serial.println(F("ERROR,1-100000 steps")); return; }
    target = (uint32_t)fullSteps * pumps[p].microsteps;
  }
  pump = p; done = 0; v = START_RATE * pumps[p].microsteps;
  bool high = pumps[p].forwardHigh != back;
  digitalWrite(pumps[p].dirPin, high ? HIGH : LOW);
  digitalWrite(PIN_ENABLE, LOW);
  delay(2);                                // drivers wake up
  startMs = millis(); lastReportMs = startMs; lastStepUs = micros(); running = true;
  Serial.print(F("RUN,")); Serial.print(p + 1); Serial.print(','); Serial.print(pumps[p].channel);
  Serial.print(back ? F(",backwards,") : F(",forwards,"));
  if (timed) { Serial.print(secs, 1); Serial.println(F(" s")); }
  else { Serial.print(fullSteps); Serial.println(F(" full steps")); }
}

void info() {
  Serial.print(F("INFO,rate,")); Serial.print(rate, 0); Serial.print(F(",accel,")); Serial.print(accel, 0);
  Serial.print(F(",microsteps"));
  for (uint8_t i = 0; i < 4; i++) { Serial.print(','); Serial.print(pumps[i].microsteps); }
  Serial.print(F(",estop,")); Serial.println(estopPressed() ? F("PRESSED") : F("released"));
  for (uint8_t i = 0; i < 4; i++) {
    Serial.print(F("INFO,pump,")); Serial.print(i + 1); Serial.print(','); Serial.print(pumps[i].channel);
    Serial.print(F(",full_steps_per_mL,"));
    if (pcalOk) { Serial.print(pcal.stepsPerMl[i], 2); Serial.println(pcal.have[i] ? F(",weighed") : F(",placeholder")); }
    else Serial.println(F("none stored"));
  }
}

void handle(char *line) {
  char *w[3];
  uint8_t n = 0;
  for (char *t = strtok(line, ", \t"); t && n < 3; t = strtok(NULL, ", \t")) w[n++] = t;
  if (!n) return;
  if (!strcmp(w[0], "STOP")) {
    if (running) finish(F("STOPPED,")); else Serial.println(F("OK,STOP"));
  } else if (!strcmp(w[0], "HOLD") && n == 3) {
    float secs = atof(w[2]);
    if (running) Serial.println(F("ERROR,busy: STOP first"));
    else if (estopPressed()) Serial.println(F("ERROR,E-stop pressed"));
    else if (!(secs > 0) || secs > 60) Serial.println(F("ERROR,0-60 s"));
    else if (atoi(w[1]) < 1 || atoi(w[1]) > 4) Serial.println(F("ERROR,pump 1-4"));
    else {
      pump = atoi(w[1]) - 1; done = 0; timed = true; holding = true;
      runMs = (unsigned long)(secs * 1000);
      digitalWrite(PIN_ENABLE, LOW);
      startMs = millis(); lastReportMs = startMs; running = true;
      Serial.print(F("HOLD,")); Serial.print(pump + 1); Serial.print(','); Serial.println(secs, 0);
    }
  } else if (!strcmp(w[0], "STEPS") && n == 3) {
    start(atoi(w[1]) - 1, atol(w[2]), 0);
  } else if (!strcmp(w[0], "SECS") && n == 3) {
    float s = atof(w[2]);
    if (s > 0 && s <= MAX_SECS) start(atoi(w[1]) - 1, 0, s); else Serial.println(F("ERROR,0-120 s"));
  } else if (!strcmp(w[0], "ML") && n == 3) {
    int8_t p = atoi(w[1]) - 1;
    float ml = atof(w[2]);
    if (!pcalOk) Serial.println(F("ERROR,no calibration stored: use STEPS"));
    else if (p < 0 || p > 3 || !(ml > 0) || ml > 100) Serial.println(F("ERROR,pump 1-4, 0-100 mL"));
    else start(p, (long)(ml * pcal.stepsPerMl[p] + 0.5), 0);
  } else if (!strcmp(w[0], "RATE") && n == 2) {
    float r = atof(w[1]);
    if (r >= START_RATE && r <= 2000) { rate = r; info(); } else Serial.println(F("ERROR,10-2000 full steps/s"));
  } else if (!strcmp(w[0], "ACCEL") && n == 2) {
    float a = atof(w[1]);
    if (a >= 10 && a <= 20000) { accel = a; info(); } else Serial.println(F("ERROR,10-20000"));
  } else if (!strcmp(w[0], "MIX") && n == 2) {
    int pwm = atoi(w[1]);
    if (pwm >= 0 && pwm <= 255 && !estopPressed()) {
      if (pwm > MIX_PWM_MAX) pwm = MIX_PWM_MAX;
      mixer(pwm); Serial.print(F("OK,MIX,")); Serial.println(pwm);
    }
    else Serial.println(F("ERROR,MIX 0-255, E-stop released"));
  } else if (!strcmp(w[0], "INFO") || !strcmp(w[0], "?")) {
    info();
  } else {
    Serial.println(F("ERROR,commands: STEPS p n | SECS p s | ML p mL | HOLD p s | RATE r | ACCEL a | MIX pwm | STOP | INFO"));
  }
}

void setup() {
  digitalWrite(PIN_ENABLE, HIGH);
  pinMode(PIN_ENABLE, OUTPUT);
  for (uint8_t i = 0; i < 4; i++) {
    digitalWrite(pumps[i].stepPin, LOW);
    pinMode(pumps[i].stepPin, OUTPUT);
    pinMode(pumps[i].dirPin, OUTPUT);
  }
  pinMode(PIN_MIX_IN1, OUTPUT);
  pinMode(PIN_MIX_PWM, OUTPUT);
  mixer(0);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  EEPROM.get(PCAL_ADDR, pcal);
  pcalOk = pcal.magic == PCAL_MAGIC;
  Serial.begin(115200);
  Serial.println(F("READY,ChemShield pump bench test"));
  info();
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') { buf[len] = 0; for (uint8_t i = 0; i < len; i++) buf[i] = toupper(buf[i]); handle(buf); len = 0; }
    else if (len < sizeof(buf) - 1) buf[len++] = c;
    else len = 0;
  }

  if (estopPressed()) {
    if (running) finish(F("STOPPED,"));
    mixer(0);
  }
  if (!running) return;

  unsigned long elapsed = millis() - startMs;
  uint8_t m = pumps[pump].microsteps;
  float a = accel * m, vMin = START_RATE * m, vTop = rate * m;
  if (timed && elapsed >= runMs) { finish(F("DONE,")); return; }
  if (!timed && done >= target) { finish(F("DONE,")); return; }
  if (holding) return;

  if (millis() - lastReportMs >= 1000) {     // so the speed can be matched to what the pump does
    lastReportMs += 1000;
    Serial.print(F("SPEED,")); Serial.print((millis() - startMs) / 1000.0, 1);
    Serial.print(','); Serial.println(v / m, 0);
  }

  // one step when its time has come; the speed follows the ramp, step by step
  unsigned long nowUs = micros();
  if (nowUs - lastStepUs < (unsigned long)(1e6 / v)) return;
  lastStepUs = nowUs;
  uint8_t pin = pumps[pump].stepPin;
  digitalWrite(pin, HIGH);
  delayMicroseconds(4);
  digitalWrite(pin, LOW);
  done++;
  float left = timed ? (runMs - elapsed) / 1000.0 * v : (float)(target - done);
  float braking = (v * v - vMin * vMin) / (2 * a);
  if (left <= braking) v -= a / v; else v += a / v;
  if (v > vTop) v = vTop;
  if (v < vMin) v = vMin;
}
