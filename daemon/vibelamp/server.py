import json
import logging
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import config, lamp_client
from .model import SessionStore, REMOVE
from .normalize import transition, codex_transition

log = logging.getLogger("vibelamp.server")
store = SessionStore(config.SESSION_TTL_SEC)

# 心跳线程停止信号：set() 后线程在下一轮醒来时优雅退出。
_stop = threading.Event()

# 已知合法状态白名单（normalize 只应产出这些；外加 model.REMOVE 走删除分支）。
# 防御层：未知 state 丢弃并告警，避免坏数据进入 store 推给灯。
_KNOWN_STATES = {"idle", "working", "done", "error", "needs_you"}

# path → 归一化器
_ROUTES = {
    "/event": transition,
    "/event/codex": codex_transition,
}


def _push_current():
    lamp_client.push(store.to_wire())


def handle_path_event(path, event):
    """按端点路由到对应归一化器。未知路径返回 False。"""
    normalize_fn = _ROUTES.get(path)
    if normalize_fn is None:
        return False
    t = normalize_fn(event)
    if t is None:
        return True       # 路径有效但事件被忽略
    sid, state, tool = t
    # 未知 state 防御：只放行白名单状态与删除信号，其余丢弃并告警。
    if state != REMOVE and state not in _KNOWN_STATES:
        log.warning("丢弃未知状态 %r（会话 %s）", state, sid)
        return True       # 路径/事件有效，仅该状态不可信 → 忽略
    store.update(sid, state, tool)
    _push_current()
    return True


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        # Content-Length 缺失/非数字时按 0 处理，绝不让钩子收到连接重置/500。
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length < 0:
                length = 0
        except (TypeError, ValueError):
            length = 0
        body = self.rfile.read(length) if length else b"{}"
        try:
            event = json.loads(body or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); return
        try:
            ok = handle_path_event(self.path, event)
        except Exception as e:
            log.exception("handle_path_event failed: %s", e)   # 绝不让钩子失败
            ok = True
        if not ok:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


def _heartbeat_loop():
    """每 HEARTBEAT_SEC 清扫死会话并重推；收到停止信号即优雅退出。"""
    # 用 Event.wait 替代 time.sleep：停止信号一到立即返回，不必等满一个周期。
    while not _stop.wait(config.HEARTBEAT_SEC):
        try:
            store.sweep()
            _push_current()
        except Exception as e:
            log.debug("heartbeat error: %s", e)


# 当前活动的 HTTP 服务实例（便于信号处理与测试驱动 shutdown）。
_httpd = None


def serve(port=None):
    """启动守护进程：心跳线程 + HTTP 服务，并装好优雅退出。

    port 默认取 config.LISTEN_PORT；测试可传 0 让系统分配空闲端口。
    """
    global _httpd
    _stop.clear()
    hb = threading.Thread(target=_heartbeat_loop, daemon=True)
    hb.start()
    listen_port = config.LISTEN_PORT if port is None else port
    httpd = ThreadingHTTPServer((config.LISTEN_HOST, listen_port), Handler)
    _httpd = httpd

    def _graceful_shutdown(signum, _frame):
        log.info("收到信号 %s，正在优雅退出守护进程……", signum)
        _stop.set()                 # 通知心跳线程退出
        # shutdown() 须在另一线程调用（不能在 serve_forever 所在线程里调）。
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    # 注册 launchd SIGTERM 与 Ctrl-C SIGINT；非主线程注册会抛 ValueError，吞掉即可。
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _graceful_shutdown)
        except (ValueError, OSError):
            pass

    log.info("vibelamp daemon listening %s:%d -> %s",
             config.LISTEN_HOST, httpd.server_address[1], config.LAMP_URL)
    try:
        httpd.serve_forever()
    finally:
        _stop.set()                 # 兜底：任何退出路径都让心跳线程收手
        httpd.server_close()        # 释放监听 socket
        hb.join(timeout=config.HEARTBEAT_SEC + 1.0)
        _httpd = None
        log.info("vibelamp daemon 已停止")
