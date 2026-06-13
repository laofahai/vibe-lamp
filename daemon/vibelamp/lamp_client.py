import json
import logging
import urllib.request
from . import config

log = logging.getLogger("vibelamp.lamp")


def push(payload, url=None, timeout=None):
    """POST payload 到灯。绝不抛异常——失败返回 False。"""
    url = url or config.LAMP_URL
    timeout = timeout or config.PUSH_TIMEOUT_SEC
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        log.debug("lamp push failed: %s", e)
        return False
