#!/usr/bin/env python3
# 生成 Vibe Lamp Core V1 的 KiCad PCB（摆件 + 板框 + 天线 keepout）。
# 第一版目标：所有真封装载入成功、能在 KiCad 10 打开。net 第二版再加。
import os, sys
import pcbnew

ROOT = "/Users/laofahai/Documents/workspace/vibe-lamp"
PROJ = os.path.join(ROOT, "hardware/kicad/vibe_lamp_core_v1")
EZ_LIB = os.path.join(PROJ, "libs/vibe_lamp.pretty")
STOCK = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"

def mm(v): return pcbnew.FromMM(v)

board = pcbnew.CreateEmptyBoard()

# 板框 40x40（放大留布线/间距余量；直角，圆角作后续工艺细节）
W = 40.0; H = 40.0
def add_edge(x1,y1,x2,y2):
    seg = pcbnew.PCB_SHAPE(board)
    seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
    seg.SetStart(pcbnew.VECTOR2I(mm(x1), mm(y1)))
    seg.SetEnd(pcbnew.VECTOR2I(mm(x2), mm(y2)))
    seg.SetLayer(pcbnew.Edge_Cuts)
    seg.SetWidth(mm(0.15))
    board.Add(seg)
add_edge(0,0,W,0); add_edge(W,0,W,H); add_edge(W,H,0,H); add_edge(0,H,0,0)

# 元件表：refdes -> (lib_path, fp_name, x, y, rot, back?)
LED = STOCK + "/LED_SMD.pretty"
RES = STOCK + "/Resistor_SMD.pretty"
CAP = STOCK + "/Capacitor_SMD.pretty"
BTN = STOCK + "/Button_Switch_SMD.pretty"
TP  = STOCK + "/TestPoint.pretty"
HDR = STOCK + "/Connector_PinHeader_2.54mm.pretty"

# 摆放原则：U1 模组占中上(x7.7..24.3,y2.4..15.6),天线朝上;其余件全部放在
# 模组外的左条/右条/下半区,互不重叠。坐标 mm，y 向下。
# 40x40 宽松布局：模组占顶部(天线朝上),LED 居中偏下,其余件按真实尺寸拉开,
# 每个件中心间距≥3mm(0603/0805)或更大(SOT/LED/USB),保证外形不重叠。
COMPS = [
    ("U1", EZ_LIB, "WIFIM-SMD_ESP32-C3-MINI-1", 20, 9.5, 0, False),   # 顶部,天线朝上
    ("D1", EZ_LIB, "LED-SMD_4P-L5.0-W5.0-TL_WS2812B-B", 20, 24, 0, False),  # 居中:WS2812B 数字灯(C2761795)
    ("J1", EZ_LIB, "USB-C_SMD-TYPE-C-31-M-12_1",20, 36.3,0, False),   # 底边(上移1.2:焊盘进板,外壳仍overhang可插线)
    ("U2", EZ_LIB, "SOT-25-5_L2.9-W1.6-P0.95-LS2.8-BL", 6, 23, 90, False),  # 左中 LDO
    ("D2", EZ_LIB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", 31, 30, 0, False),  # USB ESD(上移,靠USB)
    # 模组下方一排:去耦 + EN(间距 3.5mm)
    ("C3", CAP, "C_0805_2012Metric", 12.5, 18, 0, False),
    ("C4", CAP, "C_0603_1608Metric", 16,   18, 0, False),
    ("R5", RES, "R_0603_1608Metric", 24,   18, 0, False),
    ("C5", CAP, "C_0603_1608Metric", 27.5, 18, 0, False),
    # WS2812B 改造:删 R1/R2/R3(数字灯无需 RGB 限流)。R4 保留作数据串联电阻。
    ("R4", RES, "R_0603_1608Metric", 26,  26,   90, False),   # IO4→R4→D1.DIN 数据串联
    ("C7", CAP, "C_0603_1608Metric", 14,  24,   90, False),   # D1 电源去耦 100nF(接 LED5V)
    ("D3", EZ_LIB, "SOD-323_L1.8-W1.3-LS2.5-RD", 17, 20, 0, False),  # 1N4148WS:5V→压降~0.7V给WS2812,使3.3V数据电平达标
    # 左下:LDO 输入输出电容
    ("C1", CAP, "C_0603_1608Metric", 6, 27, 90, False),
    ("C2", CAP, "C_0603_1608Metric", 6, 30, 90, False),
    # USB 区:上移到 y30,给 USB-C 扇出腾出 ~3.8mm 走线口袋(原 1.5mm 太挤,CC2 布不通)
    ("F1", RES, "R_0603_1608Metric", 10, 30, 0, False),
    ("R6", RES, "R_0603_1608Metric", 13, 30, 0, False),   # CC1 下拉
    ("R7", RES, "R_0603_1608Metric", 21.75, 31.6, 90, False),   # CC2 下拉:放 B5 正北空走廊,CC2=1.5mm直线必通
    # 右条:按键/排针/灯带扩展
    ("SW1", EZ_LIB, "KEY-SMD_4P-L4.2-W3.2-P2.20-LS4.6", 35, 10, 0, False),  # 清网键 SKRPABE010(C115360)
    ("P1", HDR, "PinHeader_1x03_P2.54mm_Vertical", 35.5, 24, 0, False),
    ("C6", CAP, "C_0805_2012Metric", 31, 25, 90, False),
    # 测试焊盘:左列 4 个;右列 2 个拉开(TP6=IO9 远离 SW1=BTN，避免并行短路)
    ("TP1", TP, "TestPoint_Pad_D1.0mm", 3, 8,  0, False),
    ("TP2", TP, "TestPoint_Pad_D1.0mm", 3, 12, 0, False),
    ("TP3", TP, "TestPoint_Pad_D1.0mm", 3, 16, 0, False),
    ("TP4", TP, "TestPoint_Pad_D1.0mm", 3, 20, 0, False),
    ("TP5", TP, "TestPoint_Pad_D1.0mm", 38, 6, 0, False),
    ("TP6", TP, "TestPoint_Pad_D1.0mm", 38, 18, 0, False),
]

pad_report = {}
for ref, lib, name, x, y, rot, back in COMPS:
    modpath = os.path.join(lib, name + ".kicad_mod")
    if not os.path.isfile(modpath):
        print(f"!! MISSING FILE {ref}: {modpath}"); sys.stdout.flush(); continue
    print(f"loading {ref} {name} ...", flush=True)
    fp = pcbnew.FootprintLoad(lib, name)
    if fp is None:
        print(f"!! LOAD FAIL {ref}: {lib} :: {name}", flush=True); continue
    fp.SetReference(ref)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    if rot: fp.SetOrientationDegrees(rot)
    board.Add(fp)
    try: fp.Value().SetVisible(False)   # 关掉糊成一团的说明文字
    except Exception: pass
    pad_report[ref] = [p.GetName() for p in fp.Pads()]
    print(f"  {ref} ok ({len(pad_report[ref])} pads)", flush=True)

# ---- 网络连接 ----
fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
def add_to_net(net, ref, padname):
    f = fps.get(ref)
    if not f: print("  net? no comp", ref); return
    hit = False
    for p in f.Pads():
        if p.GetName() == padname:
            p.SetNet(net); hit = True
    if not hit: print(f"  net? {ref} 无 pad '{padname}'")

NETS = {
 "VBUS":    [("J1","A4B9"),("J1","B4A9"),("F1","1"),("D2","5")],
 "+5V":     [("F1","2"),("U2","1"),("U2","3"),("C1","1"),("C6","1"),("P1","1"),("D3","2")],
 "LED5V":   [("D3","1"),("D1","1"),("C7","1")],   # 二极管压降后的 WS2812 供电(~4.3V)
 "+3V3":    [("U2","5"),("C2","1"),("C3","1"),("C4","1"),("U1","3"),("R5","1"),("TP1","1")],
 "EN":      [("U1","8"),("R5","2"),("C5","1"),("TP5","1")],
 "USB_DP":  [("U1","27"),("J1","A6"),("J1","B6"),("D2","1")],
 "USB_DM":  [("U1","26"),("J1","A7"),("J1","B7"),("D2","3")],
 "CC1":     [("J1","A5"),("R6","1")],
 "CC2":     [("J1","B5"),("R7","1")],
 "IO4":     [("U1","18"),("R4","1")],
 "WS_DIN":  [("R4","2"),("D1","4")],          # 数据进 D1(DIN=脚4)
 "WS_DOUT": [("D1","2"),("P1","2")],          # D1 输出(DOUT=脚2)→ P1 外接灯带链
 "BTN":     [("U1","16"),("SW1","1"),("SW1","3")],   # 左侧两脚一端子
 "UART_RX": [("U1","30"),("TP3","1")],
 "UART_TX": [("U1","31"),("TP4","1")],
 "IO9":     [("U1","23"),("TP6","1")],
}
GND = [("J1","A1B12"),("J1","B1A12"),("J1","1"),("J1","2"),("J1","3"),("J1","4"),
       ("U2","2"),("D2","2"),("SW1","2"),("SW1","4"),("P1","3"),("R6","2"),("R7","2"),
       ("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),("C7","2"),
       ("TP2","1"),("D1","3")]
GND += [("U1",p) for p in (["1","2","11","14"]+[str(i) for i in range(36,54)])]
NETS["GND"] = GND

for name, conns in NETS.items():
    n = pcbnew.NETINFO_ITEM(board, name)
    board.Add(n)
    for ref, padname in conns:
        add_to_net(n, ref, padname)

# ---- 天线 keepout：顶边 5mm 不铺铜/不走线/不打孔（U1 天线端朝上）----
try:
    z = pcbnew.ZONE(board)
    z.SetIsRuleArea(True)
    z.SetDoNotAllowZoneFills(True); z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True)
    ls = pcbnew.LSET(); ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.B_Cu)
    z.SetLayerSet(ls)
    pts = [(6,0.3),(34,0.3),(34,2.8),(6,2.8)]
    poly = z.Outline()
    poly.NewOutline()
    for px,py in pts: poly.Append(mm(px), mm(py))
    board.Add(z)
    print("keepout ok")
except Exception as e:
    print("keepout skip:", e)

# ---- 品牌丝印 "vibe lamp" ----
def add_silk(text, x, y, size, layer, mirror=False, thick=0.15):
    try:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetLayer(layer)
        t.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(thick))
        try: t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        except Exception: pass
        if mirror:
            try: t.SetMirrored(True)
            except Exception: pass
        board.Add(t)
        print(f"silk '{text}' @({x},{y}) layer={layer}", flush=True)
    except Exception as e:
        print("silk skip:", e, flush=True)
add_silk("vibe lamp", 20, 28.6, 1.1, pcbnew.F_SilkS)               # 正面小标(LED 与底排之间空区)
add_silk("vibe lamp", 20, 20.0, 1.8, pcbnew.B_SilkS, mirror=True)  # 背面主标(背面空,大字)
add_silk("v1",        20, 23.0, 1.0, pcbnew.B_SilkS, mirror=True)  # 背面版本号

board.BuildListOfNets()
board.BuildConnectivity()
out = os.path.join(PROJ, "vibe_lamp_core_v1.kicad_pcb")
pcbnew.SaveBoard(out, board)
print("SAVED:", out, "nets=", board.GetNetCount())
