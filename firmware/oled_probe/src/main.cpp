// Manual OLED bring-up: three bounded, address-only I2C scans.
// OLED VCC must use fixed 3.3 V; SDA=21, SCL=22. No servo attached.
// An ACK establishes bus response, not controller identity or visible output.
#include <Arduino.h>
#include <Wire.h>

static constexpr int kSda = 21;
static constexpr int kScl = 22;
static unsigned long lastHeartbeat = 0;

void setup() {
  pinMode(25, INPUT);
  pinMode(26, INPUT);
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH OLED I2C PROBE SDA=21 SCL=22 HZ=100000");
  if (!Wire.begin(kSda, kScl, 100000)) {
    Serial.println("I2C_INIT:FAIL");
    return;
  }
  Wire.setTimeOut(50);
  for (unsigned int scan = 1; scan <= 3; ++scan) {
    unsigned int found = 0;
    unsigned int errors = 0;
    Serial.printf("I2C_SCAN:%u BEGIN\n", scan);
    for (uint8_t address = 0x08; address <= 0x77; ++address) {
      Wire.beginTransmission(address);
      const uint8_t result = Wire.endTransmission();
      if (result == 0) {
        ++found;
        Serial.printf("I2C_SCAN:%u ACK_7BIT:0x%02X\n", scan, address);
      } else if (result != 2) {
        ++errors;
        Serial.printf("I2C_SCAN:%u ADDRESS:0x%02X ERROR:%u\n", scan, address, result);
      }
      delay(2);
    }
    Serial.printf("I2C_SCAN:%u END FOUND:%u ERRORS:%u\n", scan, found, errors);
    delay(500);
  }
  Wire.end();
  Serial.println("I2C_PROBE:DONE BUS_RELEASED");
}

void loop() {
  if (millis() - lastHeartbeat >= 1000) {
    lastHeartbeat = millis();
    Serial.printf("OLED_PROBE_ALIVE UPTIME_MS:%lu\n", lastHeartbeat);
  }
  delay(5);
}
