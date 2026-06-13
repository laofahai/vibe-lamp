#include <WebServer.h>
#include <ArduinoJson.h>
#include "config.h"
#include "api_server.h"

static WebServer server(HTTP_PORT);
static Session g_sessions[NUM_LEDS > 8 ? NUM_LEDS : 8];
static uint8_t g_count = 0;
static uint32_t g_last_ms = 0;

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

static void handle_state() {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, server.arg("plain"));
  if (err) { server.send(400, "text/plain", "bad json"); return; }

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
  g_last_ms = now;
  server.send(200, "application/json", "{\"ok\":true}");
}

static void handle_health() {
  char buf[96];
  snprintf(buf, sizeof(buf), "{\"sessions\":%u,\"uptime_ms\":%lu}",
          (unsigned)g_count, (unsigned long)millis());
  server.send(200, "application/json", buf);
}

void api_begin() {
  server.on("/state", HTTP_POST, handle_state);
  server.on("/health", HTTP_GET, handle_health);
  server.begin();
}
void api_loop() { server.handleClient(); }
uint8_t api_session_count() { return g_count; }
const Session* api_sessions() { return g_sessions; }
uint32_t api_last_state_ms() { return g_last_ms; }
