#pragma once
struct FakeWire {
  int result = 0;
  void begin(int sda, int scl, int) { assert(sda == 21 && scl == 22); }
  void setTimeOut(int) {}
  void beginTransmission(int address) { assert(address == 0x3C); }
  int endTransmission() { return result; }
};
static FakeWire Wire;
