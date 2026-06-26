#include "wifi_cred_list.h"

namespace {
constexpr std::size_t kMaxFieldLen = 255;

void append_field(std::string& out, const std::string& field) {
  out.push_back(static_cast<char>(field.size()));
  out.append(field);
}
} // namespace

bool WifiCredList::add(const std::string& ssid, const std::string& pass) {
  if (ssid.empty() || ssid.size() > kMaxFieldLen || pass.size() > kMaxFieldLen) {
    return false;
  }

  std::size_t found = count_;
  for (std::size_t i = 0; i < count_; ++i) {
    if (entries_[i].ssid == ssid) {
      found = i;
      break;
    }
  }

  WifiCredential updated{ssid, pass};
  if (found < count_) {
    for (std::size_t i = found; i > 0; --i) {
      entries_[i] = entries_[i - 1];
    }
    entries_[0] = updated;
    return true;
  }

  std::size_t limit = count_ < kMaxEntries ? count_ : kMaxEntries - 1;
  for (std::size_t i = limit; i > 0; --i) {
    entries_[i] = entries_[i - 1];
  }
  entries_[0] = updated;
  if (count_ < kMaxEntries) {
    ++count_;
  }
  return true;
}

std::size_t WifiCredList::count() const {
  return count_;
}

const WifiCredential& WifiCredList::get(std::size_t index) const {
  return entries_[index];
}

void WifiCredList::clear() {
  for (std::size_t i = 0; i < count_; ++i) {
    entries_[i] = WifiCredential{};
  }
  count_ = 0;
}

std::string WifiCredList::serialize() const {
  std::string out;
  out.push_back(static_cast<char>(count_));
  for (std::size_t i = 0; i < count_; ++i) {
    append_field(out, entries_[i].ssid);
    append_field(out, entries_[i].pass);
  }
  return out;
}

bool WifiCredList::parse(const std::string& blob) {
  WifiCredList parsed;
  std::size_t pos = 0;
  if (blob.empty()) {
    clear();
    return true;
  }

  uint8_t n = static_cast<uint8_t>(blob[pos++]);
  if (n > kMaxEntries) {
    return false;
  }

  for (uint8_t i = 0; i < n; ++i) {
    if (pos >= blob.size()) {
      return false;
    }
    uint8_t ssid_len = static_cast<uint8_t>(blob[pos++]);
    if (pos + ssid_len > blob.size()) {
      return false;
    }
    std::string ssid = blob.substr(pos, ssid_len);
    pos += ssid_len;

    if (pos >= blob.size()) {
      return false;
    }
    uint8_t pass_len = static_cast<uint8_t>(blob[pos++]);
    if (pos + pass_len > blob.size()) {
      return false;
    }
    std::string pass = blob.substr(pos, pass_len);
    pos += pass_len;

    if (ssid.empty()) {
      return false;
    }
    parsed.entries_[parsed.count_++] = WifiCredential{ssid, pass};
  }

  if (pos != blob.size()) {
    return false;
  }

  *this = parsed;
  return true;
}
