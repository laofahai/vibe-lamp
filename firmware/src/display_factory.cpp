// 各驱动文件用 #if DISPLAY_TYPE==... 自带 display() 定义，
// factory 仅在「无任何驱动匹配」时给出编译期报错，防止配错。
#include "config.h"
#if DISPLAY_TYPE != DISPLAY_RGB_LED && \
    DISPLAY_TYPE != DISPLAY_WS2812_RING && \
    DISPLAY_TYPE != DISPLAY_WS2812_STRIP && \
    DISPLAY_TYPE != DISPLAY_DISCRETE
#error "未知 DISPLAY_TYPE，请在 build_flags 里设置"
#endif
