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

# 板框 32x32（直角；圆角作为后续表贴工艺细节）
W = 32.0; H = 32.0
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
COMPS = [
    ("U1", EZ_LIB, "WIFIM-SMD_ESP32-C3-MINI-1", 16, 9,   0, False),
    ("D1", LED,    "LED_RGB_5050-6",            16, 20,  0, False),
    ("J1", EZ_LIB, "USB-C_SMD-TYPE-C-31-M-12_1",16, 30.3,0, False),
    ("U2", EZ_LIB, "SOT-25-5_L2.9-W1.6-P0.95-LS2.8-BL", 5, 20, 90, False),
    ("D2", EZ_LIB, "SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL", 27, 26, 0, False),
    # RGB 限流电阻：在 LED 两侧/下方，离 LED 外形足够远
    ("R1", RES, "R_0603_1608Metric", 9.5, 19, 90, False),
    ("R2", RES, "R_0603_1608Metric", 22.5,19, 90, False),
    ("R3", RES, "R_0603_1608Metric", 9.5, 23, 90, False),
    ("R4", RES, "R_0603_1608Metric", 22.5,23, 90, False),
    # 模组下方一排去耦/EN
    ("C3", CAP, "C_0805_2012Metric", 12, 17, 0, False),
    ("C4", CAP, "C_0603_1608Metric", 15, 17, 0, False),
    ("R5", RES, "R_0603_1608Metric", 18, 17, 0, False),
    ("C5", CAP, "C_0603_1608Metric", 21, 17, 0, False),
    # 电源/USB 区(下方)
    ("C1", CAP, "C_0603_1608Metric", 4,  24, 90, False),
    ("C2", CAP, "C_0603_1608Metric", 8,  24, 90, False),
    ("F1", RES, "R_0603_1608Metric", 9,  27.5, 0, False),
    ("R6", RES, "R_0603_1608Metric", 13, 27.5, 0, False),
    ("R7", RES, "R_0603_1608Metric", 19, 27.5, 0, False),
    # 右条:按键/排针/灯带扩展
    ("SW1", BTN, "Panasonic_EVQPUJ_EVQPUA", 28.5, 12, 0, False),
    ("P1", HDR, "PinHeader_1x03_P2.54mm_Vertical", 28.5, 18, 0, False),
    ("C6", CAP, "C_0805_2012Metric", 25, 18, 90, False),
    # 测试焊盘:左条一列
    ("TP1", TP, "TestPoint_Pad_D1.0mm", 3, 6,  0, False),
    ("TP2", TP, "TestPoint_Pad_D1.0mm", 3, 9,  0, False),
    ("TP3", TP, "TestPoint_Pad_D1.0mm", 3, 12, 0, False),
    ("TP4", TP, "TestPoint_Pad_D1.0mm", 3, 15, 0, False),
    ("TP5", TP, "TestPoint_Pad_D1.0mm", 30, 6, 0, False),
    ("TP6", TP, "TestPoint_Pad_D1.0mm", 30, 9, 0, False),
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
 "+5V":     [("F1","2"),("U2","1"),("U2","3"),("C1","1"),("C6","1"),("P1","1")],
 "+3V3":    [("U2","5"),("C2","1"),("C3","1"),("C4","1"),("U1","3"),("R5","1"),("TP1","1")],
 "EN":      [("U1","8"),("R5","2"),("C5","1"),("TP5","1")],
 "USB_DP":  [("U1","27"),("J1","A6"),("J1","B6"),("D2","1")],
 "USB_DM":  [("U1","26"),("J1","A7"),("J1","B7"),("D2","3")],
 "CC1":     [("J1","A5"),("R6","1")],
 "CC2":     [("J1","B5"),("R7","1")],
 "IO7":     [("U1","21"),("R1","1")],
 "RGB_R":   [("R1","2"),("D1","1")],
 "IO6":     [("U1","20"),("R2","1")],
 "RGB_G":   [("R2","2"),("D1","3")],
 "IO5":     [("U1","19"),("R3","1")],
 "RGB_B":   [("R3","2"),("D1","5")],
 "IO4":     [("U1","18"),("R4","1")],
 "WS_DATA": [("R4","2"),("P1","2")],
 "BTN":     [("U1","16"),("SW1","1")],
 "UART_RX": [("U1","30"),("TP3","1")],
 "UART_TX": [("U1","31"),("TP4","1")],
 "IO9":     [("U1","23"),("TP6","1")],
}
GND = [("J1","A1B12"),("J1","B1A12"),("J1","1"),("J1","2"),("J1","3"),("J1","4"),
       ("U2","2"),("D2","2"),("SW1","2"),("P1","3"),("R6","2"),("R7","2"),
       ("C1","2"),("C2","2"),("C3","2"),("C4","2"),("C5","2"),("C6","2"),
       ("TP2","1"),("D1","2"),("D1","4")]
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
    pts = [(1.5,0.5),(28.5,0.5),(28.5,5.0),(1.5,5.0)]
    poly = z.Outline()
    poly.NewOutline()
    for px,py in pts: poly.Append(mm(px), mm(py))
    board.Add(z)
    print("keepout ok")
except Exception as e:
    print("keepout skip:", e)

board.BuildListOfNets()
board.BuildConnectivity()
out = os.path.join(PROJ, "vibe_lamp_core_v1.kicad_pcb")
pcbnew.SaveBoard(out, board)
print("SAVED:", out, "nets=", board.GetNetCount())
