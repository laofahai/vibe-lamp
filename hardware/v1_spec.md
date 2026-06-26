# Vibe Lamp Core V1 硬件规格

## 目标

V1 是一块小型桌面状态灯主控板，目标是“工厂贴好，用户不焊接”。用户拿到后只需要插 USB-C 供电，完成 WiFi 配网即可使用。

本版优先支持单颗共阴 RGB LED，预留 WS2812 灯环/灯带扩展焊盘。WS2812 不是 V1 必需功能，不影响主产品交付。

## 外形

- PCB：圆角方形，建议 28 mm x 28 mm。
- 层数：2 层板即可。
- 厚度：1.0 mm 或 1.2 mm，便于做小外壳。
- 正面中心放 RGB LED，外壳使用半透明扩散罩。
- USB-C 口放一边，作为供电和调试接口。
- 清网按钮放侧边或背面边缘，避免误触。

## 主控

- MCU：ESP32-C3-MINI-1 模组。
- 原因：
  - 体积比 ESP32-C3 SuperMini 载板小。
  - 自带射频匹配和天线，降低 RF 风险。
  - 支持原生 USB，后续刷机/日志更方便。
- 组装方式：SMT 工厂贴片，不要求用户焊接。

## 显示

### 主显示：单颗 RGB LED

- 类型：共阴 RGB LED。
- 推荐封装：贴片 RGB LED，优先选立创可贴片库存。
- 固件现有引脚：
  - R：GPIO7
  - G：GPIO6
  - B：GPIO5
- 每路串 330 ohm 电阻。

### 预留扩展：WS2812

- 预留 3 个测试焊盘或小焊盘：
  - 5V
  - DATA
  - GND
- DATA：GPIO4。
- DATA 串 330 ohm 电阻。
- 5V/GND 旁预留 470 uF 电容焊盘。
- V1 默认不装外接灯环，不要求用户焊接；这是给 V2 或工程验证留的扩展。

## 按钮

- 清网按钮：GPIO10 到 GND，输入上拉。
- 功能：长按清除 WiFi 凭据并重启进入配网。
- 按钮必须工厂贴好，用户不焊接。

## 供电

- 输入：USB-C 5V。
- 3.3V：板上 LDO 给 ESP32-C3-MINI-1 供电。
- 单颗 RGB 供电电流很小，普通 USB 口足够。
- WS2812 只是预留，若未来外接灯环，要按灯数重新核算 5V 电流。

## 固件目标

V1 主固件使用现有 `c3_rgb` env：

- `DISPLAY_TYPE=DISPLAY_RGB_LED`
- `PIN_RGB_B=5`
- `PIN_RGB_G=6`
- `PIN_RGB_R=7`
- 建议增加：`PIN_RESET_BTN=10`

WS2812 后续可新增 `c3_ring_16` 等 env，不影响 V1 主板。

## 打样/生产要求

- 必须选择 SMT 贴片服务。
- USB-C、ESP32-C3-MINI-1、LDO、RGB LED、按钮、电阻电容都应由工厂贴好。
- 用户不做任何焊接。
- 如果找硬件工程师画板，把本目录下的 `v1_schematic.md`、`v1_bom.csv`、`v1_pcb_constraints.md` 一起给对方。

