// Trusted full-rig adapter. Only fixed compiled tables can drive outputs.
// Build-only preparation; installation/execution requires separate authorization.
#include <Arduino.h>
#include <Wire.h>
#include <U8g2lib.h>
struct Step { bool pin25; bool pin26; uint16_t pulse; const char *text; };
#include "plan_data.h"

static constexpr uint32_t kDwellMs=3000, kLeaseMs=1500, kDeadlineMs=30000;
static constexpr Step kDiscovery[]={{false,false,0,"DARK"},{true,false,0,"P25"},
  {false,false,0,"DARK"},{false,true,0,"P26"},{false,false,0,"DARK END"}};
static const Step *steps=nullptr;
static size_t count=0,stepIndex=0;
static bool running=false,attached=false,faulted=false,consumed=false,displayReady=false,discovery=false;
static uint32_t started=0,applied=0,lastPing=0,heartbeat=0;
static char command[48]; static size_t commandLength=0; static bool overflow=false;
U8G2_SH1106_128X64_NONAME_F_HW_I2C display(U8G2_R0,U8X8_PIN_NONE,22,21);

static void show(const char *text) {
  if (!displayReady) return;
  display.clearBuffer();display.drawFrame(0,0,128,64);display.setFont(u8g2_font_6x12_tr);
  display.drawStr(5,13,"SparkBench");display.drawStr(5,28,text);
  display.drawStr(5,43,kProfile);display.drawStr(5,58,"Full-rig runtime");display.sendBuffer();
}
static void stopOutputs(const char *reason) {
  running=false;
  if (attached) {
    const bool wrote=ledcWrite(27,0),detached=ledcDetach(27);
    attached=!detached;
    if (!wrote || !detached) faulted=true;
  }
  digitalWrite(27,LOW);pinMode(27,OUTPUT);digitalWrite(25,LOW);digitalWrite(26,LOW);
  // Acknowledgement follows PWM/LED shutdown, before potentially slow I2C.
  Serial.printf("FULL_STOPPED REASON:%s PWM:%s UPTIME_MS:%lu\n",reason,faulted?"FAULT":"OFF",millis());
  show(reason);
}
static bool expired() {
  if (!running) return false;
  const uint32_t now=uint32_t(millis());
  if (uint32_t(now-started)>=kDeadlineMs) {stopOutputs("DEADLINE");return true;}
  if (uint32_t(now-lastPing)>=kLeaseMs) {stopOutputs("LEASE_EXPIRED");return true;}
  return false;
}
static bool apply() {
  const auto &row=steps[stepIndex];
  if (!discovery) {
    if (row.pulse<kMinPulse || row.pulse>kMaxPulse || row.pulse<500 || row.pulse>2500) {
      faulted=true;stopOutputs("RANGE_ERROR");return false;
    }
    if (!attached) {
      if (!ledcAttach(27,50,16)) {faulted=true;stopOutputs("ATTACH_ERROR");return false;}
      attached=true;
    }
    if (!ledcWrite(27,(uint32_t(row.pulse)*65535UL+10000UL)/20000UL)) {
      faulted=true;stopOutputs("WRITE_ERROR");return false;
    }
  }
  digitalWrite(25,row.pin25?HIGH:LOW);digitalWrite(26,row.pin26?HIGH:LOW);show(row.text);
  // I2C time is included in the lease/deadline; it cannot revive an expired run.
  if (expired()) return false;
  applied=uint32_t(millis());
  Serial.printf("FULL_STEP:%u PULSE_US:%u UPTIME_MS:%lu\n",unsigned(stepIndex+1),row.pulse,millis());
  return true;
}
static void handle() {
  if (!strcmp(command,"STOP")) {stopOutputs("STOP");return;}
  if (!strcmp(command,"ID") || !strcmp(command,"STATUS")) {
    Serial.printf("SPARKBENCH FULL_RUNTIME V:1 PLAN:%s CAL:%s PROFILE:%s MODE:%s OLED:%s PWM:%s AVAILABLE:%u\n",
      kPlanHash,kCalibrationHash,kProfile,running?"RUNNING":"IDLE",displayReady?"ACK":"MISSING",
      faulted?"FAULT":attached?"ON":"OFF",kEnabled&&!consumed&&!faulted);
    return;
  }
  if (!strcmp(command,"PING")) {
    if (running && !expired()) lastPing=uint32_t(millis());
    return;
  }
  const bool probe=!strcmp(command,"DISCOVER");
  const bool leds=!strcmp(kProfile,"BEHAVIOR") && !strcmp(command,"LEDS");
  const bool motion=(!strcmp(kProfile,"CALIBRATION") && !strcmp(command,"CALIBRATE")) ||
                    (!strcmp(kProfile,"BEHAVIOR") && !strcmp(command,"EXECUTE"));
  if (!probe && !leds && !motion) {Serial.println("FULL_ERROR COMMAND_REJECTED");return;}
  if (!kEnabled || faulted || running || consumed || !displayReady) {
    Serial.println("FULL_ERROR UNAVAILABLE");return;
  }
  // Every sequence is one-shot per boot. STOP/failed driver/start never re-arm.
  consumed=true;discovery=probe||leds;steps=probe?kDiscovery:kPlan;
  count=probe?sizeof(kDiscovery)/sizeof(kDiscovery[0]):sizeof(kPlan)/sizeof(kPlan[0]);stepIndex=0;
  if (!count || count>8) {faulted=true;stopOutputs("PLAN_ERROR");return;}
  running=true;started=lastPing=uint32_t(millis());apply();
}
void setup() {
  for (uint8_t p : {uint8_t(25),uint8_t(26),uint8_t(27)}) {digitalWrite(p,LOW);pinMode(p,OUTPUT);}
  Serial.begin(115200);delay(1500);Serial.println("SPARKBENCH FULL_RUNTIME BOOT PWM:OFF");
  Wire.begin(21,22,100000);Wire.setTimeOut(50);Wire.beginTransmission(0x3C);
  if (Wire.endTransmission()==0) {
    display.setI2CAddress(0x3C<<1);display.setBusClock(100000);display.begin();display.setContrast(128);displayReady=true;
  }
  stopOutputs("READY");
}
void loop() {
  expired();  // Check before handling a PING or any new input.
  for (unsigned n=0;n<64 && Serial.available();++n) {
    const char c=char(Serial.read());if(c=='\r')continue;
    if(c=='\n') {
      command[commandLength]='\0';
      if(overflow)Serial.println("FULL_ERROR COMMAND_TOO_LONG");else handle();
      commandLength=0;overflow=false;
    } else if(c<'A' || c>'Z')overflow=true;
    else if(!overflow && commandLength+1<sizeof(command))command[commandLength++]=c;
    else overflow=true;
  }
  if (running && !expired() && uint32_t(uint32_t(millis())-applied)>=kDwellMs) {
    if (++stepIndex>=count) stopOutputs("COMPLETE");else apply();
  }
  const uint32_t now=uint32_t(millis());
  if(uint32_t(now-heartbeat)>=1000) {
    heartbeat=now;Serial.printf("FULL_ALIVE UPTIME_MS:%lu MODE:%s PWM:%s\n",millis(),running?"RUNNING":"IDLE",faulted?"FAULT":attached?"ON":"OFF");
  }
  delay(2);
}
