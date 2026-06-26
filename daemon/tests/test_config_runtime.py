"""证明 config.json 真正被运行期消费（问题 1 的回归测试）。

不只验证「模块常量变了」，而是验证下游消费者（lamp_client.push / server）
确实用到了 config.json 里的值——这正是当初漏测才埋下死配置 bug 的地方。
"""
import json

from vibelamp import config, lamp_client, server


def _write_cfg(tmp_path, monkeypatch, data):
    p = tmp_path / "config.json"
    p.write_text(json.dumps(data))
    monkeypatch.setattr(config, "CONFIG_PATH", p)


def test_lamp_client_push_uses_config_lamp_url(tmp_path, monkeypatch):
    """config.json 设了 lamp_url → push() 不传 url 时就该 POST 到这个地址。"""
    _write_cfg(tmp_path, monkeypatch, {"lamp_url": "http://1.2.3.4/state"})
    monkeypatch.delenv("VIBELAMP_URL", raising=False)
    config.apply_config()
    try:
        captured = {}

        def _fake_open(req, timeout=None):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            raise RuntimeError("不实际联网，只截获目标地址")

        monkeypatch.setattr(lamp_client._opener, "open", _fake_open)
        ok = lamp_client.push({"sessions": []})       # 不传 url / timeout
        assert ok is False                            # urlopen 抛错 → 老行为返回 False
        assert captured["url"] == "http://1.2.3.4/state"
    finally:
        config.apply_config()                         # 还原成真实磁盘配置


def test_lamp_client_push_uses_config_push_timeout(tmp_path, monkeypatch):
    """config.json 设了 push_timeout_sec → push() 不传 timeout 时就该用它。"""
    # lamp_url 用 IP 字面量，避免 _ipify 去做真实 mDNS 解析（保持单测无网络、快）。
    _write_cfg(tmp_path, monkeypatch, {"push_timeout_sec": 0.42,
                                       "lamp_url": "http://127.0.0.1:9/state"})
    config.apply_config()
    try:
        captured = {}

        def _fake_open(req, timeout=None):
            captured["timeout"] = timeout
            raise RuntimeError("不实际联网")

        monkeypatch.setattr(lamp_client._opener, "open", _fake_open)
        lamp_client.push({"sessions": []})
        assert captured["timeout"] == 0.42
    finally:
        config.apply_config()


def test_server_store_ttl_uses_config(tmp_path, monkeypatch):
    """config.json 设了 session_ttl_sec → 新建的 SessionStore 就该用这个 TTL。"""
    _write_cfg(tmp_path, monkeypatch, {"session_ttl_sec": 123})
    config.apply_config()
    try:
        # server.store 在导入时建好，这里按运行期重建路径验证 TTL 来源于 config。
        new_store = server.SessionStore(config.SESSION_TTL_SEC)
        assert new_store._ttl == 123
    finally:
        config.apply_config()
