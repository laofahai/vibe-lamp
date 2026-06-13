#include "render_engine.h"
#include <stdint.h>

namespace {
RenderSettings g_settings;     // 当前生效设置
bool g_inited = false;

void ensure_inited() {
  if (!g_inited) { g_settings = render_default_settings(); g_inited = true; }
}

// WORKING 按工具分色（读运行时设置）
Rgb working_color(ToolKind t) {
  switch (t) {
    case ToolKind::COMMAND: return g_settings.col_working_command;  // 紫：跑命令
    case ToolKind::SEARCH:  return g_settings.col_working_search;   // 青：搜索
    case ToolKind::CODE:
    default:                return g_settings.col_working_code;     // 蓝：写码
  }
}

// 三角波 0..255，period 毫秒
uint8_t tri_wave(uint32_t elapsed, uint32_t period) {
  if (period < 2) return 0;                        // 防御除零：period 为 0/1 时 half=0
  uint32_t p = elapsed % period;
  uint32_t half = period / 2;
  uint32_t up = (p < half) ? p : (period - p);     // 0..half
  return (uint8_t)((up * 255) / half);
}
// 方波：前半周期 255，后半 0
uint8_t square_wave(uint32_t elapsed, uint32_t period) {
  if (period < 2) return 0;                        // 防御除零：period 为 0 时取模会崩
  return (elapsed % period) < (period / 2) ? 255 : 0;
}
Rgb scale(Rgb c, uint8_t b) {
  return Rgb{ (uint8_t)(c.r * b / 255),
             (uint8_t)(c.g * b / 255),
             (uint8_t)(c.b * b / 255) };
}

// 速度百分比缩放周期（100=原速，200=快一倍）
uint32_t scaled(uint32_t period) {
  uint16_t pct = g_settings.speed_pct ? g_settings.speed_pct : 100;
  return period * 100 / pct;
}

// 不带动画的基准色（关动画时直接用）
Rgb base_for(const Session& s) {
  switch (s.state) {
    case State::WORKING:  return working_color(s.tool);
    case State::DONE:     return g_settings.col_done;
    case State::NEEDS_YOU:return g_settings.col_needs_you;
    case State::ERROR:    return g_settings.col_error;
    case State::LOST:     return g_settings.col_lost;
    case State::BOOT:     return g_settings.col_boot;
    default:              return Rgb{0,0,0};
  }
}

// 给单个会话算出「带动画的颜色」
Rgb animated_color(const Session& s, uint32_t now_ms) {
  ensure_inited();
  if (!g_settings.animations) return base_for(s);    // 关动画 = 静态基准色
  uint32_t e = now_ms - s.state_since_ms;
  switch (s.state) {
    case State::WORKING: {
      uint8_t b = 60 + (uint8_t)((uint16_t)tri_wave(e, scaled(2000)) * 195 / 255); // 呼吸 60..255
      return scale(working_color(s.tool), b);
    }
    case State::NEEDS_YOU:
      return scale(g_settings.col_needs_you, square_wave(e, scaled(1200)));      // 慢闪
    case State::ERROR:
      return e < scaled(300) ? g_settings.col_error : Rgb{0,0,0};                // 快闪一下
    case State::DONE: {
      uint32_t win = scaled(4500);
      if (e >= win) return Rgb{0,0,0};
      return scale(g_settings.col_done, (uint8_t)(255 - (e * 255 / win)));       // 渐暗
    }
    case State::LOST: {
      uint8_t b = 20 + (uint8_t)((uint16_t)tri_wave(e, scaled(3000)) * 80 / 255); // 暗呼吸 20..100
      return scale(g_settings.col_lost, b);
    }
    case State::BOOT:
      return g_settings.col_boot;
    case State::IDLE:
    default:
      return Rgb{0,0,0};
  }
}

// 渲染末端统一施加亮度——给每个输出像素乘 brightness/255
void apply_brightness(Rgb* out, uint8_t num_leds) {
  ensure_inited();
  uint8_t b = g_settings.brightness;
  for (uint8_t i = 0; i < num_leds; ++i) {
    out[i].r = (uint8_t)(out[i].r * b / 255);
    out[i].g = (uint8_t)(out[i].g * b / 255);
    out[i].b = (uint8_t)(out[i].b * b / 255);
  }
}
} // namespace

RenderSettings render_default_settings() {
  RenderSettings s;
  s.brightness = 160;          // = 计划01 MAX_BRIGHTNESS
  s.animations = true;
  s.speed_pct = 100;
  s.col_working_code    = {0, 60, 220};
  s.col_working_command = {120, 0, 200};
  s.col_working_search  = {0, 160, 160};
  s.col_done      = {0, 200, 40};
  s.col_needs_you = {220, 20, 20};
  s.col_error     = {220, 20, 20};
  s.col_lost      = {255, 150, 0};   // = 计划01 animated_color LOST 实际缩放的色
  s.col_boot      = {0, 120, 160};   // = 计划01 BOOT 扫描头色
  return s;
}
void render_set_settings(const RenderSettings& s) { g_settings = s; g_inited = true; }
RenderSettings render_get_settings() { ensure_inited(); return g_settings; }

void render(const Session* sessions, uint8_t session_count,
           uint32_t now_ms, Rgb* out, uint8_t num_leds) {
  ensure_inited();
  if (session_count == 0) {
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = Rgb{0,0,0};
    apply_brightness(out, num_leds);
    return;
  }
  if (session_count == 1 && sessions[0].state == State::BOOT) {
    uint32_t e = now_ms - sessions[0].state_since_ms;
    uint8_t head = (num_leds > 1) ? (uint8_t)((e / 80) % num_leds) : 0;
    for (uint8_t i = 0; i < num_leds; ++i)
      out[i] = (i == head) ? g_settings.col_boot : Rgb{0,0,0};
    apply_brightness(out, num_leds);
    return;
  }
  if (session_count == 1 || num_leds == 1) {
    Rgb c = animated_color(sessions[0], now_ms);
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = c;
    apply_brightness(out, num_leds);
    return;
  }
  // 多会话：均分像素段，每段一个会话（最多 num_leds 个会话）
  uint8_t shown = session_count < num_leds ? session_count : num_leds;
  for (uint8_t i = 0; i < num_leds; ++i) {
    uint8_t seg = (uint16_t)i * shown / num_leds;   // i 落在哪段
    out[i] = animated_color(sessions[seg], now_ms);
  }
  apply_brightness(out, num_leds);
}
