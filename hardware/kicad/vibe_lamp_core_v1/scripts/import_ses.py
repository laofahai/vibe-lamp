import pcbnew, sys
pcb, ses = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(pcb)
ok = pcbnew.ImportSpecctraSES(b, ses)
pcbnew.SaveBoard(pcb, b)
print("import ok=", ok)
