import ipaddress
import json
import re
import socket
import subprocess
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
    if not ips:
        ips.update(_ifconfig_ipv4s())
    return [ip for ip in ips if _is_scan_source_ip(ip)]


def _is_scan_source_ip(ip):
    return (
        ip
        and not ip.startswith("127.")
        and not ip.startswith("169.254.")
        and not ip.startswith("100.")
    )


def _ifconfig_ipv4s():
    """macOS 上 socket.gethostname() 经常拿不到 en0 地址；用 ifconfig 作兜底。"""
    try:
        out = subprocess.check_output(["ifconfig"], text=True, timeout=2)
    except Exception:
        return []
    ips = []
    current = ""
    for line in out.splitlines():
        if line and not line[0].isspace():
            current = line.split(":", 1)[0]
            continue
        if current.startswith(("lo", "utun", "awdl", "llw")):
            continue
        m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)\b", line)
        if m:
            ips.append(m.group(1))
    return ips


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


def _scan_once(timeout, workers):
    deadline = time.time() + timeout
    found = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_probe, ip, min(0.5, timeout)) for ip in _candidate_ips()]
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


def scan(timeout=3.0, workers=48, attempts=3):
    """扫描当前 /24 局域网，返回能响应 /health 的 Vibe Lamp 列表。

    弱信号设备会偶发丢包，导致某一轮探针超时、整轮扫空。扫到就立刻返回
    （常态只扫一轮，速度不变）；只有扫空时才自动重扫，扫满 attempts 轮为止——
    死 IP 不会被重复惩罚，掉一个包补一轮就能抓回来。
    """
    result = []
    for _ in range(max(1, attempts)):
        result = _scan_once(timeout, workers)
        if result:
            break
    return result


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
