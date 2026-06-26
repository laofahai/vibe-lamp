import threading
import time
from dataclasses import dataclass

REMOVE = "__remove__"
PRIORITY = {"needs_you": 4, "error": 3, "working": 2, "done": 1, "idle": 0}


@dataclass
class SessionState:
    state: str
    tool: str
    updated_at: float
    # 是否有工具正在跑（收到 PreToolUse、还没等到 PostToolUse）。
    # 用于自愈分档：有工具在跑可能是几分钟的长构建 → 用更长的超时，避免误杀。
    in_flight: bool = False


class SessionStore:
    def __init__(self, ttl_sec, clock=time.monotonic):
        self._sessions = {}
        self._lock = threading.Lock()
        self._ttl = ttl_sec
        self._clock = clock

    def update(self, session_id, state, tool, in_flight=False):
        with self._lock:
            if state == REMOVE:
                self._sessions.pop(session_id, None)
                return
            self._sessions[session_id] = SessionState(
                state, tool, self._clock(), in_flight)

    def sweep(self):
        now = self._clock()
        with self._lock:
            dead = [sid for sid, s in self._sessions.items()
                    if now - s.updated_at > self._ttl]
            for sid in dead:
                del self._sessions[sid]

    def demote_stale(self, idle_timeout, tool_timeout):
        """把「working 但静默过久」的会话降级为 idle（灯随之灭），自愈 ESC/kill 卡蓝。

        背景：ESC / Ctrl-C 中断不触发任何钩子（官方确认 Stop 不在中断时触发），会话会
        卡在最后一个状态。**只对 working 兜底**——它是「干活中」的临时态，本就不该长亮；
        而 needs_you(红·该你了) / error 是**故意要一直提醒你的「找你」态**，绝不在此降级
        （它们靠你下一次操作、或会话 TTL 30min 无活动清理来收尾，不会被 90s 掐断）。

        working 分两档超时（按是否有工具在跑）：
          - 有工具在跑(in_flight)：可能是几分钟的长构建 → tool_timeout（长），不误杀。
          - 没工具在跑（纯思考 / 纯文字 / 已被中断）：idle_timeout（短），尽快灭。
        正常干活事件不断刷新 updated_at，永远摸不到超时；只有事件真停了
        （中断 / 走人）才触发。不刷新 updated_at（仍按原时间走 TTL）。返回降级数。"""
        now = self._clock()
        n = 0
        with self._lock:
            for s in self._sessions.values():
                if s.state != "working":      # needs_you/error 等「找你」态保留，不掐断
                    continue
                limit = tool_timeout if s.in_flight else idle_timeout
                if now - s.updated_at > limit:
                    s.state = "idle"
                    s.tool = "none"
                    s.in_flight = False
                    n += 1
        return n

    def snapshot(self):
        """调试面板用：每个会话的 sid / state / tool / 距上次事件秒数（含 idle）。"""
        now = self._clock()
        with self._lock:
            return [
                {"sid": sid, "state": s.state, "tool": s.tool,
                 "age_sec": round(now - s.updated_at, 1)}
                for sid, s in self._sessions.items()
            ]

    def to_wire(self):
        with self._lock:
            active = [s for s in self._sessions.values() if s.state != "idle"]
        active.sort(key=lambda s: PRIORITY.get(s.state, 0), reverse=True)
        return {"sessions": [{"state": s.state, "tool": s.tool} for s in active]}
