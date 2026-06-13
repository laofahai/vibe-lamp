#include "config.h"
#if DISPLAY_TYPE == DISPLAY_WS2812_RING || DISPLAY_TYPE == DISPLAY_WS2812_STRIP
#include <FastLED.h>
#include "display.h"

static CRGB g_leds[NUM_LEDS];

class Ws2812Display : public IDisplay {
public:
  void begin() override {
    FastLED.addLeds<WS2812B, PIN_WS2812, GRB>(g_leds, NUM_LEDS);
    FastLED.setBrightness(MAX_BRIGHTNESS);
  }
  void show(const Rgb* px, uint8_t n) override {
    for (uint8_t i = 0; i < n; ++i) g_leds[i] = CRGB(px[i].r, px[i].g, px[i].b);
    FastLED.show();
  }
};

static Ws2812Display g_display;
IDisplay& display() { return g_display; }
#endif
