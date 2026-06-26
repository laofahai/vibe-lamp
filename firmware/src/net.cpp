#include <WiFi.h>
#include <WiFiMulti.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>      // tzapu/WiFiManager
#include <Preferences.h>
#include <string>
#include "config.h"
#include "net.h"
#include "wifi_cred_list.h"
// 凭据由 WiFiManager 配网门户提供；连上后追加进「自建多网表」(NVS)，
// 下次开机交给 WiFiMulti 自动择优连接——记住多个网、自动挑最强可用的。

static WiFiManager wm;

// —— 自建多网凭据表的 NVS 存储（与 WiFiManager 自己的 wifi NVS 分开，互不干扰）——
static const char* CREDS_NS  = "wm_multi";
static const char* CREDS_KEY = "creds";

static void start_mdns() {
  if (MDNS.begin(MDNS_HOST)) {              // → vibelamp.local
    MDNS.addService("http", "tcp", HTTP_PORT);
  } else {
    // 注册失败时给出提示，否则用户访问 vibelamp.local 失败时毫无头绪。
    Serial.println("[警告] mDNS 注册失败，请改用 IP 地址访问设备");
  }
}

// 从 NVS 读出多网表。缺失/坏数据 → 空表，绝不崩。
static WifiCredList load_creds() {
  WifiCredList list;
  Preferences p;
  if (p.begin(CREDS_NS, /*readOnly=*/true)) {
    size_t len = p.getBytesLength(CREDS_KEY);
    if (len > 0) {
      std::string blob;
      blob.resize(len);
      p.getBytes(CREDS_KEY, &blob[0], len);
      list.parse(blob);                     // 解析失败 → list 保持空表
    }
    p.end();
  }
  return list;
}

// 把多网表写回 NVS。blob 含 \0（长度前缀），必须 putBytes（putString 会在首个 \0 截断）。
static void save_creds(const WifiCredList& list) {
  Preferences p;
  if (p.begin(CREDS_NS, /*readOnly=*/false)) {
    std::string blob = list.serialize();
    p.putBytes(CREDS_KEY, blob.data(), blob.size());
    p.end();
  }
}

static void clear_creds() {
  Preferences p;
  if (p.begin(CREDS_NS, /*readOnly=*/false)) {
    p.remove(CREDS_KEY);
    p.end();
  }
}

// 把「当前已连上的网络」追加进表头（非覆盖）并落 NVS。门户/迁移连上后调用。
static void remember_current(WifiCredList& creds) {
  String ssid = WiFi.SSID();
  String pass = WiFi.psk();
  if (ssid.length() == 0) return;
  creds.add(std::string(ssid.c_str()), std::string(pass.c_str()));
  save_creds(creds);
}

// 用已知网络多轮自动连接：WiFiMulti 扫描并连最强可用的已知网。连上返回 true。
// 多轮 + 拉长超时，容忍路由器刚上电/瞬时抖动——「连不上」≠「网不在」，避免误进配网门户。
static bool connect_known(const WifiCredList& creds) {
  if (creds.count() == 0) return false;
  WiFiMulti multi;
  for (size_t i = 0; i < creds.count(); ++i) {
    multi.addAP(creds.get(i).ssid.c_str(), creds.get(i).pass.c_str());
  }
  for (uint8_t round = 0; round < WIFI_CONNECT_ROUNDS; ++round) {
    if (multi.run(WIFI_CONNECT_TIMEOUT_MS) == WL_CONNECTED) {
      Serial.printf("[net] WiFiMulti 自动择优连上已知网: %s\n", WiFi.SSID().c_str());
      return true;
    }
  }
  return false;
}

bool net_begin() {
  WiFi.mode(WIFI_STA);
  // 配网门户超时：超时后 autoConnect 返回 false，固件继续跑（进失联态等重配）。
  wm.setConfigPortalTimeout(PROV_PORTAL_TIMEOUT);

  WifiCredList creds = load_creds();
  Serial.printf("[net] 多网表载入 %u 条已知网\n", (unsigned)creds.count());

  // 1) 多网表非空 → WiFiMulti 自动择优连接（多轮，容忍路由器刚上电/瞬时抖动）
  if (connect_known(creds)) {
    start_mdns();
    return true;
  }

  // 2) 表空 / 已知网都不可用 → 交给 WiFiManager.autoConnect：
  //    它先用自己 NVS 里存的单网凭据连（天然兼容旧固件、上次配的网——比 WiFi.begin()
  //    无参可靠），连不上才弹 VibeLamp-Setup 门户。无论旧凭据自动连上、还是门户新配上，
  //    都把「当前连上的网」导入多网表——于是每配一个新网都被记住，下次 WiFiMulti 自动择优。
  bool ok;
  if (PROV_AP_PASS[0] == '\0') {
    ok = wm.autoConnect(PROV_AP_NAME);                 // 开放热点
  } else {
    ok = wm.autoConnect(PROV_AP_NAME, PROV_AP_PASS);   // 加密热点
  }
  if (ok && WiFi.status() == WL_CONNECTED) {
    Serial.printf("[net] autoConnect 连上 %s（单网/门户），导入多网表\n", WiFi.SSID().c_str());
    remember_current(creds);
    start_mdns();
    return true;
  }
  return false;
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }

void net_reset_and_reboot() {
  wm.resetSettings();   // 清 WiFiManager 自己的 wifi NVS 凭据
  clear_creds();        // 清自建多网表（记住的所有网一并清掉）
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
  if (ok && WiFi.status() == WL_CONNECTED) {
    WifiCredList creds = load_creds();
    remember_current(creds);                 // 运行时主动重配也追加进表
    start_mdns();
  }
  return ok;
}
