// Executes the production adapter against fake GPIO/serial/display, not a
// second implementation. All results here are synthetic host regressions.
#include "main.cpp"

static void commandLine(const std::string &text) {
  Serial.input += text + "\n";
  while (!Serial.input.empty()) loop();
}
static void reset() {
  fakeMillis = 0; pins.clear(); Serial.input.clear(); Serial.output.clear();
  engine.stop(); displayReady = false; commandLength = 0; overflow = false; Wire.result = 0;
  setup();
  assert(pins[25] == LOW && pins[26] == LOW && !engine.running());
}

int main() {
  reset(); commandLine("RUN"); assert(!engine.running());
  commandLine("SERVO:27"); assert(!engine.running());
  commandLine(std::string(200, 'X') + "VISUAL"); assert(!engine.running());
  commandLine("ID"); assert(Serial.output.find(kPlanHash) != std::string::npos);
  commandLine("VISUAL"); assert(engine.running());
  fakeMillis += 1600; loop();
  assert(!engine.running() && pins[25] == LOW && pins[26] == LOW);
  assert(Serial.output.find("LEASE_EXPIRED") != std::string::npos);
  reset(); commandLine("VISUAL"); commandLine("VISUAL");
  assert(Serial.output.find("BUSY") != std::string::npos && engine.index() == 0);
  for (int n = 0; n < 100 && engine.running(); ++n) { fakeMillis += 400; commandLine("PING"); }
  assert(!engine.running() && Serial.output.find("VISUAL_DONE") != std::string::npos);
  assert(pins[25] == LOW && pins[26] == LOW);
  reset(); commandLine("DISCOVER");
  for (int n = 0; n < 100 && engine.running(); ++n) { fakeMillis += 400; commandLine("PING"); }
  assert(Serial.output.find("TEXT:P25") != std::string::npos);
  assert(Serial.output.find("TEXT:P26") != std::string::npos);
  assert(!engine.running() && pins[25] == LOW && pins[26] == LOW);
  reset(); commandLine("DISCOVER"); commandLine("STOP");
  assert(!engine.running() && pins[25] == LOW && pins[26] == LOW);
  reset(); displayReady = false; commandLine("VISUAL"); assert(!engine.running());
  // Flooded input still executes tick and releases outputs on lease expiry.
  reset(); commandLine("VISUAL"); Serial.input = std::string(5000, 'X'); fakeMillis += 1600; loop();
  assert(!engine.running() && pins[25] == LOW && pins[26] == LOW);

  sparkbench::Step step[] = {{true, false, "A"}, {false, true, "B"}};
  sparkbench::Engine e;
  assert(!e.start(step, 9, 0)); assert(e.start(step, 2, UINT32_MAX - 1000));
  e.ping(200); assert(e.tick(200) == Event::None);
  e.ping(2100); assert(e.tick(2100) == Event::Apply);
  e.ping(29000); assert(e.tick(29000) == Event::Deadline);
  assert(!e.running());
  return 0;
}
