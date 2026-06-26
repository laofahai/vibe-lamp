#pragma once
#include <stdbool.h>

// 连 WiFi：先试 NVS 里已存凭据；连不上则起 VibeLamp-Setup 配网门户。
// 配上并连上返回 true；门户超时仍未连上返回 false（loop 里照常进失联态）。
bool net_begin();

bool net_connected();

// 当前设备的局域网主机名，如 vibelamp-a1b2c3；访问 http://<name>.local
const char* net_hostname();

// 当前设备 STA MAC 地址，如 aa:bb:cc:dd:ee:ff；用于多人局域网里识别实体设备。
const char* net_mac();

// 清除已存 WiFi 凭据（NVS）并重启进配网门户。供按钮/HTTP /reset 调用。
void net_reset_and_reboot();

// 手动起配网门户（不清旧凭据，用于运行时主动重配）。返回是否配成。
bool net_start_portal();
