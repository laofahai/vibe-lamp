#pragma once

// BLE GATT 状态兜底服务（Part B②）。
// 仅在编译开 -DENABLE_BLE（独立 env:esp32_ble）时有实际实现；
// 默认构建（esp32 / esp32_ring）下本函数为空，链接产物不含任何 BLE 代码。
//
// 开一个「状态」可写特征值，onWrite 回调把收到的 JSON 交给
// api_apply_state_json()，与 HTTP /state 共用同一套状态写入 + 看门狗刷新。
// 这样 WiFi 断时 Mac 端经 BLE 续推就能继续驱动灯、且不会误判失联。
void ble_state_begin();
