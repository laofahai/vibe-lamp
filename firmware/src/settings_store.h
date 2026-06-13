#pragma once
#include "render_engine.h"

// 从 NVS 读设置（无则返回默认）；写设置到 NVS。
RenderSettings settings_load();
void settings_save(const RenderSettings& s);
