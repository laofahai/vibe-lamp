#pragma once
#include <stdbool.h>

// 连 WiFi：先试 NVS 里已存凭据；连不上则起 VibeLamp-Setup 配网门户。
// 配上并连上返回 true；门户超时仍未连上返回 false（loop 里照常进失联态）。
bool net_begin();

bool net_connected();

// 清除已存 WiFi 凭据（NVS）并重启进配网门户。供按钮/HTTP /reset 调用。
void net_reset_and_reboot();

// 手动起配网门户（不清旧凭据，用于运行时主动重配）。返回是否配成。
bool net_start_portal();
