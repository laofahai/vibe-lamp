# vibe_lamp_core_v1 (KiCad)

Core V1 桌面状态灯主控板的 KiCad 工程目录（**当前为空，工程尚未开始画**）。

28×28mm 圆角方板 · 2 层 · 1.0/1.2mm · ESP32-C3-MINI-1（自带 PCB 天线，需天线 keep-out）· USB-C 供电+原生 USB · 板载 3.3V LDO · 中心单颗共阴 RGB LED · WS2812 扩展焊盘（V1 不装）· 工厂贴片，用户不焊接。

## 从哪开始
1. 先读 `../../v1_design_review.md`，把其中 §10 的 8 个定稿问题答完（LDO 型号、RGB LED 料号/脚序、限流阻值、R4/ESD/保险丝是否贴、固件按钮脚、USB-C 脚数、表面处理）。
2. 然后按 `../../v1_kicad_build_guide.md` 一步步在 KiCad GUI 里建工程、录原理图（含完整网表）、指派封装、画 28×28 板框、布局布线（守天线 keep-out）、DRC，最后出 Gerber + BOM + CPL 送 JLCPCB SMT。

## 输入文档（画板依据，勿改）
- `../../v1_spec.md` — 规格
- `../../v1_schematic.md` — 连接表（网表来源）
- `../../v1_bom.csv` — BOM
- `../../v1_pcb_constraints.md` — 生产/布局约束
- `../../v1_design_review.md` — 设计评审（先看）
- `../../v1_kicad_build_guide.md` — 画板手册

## 注意
- 不要手写 `.kicad_sch` / `.kicad_pcb`，全部在 GUI 里做。
- 天线 keep-out 是本板第一约束：模组天线端贴板边，该区域两层禁铜/禁走线/禁过孔/禁器件。
- 另一目录 `../vibe_lamp_edge_v1/` 是 38×16mm 的**另一种形态草稿**，不是本板，仅供风格参考。
