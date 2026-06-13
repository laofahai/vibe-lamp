"""守护进程生命周期与健壮性测试。

覆盖：
  - 问题 2：心跳线程能被停止信号优雅唤醒退出；serve()/shutdown 全流程不抛异常。
  - 问题 3：Content-Length 缺失/非数字时 do_POST 不崩（不再 500/连接重置）。
  - 问题 4：未知 state 被白名单防御丢弃，不进 store、不推灯。
"""
import http.client
import threading
import time

import vibelamp.server as server
from vibelamp import config


# ——— 问题 2：优雅退出 ———————————————————————————————————————

def test_heartbeat_loop_stops_on_event(monkeypatch):
    """设置停止信号后，心跳线程应迅速退出（不再 while True 死循环）。"""
    monkeypatch.setattr(config, "HEARTBEAT_SEC", 0.05)
    # 打桩推灯，避免心跳真去联网
    monkeypatch.setattr(server, "_push_current", lambda: None)
    server._stop.clear()
    t = threading.Thread(target=server._heartbeat_loop, daemon=True)
    t.start()
    assert t.is_alive()
    server._stop.set()
    t.join(timeout=2.0)
    assert not t.is_alive()        # 停止信号让线程优雅退出
    server._stop.clear()


def test_serve_starts_and_shuts_down_cleanly(monkeypatch):
    """serve() 起服务 → 处理一次请求 → shutdown 全流程不抛异常、线程收尾。"""
    monkeypatch.setattr(config, "HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr(server, "_push_current", lambda: None)

    t = threading.Thread(target=lambda: server.serve(port=0), daemon=True)
    t.start()

    # 等服务起来（_httpd 就绪且端口已绑定）
    deadline = time.time() + 3.0
    while time.time() < deadline and server._httpd is None:
        time.sleep(0.01)
    assert server._httpd is not None
    port = server._httpd.server_address[1]

    # 发一次正常请求，确认服务真的在工作
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
    conn.request("POST", "/event",
                 body=b'{"hook_event_name":"Stop","session_id":"s1"}',
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200
    resp.read(); conn.close()

    # 触发优雅退出（模拟 SIGTERM 路径：set 停止 + shutdown）
    server._stop.set()
    server._httpd.shutdown()
    t.join(timeout=3.0)
    assert not t.is_alive()        # serve() 干净返回
    server._stop.clear()


# ——— 问题 3：Content-Length 解析健壮性 —————————————————————————

class _FakeHeaders:
    def __init__(self, value):
        self._value = value

    def get(self, name, default=None):
        if name == "Content-Length":
            return self._value
        return default


class _FakeRfile:
    def read(self, n):
        return b"{}"


class _Recorder:
    """记录 do_POST 写出的响应码，不真正起 socket。"""
    def __init__(self, cl_value):
        self.headers = _FakeHeaders(cl_value)
        self.rfile = _FakeRfile()
        self.path = "/event"
        self.status = None
        self.wrote = b""

    def send_response(self, code):
        self.status = code

    def send_header(self, *a, **k):
        pass

    def end_headers(self):
        pass

    @property
    def wfile(self):
        recorder = self

        class _W:
            def write(self, b):
                recorder.wrote = b
        return _W()


def _run_do_post(cl_value):
    """用最小桩对象跑 Handler.do_POST，避免起真服务器。"""
    rec = _Recorder(cl_value)
    server.Handler.do_POST(rec)
    return rec


def test_missing_content_length_does_not_crash():
    rec = _run_do_post(None)        # 头里没有 Content-Length
    assert rec.status == 200        # 按 0 处理，不崩


def test_non_numeric_content_length_does_not_crash():
    rec = _run_do_post("abc")       # Content-Length 非数字
    assert rec.status == 200        # 不再抛 ValueError / 500


def test_empty_content_length_does_not_crash():
    rec = _run_do_post("")          # Content-Length 空串
    assert rec.status == 200


# ——— 问题 4：未知 state 防御 ———————————————————————————————

def test_unknown_state_is_dropped(monkeypatch):
    """归一化器若产出未知 state，应被白名单防御丢弃，不进 store、不推灯。"""
    from vibelamp.model import SessionStore
    store = SessionStore(config.SESSION_TTL_SEC)
    monkeypatch.setattr(server, "store", store)
    pushed = []
    monkeypatch.setattr(server, "_push_current",
                        lambda: pushed.append(store.to_wire()))
    # 临时让 /event 路由产出一个非法 state
    monkeypatch.setitem(server._ROUTES, "/event",
                        lambda ev: ("claude:x", "bogus_state", "none"))

    ok = server.handle_path_event("/event", {"hook_event_name": "whatever"})
    assert ok is True                      # 路径有效 → 仍返回 True（不让钩子失败）
    assert "claude:x" not in store._sessions   # 未知态没进 store
    assert pushed == []                    # 没推灯


def test_known_state_still_passes(monkeypatch):
    """对照组：合法 state 正常进 store 并推灯（防御没有误伤）。"""
    from vibelamp.model import SessionStore
    store = SessionStore(config.SESSION_TTL_SEC)
    monkeypatch.setattr(server, "store", store)
    pushed = []
    monkeypatch.setattr(server, "_push_current",
                        lambda: pushed.append(store.to_wire()))
    ok = server.handle_path_event(
        "/event",
        {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Edit"})
    assert ok is True
    assert "claude:s1" in store._sessions
    assert pushed[-1] == {"sessions": [{"state": "working", "tool": "code"}]}
