#pragma once
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <vector>
#include <map>
#include <assert.h>
#define HIGH 1
#define LOW 0
#define OUTPUT 1
static unsigned long fakeMillis = 0;
static std::map<int, int> pins;
inline unsigned long millis() { return fakeMillis; }
inline void delay(unsigned long value) { fakeMillis += value; }
inline void digitalWrite(int pin, int value) { assert(pin == 25 || pin == 26); pins[pin] = value; }
inline void pinMode(int pin, int) { assert(pin == 25 || pin == 26); }
struct FakeSerial {
  std::string input, output;
  void begin(int) {}
  size_t available() { return input.size(); }
  int read() { char c = input.front(); input.erase(0, 1); return c; }
  void println(const char *s) { output += s; output += '\n'; }
  void printf(const char *format, ...) {
    char line[512]; va_list args; va_start(args, format);
    vsnprintf(line, sizeof(line), format, args); va_end(args); output += line;
  }
};
static FakeSerial Serial;
