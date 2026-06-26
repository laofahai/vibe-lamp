import http.client
import threading
import time

from vibelamp import ota, server, config


def test_update_url_from_lamp_url():
    assert ota.update_url_from_lamp_url("http://vibelamp-a1b2c3.local/state") \
        == "http://vibelamp-a1b2c3.local/update"


def test_dashboard_ota_endpoint_forwards_bytes(monkeypatch):
    got = {}

    def fake_upload_bytes(data, filename="firmware.bin", **_):
        got["data"] = data
        got["filename"] = filename
        return True

    monkeypatch.setattr(server.ota, "upload_bytes", fake_upload_bytes)
    monkeypatch.setattr(config, "HEARTBEAT_SEC", 0.05)
    monkeypatch.setattr(server, "_push_current", lambda: None)

    t = threading.Thread(target=lambda: server.serve(port=0), daemon=True)
    t.start()
    deadline = time.time() + 3.0
    while time.time() < deadline and server._httpd is None:
        time.sleep(0.01)
    assert server._httpd is not None
    port = server._httpd.server_address[1]
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2.0)
        conn.request("POST", "/api/ota?filename=test.bin",
                     body=b"firmware-bytes",
                     headers={"Content-Type": "application/octet-stream"})
        resp = conn.getresponse()
        assert resp.status == 200
        assert b'"ok": true' in resp.read()
        assert got == {"data": b"firmware-bytes", "filename": "test.bin"}
        conn.close()
    finally:
        server._stop.set()
        server._httpd.shutdown()
        t.join(timeout=3.0)
        server._stop.clear()
