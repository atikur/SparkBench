// Manual component test, not the protected command runtime.
// Confirm the photographed board/carrier mapping before upload.
// Wiring: GPIO25 -> 330 ohm resistor -> red LED anode; cathode -> GND.
// The carrier's selectable V rail is not used by this test.
#include <Arduino.h>

static constexpr uint8_t kRedLedPin = 25;
static bool ledOn = false;
static unsigned long lastChange = 0;

void setup() {
  digitalWrite(kRedLedPin, LOW);
  pinMode(kRedLedPin, OUTPUT);
  Serial.begin(115200);
  delay(300);
  Serial.println("SPARKBENCH RED LED TEST GPIO25 ACTIVE_HIGH");
  lastChange = millis();
}

void loop() {
  const unsigned long now = millis();
  if (now - lastChange >= 1000) {
    lastChange = now;
    ledOn = !ledOn;
    digitalWrite(kRedLedPin, ledOn ? HIGH : LOW);
    Serial.print("RED_LED:");
    Serial.print(ledOn ? "ON" : "OFF");
    Serial.print(" UPTIME_MS:");
    Serial.println(now);
  }
  delay(5);
}
