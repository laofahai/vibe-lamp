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


class SessionStore:
    def __init__(self, ttl_sec, clock=time.monotonic):
        self._sessions = {}
        self._lock = threading.Lock()
        self._ttl = ttl_sec
        self._clock = clock

    def update(self, session_id, state, tool):
        with self._lock:
            if state == REMOVE:
                self._sessions.pop(session_id, None)
                return
            self._sessions[session_id] = SessionState(state, tool, self._clock())

    def sweep(self):
        now = self._clock()
        with self._lock:
            dead = [sid for sid, s in self._sessions.items()
                    if now - s.updated_at > self._ttl]
            for sid in dead:
                del self._sessions[sid]

    def demote_stale_working(self, timeout):
        """把「working 但超过 timeout 没新事件」的会话降级为 idle（灯随之灭）。

        ESC / kill 中断不会触发 Stop 钩子 → 会话永远停在 working、灯卡在蓝色。
        心跳里定期调用本方法兜底自愈。不刷新 updated_at（仍按原时间走 TTL，
        最终被 sweep 清掉）。返回被降级的会话数。"""
        now = self._clock()
        n = 0
        with self._lock:
            for s in self._sessions.values():
                if s.state == "working" and now - s.updated_at > timeout:
                    s.state = "idle"
                    s.tool = "none"
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
