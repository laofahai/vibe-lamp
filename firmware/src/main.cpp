#include <Arduino.h>
#include <WiFi.h>
#include "config.h"
#include "render_engine.h"
#include "display.h"
#include "net.h"

static Rgb g_pixels[NUM_LEDS];
static Session g_session;           // 单会话（网络层接入前先写死自检）
static bool g_has_session = false;

void setup() {
  Serial.begin(115200);
  delay(300);
  display().begin();
  if (net_begin())
    Serial.printf("WiFi OK, http://%s.local  IP=%s\n", MDNS_HOST, WiFi.localIP().toString().c_str());
  else
    Serial.println("WiFi FAILED (检查 secrets.h)");
  // 自检：开机 2s BOOT，然后进入 WORKING 看呼吸
  g_session = Session{ State::WORKING, ToolKind::CODE, millis(), 0 };
  g_has_session = true;
  Serial.println("VibeLamp display self-test: WORKING breathing");
}

void loop() {
  uint32_t now = millis();
  if (g_has_session)
    render(&g_session, 1, now, g_pixels, NUM_LEDS);
  else
    render(nullptr, 0, now, g_pixels, NUM_LEDS);
  display().show(g_pixels, NUM_LEDS);
  delay(16);   // ~60fps
}
