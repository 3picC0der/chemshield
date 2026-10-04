// ChemShield Uno firmware (PPR rig: hand dosing, real pH probe).
//
// The Uno is the Pi's peripheral on USB serial (115200 baud, one line per message, "\n").
// It reads the pH board, lights the "dose now" light when the Pi approves a dose, shows the
// station's mode on the same light, and goes dark if the Pi stops talking. It decides
// nothing about doses: the gateway on the Pi does. The lines are the ones in hmi/README.md
// ("Uno lines"), and hmi/mock_uno.py behaves the same way.
//
// Wiring (Arduino Uno R3):
//   pH board V+ -> 5V,  G -> GND,  Po -> A0   (leave To and Do empty)
//   D8 -> 220 ohm to 1 kohm resistor -> LED long leg; LED short leg -> GND
//   D2 -> E-stop normally-closed contact -> GND. No button? A plain wire from D2 to GND.
//   Never use D0/D1: they carry the USB serial.
//
// Pi -> Uno
//   HB                              heartbeat, every 0.5 s. After 2 s without one: light off,
//                                   dose cancelled, "HB_LOST" sent once
//   DOSE,<seq>,<pump 1-4>,<run_ms>  light ON for run_ms -> "OK,<seq>" then "DONE,<seq>,<ms>";
//                                   or "REJECT,<seq>,<ESTOP|HALTED|BUSY|NO_HB|TOO_LONG|BAD>"
//   STOP                            light off (the dose was added or cancelled) -> "OK,STOP"
//   MODE,<NORMAL|RECOVERY|HALT>     off / slow blink / fast blink -> "OK,MODE,<mode>"
//   STATUS                          -> "STATUS,<estop 0/1>,<busy 0/1>"
// Uno -> Pi, unasked
//   PH,<pH>                         once a second, the calibrated reading (mean of ~50 samples)
//   STATUS,1,0 / STATUS,0,0         the E-stop was pressed / released
// Calibration (with the station stopped; firmware/uno/uno_tool.py does this for you)
//   CAL,<buffer pH>                 the probe sits in this buffer now: store the last 10 s mean
//   CAL,SHOW | CAL,CLEAR            -> "CAL,..." lines
//   V                               -> "V,<volts>,<pH>": the last 1 s mean voltage

#include <EEPROM.h>

// ------------------------------------------------------------------ settings
const uint8_t PIN_PH = A0;
const uint8_t PIN_LIGHT = 8;
const uint8_t PIN_BUILTIN = LED_BUILTIN;   // pin 13: mirrors the light, no wiring needed
const uint8_t PIN_ESTOP = 2;
const bool ESTOP_FITTED = true;            // false = ignore D2 (only if nothing is wired there)

const unsigned long BAUD = 115200;
const unsigned long PH_PERIOD_MS = 1000;   // one PH line a second (the Pi calls the link lost after 2 s)
const unsigned long SAMPLE_MS = 20;        // 50 samples per PH line
const unsigned long HB_TIMEOUT_MS = 2000;
const unsigned long MAX_RUN_MS = 60000;
const unsigned long ESTOP_DEBOUNCE_MS = 30;
const float VREF = 5.0;                    // the Uno's ADC reference: its own 5 V

// Without calibration: the usual PH-4502C response, 2.50 V at pH 7, -0.177 V per pH unit.
const float DEFAULT_V7 = 2.50;
const float DEFAULT_SLOPE_V_PER_PH = -0.177;

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

// ------------------------------------------------------------------ state
enum Mode { NORMAL, RECOVERY, HALT };
Mode mode = NORMAL;

bool estop = false;
bool estopRaw = false;
unsigned long estopChangedAt = 0;

bool hbSeen = false;
bool hbLost = false;
unsigned long lastHbAt = 0;

bool dosing = false;
unsigned long doseStart = 0;
unsigned long doseRunMs = 0;
long doseSeq = 0;

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

// ------------------------------------------------------------------ helpers
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

void setLight(bool on) {
  digitalWrite(PIN_LIGHT, on ? HIGH : LOW);
  digitalWrite(PIN_BUILTIN, on ? HIGH : LOW);
}

void endDose() {
  if (!dosing) return;
  dosing = false;
  Serial.print(F("DONE,")); Serial.print(doseSeq); Serial.print(',');
  Serial.println(millis() - doseStart);
}

void reject(long seq, const __FlashStringHelper *why) {
  Serial.print(F("REJECT,")); Serial.print(seq); Serial.print(','); Serial.println(why);
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
  } else if (!strcmp(head, "DOSE")) {
    long seq = n > 1 ? atol(parts[1]) : -1;
    long runMs = n > 3 ? atol(parts[3]) : -1;
    if (n < 4 || runMs <= 0) reject(seq, F("BAD"));
    else if (estop) reject(seq, F("ESTOP"));
    else if (mode == HALT) reject(seq, F("HALTED"));
    else if (!hbSeen || hbLost) reject(seq, F("NO_HB"));
    else if (dosing) reject(seq, F("BUSY"));
    else if ((unsigned long)runMs > MAX_RUN_MS) reject(seq, F("TOO_LONG"));
    else {
      dosing = true; doseStart = millis(); doseRunMs = runMs; doseSeq = seq;
      Serial.print(F("OK,")); Serial.println(seq);
    }
  } else if (!strcmp(head, "STOP")) {
    endDose();
    Serial.println(F("OK,STOP"));
  } else if (!strcmp(head, "MODE") && n > 1) {
    if (!strcmp(parts[1], "NORMAL")) mode = NORMAL;
    else if (!strcmp(parts[1], "RECOVERY")) mode = RECOVERY;
    else if (!strcmp(parts[1], "HALT")) mode = HALT;
    else { Serial.println(F("ERROR,MODE")); return; }
    if (mode == HALT) endDose();
    Serial.print(F("OK,MODE,")); Serial.println(modeName(mode));
  } else if (!strcmp(head, "STATUS")) {
    Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.print(','); Serial.println(dosing ? 1 : 0);
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
  pinMode(PIN_LIGHT, OUTPUT);
  pinMode(PIN_BUILTIN, OUTPUT);
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  setLight(false);
  Serial.begin(BAUD);
  loadCal();
  estopRaw = estop = ESTOP_FITTED && digitalRead(PIN_ESTOP) == HIGH;
  unsigned long now = millis();
  nextSampleAt = now;
  nextPhAt = now + PH_PERIOD_MS;
  Serial.println(F("READY,ChemShield Uno 1.0"));
  Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.println(F(",0"));
}

void loop() {
  unsigned long now = millis();
  readSerial();

  // E-stop: NC contact to GND, so pressed (or a loose wire) reads HIGH
  bool raw = ESTOP_FITTED && digitalRead(PIN_ESTOP) == HIGH;
  if (raw != estopRaw) { estopRaw = raw; estopChangedAt = now; }
  if (raw != estop && now - estopChangedAt >= ESTOP_DEBOUNCE_MS) {
    estop = raw;
    if (estop) endDose();
    Serial.print(F("STATUS,")); Serial.print(estop ? 1 : 0); Serial.println(F(",0"));
  }

  // Heartbeat from the Pi
  if (hbSeen && !hbLost && now - lastHbAt > HB_TIMEOUT_MS) {
    hbLost = true;
    endDose();
    Serial.println(F("HB_LOST"));
  }

  // Dose light timer
  if (dosing && now - doseStart >= doseRunMs) endDose();

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
  else if (dosing) on = true;
  else if (estop || mode == HALT) on = (now / 125) % 2;
  else if (mode == RECOVERY) on = (now / 500) % 2;
  else on = false;
  setLight(on);
}
