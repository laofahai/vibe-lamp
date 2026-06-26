# Vibe Lamp Core V1 原理图连接表

这份文件是给硬件工程师画原理图用的连接说明，不是最终原理图文件。

## 电源

### USB-C 输入

- USB-C VBUS -> `+5V`
- USB-C GND -> `GND`
- CC1 -> 5.1k -> GND
- CC2 -> 5.1k -> GND
- D+ / D- -> ESP32-C3 原生 USB D+ / D-

建议：

- VBUS 后预留保险丝或 0 ohm 跳线位。
- USB 口附近预留 ESD 器件位，V1 可按成本决定是否装。

### 3.3V

- `+5V` -> LDO IN
- LDO OUT -> `+3V3`
- LDO GND -> `GND`
- LDO 输入输出按数据手册放去耦电容。

推荐 LDO：

- 优先选立创可 SMT 的 3.3V LDO，输出能力 >= 500 mA。
- 不建议用 AMS1117 做小板主 LDO，体积和热都不划算。

## ESP32-C3-MINI-1

### 必接

- 3V3 -> `+3V3`
- GND -> `GND`
- EN -> 10k 上拉到 `+3V3`
- EN -> 100 nF 到 GND（可选，提升上电复位稳定性）
- IO9/BOOT：预留测试焊盘或下载按钮位，默认上拉，不作为产品清网按钮

### USB

- USB D+ -> ESP32-C3 USB D+
- USB D- -> ESP32-C3 USB D-

USB 差分线按常规短、等长、少过孔处理。V1 低速/全速 USB，难度不高，但不要绕远。

## RGB LED

类型：共阴 RGB LED。

连接：

- RGB 公共阴极 -> GND
- GPIO7 -> 330 ohm -> RGB_R
- GPIO6 -> 330 ohm -> RGB_G
- GPIO5 -> 330 ohm -> RGB_B

说明：

- 当前固件按高电平点亮设计。
- 如果实际选到共阳 RGB LED，驱动逻辑要反相；V1 不建议选共阳。

## WS2812 预留扩展

预留 3 焊盘，丝印：

- `5V`
- `DIN`
- `GND`

连接：

- `+5V` -> WS2812_5V 焊盘
- `GND` -> WS2812_GND 焊盘
- GPIO4 -> 330 ohm -> WS2812_DIN 焊盘
- WS2812_5V 与 GND 旁预留 470 uF 电容位

说明：

- V1 默认不装灯环。
- 这个扩展口只给后续工程验证/返修使用，不要求最终用户焊接。

## 清网按钮

- GPIO10 -> 按钮一端
- 按钮另一端 -> GND
- GPIO10 使用 MCU 内部上拉
- 可额外预留 100 nF 到 GND 做简单消抖，不强制

固件：

- `-DPIN_RESET_BTN=10`

## 调试焊盘

建议预留小测试焊盘：

- 3V3
- GND
- GPIO20/U0RX
- GPIO21/U0TX
- EN
- IO9/BOOT

这些焊盘不是给用户使用，是给工程调试/救砖用。

