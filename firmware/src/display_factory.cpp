// 各驱动文件用 #if DISPLAY_TYPE==... 自带 display() 定义，
// factory 仅在「无任何驱动匹配」时给出编译期报错，防止配错。
#include "config.h"

// DISPLAY_DISCRETE 已在 config.h 里定义取值，但还没有任何 .cpp 为它实现 display()。
// 若不在此拦截，编译能过、却在链接期报「undefined reference to display()」这种难懂的错。
// 这里提前给出清晰的编译期报错（不实现 DISCRETE 驱动，按 YAGNI 留待真有需求再做）。
#if DISPLAY_TYPE == DISPLAY_DISCRETE
#error "DISPLAY_DISCRETE 显示驱动尚未实现"
#endif

#if DISPLAY_TYPE != DISPLAY_RGB_LED && \
    DISPLAY_TYPE != DISPLAY_WS2812_RING && \
    DISPLAY_TYPE != DISPLAY_WS2812_STRIP && \
    DISPLAY_TYPE != DISPLAY_DISCRETE
#error "未知 DISPLAY_TYPE，请在 build_flags 里设置"
#endif
