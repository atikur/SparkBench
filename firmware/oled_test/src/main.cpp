// Candidate SH1106 128x64 profile; successful text/border observation is
// required before claiming display compatibility. No servo attached.
#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

static constexpr uint8_t kAddress = 0x3C;
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, 22, 21);
static unsigned long lastUpdate = 0;
static unsigned long frame = 0;
static bool ready = false;

void setup() {
  pinMode(25, INPUT);
  pinMode(26, INPUT);
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH OLED DISPLAY TEST PROFILE=SH1106_128X64 SDA=21 SCL=22 ADDR_7BIT=0x3C");
  Wire.begin(21, 22, 100000);
  Wire.setTimeOut(50);
  Wire.beginTransmission(kAddress);
  const uint8_t result = Wire.endTransmission();
  if (result != 0) {
    Serial.printf("OLED_ACK:FAIL ERROR:%u\n", result);
    return;
  }
  Serial.println("OLED_ACK:PASS");
  display.setI2CAddress(kAddress << 1);
  display.setBusClock(100000);
  display.begin();
  display.setContrast(128);
  ready = true;
}

void loop() {
  if (ready && (frame == 0 || millis() - lastUpdate >= 1000)) {
    lastUpdate = millis();
    display.clearBuffer();
    display.drawFrame(0, 0, 128, 64);
    display.setFont(u8g2_font_6x12_tr);
    display.drawStr(7, 15, "SparkBench");
    display.drawStr(7, 30, "OLED TEST");
    char counter[24];
    snprintf(counter, sizeof(counter), "Count: %lu", frame);
    display.drawStr(7, 45, counter);
    display.drawStr(7, 59, "SDA21 SCL22");
    display.sendBuffer();
    Serial.printf("OLED_FRAME_SENT:%lu UPTIME_MS:%lu\n", frame, millis());
    ++frame;
  }
  delay(5);
}
