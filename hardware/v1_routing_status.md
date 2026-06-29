# Vibe Lamp Core V1 布线状态

> 工程：`hardware/kicad/vibe_lamp_core_v1/vibe_lamp_core_v1.kicad_pcb`（KiCad 10）
> 流程：pcbnew 脚本摆件+连网 → Freerouting v1.9.0 自动布线 → 导回 SES → CC2 手补 → 双面 GND 铺铜 → JLCPCB 工艺规则 DRC。
> 板框：40×40 mm，2 层。

## 现状：电气完整,可打样（草稿待定 D1 选型）

| 指标 | 旧 | 当前 |
|---|---|---|
| 短路 | 0 | **0** ✅ |
| 未连接 | 1 (CC2) | **0** ✅ |
| DRC 违规 | 24 | **20**（全次要,见下） |

本轮改动：
- **CC2 已布通**：把 R7（CC2 下拉）移到 J1.B5 正北空走廊,CC2 成一条 1.41mm 直线手补,0 短路。
- **J1 上移 1.2mm**：USB-C 焊盘全部进板内,外壳仍 overhang 可插线（修掉焊盘出板边）。
- **USB-C 扇出口袋扩到 ~3.8mm**：底排被动件上移,给连接器扇出留道。
- **品牌丝印 "vibe lamp"**：正面（F.SilkS, LED 上方）+ 背面大字（B.SilkS）+ 背面 "v1"。
- **设计规则设为 JLCPCB 工艺**：铜到板边 0.5→0.2mm、默认间距 0.2→0.127mm。

## 剩余 20 项 DRC（全部非阻断）

| 类型 | 数量 | 性质 |
|---|---|---|
| hole_clearance / annular_width / clearance / padstack | 10 | **USB-C 连接器（立创 C165948）固有密脚间距/PTH**,立创自家封装,他们能稳定制造 |
| silk_edge_clearance | 5 | U1/J1 封装丝印超出板边（贴边器件天经地义,超出部分不印）——cosmetic |
| silk_overlap / silk_over_copper | 3 | C6 位号丝印与邻件/铺铜重叠——cosmetic（与品牌丝印无关,后者干净） |
| courtyards_overlap | 1 | TP5 与 SW1 课程框略近 |
| starved_thermal | 1 | D2 一个 GND 热焊盘连接偏细 |

> 这些是**对 KiCad 通用规则的告警**,不是真缺陷；连接器固有项 + cosmetic 丝印,JLCPCB 上传时会按自家工艺二次检查。可在 KiCad 里逐条 “Exclude” 标记确认。

## WiFi 天线

ESP32-C3-MINI-1 **自带 PCB 天线 + 射频匹配,无需单独天线元件**。模组置顶,天线端朝板顶边；顶边 keep-out 规则区（y0.3–2.8mm,无铜/无走线/无过孔）已在位。

## 打板厂要的文件（已重新导出在 `fab/`）

| 文件 | 用途 |
|---|---|
| `vibe_lamp_core_v1-gerber.zip` | Gerber 10 层（双面铜/阻焊/丝印 + 板框 + 钢网 + Excellon 钻孔）→ 上传 JLCPCB |
| `vibe_lamp_core_v1-bom.csv` | 物料表（JLCPCB 原生格式 Comment/Designator/Footprint/LCSC#）|
| `vibe_lamp_core_v1-cpl.csv` | 贴片坐标 |

> 流程：JLCPCB 下单 → 上传 gerber.zip → 选 PCBA → 传 bom.csv + cpl.csv。

### ⚠️ 下单前的 BOM 收尾（实查立创库后的结论）

已填确切立创料号：**U1=C2934569**(ESP32-C3-MINI-1)、**U2=C51118**(AP2112K-3.3)、**J1=C165948**(USB-C)、**D2=C7519**(USBLC6-2SC6)。

仍待定 / 需你确认：
- **D1（RGB 灯）——需选型决策**。当前封装是 `LED_RGB_5050-6`（6 脚 5050）。实查 JLCPCB 库：模拟 5050 现货几乎都是 **8 脚 RGBW**（如 C440461）或**带 IC 的数字灯**（WS2812/SK6812 类,如 C5380879）；**6 脚纯模拟共阴 5050 没有现成高库存料**。三选一：
  1. 改用 6 脚小封装共阴 RGB（如 SMD-6P 1.6×1.5 的 C375568）→ 需换 D1 封装 + 局部重布；
  2. 改用 WS2812B/SK6812 数字灯（单线驱动,固件改成走 WS2812 协议,板上 R1/R2/R3 限流电阻取消）→ 元件少、立创现货足,但要改固件;
  3. 维持 6 脚 5050,自行采购模拟共阴 5050 手焊 / 找贴片厂代采。
  （反例：C482558 虽是共阴 RGB,但实为 SMD-4P 3×1.5,**与 6 脚封装对不上**,别选。）
- **SW1（按键）**：封装 `Panasonic_EVQPUJ_EVQPUA`。在 JLCPCB 选 4 脚贴片轻触开关并**确认 land pattern 对得上**（候选 C10852 4×4×1.7 SMD-4P,库存偏低需复核）。
- **被动件 R/C/0Ω**：BOM 留空即可,**JLCPCB 下单界面会按“值+封装”自动匹配基础库**,你点确认；无需预填 C 号（自己猜反而易错）。

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
"$KPY" scripts/set_values.py $PCB                 # 写回元件值(470/150/1uF…)
# .kicad_pro: min_copper_edge_clearance=0.2, Default class clearance=0.127
"$KCLI" pcb drc --refill-zones --severity-all $PCB
"$KCLI" pcb export gerbers -o fab/ $PCB
"$KCLI" pcb export drill --format excellon --excellon-units mm -o fab/ $PCB
"$KCLI" pcb export pos --format csv --units mm --side both -o fab/$PCB-cpl.csv $PCB
"$KPY" scripts/gen_bom.py $PCB fab/$PCB-bom.csv
```
