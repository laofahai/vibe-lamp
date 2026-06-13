#pragma once
#include <stdbool.h>
bool net_begin();        // 连 WiFi + 启 mDNS；成功返回 true
bool net_connected();
