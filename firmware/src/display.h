#pragma once
#include "render_engine.h"

class IDisplay {
public:
  virtual ~IDisplay() {}
  virtual void begin() = 0;
  virtual void show(const Rgb* pixels, uint8_t num_leds) = 0;
};

IDisplay& display();   // 由 display_factory.cpp 按 DISPLAY_TYPE 提供
