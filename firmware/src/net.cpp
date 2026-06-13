#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>      // tzapu/WiFiManager
#include "config.h"
#include "net.h"
// 注意：不再 include "secrets.h" —— 凭据由 WiFiManager 存/取 ESP32 NVS

static WiFiManager wm;

static void start_mdns() {
  if (MDNS.begin(MDNS_HOST)) {              // → vibelamp.local
    MDNS.addService("http", "tcp", HTTP_PORT);
  }
}

bool net_begin() {
  WiFi.mode(WIFI_STA);

  // 配网门户超时：超时后 autoConnect 返回 false，固件继续跑（进失联态等重配），
  // 不死等、不阻塞看门狗逻辑。
  wm.setConfigPortalTimeout(PROV_PORTAL_TIMEOUT);

  // autoConnect：
  //  - NVS 有可用凭据 → 直接连，连上返回 true；
  //  - 无凭据 / 连不上 → 起 AP「VibeLamp-Setup」+ captive portal，
  //    用户在手机浏览器选 WiFi、填密码 → WiFiManager 自动存 NVS、重连。
  bool ok;
  if (PROV_AP_PASS[0] == '\0') {
    ok = wm.autoConnect(PROV_AP_NAME);                 // 开放热点
  } else {
    ok = wm.autoConnect(PROV_AP_NAME, PROV_AP_PASS);   // 加密热点
  }

  if (ok) {
    start_mdns();
  }
  return ok;
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }

void net_reset_and_reboot() {
  wm.resetSettings();   // 清 NVS 里的 WiFi 凭据
  delay(300);
  ESP.restart();        // 重启 → 下次 net_begin 无凭据 → 自动进配网门户
}

bool net_start_portal() {
  bool ok;
  if (PROV_AP_PASS[0] == '\0') {
    ok = wm.startConfigPortal(PROV_AP_NAME);
  } else {
    ok = wm.startConfigPortal(PROV_AP_NAME, PROV_AP_PASS);
  }
  if (ok) start_mdns();
  return ok;
}
