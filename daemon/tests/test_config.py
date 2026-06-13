import json
from vibelamp import config

def test_defaults_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nope.json")
    c = config.load_config()
    assert c["lamp_url"].startswith("http://")
    assert c["session_ttl_sec"] == 1800
    assert "claude_tool_map" in c

def test_file_overrides_defaults(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"session_ttl_sec": 60,
                             "lamp_url": "http://1.2.3.4/state"}))
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    c = config.load_config()
    assert c["session_ttl_sec"] == 60
    assert c["lamp_url"] == "http://1.2.3.4/state"
    assert c["heartbeat_sec"] == 5.0          # 未覆盖项仍取默认

def test_bad_json_falls_back_to_defaults(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text("{ not json")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    c = config.load_config()
    assert c["session_ttl_sec"] == 1800       # 坏文件不崩，回落默认


def test_env_overrides_file(tmp_path, monkeypatch):
    # 环境变量优先级最高：即便 config.json 写了 lamp_url，环境变量仍应胜出。
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"lamp_url": "http://file.example/state"}))
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    monkeypatch.setenv("VIBELAMP_URL", "http://env.example/state")
    c = config.load_config()
    assert c["lamp_url"] == "http://env.example/state"


def test_env_bad_value_ignored(tmp_path, monkeypatch):
    # 环境变量值解析失败（端口非数字）→ 忽略，回落 config.json / 默认值，不崩。
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"listen_port": 9999}))
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    monkeypatch.setenv("VIBELAMP_PORT", "not-a-number")
    c = config.load_config()
    assert c["listen_port"] == 9999


def test_apply_config_backfills_module_constants(tmp_path, monkeypatch):
    """证明 config.json 的值真正进入运行期：apply_config() 后模块级常量随之改变。

    这正是当初没测到才埋下的 bug —— 运行期读的是模块级常量，
    它们必须由 config.json 经 apply_config() 回填，而非固定写死。
    """
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "session_ttl_sec": 77,
        "lamp_url": "http://9.9.9.9/state",
        "heartbeat_sec": 2.5,
        "push_timeout_sec": 0.5,
    }))
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    # 测试结束后把模块常量恢复成真实磁盘配置，避免污染其它用例。
    monkeypatch.delenv("VIBELAMP_URL", raising=False)
    monkeypatch.setattr(config, "SESSION_TTL_SEC", config.SESSION_TTL_SEC)
    monkeypatch.setattr(config, "LAMP_URL", config.LAMP_URL)
    monkeypatch.setattr(config, "HEARTBEAT_SEC", config.HEARTBEAT_SEC)
    monkeypatch.setattr(config, "PUSH_TIMEOUT_SEC", config.PUSH_TIMEOUT_SEC)

    config.apply_config()
    try:
        assert config.SESSION_TTL_SEC == 77
        assert config.LAMP_URL == "http://9.9.9.9/state"
        assert config.HEARTBEAT_SEC == 2.5
        assert config.PUSH_TIMEOUT_SEC == 0.5
    finally:
        # monkeypatch 会自动还原 CONFIG_PATH 与上面四个常量属性；
        # 再 apply 一次让常量与还原后的 CONFIG_PATH（真实磁盘）一致。
        config.apply_config()
