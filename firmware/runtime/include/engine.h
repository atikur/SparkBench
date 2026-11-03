#pragma once
#include <stddef.h>
#include <stdint.h>

namespace sparkbench {
struct Step { bool pin25; bool pin26; const char *text; };
enum class Event { None, Apply, Complete, LeaseExpired, Deadline };

// Shared by production firmware and native behavioral tests. GPIO access is
// confined to the trusted adapter. All timing subtraction survives uint32 wrap.
class Engine {
 public:
  static constexpr uint32_t kDwellMs = 3000, kLeaseMs = 1500, kMaxRunMs = 30000;
  bool start(const Step *steps, size_t count, uint32_t now) {
    if (running_ || !steps || count == 0 || count > 8) return false;
    steps_ = steps; count_ = count; index_ = 0;
    started_ = applied_ = ping_ = now; running_ = true;
    return true;
  }
  void ping(uint32_t now) { if (running_) ping_ = now; }
  void applied(uint32_t now) { applied_ = now; }
  void stop() { running_ = false; }
  bool running() const { return running_; }
  size_t index() const { return index_; }
  const Step &step() const { return steps_[index_]; }
  Event tick(uint32_t now) {
    if (!running_) return Event::None;
    if (uint32_t(now - ping_) >= kLeaseMs) { stop(); return Event::LeaseExpired; }
    if (uint32_t(now - started_) >= kMaxRunMs) { stop(); return Event::Deadline; }
    if (uint32_t(now - applied_) < kDwellMs) return Event::None;
    if (++index_ >= count_) { stop(); return Event::Complete; }
    applied_ = now;
    return Event::Apply;
  }
 private:
  const Step *steps_ = nullptr;
  size_t count_ = 0, index_ = 0;
  uint32_t started_ = 0, applied_ = 0, ping_ = 0;
  bool running_ = false;
};
}  // namespace sparkbench
