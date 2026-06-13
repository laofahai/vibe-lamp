#include <WiFi.h>
#include <ESPmDNS.h>
#include "config.h"
#include "net.h"
#include "secrets.h"

bool net_begin() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > 20000) return false;   // 20s 超时
    delay(250);
  }
  if (MDNS.begin(MDNS_HOST)) {                     // → vibelamp.local
    MDNS.addService("http", "tcp", HTTP_PORT);
  }
  return true;
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }
