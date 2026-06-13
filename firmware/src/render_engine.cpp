#include "render_engine.h"
#include <stdint.h>

namespace {
// 各状态基准色
constexpr Rgb COL_IDLE   = {0, 0, 0};
constexpr Rgb COL_DONE   = {0, 200, 40};
constexpr Rgb COL_NEEDS  = {220, 20, 20};
constexpr Rgb COL_ERROR  = {220, 20, 20};
constexpr Rgb COL_LOST   = {120, 70, 0};   // 暗琥珀
constexpr Rgb COL_BOOT   = {0, 80, 120};

// WORKING 按工具分色
Rgb working_color(ToolKind t) {
  switch (t) {
    case ToolKind::COMMAND: return {120, 0, 200};  // 紫：跑命令
    case ToolKind::SEARCH:  return {0, 160, 160};   // 青：搜索
    case ToolKind::CODE:
    default:                return {0, 60, 220};    // 蓝：写码
  }
}

// 三角波 0..255，period 毫秒
uint8_t tri_wave(uint32_t elapsed, uint32_t period) {
  uint32_t p = elapsed % period;
  uint32_t half = period / 2;
  uint32_t up = (p < half) ? p : (period - p);     // 0..half
  return (uint8_t)((up * 255) / half);
}
// 方波：前半周期 255，后半 0
uint8_t square_wave(uint32_t elapsed, uint32_t period) {
  return (elapsed % period) < (period / 2) ? 255 : 0;
}
Rgb scale(Rgb c, uint8_t b) {
  return Rgb{ (uint8_t)(c.r * b / 255),
             (uint8_t)(c.g * b / 255),
             (uint8_t)(c.b * b / 255) };
}

// 给单个会话算出「带动画的颜色」
Rgb animated_color(const Session& s, uint32_t now_ms) {
  uint32_t e = now_ms - s.state_since_ms;
  switch (s.state) {
    case State::WORKING: {
      uint8_t b = 60 + (uint8_t)((uint16_t)tri_wave(e, 2000) * 195 / 255); // 呼吸 60..255
      return scale(working_color(s.tool), b);
    }
    case State::NEEDS_YOU:
      return scale(COL_NEEDS, square_wave(e, 1200));      // 慢闪
    case State::ERROR:
      return e < 300 ? COL_ERROR : Rgb{0,0,0};            // 快闪一下
    case State::DONE: {
      if (e >= 4500) return Rgb{0,0,0};
      uint8_t b = (uint8_t)(255 - (e * 255 / 4500));      // 渐暗
      return scale(COL_DONE, b);
    }
    case State::LOST: {
      uint8_t b = 20 + (uint8_t)((uint16_t)tri_wave(e, 3000) * 80 / 255); // 暗呼吸 20..100
      return scale(Rgb{255,150,0}, b);
    }
    case State::BOOT:
      return COL_BOOT;
    case State::IDLE:
    default:
      return COL_IDLE;
  }
}
} // namespace

void render(const Session* sessions, uint8_t session_count,
           uint32_t now_ms, Rgb* out, uint8_t num_leds) {
  if (session_count == 0) {
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = Rgb{0,0,0};
    return;
  }
  if (session_count == 1 && sessions[0].state == State::BOOT) {
    uint32_t e = now_ms - sessions[0].state_since_ms;
    uint8_t head = (num_leds > 1) ? (uint8_t)((e / 80) % num_leds) : 0;
    for (uint8_t i = 0; i < num_leds; ++i)
      out[i] = (i == head) ? Rgb{0,120,160} : Rgb{0,0,0};
    return;
  }
  if (session_count == 1 || num_leds == 1) {
    Rgb c = animated_color(sessions[0], now_ms);
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = c;
    return;
  }
  // 多会话：均分像素段，每段一个会话（最多 num_leds 个会话）
  uint8_t shown = session_count < num_leds ? session_count : num_leds;
  for (uint8_t i = 0; i < num_leds; ++i) {
    uint8_t seg = (uint16_t)i * shown / num_leds;   // i 落在哪段
    out[i] = animated_color(sessions[seg], now_ms);
  }
}
