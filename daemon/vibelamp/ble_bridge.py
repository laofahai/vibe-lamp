"""Vibe Lamp BLE 桥接进程（计划 04 Part B②）。

常驻进程：握住灯的 BLE 连接，监听本地 Unix domain socket，
收守护进程经 socket 转来的 wire JSON（与 HTTP /state 同款），经 BLE 写到灯的状态特征值。
断连自动重连。仅在 WiFi 主链路不可达时由守护进程（lamp_client._send_ble）投递。

为什么需要常驻：hook 是一次性命令、push 无连接，而 BLE 是有连接、建连耗 1～3s，
无法每条状态现连现断——故由本进程握住连接，状态来了直接 write。

运行：python -m vibelamp.ble_bridge（需 `pip install bleak`，且仅 VIBELAMP_BLE=1 时安装为 LaunchAgent）。

设计：把「socket 收到数据 → 该写 BLE」的纯逻辑（should_forward / decode_payload）与
实际 bleak IO（_BleConnection、_serve）分开——纯逻辑可单测，bleak IO 靠真机验证。
"""
import asyncio
import logging
import os
import socket

from . import config

log = logging.getLogger("vibelamp.ble_bridge")


# ——— 纯逻辑（无 BLE IO，可单测）———————————————————————————————

def should_forward(data):
    """收到的 socket 数据是否值得转发给 BLE。

    空数据 / None 丢弃（守护进程偶发空报文）；非空即转发。
    不在这里解析 JSON——wire 格式由守护进程保证，桥接只做透传。
    """
    return bool(data)


def decode_payload(data):
    """把 socket 收到的 bytes 规整成将写入 BLE 特征值的 bytes。

    桥接对 payload 内容透明（与 HTTP /state 同款 JSON），原样透传即可。
    传入若是 str 则按 UTF-8 编码，便于上层/测试两用。
    """
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


# ——— BLE IO（靠真机验证，无法纯 native 单测）—————————————————————

class _BleConnection:
    """封装与灯的 BLE 连接：懒连接 + 断线重连 + 写特征。

    write() 在未连/掉线时先 scan→connect 再写；任何 BLE 异常都吞掉并标记需重连，
    与守护进程「绝不抛异常」纪律一致——桥接进程不能因一次 BLE 失败而崩。
    """

    def __init__(self):
        self._client = None
        self._client_cls = None
        self._scanner_cls = None

    def _load_bleak(self):
        """bleak 是可选依赖；只在真正跑 BLE 桥接时加载，避免纯逻辑测试被依赖卡住。"""
        if self._client_cls is None or self._scanner_cls is None:
            from bleak import BleakClient, BleakScanner
            self._client_cls = BleakClient
            self._scanner_cls = BleakScanner

    async def _ensure_connected(self):
        if self._client is not None and self._client.is_connected:
            return True
        self._load_bleak()
        # 懒连接 / 断线重连：扫到灯才连
        dev = await self._scanner_cls.find_device_by_name(
            config.BLE_DEVICE_NAME, timeout=config.BLE_SCAN_TIMEOUT_SEC)
        if dev is None:
            log.debug("ble scan: lamp %s not found", config.BLE_DEVICE_NAME)
            self._client = None
            return False
        client = self._client_cls(dev)
        try:
            await client.connect()
        except Exception as e:
            log.debug("ble connect failed: %s", e)
            self._client = None
            return False
        self._client = client
        log.info("ble connected to %s", config.BLE_DEVICE_NAME)
        return True

    async def write(self, payload):
        """把 payload（bytes）经 BLE 写到状态特征值。失败返回 False、不抛异常。"""
        if not await self._ensure_connected():
            return False
        try:
            await self._client.write_gatt_char(
                config.BLE_CHAR_UUID, payload, response=False)
            return True
        except Exception as e:
            log.debug("ble write failed: %s", e)
            self._client = None   # 写失败 → 下次重连
            return False

    async def close(self):
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None


async def _serve(sock_path):
    """监听本地 Unix socket，收 wire JSON 经 BLE 写灯。"""
    # 清理旧 socket 文件，确保父目录存在
    try:
        os.makedirs(os.path.dirname(sock_path), exist_ok=True)
    except Exception:
        pass
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass

    srv = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    srv.bind(sock_path)
    srv.setblocking(False)
    loop = asyncio.get_event_loop()
    conn = _BleConnection()

    log.info("ble bridge listening on %s -> %s", sock_path, config.BLE_DEVICE_NAME)
    try:
        while True:
            data = await loop.sock_recv(srv, 4096)
            if not should_forward(data):
                continue
            await conn.write(decode_payload(data))
    finally:
        await conn.close()
        srv.close()
        try:
            os.unlink(sock_path)
        except OSError:
            pass


def run():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_serve(config.BLE_BRIDGE_SOCKET))


if __name__ == "__main__":
    run()
