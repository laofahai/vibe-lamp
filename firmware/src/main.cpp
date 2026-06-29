#include <Arduino.h>
#include <WiFi.h>
#include "config.h"
#include "render_engine.h"
#include "display.h"
#include "net.h"
#include "api_server.h"
#include "settings_store.h"
#include "ble_state.h"

static Rgb g_pixels[NUM_LEDS];

void setup() {
  Serial.begin(115200);
  delay(300);
  display().begin();
  render_set_settings(settings_load());   // 从 NVS 恢复用户设置

  // —— 重配网入口：开机时长按按钮 → 清凭据 + 重启进配网门户 ——
  pinMode(PIN_RESET_BTN, INPUT_PULLUP);
  if (digitalRead(PIN_RESET_BTN) == LOW) {        // 上电瞬间已按下
    Serial.println("检测到重配网按钮，按住 3s 将清除 WiFi 凭据...");
    uint32_t start = millis();
    while (digitalRead(PIN_RESET_BTN) == LOW) {
      if (millis() - start >= RESET_HOLD_MS) {
        Serial.println("重置 WiFi 凭据，重启进入配网门户");
        net_reset_and_reboot();                   // 内部 resetSettings + ESP.restart()
      }
      delay(50);
    }
    // 没按满 3s 松手 → 不重置，继续正常启动
  }

  if (net_begin())
    Serial.printf("WiFi OK, http://%s.local  IP=%s\n", net_hostname(), WiFi.localIP().toString().c_str());
  else
    Serial.println("WiFi 未连接（长按 BOOT 键 3s 或访问 /reset 重新配网）");
  api_begin();

#ifdef ENABLE_BLE
  ble_state_begin();
  Serial.println("BLE 状态兜底服务已启动（设备名 VibeLamp）");
#endif
}

void loop() {
  static uint32_t boot_start = millis();
  if (millis() - boot_start < 1500) {
    Session boot{ State::BOOT, ToolKind::NONE, boot_start, 0 };
    render(&boot, 1, millis(), g_pixels, NUM_LEDS);
    display().show(g_pixels, NUM_LEDS);
    api_loop();
    delay(16);
    return;
  }
  api_loop();
  uint32_t now = millis();

  const Session* sessions = api_sessions();
  uint8_t count = api_session_count();
  uint32_t last = api_last_state_ms();

  // 看门狗：从未收到过 / 超时未收到 → 失联（仅在 WiFi 已起来后才算失联）
  bool stale = (last == 0) || (now - last > WATCHDOG_TIMEOUT_MS);

  if (stale && net_connected()) {
    Session lost{ State::LOST, ToolKind::NONE, /*since*/ (last? last+WATCHDOG_TIMEOUT_MS : 0), 0 };
    render(&lost, 1, now, g_pixels, NUM_LEDS);
  } else if (count == 0) {
    render(nullptr, 0, now, g_pixels, NUM_LEDS);   // idle
  } else {
    render(sessions, count, now, g_pixels, NUM_LEDS);
  }
  display().show(g_pixels, NUM_LEDS);
  delay(16);
}
