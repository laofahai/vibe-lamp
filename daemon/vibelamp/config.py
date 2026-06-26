"""守护进程配置。

取值优先级（高 → 低）：**环境变量 > ~/.vibelamp/config.json > 内置默认值**。

运行期可配字段（灯地址、推送超时、心跳间隔、会话超时、BLE 兜底等）统一经
`load_config()` 解析，再回填为模块级常量供各模块读取。守护进程长跑，config.json
改动需重启守护进程生效（不做热重载，符合 HARDWARE.md 的「编辑后重启生效」约定）。

环境变量保留覆盖能力：即便 config.json 写了某字段，设了对应环境变量仍以环境变量为准。

注意：监听端口（LISTEN_PORT）不在可配字段内——它是 daemon 绑定口与 install.py 写入
钩子 curl 的固定契约，改它会让二者漂移、状态再也送不到灯。需自定端口时用 serve(port=)。
"""
import json
import os
from pathlib import Path

# —— 固定（非运行期可配）——
# 守护进程监听地址（钩子 curl 的目标，固定回环）
LISTEN_HOST = "127.0.0.1"
# 守护进程监听端口：daemon 绑定口 == install.py 写入钩子 curl 的端口，是二者之间的固定
# 契约。故意不走 config.json/环境变量——改它会让钩子 URL 与绑定口漂移、状态送不到灯。
# 测试需自定端口时用 server.serve(port=...) 显式传入。
LISTEN_PORT = 8787

# —— Codex 配置文件路径 ——
CODEX_DIR = Path.home() / ".codex"
CODEX_HOOKS_JSON = CODEX_DIR / "hooks.json"     # sidecar 纯 JSON 钩子文件
CODEX_CONFIG_TOML = CODEX_DIR / "config.toml"   # 仅追加 hooks 指针注释 + notify 一行

# 灯的 BLE 状态服务/特征 UUID（须与固件 ble_state.* 一致；属硬件契约，不走 config.json）
BLE_SERVICE_UUID = "6e6c0001-b5a3-f393-e0a9-e50e24dcca9e"
BLE_CHAR_UUID = "6e6c0002-b5a3-f393-e0a9-e50e24dcca9e"
# BLE 桥接扫描灯的超时（秒）
BLE_SCAN_TIMEOUT_SEC = 8.0

CONFIG_PATH = Path.home() / ".vibelamp" / "config.json"

# —— 内置默认值（纯默认，不含环境变量）——
# config.json 缺失/缺项时回落到这里；install.py 也据此生成默认配置文件。
_DEFAULTS = {
    # 灯的状态端点（macOS 原生解析 .local）
    "lamp_url": "http://vibelamp.local/state",
    # 心跳间隔（秒）：每 5s 重推（兼做灯重启自愈）
    "heartbeat_sec": 5.0,
    # 推送灯的超时（秒）
    "push_timeout_sec": 1.0,
    # 无活动多久算死会话（秒）：30min 兜底清理
    "session_ttl_sec": 1800,
    # working 但多久没新事件就降级为 idle（秒）：ESC/kill 不发 Stop 钩子 → 会话卡在
    # working、灯卡蓝；此兜底让灯自愈。取值须 > 最长单次工具调用（长构建/测试），否则
    # 长任务静默期会被误判空闲、先灭一下再亮（PostToolUse 到达时重新点亮）。
    "working_idle_timeout_sec": 180,
    # BLE 兜底桥接（默认关闭，确保现有 WiFi-only 行为不变）
    "ble_fallback_enabled": False,
    # 守护进程 → BLE 桥接进程 的本地通道（Unix domain socket 路径）
    "ble_bridge_socket": str(Path.home() / ".vibelamp" / "ble_bridge.sock"),
    # 灯的 BLE 设备名（须与固件 BLE_STATE_DEVICE_NAME 一致）
    "ble_device_name": "VibeLamp",
    # Claude 工具名 → code/command/search（覆盖计划02/03硬编码默认）
    "claude_tool_map": {
        "Edit": "code", "Write": "code", "MultiEdit": "code", "NotebookEdit": "code",
        "Bash": "command",
        "Read": "search", "Grep": "search", "Glob": "search",
        "WebSearch": "search", "WebFetch": "search", "Agent": "search", "Task": "search",
    },
}

# —— 环境变量覆盖映射 ——
# 键 = config.json/默认值 字段名；值 = (环境变量名, 解析函数)。
# 设了环境变量则以其为准（优先级最高），未设则用 config.json / 默认值。
def _as_bool(v):
    return str(v).strip() == "1"


_ENV_OVERRIDES = {
    "lamp_url": ("VIBELAMP_URL", str),
    "ble_fallback_enabled": ("VIBELAMP_BLE", _as_bool),
    "ble_bridge_socket": ("VIBELAMP_BLE_SOCK", str),
}


def _apply_env_overrides(cfg):
    """把已生效的环境变量覆盖进 cfg（环境变量优先级最高）。坏值忽略、不崩。"""
    for key, (env_name, parse) in _ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None:
            continue
        try:
            cfg[key] = parse(raw)
        except Exception:
            pass        # 环境变量值解析失败 → 忽略，保留 file/默认值
    return cfg


def load_config():
    """解析最终配置：内置默认 ← config.json ← 环境变量（环境变量优先）。

    缺失/坏文件回落默认，不崩。每次调用都重读 CONFIG_PATH（守护进程在启动时经
    apply_config() 读一次并缓存到模块级常量，运行期不反复调用此函数）。
    """
    cfg = dict(_DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            user = json.loads(CONFIG_PATH.read_text() or "{}")
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if v is not None})
    except Exception:
        pass
    _apply_env_overrides(cfg)
    return cfg


def apply_config():
    """重新解析配置并回填模块级常量，供运行期各模块读取。

    模块导入时调用一次（见文件末尾）；改了 CONFIG_PATH / 环境变量后可再调以刷新
    （主要给测试与显式刷新用）。返回最新的配置字典。
    """
    global LAMP_URL, HEARTBEAT_SEC, PUSH_TIMEOUT_SEC, SESSION_TTL_SEC
    global WORKING_IDLE_TIMEOUT_SEC
    global BLE_FALLBACK_ENABLED, BLE_BRIDGE_SOCKET, BLE_DEVICE_NAME
    cfg = load_config()
    LAMP_URL = cfg["lamp_url"]
    HEARTBEAT_SEC = cfg["heartbeat_sec"]
    PUSH_TIMEOUT_SEC = cfg["push_timeout_sec"]
    SESSION_TTL_SEC = cfg["session_ttl_sec"]
    WORKING_IDLE_TIMEOUT_SEC = cfg["working_idle_timeout_sec"]
    BLE_FALLBACK_ENABLED = cfg["ble_fallback_enabled"]
    BLE_BRIDGE_SOCKET = cfg["ble_bridge_socket"]
    BLE_DEVICE_NAME = cfg["ble_device_name"]
    return cfg


# 模块导入时解析一次，回填下列模块级常量（运行期各模块直接读这些常量）：
#   LAMP_URL / HEARTBEAT_SEC / PUSH_TIMEOUT_SEC / SESSION_TTL_SEC /
#   BLE_FALLBACK_ENABLED / BLE_BRIDGE_SOCKET / BLE_DEVICE_NAME
# （LISTEN_PORT 是固定契约常量，见文件顶部，不经 config 回填。）
apply_config()
