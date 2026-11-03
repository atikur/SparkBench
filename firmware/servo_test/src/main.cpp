// Manual, unloaded SG90 test. External ~5 V supply; common ground; GPIO27.
// No automatic motion on boot/reset/open. CENTER and TEST require serial input.
// Pulse widths are commands, not measurements of the shaft's actual angle.
#include <Arduino.h>

static constexpr uint8_t kServoPin = 27;
static constexpr uint32_t kFrequency = 50;
static constexpr uint8_t kResolution = 16;
static constexpr uint16_t kPulsesUs[] = {1500, 1300, 1700, 1500};
enum class Mode { Idle, Center, Test };
static Mode mode = Mode::Idle;
static bool attached = false;
static uint8_t stepIndex = 0;
static unsigned long stepStarted = 0;
static unsigned long lastHeartbeat = 0;
static char command[24];
static size_t commandLength = 0;
static bool commandOverflow = false;

static const char *modeName() {
  if (mode == Mode::Center) return "CENTER";
  if (mode == Mode::Test) return "TEST";
  return "IDLE";
}

static void stopServo() {
  if (attached) {
    ledcWrite(kServoPin, 0);
    ledcDetach(kServoPin);
    attached = false;
  }
  digitalWrite(kServoPin, LOW);
  pinMode(kServoPin, OUTPUT);
  mode = Mode::Idle;
  Serial.println("SERVO_STOPPED SIGNAL_LOW PWM_OFF");
}

static bool sendPulse(uint16_t pulseUs) {
  if (!attached) {
    attached = ledcAttach(kServoPin, kFrequency, kResolution);
    if (!attached) {
      Serial.println("SERVO_ERROR PWM_ATTACH_FAILED");
      stopServo();
      return false;
    }
  }
  const uint32_t duty = (static_cast<uint32_t>(pulseUs) * 65535UL + 10000UL) / 20000UL;
  if (!ledcWrite(kServoPin, duty)) {
    Serial.println("SERVO_ERROR PWM_WRITE_FAILED");
    stopServo();
    return false;
  }
  stepStarted = millis();
  Serial.printf("SERVO_COMMAND PULSE_US:%u GPIO:27 HZ:50 MODE:%s\n", pulseUs, modeName());
  return true;
}

static void handleCommand() {
  if (!strcmp(command, "ID") || !strcmp(command, "STATUS")) {
    Serial.printf("SPARKBENCH SERVO_TEST GPIO:27 MODE:%s PWM:%s\n", modeName(), attached ? "ON" : "OFF");
  } else if (!strcmp(command, "STOP")) {
    stopServo();
  } else if (!strcmp(command, "CENTER")) {
    stopServo();
    mode = Mode::Center;
    sendPulse(1500);
  } else if (!strcmp(command, "TEST")) {
    stopServo();
    mode = Mode::Test;
    stepIndex = 0;
    sendPulse(kPulsesUs[stepIndex]);
  } else if (commandLength) {
    Serial.println("ERROR COMMANDS:ID STATUS CENTER TEST STOP");
  }
}

void setup() {
  digitalWrite(kServoPin, LOW);
  pinMode(kServoPin, OUTPUT);
  pinMode(25, INPUT);
  pinMode(26, INPUT);
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH SERVO_TEST READY GPIO:27 PWM:OFF WAITING_FOR_COMMAND");
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
  if (mode == Mode::Center && now - stepStarted >= 3000) {
    stopServo();
    Serial.println("SERVO_CENTER_DONE");
  } else if (mode == Mode::Test && now - stepStarted >= 2000) {
    ++stepIndex;
    if (stepIndex >= sizeof(kPulsesUs) / sizeof(kPulsesUs[0])) {
      stopServo();
      Serial.println("SERVO_TEST_DONE");
    } else {
      sendPulse(kPulsesUs[stepIndex]);
    }
  }
  if (now - lastHeartbeat >= 1000) {
    lastHeartbeat = now;
    Serial.printf("SERVO_ALIVE UPTIME_MS:%lu MODE:%s PWM:%s\n", now, modeName(), attached ? "ON" : "OFF");
  }
  delay(2);
}
