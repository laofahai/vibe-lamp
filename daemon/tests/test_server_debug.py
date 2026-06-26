"""调试 HTTP 面板的回归测试。

覆盖：
  - 事件流环形缓冲：每条钩子事件被记录（含被忽略的事件）。
  - /api/state 载荷形状：会话快照 + 实际上灯 wire + 链路健康。
  - 手动测试覆盖：set 把灯钉在测试色、覆盖期实时状态不上灯、clear 恢复实时。
  - GET 烟雾测试：面板首页与 /api/state 经真实 HTTP 返回 200。
"""
import http.client
import json
import threading
import time

import vibelamp.server as server
from vibelamp import config
from vibelamp.model import SessionStore


def _fresh(monkeypatch):
    """全新空 store + 清空事件缓冲 + 复位测试覆盖，避免跨用例污染。"""
    store = SessionStore(config.SESSION_TTL_SEC)
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(server, "_test_override", None, raising=False)
    server._events.clear()
    return store


# ——— 事件流 ————————————————————————————————————————————

def test_event_recorded(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(server, "_push_current", lambda: None)
    server.handle_path_event(
        "/event",
        {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Edit"})
    ev = list(server._events)[-1]
    assert ev["name"] == "PreToolUse"
    assert ev["sid"] == "claude:s1"
    assert ev["result"] == "working/code"


def test_ignored_event_still_recorded(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(server, "_push_current", lambda: None)
    # 未映射事件名 → transition 返回 None → 记为 ignored（面板也要看得见）
    server.handle_path_event(
        "/event", {"hook_event_name": "SomethingUnmapped", "session_id": "s1"})
    assert list(server._events)[-1]["result"] == "ignored"


def test_remove_event_recorded(monkeypatch):
    _fresh(monkeypatch)
    monkeypatch.setattr(server, "_push_current", lambda: None)
    server.handle_path_event(
        "/event", {"hook_event_name": "SessionEnd", "session_id": "s1"})
    assert list(server._events)[-1]["result"] == "removed"


# ——— /api/state 载荷 —————————————————————————————————————

def test_state_payload_shape(monkeypatch):
    store = _fresh(monkeypatch)
    store.update("claude:x", "working", "code")
    payload = server._state_payload()
    assert payload["wire"] == {"sessions": [{"state": "working", "tool": "code"}]}
    assert any(s["sid"] == "claude:x" for s in payload["sessions"])
    assert "lamp" in payload and "override" in payload


# ——— 手动测试覆盖 ————————————————————————————————————————

def test_apply_test_override_then_clear(monkeypatch):
    store = _fresh(monkeypatch)
    pushed = []
    monkeypatch.setattr(server.lamp_client, "push",
                        lambda wire, **k: (pushed.append(wire) or True))
    # set：灯被钉在 needs_you（红）
    server._apply_test({"action": "set", "state": "needs_you", "tool": "none"})
    assert pushed[-1] == {"sessions": [{"state": "needs_you", "tool": "none"}]}
    # 覆盖期：即便真实会话在 working，_push_current 仍推 override
    store.update("claude:x", "working", "code")
    server._push_current()
    assert pushed[-1] == {"sessions": [{"state": "needs_you", "tool": "none"}]}
    # 但 /api/state 仍如实显示真实会话（面板不被测试模式蒙蔽）
    assert any(s["state"] == "working" for s in server._state_payload()["sessions"])
    # clear：恢复实时 → 推真实 wire
    server._apply_test({"action": "clear"})
    assert pushed[-1] == {"sessions": [{"state": "working", "tool": "code"}]}


def test_apply_test_off_pushes_empty(monkeypatch):
    _fresh(monkeypatch)
    pushed = []
    monkeypatch.setattr(server.lamp_client, "push",
                        lambda wire, **k: (pushed.append(wire) or True))
    server._apply_test({"action": "set", "state": "off"})
    assert pushed[-1] == {"sessions": []}


def test_apply_test_unknown_state_falls_back_off(monkeypatch):
    _fresh(monkeypatch)
    pushed = []
    monkeypatch.setattr(server.lamp_client, "push",
                        lambda wire, **k: (pushed.append(wire) or True))
    server._apply_test({"action": "set", "state": "bogus"})
    assert pushed[-1] == {"sessions": []}     # 未知态 → 灭，绝不把垃圾态推给灯


# ——— GET 烟雾测试（真实 HTTP）————————————————————————————

def test_http_get_dashboard_and_api(monkeypatch):
    monkeypatch.setattr(config, "HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr(server, "_push_current", lambda: None)   # 心跳不真联网

    t = threading.Thread(target=lambda: server.serve(port=0), daemon=True)
    t.start()
    deadline = time.time() + 3.0
    while time.time() < deadline and server._httpd is None:
        time.sleep(0.01)
    assert server._httpd is not None
    port = server._httpd.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        conn.request("GET", "/")
        r = conn.getresponse()
        assert r.status == 200
        assert b"VibeLamp" in r.read()

        conn.request("GET", "/api/state")
        r = conn.getresponse()
        assert r.status == 200
        data = json.loads(r.read())
        assert "wire" in data and "sessions" in data and "lamp" in data

        conn.request("GET", "/api/events")
        r = conn.getresponse()
        assert r.status == 200
        assert "events" in json.loads(r.read())

        conn.request("GET", "/nope")
        r = conn.getresponse()
        assert r.status == 404
        r.read()
        conn.close()
    finally:
        server._stop.set()
        server._httpd.shutdown()
        t.join(timeout=3.0)
        server._stop.clear()
