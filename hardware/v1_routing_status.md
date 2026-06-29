# Vibe Lamp Core V1 布线状态（自动布线草稿）

> 工程文件：`hardware/kicad/vibe_lamp_core_v1/vibe_lamp_core_v1.kicad_pcb`
> 生成方式：pcbnew 脚本摆件+连网 → Freerouting v1.9.0 自动布线 → 导回 SES → 双面 GND 铺铜。

## 现状：**草稿，未达可打样**

自动布线把约 75% 连接走通（86 条网络连接中 64 条已布），但仍有需**人工在 KiCad 里清理**的问题。这正是“画好能打开的板”与“可下单打样的板”之间的最后一段，必须有人在 PCB 编辑器里收尾。

## 待清理的 DRC 问题（来自 kicad-cli DRC）

| 类型 | 数量 | 说明 / 处理 |
|---|---|---|
| 未布通连接 (unconnected) | 21 | Freerouting 双层没布满，剩余手工补线或重布 |
| 短路 (shorting_items) | 4 | **必须修**：不同网络铜重叠 |
| 天线 keepout 穿越 (items_not_allowed) | 17 | 走线/铜进入了模组天线禁区，需挪线/挖空铺铜 |
| 元件外形重叠 (courtyards_overlap) | 9 | 摆放偏挤，需拉开间距 |
| 间距/孔/边距 (clearance/hole/edge) | ~14 | 调线宽间距、远离板边 |
| 阻焊桥 (solder_mask_bridge) | 5 | 细间距阻焊，调规则或挪线 |
| 丝印压铜/重叠 (silk_*) | ~26 | 纯外观，打样前隐藏/挪动位号即可 |

## 已经做对的部分（可直接复用）

- 真实封装（ESP32-C3-MINI-1 / USB-C TYPE-C-31-M-12 / AP2112K / USBLC6 均来自立创，封装与库存对得上）。
- 22 个网络的连接关系（netlist）正确，已验证零映射告警。
- 天线 keepout 规则区已建（在顶边）。
- 双面 GND 铺铜已加。

## 收尾两条路（择一）

1. **交 PCB 布线服务 / 会 KiCad 的人**：从这版 75% 已布的草稿继续，修短路、补 21 条、清 keepout、拉开重叠，跑通 DRC 后导 Gerber。对“不会 KiCad”的人这是最稳的。
2. **继续自动布线迭代**：先把摆放拉开（消除 courtyard 重叠）+ 让布线器尊重 keepout + 加大 pass 数重布；可能多轮，且短路仍可能要手工修。

## 复现命令（本机）

```bash
KPY="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
KCLI="/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
# 摆件+连网：scratchpad/gen_pcb.py    导出 DSN：export_dsn.py    导回 SES：import_ses.py    GND 铺铜：gnd_pour.py
java -jar ~/Downloads/freerouting-1.9.0.jar -de core.dsn -do core.ses -mp 20   # 需图形会话，非 headless
"$KCLI" pcb drc vibe_lamp_core_v1.kicad_pcb
```
