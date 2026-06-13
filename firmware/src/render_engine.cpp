#include "render_engine.h"

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

Rgb base_color(const Session& s) {
  switch (s.state) {
    case State::WORKING:  return working_color(s.tool);
    case State::DONE:     return COL_DONE;
    case State::NEEDS_YOU:return COL_NEEDS;
    case State::ERROR:    return COL_ERROR;
    case State::LOST:     return COL_LOST;
    case State::BOOT:     return COL_BOOT;
    case State::IDLE:
    default:              return COL_IDLE;
  }
}
} // namespace

void render(const Session* sessions, uint8_t session_count,
           uint32_t /*now_ms*/, Rgb* out, uint8_t num_leds) {
  if (session_count == 0) {
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = COL_IDLE;
    return;
  }
  // Task 2 先只处理第一个会话，铺满全部像素（动画/分段后续任务加）
  Rgb c = base_color(sessions[0]);
  for (uint8_t i = 0; i < num_leds; ++i) out[i] = c;
}
