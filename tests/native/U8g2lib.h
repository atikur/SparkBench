#pragma once
#define U8G2_R0 0
#define U8X8_PIN_NONE 255
static const char *u8g2_font_6x12_tr = "font";
static const char *u8g2_font_helvB10_tr = "bold";
struct U8G2_SH1106_128X64_NONAME_F_HW_I2C {
  U8G2_SH1106_128X64_NONAME_F_HW_I2C(int, int, int scl, int sda) { assert(scl == 22 && sda == 21); }
  void clearBuffer() {}
  void drawFrame(int, int, int, int) {}
  void setFont(const char *) {}
  int getStrWidth(const char *text) { return int(strlen(text))*9; }
  void drawStr(int, int, const char *) {}
  void sendBuffer() { fakeMillis += 128; }
  void setI2CAddress(int address) { assert(address == 0x78); }
  void setBusClock(int) {}
  void begin() {}
  void setContrast(int) {}
};
