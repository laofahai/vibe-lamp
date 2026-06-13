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
