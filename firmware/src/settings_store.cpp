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
    // 仅当存储的 blob 长度与当前结构完全一致时才读取，
    // 否则（掉电半写、结构改过）会把垃圾/部分字节灌进 s，
    // 这种情况回退到默认值，保证字段都是合法的。
    if (p.getBytesLength(KEY) == sizeof(s)) {
      size_t n = p.getBytes(KEY, &s, sizeof(s));   // 覆盖默认
      if (n != sizeof(s)) {
        s = render_default_settings();             // 实际读到的字节数不符 → 回退默认
      }
    }
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
