import json
import logging
import socket
import urllib.request
from urllib.parse import urlsplit, urlunsplit
from . import config

log = logging.getLogger("vibelamp.lamp")

# 灯永远在局域网（mDNS vibelamp.local / LAN IP）——绝不该走转发代理。
# urllib 默认 opener 会读 HTTP_PROXY/http_proxy/ALL_PROXY 等环境变量并代理请求；
# 用户 Mac 设了系统代理时，推灯请求会被代理劫走 → 灯收不到（与联调期 curl 的 502 同源）。
# 用「空 ProxyHandler」构造一个永不走代理的 opener，专供推灯用（空 dict 会覆盖读环境变量的默认行为）。
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# —— mDNS 主机名 → IP 解析缓存 ——
# 某些 Mac 上解析 vibelamp.local 要数秒（系统先问单播 DNS 超时、再落 mDNS）。
# 每次推送都付这个代价 → 1s 推送超时必然失败。故解析一次、按主机名缓存 IP，之后直推 IP
# （秒级）；推送失败时由 push() 失效缓存、下轮重解析——灯换 IP（DHCP）也能自动跟上。
# 名字（vibelamp.local）仍是对外的稳定地址，IP 只是内部加速缓存。
_ip_cache = {}   # hostname -> ip


def _ipify(url):
    """把 url 主机名解析成 IPv4 并替换。已是 IP 字面量 / 解析失败 → 原样返回（不抛）。"""
    parts = urlsplit(url)
    host = parts.hostname
    if not host:
        return url
    try:
        socket.inet_aton(host)
        return url                          # 已是 IPv4 字面量，免解析
    except OSError:
        pass
    ip = _ip_cache.get(host)
    if ip is None:
        try:
            # 只取 IPv4：灯是 IPv4 设备，且避开部分 Mac 上 IPv6(AAAA) 解析挂数秒的坑
            infos = socket.getaddrinfo(host, parts.port or 80,
                                       socket.AF_INET, socket.SOCK_STREAM)
            ip = infos[0][4][0]
            _ip_cache[host] = ip
        except Exception:
            return url                      # 解析不了 → 回退原 url，交给 urllib 自己试
    netloc = ip if not parts.port else "%s:%d" % (ip, parts.port)
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def _invalidate(url):
    """清掉某主机名的 IP 缓存（推送失败后调用，下次重解析以兼容灯换 IP）。"""
    host = urlsplit(url).hostname
    if host:
        _ip_cache.pop(host, None)


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
    # HTTP 主链路：解析缓存命中则直推 IP（秒级）；失败则失效缓存、重解析重试一次（兼容灯换 IP）。
    for attempt in range(2):
        req = urllib.request.Request(
            _ipify(url), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with _opener.open(req, timeout=timeout) as resp:
                if 200 <= resp.status < 300:
                    return True
        except Exception as e:
            log.debug("lamp push failed (attempt %d): %s", attempt, e)
            _invalidate(url)
    # —— WiFi 不可达：BLE 兜底（仅在启用时；默认关闭）——
    if config.BLE_FALLBACK_ENABLED:
        return _send_ble(payload)
    return False
