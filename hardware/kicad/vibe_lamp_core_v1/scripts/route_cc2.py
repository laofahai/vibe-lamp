#!/usr/bin/env python3
# 手补 CC2：J1.B5 → R7.1 的一条直线。
# R7 在 gen_pcb.py 中被放到 B5 正北空走廊(同 x=21.75),所以 CC2 是一条
# 竖直短线,Freerouting 常因优先级跳过它,这里直接补上(0 短路)。
import sys, pcbnew
def mm(v): return pcbnew.FromMM(v)
pcb = sys.argv[1] if len(sys.argv) > 1 else "vibe_lamp_core_v1.kicad_pcb"
b = pcbnew.LoadBoard(pcb)

fps = {f.GetReference(): f for f in b.GetFootprints()}
def pad_pos(ref, name):
    for p in fps[ref].Pads():
        if p.GetName() == name:
            return pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
    raise SystemExit(f"pad {ref}.{name} 未找到")
bx, by = pad_pos("J1", "B5")
rx, ry = pad_pos("R7", "1")
print(f"CC2: J1.B5({bx:.2f},{by:.2f}) -> R7.1({rx:.2f},{ry:.2f})")

cc2 = None
for code, ni in b.GetNetInfo().NetsByNetcode().items():
    if ni.GetNetname() == "CC2":
        cc2 = ni; break
if cc2 is None:
    raise SystemExit("CC2 网络不存在")

t = pcbnew.PCB_TRACK(b)
t.SetStart(pcbnew.VECTOR2I(mm(bx), mm(by)))
t.SetEnd(pcbnew.VECTOR2I(mm(rx), mm(ry)))
t.SetWidth(mm(0.20)); t.SetLayer(pcbnew.F_Cu); t.SetNet(cc2)
b.Add(t)
b.BuildConnectivity()
pcbnew.SaveBoard(pcb, b)
print("CC2 track added on F.Cu, width 0.20mm")
