// Trusted adapter. Generated input is only the validated plan_data.h table.
// GPIO27 is never configured or written. No PWM/servo API is linked here.
#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>
#include "engine.h"
#include "plan_data.h"

using sparkbench::Event;
sparkbench::Engine engine;
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0, U8X8_PIN_NONE, 22, 21);
static bool displayReady = false;
static uint32_t heartbeat = 0;
static char command[96];
static size_t commandLength = 0;
static bool overflow = false;
// Probe order is independent of assumed red/green wiring: physical pins only.
static constexpr sparkbench::Step kDiscovery[] = {
  {false, false, "DARK"}, {true, false, "P25"},
  {false, false, "DARK"}, {false, true, "P26"},
  {false, false, "DARK END"},
};

static void show(const char *text) {
  if (!displayReady) return;
  display.clearBuffer(); display.drawFrame(0, 0, 128, 64);
  display.setFont(u8g2_font_6x12_tr);
  display.drawStr(5, 13, "SparkBench");
  // Labels need enough physical pixels for independent camera reading, so each uses the
  // largest font that fits, centred in rows 17-47. Label contents are preserved.
  static const struct { const uint8_t *font; int baseline; } kLabelFonts[] = {
    {u8g2_font_helvB24_tr, 44}, {u8g2_font_helvB18_tr, 41}, {u8g2_font_helvB14_tr, 39},
    {u8g2_font_helvB10_tr, 37}, {u8g2_font_6x12_tr, 36},
  };
  for (const auto &choice : kLabelFonts) {
    display.setFont(choice.font);
    if (display.getStrWidth(text) <= 118 || choice.font == u8g2_font_6x12_tr) { display.drawStr(5, choice.baseline, text); break; }
  }
  display.setFont(u8g2_font_6x12_tr);
  display.drawStr(5, 58, "Servo unused"); display.sendBuffer();
}

static void stop(const char *reason) {
  engine.stop(); digitalWrite(25, LOW); digitalWrite(26, LOW); show(reason);
  Serial.printf("VISUAL_STOPPED STATUS:%s RED:0 GREEN:0 UPTIME_MS:%lu\n", reason, millis());
}

static void apply() {
  const auto &step = engine.step();
  digitalWrite(25, step.pin25 ? HIGH : LOW); digitalWrite(26, step.pin26 ? HIGH : LOW);
  show(step.text); engine.applied(millis());
  // State values are telemetry only; verifier uses timing/IDs plus camera pixels.
  Serial.printf("VISUAL_STEP:%u RED:%u GREEN:%u TEXT:%s UPTIME_MS:%lu\n",
      unsigned(engine.index() + 1), step.pin25, step.pin26, step.text, millis());
}

static void handle() {
  if (!strcmp(command, "STOP")) { stop("STOPPED"); return; }
  if (!strcmp(command, "PING")) { engine.ping(millis()); return; }
  if (!strcmp(command, "ID") || !strcmp(command, "STATUS")) {
    Serial.printf("SPARKBENCH LED_OLED_RUNTIME V:1 PLAN:%s MODE:%s OLED:%s SERVO:UNUSED\n",
        kPlanHash, engine.running() ? "RUNNING" : "IDLE", displayReady ? "ACK" : "MISSING");
    return;
  }
  const bool visual = !strcmp(command, "VISUAL"), discover = !strcmp(command, "DISCOVER");
  if (!visual && !discover) { Serial.println("VISUAL_ERROR COMMAND_REJECTED"); return; }
  if (!displayReady) { Serial.println("VISUAL_ERROR OLED_NOT_READY"); return; }
  const auto *steps = discover ? kDiscovery : kPlan;
  const size_t count = discover ? sizeof(kDiscovery)/sizeof(kDiscovery[0]) : sizeof(kPlan)/sizeof(kPlan[0]);
  if (!engine.start(steps, count, millis())) { Serial.println("VISUAL_ERROR BUSY"); return; }
  apply();
}

void setup() {
  digitalWrite(25, LOW); digitalWrite(26, LOW); pinMode(25, OUTPUT); pinMode(26, OUTPUT);
  Serial.begin(115200); delay(1500);
  Serial.println("SPARKBENCH LED_OLED_RUNTIME BOOT SERVO:UNUSED");
  Wire.begin(21, 22, 100000); Wire.setTimeOut(50); Wire.beginTransmission(0x3C);
  if (Wire.endTransmission() == 0) {
    display.setI2CAddress(0x3C << 1); display.setBusClock(100000);
    display.begin(); display.setContrast(128); displayReady = true;
  }
  stop("READY");
}

void loop() {
  // Bound input work per loop so serial flooding cannot starve lease expiry.
  for (unsigned n = 0; n < 64 && Serial.available(); ++n) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      command[commandLength] = '\0';
      if (overflow) Serial.println("VISUAL_ERROR COMMAND_TOO_LONG");
      else handle();
      commandLength = 0; overflow = false;
    } else if (!overflow && commandLength + 1 < sizeof(command)) command[commandLength++] = c;
    else overflow = true;
  }
  switch (engine.tick(millis())) {
    case Event::Apply: apply(); break;
    case Event::Complete: stop("COMPLETE"); Serial.println("VISUAL_DONE"); break;
    case Event::LeaseExpired: stop("LEASE_EXPIRED"); Serial.println("VISUAL_ERROR LEASE_EXPIRED"); break;
    case Event::Deadline: stop("DEADLINE"); Serial.println("VISUAL_ERROR DEADLINE"); break;
    default: break;
  }
  const uint32_t now = millis();
  if (uint32_t(now - heartbeat) >= 1000) {
    heartbeat = now;
    Serial.printf("VISUAL_ALIVE UPTIME_MS:%lu MODE:%s\n", now, engine.running() ? "RUNNING" : "IDLE");
  }
  delay(2);
}
