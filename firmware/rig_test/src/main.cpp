// Hand-written combined bring-up; mappings were established manually.
// No discovery, generation, camera verification, or protected runtime yet.
// External servo ~5 V, common GND. OLED fixed 3.3 V. RUN is explicit.
#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>

static constexpr uint8_t kRed = 25, kGreen = 26, kServo = 27;
struct Step {
  uint16_t pulseUs;
  bool red;
  bool green;
  const char *text;
};
static constexpr Step kSteps[] = {
  {1500, true, false, "CENTER"},
  {1300, false, true, "SIDE A"},
  {1700, true, true, "SIDE B"},
  {1500, false, false, "CENTER"},
};
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, 22, 21);
static bool displayReady = false, running = false, pwmAttached = false;
static unsigned int stepIndex = 0;
static unsigned long stepStarted = 0, lastHeartbeat = 0;
static char command[24];
static size_t commandLength = 0;
static bool commandOverflow = false;

static void showStatus(const char *status, const Step *step = nullptr) {
  if (!displayReady) return;
  display.clearBuffer();
  display.drawFrame(0, 0, 128, 64);
  display.setFont(u8g2_font_6x12_tr);
  display.drawStr(5, 13, "SparkBench");
  display.drawStr(5, 28, status);
  char line[24];
  if (step) {
    snprintf(line, sizeof(line), "R:%u G:%u PWM:%u", step->red, step->green, step->pulseUs);
    display.drawStr(5, 43, line);
    snprintf(line, sizeof(line), "Step %u / 4", stepIndex + 1);
    display.drawStr(5, 58, line);
  } else {
    display.drawStr(5, 43, "Outputs off");
    display.drawStr(5, 58, "USB command: RUN");
  }
  display.sendBuffer();
}

static void stopOutputs(const char *status) {
  if (pwmAttached) {
    ledcWrite(kServo, 0);
    ledcDetach(kServo);
    pwmAttached = false;
  }
  digitalWrite(kServo, LOW);
  pinMode(kServo, OUTPUT);
  digitalWrite(kRed, LOW);
  digitalWrite(kGreen, LOW);
  running = false;
  Serial.printf("RIG_STOPPED STATUS:%s PWM:OFF RED:0 GREEN:0\n", status);
  showStatus(status);
}

static bool applyStep() {
  const Step &step = kSteps[stepIndex];
  const uint32_t duty = (static_cast<uint32_t>(step.pulseUs) * 65535UL + 10000UL) / 20000UL;
  if (!ledcWrite(kServo, duty)) {
    Serial.println("RIG_ERROR PWM_WRITE_FAILED");
    stopOutputs("PWM ERROR");
    return false;
  }
  digitalWrite(kRed, step.red ? HIGH : LOW);
  digitalWrite(kGreen, step.green ? HIGH : LOW);
  showStatus(step.text, &step);
  stepStarted = millis();
  Serial.printf("RIG_STEP:%u PULSE_US:%u RED:%u GREEN:%u TEXT:%s UPTIME_MS:%lu\n",
                stepIndex + 1, step.pulseUs, step.red, step.green, step.text, stepStarted);
  return true;
}

static void handleCommand() {
  if (!strcmp(command, "ID") || !strcmp(command, "STATUS")) {
    Serial.printf("SPARKBENCH RIG_TEST MODE:%s PWM:%s OLED:%s\n",
                  running ? "RUNNING" : "IDLE", pwmAttached ? "ON" : "OFF", displayReady ? "ACK" : "MISSING");
  } else if (!strcmp(command, "STOP")) {
    stopOutputs("STOPPED");
  } else if (!strcmp(command, "RUN")) {
    stopOutputs("STARTING");
    if (!displayReady) {
      Serial.println("RIG_ERROR OLED_NOT_READY");
      return;
    }
    pwmAttached = ledcAttach(kServo, 50, 16);
    if (!pwmAttached) {
      Serial.println("RIG_ERROR PWM_ATTACH_FAILED");
      stopOutputs("PWM ERROR");
      return;
    }
    running = true;
    stepIndex = 0;
    applyStep();
  } else if (commandLength) {
    Serial.println("ERROR COMMANDS:ID STATUS RUN STOP");
  }
}

void setup() {
  for (uint8_t pin : {kRed, kGreen, kServo}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH RIG_TEST BOOT OUTPUTS_OFF RED=25 GREEN=26 SERVO=27 SDA=21 SCL=22");
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
    showStatus("READY");
  } else {
    Serial.printf("RIG_ERROR OLED_ACK_FAILED CODE:%u\n", result);
  }
  Serial.printf("RIG_READY WAITING_FOR_RUN OLED:%s PWM:OFF\n", displayReady ? "ACK" : "MISSING");
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
  if (running && now - stepStarted >= 2000) {
    ++stepIndex;
    if (stepIndex >= sizeof(kSteps) / sizeof(kSteps[0])) {
      stopOutputs("COMPLETE");
      Serial.println("RIG_TEST_DONE");
    } else {
      applyStep();
    }
  }
  if (now - lastHeartbeat >= 1000) {
    lastHeartbeat = now;
    Serial.printf("RIG_ALIVE UPTIME_MS:%lu MODE:%s PWM:%s\n", now, running ? "RUNNING" : "IDLE", pwmAttached ? "ON" : "OFF");
  }
  delay(2);
}
