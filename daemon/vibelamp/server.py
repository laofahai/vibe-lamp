import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import config, lamp_client
from .model import SessionStore
from .normalize import transition

log = logging.getLogger("vibelamp.server")
store = SessionStore(config.SESSION_TTL_SEC)


def handle_event(event):
    t = transition(event)
    if t is None:
        return
    sid, state, tool = t
    store.update(sid, state, tool)
    lamp_client.push(store.to_wire())


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/event":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            event = json.loads(body or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); return
        try:
            handle_event(event)
        except Exception as e:
            log.exception("handle_event failed: %s", e)   # 绝不让钩子失败
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
            lamp_client.push(store.to_wire())
        except Exception as e:
            log.debug("heartbeat error: %s", e)


def serve():
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((config.LISTEN_HOST, config.LISTEN_PORT), Handler)
    log.info("vibelamp daemon listening %s:%d -> %s",
             config.LISTEN_HOST, config.LISTEN_PORT, config.LAMP_URL)
    httpd.serve_forever()
