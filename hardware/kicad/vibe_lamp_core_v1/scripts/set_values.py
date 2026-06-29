import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
VAL = {"R1":"470","R2":"150","R3":"150","R4":"330","R5":"10k","R6":"5.1k","R7":"5.1k","F1":"0R",
 "C1":"1uF","C2":"1uF","C3":"10uF","C4":"100nF","C5":"100nF","C6":"470uF",
 "D1":"RGB-LED-5050-CC","U1":"ESP32-C3-MINI-1","U2":"AP2112K-3.3",
 "J1":"USB-C-TYPE-C-31-M-12","D2":"USBLC6-2SC6","SW1":"SW-PUSH","P1":"WS2812-EXT-1x3"}
for fp in b.GetFootprints():
    r=fp.GetReference()
    if r in VAL: fp.SetValue(VAL[r])
pcbnew.SaveBoard(sys.argv[1], b)
print("values set")
