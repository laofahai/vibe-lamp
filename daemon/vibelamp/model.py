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

    def to_wire(self):
        with self._lock:
            active = [s for s in self._sessions.values() if s.state != "idle"]
        active.sort(key=lambda s: PRIORITY.get(s.state, 0), reverse=True)
        return {"sessions": [{"state": s.state, "tool": s.tool} for s in active]}
