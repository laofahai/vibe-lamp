"""BLE 兜底降级的纯逻辑测试（不依赖 bleak / 不依赖真 BLE）。

只测 lamp_client.push 的降级决策：
  - HTTP push 失败 + BLE_FALLBACK_ENABLED 开 → 把同款 wire JSON 经本地 socket 投给桥接进程；
  - BLE_FALLBACK_ENABLED 关 → 老行为（不投递、返回 False）；
  - socket 投递失败 → 不抛异常、返回 False。
真正的 BLE 收发（bleak IO）靠真机验证，不在单测范围。
"""
import json
import os
import socket
import tempfile

from vibelamp import config, lamp_client


def _make_socket_path():
    return os.path.join(tempfile.mkdtemp(), "ble.sock")


def test_push_fallback_to_ble_when_http_down(monkeypatch):
    """HTTP 不可达 + 开启 BLE 兜底 → 把同款 JSON 投给桥接 socket，返回 True。"""
    sock_path = _make_socket_path()
    monkeypatch.setattr(config, "BLE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCKET", sock_path)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.settimeout(2.0)
    try:
        ok = lamp_client.push(
            {"sessions": [{"state": "needs_you"}]},
            url="http://127.0.0.1:1/state", timeout=0.3)
        assert ok is True  # BLE 兜底投递成功
        got = json.loads(srv.recv(4096).decode("utf-8"))
        assert got == {"sessions": [{"state": "needs_you"}]}  # 桥接收到同款 wire
    finally:
        srv.close()


def test_no_ble_fallback_when_disabled(monkeypatch):
    """关闭 BLE 兜底 → 维持老行为：HTTP 失败直接返回 False，不投递。"""
    sock_path = _make_socket_path()
    monkeypatch.setattr(config, "BLE_FALLBACK_ENABLED", False)
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCKET", sock_path)

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.setblocking(False)
    try:
        ok = lamp_client.push(
            {"sessions": []},
            url="http://127.0.0.1:1/state", timeout=0.3)
        assert ok is False  # 没开 BLE 兜底 → 老行为
        # 桥接 socket 不应收到任何数据
        try:
            data = srv.recv(4096)
        except BlockingIOError:
            data = None
        assert data is None
    finally:
        srv.close()


def test_ble_send_failure_does_not_raise(monkeypatch):
    """桥接 socket 不存在（无人监听）→ 投递失败也不抛异常、返回 False。"""
    # 指向一个不存在的 socket 路径：没有桥接进程在监听
    sock_path = _make_socket_path()  # 路径所在目录存在，但没有人 bind 这个 .sock
    monkeypatch.setattr(config, "BLE_FALLBACK_ENABLED", True)
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCKET", sock_path)

    ok = lamp_client.push(
        {"sessions": [{"state": "working", "tool": "code"}]},
        url="http://127.0.0.1:1/state", timeout=0.3)
    assert ok is False  # 投递失败但不抛异常


def test_send_ble_returns_true_on_success(monkeypatch):
    """直接测 _send_ble：socket 存在时返回 True 并送达。"""
    sock_path = _make_socket_path()
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCKET", sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.settimeout(2.0)
    try:
        payload = {"sessions": [{"state": "thinking"}]}
        ok = lamp_client._send_ble(payload)
        assert ok is True
        got = json.loads(srv.recv(4096).decode("utf-8"))
        assert got == payload
    finally:
        srv.close()


def test_send_ble_returns_false_when_no_listener(monkeypatch):
    """直接测 _send_ble：无人监听时吞异常、返回 False。"""
    sock_path = _make_socket_path()  # 没有人 bind
    monkeypatch.setattr(config, "BLE_BRIDGE_SOCKET", sock_path)
    ok = lamp_client._send_ble({"sessions": []})
    assert ok is False


def test_config_ble_fallback_default_disabled():
    """BLE 兜底默认必须关闭（确保现有行为不变）。"""
    # 在未设置环境变量时，模块级常量默认应为 False。
    # 这里直接断言 load_config 的默认值，避免依赖进程环境。
    cfg = config.load_config()
    assert cfg["ble_fallback_enabled"] is False


# —— BLE 桥接进程的纯逻辑（不依赖 bleak IO，可单测）——
# 仅测「socket 收到数据 → 该不该写 BLE / 怎么编码」这部分纯逻辑；
# 真正的 bleak scan/connect/write 靠真机验证，不在单测范围。

def test_bridge_should_forward_skips_empty():
    from vibelamp import ble_bridge
    assert ble_bridge.should_forward(b"") is False
    assert ble_bridge.should_forward(None) is False
    assert ble_bridge.should_forward(b'{"sessions":[]}') is True


def test_bridge_decode_payload_passthrough():
    from vibelamp import ble_bridge
    # bytes 原样透传
    assert ble_bridge.decode_payload(b'{"sessions":[]}') == b'{"sessions":[]}'
    # str 按 UTF-8 编码
    assert ble_bridge.decode_payload('{"sessions":[]}') == b'{"sessions":[]}'
