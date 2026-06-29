import pcbnew, sys, csv
b = pcbnew.LoadBoard(sys.argv[1])
# 确定立创料号（U1/U2/J1/D2 是从立创拉的，料号确定；被动件留空待选 JLCPCB 基础库）
LCSC = {"U1":"C2934569","U2":"C51118","J1":"C165948","D2":"C7519","D1":"C2761795","SW1":"C115360"}
DNP = {"C6","P1"}   # 默认不贴:C6(470uF,仅外接灯带需要)、P1(排针,手焊扩展口)
rows=[]
for fp in b.GetFootprints():
    ref=fp.GetReference(); val=fp.GetValue()
    fpid=fp.GetFPID().GetLibItemName()
    if ref.startswith("TP") or ref in DNP: continue   # 测试焊盘 + DNP 不进贴片 BOM
    rows.append((ref, val, str(fpid), LCSC.get(ref,"")))
# 按 (value, footprint, lcsc) 合并位号 → JLCPCB BOM 格式
from collections import defaultdict
grp=defaultdict(list)
for ref,val,fpid,lcsc in rows: grp[(val,fpid,lcsc)].append(ref)
def keyn(r):
    import re; m=re.match(r"([A-Za-z]+)(\d+)",r); return (m.group(1),int(m.group(2))) if m else (r,0)
with open(sys.argv[2],"w",newline="") as f:
    w=csv.writer(f); w.writerow(["Comment","Designator","Footprint","LCSC Part #"])
    for (val,fpid,lcsc),refs in sorted(grp.items()):
        refs=sorted(refs,key=keyn)
        w.writerow([val, ",".join(refs), fpid, lcsc])
print("BOM rows:", len(grp))
