#pragma once
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>
#include <map>
#include <assert.h>
#define LOW 0
#define HIGH 1
#define OUTPUT 1
static unsigned long fakeMillis = 0;
static std::map<int,int> pins;
static bool pwmAttached = false, failAttach = false, failWrite = false, failDetach = false;
static unsigned attachCount = 0, detachCount = 0;
static std::vector<uint32_t> duties;
inline unsigned long millis() { return fakeMillis; }
inline void delay(unsigned long value) { fakeMillis += value; }
inline void digitalWrite(int pin,int value) { assert(pin==25 || pin==26 || pin==27);pins[pin]=value; }
inline void pinMode(int pin,int) { assert(pin==25 || pin==26 || pin==27); }
inline bool ledcAttach(uint8_t pin,uint32_t hz,uint8_t bits) {
  assert(pin==27 && hz==50 && bits==16);++attachCount;
  if (failAttach) return false;
  pwmAttached=true;return true;
}
inline bool ledcWrite(uint8_t pin,uint32_t duty) {
  assert(pin==27);
  if (duty) { assert(pwmAttached);assert(duty>=4260 && duty<=5570); }
  duties.push_back(duty);
  return !failWrite;
}
inline bool ledcDetach(uint8_t pin) {
  assert(pin==27);++detachCount;
  if (failDetach) return false;
  pwmAttached=false;return true;
}
struct FakeSerial {
  std::string input,output;
  void begin(int) {}
  size_t available() { return input.size(); }
  int read() { char c=input.front();input.erase(0,1);return c; }
  void println(const char *s) { output+=s;output+='\n'; }
  void printf(const char *format,...) {
    char line[512];va_list args;va_start(args,format);vsnprintf(line,sizeof(line),format,args);va_end(args);output+=line;
  }
};
static FakeSerial Serial;
