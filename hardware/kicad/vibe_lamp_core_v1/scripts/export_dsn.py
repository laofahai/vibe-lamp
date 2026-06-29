import pcbnew, sys
pcb, dsn = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(pcb)
ok = pcbnew.ExportSpecctraDSN(b, dsn)
print("export ok=", ok)
