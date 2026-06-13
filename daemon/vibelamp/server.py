import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import config, lamp_client
from .model import SessionStore
from .normalize import transition, codex_transition

log = logging.getLogger("vibelamp.server")
store = SessionStore(config.SESSION_TTL_SEC)

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
    store.update(sid, state, tool)
    _push_current()
    return True


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
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
    while True:
        time.sleep(config.HEARTBEAT_SEC)
        try:
            store.sweep()
            _push_current()
        except Exception as e:
            log.debug("heartbeat error: %s", e)


def serve():
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((config.LISTEN_HOST, config.LISTEN_PORT), Handler)
    log.info("vibelamp daemon listening %s:%d -> %s",
             config.LISTEN_HOST, config.LISTEN_PORT, config.LAMP_URL)
    httpd.serve_forever()
