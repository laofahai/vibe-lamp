import mimetypes
import uuid
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import config
from .lamp_client import _ipify, _opener


def update_url_from_lamp_url(lamp_url=None):
    """把 http://设备/state 转成 http://设备/update。"""
    url = lamp_url or config.LAMP_URL
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/update", "", ""))


def default_firmware_bin(env="c3_rgb"):
    root = Path(__file__).resolve().parents[2]
    return root / "firmware" / ".pio" / "build" / env / "firmware.bin"


def _multipart(field_name, file_path):
    boundary = "----vibelamp-%s" % uuid.uuid4().hex
    path = Path(file_path)
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    head = (
        "--%s\r\n"
        'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
        "Content-Type: %s\r\n\r\n"
    ) % (boundary, field_name, path.name, ctype)
    tail = "\r\n--%s--\r\n" % boundary
    data = head.encode("utf-8") + path.read_bytes() + tail.encode("utf-8")
    return boundary, data


def _post_multipart(body, boundary, url=None, timeout=60):
    target = url or update_url_from_lamp_url()
    headers = {"Content-Type": "multipart/form-data; boundary=%s" % boundary}
    req = urllib.request.Request(_ipify(target), data=body, method="POST", headers=headers)
    with _opener.open(req, timeout=timeout) as resp:
        return 200 <= resp.status < 300


def upload(file_path=None, url=None, timeout=60):
    """上传固件 bin。成功返回 True，失败返回 False，不抛给钩子链路。"""
    path = Path(file_path or default_firmware_bin())
    if not path.exists():
        raise FileNotFoundError(str(path))

    boundary, body = _multipart("firmware", path)
    return _post_multipart(body, boundary, url=url, timeout=timeout)


def upload_bytes(data, filename="firmware.bin", url=None, timeout=60):
    """从本机守护进程网页收到固件字节后，转成灯端 /update 需要的 multipart 上传。"""
    boundary = "----vibelamp-%s" % uuid.uuid4().hex
    head = (
        "--%s\r\n"
        'Content-Disposition: form-data; name="firmware"; filename="%s"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ) % (boundary, filename)
    tail = "\r\n--%s--\r\n" % boundary
    body = head.encode("utf-8") + data + tail.encode("utf-8")
    return _post_multipart(body, boundary, url=url, timeout=timeout)
