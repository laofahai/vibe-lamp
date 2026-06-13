#pragma once
#include <stddef.h>
#include "render_engine.h"

void api_begin();
void api_loop();                       // 在 loop() 里调，处理请求
uint8_t api_session_count();           // 当前会话数
const Session* api_sessions();         // 当前会话数组
uint32_t api_last_state_ms();          // 最近一次收到 /state 的 millis

// 把一段 /state 同款 JSON 应用到会话表（HTTP 与 BLE 共用同一套状态写入）。
// 返回 true=解析成功。内部会重置看门狗计时（g_last_ms = millis()），
// 这样 BLE 续推也算「有人在喂」，WiFi 断时不会误判失联。
bool api_apply_state_json(const char* json, size_t len);
