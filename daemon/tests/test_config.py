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
