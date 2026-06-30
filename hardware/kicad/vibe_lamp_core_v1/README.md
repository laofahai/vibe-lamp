# Vibe Lamp Core V1 (KiCad)

Core V1 桌面状态灯主控板的 KiCad 工程目录。当前版本已经包含 PCB 源文件、渲染图、JLCPCB Gerber/BOM/CPL 输出，可作为 PCBA 打样下单基础。

40×40mm 圆角方板 · 2 层 · ESP32-C3-MINI-1（自带 PCB 天线，天线 keep-out 在位）· USB-C 供电+原生 USB · 板载 3.3V LDO · 板载 WS2812B 状态灯 · WS2812 扩展焊盘 · 清网按钮 · 工厂贴片，用户不焊接主板。

## 当前状态

- 电气完整：0 短路、0 未连接。
- 生产资料已生成：`fab/vibe_lamp_core_v1-gerber.zip`、`fab/vibe_lamp_core_v1-bom.csv`、`fab/vibe_lamp_core_v1-cpl.csv`。
- 3D 预览图在 `renders/`。
- 详细布线/DRC 说明见 `../../v1_routing_status.md`。

## 目录内容

| 路径 | 用途 |
|---|---|
| `vibe_lamp_core_v1.kicad_pcb` | PCB 源文件 |
| `vibe_lamp_core_v1.kicad_pro` | KiCad 工程配置 |
| `libs/` | 本工程使用的符号、封装、3D 模型 |
| `scripts/` | 生成/布线/导出辅助脚本 |
| `renders/` | 顶视与等轴测 3D 渲染图 |
| `fab/` | JLCPCB 下单文件 |

## 下单入口

1. 先读 `../../v1_routing_status.md`，确认剩余 DRC 告警的性质。
2. JLCPCB 下单时上传 `fab/vibe_lamp_core_v1-gerber.zip`。
3. 选择 PCBA 后上传 `fab/vibe_lamp_core_v1-bom.csv` 与 `fab/vibe_lamp_core_v1-cpl.csv`。
4. 被动件按阻值/容值在 JLCPCB 页面确认基础库匹配。

## 注意
- 天线 keep-out 是本板第一约束：模组天线端贴板边，该区域两层禁铜/禁走线/禁过孔/禁器件。
- 下单/编辑前留意 KiCad 自动回写 `.kicad_pro` 的问题，详见 `../../v1_routing_status.md`。
