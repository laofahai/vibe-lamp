#include "config.h"
#if DISPLAY_TYPE == DISPLAY_RGB_LED
#include <Arduino.h>
#include "display.h"

// 安装的 Arduino-ESP32 core 为 2.0.17（非计划假设的 3.x），
// ledc 用「通道」API：ledcSetup(ch,freq,res) + ledcAttachPin(pin,ch) + ledcWrite(ch,duty)。
// R/G/B 分别用通道 0/1/2。
#define LEDC_CH_R 0
#define LEDC_CH_G 1
#define LEDC_CH_B 2

class RgbLedDisplay : public IDisplay {
public:
  void begin() override {
    ledcSetup(LEDC_CH_R, LEDC_FREQ, LEDC_RES);
    ledcSetup(LEDC_CH_G, LEDC_FREQ, LEDC_RES);
    ledcSetup(LEDC_CH_B, LEDC_FREQ, LEDC_RES);
    ledcAttachPin(PIN_RGB_R, LEDC_CH_R);
    ledcAttachPin(PIN_RGB_G, LEDC_CH_G);
    ledcAttachPin(PIN_RGB_B, LEDC_CH_B);
  }
  void show(const Rgb* px, uint8_t /*n*/) override {
    // 共阴：duty 直接给值；亮度已在渲染层统一施加，此处不再二次缩放
    ledcWrite(LEDC_CH_R, px[0].r);
    ledcWrite(LEDC_CH_G, px[0].g);
    ledcWrite(LEDC_CH_B, px[0].b);
  }
};

static RgbLedDisplay g_display;
IDisplay& display() { return g_display; }
#endif
