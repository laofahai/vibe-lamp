#include <WebServer.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <Update.h>
#include "config.h"
#include "api_server.h"
#include "render_engine.h"
#include "settings_store.h"
#include "net.h"

static WebServer server(HTTP_PORT);
static Session g_sessions[NUM_LEDS > 8 ? NUM_LEDS : 8];
static uint8_t g_count = 0;
static uint32_t g_last_ms = 0;
static bool g_ota_ok = false;

static State parse_state(const char* s) {
  if (!s) return State::IDLE;
  if (!strcmp(s, "working"))   return State::WORKING;
  if (!strcmp(s, "done"))      return State::DONE;
  if (!strcmp(s, "needs_you")) return State::NEEDS_YOU;
  if (!strcmp(s, "error"))     return State::ERROR;
  if (!strcmp(s, "lost"))      return State::LOST;
  if (!strcmp(s, "boot"))      return State::BOOT;
  return State::IDLE;
}
static ToolKind parse_tool(const char* t) {
  if (!t) return ToolKind::NONE;
  if (!strcmp(t, "code"))    return ToolKind::CODE;
  if (!strcmp(t, "command")) return ToolKind::COMMAND;
  if (!strcmp(t, "search"))  return ToolKind::SEARCH;
  return ToolKind::NONE;
}

// 解析 /state 同款 JSON → 写入会话表 + 刷新看门狗。HTTP 与 BLE 共用此函数。
bool api_apply_state_json(const char* json, size_t len) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, json, len);
  if (err) return false;

  JsonArray arr = doc["sessions"].as<JsonArray>();
  uint8_t cap = sizeof(g_sessions) / sizeof(g_sessions[0]);
  uint8_t n = 0;
  uint32_t now = millis();
  for (JsonObject o : arr) {
    if (n >= cap) break;
    State st = parse_state(o["state"]);
    ToolKind tk = parse_tool(o["tool"]);
    // 状态没变就保留 state_since_ms，让动画相位连续；变了才重置
    if (n < g_count && g_sessions[n].state == st && g_sessions[n].tool == tk) {
      // 保留 state_since_ms
    } else {
      g_sessions[n].state_since_ms = now;
    }
    g_sessions[n].state = st;
    g_sessions[n].tool = tk;
    g_sessions[n].pulse_at_ms = 0;
    ++n;
  }
  g_count = n;
  g_last_ms = now;          // 重置看门狗：BLE 收到也算「有人在喂」
  return true;
}

static void handle_state() {
  String body = server.arg("plain");
  if (api_apply_state_json(body.c_str(), body.length()))
    server.send(200, "application/json", "{\"ok\":true}");
  else
    server.send(400, "text/plain", "bad json");
}

static void handle_health() {
  char buf[256];
  snprintf(buf, sizeof(buf),
          "{\"sessions\":%u,\"uptime_ms\":%lu,\"host\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\"}",
          (unsigned)g_count, (unsigned long)millis(),
          net_hostname(), net_mac(), WiFi.localIP().toString().c_str());
  server.send(200, "application/json", buf);
}

// —— 设置页：颜色用 #rrggbb，前端取色器直接对接 ——
static String hex(Rgb c) {
  char b[8]; snprintf(b, sizeof(b), "#%02x%02x%02x", c.r, c.g, c.b); return String(b);
}
static Rgb unhex(const String& s) {     // "#rrggbb" → Rgb
  long v = strtol(s.c_str() + (s.startsWith("#") ? 1 : 0), nullptr, 16);
  return Rgb{ (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)(v) };
}

static void handle_get_settings() {
  RenderSettings s = render_get_settings();
  JsonDocument d;
  d["brightness"] = s.brightness;
  d["animations"] = s.animations;
  d["speed_pct"] = s.speed_pct;
  d["working_code"]    = hex(s.col_working_code);
  d["working_command"] = hex(s.col_working_command);
  d["working_search"]  = hex(s.col_working_search);
  d["done"]      = hex(s.col_done);
  d["needs_you"] = hex(s.col_needs_you);
  d["error"]     = hex(s.col_error);
  d["lost"]      = hex(s.col_lost);
  d["boot"]      = hex(s.col_boot);
  String out; serializeJson(d, out);
  server.send(200, "application/json", out);
}

static void handle_post_settings() {
  JsonDocument d;
  if (deserializeJson(d, server.arg("plain"))) {
    server.send(400, "text/plain", "bad json"); return;
  }
  RenderSettings s = render_get_settings();
  if (d["brightness"].is<int>()) s.brightness = (uint8_t)d["brightness"].as<int>();
  if (d["animations"].is<bool>()) s.animations = d["animations"].as<bool>();
  if (d["speed_pct"].is<int>()) {
    int sp = d["speed_pct"].as<int>();
    s.speed_pct = (uint8_t)(sp > 255 ? 255 : (sp < 1 ? 1 : sp));   // 钳到 1..255，防 uint8_t 回绕
  }
  if (d["working_code"].is<const char*>())    s.col_working_code = unhex(d["working_code"].as<String>());
  if (d["working_command"].is<const char*>()) s.col_working_command = unhex(d["working_command"].as<String>());
  if (d["working_search"].is<const char*>())  s.col_working_search = unhex(d["working_search"].as<String>());
  if (d["done"].is<const char*>())      s.col_done = unhex(d["done"].as<String>());
  if (d["needs_you"].is<const char*>()) s.col_needs_you = unhex(d["needs_you"].as<String>());
  if (d["error"].is<const char*>())     s.col_error = unhex(d["error"].as<String>());
  if (d["lost"].is<const char*>())      s.col_lost = unhex(d["lost"].as<String>());
  if (d["boot"].is<const char*>())      s.col_boot = unhex(d["boot"].as<String>());
  render_set_settings(s);     // 即时生效
  settings_save(s);           // 落 NVS
  server.send(200, "application/json", "{\"ok\":true}");
}

static const char SETTINGS_HTML[] PROGMEM = R"HTML(
<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Vibe Lamp 设置</title><style>body{font-family:sans-serif;max-width:420px;margin:20px auto;padding:0 12px}
label{display:flex;justify-content:space-between;align-items:center;margin:10px 0}input[type=color]{width:48px}
button{width:100%;padding:12px;margin-top:16px;font-size:16px}</style></head><body>
<h2>Vibe Lamp 设置</h2>
<label>亮度 <input id=brightness type=range min=0 max=255></label>
<label>动画 <input id=animations type=checkbox></label>
<label>动画速度% <input id=speed_pct type=number min=20 max=255></label>
<label>干活·写码 <input id=working_code type=color></label>
<label>干活·命令 <input id=working_command type=color></label>
<label>干活·搜索 <input id=working_search type=color></label>
<label>完成 <input id=done type=color></label>
<label>要介入 <input id=needs_you type=color></label>
<label>出错 <input id=error type=color></label>
<label>失联 <input id=lost type=color></label>
<label>开机 <input id=boot type=color></label>
<button onclick=save()>保存</button>
<p id=msg></p>
<script>
const ids=['brightness','animations','speed_pct','working_code','working_command','working_search','done','needs_you','error','lost','boot'];
fetch('/settings').then(r=>r.json()).then(s=>{for(const k of ids){const e=document.getElementById(k);
 if(e.type==='checkbox')e.checked=s[k];else e.value=s[k];}});
function save(){const b={};for(const k of ids){const e=document.getElementById(k);
 b[k]=e.type==='checkbox'?e.checked:(e.type==='color'?e.value:Number(e.value));}
 fetch('/settings',{method:'POST',body:JSON.stringify(b)}).then(r=>r.json())
 .then(()=>document.getElementById('msg').textContent='已保存 ✓');}
</script></body></html>
)HTML";

static void handle_root() {
  server.send_P(200, "text/html", SETTINGS_HTML);
}

static void handle_update_done() {
  if (g_ota_ok) {
    server.send(200, "text/html", "<!doctype html><meta charset=utf-8><p>固件升级成功，正在重启...</p>");
    delay(300);
    ESP.restart();
  } else {
    String msg = "<!doctype html><meta charset=utf-8><p>固件升级失败：";
    msg += Update.errorString();
    msg += "</p><p><a href=/update>返回重试</a></p>";
    server.send(500, "text/html", msg);
  }
}

static void handle_update_upload() {
  HTTPUpload& upload = server.upload();

  if (upload.status == UPLOAD_FILE_START) {
    g_ota_ok = false;

    Serial.printf("[ota] 开始升级: %s\n", upload.filename.c_str());
    uint32_t max_space = (ESP.getFreeSketchSpace() - 0x1000) & 0xFFFFF000;
    if (!Update.begin(max_space, U_FLASH)) {
      Serial.printf("[ota] begin 失败: %s\n", Update.errorString());
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (Update.hasError()) return;
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Serial.printf("[ota] write 失败: %s\n", Update.errorString());
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    if (Update.hasError()) return;
    g_ota_ok = Update.end(true);
    if (g_ota_ok) {
      Serial.printf("[ota] 升级成功，写入 %u 字节\n", upload.totalSize);
    } else {
      Serial.printf("[ota] end 失败: %s\n", Update.errorString());
    }
  } else if (upload.status == UPLOAD_FILE_ABORTED) {
    Update.abort();
    Serial.println("[ota] 上传中止");
  }
}

// —— 软件触发重配网：清 NVS 凭据后重启进配网门户 ——
static void handle_reset() {
  server.send(200, "text/plain", "resetting wifi, rebooting into setup portal");
  delay(200);
  net_reset_and_reboot();    // 来自 net.h
}

void api_begin() {
  server.on("/", HTTP_GET, handle_root);
  server.on("/settings", HTTP_GET, handle_get_settings);
  server.on("/settings", HTTP_POST, handle_post_settings);
  server.on("/state", HTTP_POST, handle_state);
  server.on("/health", HTTP_GET, handle_health);
  server.on("/update", HTTP_POST, handle_update_done, handle_update_upload);
  server.on("/reset", HTTP_POST, handle_reset);   // POST，避免 <img src> 等 CSRF 误触清网
  server.begin();
}
void api_loop() { server.handleClient(); }
uint8_t api_session_count() { return g_count; }
const Session* api_sessions() { return g_sessions; }
uint32_t api_last_state_ms() { return g_last_ms; }
