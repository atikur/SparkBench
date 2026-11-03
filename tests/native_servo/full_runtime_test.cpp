// Execute the production adapter against fake hardware. No physical evidence.
#include "main.cpp"
static void issue(const std::string &value) {
  Serial.input+=value+"\n";while(!Serial.input.empty())loop();
}
static void reset() {
  fakeMillis=0;pins.clear();Serial.input.clear();Serial.output.clear();duties.clear();
  pwmAttached=failAttach=failWrite=failDetach=false;attachCount=detachCount=0;
  running=attached=faulted=consumed=displayReady=discovery=false;count=stepIndex=0;steps=nullptr;
  started=applied=lastPing=heartbeat=0;commandLength=0;overflow=false;Wire.result=0;setup();
  assert(!running&&!pwmAttached&&duties.empty()&&attachCount==0&&pins[27]==LOW);
}
int main() {
  const char *start=!strcmp(kProfile,"CALIBRATION")?"CALIBRATE":"EXECUTE";
  if(!kEnabled){reset();issue("EXECUTE");issue("CALIBRATE");issue("DISCOVER");assert(!running&&duties.empty());return 0;}
  reset();issue("RUN");issue(!strcmp(start,"CALIBRATE")?"EXECUTE":"CALIBRATE");issue("PULSE 2500");issue(std::string(200,'X')+start);
  issue(std::string(start)+std::string(1,'\0')+"BAD");
  assert(!running&&duties.empty());
  issue(start);assert(running&&pwmAttached&&duties.back()==(uint32_t(kPlan[0].pulse)*65535UL+10000UL)/20000UL);
  issue("STOP");assert(!running&&!pwmAttached&&pins[25]==LOW&&pins[26]==LOW);
  const auto stopped=duties.size();issue(start);assert(duties.size()==stopped);
  reset();issue(start);fakeMillis+=1600;issue("PING");assert(!running&&!pwmAttached);
  assert(Serial.output.find("REASON:LEASE_EXPIRED")!=std::string::npos);
  reset();issue(start);
  for(unsigned n=0;n<100&&running;++n){fakeMillis+=400;issue("PING");}
  assert(!running&&!pwmAttached&&Serial.output.find("REASON:COMPLETE")!=std::string::npos);
  std::vector<uint32_t> expected;
  for(const auto &s:kPlan)expected.push_back((uint32_t(s.pulse)*65535UL+10000UL)/20000UL);
  expected.push_back(0);assert(duties==expected);
  reset();issue("DISCOVER");
  for(unsigned n=0;n<100&&running;++n){fakeMillis+=400;issue("PING");}
  assert(!running&&attachCount==0&&duties.empty()&&pins[27]==LOW);
  if(!strcmp(kProfile,"BEHAVIOR")) {
    reset();issue("LEDS");assert(running&&attachCount==0&&duties.empty());issue("STOP");
    assert(!running&&attachCount==0&&duties.empty());
  }
  reset();displayReady=false;issue(start);assert(!running&&duties.empty());
  reset();issue(start);Serial.input=std::string(5000,'X');fakeMillis+=1600;loop();assert(!running&&!pwmAttached);
  reset();failAttach=true;issue(start);assert(faulted&&!running&&!pwmAttached);
  reset();failWrite=true;issue(start);assert(faulted&&!running&&!pwmAttached);
  reset();issue(start);failDetach=true;issue("STOP");assert(faulted&&!running);
  issue("ID");assert(Serial.output.find("PWM:FAULT")!=std::string::npos);
  reset();fakeMillis=UINT32_MAX-500;issue(start);fakeMillis+=800;issue("PING");assert(running);
  fakeMillis+=1600;issue("PING");assert(!running&&!pwmAttached);
  reset();issue(start);fakeMillis+=30001;issue("PING");assert(!running&&!pwmAttached);
  assert(Serial.output.find("REASON:DEADLINE")!=std::string::npos);
  return 0;
}
