// Manual, bounded two-pin LED diagnostic for the identified classic ESP32.
// GPIO25: 3 slow flashes. GPIO26: 6 fast flashes. Two seconds off between phases.
// Inactive candidate is INPUT. Only one selected candidate is driven at a time.
// Not the protected runtime. Do not use with a servo or other peripherals fitted.
#include <Arduino.h>

struct Phase {
  uint8_t pin;
  unsigned long halfPeriodMs;
  uint8_t transitions;
};

static constexpr Phase phases[] = {{25, 1000, 6}, {26, 200, 12}};
static uint8_t phaseIndex = 0;
static uint8_t transitionsDone = 0;
static bool ledOn = false;
static bool inGap = false;
static unsigned long lastChange = 0;

static void releasePin(uint8_t pin) {
  digitalWrite(pin, LOW);
  pinMode(pin, INPUT);
}

static void reportState() {
  Serial.print("PROBE_GPIO:");
  Serial.print(phases[phaseIndex].pin);
  Serial.print(" STATE:");
  Serial.print(ledOn ? "ON" : "OFF");
  Serial.print(" UPTIME_MS:");
  Serial.println(millis());
}

static void beginPhase() {
  const Phase &phase = phases[phaseIndex];
  transitionsDone = 0;
  inGap = false;
  digitalWrite(phase.pin, LOW);
  pinMode(phase.pin, OUTPUT);
  ledOn = true;
  digitalWrite(phase.pin, HIGH);
  lastChange = millis();
  reportState();
}

void setup() {
  releasePin(25);
  releasePin(26);
  Serial.begin(115200);
  delay(300);
  Serial.println("SPARKBENCH MANUAL LED PIN PROBE: 25=SLOW; 26=FAST");
  beginPhase();
}

void loop() {
  const unsigned long now = millis();
  if (inGap) {
    if (now - lastChange >= 2000) {
      phaseIndex = (phaseIndex + 1) % 2;
      beginPhase();
    }
  } else if (now - lastChange >= phases[phaseIndex].halfPeriodMs) {
    lastChange = now;
    ++transitionsDone;
    if (transitionsDone >= phases[phaseIndex].transitions) {
      ledOn = false;
      releasePin(phases[phaseIndex].pin);
      inGap = true;
      Serial.println("PROBE_GAP:ALL_CANDIDATES_INPUT");
    } else {
      ledOn = !ledOn;
      digitalWrite(phases[phaseIndex].pin, ledOn ? HIGH : LOW);
      reportState();
    }
  }
  delay(2);
}
