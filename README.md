# Vibe Lamp

AI 编码状态实体氛围灯 —— 把 Claude Code / Codex 会话的实时状态用一圈 LED 显示在桌面上。Vibe Island 的"实体灯版"。

> 余光一瞥就知道 AI 在干活（🔵蓝）、干完了（🟢绿）、还是卡住要你介入（🔴红）。

## 怎么运转

```
agent 钩子 (Claude Code / Codex) → Mac 转译器(常驻) → WiFi → ESP32 → WS2812 灯环
```

- **采集层**：各 agent 自带钩子，状态变化时调用本地转译器
- **转译/聚合层**：Mac 常驻守护进程，合并所有会话状态，决定该显示什么，经 WiFi 推给灯
- **显示层**：ESP32 傻瓜显示端，收指令驱动 LED，自带失联检测

## 文档

- 设计文档：[superpowers/specs/2026-06-13-vibe-lamp-design.md](superpowers/specs/2026-06-13-vibe-lamp-design.md)

## 状态

设计阶段。尚未开始实现。
