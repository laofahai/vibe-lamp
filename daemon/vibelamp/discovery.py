import ipaddress
import json
import socket
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from urllib.parse import urlsplit

from . import config

_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _local_ipv4s():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(item[4][0])
    except Exception:
        pass
    return [ip for ip in ips if not ip.startswith("127.")]


def _candidate_ips():
    seen = set()
    for ip in _local_ipv4s():
        try:
            net = ipaddress.ip_network(ip + "/24", strict=False)
        except Exception:
            continue
        for host in net.hosts():
            s = str(host)
            if s not in seen:
                seen.add(s)
                yield s


def _probe(ip, timeout):
    url = "http://%s/health" % ip
    try:
        with _opener.open(url, timeout=timeout) as resp:
            if not (200 <= resp.status < 300):
                return None
            data = json.loads(resp.read().decode("utf-8") or "{}")
            host = data.get("host") or ""
            mac = data.get("mac") or ""
            if not host.startswith("vibelamp"):
                return None
            return {
                "host": host,
                "mac": mac,
                "ip": ip,
                "url": "http://%s/state" % ip,
            }
    except Exception:
        return None


def scan(timeout=3.0, workers=48):
    """扫描当前 /24 局域网，返回能响应 /health 的 Vibe Lamp 列表。"""
    deadline = time.time() + timeout
    found = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_probe, ip, min(0.35, timeout)) for ip in _candidate_ips()]
        try:
            for fut in as_completed(futs, timeout=timeout + 0.5):
                item = fut.result()
                if item:
                    found.append(item)
                if time.time() > deadline:
                    break
        except TimeoutError:
            pass
    found.sort(key=lambda x: (x.get("host") or "", x.get("ip") or ""))
    return found


def _same_lamp(item, lamp_id=None, lamp_mac=None):
    lamp_id = lamp_id or config.LAMP_ID
    lamp_mac = (lamp_mac or config.LAMP_MAC or "").lower()
    host = (item.get("host") or "").lower()
    mac = (item.get("mac") or "").lower()
    return bool((lamp_id and host == lamp_id.lower()) or (lamp_mac and mac == lamp_mac))


def bind(item):
    """把发现到的灯写入 config.json，并刷新运行期配置。"""
    cfg = config.load_config()
    cfg["lamp_id"] = item.get("host") or cfg.get("lamp_id", "")
    cfg["lamp_mac"] = item.get("mac") or cfg.get("lamp_mac", "")
    cfg["lamp_url"] = item.get("url") or cfg.get("lamp_url", "")
    config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config.CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
    config.apply_config()
    return cfg


def rebind_configured_lamp(timeout=3.0):
    """按已绑定 host/MAC 在当前局域网找回同一盏灯，找到则更新 lamp_url。"""
    if not (config.LAMP_ID or config.LAMP_MAC):
        # 兼容旧配置：lamp_url 是唯一 host 时，也可用 host 作为 lamp_id。
        host = urlsplit(config.LAMP_URL).hostname or ""
        if host.endswith(".local"):
            config.LAMP_ID = host[:-6]
    for item in scan(timeout=timeout):
        if _same_lamp(item):
            bind(item)
            return item
    return None
