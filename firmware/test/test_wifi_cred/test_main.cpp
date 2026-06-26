#include <unity.h>
#include "wifi_cred_list.h"

// 新增的 ssid 进表头（最近使用在最前），count 递增。
void test_add_new_goes_to_front() {
  WifiCredList l;
  TEST_ASSERT_TRUE(l.add("A", "pa"));
  TEST_ASSERT_TRUE(l.add("B", "pb"));
  TEST_ASSERT_EQUAL_UINT(2, (unsigned)l.count());
  TEST_ASSERT_EQUAL_STRING("B", l.get(0).ssid.c_str());   // 最近的在最前
  TEST_ASSERT_EQUAL_STRING("A", l.get(1).ssid.c_str());
}

// 已存在的 ssid：更新密码并置顶，count 不变（不重复）。
void test_add_existing_updates_and_promotes() {
  WifiCredList l;
  l.add("A", "pa"); l.add("B", "pb"); l.add("C", "pc");
  TEST_ASSERT_TRUE(l.add("A", "newpa"));                  // 已存在
  TEST_ASSERT_EQUAL_UINT(3, (unsigned)l.count());          // 数量不变
  TEST_ASSERT_EQUAL_STRING("A", l.get(0).ssid.c_str());    // 置顶
  TEST_ASSERT_EQUAL_STRING("newpa", l.get(0).pass.c_str()); // 密码已更新
}

// 超容量：淘汰最旧（队尾），count 封顶 kMaxEntries，最新在前。
void test_capacity_evicts_oldest() {
  WifiCredList l;
  l.add("A","1"); l.add("B","2"); l.add("C","3"); l.add("D","4"); l.add("E","5"); // 满 5
  TEST_ASSERT_EQUAL_UINT(5, (unsigned)l.count());
  l.add("F","6");                                          // 第 6 个 → 淘汰最旧 A
  TEST_ASSERT_EQUAL_UINT(5, (unsigned)l.count());
  TEST_ASSERT_EQUAL_STRING("F", l.get(0).ssid.c_str());    // 最新在前
  for (size_t i = 0; i < l.count(); ++i)                   // A 应已被淘汰
    TEST_ASSERT_TRUE(l.get(i).ssid != "A");
}

// 空 ssid 拒绝（密码可空，ssid 不可空）。
void test_empty_ssid_rejected() {
  WifiCredList l;
  TEST_ASSERT_FALSE(l.add("", "x"));
  TEST_ASSERT_EQUAL_UINT(0, (unsigned)l.count());
}

// 序列化 ↔ 反序列化往返无损：含空格 ssid、空密码（开放网）、顺序一致。
void test_serialize_parse_roundtrip() {
  WifiCredList l;
  l.add("Home WiFi", "p@ss 123");   // 含空格/特殊字符
  l.add("Open Net", "");            // 空密码（开放网）
  std::string blob = l.serialize();

  WifiCredList l2;
  TEST_ASSERT_TRUE(l2.parse(blob));
  TEST_ASSERT_EQUAL_UINT((unsigned)l.count(), (unsigned)l2.count());
  for (size_t i = 0; i < l.count(); ++i) {
    TEST_ASSERT_EQUAL_STRING(l.get(i).ssid.c_str(), l2.get(i).ssid.c_str());
    TEST_ASSERT_EQUAL_STRING(l.get(i).pass.c_str(), l2.get(i).pass.c_str());
  }
}

// 空 blob → 清空成空表，返回 true。
void test_parse_empty_blob_is_empty() {
  WifiCredList l;
  l.add("X", "y");
  TEST_ASSERT_TRUE(l.parse(""));
  TEST_ASSERT_EQUAL_UINT(0, (unsigned)l.count());
}

// 残缺 blob（声称 3 条却没数据）→ 拒绝，返回 false。
void test_parse_rejects_garbage() {
  WifiCredList l;
  std::string bad;
  bad.push_back((char)3);   // count=3，后面无内容
  TEST_ASSERT_FALSE(l.parse(bad));
}

void setUp() {}
void tearDown() {}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_add_new_goes_to_front);
  RUN_TEST(test_add_existing_updates_and_promotes);
  RUN_TEST(test_capacity_evicts_oldest);
  RUN_TEST(test_empty_ssid_rejected);
  RUN_TEST(test_serialize_parse_roundtrip);
  RUN_TEST(test_parse_empty_blob_is_empty);
  RUN_TEST(test_parse_rejects_garbage);
  return UNITY_END();
}
