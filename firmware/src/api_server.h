#pragma once
#include "render_engine.h"

void api_begin();
void api_loop();                       // 在 loop() 里调，处理请求
uint8_t api_session_count();           // 当前会话数
const Session* api_sessions();         // 当前会话数组
uint32_t api_last_state_ms();          // 最近一次收到 /state 的 millis
