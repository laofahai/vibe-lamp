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

void setUp() {} void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_empty_sessions_is_idle_dark);
  RUN_TEST(test_needs_you_is_reddish);
  RUN_TEST(test_working_code_is_bluish);
  return UNITY_END();
}
