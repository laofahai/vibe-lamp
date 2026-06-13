# Vibe Lamp 实现计划 04 — 网页配网（WiFiManager）+ BLE

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 设计依据：`superpowers/specs/2026-06-13-vibe-lamp-design.md`（§6 通信与配网、§6.3 BLE、§7 固件生命周期）。前置：计划 01（固件）已产出 `firmware/`，其中 WiFi 凭据**硬编码在 `firmware/include/secrets.h`**，`net.cpp` 用 `WiFi.begin(WIFI_SSID, WIFI_PASS)`（见计划 01 Task 6）。本计划把硬编码凭据替换成**正经运行时配网**，并补 BLE 通道。

**Goal:** 让 Vibe Lamp 刷一次固件后，**无需重烧即可换网**——首次/连不上时自建热点 `VibeLamp-Setup`，手机浏览器配网，凭据存进 ESP32 NVS（Part A）；再为换网/搬家加按钮一键重配网入口。Part B 补 BLE：① 直接用乐鑫官方 App 做 BLE 配网；② WiFi 断时由 Mac 端常驻 bleak 桥接进程经 BLE GATT 把状态推给灯，做主链路（WiFi HTTP）的兜底冗余。

**Architecture:**
- **Part A（v1 主路）** — 重写计划 01 的 `net.cpp`：用 tzapu/WiFiManager 的 `autoConnect()` 取代 `WiFi.begin(WIFI_SSID, WIFI_PASS)`。WiFiManager 自己读/写 ESP32 NVS、自己起 captive portal、自己重连，**不再 include `secrets.h`**。开机检测「重配网按钮」长按 → `resetSettings()` + 重启进配网门户；另挂一个 `/reset` HTTP 端点作软件备选。mDNS（`vibelamp.local`）连上后照常广播，下游守护进程（计划 02）零改动。
- **Part B（v1.1 增强，标注为后补）** —
  - **① BLE 配网**：固件用 Arduino-ESP32 自带的 `WiFiProv`（`WiFiProv.beginProvision(WIFI_PROV_SCHEME_BLE, ...)`），手机装乐鑫官方「ESP BLE Provisioning」App（iOS/安卓现成，扫 QR 即配），无需自写 App。与 Part A 互为两条配网路（编译期或运行期二选一），不混跑。
  - **② BLE 兜底状态推送**：固件加一个 BLE GATT 服务，开一个「状态」特征值，接收与 HTTP `/state` **同款 JSON payload**；写入后复用计划 01 的同一套 `parse_state`/`render` 路径。Mac 侧因为 hook 是一次性命令（无法自己维持 BLE 连接），需要一个**常驻 bleak 桥接进程**握住 BLE 连接：计划 02 的守护进程 HTTP push 失败时，把同一份 wire JSON 转交本地桥接进程，由它经 BLE 写给灯。

**Tech Stack:**
- 固件：PlatformIO + Arduino-ESP32 core 3.x、**tzapu/WiFiManager @ ^2.0.17**（Part A）、Arduino-ESP32 自带 `WiFiProv` + ESP-IDF BLE provisioning（Part B ①）、Arduino-ESP32 自带 `BLEDevice`/`BLEServer`（NimBLE 后端，Part B ②）。沿用计划 01 的 ArduinoJson 解析。
- Mac 桥接：Python 3.9+ + **bleak**（跨平台 BLE 客户端库，pip 装）；与计划 02 守护进程同进程组协作。

> **版本核实（2026-06-13）**：tzapu/WiFiManager 最新稳定版为 **v2.0.17**（GitHub Releases 与 PlatformIO Registry 一致），支持 ESP32 + ESP8266，captive portal 久经考验。BLE provisioning API 签名核自 espressif/arduino-esp32 的 `WiFiProv` 官方示例。

---

## 重要诚实约束（先读）

- **嵌入式 WiFi/BLE 无法纯 native 单测。** 本计划的「测试」≠ 计划 01 渲染引擎那种 native Unity 单测。这里的验证手段是：
  1. **编译**（`pio run` 成功，证明 API 用法/链接无误）；
  2. **上板烧录**（`pio run -t upload`）；
  3. **手机/电脑实操**（连热点、填密码、扫 QR、看灯）。
- 凡硬件相关步骤，均如实标注「**靠上板 + 手机验证**」，不假装能 native 测。可 native 测的只有：Part B 的 Mac 端 bleak 桥接进程的**纯逻辑/降级决策**部分（用假 BLE client mock），以及 wire JSON 与计划 01/02 协议一致性的字符串断言。
- Part B 标注为 **v1.1 后续增强**：详细度低于 Part A，但架构、关键 API 签名、代码骨架、上板验证步骤齐全，可直接据此实现。

---

## 文件结构

```
firmware/
├── platformio.ini              # 【修改 01】加 tzapu/WiFiManager 依赖；加 BLE 配网 env（Part B①）
├── include/
│   ├── config.h                # 【修改 01】加重配网按钮引脚、AP 名/超时、BLE 服务/特征 UUID
│   └── secrets.h               # 【01 遗留】Part A 后 net.cpp 不再依赖它；保留给 BLE pop 等可选项
├── src/
│   ├── net.h                   # 【修改 01】net_begin 语义改为「WiFiManager 配网+连」；加 net_check_reset_button / net_start_portal
│   ├── net.cpp                 # 【重写 01】去掉 secrets.h，改用 WiFiManager.autoConnect()
│   ├── main.cpp                # 【修改 01】setup 里先查重配网按钮；loop 里挂 /reset（经 api_server）
│   ├── api_server.cpp          # 【修改 01】加 GET /reset 端点（软件触发重配网）
│   ├── ble_prov.h / .cpp       # 【新建·Part B①】可选 BLE 配网（WiFiProv），编译期开关
│   └── ble_state.h / .cpp      # 【新建·Part B②】BLE GATT 状态服务，收 JSON → 复用渲染路径
└── ...                         # 计划 01 其余文件不动

daemon/                         # 计划 02 产出
├── vibelamp/
│   ├── config.py               # 【修改 02】加 BLE 桥接开关与 socket 路径
│   ├── lamp_client.py          # 【修改 02】push 失败时改走 BLE 桥（fallback 决策）
│   └── ble_bridge.py           # 【新建·Part B②】常驻 bleak 桥接：握 BLE 连接，收 wire JSON 写灯
└── tests/
    └── test_ble_fallback.py    # 【新建·Part B②】push 失败→BLE 兜底的纯逻辑测试（mock）
```

**职责边界**：Part A 只动「怎么拿到/存 WiFi 凭据并连上」这一层，**不碰渲染引擎、HTTP /state、看门狗**——它们对「WiFi 怎么连上的」无感知。Part B ① 与 Part A 是两条互斥的配网路（`-DPROV_MODE` 选）。Part B ② 的 BLE 状态服务与 HTTP /state **共用同一份 JSON 解析与 Session 写入**，绝不另起一套状态语义。

---

# Part A — 网页配网 WiFiManager（v1）

## Task 1: 加 WiFiManager 依赖 + config 常量

**Files:**
- Modify: `firmware/platformio.ini`
- Modify: `firmware/include/config.h`

- [ ] **Step 1: `platformio.ini` 的 `[env:esp32]` 加 WiFiManager 依赖**

在计划 01 的 `lib_deps` 末尾追加一行（保留原有 FastLED / ArduinoJson）：

```ini
[env:esp32]
platform = espressif32
board = esp32dev
framework = arduino
monitor_speed = 115200
lib_deps =
    fastled/FastLED@^3.9.0
    bblanchon/ArduinoJson@^7.2.0
    tzapu/WiFiManager@^2.0.17      ; 网页配网（captive portal），自管 NVS 凭据
build_flags =
    -DDISPLAY_TYPE=DISPLAY_RGB_LED
```

> `^2.0.17` 取当前最新稳定版（2026-06-13 核实）。`esp32_ring` env `extends = env:esp32`，自动继承该依赖，无需重复写。`native` env 不引此库（WiFiManager 依赖 Arduino/ESP32，纯逻辑测试不需要）。

- [ ] **Step 2: `include/config.h` 末尾加配网相关常量**

```cpp
// —— 网页配网（WiFiManager）——
#define PROV_AP_NAME       "VibeLamp-Setup"   // 配网热点 SSID
#define PROV_AP_PASS       ""                 // 空 = 开放热点（家用够用；要加密改成 >=8 位）
#define PROV_PORTAL_TIMEOUT 180               // 配网门户超时（秒）；超时后退出门户继续 loop

// —— 重配网按钮（开机长按触发 resetSettings + 重开门户）——
// 用板载 BOOT 按钮（多数 ESP32 开发板 = GPIO0，已接上拉，按下拉低）
#define PIN_RESET_BTN      0
#define RESET_HOLD_MS      3000UL             // 开机时长按 3s 触发重配网
```

> 若你的板子 BOOT 键不在 GPIO0，或想用独立按钮，改 `PIN_RESET_BTN` 并自接一个对地按钮（内部上拉，按下读到 LOW）。

- [ ] **Step 3: 编译确认依赖能拉取**

Run: `cd firmware && pio run -e esp32`
Expected: PlatformIO 自动下载 `WiFiManager @ 2.0.17`，编译 `SUCCESS`。（此时 net.cpp 还没改，仍编得过——只是把依赖拉下来。）

- [ ] **Step 4: 提交**

```bash
cd firmware && git add platformio.ini include/config.h
git commit -m "feat(firmware): 引入 WiFiManager 依赖 + 配网/重置按钮常量"
```

---

## Task 2: 重写 net.cpp —— 用 WiFiManager 取代 secrets.h 硬编码

这是 Part A 的核心：把计划 01 Task 6 的 `WiFi.begin(WIFI_SSID, WIFI_PASS)` 换成 `wm.autoConnect()`。**靠上板 + 手机验证**（编译能过即先行验证 API 用法）。

**Files:**
- Modify: `firmware/src/net.h`
- Modify: `firmware/src/net.cpp`（重写）

- [ ] **Step 1: 改 `net.h`，扩出配网相关接口**

```cpp
#pragma once
#include <stdbool.h>

// 连 WiFi：先试 NVS 里已存凭据；连不上则起 VibeLamp-Setup 配网门户。
// 配上并连上返回 true；门户超时仍未连上返回 false（loop 里照常进失联态）。
bool net_begin();

bool net_connected();

// 清除已存 WiFi 凭据（NVS）并重启进配网门户。供按钮/HTTP /reset 调用。
void net_reset_and_reboot();

// 手动起配网门户（不清旧凭据，用于运行时主动重配）。返回是否配成。
bool net_start_portal();
```

- [ ] **Step 2: 重写 `net.cpp`（去掉 `#include "secrets.h"`）**

```cpp
#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>      // tzapu/WiFiManager
#include "config.h"
#include "net.h"
// 注意：不再 include "secrets.h" —— 凭据由 WiFiManager 存/取 ESP32 NVS

static WiFiManager wm;

static void start_mdns() {
  if (MDNS.begin(MDNS_HOST)) {              // → vibelamp.local
    MDNS.addService("http", "tcp", HTTP_PORT);
  }
}

bool net_begin() {
  WiFi.mode(WIFI_STA);

  // 配网门户超时：超时后 autoConnect 返回 false，固件继续跑（进失联态等重配），
  // 不死等、不阻塞看门狗逻辑。
  wm.setConfigPortalTimeout(PROV_PORTAL_TIMEOUT);

  // autoConnect：
  //  - NVS 有可用凭据 → 直接连，连上返回 true；
  //  - 无凭据 / 连不上 → 起 AP「VibeLamp-Setup」+ captive portal，
  //    用户在手机浏览器选 WiFi、填密码 → WiFiManager 自动存 NVS、重连。
  bool ok;
  if (PROV_AP_PASS[0] == '\0') {
    ok = wm.autoConnect(PROV_AP_NAME);                 // 开放热点
  } else {
    ok = wm.autoConnect(PROV_AP_NAME, PROV_AP_PASS);   // 加密热点
  }

  if (ok) {
    start_mdns();
  }
  return ok;
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }

void net_reset_and_reboot() {
  wm.resetSettings();   // 清 NVS 里的 WiFi 凭据
  delay(300);
  ESP.restart();        // 重启 → 下次 net_begin 无凭据 → 自动进配网门户
}

bool net_start_portal() {
  bool ok;
  if (PROV_AP_PASS[0] == '\0') {
    ok = wm.startConfigPortal(PROV_AP_NAME);
  } else {
    ok = wm.startConfigPortal(PROV_AP_NAME, PROV_AP_PASS);
  }
  if (ok) start_mdns();
  return ok;
}
```

> **`secrets.h` 去向**：Part A 之后 `net.cpp` 不再 include 它。`firmware/.gitignore` 里那条 `include/secrets.h`（计划 01）可保留——Part B① 的 BLE pop（proof-of-possession 口令）等可选机密仍适合放它，不强制删。`net_begin()` 签名与返回语义与计划 01 完全一致（连上 true / 失败 false），所以 `main.cpp` 里 `if (net_begin()) ... else ...` 那段**不用改逻辑**。

- [ ] **Step 3: 编译验证（不插板也能编）**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。证明 WiFiManager 头文件、`autoConnect`/`resetSettings`/`startConfigPortal` 签名用法正确、链接通过。

- [ ] **Step 4: 上板 + 手机配网验证（首次配网，靠上板 + 手机验证）**

```bash
cd firmware && pio run -e esp32 -t upload && pio device monitor
```
操作与期望：
1. 因为是新固件、NVS 无凭据（或已被 reset），串口应打印 WiFiManager 起门户的日志；ESP32 出现一个 WiFi 热点 **`VibeLamp-Setup`**。
2. 手机/电脑连上 `VibeLamp-Setup`（无密码）→ 系统弹出 captive portal（不弹就浏览器访问 `http://192.168.4.1`）。
3. 点 **Configure WiFi** → 选你家 WiFi → 填密码 → Save。
4. ESP32 自动重连、存 NVS；串口回到计划 01 的 `WiFi OK, http://vibelamp.local IP=192.168.x.x`。
5. Mac 上 `ping vibelamp.local` 通；`curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'` 灯变蓝呼吸（验证配网后主链路照常工作）。

- [ ] **Step 5: 断电重启验证「凭据持久」（靠上板验证）**

拔电再上电。Expected：**不再弹配网门户**，直接连上家里 WiFi（凭据已存 NVS，断电不丢）→ 串口直接 `WiFi OK`。这验证了计划设计 §7 的「②首次配网一次，③日常运行永不插线」。

- [ ] **Step 6: 提交**

```bash
cd firmware && git add src/net.h src/net.cpp
git commit -m "feat(firmware): WiFiManager 网页配网替换 secrets.h 硬编码"
```

---

## Task 3: 重配网入口 —— 开机长按按钮 + /reset HTTP 端点

让换网/搬家时不用重烧、不用拆机：开机按住按钮即清凭据重配；再附一个 `/reset` 端点作软件备选。**靠上板 + 手机验证**。

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `firmware/src/api_server.cpp`

- [ ] **Step 1: `main.cpp` 的 `setup()` 在 `net_begin()` 之前查重配网按钮**

在 `setup()` 里、`display().begin();` 之后、`net_begin()` 之前插入：

```cpp
  // —— 重配网入口：开机时长按按钮 → 清凭据 + 重启进配网门户 ——
  pinMode(PIN_RESET_BTN, INPUT_PULLUP);
  if (digitalRead(PIN_RESET_BTN) == LOW) {        // 上电瞬间已按下
    Serial.println("检测到重配网按钮，按住 3s 将清除 WiFi 凭据...");
    uint32_t start = millis();
    while (digitalRead(PIN_RESET_BTN) == LOW) {
      if (millis() - start >= RESET_HOLD_MS) {
        Serial.println("重置 WiFi 凭据，重启进入配网门户");
        net_reset_and_reboot();                   // 内部 resetSettings + ESP.restart()
      }
      delay(50);
    }
    // 没按满 3s 松手 → 不重置，继续正常启动
  }
```

> 选「开机长按」而非「运行中随时按」：开机判定一次最简单、零误触、不占 loop 时间；GPIO0 同时是 BOOT 键，运行中另作他用也不冲突。运行中想重配走下面的 `/reset` 端点。

- [ ] **Step 2: `api_server.cpp` 加 `GET /reset` 端点（软件备选）**

在 `api_begin()` 里注册路由（与计划 01 的 `/state`、`/health` 并列）：

```cpp
static void handle_reset() {
  server.send(200, "text/plain", "resetting wifi, rebooting into setup portal");
  delay(200);
  net_reset_and_reboot();    // 来自 net.h
}
```

并在 `api_begin()` 里加一行注册，同时在 `api_server.cpp` 顶部 `#include "net.h"`：

```cpp
  server.on("/reset", HTTP_GET, handle_reset);
```

> 用 GET 是为了浏览器一键可点（`http://vibelamp.local/reset`）。家庭可信 LAN 内可接受（与计划 01 已知限制「HTTP 无鉴权，假设可信 LAN」一致）；将来加 token 时一并保护。

- [ ] **Step 3: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。

- [ ] **Step 4: 上板验证两条重配网路（靠上板 + 手机验证）**

```bash
cd firmware && pio run -e esp32 -t upload
```
- **按钮路**：断电 → 按住 BOOT 键 → 上电并保持 3 秒 → 串口打印「重置 WiFi 凭据」并重启 → 出现 `VibeLamp-Setup` 热点（凭据已清）。重新配一次能连上。
- **HTTP 路**：设备在线时 `curl http://vibelamp.local/reset`（或浏览器打开）→ 设备回 `resetting...` 后重启进门户。

- [ ] **Step 5: 提交**

```bash
cd firmware && git add src/main.cpp src/api_server.cpp
git commit -m "feat(firmware): 重配网入口（开机长按按钮 + /reset 端点）"
```

---

## Part A 小结（v1 完成标准）

- `pio run -e esp32` 与 `pio run -e esp32_ring` 编译成功（WiFiManager 依赖正确拉取）。
- 新固件首次上电起 `VibeLamp-Setup` 热点，手机浏览器配网后连上家里 WiFi，凭据存 NVS。
- 断电重启不再要求配网，直接连上（凭据持久）。
- 配网后 `vibelamp.local` 的 `/state` 主链路照常工作（计划 01/02 无感知）。
- 开机长按按钮 或 `GET /reset` 均能清凭据、重进配网门户。
- `net.cpp` 不再依赖 `secrets.h`。

---

# Part B — BLE（v1.1 后续增强）

> 标注：以下为 **v1.1**。先把 Part A 的 WiFi 主链路 + 计划 01 失联处理做扎实再上 BLE（与设计 §6.3「v1 先把 WiFi 主链路做扎实，BLE 兜底后补」一致）。详细度略低于 Part A，但 API 与骨架可直接落地。

## Task 4 (Part B①): BLE 配网 —— 套用乐鑫官方 App + WiFiProv

**思路**：不自写手机 App。手机装乐鑫官方 **「ESP BLE Provisioning」**（iOS App Store / 安卓 Play & 国内商店均有），固件用 Arduino-ESP32 自带的 `WiFiProv`（底层 ESP-IDF wifi_provisioning），以 BLE 为传输通道。固件开机若无凭据，起 BLE provisioning service，串口/QR 给出配网信息；App 扫 QR → 选 WiFi → 填密码 → 凭据写入 NVS（与 Part A 同一份 NVS）。

> **与 Part A 的关系**：这是**第二条配网路**，编译期用 `-DPROV_MODE` 二选一（默认 `PROV_WEB` 走 Part A；`PROV_BLE` 走本任务），不在同一固件里同时跑两套门户。

**Files:**
- Create: `firmware/src/ble_prov.h`
- Create: `firmware/src/ble_prov.cpp`
- Modify: `firmware/include/config.h`（加 `PROV_MODE` 与 pop/service 常量）
- Modify: `firmware/src/net.cpp`（`net_begin()` 按 `PROV_MODE` 分流）
- Modify: `firmware/platformio.ini`（加 `esp32_ble_prov` env）

- [ ] **Step 1: `config.h` 加配网模式与 BLE 配网参数**

```cpp
// —— 配网模式（编译期二选一）——
#define PROV_WEB 1     // Part A：WiFiManager 网页配网
#define PROV_BLE 2     // Part B①：BLE 配网（乐鑫官方 App）
#ifndef PROV_MODE
#define PROV_MODE PROV_WEB
#endif

// —— BLE 配网（仅 PROV_MODE==PROV_BLE 用）——
#define BLE_PROV_SERVICE_NAME "PROV_VIBELAMP"   // BLE 广播名，App 里看到的设备名
#define BLE_PROV_POP          "vibelamp123"     // proof-of-possession 配对口令（QR 里带）
```

- [ ] **Step 2: 写 `ble_prov.h`**

```cpp
#pragma once
#include <stdbool.h>
// 起 BLE provisioning（乐鑫 WiFiProv）。已存凭据则直接连、不起 BLE。
// 阻塞等待直到连上（或内部超时）。连上返回 true。
bool ble_prov_begin();
```

- [ ] **Step 3: 写 `ble_prov.cpp`（关键骨架，API 核自 espressif/arduino-esp32 WiFiProv 示例）**

```cpp
#include "config.h"
#if PROV_MODE == PROV_BLE
#include <WiFi.h>
#include <WiFiProv.h>          // Arduino-ESP32 自带
#include <ESPmDNS.h>
#include "ble_prov.h"
#include "net.h"

static volatile bool s_connected = false;

// WiFiProv 事件回调：打印进度、捕获「已连上」
static void prov_event(arduino_event_t *sys_event) {
  switch (sys_event->event_id) {
    case ARDUINO_EVENT_PROV_START:
      Serial.println("BLE 配网已启动，请用「ESP BLE Provisioning」App 扫码配网");
      break;
    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.printf("配网成功，IP=%s\n", WiFi.localIP().toString().c_str());
      s_connected = true;
      break;
    case ARDUINO_EVENT_PROV_CRED_FAIL:
      Serial.println("配网失败：WiFi 密码错或信号差");
      break;
    case ARDUINO_EVENT_PROV_END:
      Serial.println("BLE 配网流程结束");
      break;
    default: break;
  }
}

bool ble_prov_begin() {
  WiFi.onEvent(prov_event);

  // 默认 128-bit service UUID（来自官方示例，可自定义）
  uint8_t uuid[16] = {
    0xb4, 0xdf, 0x5a, 0x1c, 0x3f, 0x6b, 0xf4, 0xbf,
    0xea, 0x4a, 0x82, 0x03, 0x04, 0x90, 0x1a, 0x02
  };

  // scheme=BLE；HANDLER_FREE_BTDM=配网后释放蓝牙栈省内存；
  // SECURITY_1=带 pop 的加密信道；reset_provisioned=false（已存凭据则直接连不起 BLE）
  WiFiProv.beginProvision(
    NETWORK_PROV_SCHEME_BLE,
    NETWORK_PROV_SCHEME_HANDLER_FREE_BTDM,
    NETWORK_PROV_SECURITY_1,
    BLE_PROV_POP,
    BLE_PROV_SERVICE_NAME,
    nullptr,          // service_key（BLE 模式忽略）
    uuid,
    false);

  // 串口打印 QR，App 扫码即配（也可在 App 里手动选设备名 PROV_VIBELAMP）
  WiFiProv.printQR(BLE_PROV_SERVICE_NAME, BLE_PROV_POP, "ble");

  // 阻塞等连上（最长 ~180s）
  uint32_t start = millis();
  while (!s_connected && millis() - start < 180000UL) {
    delay(200);
  }
  if (s_connected && MDNS.begin(MDNS_HOST)) {
    MDNS.addService("http", "tcp", HTTP_PORT);
  }
  return s_connected;
}
#endif
```

> **API 名注意**：Arduino-ESP32 core 3.x 起，provisioning 常量从 `WIFI_PROV_*` 改名为 `NETWORK_PROV_*`（`WIFI_PROV_SCHEME_BLE` → `NETWORK_PROV_SCHEME_BLE` 等），上面用的是 3.x 名。若编译报「未声明标识符」，对照你装的 core 版本在 `WiFiProv.h` / `NetworkProvisioning.h` 里 grep 确认确切宏名再改——**这是上板前必做的一次核对**（core 版本差异是此处最常见的坑）。

- [ ] **Step 4: `net.cpp` 的 `net_begin()` 按 `PROV_MODE` 分流**

把 Task 2 的 `net_begin()` 改成：

```cpp
bool net_begin() {
  WiFi.mode(WIFI_STA);
#if PROV_MODE == PROV_BLE
  return ble_prov_begin();          // Part B①：BLE 配网
#else
  // —— Part A：WiFiManager 网页配网 ——（Task 2 原内容）
  wm.setConfigPortalTimeout(PROV_PORTAL_TIMEOUT);
  bool ok = (PROV_AP_PASS[0] == '\0')
            ? wm.autoConnect(PROV_AP_NAME)
            : wm.autoConnect(PROV_AP_NAME, PROV_AP_PASS);
  if (ok) start_mdns();
  return ok;
#endif
}
```

并在 `net.cpp` 顶部条件包含：`#if PROV_MODE == PROV_BLE` 时 `#include "ble_prov.h"`。

- [ ] **Step 5: `platformio.ini` 加 BLE 配网 env**

```ini
[env:esp32_ble_prov]
extends = env:esp32
build_flags =
    -DDISPLAY_TYPE=DISPLAY_RGB_LED
    -DPROV_MODE=PROV_BLE
```

> BLE provisioning 占 flash 较大，若链接报「分区不够」，在 `[env:esp32_ble_prov]` 加 `board_build.partitions = huge_app.csv`（或 `min_spiffs.csv`）。

- [ ] **Step 6: 编译**

Run: `cd firmware && pio run -e esp32_ble_prov`
Expected: `SUCCESS`（先解决 Step 3 注里的宏名核对，再编）。

- [ ] **Step 7: 上板 + 手机 App 配网（靠上板 + 手机验证）**

```bash
cd firmware && pio run -e esp32_ble_prov -t upload && pio device monitor
```
1. 串口打印 `BLE 配网已启动` 与一段 QR（ASCII）。
2. 手机装并打开「ESP BLE Provisioning」App → 扫串口里的 QR（或选设备 `PROV_VIBELAMP`、输 pop `vibelamp123`）。
3. App 里选家里 WiFi、填密码 → Provision。
4. 串口出现 `配网成功，IP=192.168.x.x`；`ping vibelamp.local` 通；`curl .../state` 灯变色。

- [ ] **Step 8: 提交**

```bash
cd firmware && git add src/ble_prov.h src/ble_prov.cpp include/config.h src/net.cpp platformio.ini
git commit -m "feat(firmware): BLE 配网（乐鑫 WiFiProv，可选 PROV_MODE）"
```

---

## Task 5 (Part B②): BLE GATT 状态服务 —— WiFi 断时的兜底接收端

**目标**：固件加一个 BLE GATT 服务，开一个「状态」特征值（可写），接收**与 HTTP `/state` 完全同款**的 wire JSON（`{"sessions":[{"state":"working","tool":"code"},...]}`）。写入后走计划 01 已有的同一套 `parse_state`/`parse_tool`/Session 写入路径——**不另立状态语义**。这样 WiFi 断时，Mac 端经 BLE 写这个特征值就能继续驱动灯。

**Files:**
- Create: `firmware/src/ble_state.h`
- Create: `firmware/src/ble_state.cpp`
- Modify: `firmware/include/config.h`（BLE 状态服务/特征 UUID）
- Modify: `firmware/src/api_server.h/.cpp`（抽出 JSON→Session 的公共函数，供 HTTP 与 BLE 共用）
- Modify: `firmware/src/main.cpp`（setup 里 `ble_state_begin()`）

- [ ] **Step 1: `config.h` 加 BLE 状态服务 UUID**

```cpp
// —— BLE 状态推送服务（Part B②，与配网无关，可与 WiFi 共存）——
#define BLE_STATE_DEVICE_NAME  "VibeLamp"
#define BLE_STATE_SERVICE_UUID "6e6c0001-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_STATE_CHAR_UUID    "6e6c0002-b5a3-f393-e0a9-e50e24dcca9e"
```

- [ ] **Step 2: 从 `api_server.cpp` 抽出「JSON 字符串 → 写入 Session 表」的公共函数**

计划 01 的 `handle_state()` 里有「解析 JSON → 填 `g_sessions` → 置 `g_last_ms`」一段。把它抽成可被 BLE 复用的公共函数，在 `api_server.h` 暴露：

```cpp
// api_server.h 追加：把一段 /state 同款 JSON 应用到会话表（HTTP 与 BLE 共用）。
// 返回 true=解析成功。内部会重置看门狗计时（g_last_ms = millis()）。
bool api_apply_state_json(const char* json, size_t len);
```

`api_server.cpp` 里把 `handle_state()` 的解析体迁进 `api_apply_state_json()`，`handle_state()` 改为调它：

```cpp
bool api_apply_state_json(const char* json, size_t len) {
  JsonDocument doc;
  if (deserializeJson(doc, json, len)) return false;
  JsonArray arr = doc["sessions"].as<JsonArray>();
  uint8_t cap = sizeof(g_sessions) / sizeof(g_sessions[0]);
  uint8_t n = 0;
  uint32_t now = millis();
  for (JsonObject o : arr) {
    if (n >= cap) break;
    State st = parse_state(o["state"]);
    ToolKind tk = parse_tool(o["tool"]);
    if (!(n < g_count && g_sessions[n].state == st && g_sessions[n].tool == tk))
      g_sessions[n].state_since_ms = now;
    g_sessions[n].state = st;
    g_sessions[n].tool = tk;
    g_sessions[n].pulse_at_ms = 0;
    ++n;
  }
  g_count = n;
  g_last_ms = now;          // 重置看门狗：BLE 收到也算「有人在喂」
  return true;
}

static void handle_state() {
  String body = server.arg("plain");
  if (api_apply_state_json(body.c_str(), body.length()))
    server.send(200, "application/json", "{\"ok\":true}");
  else
    server.send(400, "text/plain", "bad json");
}
```

> 关键：**BLE 写也调 `api_apply_state_json` 并刷新 `g_last_ms`**——这样看门狗对「数据从 WiFi 来还是 BLE 来」无感知，WiFi 断、BLE 续推时灯不会误判失联。这正是「双通道冗余，灯几乎不会真失联」（设计 §6.3）。

- [ ] **Step 3: 写 `ble_state.h`**

```cpp
#pragma once
void ble_state_begin();   // 起 BLE GATT 状态服务，注册可写特征
```

- [ ] **Step 4: 写 `ble_state.cpp`（Arduino-ESP32 自带 BLEDevice，关键骨架）**

```cpp
#include "config.h"
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include "ble_state.h"
#include "api_server.h"     // api_apply_state_json

class StateCharCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* ch) override {
    std::string v = ch->getValue();        // 收到的 JSON 字符串
    api_apply_state_json(v.c_str(), v.size());   // 复用 HTTP 同款路径
  }
};

void ble_state_begin() {
  BLEDevice::init(BLE_STATE_DEVICE_NAME);
  BLEServer* server = BLEDevice::createServer();
  BLEService* svc = server->createService(BLE_STATE_SERVICE_UUID);
  BLECharacteristic* ch = svc->createCharacteristic(
      BLE_STATE_CHAR_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  ch->setCallbacks(new StateCharCallbacks());
  svc->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLE_STATE_SERVICE_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}
```

> **共存说明**：设计 §9「WiFi + BLE 共存对低流量场景无压力」。本服务与 STA 模式 WiFi 同时跑没问题。注意：若同时编进了 Task 4 的 BLE **配网**（`PROV_MODE==PROV_BLE`，配网后用了 `FREE_BTDM` 释放蓝牙栈），二者会争蓝牙栈——**建议 BLE 配网与 BLE 状态服务不要同时启用**（配网用 Part A 网页路、状态兜底用本服务，是最干净的组合）。`main.cpp` 里据此决定是否调 `ble_state_begin()`。

- [ ] **Step 5: `main.cpp` setup 里起 BLE 状态服务**

在 `setup()` 末尾（`api_begin()` 之后）加：

```cpp
#if PROV_MODE != PROV_BLE        // 避免与 BLE 配网争蓝牙栈
  ble_state_begin();
  Serial.println("BLE 状态兜底服务已启动（设备名 VibeLamp）");
#endif
```

并 `#include "ble_state.h"`。

- [ ] **Step 6: 编译**

Run: `cd firmware && pio run -e esp32`
Expected: `SUCCESS`。（BLE 库占空间大，若报分区不够，同 Task 4 Step 5 注调分区表。）

- [ ] **Step 7: 上板 + 用手机 BLE 调试 App 验证（靠上板 + 手机验证）**

```bash
cd firmware && pio run -e esp32 -t upload
```
用手机的 **nRF Connect**（或 LightBlue）BLE 调试 App：
1. 扫到设备 `VibeLamp` → 连接 → 找到 service `6e6c0001-...` 下的 characteristic `6e6c0002-...`。
2. 往该特征写入 UTF-8 文本：`{"sessions":[{"state":"needs_you"}]}`。
3. Expected：灯立刻变**红慢闪**（与 HTTP /state 同效果）。再写 `{"sessions":[{"state":"working","tool":"command"}]}` → 紫呼吸。
4. 把 ESP32 拔网线/关路由（WiFi 断）后再写 → 灯仍随 BLE 写变化、**不进失联态**（证明 BLE 续上了看门狗）。

- [ ] **Step 8: 提交**

```bash
cd firmware && git add src/ble_state.h src/ble_state.cpp src/api_server.h src/api_server.cpp src/main.cpp include/config.h
git commit -m "feat(firmware): BLE GATT 状态服务（复用 /state 路径，WiFi 断兜底）"
```

---

## Task 6 (Part B②): Mac 端 bleak 桥接进程 + 守护进程降级

**为什么需要常驻桥接进程（诚实说明）**：计划 02 的钩子是**一次性 `curl`**，连守护进程都不自己维持长连接（push 完即退）。BLE 不同于 HTTP——它是**有连接的**：要先 scan→connect→discover→write，建连本身就要 1～3 秒。如果每条状态都现连现断，延迟高、还会和「设备已被别人连着」打架。所以**必须有一个常驻进程握住这条 BLE 连接**，状态来了直接 write。Claude Code/Codex 的 hook 做不到这点，于是这活落在 Mac 端：让一个 **bleak 桥接进程**常驻，守护进程（计划 02）push WiFi 失败时把同一份 wire JSON 交给它，由它经已握住的 BLE 连接写给灯。

**Files:**
- Create: `daemon/vibelamp/ble_bridge.py`
- Modify: `daemon/vibelamp/config.py`
- Modify: `daemon/vibelamp/lamp_client.py`
- Create: `daemon/tests/test_ble_fallback.py`

- [ ] **Step 1: `config.py` 加 BLE 桥接开关与本地 socket**

在计划 02 的 `config.py` 末尾追加：

```python
# —— BLE 兜底桥接（Part B②，可选）——
BLE_ENABLED = os.environ.get("VIBELAMP_BLE", "0") == "1"   # 默认关；置 1 启用
BLE_DEVICE_NAME = "VibeLamp"                                # 与固件 BLE_STATE_DEVICE_NAME 一致
BLE_SERVICE_UUID = "6e6c0001-b5a3-f393-e0a9-e50e24dcca9e"
BLE_CHAR_UUID = "6e6c0002-b5a3-f393-e0a9-e50e24dcca9e"
# 守护进程 → 桥接进程 的本地通道（Unix domain socket）
BLE_BRIDGE_SOCK = os.environ.get(
    "VIBELAMP_BLE_SOCK", "/tmp/vibelamp-ble.sock")
```

- [ ] **Step 2: 写 `ble_bridge.py`（常驻桥接进程骨架）**

```python
"""Vibe Lamp BLE 桥接：常驻握住灯的 BLE 连接，
   收守护进程经 Unix socket 转来的 wire JSON，写到灯的状态特征。
   仅在 WiFi 主链路不可达时由守护进程调用。需 `pip install bleak`。"""
import asyncio
import os
import socket

from bleak import BleakClient, BleakScanner
from . import config


async def _find_lamp():
    """按设备名扫到灯，返回 BLEDevice（扫不到返回 None）。"""
    return await BleakScanner.find_device_by_name(
        config.BLE_DEVICE_NAME, timeout=8.0)


async def _serve(sock_path):
    # 清理旧 socket
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.setblocking(False)
    loop = asyncio.get_event_loop()

    client = None
    while True:
        data = await loop.sock_recv(srv, 4096)   # 守护进程发来的 wire JSON（bytes）
        if not data:
            continue
        # 懒连接 + 断线重连：第一次/掉线时才 scan+connect
        if client is None or not client.is_connected:
            dev = await _find_lamp()
            if dev is None:
                continue                          # 扫不到灯，丢弃这次（下次再试）
            client = BleakClient(dev)
            try:
                await client.connect()
            except Exception:
                client = None
                continue
        try:
            await client.write_gatt_char(
                config.BLE_CHAR_UUID, data, response=False)
        except Exception:
            client = None                         # 写失败 → 下次重连


def run():
    asyncio.run(_serve(config.BLE_BRIDGE_SOCK))


if __name__ == "__main__":
    run()
```

> **运行方式**：作为 launchd 的**第二个** LaunchAgent 常驻（与计划 02 的守护进程并列；plist 同款，`ProgramArguments` 改 `-m vibelamp.ble_bridge`，仅在 `BLE_ENABLED` 时安装）。它不监听网络，只听本地 Unix socket，安全。

- [ ] **Step 3: `lamp_client.py` —— WiFi push 失败时改走 BLE 桥**

改计划 02 的 `push()`：HTTP 成功就返回；失败且 `BLE_ENABLED` 时，把同一份 JSON 经 Unix socket 发给桥接进程（datagram，不阻塞、不抛异常）：

```python
import socket

def _send_ble(payload):
    """把 wire JSON 经本地 socket 交给 BLE 桥接进程。绝不抛异常。"""
    try:
        data = json.dumps(payload).encode("utf-8")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(data, config.BLE_BRIDGE_SOCK)
        s.close()
        return True
    except Exception as e:
        log.debug("ble bridge send failed: %s", e)
        return False


def push(payload, url=None, timeout=None):
    url = url or config.LAMP_URL
    timeout = timeout or config.PUSH_TIMEOUT_SEC
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True
    except Exception as e:
        log.debug("lamp push failed: %s", e)
    # —— WiFi 不可达：BLE 兜底（仅在启用时）——
    if config.BLE_ENABLED:
        return _send_ble(payload)
    return False
```

> 语义：BLE 是**降级路径**，只在 WiFi push 失败时走。`_send_ble` 把 JSON 丢给桥接进程就返回（fire-and-forget，与守护进程「push 绝不阻塞钩子」的纪律一致）。真正的 BLE 写在桥接进程里异步发生。

- [ ] **Step 4: 写降级决策的纯逻辑测试（可 native 测的部分）**

`tests/test_ble_fallback.py`：

```python
import json, socket, os, tempfile, time
from vibelamp import lamp_client, config

def test_push_fallback_to_ble_when_http_down(monkeypatch):
    # 开 BLE 兜底，指向一个临时 Unix socket（充当桥接进程）
    sock_path = os.path.join(tempfile.mkdtemp(), "ble.sock")
    monkeypatch.setattr(config, "BLE_ENABLED", True)
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCK", sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path); srv.settimeout(2.0)

    # HTTP 指向没人监听的端口 → 必然失败 → 应改走 BLE
    ok = lamp_client.push({"sessions": [{"state": "needs_you"}]},
                          url="http://127.0.0.1:1/state", timeout=0.3)
    assert ok is True                                  # BLE 兜底成功
    got = json.loads(srv.recv(4096).decode())
    assert got == {"sessions": [{"state": "needs_you"}]}  # 桥接收到同款 wire
    srv.close()

def test_no_ble_fallback_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "BLE_ENABLED", False)
    ok = lamp_client.push({"sessions": []},
                          url="http://127.0.0.1:1/state", timeout=0.3)
    assert ok is False                                 # 没开 BLE → 老行为，返回 False
```

- [ ] **Step 5: 跑纯逻辑测试**

Run: `cd daemon && python -m pytest tests/test_ble_fallback.py -v`
Expected: 2 个 PASS。（这验证「HTTP 失败 → 降级把同款 JSON 投给桥接 socket」的决策逻辑；真正的 BLE 收发靠下一步上板验证。）

- [ ] **Step 6: 真实 BLE 端到端（靠真机 + 真灯验证）**

前置：灯已烧 Task 5 的 BLE 状态服务固件；Mac `pip install bleak`。
```bash
# 终端 A：起桥接进程
cd daemon && VIBELAMP_BLE=1 python -m vibelamp.ble_bridge
# 终端 B：起守护进程，开 BLE 兜底
cd daemon && VIBELAMP_BLE=1 python -m vibelamp
```
验证：
1. **拔掉灯的 WiFi**（关路由 / 让 `vibelamp.local` 不可达）。
2. 终端 C 模拟一个钩子：`curl -s -X POST http://127.0.0.1:8787/event -d '{"hook_event_name":"Notification","session_id":"s1"}'`。
3. Expected：HTTP push 失败 → 走 BLE 桥 → 桥接进程经 BLE 写灯 → 灯**红慢闪**（即使 WiFi 断着）。
4. 恢复 WiFi 后下一次心跳走回 HTTP 主链路（BLE 仅兜底）。

- [ ] **Step 7: 提交**

```bash
cd daemon && git add vibelamp/ble_bridge.py vibelamp/config.py vibelamp/lamp_client.py tests/test_ble_fallback.py
git commit -m "feat(daemon): BLE 兜底桥接进程 + WiFi 失败降级（bleak）"
```

---

## 验收（整计划完成标准）

**Part A（v1，必须全绿）**
- `pio run -e esp32` 与 `pio run -e esp32_ring` 编译成功，WiFiManager `@2.0.17` 正确拉取。
- 新固件首次上电起 `VibeLamp-Setup` 热点；手机浏览器配网后连上家里 WiFi，凭据存 NVS。
- 断电重启不再要求配网（凭据持久）。
- 配网后 `vibelamp.local` 的 `/state`、`/health`、看门狗均照常（计划 01/02 行为不变）。
- 开机长按按钮 与 `GET /reset` 都能清凭据、重进配网门户。
- `net.cpp` 不再 `#include "secrets.h"`。

**Part B（v1.1 增强）**
- `pio run -e esp32_ble_prov` 编译成功；手机用乐鑫官方 App 能 BLE 配网（Task 4）。
- BLE 状态服务固件下，nRF Connect 写特征值能驱动灯，WiFi 断时仍生效、不误失联（Task 5）。
- `python -m pytest tests/test_ble_fallback.py` 全绿；真机下 WiFi 断 → BLE 桥接续推（Task 6）。

## 后续计划（本计划不含）

- **OTA 无线固件升级**（设计 §7 ①、§11 v1.1+）：配网完成后下一步，免 USB 刷固件。
- **手机直控灯**（改色/调亮度/静音）：可复用 Task 5 的 BLE GATT 服务，加「命令」特征。
- **BLE 状态服务加鉴权 / 配对绑定**：v1 假设可信环境（与 HTTP 无鉴权一致），将来收紧。

## 自查记录

- **Spec 覆盖**：§6.2「v1 WiFiManager 网页配网」= Part A（Task 1–3）；§6.2「v1.1 备选 BLE 配网（乐鑫官方 App）」= Part B① Task 4；§6.3「WiFi 断时切 BLE 兜底推送、双通道冗余」= Part B② Task 5（固件 GATT）+ Task 6（Mac bleak 桥接）；§7 ②「首次配网存 NVS、断电不丢」与 ④「换网重配」由 Task 2 Step 5 与 Task 3 验证。
- **延续计划 01/02**：沿用 `firmware/src/net.cpp`、`net.h`、`include/config.h`、`platformio.ini`、`src/main.cpp`、`src/api_server.*` 文件结构；标注每个文件是「新建」还是「修改 01/02」；`net_begin()` 返回语义不变，`main.cpp` 调用处零改逻辑；BLE 状态服务复用计划 01 的 `parse_state`/`parse_tool`/Session 写入与计划 02 的 wire 协议（`{"sessions":[{"state","tool"}]}`），不另立语义；commit 用 `feat(firmware)`/`feat(daemon)` 中文风格。
- **版本/API 核实（2026-06-13）**：WiFiManager 取 **v2.0.17**（GitHub Releases + PlatformIO Registry 当前最新稳定）；`autoConnect(apName[, apPass])` / `startConfigPortal(...)` / `setConfigPortalTimeout(秒)` / `resetSettings()` 均核自 Context7（`/tzapu/wifimanager`）与官方 wiki；开机长按按钮 + 短按起门户的范式取自其官方 usage-pattern。BLE provisioning 的 `WiFiProv.beginProvision(scheme=…SCHEME_BLE, …)`、默认 UUID、`printQR(name,pop,"ble")` 核自 espressif/arduino-esp32 的 `WiFiProv` 官方示例；已标注 core 3.x 把 `WIFI_PROV_*` 改名 `NETWORK_PROV_*`，上板前须按所装 core 版本 grep 核对宏名。
- **诚实约束**：全程明确「嵌入式 WiFi/BLE 无法纯 native 单测」，配网/BLE 步骤一律标「靠上板 + 手机验证」（编译只证 API 用法对）；唯一能 native 测的是 Mac 端「HTTP 失败→BLE 降级投递」的纯逻辑（Task 6 Step 4–5，用假 socket/mock）。
- **诚实约束·BLE 兜底依赖**：明写了「为什么必须有 Mac 端常驻 bleak 桥接进程」——hook/守护进程的 push 是一次性、无连接的，而 BLE 是有连接、建连耗时的，无法每条状态现连现断，故需常驻进程握住连接；守护进程仅在 WiFi push 失败时把同款 JSON 经本地 socket 交给它。
- **无占位**：每个代码步骤给完整可编译/可运行代码与确切命令、期望输出；硬件步骤给接线/操作/期望现象。
- **已知取舍**：BLE 配网（Part B①，配后释放蓝牙栈）与 BLE 状态服务（Part B②，常驻蓝牙栈）会争蓝牙栈，已建议「配网走网页路、状态兜底走 BLE 服务」的干净组合，并在 `main.cpp` 用 `#if PROV_MODE != PROV_BLE` 互斥；BLE provisioning 占 flash 大，给了改分区表的兜底。
```