#include "ble_state.h"

#ifdef ENABLE_BLE
// —— 仅 -DENABLE_BLE 构建（env:esp32_ble）才编入下面整段 BLE 代码 ——
// Arduino-ESP32 core 2.0.17 自带 Bluedroid BLE 栈
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include "config.h"
#include "api_server.h"   // api_apply_state_json

// 收到 BLE 写入的状态特征值 → 复用 HTTP /state 同款解析路径
class StateCharCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* ch) override {
    std::string v = ch->getValue();              // 收到的 JSON 字符串
    api_apply_state_json(v.c_str(), v.size());   // 共用状态写入 + 看门狗刷新
  }
};

void ble_state_begin() {
  BLEDevice::init(BLE_STATE_DEVICE_NAME);
  BLEServer* server = BLEDevice::createServer();
  BLEService* svc = server->createService(BLE_STATE_SERVICE_UUID);
  BLECharacteristic* ch = svc->createCharacteristic(
      BLE_STATE_CHAR_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  ch->setCallbacks(new StateCharCallbacks());
  svc->start();

  BLEAdvertising* adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLE_STATE_SERVICE_UUID);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

#else
// 默认构建：不含任何 BLE 代码，提供空实现让 main.cpp 的调用点链接通过
void ble_state_begin() {}
#endif
