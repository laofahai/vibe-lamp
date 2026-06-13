#include <Arduino.h>
#include "config.h"

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.printf("VibeLamp boot. DISPLAY_TYPE=%d NUM_LEDS=%d\n", DISPLAY_TYPE, NUM_LEDS);
}

void loop() {
  delay(1000);
}
