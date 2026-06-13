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
