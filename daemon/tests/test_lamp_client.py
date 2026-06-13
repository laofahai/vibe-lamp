import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from vibelamp import lamp_client

class _Capture(BaseHTTPRequestHandler):
    received = None
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _Capture.received = json.loads(self.rfile.read(length))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass

def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

def test_push_posts_json_and_returns_true():
    srv = _serve()
    port = srv.server_address[1]
    ok = lamp_client.push({"sessions": [{"state": "working", "tool": "code"}]},
                          url=f"http://127.0.0.1:{port}/state")
    assert ok is True
    assert _Capture.received == {"sessions": [{"state": "working", "tool": "code"}]}
    srv.shutdown()

def test_push_unreachable_returns_false_no_raise():
    # 没人监听的端口；push 必须吞掉异常、返回 False
    ok = lamp_client.push({"sessions": []},
                          url="http://127.0.0.1:1/state", timeout=0.3)
    assert ok is False
