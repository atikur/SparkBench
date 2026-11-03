// Actual prepared adapter against fake GPIO/PWM/serial. Never physical evidence.
#include "main.cpp"

static void issue(const std::string &value) {
  Serial.input+=value+"\n";
  while (!Serial.input.empty()) loop();
}
static void reset() {
  fakeMillis=0;pins.clear();Serial.input.clear();Serial.output.clear();duties.clear();
  pwmAttached=failAttach=failWrite=failDetach=false;attachCount=detachCount=0;
  running=attached=consumed=faulted=false;stepIndex=0;
  started=applied=lastPing=heartbeat=0;commandLength=0;overflow=false;
  setup();
  assert(!running && !pwmAttached && attachCount==0 && duties.empty());
  assert(pins[25]==LOW && pins[26]==LOW && pins[27]==LOW);
}
int main() {
  reset();issue("ID");issue("PING");
  for (const char *cmd : {"RUN","CENTER","TEST","PULSE 2500","HOLD 1700","SERVO_TEST extra"}) issue(cmd);
  issue(std::string(200,'X')+"SERVO_TEST");
  assert(!running && attachCount==0);
  issue("SERVO_TEST");assert(running && pwmAttached && duties.back()==4915);
  issue("STOP");assert(!running && !pwmAttached && duties.back()==0);
  const auto count=duties.size();issue("SERVO_TEST");assert(duties.size()==count && !running);

  reset();issue("SERVO_TEST");fakeMillis+=1600;loop();
  assert(!running && !pwmAttached && Serial.output.find("LEASE_EXPIRED")!=std::string::npos);
  reset();issue("SERVO_TEST");fakeMillis+=1600;issue("PING");
  assert(!running && !pwmAttached);  // A late PING must not resurrect an expired lease.

  reset();issue("SERVO_TEST");
  for (int i=0;i<25 && running;++i) { fakeMillis+=400;issue("PING"); }
  assert(!running && !pwmAttached && attachCount==1 && detachCount==1);
  std::vector<uint32_t> expected={4915,4260,5570,4915,0};assert(duties==expected);
  assert(Serial.output.find("REASON:COMPLETE")!=std::string::npos);
  const auto completeCount=duties.size();issue("SERVO_TEST");assert(duties.size()==completeCount);

  reset();issue("SERVO_TEST");Serial.input=std::string(5000,'X');fakeMillis+=1600;loop();
  assert(!running && !pwmAttached);  // Serial flooding cannot starve timeout handling.

  reset();failAttach=true;issue("SERVO_TEST");assert(faulted && !running && !pwmAttached);
  reset();failWrite=true;issue("SERVO_TEST");assert(faulted && !running && !pwmAttached);
  reset();issue("SERVO_TEST");failDetach=true;issue("STOP");assert(faulted && !running);
  issue("ID");assert(Serial.output.find("PWM:FAULT")!=std::string::npos);

  reset();fakeMillis=UINT32_MAX-500;issue("SERVO_TEST");
  fakeMillis+=800;issue("PING");assert(running);
  fakeMillis+=1600;issue("PING");assert(!running && !pwmAttached);

  reset();issue("SERVO_TEST");fakeMillis+=10001;issue("PING");
  assert(!running && !pwmAttached && Serial.output.find("REASON:DEADLINE")!=std::string::npos);
  return 0;
}
