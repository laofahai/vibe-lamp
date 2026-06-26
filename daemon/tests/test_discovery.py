import json

from vibelamp import config, discovery


def test_probe_accepts_vibelamp_health(monkeypatch):
    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self):
            return json.dumps({"host": "vibelamp-ab7834", "mac": "90:70:69:ab:78:34"}).encode()

    monkeypatch.setattr(discovery._opener, "open", lambda url, timeout=None: Resp())
    assert discovery._probe("192.168.1.23", 0.1) == {
        "host": "vibelamp-ab7834",
        "mac": "90:70:69:ab:78:34",
        "ip": "192.168.1.23",
        "url": "http://192.168.1.23/state",
    }


def test_bind_writes_identity_and_url(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    item = {"host": "vibelamp-ab7834", "mac": "90:70:69:ab:78:34",
            "ip": "192.168.1.23", "url": "http://192.168.1.23/state"}
    cfg = discovery.bind(item)
    assert cfg["lamp_id"] == "vibelamp-ab7834"
    assert cfg["lamp_mac"] == "90:70:69:ab:78:34"
    assert cfg["lamp_url"] == "http://192.168.1.23/state"
