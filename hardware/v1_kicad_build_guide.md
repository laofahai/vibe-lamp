# Vibe Lamp Core V1 — KiCad 画板手册

面向：要在 `hardware/kicad/vibe_lamp_core_v1/`（目前为空目录）里，用 KiCad 8.x GUI 把 Core V1 从零画到可送 JLCPCB SMT 的人。

输入文档：`v1_spec.md`、`v1_schematic.md`、`v1_bom.csv`、`v1_pcb_constraints.md`、`v1_design_review.md`。
**开工前先把 `v1_design_review.md` §10 的 8 个问题答完**（LDO、RGB LED、限流电阻、R4/ESD/保险丝是否贴、固件按钮脚、USB-C 脚数、表面处理）。本手册按"评审建议的默认选择"给出具体料号与 KiCad 名称。

约束复述：28×28mm 圆角方板、2 层、板厚 1.0 或 1.2mm、工厂贴片、用户不焊接。**不要手写 `.kicad_sch`/`.kicad_pcb`，全部在 GUI 里做。**

---

## 0. 建工程

1. KiCad → File → New Project，路径选 `hardware/kicad/vibe_lamp_core_v1/`，工程名 `vibe_lamp_core_v1`。
2. 生成 `vibe_lamp_core_v1.kicad_pro / .kicad_sch / .kicad_pcb`（由 GUI 生成，勿手搓）。
3. 板厂规则（Board Setup，先定后画，省得返工）：
   - 层数 2，铜厚 1oz。
   - 板厚 1.0 或 1.2mm（建议 1.0mm，外壳更薄）。
   - 最小线宽/间距：JLCPCB 标准工艺 **6mil/6mil（0.15mm）** 即可；本板不密，留余量。
   - 最小过孔：0.3mm 孔 / 0.6mm 盘。
   - 与 `vibe_lamp_edge_v1` 草稿保持同一套规则风格（6mil/0.3mm），便于复用习惯。

---

## 1. 元件与封装选型表（开工即用）

下面每行给出：原理图符号库、推荐料号（LCSC/JLCPCB）、KiCad 封装名。**料号请在 JLCPCB 下单页再核对一次库存/编号**（库存会变）。

| 位号 | 器件 | 推荐料号（LCSC） | KiCad 符号 | KiCad 封装 |
|---|---|---|---|---|
| U1 | ESP32-C3-MINI-1-N4 | C3013922（-N4）/ 1U 版 C2934569 | `RF_Module:ESP32-C3-MINI-1` | `RF_Module:ESP32-C3-MINI-1`（若你的 KiCad 版本无此封装，用 Espressif 官方库，见 §2） |
| J1 | USB-C 16P 电源座 | C165948（HRO TYPE-C-31-M-12） | `Connector:USB_C_Receptacle_USB2.0` 或 `Connector_USB:USB_C_Receptacle_USB2.0_16P` | `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12` |
| U2 | 3.3V LDO 600mA | C51118（AP2112K-3.3）/ C82942（ME6211C33） | `Regulator_Linear:AP2112K-3.3`（无则用通用 5 脚 LDO 符号） | `Package_TO_SOT_SMD:SOT-23-5` |
| D1 | 共阴 5050 RGB LED | 选定后用 easyeda2kicad 导入（见 §2） | 自建/导入（共阴，R/G/B 阳极 + 公共阴极） | 跟随所选料号（PLCC-6 5050） |
| D2 | USB ESD（DNP 留位） | C7519（USBLC6-2SC6） | `Power_Protection:USBLC6-2SC6` | `Package_TO_SOT_SMD:SOT-23-6` |
| F1 | VBUS 0Ω/保险丝位 | C17168（0Ω 0603）或自恢复保险丝 | `Device:R`（0Ω）或 `Device:Fuse` | `Resistor_SMD:R_0603_1608Metric` |
| R1/R2/R3 | RGB 限流 330Ω（或按通道调，见评审 R-07） | C23138（330Ω 0603） | `Device:R` | `Resistor_SMD:R_0603_1608Metric` |
| R4 | WS2812 数据 330Ω（V1 可 DNP） | C23138 | `Device:R` | `Resistor_SMD:R_0603_1608Metric` |
| R5 | EN 上拉 10k | C25804（10k 0603） | `Device:R` | `Resistor_SMD:R_0603_1608Metric` |
| R6/R7 | CC 下拉 5.1k | C23186（5.1k 0603） | `Device:R` | `Resistor_SMD:R_0603_1608Metric` |
| C1/C2 | LDO 输入/输出 1µF | C15849（1µF 0603 25V） | `Device:C` | `Capacitor_SMD:C_0603_1608Metric` |
| C3 | 模组储能 10µF | C15850（10µF 0805 25V） | `Device:C` | `Capacitor_SMD:C_0805_2012Metric` |
| C4/C5 | 去耦/EN 100nF | C14663（100nF 0603 50V X7R） | `Device:C` | `Capacitor_SMD:C_0603_1608Metric` |
| C6 | WS2812 储能 470µF（DNP） | C series 电解/钽 6.3V+ | `Device:CP` | 跟随所选料（SMD 电解/钽，留位） |
| SW1 | 清网轻触开关 | C318884（TS-1187A 3×6）或侧按式 | `Switch:SW_Push` | 跟随所选料（见 §2 按钮说明） |
| TP1–TP6 | 测试焊盘 | 无料 | `Connector:TestPoint` | `TestPoint:TestPoint_Pad_1.5x1.5mm` |
| P1 | WS2812 扩展焊盘（DNP） | 无料 | 3×`Connector:TestPoint` 或 3P 排针符号 | 自做 3 个 1.0–1.5mm 焊盘，丝印 `5V DIN GND` |

> 备注：料号末尾的 C 编号是 LCSC 的常备件，绝大多数是 JLCPCB Basic/Extended，能直接走 SMT。下单前在 JLCPCB 元件库搜一遍确认 "SMT Assembly" 可用且有库存。

---

## 2. 三个"非标准库"器件的获取方式（重点）

### 2.1 ESP32-C3-MINI-1（U1）— 封装含天线 keep-out，务必用权威封装
- 优先用 KiCad 8 自带 `RF_Module:ESP32-C3-MINI-1`（符号 + 封装）。
- 若版本里没有该封装，**用 Espressif 官方 KiCad 库**：`github.com/espressif/kicad-libraries`（含 ESP32-C3-MINI-1 符号、封装、3D、以及天线 keep-out 提示）。下载后在 Preferences → Manage Symbol/Footprint Libraries 添加。
- 这一步别用第三方乱搓的封装：天线 keep-out 区域、模组下方散热/接地焊盘的画法直接影响射频和可制造性。

### 2.2 RGB LED（D1）— 用 easyeda2kicad 按所选料号导入
共阴 RGB 5050 各家脚序不同，**必须按选定料号导封装**，不要套通用件：
```
pip install easyeda2kicad
easyeda2kicad --full --lcsc_id=C<你选的RGB料号> --output ./vibe_lamp_core_v1_lcsc
```
会生成 `.kicad_sym / .pretty / .3dshapes`，添加到工程库后指派给 D1。导入后**对照 datasheet 核对哪个脚是公共阴极、哪三个是 R/G/B 阳极**，并据此连原理图网络（公共阴极→GND，R/G/B 阳极→各 330Ω）。
同法可处理 SW1、C6、J1（若想用厂家原始封装而非 KiCad 标准件）。

### 2.3 清网按钮（SW1）
- 默认：竖直按压 SMD 轻触开关（如 TS-1187A，3×6×2.5mm，4 脚），外壳做按键柱顶到它。封装可用其 LCSC 导入件，或 KiCad `Button_Switch_SMD:` 系列里脚距匹配的件。
- 若外壳是侧边针孔：改选侧按式（side-actuated）轻触开关。
- 接法固定：两组脚分别是同一对触点，取一对接 `BTN_RESET`(GPIO10) 与 `GND` 即可；按下导通把 GPIO10 拉到 GND。

---

## 3. 原理图录入（完整网表，照抄即可）

新建/打开 `vibe_lamp_core_v1.kicad_sch`，放置符号并按下表连线。**这是 `v1_schematic.md` 的可执行展开版，含 C3 具体脚号。**

### 3.1 电源树
- `J1` VBUS（A4/B4/A9/B9 全部）→ `F1` → `+5V`
- `J1` GND（A1/B1/A12/B12 全部）+ 外壳 SHELL → `GND`
- `J1` CC1 → `R6`(5.1k) → `GND`
- `J1` CC2 → `R7`(5.1k) → `GND`
- `+5V` → `U2` IN；`U2` OUT → `+3V3`；`U2` GND → `GND`；`U2` EN/CE → `+5V`（AP2112/ME6211 的使能脚拉高常开）
- `C1`(1µF) 跨 IN–GND，靠 U2；`C2`(1µF) 跨 OUT–GND，靠 U2
- 输入端可并 `10µF`（吸收 USB 浪涌；可与 C3 共用一颗或单列）

### 3.2 ESP32-C3-MINI-1（U1）
- `3V3` → `+3V3`
- `GND` 焊盘 + 模组底部 EP/GND → `GND`
- `EN` → `R5`(10k) → `+3V3`；`EN` → `C5`(100nF) → `GND`；`EN` → `TP5`
- `+3V3` 旁去耦：`C3`(10µF) + `C4`(100nF) 跨 3V3–GND，靠模组 3V3 脚
- `IO19`(USB D+) → `USB_DP` → `J1` D+（A6 与 B6 短接）
- `IO18`(USB D-) → `USB_DM` → `J1` D-（A7 与 B7 短接）
- `IO9`(BOOT, strapping) → `TP6`（内部上拉，留作下载短地用，不加外部下拉）
- `IO20`(U0RXD) → `TP3`；`IO21`(U0TXD) → `TP4`
- `IO2 / IO8`（strapping，未用）→ 保持 NC，**不要布下拉/走线**
- `D2`(USBLC6-2SC6, DNP) 跨在 `USB_DP`/`USB_DM`/`+5V`/`GND` 上做 ESD（按手册脚位）

### 3.3 RGB LED（D1，共阴）
- `IO7` → `R1`(330Ω) → `RGB_R`(D1 红阳极)
- `IO6` → `R2`(330Ω) → `RGB_G`(D1 绿阳极)
- `IO5` → `R3`(330Ω) → `RGB_B`(D1 蓝阳极)
- D1 公共阴极 → `GND`
- （若采纳评审 R-07：红用 470–680Ω、蓝绿用 150–220Ω，按定稿值改 R1/R2/R3）

### 3.4 WS2812 预留（V1 默认不装外接灯环）
- `IO4` → `R4`(330Ω) → `WS2812_DIN` → `P1` 的 DIN 焊盘
- `+5V` → `P1` 的 5V 焊盘；`GND` → `P1` 的 GND 焊盘
- `C6`(470µF, DNP) 跨 P1 的 5V–GND，靠 P1
- P1 丝印 `5V DIN GND`；R4/C6/P1 标 DNP（见评审 §5）

### 3.5 清网按钮（SW1）
- `IO10` → `BTN_RESET` → `SW1` 一端；`SW1` 另一端 → `GND`
- 用 C3 内部上拉；可选并 100nF 到 GND 做消抖（非必须）
- 固件侧：确认 `[env:c3_rgb]` 含 `-DPIN_RESET_BTN=10`（评审 R-06）

### 3.6 测试焊盘
- TP1=`+3V3`，TP2=`GND`，TP3=`U0RX(IO20)`，TP4=`U0TX(IO21)`，TP5=`EN`，TP6=`IO9`

录完做 **ERC**（Inspect → Electrical Rules Checker），把所有未连接脚、单端网络清干净（strapping NC 脚加 "no-connect" 标记）。

---

## 4. 封装指派

- Tools → Assign Footprints，按 §1 表逐一指派。
- 标准件直接用 KiCad 内置（电阻电容 0603/0805、SOT-23-5、Type-C HRO、TestPoint）。
- U1 用 Espressif/内置 RF_Module 封装；D1/SW1/C6 用 easyeda2kicad 导入件。
- P1：在封装编辑器里自建一个"3 焊盘 + 丝印 5V/DIN/GND"的封装（焊盘 1.0–1.5mm，间距 2.0–2.54mm），或直接放 3 个 TestPoint。
- 对 R4、C6、D2、P1、TP1–6 设置元件属性 **"Do not populate"**（必要时再勾 "Exclude from position files"），保证 CPL 干净。

---

## 5. 板框（28×28 圆角方）

在 PCB 编辑器 Edge.Cuts 层：
1. 画 28×28mm 方形（建议把板原点设在某角，便于尺寸对齐）。
2. 四角倒圆角，半径建议 **R3–R4mm**（与外壳呼应；可先 R3）。
   - 做法：用圆弧替换四角，或用 KiCad 8 的矩形工具后手改角；保证 Edge.Cuts 是闭合无缝的单轮廓（否则 DRC/制板报错）。
3. 预留外壳定位：若外壳靠卡扣，可不打安装孔；若需要螺丝，**安装孔远离天线端**（见 §7）。本板小，优先无孔卡扣固定。

---

## 6. 布局规划（先摆位再布线）

28×28 内同时满足"LED 居中 + 模组天线贴一边 + USB-C 占一边 + 按钮在边缘 + 天线 keep-out"，空间偏紧，按下图思路摆：

```
        上边缘 = 模组天线端（天线指向板外，keep-out 压在这条边）
   ┌──────────────[ 天线 keep-out 区，禁铜/禁走线 ]──────────────┐
   │   ███████  ESP32-C3-MINI-1 模组（天线端朝上贴边） ███████    │
   │                                                              │
左 │            ○ R1 R2 R3 靠近 D1/模组                           │ 右
边 │                     ┌───────────┐                            │ 边
   │   U2 LDO            │  D1 RGB   │   ← 正中心，扩散罩对准      │
   │   C1 C2 C3 C4 C5    │  (居中)   │                            │
   │                     └───────────┘        R4/P1/C6(DNP)→边角  │
   │   TP1..TP6 排一排（背面或边角）                              │
   └───────[ USB-C J1 居中靠下边缘 ]────────[ SW1 靠边缘 ]────────┘
        下边缘 = USB-C 插拔口          侧/角 = 清网按钮
```

要点：
- **D1 RGB 放几何正中心**（spec 强制），三路限流电阻 R1/R2/R3 就近放（靠 D1 或靠模组皆可）。
- **模组天线端贴“天线边”**（与 USB-C 的边相对，避免 USB 外壳金属靠近天线）。模组放正面上方或背面均可，但天线端必须贴板边且其 keep-out 不被任何金属遮挡。
- **USB-C 居中靠一条边**，外壳在该边开口；CC 电阻 R6/R7、ESD D2 就近 USB。
- **SW1 在边缘/角**（避免误触，外壳可针孔或按键柱）。
- LDO + 输入输出电容 C1/C2 三者紧贴；模组去耦 C3/C4 紧贴模组 3V3 脚。
- TP/扩展焊盘放背面或边角非视觉区。
- 摆完先目测：模组 + LED + USB 三大件能否共存于 28×28，若挤，模组移背面、TP/P1 移背面。

---

## 7. 天线 keep-out（本板头号规则，单独强调）

ESP32-C3-MINI-1 **自带 PCB 天线 + 射频匹配，无需任何外置天线器件**。必须：
- 模组天线端**与板边对齐**（天线朝板外）。
- 在天线正下方/正前方建立 **keep-out（Rule Area / Keepout Zone）**，覆盖范围参照 Espressif ESP32-C3-MINI-1 datasheet 的天线净空尺寸（典型为模组天线那一段向板内延伸的一块区域 + 到板边）。
- keep-out 内：**所有层禁止铺铜、禁止走线、禁止过孔、禁止焊盘/器件**；GND 灌铜也要在此区域开窗（不要把地铺进去）。
- KiCad 操作：Place → Add Rule Area，勾选 "Keep out tracks / vias / pads / copper pour / footprints"，应用到 F.Cu + B.Cu（两层都要）。把这块区域画在天线投影 + 板边那一带。
- 机械：安装孔/螺丝/金属件远离天线端；外壳此处不要有金属或大面积导电涂层。
- （备选记录）若日后必须外置天线 → 换 **ESP32-C3-MINI-1U**（带 U.FL/IPEX），属换料改封装，不在 V1。

---

## 8. 布线与铺铜规则

1. **先布关键网络**：
   - USB D+/D-（`USB_DP`/`USB_DM`）走差分：短、并行、尽量等长、少过孔、避免绕远（C3 是全速 USB，难度不高但别乱走）。
   - VBUS/`+5V`/`GND` 主电源加宽（建议 ≥0.4–0.5mm；将来真接 WS2812 灯环要更宽，但 V1 单灯电流小）。
2. **去耦就近**：C3/C4 到模组 3V3 的走线尽量短粗；C1/C2 紧贴 LDO。
3. **铺铜**：双面 GND 灌铜 + 适当过孔缝合（stitching），改善回流和散热。
   - **唯一例外：天线 keep-out 区严禁灌铜**（见 §7）。灌铜后检查该区域确实开窗。
4. **CC/信号**：R6/R7 就近 USB-C 的 CC 脚；RGB 三路信号短走即可。
5. 丝印：D1 标公共脚方向（防贴反）、P1 标 `5V DIN GND`、各 TP 标名称、加板名/版本/极性标识。

---

## 9. DRC

- Inspect → Design Rules Checker，清零 error。
- 重点确认：
  - Edge.Cuts 闭合、圆角无缝。
  - 天线 keep-out 区内无铜/无走线/无过孔（DRC + 目视双确认）。
  - 所有过孔/线宽满足 JLCPCB 工艺（6mil/0.3mm）。
  - 未连接网络为 0；DNP 件不影响连通性（DNP 但焊盘网络仍应正确）。
- 跑一次 3D View 目视：模组天线端贴边、USB-C 朝外、LED 居中、无器件压到板框/keep-out。

---

## 10. 出厂文件导出（JLCPCB SMT）

### 10.1 Gerber + 钻孔
- File → Plot：
  - 层：F.Cu, B.Cu, F.Paste, B.Paste, F.SilkS, B.SilkS, F.Mask, B.Mask, Edge.Cuts。
  - 选项：Plot footprint values/refs 按需；用 Protel 扩展名或保持 KiCad 默认（JLCPCB 都认 KiCad zip）。
- Generate Drill Files：PTH/NPTH 合并或分开均可，单位与 Gerber 一致。
- 把上述文件打成一个 zip，JLCPCB 上传即可识别层。

### 10.2 BOM（给 SMT）
- Tools → Generate BOM（或用 JLCPCB 的 KiCad 插件 "Fabrication Toolkit" / `JLC-Plugin-for-KiCad`，最省事）。
- BOM 至少含：Comment(值)、Designator(位号)、Footprint、**LCSC Part #**（关键，SMT 靠它取料）。
- **DNP 件（R4 视决定 / C6 / D2 / P1 / TP1–6）从贴片 BOM 中排除或标 DNP**，与评审 §5 一致。

### 10.3 CPL / 坐标（pick-and-place）
- File → Fabrication Outputs → Component Placement (.pos)，或用上面插件一键出 CPL。
- 坐标必须含 Designator / Mid X / Mid Y / Rotation / Layer。
- **DNP/测试焊盘不要出现在 CPL**（否则贴片会去贴空位/报错）。
- 出件后核对旋转角：U1、J1、D1、U2 是贴片最易贴反的件，必要时按 JLCPCB 预览图调 rotation。

### 10.4 装配图 / 其他
- 导出装配图（assembly drawing，含位号 + 极性）随包交付。
- 一并交付：本工程文件、Gerber、Drill、BOM、CPL、装配图，以及 `v1_*.md` 设计说明（`v1_pcb_constraints.md` §交付清单要求）。

---

## 11. 收尾自查清单

- [ ] 评审 §10 八问全部已定稿（尤其 LDO、RGB LED 料号、限流阻值、固件按钮脚）
- [ ] ERC / DRC 全绿
- [ ] 天线 keep-out 两层均无铜/线/孔/件
- [ ] USB D+/D- 差分短而直；VBUS/GND 加宽
- [ ] DNP 件未进 CPL；BOM 带 LCSC 料号
- [ ] 3D 目视：天线贴边、LED 居中、USB 朝外、按钮在边缘
- [ ] 固件 `[env:c3_rgb]` 已加 `-DPIN_RESET_BTN=10`
- [ ] 板名/版本/极性丝印齐全

> 本手册是画板流程指引，不替代器件 datasheet。料号/封装以选定料的官方资料为准；LCSC 编号下单前再核对库存。
