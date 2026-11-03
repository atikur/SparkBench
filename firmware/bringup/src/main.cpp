// Serial-only ESP32 bring-up; USB/serial configuration comes from the build profile.
// This is not the diagnostic runtime and does not touch GPIO outputs.
#include <Arduino.h>

static unsigned long lastHeartbeat = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("SPARKBENCH BRINGUP");
  Serial.print("CHIP:");
  Serial.println(ESP.getChipModel());
  Serial.print("FLASH_BYTES:");
  Serial.println(ESP.getFlashChipSize());
}

void loop() {
  const unsigned long now = millis();
  if (now - lastHeartbeat >= 1000) {
    lastHeartbeat = now;
    Serial.print("HEARTBEAT:");
    Serial.println(now);
  }
  delay(10);
}
