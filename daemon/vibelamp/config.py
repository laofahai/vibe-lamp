import os

# 灯的状态端点（macOS 原生解析 .local）
LAMP_URL = os.environ.get("VIBELAMP_URL", "http://vibelamp.local/state")
# 守护进程监听（钩子 curl 的目标）
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("VIBELAMP_PORT", "8787"))
# 心跳与超时
HEARTBEAT_SEC = 5.0          # 每 5s 重推（兼做灯重启自愈）
PUSH_TIMEOUT_SEC = 1.0       # 推送灯的超时
SESSION_TTL_SEC = 1800       # 30min 无活动的死会话兜底清理

from pathlib import Path

# —— BLE 兜底桥接（计划 04 Part B②，可选；默认关闭）——
# WiFi HTTP push 失败时，是否把同款 wire JSON 经本地 Unix socket 投给常驻 BLE 桥接进程。
# 默认 False —— 不启用即维持原有 WiFi-only 行为（现有测试与默认行为不变）。
BLE_FALLBACK_ENABLED = os.environ.get("VIBELAMP_BLE", "0") == "1"
# 灯的 BLE 设备名（须与固件 BLE_STATE_DEVICE_NAME 一致）
BLE_DEVICE_NAME = "VibeLamp"
# 灯的 BLE 状态服务/特征 UUID（须与固件 ble_state.* 一致）
BLE_SERVICE_UUID = "6e6c0001-b5a3-f393-e0a9-e50e24dcca9e"
BLE_CHAR_UUID = "6e6c0002-b5a3-f393-e0a9-e50e24dcca9e"
# 守护进程 → BLE 桥接进程 的本地通道（Unix domain socket 路径）
BLE_BRIDGE_SOCKET = os.environ.get(
    "VIBELAMP_BLE_SOCK",
    str(Path.home() / ".vibelamp" / "ble_bridge.sock"))
# BLE 桥接扫描灯的超时（秒）
BLE_SCAN_TIMEOUT_SEC = 8.0

# —— Codex 配置文件路径 ——
CODEX_DIR = Path.home() / ".codex"
CODEX_HOOKS_JSON = CODEX_DIR / "hooks.json"     # sidecar 纯 JSON 钩子文件
CODEX_CONFIG_TOML = CODEX_DIR / "config.toml"   # 仅追加 hooks 指针注释 + notify 一行

import json

CONFIG_PATH = Path.home() / ".vibelamp" / "config.json"

_DEFAULTS = {
    "lamp_url": LAMP_URL,
    "listen_port": LISTEN_PORT,
    "heartbeat_sec": HEARTBEAT_SEC,
    "session_ttl_sec": SESSION_TTL_SEC,
    # BLE 兜底桥接（默认关闭，确保现有 WiFi-only 行为不变）
    "ble_fallback_enabled": BLE_FALLBACK_ENABLED,
    "ble_bridge_socket": BLE_BRIDGE_SOCKET,
    "ble_device_name": BLE_DEVICE_NAME,
    # Claude 工具名 → code/command/search（覆盖计划02/03硬编码默认）
    "claude_tool_map": {
        "Edit": "code", "Write": "code", "MultiEdit": "code", "NotebookEdit": "code",
        "Bash": "command",
        "Read": "search", "Grep": "search", "Glob": "search",
        "WebSearch": "search", "WebFetch": "search", "Agent": "search", "Task": "search",
    },
}


def load_config():
    """读 ~/.vibelamp/config.json 覆盖默认；缺失/坏文件回落默认，不崩。"""
    cfg = dict(_DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text() or "{}")
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if v is not None})
    except Exception:
        pass
    return cfg
