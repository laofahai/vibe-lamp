# Vibe Lamp Core V1 布线状态

> 工程：`hardware/kicad/vibe_lamp_core_v1/vibe_lamp_core_v1.kicad_pcb`（KiCad 10）
> 流程：pcbnew 脚本摆件+连网 → Freerouting v1.9.0 自动布线(100 pass) → 导回 SES → 双面 GND 铺铜。
> 板框：40×40 mm（尺寸可调），2 层。

## 现状：接近可打样，仅余少量收尾

| 指标 | 初版 | 当前 |
|---|---|---|
| DRC 违规 | 86 | **23** |
| 未连接 | 21 | **1** |
| 短路 | 4 | **0** ✅ |
| 元件外形重叠 | 9 | **1** |

布局规整(模组居顶天线朝上、LED 居中、USB-C 居底、测试点成列)、走线干净、GND 铺铜到位、无短路。

## 剩余 23 项（多为次要/可调，非阻断）

| 类型 | 数量 | 性质 / 处理 |
|---|---|---|
| clearance（间距 0.10–0.18mm） | 6 | freerouting 局部挤窄；放宽规则到 JLCPCB 0.127mm 可清大部分，个别需手工挪线 |
| starved_thermal（GND 热焊盘细） | 5 | 铺铜热连接偏细；调热焊盘参数或可接受 |
| silk_edge / padstack / annular / hole / copper_edge | 各 2–3 | 丝印/过孔环宽/孔距/铜距板边；规则微调或挪动 |
| unconnected | 1 | 1 条 freerouting 未布通，手工补一段即可 |
| courtyard_overlap | 1 | 一对元件略近 |

## 已做对、可直接用

- 真实封装均来自立创（ESP32-C3-MINI-1 / USB-C TYPE-C-31-M-12 / AP2112K-3.3 / USBLC6），对得上 JLCPCB 库存。
- 22 个网络连接关系正确（零映射告警），自动布线 ~99% 完成、零短路。
- 天线 keepout 规则区在顶边；双面 GND 铺铜。

## 到可打样还差（一次性收尾）

1. 放宽间距规则到 JLCPCB 工艺（0.127mm）清掉边缘性 clearance；
2. 手工补 1 条未连、微调 5 处热焊盘、挪开 1 对近距元件；
3. DRC 归零后 `kicad-cli pcb export gerbers / drill`，导 BOM+CPL 下单。

## 复现命令

```bash
KPY="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KCLI="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
"$KPY" scripts/gen_pcb.py          # 摆件+连网+keepout
"$KPY" scripts/export_dsn.py <pcb> core.dsn
java -jar ~/Downloads/freerouting-1.9.0.jar -de core.dsn -do core.ses -mp 100   # 需图形会话
"$KPY" scripts/import_ses.py <pcb> core.ses
"$KPY" scripts/gnd_pour.py <pcb>
"$KCLI" pcb drc <pcb>
```
