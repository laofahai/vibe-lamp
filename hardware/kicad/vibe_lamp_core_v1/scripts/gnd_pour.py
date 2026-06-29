import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
def mm(v): return pcbnew.FromMM(v)
gnd = b.FindNet("GND")
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNetCode(gnd.GetNetCode())
    z.SetIsRuleArea(False); z.SetLocalClearance(mm(0.3)); z.SetMinThickness(mm(0.2))
    p = z.Outline(); p.NewOutline()
    for x,y in [(0.7,0.7),(39.3,0.7),(39.3,39.3),(0.7,39.3)]: p.Append(mm(x),mm(y))
    b.Add(z)
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.SaveBoard(sys.argv[1], b)
print("GND zones filled")
