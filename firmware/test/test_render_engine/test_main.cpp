#include <unity.h>
#include "render_engine.h"

static Rgb px;  // 单像素缓冲

static Session mk(State s, ToolKind t = ToolKind::NONE) {
  return Session{ s, t, /*state_since_ms*/0, /*pulse_at_ms*/0 };
}

void test_empty_sessions_is_idle_dark() {
  render(nullptr, 0, /*now*/0, &px, 1);
  TEST_ASSERT_EQUAL_UINT8(0, px.r);
  TEST_ASSERT_EQUAL_UINT8(0, px.g);
  TEST_ASSERT_EQUAL_UINT8(0, px.b);
}

void test_needs_you_is_reddish() {
  Session s = mk(State::NEEDS_YOU);
  render(&s, 1, /*now*/0, &px, 1);   // t=0：闪烁相位为「亮」
  TEST_ASSERT_GREATER_THAN_UINT8(100, px.r);
  TEST_ASSERT_LESS_THAN_UINT8(60, px.g);
  TEST_ASSERT_LESS_THAN_UINT8(60, px.b);
}

void test_working_code_is_bluish() {
  Session s = mk(State::WORKING, ToolKind::CODE);
  render(&s, 1, /*now*/0, &px, 1);   // t=0：呼吸相位最亮
  TEST_ASSERT_GREATER_THAN_UINT8(px.r, px.b);  // 蓝 > 红
}

// 工具函数：按相位取亮度，断言「呼吸」在波峰/波谷不同
void test_working_breathes() {
  Session s = mk(State::WORKING, ToolKind::CODE);
  s.state_since_ms = 0;
  Rgb peak, trough;
  render(&s, 1, 1000, &peak,   1);   // 半周期 → 三角波波峰（最亮，周期 2000ms）
  render(&s, 1, 0,    &trough, 1);   // 相位 0 → 三角波波谷（最暗）
  TEST_ASSERT_GREATER_THAN_UINT8(peak.b / 2, peak.b);     // 占位避免优化
  TEST_ASSERT_TRUE(trough.b < peak.b);                    // 暗于波峰
}

void test_needs_you_blinks_off() {
  Session s = mk(State::NEEDS_YOU);
  s.state_since_ms = 0;
  Rgb on, off;
  render(&s, 1, 0,   &on,  1);   // 慢闪：亮半周期
  render(&s, 1, 600, &off, 1);   // 暗半周期（周期 1200ms）
  TEST_ASSERT_GREATER_THAN_UINT8(100, on.r);
  TEST_ASSERT_LESS_THAN_UINT8(30, off.r);   // 灭
}

void test_done_fades_out() {
  Session s = mk(State::DONE);
  s.state_since_ms = 0;
  Rgb early, late;
  render(&s, 1, 0,    &early, 1);   // 刚完成：亮
  render(&s, 1, 4000, &late,  1);   // 4s 后：基本暗（渐暗窗 ~4500ms）
  TEST_ASSERT_GREATER_THAN_UINT8(100, early.g);
  TEST_ASSERT_LESS_THAN_UINT8(early.g, late.g + 1);  // late 不亮于 early
  TEST_ASSERT_LESS_THAN_UINT8(40, late.g);
}

void test_error_flashes_then_settles() {
  Session s = mk(State::ERROR);
  s.state_since_ms = 0;
  Rgb flash, after;
  render(&s, 1, 0,   &flash, 1);   // 快闪窗内：红
  render(&s, 1, 500, &after, 1);   // 快闪窗后（~300ms）：灭，等转译器推下一状态
  TEST_ASSERT_GREATER_THAN_UINT8(120, flash.r);
  TEST_ASSERT_LESS_THAN_UINT8(40, after.r);
}

void setUp() {} void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_empty_sessions_is_idle_dark);
  RUN_TEST(test_needs_you_is_reddish);
  RUN_TEST(test_working_code_is_bluish);
  RUN_TEST(test_working_breathes);
  RUN_TEST(test_needs_you_blinks_off);
  RUN_TEST(test_done_fades_out);
  RUN_TEST(test_error_flashes_then_settles);
  return UNITY_END();
}
