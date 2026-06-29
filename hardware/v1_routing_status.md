# Vibe Lamp Core V1 布线状态

> 工程：`hardware/kicad/vibe_lamp_core_v1/vibe_lamp_core_v1.kicad_pcb`（KiCad 10）
> 流程：pcbnew 脚本摆件+连网 → Freerouting v1.9.0 自动布线 → 导回 SES → CC2 手补 → 双面 GND 铺铜 → JLCPCB 工艺规则 DRC。
> 板框：40×40 mm，2 层。

## 现状：✅ 电气完整、BOM 齐料、可下单 PCBA

| 指标 | 结果 |
|---|---|
| 短路 | **0** ✅ |
| 未连接 | **0** ✅ |
| DRC 违规 | **18**（全部非阻断:10 个 USB-C 连接器固有 + 8 个 cosmetic 丝印） |
| BOM 关键料号 | **6/6 已填**(U1/U2/J1/D2/D1/SW1),被动件 JLCPCB 自动匹配 |

## 关键设计决策：D1 改用 WS2812B 数字灯

实查立创库后定的最优解(详见 git 历史):
- **6 脚 5050 模拟共阴 RGB 立创无现成高库存料**(模拟 5050 基本是 8 脚 RGBW 或带 IC 数字灯)。
- 改用 **WS2812B(C2761795,库存 55 万)**:单线驱动、去掉 R1/R2/R3 三个限流电阻、立创现货充足、24 位色、颜色一致。
- 数据链:`GPIO4 → R4(330Ω) → D1.DIN`;`D1.DOUT → P1`(板载 D1 是链首,P1 可级联外部灯带)。
- 新增 **C7 100nF** 给 D1 就近去耦。
- SW1 清网键改用 **SKRPABE010(C115360,库存 1.8万)**——Panasonic SMD 轻触开关现货,封装实测对得上。
- 配套固件:**新增 env `c3_core_v1`**(WS2812 单灯,GPIO4,NUM_LEDS=1)。**不影响现有 SuperMini 模拟板(env `c3_rgb`)**。

## 本轮其它改动

- **CC2 已布通**：R7 移到 J1.B5 正北空走廊,CC2 走一条 1.41mm 直线(`scripts/route_cc2.py`),0 短路。
- **J1 上移 1.2mm**:USB-C 焊盘全进板内,外壳仍 overhang 可插线。
- **品牌丝印 "vibe lamp"**:正面 + 背面大字 + 背面 "v1"。
- **设计规则 = JLCPCB 工艺**:铜到板边 0.2mm、默认间距 0.127mm、最少热焊盘臂 1。

## 剩余 18 项 DRC（全部非阻断）

| 类型 | 数量 | 性质 |
|---|---|---|
| hole_clearance / annular_width / clearance / padstack | 10 | **USB-C 连接器(立创 C165948)固有密脚/PTH**,立创自家封装,稳定可造 |
| silk_edge_clearance | 5 | U1/J1 封装丝印超出板边(贴边器件,超出部分不印)——cosmetic |
| silk_overlap / silk_over_copper | 3 | C6 位号丝印与邻件/铺铜重叠——cosmetic |

> 均为对 KiCad 通用规则的告警,**无真实设计缺陷**;JLCPCB 上传时会按自家工艺二次检查。可在 KiCad 逐条 Exclude 确认。

## WiFi 天线

ESP32-C3-MINI-1 **自带 PCB 天线 + 射频匹配,无需单独天线元件**。模组置顶、天线端朝板顶边;顶边 keep-out 规则区(y0.3–2.8mm,无铜/无走线/无过孔)在位。

## ⚠️ 注意:下单/编辑前请关闭 KiCad

KiCad 开着此工程时会**自动回写 `.kicad_pro`**,把设计规则还原成默认(铜到板边 0.5、间距 0.2),导致 DRC 假阳性变多。下单前如需重跑 DRC,请先关 KiCad,或确认 `.kicad_pro` 里 `min_copper_edge_clearance=0.2 / clearance=0.127 / min_resolved_spokes=1`。

## 打板厂要的文件（已生成在 `fab/`）

| 文件 | 用途 |
|---|---|
| `vibe_lamp_core_v1-gerber.zip` | Gerber 10 层(双面铜/阻焊/丝印 + 板框 + 钢网 + Excellon 钻孔)→ 上传 JLCPCB |
| `vibe_lamp_core_v1-bom.csv` | 物料表(JLCPCB 原生格式,6 个关键料号已填) |
| `vibe_lamp_core_v1-cpl.csv` | 贴片坐标 |

> 流程:JLCPCB 下单 → 上传 gerber.zip → 选 PCBA → 传 bom.csv + cpl.csv → 被动件(R/C/0Ω)在界面按值确认基础库即可。

## 复现命令

```bash
KPY="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KCLI="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PCB=vibe_lamp_core_v1.kicad_pcb
"$KPY" scripts/gen_pcb.py                         # 摆件+连网+天线keepout+品牌丝印
"$KPY" scripts/export_dsn.py $PCB core.dsn
java -jar ~/Downloads/freerouting-1.9.0.jar -de core.dsn -do core.ses -mp 100   # 可无人值守批处理
"$KPY" scripts/import_ses.py $PCB core.ses
"$KPY" scripts/route_cc2.py $PCB                  # 手补 CC2 直线(B5→R7.1)
"$KPY" scripts/gnd_pour.py $PCB
"$KPY" scripts/set_values.py $PCB                 # 写回元件值
# .kicad_pro: min_copper_edge_clearance=0.2, Default clearance=0.127, min_resolved_spokes=1
"$KCLI" pcb drc --refill-zones --severity-all $PCB
"$KCLI" pcb export gerbers -o fab/ $PCB
"$KCLI" pcb export drill --format excellon --excellon-units mm -o fab/ $PCB
"$KCLI" pcb export pos --format csv --units mm --side both -o fab/$PCB-cpl.csv $PCB
"$KPY" scripts/gen_bom.py $PCB fab/$PCB-bom.csv
```
