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

// —— 像素数 ——
#if DISPLAY_TYPE == DISPLAY_RGB_LED
  #define NUM_LEDS 1
#elif DISPLAY_TYPE == DISPLAY_WS2812_RING
  #define NUM_LEDS 16
#elif DISPLAY_TYPE == DISPLAY_WS2812_STRIP
  #define NUM_LEDS 8
#else
  #define NUM_LEDS 3
#endif

// —— 引脚 ——
// RGB LED（共阴；共阳需在驱动里反相）
#define PIN_RGB_R 25
#define PIN_RGB_G 26
#define PIN_RGB_B 27
// WS2812 数据脚
#define PIN_WS2812 4

// —— PWM ——
#define LEDC_FREQ 5000
#define LEDC_RES  8        // 8 bit：0..255

// —— 网络 ——
#define MDNS_HOST "vibelamp"          // → vibelamp.local
#define HTTP_PORT 80
#define WATCHDOG_TIMEOUT_MS 30000UL   // 30s 无 /state → 失联

// —— 亮度上限（保护眼睛/限流）——
#define MAX_BRIGHTNESS 160

// —— 网页配网（WiFiManager）——
#define PROV_AP_NAME       "VibeLamp-Setup"   // 配网热点 SSID
#define PROV_AP_PASS       ""                 // 空 = 开放热点（家用够用；要加密改成 >=8 位）
#define PROV_PORTAL_TIMEOUT 180               // 配网门户超时（秒）；超时后退出门户继续 loop

// —— 重配网按钮（开机长按触发 resetSettings + 重开门户）——
// 用板载 BOOT 按钮（多数 ESP32 开发板 = GPIO0，已接上拉，按下拉低）
#define PIN_RESET_BTN      0
#define RESET_HOLD_MS      3000UL             // 开机时长按 3s 触发重配网
