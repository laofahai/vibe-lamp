#pragma once
#include <stdint.h>

// —— 显示硬件类型（由 build_flags 的 -DDISPLAY_TYPE 选择）——
#define DISPLAY_RGB_LED     1   // 单颗共阴 RGB LED，3 路 PWM
#define DISPLAY_WS2812_RING 2   // WS2812 灯环
#define DISPLAY_WS2812_STRIP 3  // WS2812 灯条
#define DISPLAY_DISCRETE    4   // 多颗分立定色 LED

#ifndef DISPLAY_TYPE
#define DISPLAY_TYPE DISPLAY_RGB_LED
#endif

// —— 像素数（可由 build_flag -DNUM_LEDS 覆盖，例如 Core V1 板单颗 WS2812 用 1）——
#ifndef NUM_LEDS
#if DISPLAY_TYPE == DISPLAY_RGB_LED
  #define NUM_LEDS 1
#elif DISPLAY_TYPE == DISPLAY_WS2812_RING
  #define NUM_LEDS 16
#elif DISPLAY_TYPE == DISPLAY_WS2812_STRIP
  #define NUM_LEDS 8
#else
  #define NUM_LEDS 3
#endif
#endif

// —— 引脚 ——
// RGB LED（共阴；共阳需在驱动里反相）
#ifndef PIN_RGB_R
#define PIN_RGB_R 25
#endif
#ifndef PIN_RGB_G
#define PIN_RGB_G 26
#endif
#ifndef PIN_RGB_B
#define PIN_RGB_B 27
#endif
// WS2812 数据脚
#ifndef PIN_WS2812
#define PIN_WS2812 4
#endif

// —— PWM ——
#define LEDC_FREQ 5000
#define LEDC_RES  8        // 8 bit：0..255

// —— 网络 ——
#define MDNS_HOST "vibelamp"          // 设备名基准；实际 mDNS 会追加芯片 MAC 后缀，避免多人局域网冲突
#define HTTP_PORT 80
#define WATCHDOG_TIMEOUT_MS 30000UL   // 30s 无 /state → 失联

// —— 亮度上限（保护眼睛/限流）——
#define MAX_BRIGHTNESS 160

// —— 网页配网（WiFiManager）——
#define PROV_AP_NAME       "VibeLamp-Setup"   // 配网热点 SSID
#define PROV_AP_PASS       ""                 // 空 = 开放热点（家用够用；要加密改成 >=8 位）
#define PROV_PORTAL_TIMEOUT 180               // 配网门户超时（秒）；超时后退出门户继续 loop
#define WIFI_CONNECT_TIMEOUT_MS 12000UL       // 每轮自动连接已知 WiFi 的最长等待
#define WIFI_CONNECT_ROUNDS     4             // 多试几轮，避免路由器刚启动/瞬时抖动误进门户
#define WIFI_CONNECT_RETRY_DELAY_MS 1500UL    // 每轮扫描/连接失败后稍等，让射频和路由器稳定
#define PROV_CONNECT_TIMEOUT    20            // 门户提交后连接新 WiFi 的最长等待（秒），避免卡在保存页

// —— 重配网按钮（开机长按触发 resetSettings + 重开门户）——
// 用板载 BOOT 按钮（多数经典 ESP32 开发板 = GPIO0，已接上拉，按下拉低）。
// 注意 ESP32-C3：BOOT 键是 GPIO9，且是 strapping 脚——上电瞬间拉低会进「串口下载模式」、
//   固件根本不运行，所以 C3 上「开机长按 BOOT」这套用不了。C3 产品板请把按钮接到一个
//   空闲 GPIO（如 GPIO10/0/1/3/4），用 build_flag -DPIN_RESET_BTN=<gpio> 覆盖；
//   面包板没接按钮时无需理会（GPIO0 在 C3 非 strapping，INPUT_PULLUP 读高=未按，不会误触）。
//   无按钮也可随时用 HTTP `curl -X POST http://vibelamp.local/reset` 清网重配。
#ifndef PIN_RESET_BTN
#define PIN_RESET_BTN      0
#endif
#define RESET_HOLD_MS      3000UL             // 开机时长按 3s 触发重配网

// —— BLE 状态推送服务（Part B②，与配网无关，可与 WiFi 共存）——
// 仅在编译开 -DENABLE_BLE 时生效（独立 env:esp32_ble）；默认构建不含 BLE。
#define BLE_STATE_DEVICE_NAME  "VibeLamp"
#define BLE_STATE_SERVICE_UUID "6e6c0001-b5a3-f393-e0a9-e50e24dcca9e"
#define BLE_STATE_CHAR_UUID    "6e6c0002-b5a3-f393-e0a9-e50e24dcca9e"
