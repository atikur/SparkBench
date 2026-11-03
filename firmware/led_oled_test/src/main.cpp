// Prepared diagnostic only. Not installed by camera acquisition or bootstrap.
// Only LEDs and fixed OLED bus are used. No servo GPIO or PWM API is used.
#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

static constexpr uint8_t kRed = 25, kGreen = 26;
static constexpr unsigned long kDwellMs = 3000;
struct Step { bool red; bool green; const char *text; };
// Expected values are maintained independently in specs/led_oled_only.json.
static constexpr Step kSteps[] = {
  {false, false, "DARK"}, {true, false, "RED"},
  {false, true, "GREEN"}, {true, true, "BOTH"},
  {false, false, "DARK END"},
};
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, 22, 21);
static bool displayReady = false, running = false;
static unsigned int stepIndex = 0;
static unsigned long stepStarted = 0, lastHeartbeat = 0;
static char command[24];
static size_t commandLength = 0;
static bool commandOverflow = false;

static void showStatus(const char *text, const Step *step = nullptr) {
  if (!displayReady) return;
  display.clearBuffer();
  display.drawFrame(0, 0, 128, 64);
  display.setFont(u8g2_font_6x12_tr);
  display.drawStr(5, 13, "SparkBench");
  display.drawStr(5, 28, text);
  char line[24];
  if (step) {
    snprintf(line, sizeof(line), "R:%u G:%u", step->red, step->green);
    display.drawStr(5, 43, line);
    snprintf(line, sizeof(line), "Step %u / 5", stepIndex + 1);
    display.drawStr(5, 58, line);
  } else {
    display.drawStr(5, 43, "LEDs off");
    display.drawStr(5, 58, "Command: VISUAL");
  }
  display.sendBuffer();
}

static void stopOutputs(const char *text) {
  digitalWrite(kRed, LOW);
  digitalWrite(kGreen, LOW);
  running = false;
  showStatus(text);
  Serial.printf("VISUAL_STOPPED STATUS:%s RED:0 GREEN:0 UPTIME_MS:%lu\n", text, millis());
}

static void applyStep() {
  const Step &step = kSteps[stepIndex];
  digitalWrite(kRed, step.red ? HIGH : LOW);
  digitalWrite(kGreen, step.green ? HIGH : LOW);
  showStatus(step.text, &step);
  // Event marks completion of display transfer. Future measurements must
  // exclude transitions and align UART receipt time with camera host uptime.
  stepStarted = millis();
  Serial.printf("VISUAL_STEP:%u RED:%u GREEN:%u TEXT:%s UPTIME_MS:%lu\n",
                stepIndex + 1, step.red, step.green, step.text, stepStarted);
}

static void handleCommand() {
  if (!strcmp(command, "ID") || !strcmp(command, "STATUS")) {
    Serial.printf("SPARKBENCH LED_OLED_TEST MODE:%s OLED:%s SERVO:UNUSED\n",
                  running ? "RUNNING" : "IDLE", displayReady ? "ACK" : "MISSING");
  } else if (!strcmp(command, "STOP")) {
    stopOutputs("STOPPED");
  } else if (!strcmp(command, "VISUAL")) {
    if (running) {
      Serial.println("VISUAL_ERROR BUSY");
      return;
    }
    if (!displayReady) {
      Serial.println("VISUAL_ERROR OLED_NOT_READY");
      return;
    }
    running = true;
    stepIndex = 0;
    applyStep();
  } else if (commandLength) {
    Serial.println("ERROR COMMANDS:ID STATUS VISUAL STOP");
  }
}

void setup() {
  for (uint8_t pin : {kRed, kGreen}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH LED_OLED_TEST BOOT RED=25 GREEN=26 SDA=21 SCL=22 SERVO:UNUSED");
  Wire.begin(21, 22, 100000);
  Wire.setTimeOut(50);
  Wire.beginTransmission(0x3C);
  const uint8_t result = Wire.endTransmission();
  if (result == 0) {
    display.setI2CAddress(0x3C << 1);
    display.setBusClock(100000);
    display.begin();
    display.setContrast(128);
    displayReady = true;
  } else {
    Serial.printf("VISUAL_ERROR OLED_ACK_FAILED CODE:%u\n", result);
  }
  stopOutputs("READY");
}

void loop() {
  while (Serial.available()) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      command[commandLength] = '\0';
      if (!commandOverflow) handleCommand();
      else Serial.println("ERROR COMMAND_TOO_LONG");
      commandLength = 0;
      commandOverflow = false;
    } else if (!commandOverflow && commandLength + 1 < sizeof(command)) {
      command[commandLength++] = c;
    } else {
      commandOverflow = true;
    }
  }
  const unsigned long now = millis();
  if (running && now - stepStarted >= kDwellMs) {
    ++stepIndex;
    if (stepIndex >= sizeof(kSteps) / sizeof(kSteps[0])) {
      stopOutputs("COMPLETE");
      Serial.println("VISUAL_DONE");
    } else {
      applyStep();
    }
  }
  if (now - lastHeartbeat >= 1000) {
    lastHeartbeat = now;
    Serial.printf("VISUAL_ALIVE UPTIME_MS:%lu MODE:%s\n", now, running ? "RUNNING" : "IDLE");
  }
  delay(2);
}
