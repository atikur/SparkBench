// Compile-only preparation. Installation and servo actuation are not authorized.
// Fixed historical pulse sequence only; no generic PULSE/HOLD interface or RUN.
// Commands and UART acknowledgements do not measure actual waveform or angles.
#include <Arduino.h>

static constexpr uint8_t kServoPin = 27;
static constexpr uint16_t kPulsesUs[] = {1500, 1300, 1700, 1500};
static constexpr uint32_t kDwellMs = 2000, kLeaseMs = 1500, kMaxMs = 10000;
static constexpr uint32_t kFrequency = 50;
static constexpr uint8_t kResolution = 16;
static bool running = false, attached = false, consumed = false, faulted = false;
static unsigned stepIndex = 0;
static uint32_t started = 0, applied = 0, lastPing = 0, heartbeat = 0;
static char command[48];
static size_t commandLength = 0;
static bool overflow = false;

static void stopOutputs(const char *reason) {
  running = false;
  if (attached) {
    const bool writeOk = ledcWrite(kServoPin, 0);
    const bool detachOk = ledcDetach(kServoPin);
    attached = !detachOk;
    if (!writeOk || !detachOk) faulted = true;
  }
  digitalWrite(kServoPin, LOW);
  pinMode(kServoPin, OUTPUT);
  digitalWrite(25, LOW);
  digitalWrite(26, LOW);
  Serial.printf("SERVO_GUARD_STOPPED REASON:%s PWM:%s UPTIME_MS:%lu\n",
      reason, faulted ? "FAULT" : "OFF", millis());
}

static bool applyStep() {
  const uint16_t pulse = kPulsesUs[stepIndex];
  if (pulse < 1300 || pulse > 1700) {
    faulted = true;
    stopOutputs("PULSE_RANGE_ERROR");
    return false;
  }
  if (!attached) {
    if (!ledcAttach(kServoPin, kFrequency, kResolution)) {
      faulted = true;
      stopOutputs("PWM_ATTACH_ERROR");
      return false;
    }
    attached = true;
  }
  const uint32_t duty = (uint32_t(pulse) * 65535UL + 10000UL) / 20000UL;
  if (!ledcWrite(kServoPin, duty)) {
    faulted = true;
    stopOutputs("PWM_WRITE_ERROR");
    return false;
  }
  applied = uint32_t(millis());
  Serial.printf("SERVO_GUARD_STEP:%u PULSE_US:%u UPTIME_MS:%lu\n",
      stepIndex + 1, pulse, millis());
  return true;
}

static void handleCommand() {
  if (!strcmp(command, "ID") || !strcmp(command, "STATUS")) {
    Serial.printf("SPARKBENCH SERVO_GUARDED V:1 MODE:%s PWM:%s AVAILABLE:%u GPIO:27 RANGE_US:1300-1700\n",
        running ? "RUNNING" : "IDLE", faulted ? "FAULT" : attached ? "ON" : "OFF", !consumed && !faulted);
  } else if (!strcmp(command, "STOP")) {
    stopOutputs("STOP");
  } else if (!strcmp(command, "PING")) {
    if (running) {
      const uint32_t now = uint32_t(millis());
      if (uint32_t(now - started) >= kMaxMs) stopOutputs("DEADLINE");
      else if (uint32_t(now - lastPing) >= kLeaseMs) stopOutputs("LEASE_EXPIRED");
      else lastPing = now;
    }
  } else if (!strcmp(command, "SERVO_TEST")) {
    if (faulted || consumed || running) {
      Serial.println("SERVO_GUARD_ERROR TEST_UNAVAILABLE");
      return;
    }
    consumed = true;  // One fixed sequence per boot, including aborted sequences.
    running = true;
    stepIndex = 0;
    started = lastPing = uint32_t(millis());
    applyStep();
  } else if (commandLength) {
    Serial.println("SERVO_GUARD_ERROR COMMAND_REJECTED");
  }
}

void setup() {
  for (uint8_t pin : {uint8_t(25), uint8_t(26), kServoPin}) {
    digitalWrite(pin, LOW);
    pinMode(pin, OUTPUT);
  }
  Serial.begin(115200);
  delay(1500);
  Serial.println("SPARKBENCH SERVO_GUARDED BOOT PWM:OFF WAITING_FOR_EXPLICIT_TEST");
  stopOutputs("READY");
}

void loop() {
  // Bound parser work so a long/flooded serial stream cannot starve timeouts.
  for (unsigned n = 0; n < 64 && Serial.available(); ++n) {
    const char c = char(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      command[commandLength] = '\0';
      if (overflow) Serial.println("SERVO_GUARD_ERROR COMMAND_TOO_LONG");
      else handleCommand();
      commandLength = 0;
      overflow = false;
    } else if (!overflow && commandLength + 1 < sizeof(command)) {
      command[commandLength++] = c;
    } else {
      overflow = true;
    }
  }
  const uint32_t now = uint32_t(millis());
  if (running) {
    if (uint32_t(now - lastPing) >= kLeaseMs) {
      stopOutputs("LEASE_EXPIRED");
    } else if (uint32_t(now - started) >= kMaxMs) {
      stopOutputs("DEADLINE");
    } else if (uint32_t(now - applied) >= kDwellMs) {
      if (++stepIndex >= sizeof(kPulsesUs)/sizeof(kPulsesUs[0])) {
        stopOutputs("COMPLETE");
      } else {
        applyStep();
      }
    }
  }
  if (uint32_t(now - heartbeat) >= 1000) {
    heartbeat = now;
    Serial.printf("SERVO_GUARD_ALIVE UPTIME_MS:%lu MODE:%s PWM:%s\n", millis(),
        running ? "RUNNING" : "IDLE", faulted ? "FAULT" : attached ? "ON" : "OFF");
  }
  delay(2);
}
