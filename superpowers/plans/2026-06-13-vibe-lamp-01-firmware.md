# Vibe Lamp 实现计划 01 — ESP32 固件

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 设计依据：`superpowers/specs/2026-06-13-vibe-lamp-design.md`。这是 v1 五个计划中的第 1 个，**只覆盖 ESP32 固件**，产出一个「能被 curl 点亮、支持四种显示硬件、带失联看门狗」的独立可验证设备。守护进程/钩子/Codex/网页配网是后续计划。

**Goal:** ESP32 固件——接收 HTTP 推来的「会话状态」，渲染成颜色+动画，驱动 RGB LED / WS2812 灯环/灯条 / 分立 LED；断推 30s 自动进入失联显示。

**Architecture:** 三个解耦层：(1) **渲染引擎** 纯逻辑——把「会话状态列表 + 当前时间」算成每像素 RGB（无硬件依赖，native 单测）；(2) **显示驱动** 把每像素 RGB 落到具体硬件（RGB LED 走 ledc PWM / WS2812 走 FastLED），编译期 `DISPLAY_TYPE` 选；(3) **网络层** WiFi + mDNS + HTTP 端点，解析 JSON 喂给渲染引擎，并维护看门狗。

**Tech Stack:** PlatformIO + Arduino-ESP32 core 3.x、FastLED、ArduinoJson、ESP32 WebServer/ESPmDNS/WiFi、Unity（native 单测）。

---

## 文件结构

```
firmware/
├── platformio.ini              # 两个 env：esp32（上板）+ native（跑纯逻辑单测）
├── include/
│   └── config.h                # DISPLAY_TYPE、NUM_LEDS、引脚、超时、mDNS 名
├── src/
│   ├── main.cpp                # setup/loop 装配
│   ├── render_engine.h         # 纯逻辑接口：State 枚举、Session、SessionView、render()
│   ├── render_engine.cpp       # 纯逻辑实现：状态→每像素 Rgb（含动画、分段）
│   ├── display.h               # IDisplay 抽象接口
│   ├── display_factory.cpp     # 按 DISPLAY_TYPE 返回对应驱动实例
│   ├── display_rgb_led.cpp     # 单颗共阴 RGB LED（ledc PWM）
│   ├── display_ws2812.cpp      # WS2812 灯环/灯条（FastLED）
│   ├── net.h / net.cpp         # WiFi 连接 + mDNS 广播 vibelamp.local
│   └── api_server.h/.cpp       # WebServer：POST /state、GET /health；解析 JSON
├── test/
│   └── test_render_engine/
│       └── test_main.cpp       # Unity 单测（native env）
└── .gitignore                  # 含 include/secrets.h
```

**职责边界**：`render_engine` 不 include 任何 Arduino/FastLED 头，只依赖 `<stdint.h>`——保证能在 native 跑单测。硬件细节全在 display 驱动里。`api_server` 只做 JSON 解析 + 调 render_engine 的状态写入，不碰硬件。

**关键类型（贯穿全程，先在此锁定签名）**：

```cpp
// render_engine.h —— 所有任务都以这些签名为准
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
```

---

## Task 1: PlatformIO 工程骨架（esp32 + native 双 env）

**Files:**
- Create: `firmware/platformio.ini`
- Create: `firmware/include/config.h`
- Create: `firmware/src/main.cpp`
- Create: `firmware/.gitignore`

- [ ] **Step 1: 写 `platformio.ini`**

```ini
[platformio]
default_envs = esp32

[env:esp32]
platform = espressif32
board = esp32dev          ; 手上的 ESP32 开发板；换板改这里
framework = arduino
monitor_speed = 115200
lib_deps =
    fastled/FastLED@^3.9.0
    bblanchon/ArduinoJson@^7.2.0
build_flags =
    -DDISPLAY_TYPE=DISPLAY_RGB_LED   ; 打样默认单颗 RGB LED

[env:native]
platform = native
build_flags =
    -DDISPLAY_TYPE=DISPLAY_RGB_LED
    -std=gnu++17
test_filter = test_render_engine
```

- [ ] **Step 2: 写 `include/config.h`**

```cpp
#pragma once
#include <stdint.h>

// —— 显示硬件类型（由 build_flags 的 -DDISPLAY_TYPE 选择）——
#define DISPLAY_RGB_LED     1   // 单颗共阴 RGB LED，3 路 PWM
#define DISPLAY_WS2812_RING 2   // WS2812 灯环
#define DISPLAY_WS2812_STRIP 3  // WS2812 灯条
#define DISPLAY_DISCRETE    4   // 多颗分立定色 LED

#ifndef DISPLAY_TYPE
#define DISPLAY_TYPE DISPLAY_RGB_LED
#endif

// —— 像素数 ——
#if DISPLAY_TYPE == DISPLAY_RGB_LED
  #define NUM_LEDS 1
#elif DISPLAY_TYPE == DISPLAY_WS2812_RING
  #define NUM_LEDS 16
#elif DISPLAY_TYPE == DISPLAY_WS2812_STRIP
  #define NUM_LEDS 8
#else
  #define NUM_LEDS 3
#endif

// —— 引脚 ——
// RGB LED（共阴；共阳需在驱动里反相）
#define PIN_RGB_R 25
#define PIN_RGB_G 26
#define PIN_RGB_B 27
// WS2812 数据脚
#define PIN_WS2812 4

// —— PWM ——
#define LEDC_FREQ 5000
#define LEDC_RES  8        // 8 bit：0..255

// —— 网络 ——
#define MDNS_HOST "vibelamp"          // → vibelamp.local
#define HTTP_PORT 80
#define WATCHDOG_TIMEOUT_MS 30000UL   // 30s 无 /state → 失联

// —— 亮度上限（保护眼睛/限流）——
#define MAX_BRIGHTNESS 160
```

- [ ] **Step 3: 写最小 `src/main.cpp`（先只串口打印，验证工具链）**

```cpp
#include <Arduino.h>
#include "config.h"

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("VibeLamp boot. DISPLAY_TYPE=%d NUM_LEDS=%d\n", DISPLAY_TYPE, NUM_LEDS);
}

void loop() {
  delay(1000);
}
```

- [ ] **Step 4: 写 `.gitignore`**

```gitignore
.pio/
include/secrets.h
```

- [ ] **Step 5: 编译验证（不需要插板）**

Run: `cd firmware && pio run -e esp32`
Expected: 编译成功，`SUCCESS`。（若无开发板也能编译通过。）

- [ ] **Step 6: 提交**

```bash
cd firmware && git add platformio.ini include/config.h src/main.cpp .gitignore
git commit -m "feat(firmware): PlatformIO 骨架 + config.h"
```

---

## Task 2: 渲染引擎纯逻辑——静态颜色（TDD，native）

先做「每个状态的基准色」，动画在 Task 3 加。

**Files:**
- Create: `firmware/src/render_engine.h`（用上面「关键类型」的完整内容）
- Create: `firmware/src/render_engine.cpp`
- Create: `firmware/test/test_render_engine/test_main.cpp`

- [ ] **Step 1: 写失败测试**

`test/test_render_engine/test_main.cpp`:

```cpp
#include <unity.h>
#include "render_engine.h"

static Rgb px;  // 单像素缓冲

static Session mk(State s, ToolKind t = ToolKind::NONE) {
  return Session{ s, t, /*state_since_ms*/0, /*pulse_at_ms*/0 };
}

void test_empty_sessions_is_idle_dark() {
  render(nullptr, 0, /*now*/0, &px, 1);
  TEST_ASSERT_EQUAL_UINT8(0, px.r);
  TEST_ASSERT_EQUAL_UINT8(0, px.g);
  TEST_ASSERT_EQUAL_UINT8(0, px.b);
}

void test_needs_you_is_reddish() {
  Session s = mk(State::NEEDS_YOU);
  render(&s, 1, /*now*/0, &px, 1);   // t=0：闪烁相位为「亮」
  TEST_ASSERT_GREATER_THAN_UINT8(100, px.r);
  TEST_ASSERT_LESS_THAN_UINT8(60, px.g);
  TEST_ASSERT_LESS_THAN_UINT8(60, px.b);
}

void test_working_code_is_bluish() {
  Session s = mk(State::WORKING, ToolKind::CODE);
  render(&s, 1, /*now*/0, &px, 1);   // t=0：呼吸相位最亮
  TEST_ASSERT_GREATER_THAN_UINT8(px.r, px.b);  // 蓝 > 红
}

void setUp() {} void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_empty_sessions_is_idle_dark);
  RUN_TEST(test_needs_you_is_reddish);
  RUN_TEST(test_working_code_is_bluish);
  return UNITY_END();
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd firmware && pio test -e native`
Expected: 编译失败（`render_engine.h` 不存在 / `render` 未定义）。

- [ ] **Step 3: 写 `render_engine.h`**

把上面「关键类型」一节的完整代码写入 `src/render_engine.h`（含 `#pragma once`、枚举、结构体、`render()` 声明）。

- [ ] **Step 4: 写 `render_engine.cpp`（先静态色，动画占位为常亮）**

```cpp
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
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd firmware && pio test -e native`
Expected: 3 个测试全 PASS。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/render_engine.h src/render_engine.cpp test/
git commit -m "feat(firmware): 渲染引擎静态色 + native 单测"
```

---

## Task 3: 渲染引擎动画（呼吸/慢闪/快闪/渐暗/失联呼吸/脉冲）（TDD）

动画都用 `now_ms` 算相位，纯函数、可在 native 用固定时间戳断言。

**Files:**
- Modify: `firmware/src/render_engine.cpp`
- Modify: `firmware/test/test_render_engine/test_main.cpp`

- [ ] **Step 1: 追加失败测试**

在 `test_main.cpp` 追加（并在 `main()` 里 `RUN_TEST` 它们）：

```cpp
// 工具函数：按相位取亮度，断言「呼吸」在波峰/波谷不同
void test_working_breathes() {
  Session s = mk(State::WORKING, ToolKind::CODE);
  s.state_since_ms = 0;
  Rgb peak, trough;
  render(&s, 1, 0,    &peak,   1);   // 相位 0 → 最亮
  render(&s, 1, 1000, &trough, 1);   // 半周期 → 最暗（周期 2000ms）
  TEST_ASSERT_GREATER_THAN_UINT8(peak.b / 2, peak.b);     // 占位避免优化
  TEST_ASSERT_TRUE(trough.b < peak.b);                    // 暗于波峰
}

void test_needs_you_blinks_off() {
  Session s = mk(State::NEEDS_YOU);
  s.state_since_ms = 0;
  Rgb on, off;
  render(&s, 1, 0,   &on,  1);   // 慢闪：亮半周期
  render(&s, 1, 600, &off, 1);   // 暗半周期（周期 1200ms）
  TEST_ASSERT_GREATER_THAN_UINT8(100, on.r);
  TEST_ASSERT_LESS_THAN_UINT8(30, off.r);   // 灭
}

void test_done_fades_out() {
  Session s = mk(State::DONE);
  s.state_since_ms = 0;
  Rgb early, late;
  render(&s, 1, 0,    &early, 1);   // 刚完成：亮
  render(&s, 1, 4000, &late,  1);   // 4s 后：基本暗（渐暗窗 ~4500ms）
  TEST_ASSERT_GREATER_THAN_UINT8(100, early.g);
  TEST_ASSERT_LESS_THAN_UINT8(early.g, late.g + 1);  // late 不亮于 early
  TEST_ASSERT_LESS_THAN_UINT8(40, late.g);
}

void test_error_flashes_then_settles() {
  Session s = mk(State::ERROR);
  s.state_since_ms = 0;
  Rgb flash, after;
  render(&s, 1, 0,   &flash, 1);   // 快闪窗内：红
  render(&s, 1, 500, &after, 1);   // 快闪窗后（~300ms）：灭，等转译器推下一状态
  TEST_ASSERT_GREATER_THAN_UINT8(120, flash.r);
  TEST_ASSERT_LESS_THAN_UINT8(40, after.r);
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd firmware && pio test -e native`
Expected: 新增测试 FAIL（当前是常亮，无相位变化）。

- [ ] **Step 3: 实现动画**

在 `render_engine.cpp` 的匿名 namespace 加亮度工具，并重写 `render()`：

```cpp
#include <stdint.h>

namespace {
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
  Rgb c = animated_color(sessions[0], now_ms);
  for (uint8_t i = 0; i < num_leds; ++i) out[i] = c;
}
```

> 注意：`base_color()` 不再被 `render` 调用，可保留给测试或删除。`working_color`/`COL_*` 需在 `animated_color` 可见——把它们移到同一匿名 namespace 顶部。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd firmware && pio test -e native`
Expected: 全部 PASS（含 Task 2 的 3 个 + 新 4 个）。

- [ ] **Step 5: 提交**

```bash
cd firmware && git add src/render_engine.cpp test/
git commit -m "feat(firmware): 渲染引擎动画（呼吸/闪/渐暗/失联）"
```

---

## Task 4: 多会话分段渲染（TDD）

**Files:**
- Modify: `firmware/src/render_engine.cpp`（`render()` 分段分支）
- Modify: `firmware/test/test_render_engine/test_main.cpp`

- [ ] **Step 1: 追加失败测试**

```cpp
void test_two_sessions_split_ring() {
  Rgb leds[16];
  Session ss[2] = {
    mk(State::WORKING, ToolKind::CODE),   // 蓝
    mk(State::NEEDS_YOU)                   // 红
  };
  ss[0].state_since_ms = 0; ss[1].state_since_ms = 0;
  render(ss, 2, 0, leds, 16);
  // 前 8 颗偏蓝，后 8 颗偏红
  TEST_ASSERT_GREATER_THAN_UINT8(leds[0].r, leds[0].b);
  TEST_ASSERT_GREATER_THAN_UINT8(leds[15].b, leds[15].r);
}

void test_single_session_fills_all() {
  Rgb leds[16];
  Session s = mk(State::WORKING, ToolKind::CODE);
  s.state_since_ms = 0;
  render(&s, 1, 0, leds, 16);
  for (int i = 0; i < 16; ++i)
    TEST_ASSERT_GREATER_THAN_UINT8(leds[i].r, leds[i].b);  // 全蓝
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd firmware && pio test -e native`
Expected: `test_two_sessions_split_ring` FAIL（当前只渲染 session[0] 铺满）。

- [ ] **Step 3: 实现分段**

替换 `render()` 末段：

```cpp
void render(const Session* sessions, uint8_t session_count,
           uint32_t now_ms, Rgb* out, uint8_t num_leds) {
  if (session_count == 0) {
    for (uint8_t i = 0; i < num_leds; ++i) out[i] = Rgb{0,0,0};
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd firmware && pio test -e native`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd firmware && git add src/render_engine.cpp test/
git commit -m "feat(firmware): 多会话分段渲染"
```

---

## Task 5: 显示驱动抽象 + RGB LED 驱动（ledc）

native 无法测硬件；此任务靠**编译 + 上板观察**验证。

**Files:**
- Create: `firmware/src/display.h`
- Create: `firmware/src/display_rgb_led.cpp`
- Create: `firmware/src/display_factory.cpp`

- [ ] **Step 1: 写 `display.h`（抽象接口）**

```cpp
#pragma once
#include "render_engine.h"

class IDisplay {
public:
  virtual ~IDisplay() {}
  virtual void begin() = 0;
  virtual void show(const Rgb* pixels, uint8_t num_leds) = 0;
};

IDisplay& display();   // 由 display_factory.cpp 按 DISPLAY_TYPE 提供
```

- [ ] **Step 2: 写 `display_rgb_led.cpp`（ESP32 core 3.x 新 ledc API）**

```cpp
#include "config.h"
#if DISPLAY_TYPE == DISPLAY_RGB_LED
#include <Arduino.h>
#include "display.h"

class RgbLedDisplay : public IDisplay {
public:
  void begin() override {
    // core 3.x：ledcAttach(pin, freq, resolution) 自动分配通道
    ledcAttach(PIN_RGB_R, LEDC_FREQ, LEDC_RES);
    ledcAttach(PIN_RGB_G, LEDC_FREQ, LEDC_RES);
    ledcAttach(PIN_RGB_B, LEDC_FREQ, LEDC_RES);
  }
  void show(const Rgb* px, uint8_t /*n*/) override {
    // 共阴：duty 直接给值；亮度上限保护
    ledcWrite(PIN_RGB_R, (px[0].r * MAX_BRIGHTNESS) / 255);
    ledcWrite(PIN_RGB_G, (px[0].g * MAX_BRIGHTNESS) / 255);
    ledcWrite(PIN_RGB_B, (px[0].b * MAX_BRIGHTNESS) / 255);
  }
};

static RgbLedDisplay g_display;
IDisplay& display() { return g_display; }
#endif
```

> 共阳 RGB LED：把每路 duty 改成 `255 - value`（在 `show` 里反相）。

- [ ] **Step 3: 写 `display_factory.cpp`（WS2812 分支留到 Task 8）**

```cpp
// 各驱动文件用 #if DISPLAY_TYPE==... 自带 display() 定义，
// factory 仅在「无任何驱动匹配」时给出编译期报错，防止配错。
#include "config.h"
#if DISPLAY_TYPE != DISPLAY_RGB_LED && \
    DISPLAY_TYPE != DISPLAY_WS2812_RING && \
    DISPLAY_TYPE != DISPLAY_WS2812_STRIP && \
    DISPLAY_TYPE != DISPLAY_DISCRETE
#error "未知 DISPLAY_TYPE，请在 build_flags 里设置"
#endif
```

- [ ] **Step 4: main.cpp 接渲染引擎 + 显示驱动，自检动画**

替换 `src/main.cpp`：

```cpp
#include <Arduino.h>
#include "config.h"
#include "render_engine.h"
#include "display.h"

static Rgb g_pixels[NUM_LEDS];
static Session g_session;           // 单会话（网络层接入前先写死自检）
static bool g_has_session = false;

void setup() {
  Serial.begin(115200);
  delay(300);
  display().begin();
  // 自检：开机 2s BOOT，然后进入 WORKING 看呼吸
  g_session = Session{ State::WORKING, ToolKind::CODE, millis(), 0 };
  g_has_session = true;
  Serial.println("VibeLamp display self-test: WORKING breathing");
}

void loop() {
  uint32_t now = millis();
  if (g_has_session)
    render(&g_session, 1, now, g_pixels, NUM_LEDS);
  else
    render(nullptr, 0, now, g_pixels, NUM_LEDS);
  display().show(g_pixels, NUM_LEDS);
  delay(16);   // ~60fps
}
```

- [ ] **Step 5: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。

- [ ] **Step 6: 上板观察（需接线）**

接线：共阴 RGB LED 的 R/G/B 经各自限流电阻（~220Ω）接 GPIO25/26/27，公共阴极接 GND。
Run: `pio run -e esp32 -t upload && pio device monitor`
Expected: 看到串口 `display self-test`，LED 呈**蓝色呼吸**。换 `g_session.state` 为 `NEEDS_YOU` 重烧应见**红色慢闪**。

- [ ] **Step 7: 提交**

```bash
cd firmware && git add src/display.h src/display_rgb_led.cpp src/display_factory.cpp src/main.cpp
git commit -m "feat(firmware): 显示抽象 + RGB LED 驱动 + 动画自检"
```

---

## Task 6: WiFi 连接 + mDNS 广播（vibelamp.local）

凭据先放 `secrets.h`（gitignored）；网页配网是后续计划。

**Files:**
- Create: `firmware/include/secrets.h`（本地，不提交）
- Create: `firmware/src/net.h`
- Create: `firmware/src/net.cpp`
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: 写 `include/secrets.h`（本地填真实 WiFi）**

```cpp
#pragma once
#define WIFI_SSID "你的WiFi名"
#define WIFI_PASS "你的WiFi密码"
```

- [ ] **Step 2: 写 `net.h`**

```cpp
#pragma once
#include <stdbool.h>
bool net_begin();        // 连 WiFi + 启 mDNS；成功返回 true
bool net_connected();
```

- [ ] **Step 3: 写 `net.cpp`**

```cpp
#include <WiFi.h>
#include <ESPmDNS.h>
#include "config.h"
#include "net.h"
#include "secrets.h"

bool net_begin() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > 20000) return false;   // 20s 超时
    delay(250);
  }
  if (MDNS.begin(MDNS_HOST)) {                     // → vibelamp.local
    MDNS.addService("http", "tcp", HTTP_PORT);
  }
  return true;
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }
```

- [ ] **Step 4: main.cpp setup 里调用 `net_begin()`**

在 `setup()` 的 `display().begin();` 之后加：

```cpp
  if (net_begin())
    Serial.printf("WiFi OK, http://%s.local  IP=%s\n", MDNS_HOST, WiFi.localIP().toString().c_str());
  else
    Serial.println("WiFi FAILED (检查 secrets.h)");
```

并在 main.cpp 顶部 `#include "net.h"` 和 `#include <WiFi.h>`。

- [ ] **Step 5: 上板验证**

Run: `cd firmware && pio run -e esp32 -t upload && pio device monitor`
Expected: 串口打印 `WiFi OK, http://vibelamp.local IP=192.168.x.x`。
另在 Mac 上 `ping vibelamp.local` 应通（macOS 原生解析 .local）。

- [ ] **Step 6: 提交（不含 secrets.h）**

```bash
cd firmware && git add src/net.h src/net.cpp src/main.cpp
git commit -m "feat(firmware): WiFi 连接 + mDNS vibelamp.local"
```

---

## Task 7: HTTP 端点 POST /state + GET /health + 看门狗

**Files:**
- Create: `firmware/src/api_server.h`
- Create: `firmware/src/api_server.cpp`
- Modify: `firmware/src/main.cpp`

JSON 约定（守护进程会发的格式）：

```json
{ "sessions": [
    { "state": "working", "tool": "code" },
    { "state": "needs_you" }
] }
```
`state` ∈ idle|working|done|needs_you|error|lost|boot；`tool` ∈ none|code|command|search（缺省 none）。空 `sessions` → 全 idle。

- [ ] **Step 1: 写 `api_server.h`**

```cpp
#pragma once
#include "render_engine.h"

void api_begin();
void api_loop();                       // 在 loop() 里调，处理请求
uint8_t api_session_count();           // 当前会话数
const Session* api_sessions();         // 当前会话数组
uint32_t api_last_state_ms();          // 最近一次收到 /state 的 millis
```

- [ ] **Step 2: 写 `api_server.cpp`**

```cpp
#include <WebServer.h>
#include <ArduinoJson.h>
#include "config.h"
#include "api_server.h"

static WebServer server(HTTP_PORT);
static Session g_sessions[NUM_LEDS > 8 ? NUM_LEDS : 8];
static uint8_t g_count = 0;
static uint32_t g_last_ms = 0;

static State parse_state(const char* s) {
  if (!s) return State::IDLE;
  if (!strcmp(s, "working"))   return State::WORKING;
  if (!strcmp(s, "done"))      return State::DONE;
  if (!strcmp(s, "needs_you")) return State::NEEDS_YOU;
  if (!strcmp(s, "error"))     return State::ERROR;
  if (!strcmp(s, "lost"))      return State::LOST;
  if (!strcmp(s, "boot"))      return State::BOOT;
  return State::IDLE;
}
static ToolKind parse_tool(const char* t) {
  if (!t) return ToolKind::NONE;
  if (!strcmp(t, "code"))    return ToolKind::CODE;
  if (!strcmp(t, "command")) return ToolKind::COMMAND;
  if (!strcmp(t, "search"))  return ToolKind::SEARCH;
  return ToolKind::NONE;
}

static void handle_state() {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, server.arg("plain"));
  if (err) { server.send(400, "text/plain", "bad json"); return; }

  JsonArray arr = doc["sessions"].as<JsonArray>();
  uint8_t cap = sizeof(g_sessions) / sizeof(g_sessions[0]);
  uint8_t n = 0;
  uint32_t now = millis();
  for (JsonObject o : arr) {
    if (n >= cap) break;
    State st = parse_state(o["state"]);
    ToolKind tk = parse_tool(o["tool"]);
    // 状态没变就保留 state_since_ms，让动画相位连续；变了才重置
    if (n < g_count && g_sessions[n].state == st && g_sessions[n].tool == tk) {
      // 保留 state_since_ms
    } else {
      g_sessions[n].state_since_ms = now;
    }
    g_sessions[n].state = st;
    g_sessions[n].tool = tk;
    g_sessions[n].pulse_at_ms = 0;
    ++n;
  }
  g_count = n;
  g_last_ms = now;
  server.send(200, "application/json", "{\"ok\":true}");
}

static void handle_health() {
  char buf[96];
  snprintf(buf, sizeof(buf), "{\"sessions\":%u,\"uptime_ms\":%lu}",
          (unsigned)g_count, (unsigned long)millis());
  server.send(200, "application/json", buf);
}

void api_begin() {
  server.on("/state", HTTP_POST, handle_state);
  server.on("/health", HTTP_GET, handle_health);
  server.begin();
}
void api_loop() { server.handleClient(); }
uint8_t api_session_count() { return g_count; }
const Session* api_sessions() { return g_sessions; }
uint32_t api_last_state_ms() { return g_last_ms; }
```

- [ ] **Step 3: main.cpp 接入 API + 看门狗**

重写 `loop()` 与 `setup()` 尾部：

```cpp
// setup() 末尾加：
  api_begin();

// 替换 loop()：
void loop() {
  api_loop();
  uint32_t now = millis();

  const Session* sessions = api_sessions();
  uint8_t count = api_session_count();
  uint32_t last = api_last_state_ms();

  // 看门狗：从未收到过 / 超时未收到 → 失联（仅在 WiFi 已起来后才算失联）
  bool stale = (last == 0) || (now - last > WATCHDOG_TIMEOUT_MS);

  if (stale && net_connected()) {
    Session lost{ State::LOST, ToolKind::NONE, /*since*/ (last? last+WATCHDOG_TIMEOUT_MS : 0), 0 };
    render(&lost, 1, now, g_pixels, NUM_LEDS);
  } else if (count == 0) {
    render(nullptr, 0, now, g_pixels, NUM_LEDS);   // idle
  } else {
    render(sessions, count, now, g_pixels, NUM_LEDS);
  }
  display().show(g_pixels, NUM_LEDS);
  delay(16);
}
```

在 main.cpp 顶部 `#include "api_server.h"`。移除 Task 5 里写死的 `g_session` 自检变量。

- [ ] **Step 4: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。

- [ ] **Step 5: 上板 + curl 端到端验证**

Run（上板后，在 Mac 上）:
```bash
pio run -e esp32 -t upload
# 等串口显示 WiFi OK 后：
curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'
curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"needs_you"}]}'
curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"done"}]}'
curl http://vibelamp.local/health
```
Expected: 灯依次变**蓝呼吸 → 红慢闪 → 绿渐暗**；`/health` 返回 JSON。停发 30s 后灯转**琥珀失联呼吸**；再发 /state 立即恢复。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/api_server.h src/api_server.cpp src/main.cpp
git commit -m "feat(firmware): HTTP /state /health + 看门狗失联"
```

---

## Task 8: WS2812 驱动（FastLED）—— 灯环/灯条/分立支持

**Files:**
- Create: `firmware/src/display_ws2812.cpp`
- Modify: `firmware/platformio.ini`（加 WS2812 env）

- [ ] **Step 1: 写 `display_ws2812.cpp`**

```cpp
#include "config.h"
#if DISPLAY_TYPE == DISPLAY_WS2812_RING || DISPLAY_TYPE == DISPLAY_WS2812_STRIP
#include <FastLED.h>
#include "display.h"

static CRGB g_leds[NUM_LEDS];

class Ws2812Display : public IDisplay {
public:
  void begin() override {
    FastLED.addLeds<WS2812B, PIN_WS2812, GRB>(g_leds, NUM_LEDS);
    FastLED.setBrightness(MAX_BRIGHTNESS);
  }
  void show(const Rgb* px, uint8_t n) override {
    for (uint8_t i = 0; i < n; ++i) g_leds[i] = CRGB(px[i].r, px[i].g, px[i].b);
    FastLED.show();
  }
};

static Ws2812Display g_display;
IDisplay& display() { return g_display; }
#endif
```

> 灯环与灯条用同一驱动；区别只是 `NUM_LEDS` 和物理排布（环首尾相邻），渲染引擎已用比例分段，无需区分。分立定色 LED 版（`DISPLAY_DISCRETE`）的驱动结构相同，按颜色阈值点亮对应 GPIO——可在需要时按本任务模式再加 `display_discrete.cpp`。

- [ ] **Step 2: platformio.ini 加 WS2812 env**

```ini
[env:esp32_ring]
extends = env:esp32
build_flags =
    -DDISPLAY_TYPE=DISPLAY_WS2812_RING
```

- [ ] **Step 3: 编译两种 env**

Run: `cd firmware && pio run -e esp32 && pio run -e esp32_ring`
Expected: 两个都 `SUCCESS`（验证两套驱动都能独立编出）。

- [ ] **Step 4: 上板验证灯环（接线后）**

接线：WS2812 灯环 DIN→GPIO4，5V→5V，GND→GND（数据线建议串 330Ω，电源建议并 1000µF 电容）。
Run:
```bash
pio run -e esp32_ring -t upload
curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"},{"state":"needs_you"}]}'
```
Expected: 灯环**前半圈蓝呼吸、后半圈红慢闪**（多会话分段）。

- [ ] **Step 5: 提交**

```bash
cd firmware && git add src/display_ws2812.cpp platformio.ini
git commit -m "feat(firmware): WS2812 灯环/灯条驱动（FastLED）"
```

---

## Task 9: 开机动画 + 收尾

**Files:**
- Modify: `firmware/src/render_engine.cpp`（BOOT 扫描动画）
- Modify: `firmware/test/test_render_engine/test_main.cpp`
- Modify: `firmware/src/main.cpp`（开机先 BOOT 1.5s）

- [ ] **Step 1: 给 BOOT 写一个「亮点扫描」测试**

```cpp
void test_boot_scans() {
  Rgb leds[16];
  Session s = mk(State::BOOT);
  s.state_since_ms = 0;
  render(&s, 1, 0,   leds, 16);   // t=0 亮点在头部
  Rgb head0 = leds[0];
  render(&s, 1, 200, leds, 16);   // 稍后亮点移动
  TEST_ASSERT_TRUE(head0.b != leds[0].b || head0.g != leds[0].g);
}
```

- [ ] **Step 2: 跑测试确认失败 → 实现 BOOT 扫描**

在 `animated_color` 之外、`render()` 里对 `BOOT` 单独处理（因为它跨像素）：在 `render()` 开头判断 `sessions[0].state==BOOT && session_count==1` 时，按 `now_ms` 让一个亮点沿像素移动，其余暗。给出完整实现：

```cpp
  if (session_count == 1 && sessions[0].state == State::BOOT) {
    uint32_t e = now_ms - sessions[0].state_since_ms;
    uint8_t head = (num_leds > 1) ? (uint8_t)((e / 80) % num_leds) : 0;
    for (uint8_t i = 0; i < num_leds; ++i)
      out[i] = (i == head) ? Rgb{0,120,160} : Rgb{0,0,0};
    return;
  }
```

（放在 `render()` 内、空会话判断之后、单/多会话分支之前。）

- [ ] **Step 3: 跑测试确认通过**

Run: `cd firmware && pio test -e native`
Expected: 全 PASS。

- [ ] **Step 4: main.cpp 开机先放 1.5s BOOT**

在 `loop()` 最前面加：

```cpp
  static uint32_t boot_start = millis();
  if (millis() - boot_start < 1500) {
    Session boot{ State::BOOT, ToolKind::NONE, boot_start, 0 };
    render(&boot, 1, millis(), g_pixels, NUM_LEDS);
    display().show(g_pixels, NUM_LEDS);
    api_loop();
    delay(16);
    return;
  }
```

- [ ] **Step 5: 编译 + 上板看开机动画**

Run: `cd firmware && pio run -e esp32 -t upload && pio device monitor`
Expected: 上电先见**亮点扫描 ~1.5s**，再进入正常状态显示。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/render_engine.cpp src/main.cpp test/
git commit -m "feat(firmware): 开机扫描动画"
```

---

## 验收（整计划完成标准）

- `pio test -e native` 全绿（渲染引擎纯逻辑全覆盖）。
- `pio run -e esp32` 与 `pio run -e esp32_ring` 均编译成功。
- 上板后 `curl -X POST http://vibelamp.local/state -d '{...}'` 能驱动全部状态；停发 30s 转失联；恢复后立即正确。
- 灯环 env 下两会话能分段显示。
- 设备**不依赖任何其它组件即可独立验证**（守护进程未写也能用 curl 测）。

## 后续计划（各自独立成文，本计划不含）

- **计划 02 — Python 守护进程 + Claude Code 钩子 + launchd**：收 hook 事件、会话合并、推送 vibelamp.local、心跳、超时兜底、幂等装钩子、开机自启。
- **计划 03 — Codex 接入**：config.toml hooks + notify、事件归一化、session id 核实兜底。
- **计划 04 — 网页配网（WiFiManager）+ BLE 兜底/配网**：替换 secrets.h 硬编码；WiFi 断切 BLE。

## 自查记录

- **Spec 覆盖**：固件层职责（联网/mDNS/HTTP/看门狗/渲染/显示抽象/四种硬件/多会话/失联态/开机动画）均有对应任务。配网（WiFiManager）按设计属后续计划，本计划用 secrets.h 占位并已说明。
- **类型一致**：`State`/`ToolKind`/`Rgb`/`Session`/`render()` 签名自 Task 2 锁定，后续任务一致引用；JSON 的 state/tool 字符串与枚举解析在 Task 7 对齐。
- **无占位**：每个代码步骤给了完整可编译代码；硬件相关步骤给了接线与 curl 验证命令。
- **已知取舍**：native 单测只覆盖纯渲染逻辑；WiFi/HTTP/驱动靠上板 + curl 集成验证（嵌入式无法纯 native 测硬件，已在对应任务标注）。
