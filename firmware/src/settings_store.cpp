#include <Preferences.h>
#include "settings_store.h"

static const char* NS = "vibelamp";
static const char* KEY = "render";
static const uint8_t VER = 1;

RenderSettings settings_load() {
  Preferences p;
  p.begin(NS, /*readOnly=*/true);
  RenderSettings s = render_default_settings();
  uint8_t ver = p.getUChar("ver", 0);
  if (ver == VER) {
    p.getBytes(KEY, &s, sizeof(s));   // 覆盖默认
  }
  p.end();
  return s;
}

void settings_save(const RenderSettings& s) {
  Preferences p;
  p.begin(NS, /*readOnly=*/false);
  p.putBytes(KEY, &s, sizeof(s));
  p.putUChar("ver", VER);
  p.end();
}
