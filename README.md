# Vibe Lamp

> AI 编码状态实体氛围灯 —— 把 Claude Code / Codex 会话的实时状态做成一盏桌面氛围灯。
> 余光一瞥就知道 AI 在干活、干完了、还是卡住要你介入，不用盯着屏幕。

**蓝 = 干活中 · 绿 = 完成 · 红 = 要你介入。** 它的灵感来自 [Vibe Island](https://vibeisland.app/)（macOS 刘海/菜单栏面板）——把同样的状态搬到桌上一盏看得见的灯上，可以说是它的「实体灯版」。

> **但不依赖、也无需安装 Vibe Island。** Vibe Lamp 直接读各 agent 自己的钩子（Claude Code `~/.claude/settings.json`、Codex `~/.codex/hooks.json`）拿状态，和 Vibe Island 是各自独立的「钩子消费者」。两者可以共存（钩子会各跑各的），也可以只装其一。

---

## 它解决什么

盯着终端等 AI agent 跑完、或者错过它卡住等你批准权限，都很累。Vibe Lamp 把当前编码会话的状态变成一束环境光：

- **环境感知**：状态做成桌面氛围光，不抢注意力，但需要时一眼可见。
- **不说谎**：灯永远反映真实状态。断线时显示「失联」（琥珀色慢呼吸），而不是冻结在旧颜色误导你。
- **多 agent**：同时支持 Claude Code 和 Codex，架构上可扩展更多。

---

## 架构一览

业务逻辑全在 Mac 端，ESP32 只是个「傻瓜显示端」。三层各司其职：

```
┌──────────────────────────── 你的 Mac ────────────────────────────┐
│                                                                   │
│   Claude Code ──hooks──┐                                          │
│                        ├──→  转译器（常驻后台守护进程）              │
│   Codex ──────hooks────┘       · 合并所有会话状态                   │
│                                · 决定该给灯显示什么                  │
│                                · 心跳 + 超时兜底 + 推送重试           │
│                                       │                           │
└───────────────────────────────────────│──────────────────────────┘
                                        │  WiFi / HTTP 推送 + 心跳
                                        ▼
                              ┌────────────────────┐
                              │  ESP32（傻瓜显示端） │
                              │  · 收指令 → 驱动 LED │
                              │  · 看门狗 → 失联检测  │
                              └─────────│──────────┘
                                        ▼
                          RGB LED / WS2812 灯环（出色彩 + 动效）
```

- **采集层**：各 agent 用自带的钩子机制，状态变化时用一行 `curl` 把事件 POST 给本地转译器（带 `--max-time 1 || true`，转译器挂掉也绝不拖慢 agent 本身）。
- **转译/聚合层**：Mac 常驻守护进程，合并所有活动会话状态，算出「该显示什么」，经 WiFi 推给灯，并定期发心跳。
- **显示层**：ESP32 跑一个小 HTTP 服务收指令，本地逐帧渲染颜色与动效；超过约 30 秒没收到消息就进入「失联」显示。

> 加新 agent 只改转译器，**固件一行不动**。动画在固件本地跑，网络上只传「离散状态变化 + 心跳」，流量极小。

---

## 状态 → 颜色对照

| 状态 | 显示 | 什么时候 |
|---|---|---|
| ⚫ 空闲 | 暗 / 灭 | 会话结束 / 无活动 |
| 🔵 干活中 | 蓝**呼吸**，按工具分色：写码=蓝 · 跑命令=紫 · 搜索=青 | 提交指令 / 调用工具 |
| 💓 推进一步 | 每次工具调用一个**跳动脉冲** | 调用工具 |
| 🟢 完成 | 绿亮 3–5 秒 → **渐暗**回空闲 | 主回合结束 |
| 🔴 要你介入 | 红**慢闪** | 需要权限 / 批准请求 |
| ⚡ 出错 | 红**快闪一下** → 弹回干活色 | 工具调用报错 |
| 🟠 失联 | 暗琥珀**慢呼吸**（明显区别于以上各色） | 看门狗约 30 秒没收到消息 |
| 🚀 开机 | 上电跑个扫描动画 | 上电 / 会话开始 |

**铁律**：「空闲（暗）」和「失联（琥珀）」严格区分——一盏卡死在蓝色的灯，比没有灯还坏。

多会话时（如 Claude Code + Codex 同开），灯环按段分配，每个会话占一段各显各的状态；单颗 RGB LED 只显示合并后的整体状态。

---

## 怎么运转（合并优先级）

转译器把所有活动会话合并成「该给灯显示什么」，单灯/整体氛围时的优先级：

```
任一会话「要你介入」 → 🔴 红（最高优先级）
否则任一「出错」     → ⚡ 红快闪
否则任一「干活中」   → 🔵 蓝呼吸
否则有「刚完成」     → 🟢 绿（短暂，几秒后转空闲）
否则全部空闲        → ⚫ 暗
```

---

## 硬件清单

打样只要一颗 RGB LED 就能验证完整的色彩与动效模型；想要多会话分段显示再上 WS2812 灯环。

| 部件 | 打样（最简） | 成品（可选升级） |
|---|---|---|
| 主控 | 手上的 ESP32 开发板 | ESP32-C3 SuperMini / XIAO ESP32-C3（更小更便宜，功能零差别） |
| 显示 | 单颗**共阴 RGB LED**（3 路 PWM） | WS2812 灯环（16 灯） |
| 配件 | 面包板、杜邦线、3 个 ~220Ω 限流电阻 | WS2812 数据线串 ~330Ω 电阻、电源并 ~1000µF 电容 |
| 扩散 | 无（裸灯即可） | 乳白亚克力扩散罩 / 白色 PLA 3D 打印外壳 |
| 供电 | USB | USB |

> 详细接线、引脚、烧录、配网、点灯自测，见 **[HARDWARE.md](HARDWARE.md)**。

---

## 快速上手

跟着 **[HARDWARE.md](HARDWARE.md)** 走一遍，今晚就能让灯随真实会话变色，大致是：

1. 接线（单颗 RGB LED 或 WS2812 灯环）。
2. 烧录固件：`cd firmware && pio run -e esp32 -t upload`。
3. 配网：手机连 `VibeLamp-Setup` 热点 → 浏览器自动弹配网页 → 填家里 WiFi 密码。
4. 手动点灯自测：`curl -X POST http://vibelamp.local/state -d '{"sessions":[{"state":"working","tool":"code"}]}'`。
5. 接入真实会话：`cd daemon && python install.py install`，然后开 Claude Code / Codex 跑任务看灯。

---

## 开发 / 测试

**守护进程（Python，仅标准库 + pytest）：**

```bash
# 跑全部测试（49 个）
/Users/laofahai/Documents/workspace/vibe-lamp/.venv/bin/python -m pytest daemon

# 本地手动起守护进程
cd daemon && python -m vibelamp
```

**固件（PlatformIO / Arduino-ESP32 core 2.0.17）：**

```bash
cd firmware

# 跑渲染引擎纯逻辑单测（14 个，无需开发板）
pio test -e native

# 编译上板固件（单颗 RGB LED 版）
pio run -e esp32

# 编译灯环版
pio run -e esp32_ring

# 烧录 + 串口监视
pio run -e esp32 -t upload && pio device monitor
```

> 上面的 `pio` 可用仓库内置虚拟环境：`/Users/laofahai/Documents/workspace/vibe-lamp/.venv/bin/pio`。

---

## 项目状态 / 路线图

设计文档 + 5 份实现计划已完成并公开。当前进度：

**已完成**
- ✅ 设计文档（三层架构、状态模型、显示驱动抽象、断线处理、自定义设置）。
- ✅ ESP32 固件：联网 + mDNS（`vibelamp.local`）、HTTP `/state` `/health`、看门狗失联、四种显示硬件抽象、多会话分段、全套状态动效、开机动画。**14 个 native 测试全绿，`esp32` / `esp32_ring` 双 env 编译通过。**
- ✅ Python 守护进程：会话合并、心跳、超时兜底、推送重试、launchd 自启；Claude Code + Codex 钩子接入（含 Codex）。**49 个 pytest 全绿。**
- ✅ WiFiManager 网页配网（连 `VibeLamp-Setup` 热点，浏览器配网，凭据存 NVS，断电不丢）。
- ✅ 用户自定义设置：灯自带设置网页（亮度/颜色/动画，存 NVS，访问 `http://vibelamp.local/`）+ 守护进程配置文件 `~/.vibelamp/config.json`。

**待做（v1.1+）**
- ⏳ **计划 04 — BLE**：WiFi 断时切 BLE 兜底推送（双通道冗余）+ 乐鑫官方 App BLE 配网。
- ⏳ **真机校准**：工具名→颜色映射表细化、上板观察动效手感、亮度/呼吸速度调优；Codex 钩子字段真机核对（计划 03 Task 5）。
- ⏳ OTA 无线固件升级、手机直控灯、更多 agent（Gemini CLI / Cursor）、物理按钮、成品外壳。

---

## 目录结构

```
vibe-lamp/
├── README.md                  # 本文件
├── HARDWARE.md                # 今晚照着做的硬件上手指南
├── firmware/                  # ESP32 固件（PlatformIO）
│   ├── platformio.ini         #   env：esp32 / esp32_ring / native
│   ├── include/config.h       #   引脚、灯数、超时、mDNS 名、亮度上限
│   ├── src/                   #   渲染引擎 + 显示驱动 + 网络 + HTTP API
│   └── test/                  #   渲染引擎 native 单测
├── daemon/                    # Mac 端守护进程（Python，仅标准库）
│   ├── install.py             #   幂等装钩子 + launchd + Codex 配置
│   ├── vibelamp/              #   服务器、会话合并、推灯客户端、配置
│   └── tests/                 #   pytest
└── superpowers/               # 设计文档与实现计划
    ├── specs/                 #   总设计
    └── plans/                 #   5 份实现计划
```

---

## 技术栈

- **守护进程**：Python（仅标准库，零第三方依赖），macOS launchd 自启。
- **固件**：PlatformIO + Arduino-ESP32（core 2.0.17）、FastLED、ArduinoJson、WiFiManager。
- **寻址**：mDNS `vibelamp.local`（macOS 原生解析，无需额外软件）。

设计文档：[superpowers/specs/2026-06-13-vibe-lamp-design.md](superpowers/specs/2026-06-13-vibe-lamp-design.md)
