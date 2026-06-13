#pragma once
#include <stdint.h>

enum class State : uint8_t {
  IDLE = 0,      // 空闲：暗
  WORKING,       // 干活：蓝呼吸（tool 细分色）
  DONE,          // 完成：绿亮后渐暗
  NEEDS_YOU,     // 要介入：红慢闪
  ERROR,         // 出错：红快闪一下
  LOST,          // 失联：琥珀慢呼吸
  BOOT           // 开机动画
};

enum class ToolKind : uint8_t { NONE = 0, CODE, COMMAND, SEARCH };

struct Rgb { uint8_t r, g, b; };  // 纯逻辑用的颜色，不依赖 FastLED

struct Session {
  State state;
  ToolKind tool;        // 仅 WORKING 时有意义，用于分色
  uint32_t state_since_ms;   // 该状态进入时刻（millis），驱动动画相位
  uint32_t pulse_at_ms;      // 最近一次 tool 调用脉冲时刻（0 = 无）
};

// 纯函数：把会话列表渲染成 out[0..num_leds-1]。now_ms 由调用方传入。
// sessions 为空 → 整体 IDLE。多会话 → 分段（仅 num_leds>1 有意义）。
void render(const Session* sessions, uint8_t session_count,
           uint32_t now_ms, Rgb* out, uint8_t num_leds);

// 用户可调的显示设置（存 NVS，默认 = 计划 01 原值）
struct RenderSettings {
  uint8_t brightness;        // 0..255 全局亮度（在渲染末端统一施加）
  bool    animations;        // false = 各状态用静态基准色，不呼吸/闪
  uint8_t speed_pct;         // 动画速度百分比，100 = 原速；200 = 快一倍
  Rgb     col_working_code;
  Rgb     col_working_command;
  Rgb     col_working_search;
  Rgb     col_done;
  Rgb     col_needs_you;
  Rgb     col_error;
  Rgb     col_lost;
  Rgb     col_boot;
};

RenderSettings render_default_settings();        // 计划 01 原值
void render_set_settings(const RenderSettings& s);
RenderSettings render_get_settings();
