import json
import logging
import socket
import urllib.request
from . import config

log = logging.getLogger("vibelamp.lamp")


def _send_ble(payload):
    """把 wire JSON 经本地 Unix socket 交给常驻 BLE 桥接进程。

    fire-and-forget：投递成功返回 True，失败（无人监听/路径不存在等）返回 False。
    绝不抛异常——与 push「绝不让钩子失败」纪律一致。真正的 BLE 写在桥接进程里异步发生。
    """
    s = None
    try:
        data = json.dumps(payload).encode("utf-8")
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(data, config.BLE_BRIDGE_SOCKET)
        return True
    except Exception as e:
        log.debug("ble bridge send failed: %s", e)
        return False
    finally:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass


def push(payload, url=None, timeout=None):
    """POST payload 到灯。绝不抛异常——失败返回 False。

    WiFi HTTP 主链路失败时，若开启 BLE 兜底（config.BLE_FALLBACK_ENABLED），
    把同一份 wire JSON 经本地 socket 投给 BLE 桥接进程（投递成功返回 True）。
    BLE 兜底默认关闭——关闭时维持原有 WiFi-only 行为（HTTP 失败直接返回 False）。
    """
    url = url or config.LAMP_URL
    timeout = timeout or config.PUSH_TIMEOUT_SEC
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= resp.status < 300:
                return True
    except Exception as e:
        log.debug("lamp push failed: %s", e)
    # —— WiFi 不可达：BLE 兜底（仅在启用时；默认关闭）——
    if config.BLE_FALLBACK_ENABLED:
        return _send_ble(payload)
    return False
