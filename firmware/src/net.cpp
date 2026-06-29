#include <WiFi.h>
#include <ESPmDNS.h>
#include <WiFiManager.h>      // tzapu/WiFiManager
#include <Preferences.h>
#include <esp_wifi.h>
#include <cstring>
#include <string>
#include "config.h"
#include "net.h"
#include "wifi_cred_list.h"
// 凭据由 WiFiManager 配网门户提供；连上后追加进「自建多网表」(NVS)。
// WiFiManager 只做 captive portal UI，不再作为单网凭据真源。

static WiFiManager wm;
static String g_host;
static String g_mac;
static String g_ap_name;
static String g_portal_title;
static String g_portal_html;
static WiFiManagerParameter* g_identity_param = nullptr;
static bool g_wifi_events_installed = false;

// —— 自建多网凭据表的 NVS 存储（与 WiFiManager 自己的 wifi NVS 分开，互不干扰）——
static const char* CREDS_NS  = "wm_multi";
static const char* CREDS_KEY = "creds";

static const char* current_host() {
  if (g_host.length() == 0) {
    char suffix[7];
    uint8_t mac[6];
    WiFi.macAddress(mac);
    snprintf(suffix, sizeof(suffix), "%02x%02x%02x", mac[3], mac[4], mac[5]);
    g_host = String(MDNS_HOST) + "-" + suffix;
  }
  return g_host.c_str();
}

static const char* current_mac() {
  if (g_mac.length() == 0) {
    uint8_t mac[6];
    WiFi.macAddress(mac);
    char buf[18];
    snprintf(buf, sizeof(buf), "%02x:%02x:%02x:%02x:%02x:%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    g_mac = buf;
  }
  return g_mac.c_str();
}

static const char* portal_ap_name() {
  if (g_ap_name.length() == 0) {
    String host = current_host();
    int dash = host.lastIndexOf('-');
    String suffix = dash >= 0 ? host.substring(dash + 1) : host;
    g_ap_name = String(PROV_AP_NAME) + "-" + suffix;
  }
  return g_ap_name.c_str();
}

static void configure_portal_identity() {
  const char* host = current_host();
  const char* mac = current_mac();
  g_portal_title = String("Vibe Lamp ") + host;
  wm.setTitle(g_portal_title);
  wm.setHostname(host);

  if (!g_identity_param) {
    g_portal_html =
      String("<p><b>设备名</b><br><code>") + host + ".local</code></p>"
      "<p><b>MAC 地址</b><br><code>" + mac + "</code></p>"
      "<p>多人同网时，用这个设备名绑定本机守护进程。</p>";
    g_identity_param = new WiFiManagerParameter(g_portal_html.c_str());
    wm.addParameter(g_identity_param);
  }
}

static void configure_wifi_events() {
  if (g_wifi_events_installed) return;
  WiFi.onEvent([](WiFiEvent_t event, WiFiEventInfo_t info) {
    if (event == ARDUINO_EVENT_WIFI_STA_DISCONNECTED) {
      Serial.printf("[net] WiFi 断开 reason=%u status=%d\n",
                    (unsigned)info.wifi_sta_disconnected.reason,
                    (int)WiFi.status());
    } else if (event == ARDUINO_EVENT_WIFI_STA_GOT_IP) {
      Serial.printf("[net] WiFi 获得 IP: %s\n",
                    WiFi.localIP().toString().c_str());
    }
  });
  g_wifi_events_installed = true;
}

static void reset_sta_radio() {
  WiFi.disconnect(false, false);
  uint32_t start = millis();
  while (WiFi.status() != WL_DISCONNECTED &&
         WiFi.status() != WL_IDLE_STATUS &&
         WiFi.status() != WL_NO_SSID_AVAIL &&
         (millis() - start) < 1500) {
    delay(50);
  }
  delay(250);
}

static wl_status_t wait_for_connect_result(uint32_t timeout_ms) {
  uint32_t start = millis();
  wl_status_t st = (wl_status_t)WiFi.status();
  while (st != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(100);
    st = (wl_status_t)WiFi.status();
  }
  Serial.printf("[net] 连接等待结束 status=%d elapsed=%lu\n",
                (int)st, (unsigned long)(millis() - start));
  return st;
}

static bool configure_sta_radio() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  esp_err_t err = esp_wifi_set_protocol(
      WIFI_IF_STA, WIFI_PROTOCOL_11B | WIFI_PROTOCOL_11G | WIFI_PROTOCOL_11N);
  if (err != ESP_OK) {
    Serial.printf("[net] 设置 WiFi 协议失败 err=%d\n", (int)err);
  }
  return err == ESP_OK;
}

static const char* auth_mode_name(uint8_t auth) {
  switch (auth) {
    case WIFI_AUTH_OPEN: return "OPEN";
    case WIFI_AUTH_WEP: return "WEP";
    case WIFI_AUTH_WPA_PSK: return "WPA";
    case WIFI_AUTH_WPA2_PSK: return "WPA2";
    case WIFI_AUTH_WPA_WPA2_PSK: return "WPA/WPA2";
    case WIFI_AUTH_ENTERPRISE: return "ENTERPRISE";
    case WIFI_AUTH_WPA3_PSK: return "WPA3";
    case WIFI_AUTH_WPA2_WPA3_PSK: return "WPA2/WPA3";
    case WIFI_AUTH_WAPI_PSK: return "WAPI";
    default: return "UNKNOWN";
  }
}

static void apply_min_security(const WifiCredential& cred) {
  // Arduino-ESP32 默认最低安全级别是 WPA2；一些老路由/混合模式会扫成 WPA，
  // 不放宽会表现为扫得到 SSID、连接时却 NO_AP_FOUND。
  WiFi.setMinSecurity(cred.pass.empty() ? WIFI_AUTH_OPEN : WIFI_AUTH_WPA_PSK);
}

static void start_mdns() {
  const char* host = current_host();
  if (MDNS.begin(host)) {              // → vibelamp-xxxxxx.local，避免多人局域网撞名
    MDNS.addService("http", "tcp", HTTP_PORT);
    MDNS.addServiceTxt("http", "tcp", "name", host);
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

static void remember_credential(WifiCredList& creds,
                                const std::string& ssid,
                                const std::string& pass) {
  if (ssid.empty()) return;
  creds.add(ssid, pass);
  save_creds(creds);
}

struct ApCandidate {
  size_t cred_index;
  uint8_t bssid[6];
  int32_t channel;
  int32_t rssi;
};

static void sort_candidates(ApCandidate* items, size_t count) {
  for (size_t i = 0; i + 1 < count; ++i) {
    for (size_t j = i + 1; j < count; ++j) {
      if (items[j].rssi > items[i].rssi) {
        ApCandidate tmp = items[i];
        items[i] = items[j];
        items[j] = tmp;
      }
    }
  }
}

static size_t scan_known_candidates(const WifiCredList& creds,
                                    ApCandidate* out,
                                    size_t max_count) {
  int n = WiFi.scanNetworks();
  if (n <= 0) {
    Serial.printf("[net] 扫描到 %d 个 WiFi 网络\n", n);
    return 0;
  }

  size_t count = 0;
  Serial.printf("[net] 扫描到 %d 个 WiFi 网络\n", n);
  for (int i = 0; i < n && count < max_count; ++i) {
    String ssid;
    int32_t rssi;
    uint8_t enc;
    uint8_t* bssid;
    int32_t channel;
    WiFi.getNetworkInfo(i, ssid, enc, rssi, bssid, channel);

    for (size_t c = 0; c < creds.count(); ++c) {
      if (ssid != creds.get(c).ssid.c_str()) continue;
      if (enc != WIFI_AUTH_OPEN && creds.get(c).pass.empty()) continue;

      out[count].cred_index = c;
      memcpy(out[count].bssid, bssid, sizeof(out[count].bssid));
      out[count].channel = channel;
      out[count].rssi = rssi;
      Serial.printf("[net] 候选 AP: ssid=%s rssi=%d channel=%d auth=%u(%s) bssid=%02x:%02x:%02x:%02x:%02x:%02x\n",
                    ssid.c_str(), (int)rssi, (int)channel,
                    (unsigned)enc, auth_mode_name(enc),
                    out[count].bssid[0], out[count].bssid[1], out[count].bssid[2],
                    out[count].bssid[3], out[count].bssid[4], out[count].bssid[5]);
      ++count;
      break;
    }
  }
  WiFi.scanDelete();
  sort_candidates(out, count);
  return count;
}

static wl_status_t connect_candidate(const WifiCredList& creds,
                                     const ApCandidate& ap,
                                     uint32_t timeout_ms) {
  const WifiCredential& cred = creds.get(ap.cred_index);
  Serial.printf("[net] 尝试 AP: ssid=%s rssi=%d channel=%d bssid=%02x:%02x:%02x:%02x:%02x:%02x\n",
                cred.ssid.c_str(), (int)ap.rssi, (int)ap.channel,
                ap.bssid[0], ap.bssid[1], ap.bssid[2],
                ap.bssid[3], ap.bssid[4], ap.bssid[5]);

  reset_sta_radio();
  apply_min_security(cred);
  WiFi.begin(cred.ssid.c_str(),
             cred.pass.empty() ? nullptr : cred.pass.c_str(),
             ap.channel,
             ap.bssid);
  return wait_for_connect_result(timeout_ms);
}

static wl_status_t connect_credential_auto(const WifiCredential& cred,
                                           uint32_t timeout_ms) {
  Serial.printf("[net] 尝试自动选择 AP: ssid=%s\n", cred.ssid.c_str());
  reset_sta_radio();
  apply_min_security(cred);
  WiFi.begin(cred.ssid.c_str(),
             cred.pass.empty() ? nullptr : cred.pass.c_str());
  return wait_for_connect_result(timeout_ms);
}

// 用已知网络多轮自动连接：扫描所有可见 AP，按 SSID 匹配多网表；同名多 AP/合并 SSID
// 按 RSSI 从强到弱逐个 BSSID 尝试。单路由器是 1 个候选，多 AP 是多个候选。
// 多轮 + 拉长超时，容忍路由器刚上电/瞬时抖动——「连不上」≠「网不在」，避免误进配网门户。
static bool connect_known(const WifiCredList& creds) {
  if (creds.count() == 0) return false;
  for (size_t i = 0; i < creds.count(); ++i) {
    Serial.printf("[net] 已知 WiFi[%u]: %s\n",
                  (unsigned)i, creds.get(i).ssid.c_str());
  }

  constexpr size_t kMaxCandidates = 24;
  ApCandidate candidates[kMaxCandidates];
  for (uint8_t round = 0; round < WIFI_CONNECT_ROUNDS; ++round) {
    Serial.printf("[net] 自动连接已知 WiFi，第 %u/%u 轮\n",
                  (unsigned)(round + 1), (unsigned)WIFI_CONNECT_ROUNDS);

    reset_sta_radio();
    size_t count = scan_known_candidates(creds, candidates, kMaxCandidates);
    if (count == 0) {
      Serial.println("[net] 本轮没有发现任何已知 SSID");
      delay(WIFI_CONNECT_RETRY_DELAY_MS);
      continue;
    }

    bool visible[WifiCredList::kMaxEntries] = {};
    for (size_t i = 0; i < count; ++i) {
      if (candidates[i].cred_index < WifiCredList::kMaxEntries) {
        visible[candidates[i].cred_index] = true;
      }
    }

    for (size_t i = 0; i < creds.count(); ++i) {
      if (!visible[i]) continue;
      wl_status_t st = connect_credential_auto(creds.get(i), WIFI_CONNECT_TIMEOUT_MS);
      if (st == WL_CONNECTED) {
        Serial.printf("[net] 自动连上已知网: %s IP=%s RSSI=%d\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return true;
      }
    }

    reset_sta_radio();
    for (size_t i = 0; i < count; ++i) {
      wl_status_t st = connect_candidate(creds, candidates[i], WIFI_CONNECT_TIMEOUT_MS);
      if (st == WL_CONNECTED) {
        Serial.printf("[net] 自动连上已知网: %s IP=%s RSSI=%d\n",
                      WiFi.SSID().c_str(), WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return true;
      }
    }
    reset_sta_radio();
    delay(WIFI_CONNECT_RETRY_DELAY_MS);
  }
  return false;
}

static bool connect_submitted_and_remember(WifiCredList& creds,
                                           const String& ssid,
                                           const String& pass) {
  if (ssid.length() == 0) {
    Serial.println("[net] 门户没有提交 SSID，不写多网表");
    return false;
  }

  WifiCredList submitted;
  submitted.add(std::string(ssid.c_str()), std::string(pass.c_str()));
  Serial.printf("[net] 门户提交 WiFi: %s，开始用固件多 AP 逻辑验证连接\n", ssid.c_str());
  if (!connect_known(submitted)) {
    Serial.printf("[net] 门户提交 WiFi 连接失败: %s，不写多网表\n", ssid.c_str());
    return false;
  }

  Serial.printf("[net] 门户提交 WiFi 已连通，写入多网表: %s\n", ssid.c_str());
  remember_credential(creds, std::string(ssid.c_str()), std::string(pass.c_str()));
  return true;
}

static bool run_config_portal(WifiCredList& creds) {
  // 提交后必须退出门户，不能卡在 Saving credentials。
  // WiFiManager 只把表单写进 STA config；真正连接、验证、写表都由本文件完成。
  wm.setSaveConnect(false);
  wm.setBreakAfterConfig(true);
  wm.setPreSaveConfigCallback([]() {
    wm.stopConfigPortal();
  });
  wm.setConfigPortalTimeout(PROV_PORTAL_TIMEOUT);
  wm.setConnectTimeout(PROV_CONNECT_TIMEOUT);
  wm.setSaveConnectTimeout(1);

  bool portal_ok;
  if (PROV_AP_PASS[0] == '\0') {
    portal_ok = wm.startConfigPortal(portal_ap_name());                 // 开放热点
  } else {
    portal_ok = wm.startConfigPortal(portal_ap_name(), PROV_AP_PASS);   // 加密热点
  }

  String submitted_ssid = wm.getWiFiSSID(true);
  String submitted_pass = wm.getWiFiPass(true);
  wm.resetSettings();                      // 清 WiFiManager 临时写入的单网 NVS，只保留自建多网表

  if (!portal_ok && submitted_ssid.length() == 0) {
    Serial.println("[net] 配网门户超时/退出，未收到新 WiFi");
    return false;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[net] 门户期间已连上 %s，导入多网表\n", WiFi.SSID().c_str());
    remember_current(creds);
    start_mdns();
    return true;
  }

  if (connect_submitted_and_remember(creds, submitted_ssid, submitted_pass)) {
    start_mdns();
    return true;
  }

  return false;
}

bool net_begin() {
  configure_sta_radio();
  configure_wifi_events();
  delay(500);
  configure_portal_identity();

  WifiCredList creds = load_creds();
  Serial.printf("[net] 多网表载入 %u 条已知网\n", (unsigned)creds.count());

  // 1) 多网表非空 → 固件扫描同名 AP 并择优连接（多轮，容忍路由器刚上电/瞬时抖动）
  if (connect_known(creds)) {
    start_mdns();
    return true;
  }

  // 2) 表空 / 已知网都不可用 → 只启动配网门户。
  //    关键原则：自建多网表是唯一持久化真源；WiFiManager 只做 captive portal UI，
  //    不再用 autoConnect 读它自己的单网 NVS，避免两套存储出现“门户显示 xinqidian，
  //    多网表却还是 laofahai”的分裂状态。
  return run_config_portal(creds);
}

bool net_connected() { return WiFi.status() == WL_CONNECTED; }

const char* net_hostname() { return current_host(); }

const char* net_mac() { return current_mac(); }

void net_reset_and_reboot() {
  wm.resetSettings();   // 清 WiFiManager 自己的 wifi NVS 凭据
  clear_creds();        // 清自建多网表（记住的所有网一并清掉）
  delay(300);
  ESP.restart();        // 重启 → 下次 net_begin 无凭据 → 自动进配网门户
}

bool net_start_portal() {
  configure_portal_identity();
  WifiCredList creds = load_creds();
  return run_config_portal(creds);
}
