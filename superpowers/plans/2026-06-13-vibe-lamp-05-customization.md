# Vibe Lamp 实现计划 05 — 用户自定义设置

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 设计依据：`superpowers/specs/2026-06-13-vibe-lamp-design.md` §13。前置：计划 01（固件渲染引擎/显示驱动/HTTP 服务）、计划 02（守护进程 config/normalize）。本计划让用户**无需重烧/改代码**就能定制灯的外观与行为。

**Goal:** 两个自定义面，各归其位——① **显示偏好**（亮度/各状态颜色/动画快慢与开关）→ 灯自带设置网页 `http://vibelamp.local/`，存 NVS、即时生效、断电不丢；② **逻辑偏好**（工具分色规则/会话超时/心跳/灯地址）→ 守护进程配置文件 `~/.vibelamp/config.json`。

**Architecture:**
- **Part A（固件）**：渲染引擎的颜色/动画从硬编码常量改为运行时 `RenderSettings`（模块全局 `g_settings`，默认值 = 计划 01 原常量，保持 `render()` 签名不变以兼容计划 01 测试）。亮度统一到渲染层施加（移除计划 01 显示驱动里的 `MAX_BRIGHTNESS` 二次缩放）。`settings_store` 用 Preferences 把 `RenderSettings` 存/取 NVS。HTTP 加 `GET /`（设置页）、`GET /settings`（当前值 JSON）、`POST /settings`（保存 NVS + 即时应用）。
- **Part B（守护进程）**：`config.py` 启动时读 `~/.vibelamp/config.json`，缺省值兜底；`normalize` 的工具分色表从配置读；`install.py` 首次生成默认配置文件。

**Tech Stack:** 固件——Arduino-ESP32 `Preferences`（NVS）、计划 01 的 WebServer/ArduinoJson、native Unity 单测渲染设置纯逻辑。守护进程——Python 仅标准库（json）+ pytest。

---

## 文件结构（标注新建 / 改前序计划）

```
firmware/
├── src/
│   ├── render_engine.h     # 【改 01】加 RenderSettings 结构 + render_set_settings/get
│   ├── render_engine.cpp   # 【改 01】COL_* 常量改读 g_settings；动画速度/开关；末端施加亮度
│   ├── settings_store.h/.cpp  # 【新建】Preferences 存取 RenderSettings（含默认与版本）
│   ├── display_rgb_led.cpp # 【改 01】移除 MAX_BRIGHTNESS 二次缩放（亮度已在渲染层）
│   ├── display_ws2812.cpp  # 【改 01】FastLED.setBrightness(255)，亮度交渲染层
│   ├── api_server.cpp      # 【改 01】加 GET / 、GET /settings 、POST /settings
│   └── main.cpp            # 【改 01】setup 里 settings_store_load() → render_set_settings()
└── test/test_render_engine/test_main.cpp  # 【改 01】新增设置改变输出的用例

daemon/
├── vibelamp/
│   ├── config.py           # 【改 02】load_config() 读 ~/.vibelamp/config.json 覆盖默认
│   └── normalize.py        # 【改 02】classify_tool 从 config.CLAUDE_TOOL_MAP 读
├── tests/
│   ├── test_config.py      # 【新建】配置文件加载/默认合并
│   └── test_normalize.py   # 【改 02/03】工具映射可配置用例
└── install.py              # 【改 02】首次生成 ~/.vibelamp/config.json
```

---

# Part A — 固件设置网页（显示偏好，存 NVS）

## Task 1: RenderSettings 结构 + 渲染引擎运行时化（改 01，TDD）

把计划 01 `render_engine.cpp` 里写死的 `COL_*`、`working_color()` 颜色、动画周期，改为读模块全局 `g_settings`。默认值等于计划 01 原值，**所以计划 01 的现有测试不变也应继续通过**。

**Files:**
- Modify: `firmware/src/render_engine.h`
- Modify: `firmware/src/render_engine.cpp`
- Modify: `firmware/test/test_render_engine/test_main.cpp`

- [ ] **Step 1: 在 `render_engine.h` 加 RenderSettings 与存取声明**

在 `render()` 声明之后追加：

```cpp
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
```

- [ ] **Step 2: 写失败测试（设置改变输出）**

在 `test_main.cpp` 追加（并 `RUN_TEST`）：

```cpp
void test_default_settings_match_legacy() {
  render_set_settings(render_default_settings());
  Session s = mk(State::WORKING, ToolKind::CODE);
  render(&s, 1, 0, &px, 1);          // 默认蓝呼吸波峰，蓝 > 红（与计划01一致）
  TEST_ASSERT_GREATER_THAN_UINT8(px.r, px.b);
}

void test_custom_color_applied() {
  RenderSettings cfg = render_default_settings();
  cfg.col_done = Rgb{10, 20, 200};   // 把"完成"改成蓝
  render_set_settings(cfg);
  Session s = mk(State::DONE);
  s.state_since_ms = 0;
  render(&s, 1, 0, &px, 1);
  TEST_ASSERT_GREATER_THAN_UINT8(px.r, px.b);   // 现在完成是蓝
}

void test_brightness_scales_output() {
  RenderSettings cfg = render_default_settings();
  cfg.brightness = 64;               // 1/4 亮度
  render_set_settings(cfg);
  Session s = mk(State::NEEDS_YOU);
  s.state_since_ms = 0;
  render(&s, 1, 0, &px, 1);          // needs_you 闪烁亮相位，但被亮度压到 ~1/4
  TEST_ASSERT_LESS_THAN_UINT8(120, px.r);
}

void test_animations_off_is_static() {
  RenderSettings cfg = render_default_settings();
  cfg.animations = false;
  render_set_settings(cfg);
  Session s = mk(State::NEEDS_YOU);
  s.state_since_ms = 0;
  Rgb on, later;
  render(&s, 1, 0,   &on,    1);
  render(&s, 1, 600, &later, 1);     // 关动画：两个相位应一致（不再慢闪到灭）
  TEST_ASSERT_EQUAL_UINT8(on.r, later.r);
}
```

> 注意：`test_main.cpp` 每个用例开头都 `render_set_settings(...)` 显式设定，避免用例间全局状态串扰。给计划 01 已有用例也在 `setUp()` 里统一 `render_set_settings(render_default_settings())` 复位（见 Step 4）。

- [ ] **Step 3: 跑测试确认失败**

Run: `cd firmware && pio test -e native`
Expected: 新用例 FAIL（`render_set_settings` 等未定义）。

- [ ] **Step 4: 改 `render_engine.cpp`**

① 在匿名 namespace 顶部，把原 `COL_*` 常量改为「默认值」来源，并加模块全局 `g_settings`：

```cpp
namespace {
RenderSettings g_settings;     // 当前生效设置
bool g_inited = false;

void ensure_inited() {
  if (!g_inited) { g_settings = render_default_settings(); g_inited = true; }
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
  s.col_lost      = {255, 150, 0};
  s.col_boot      = {0, 120, 160};
  return s;
}
void render_set_settings(const RenderSettings& s) { g_settings = s; g_inited = true; }
RenderSettings render_get_settings() { ensure_inited(); return g_settings; }
```

② `working_color()` 改读设置：

```cpp
Rgb working_color(ToolKind t) {
  switch (t) {
    case ToolKind::COMMAND: return g_settings.col_working_command;
    case ToolKind::SEARCH:  return g_settings.col_working_search;
    case ToolKind::CODE:
    default:                return g_settings.col_working_code;
  }
}
```

③ `animated_color()` 改读设置色 + 速度 + 开关。把里面 `COL_NEEDS`/`COL_DONE`/`COL_LOST`/`COL_BOOT` 等替换为 `g_settings.col_*`；周期统一经 `scaled()` 缩放；`animations==false` 时直接返回基准色：

```cpp
namespace {
uint32_t scaled(uint32_t period) {        // 速度百分比缩放周期
  uint16_t pct = g_settings.speed_pct ? g_settings.speed_pct : 100;
  return period * 100 / pct;
}
Rgb base_for(const Session& s) {          // 不带动画的基准色
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
} // namespace

Rgb animated_color(const Session& s, uint32_t now_ms) {
  ensure_inited();
  if (!g_settings.animations) return base_for(s);    // 关动画 = 静态基准色
  uint32_t e = now_ms - s.state_since_ms;
  switch (s.state) {
    case State::WORKING: {
      uint8_t b = 60 + (uint8_t)((uint16_t)tri_wave(e, scaled(2000)) * 195 / 255);
      return scale(working_color(s.tool), b);
    }
    case State::NEEDS_YOU:
      return scale(g_settings.col_needs_you, square_wave(e, scaled(1200)));
    case State::ERROR:
      return e < scaled(300) ? g_settings.col_error : Rgb{0,0,0};
    case State::DONE: {
      uint32_t win = scaled(4500);
      if (e >= win) return Rgb{0,0,0};
      return scale(g_settings.col_done, (uint8_t)(255 - (e * 255 / win)));
    }
    case State::LOST: {
      uint8_t b = 20 + (uint8_t)((uint16_t)tri_wave(e, scaled(3000)) * 80 / 255);
      return scale(g_settings.col_lost, b);
    }
    case State::BOOT:    return g_settings.col_boot;
    default:             return Rgb{0,0,0};
  }
}
```

④ 在 `render()` 末端统一施加亮度——给每个输出像素乘 `brightness/255`。在 `render()` 的每个写 `out[i]` 分支后，或在函数结尾加一遍：

```cpp
// render() 结尾，return 前，对已填好的 out[] 统一施加亮度
void apply_brightness(Rgb* out, uint8_t num_leds) {
  ensure_inited();
  uint8_t b = g_settings.brightness;
  for (uint8_t i = 0; i < num_leds; ++i) {
    out[i].r = (uint8_t)(out[i].r * b / 255);
    out[i].g = (uint8_t)(out[i].g * b / 255);
    out[i].b = (uint8_t)(out[i].b * b / 255);
  }
}
```

把 `render()` 的三个 return 点改为先 `apply_brightness(out, num_leds); return;`（IDLE 全暗那条可跳过，乘任何亮度仍是 0，调不调用都行；为统一可一律调用）。

> 把 `apply_brightness` 声明放在 `render()` 之前（同文件靠前），或设为 `render_engine.cpp` 内部前置声明。

⑤ 给计划 01 现有测试的 `setUp()` 加复位（避免用例间设置串扰）：

```cpp
void setUp() { render_set_settings(render_default_settings()); }
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd firmware && pio test -e native`
Expected: 计划 01 原用例 + 本任务 4 个新用例全 PASS。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/render_engine.h src/render_engine.cpp test/
git commit -m "feat(firmware): 渲染设置运行时化（颜色/动画/亮度）"
```

---

## Task 2: NVS 持久化 RenderSettings + 显示驱动去重缩放（改 01）

**Files:**
- Create: `firmware/src/settings_store.h`
- Create: `firmware/src/settings_store.cpp`
- Modify: `firmware/src/display_rgb_led.cpp`
- Modify: `firmware/src/display_ws2812.cpp`
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: 写 `settings_store.h`**

```cpp
#pragma once
#include "render_engine.h"

// 从 NVS 读设置（无则返回默认）；写设置到 NVS。
RenderSettings settings_load();
void settings_save(const RenderSettings& s);
```

- [ ] **Step 2: 写 `settings_store.cpp`（Preferences blob + 版本字节）**

```cpp
#include <Preferences.h>
#include "settings_store.h"

static const char* NS = "vibelamp";
static const char* KEY = "render";
static const uint8_t VER = 1;

RenderSettings settings_load() {
  Preferences p;
  p.begin(NS, /*readOnly=*/true);
  RenderSettings s = render_default_settings();
  uint8_t ver = p.getUChar("ver", 0);
  if (ver == VER) {
    p.getBytes(KEY, &s, sizeof(s));   // 覆盖默认
  }
  p.end();
  return s;
}

void settings_save(const RenderSettings& s) {
  Preferences p;
  p.begin(NS, /*readOnly=*/false);
  p.putBytes(KEY, &s, sizeof(s));
  p.putUChar("ver", VER);
  p.end();
}
```

> 用整结构 blob + 版本字节：结构体改了就 bump `VER`，旧 blob 被忽略、回落默认，避免读到错位数据。

- [ ] **Step 3: 显示驱动移除二次缩放（亮度已在渲染层施加）**

`display_rgb_led.cpp` 的 `show()` 改为直接写值（去掉 `* MAX_BRIGHTNESS / 255`）：

```cpp
  void show(const Rgb* px, uint8_t) override {
    ledcWrite(PIN_RGB_R, px[0].r);
    ledcWrite(PIN_RGB_G, px[0].g);
    ledcWrite(PIN_RGB_B, px[0].b);
  }
```

`display_ws2812.cpp` 的 `begin()` 把 `FastLED.setBrightness(MAX_BRIGHTNESS)` 改为 `FastLED.setBrightness(255)`（亮度交渲染层）。

- [ ] **Step 4: `main.cpp` 开机加载设置**

在 `setup()` 里 `display().begin();` 之后、`net_begin()` 之前加：

```cpp
  render_set_settings(settings_load());   // 从 NVS 恢复用户设置
```

并 `#include "settings_store.h"`。

- [ ] **Step 5: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/settings_store.h src/settings_store.cpp src/display_rgb_led.cpp src/display_ws2812.cpp src/main.cpp
git commit -m "feat(firmware): NVS 持久化渲染设置 + 显示驱动亮度收口"
```

---

## Task 3: 设置网页端点（GET / + GET/POST /settings）

**Files:**
- Modify: `firmware/src/api_server.cpp`

- [ ] **Step 1: 加设置页 HTML 与 JSON 端点**

在 `api_begin()` 里追加路由：

```cpp
  server.on("/", HTTP_GET, handle_root);
  server.on("/settings", HTTP_GET, handle_get_settings);
  server.on("/settings", HTTP_POST, handle_post_settings);
```

并在文件里加这些处理函数（`#include "settings_store.h"`、`#include "render_engine.h"`）。颜色用 `#rrggbb`，前端取色器直接对接：

```cpp
static String hex(Rgb c) {
  char b[8]; snprintf(b, sizeof(b), "#%02x%02x%02x", c.r, c.g, c.b); return String(b);
}
static Rgb unhex(const String& s) {     // "#rrggbb" → Rgb
  long v = strtol(s.c_str() + (s.startsWith("#") ? 1 : 0), nullptr, 16);
  return Rgb{ (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)(v) };
}

static void handle_get_settings() {
  RenderSettings s = render_get_settings();
  JsonDocument d;
  d["brightness"] = s.brightness;
  d["animations"] = s.animations;
  d["speed_pct"] = s.speed_pct;
  d["working_code"]    = hex(s.col_working_code);
  d["working_command"] = hex(s.col_working_command);
  d["working_search"]  = hex(s.col_working_search);
  d["done"]      = hex(s.col_done);
  d["needs_you"] = hex(s.col_needs_you);
  d["error"]     = hex(s.col_error);
  d["lost"]      = hex(s.col_lost);
  d["boot"]      = hex(s.col_boot);
  String out; serializeJson(d, out);
  server.send(200, "application/json", out);
}

static void handle_post_settings() {
  JsonDocument d;
  if (deserializeJson(d, server.arg("plain"))) {
    server.send(400, "text/plain", "bad json"); return;
  }
  RenderSettings s = render_get_settings();
  if (d["brightness"].is<int>()) s.brightness = (uint8_t)d["brightness"].as<int>();
  if (d["animations"].is<bool>()) s.animations = d["animations"].as<bool>();
  if (d["speed_pct"].is<int>())  s.speed_pct = (uint8_t)d["speed_pct"].as<int>();
  if (d["working_code"].is<const char*>())    s.col_working_code = unhex(d["working_code"].as<String>());
  if (d["working_command"].is<const char*>()) s.col_working_command = unhex(d["working_command"].as<String>());
  if (d["working_search"].is<const char*>())  s.col_working_search = unhex(d["working_search"].as<String>());
  if (d["done"].is<const char*>())      s.col_done = unhex(d["done"].as<String>());
  if (d["needs_you"].is<const char*>()) s.col_needs_you = unhex(d["needs_you"].as<String>());
  if (d["error"].is<const char*>())     s.col_error = unhex(d["error"].as<String>());
  if (d["lost"].is<const char*>())      s.col_lost = unhex(d["lost"].as<String>());
  if (d["boot"].is<const char*>())      s.col_boot = unhex(d["boot"].as<String>());
  render_set_settings(s);     // 即时生效
  settings_save(s);           // 落 NVS
  server.send(200, "application/json", "{\"ok\":true}");
}
```

- [ ] **Step 2: 加设置页 HTML（存 PROGMEM，避免占 RAM）**

```cpp
static const char SETTINGS_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Vibe Lamp 设置</title><style>body{font-family:sans-serif;max-width:420px;margin:20px auto;padding:0 12px}
label{display:flex;justify-content:space-between;align-items:center;margin:10px 0}input[type=color]{width:48px}
button{width:100%;padding:12px;margin-top:16px;font-size:16px}</style></head><body>
<h2>Vibe Lamp 设置</h2>
<label>亮度 <input id=brightness type=range min=0 max=255></label>
<label>动画 <input id=animations type=checkbox></label>
<label>动画速度% <input id=speed_pct type=number min=20 max=400></label>
<label>干活·写码 <input id=working_code type=color></label>
<label>干活·命令 <input id=working_command type=color></label>
<label>干活·搜索 <input id=working_search type=color></label>
<label>完成 <input id=done type=color></label>
<label>要介入 <input id=needs_you type=color></label>
<label>出错 <input id=error type=color></label>
<label>失联 <input id=lost type=color></label>
<label>开机 <input id=boot type=color></label>
<button onclick=save()>保存</button>
<p id=msg></p>
<script>
const ids=['brightness','animations','speed_pct','working_code','working_command','working_search','done','needs_you','error','lost','boot'];
fetch('/settings').then(r=>r.json()).then(s=>{for(const k of ids){const e=document.getElementById(k);
 if(e.type==='checkbox')e.checked=s[k];else e.value=s[k];}});
function save(){const b={};for(const k of ids){const e=document.getElementById(k);
 b[k]=e.type==='checkbox'?e.checked:(e.type==='color'?e.value:Number(e.value));}
 fetch('/settings',{method:'POST',body:JSON.stringify(b)}).then(r=>r.json())
 .then(()=>document.getElementById('msg').textContent='已保存 ✓');}
</script></body></html>
)HTML";

static void handle_root() {
  server.send_P(200, "text/html", SETTINGS_HTML);
}
```

- [ ] **Step 3: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。

- [ ] **Step 4: 提交**

```bash
cd firmware && git add src/api_server.cpp
git commit -m "feat(firmware): 设置网页 + /settings 读写（NVS 持久化）"
```

---

## Task 4: 上板验证设置网页（靠上板 + 浏览器）

- [ ] **Step 1: 上板**

Run: `cd firmware && pio run -e esp32 -t upload && pio device monitor`
等串口显示 WiFi OK。

- [ ] **Step 2: 浏览器实操**

Run: Mac/手机浏览器打开 `http://vibelamp.local/`。
Expected: 见设置页，各项已填当前值。拖亮度滑块 → 保存 → 推一条 `curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'`，灯亮度按设置变化。把「完成」改成蓝、保存，再推 done，灯呈蓝渐暗。关掉动画保存，working 变静态常亮。

- [ ] **Step 3: 断电持久化验证**

Run: 拔电重上 → 再开 `http://vibelamp.local/`。
Expected: 设置仍是上次保存的值（NVS 持久化生效）。

---

# Part B — 守护进程配置文件（逻辑偏好）

## Task 5: config.py 读 ~/.vibelamp/config.json（改 02，TDD）

**Files:**
- Modify: `daemon/vibelamp/config.py`
- Create: `daemon/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

`tests/test_config.py`:

```python
import json
from vibelamp import config

def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nope.json")
    c = config.load_config()
    assert c["lamp_url"].startswith("http://")
    assert c["session_ttl_sec"] == 1800
    assert "claude_tool_map" in c

def test_file_overrides_defaults(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"session_ttl_sec": 60,
                             "lamp_url": "http://1.2.3.4/state"}))
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    c = config.load_config()
    assert c["session_ttl_sec"] == 60
    assert c["lamp_url"] == "http://1.2.3.4/state"
    assert c["heartbeat_sec"] == 5.0          # 未覆盖项仍取默认

def test_bad_json_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text("{ not json")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    c = config.load_config()
    assert c["session_ttl_sec"] == 1800       # 坏文件不崩，回落默认
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_config.py -v`
Expected: AttributeError（`load_config` / `CONFIG_PATH` 不存在）。

- [ ] **Step 3: 改 `config.py` 加配置加载**

在 `config.py` 末尾追加（保留计划 02 的常量作默认值来源）：

```python
import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".vibelamp" / "config.json"

_DEFAULTS = {
    "lamp_url": LAMP_URL,
    "listen_port": LISTEN_PORT,
    "heartbeat_sec": HEARTBEAT_SEC,
    "session_ttl_sec": SESSION_TTL_SEC,
    # Claude 工具名 → code/command/search（覆盖计划02/03硬编码默认）
    "claude_tool_map": {
        "Edit": "code", "Write": "code", "MultiEdit": "code", "NotebookEdit": "code",
        "Bash": "command",
        "Read": "search", "Grep": "search", "Glob": "search",
        "WebSearch": "search", "WebFetch": "search", "Agent": "search", "Task": "search",
    },
}


def load_config():
    """读 ~/.vibelamp/config.json 覆盖默认；缺失/坏文件回落默认，不崩。"""
    cfg = dict(_DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text() or "{}")
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if v is not None})
    except Exception:
        pass
    return cfg
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_config.py -v`
Expected: 3 个 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/config.py tests/test_config.py
git commit -m "feat(daemon): 读 ~/.vibelamp/config.json 覆盖默认（容错回落）"
```

---

## Task 6: normalize 工具分色表可配置（改 02/03，TDD）

**Files:**
- Modify: `daemon/vibelamp/normalize.py`
- Modify: `daemon/tests/test_normalize.py`

- [ ] **Step 1: 加失败测试**

在 `tests/test_normalize.py` 追加：

```python
def test_classify_tool_uses_config_map(monkeypatch):
    from vibelamp import normalize
    monkeypatch.setattr(normalize, "_CLAUDE_MAP", {"FooTool": "command"})
    assert normalize.classify_tool("FooTool") == "command"
    assert normalize.classify_tool("Unknown") == "code"   # 缺省仍 code
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_normalize.py::test_classify_tool_uses_config_map -v`
Expected: FAIL（`_CLAUDE_MAP` 不存在）。

- [ ] **Step 3: 改 `normalize.py` 的 `classify_tool` 读配置**

把计划 02 的 `_CODE`/`_SEARCH` 集合 + `classify_tool` 替换为读 config map：

```python
from . import config as _config

_CLAUDE_MAP = _config.load_config()["claude_tool_map"]


def classify_tool(tool_name):
    return _CLAUDE_MAP.get(tool_name, "code")   # 缺省归写码色
```

> `_CLAUDE_MAP` 模块加载时读一次配置；测试用 monkeypatch 替换。Codex 端 `classify_codex_tool`（计划 03）同理可改读 `config` 的 `codex_tool_map`——本步先做 Claude 端，Codex 端按需在计划 03 的对应位置照此改（可选）。

- [ ] **Step 4: 跑全量回归**

Run: `cd daemon && python -m pytest -v`
Expected: 全绿（含计划 02/03 的 normalize 用例 + 本用例）。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/normalize.py tests/test_normalize.py
git commit -m "feat(daemon): 工具分色表从配置读"
```

---

## Task 7: install.py 首次生成默认配置 + 验收

**Files:**
- Modify: `daemon/install.py`

- [ ] **Step 1: install() 里生成默认 config.json（不存在才写，不覆盖用户改动）**

在 `install.py` 的 `install()` 末尾追加，并加一个辅助函数：

```python
def _ensure_default_config():
    from vibelamp import config as cfg
    path = cfg.CONFIG_PATH
    if path.exists():
        return                       # 已有就不覆盖用户改动
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg._DEFAULTS, indent=2, ensure_ascii=False))
    print(f"✅ 已生成默认配置 {path}（可编辑工具分色/超时等）")
```

`install()` 末尾调 `_ensure_default_config()`。

- [ ] **Step 2: 实跑安装并核对**

Run:
```bash
cd daemon && python install.py install
cat ~/.vibelamp/config.json | python -m json.tool | head
```
Expected: 生成 `~/.vibelamp/config.json`，含 lamp_url / session_ttl_sec / claude_tool_map。改 `session_ttl_sec` 后重启守护进程（`launchctl unload/load` 或重登）生效。再跑一次 `install` 不覆盖已改的文件。

- [ ] **Step 3: 提交**

```bash
cd daemon && git add install.py
git commit -m "feat(daemon): install 首次生成默认 ~/.vibelamp/config.json"
```

---

## 验收（整计划完成标准）

- 固件：`pio test -e native` 全绿（计划 01 原用例 + 设置改变输出新用例）；`pio run -e esp32` 成功。
- 上板浏览器开 `http://vibelamp.local/` 能调亮度/颜色/动画并即时生效，断电重连保持（NVS）。
- 守护进程：`python -m pytest` 全绿（新增 test_config + normalize 配置用例）；`~/.vibelamp/config.json` 可覆盖灯地址/超时/工具分色；坏文件不崩、回落默认。
- 默认值与计划 01/02 完全一致——**不改任何设置时行为与之前一字不差**。

## 自查记录

- **Spec 覆盖**：§13.1 显示偏好（亮度/颜色/动画）→ Part A 固件设置网页 + NVS；§13.2 逻辑偏好（工具分色/超时/灯地址）→ Part B 守护进程配置文件；§13.3 分工（外观存灯、逻辑存配置、硬件类型仍编译期）已贯彻。
- **兼容前序计划**：`RenderSettings` 默认值逐字段等于计划 01 原常量，`render()` 签名不变 → 计划 01 测试不改也应通过（仅 `setUp` 加复位防串扰）；config 默认值等于计划 02 常量 → 不写配置文件时行为不变；工具分色默认表等于计划 02/03 的硬编码集合。
- **亮度收口**：亮度从计划 01 散在显示驱动里的 `MAX_BRIGHTNESS` 二次缩放，收口到渲染层 `apply_brightness` 统一施加（驱动改为不再缩放），避免双重变暗——这是对计划 01 的明确修改，已在文件结构与 Task 2 标注。
- **NVS 安全**：整结构 blob + 版本字节，结构改动 bump VER、旧数据回落默认，不读错位。
- **无占位**：每步给完整代码（含设置页 HTML/JS）+ 确切命令 + 期望；硬件步骤如实标注「靠上板 + 浏览器验证」。
- **有意从简**：色彩取色器用 `#rrggbb` 文本/原生 color input，不做实时预览；Codex 工具分色配置化在 Task 6 标为可选（Claude 端先做），避免与计划 03 强耦合。
