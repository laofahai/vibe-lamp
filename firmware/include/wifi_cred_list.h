#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

struct WifiCredential {
  std::string ssid;
  std::string pass;
};

class WifiCredList {
public:
  static constexpr std::size_t kMaxEntries = 5;

  bool add(const std::string& ssid, const std::string& pass);
  std::size_t count() const;
  const WifiCredential& get(std::size_t index) const;
  void clear();

  std::string serialize() const;
  bool parse(const std::string& blob);

private:
  WifiCredential entries_[kMaxEntries];
  std::size_t count_ = 0;
};
