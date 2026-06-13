# Vibe Lamp 实现计划 02 — 守护进程 + Claude Code 钩子 + launchd

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 设计依据：`superpowers/specs/2026-06-13-vibe-lamp-design.md`。前置：计划 01（固件）产出的 `vibelamp.local` 能被 `curl -X POST /state` 驱动。本计划产出「真实 Claude Code 会话 → 灯」的完整链路。

**Goal:** 一个 macOS 常驻 Python 守护进程：接收 Claude Code 钩子事件、维护多会话状态、合并后推送给灯、定时心跳、超时兜底；外加幂等装钩子的安装脚本和 launchd 开机自启。

**Architecture:** 钩子（一行 curl）把事件 POST 到守护进程的 `127.0.0.1:8787/event` → 归一化成 `(session_id, state, tool)` → 更新线程安全的 SessionStore → 合并成 `{"sessions":[...]}`（按优先级排序，最重要的在前）→ 经 `urllib` POST 到 `vibelamp.local/state`。后台心跳线程每 5s 重推（兼做 ESP32 重启自愈）并清理超时死会话。

**Tech Stack:** Python 3.9+ **仅标准库**（http.server、urllib、threading、json、dataclasses）；pytest 做开发测试；launchd LaunchAgent 自启。macOS 原生解析 `.local`，无需 mDNS 库。

---

## 文件结构

```
daemon/
├── pyproject.toml
├── vibelamp/
│   ├── __init__.py
│   ├── config.py          # 常量：灯地址、监听端口、心跳/超时
│   ├── model.py           # SessionState、SessionStore（线程安全）、合并→wire
│   ├── normalize.py       # Claude Code 钩子 JSON → (session_id, state, tool)
│   ├── lamp_client.py     # push(payload) 到灯，绝不抛异常
│   ├── server.py          # HTTP 收事件 + 心跳线程 + 装配
│   └── __main__.py        # 入口：python -m vibelamp
├── tests/
│   ├── test_model.py
│   ├── test_normalize.py
│   ├── test_lamp_client.py
│   └── test_install.py
├── install.py             # 幂等合并钩子 + 装/卸 launchd
└── com.vibelamp.daemon.plist.template
```

**wire 协议**（与固件 Task 7 严格一致）：`{"sessions":[{"state":"working","tool":"code"},{"state":"needs_you"}]}`。`state` ∈ working|done|needs_you|error（守护进程只发这四种；idle 用空数组表示，lost/boot 由固件自行派生）。`tool` ∈ none|code|command|search。数组按优先级降序，`sessions[0]` 最重要（单颗 LED 只显示它）。

---

## Task 1: 包骨架 + config

**Files:**
- Create: `daemon/pyproject.toml`
- Create: `daemon/vibelamp/__init__.py`
- Create: `daemon/vibelamp/config.py`

- [ ] **Step 1: 写 `pyproject.toml`**

```toml
[project]
name = "vibelamp"
version = "0.1.0"
requires-python = ">=3.9"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: 写 `vibelamp/__init__.py`（空文件）**

```python
```

- [ ] **Step 3: 写 `vibelamp/config.py`**

```python
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
```

- [ ] **Step 4: 验证可导入**

Run: `cd daemon && python -c "import vibelamp.config as c; print(c.LAMP_URL, c.LISTEN_PORT)"`
Expected: `http://vibelamp.local/state 8787`

- [ ] **Step 5: 提交**

```bash
cd daemon && git add pyproject.toml vibelamp/__init__.py vibelamp/config.py
git commit -m "feat(daemon): 包骨架 + config"
```

---

## Task 2: SessionStore + 合并成 wire（TDD）

**Files:**
- Create: `daemon/vibelamp/model.py`
- Create: `daemon/tests/test_model.py`

- [ ] **Step 1: 写失败测试**

`tests/test_model.py`:

```python
from vibelamp.model import SessionStore, REMOVE

def test_empty_store_is_empty_sessions():
    s = SessionStore(ttl_sec=1800)
    assert s.to_wire() == {"sessions": []}

def test_single_session_in_wire():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "working", "code")
    assert s.to_wire() == {"sessions": [{"state": "working", "tool": "code"}]}

def test_idle_session_excluded():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "idle", "none")
    assert s.to_wire() == {"sessions": []}

def test_sessions_sorted_by_priority():
    s = SessionStore(ttl_sec=1800)
    s.update("a", "working", "code")
    s.update("b", "needs_you", "none")
    s.update("c", "done", "none")
    states = [x["state"] for x in s.to_wire()["sessions"]]
    assert states == ["needs_you", "working", "done"]  # needs_you 最优先

def test_remove_session():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "working", "code")
    s.update("sid1", REMOVE, "none")
    assert s.to_wire() == {"sessions": []}

def test_sweep_expires_old_sessions():
    clock = [1000.0]
    s = SessionStore(ttl_sec=60, clock=lambda: clock[0])
    s.update("sid1", "working", "code")
    clock[0] = 1100.0   # 100s 后，超过 60s ttl
    s.sweep()
    assert s.to_wire() == {"sessions": []}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_model.py -v`
Expected: ImportError（`model` 不存在）。

- [ ] **Step 3: 写 `vibelamp/model.py`**

```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_model.py -v`
Expected: 6 个测试全 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/model.py tests/test_model.py
git commit -m "feat(daemon): SessionStore 合并+优先级排序+超时清理"
```

---

## Task 3: Claude Code 事件归一化（TDD）

**Files:**
- Create: `daemon/vibelamp/normalize.py`
- Create: `daemon/tests/test_normalize.py`

- [ ] **Step 1: 写失败测试**

`tests/test_normalize.py`:

```python
from vibelamp.normalize import transition, classify_tool
from vibelamp.model import REMOVE

def test_classify_tool():
    assert classify_tool("Edit") == "code"
    assert classify_tool("Write") == "code"
    assert classify_tool("Bash") == "command"
    assert classify_tool("Grep") == "search"
    assert classify_tool("WebSearch") == "search"
    assert classify_tool("Unknown") == "code"     # 默认
    assert classify_tool(None) == "code"

def test_user_prompt_submit_working():
    assert transition({"hook_event_name": "UserPromptSubmit", "session_id": "s1"}) \
        == ("s1", "working", "none")

def test_pretooluse_classifies_tool():
    assert transition({"hook_event_name": "PreToolUse", "session_id": "s1",
                       "tool_name": "Bash"}) == ("s1", "working", "command")

def test_notification_needs_you():
    assert transition({"hook_event_name": "Notification", "session_id": "s1"}) \
        == ("s1", "needs_you", "none")

def test_stop_done():
    assert transition({"hook_event_name": "Stop", "session_id": "s1"}) \
        == ("s1", "done", "none")

def test_failure_error():
    assert transition({"hook_event_name": "PostToolUseFailure", "session_id": "s1"}) \
        == ("s1", "error", "none")

def test_session_end_removes():
    assert transition({"hook_event_name": "SessionEnd", "session_id": "s1"}) \
        == ("s1", REMOVE, "none")

def test_missing_session_id_defaults():
    assert transition({"hook_event_name": "Stop"}) == ("default", "done", "none")

def test_unknown_event_ignored():
    assert transition({"hook_event_name": "SubagentStop", "session_id": "s1"}) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: ImportError。

- [ ] **Step 3: 写 `vibelamp/normalize.py`**

```python
from .model import REMOVE

_CODE = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
_SEARCH = {"Read", "Grep", "Glob", "WebSearch", "WebFetch", "Agent", "Task"}


def classify_tool(tool_name):
    if tool_name in _CODE:
        return "code"
    if tool_name == "Bash":
        return "command"
    if tool_name in _SEARCH:
        return "search"
    return "code"   # 默认归为写码色


def transition(event):
    """Claude Code 钩子 JSON → (session_id, state, tool)；返回 None 表示忽略。"""
    name = event.get("hook_event_name")
    sid = event.get("session_id") or "default"
    if name == "UserPromptSubmit":
        return (sid, "working", "none")
    if name in ("PreToolUse", "PostToolUse"):
        return (sid, "working", classify_tool(event.get("tool_name")))
    if name == "PostToolUseFailure":
        return (sid, "error", "none")
    if name == "Notification":
        return (sid, "needs_you", "none")
    if name == "Stop":
        return (sid, "done", "none")
    if name == "SessionStart":
        return (sid, "idle", "none")
    if name == "SessionEnd":
        return (sid, REMOVE, "none")
    return None
```

> 说明：`SubagentStop` 等事件返回 None（不改状态）。`error` 状态较短暂，下一次工具事件会覆盖回 working——这是 v1 的简化（见设计文档已知限制）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/normalize.py tests/test_normalize.py
git commit -m "feat(daemon): Claude Code 事件归一化 + 工具分色"
```

---

## Task 4: 灯客户端 push —— 绝不抛异常（TDD）

**Files:**
- Create: `daemon/vibelamp/lamp_client.py`
- Create: `daemon/tests/test_lamp_client.py`

- [ ] **Step 1: 写失败测试（用本地 mock HTTP server 验证）**

`tests/test_lamp_client.py`:

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from vibelamp import lamp_client

class _Capture(BaseHTTPRequestHandler):
    received = None
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        _Capture.received = json.loads(self.rfile.read(length))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass

def _serve():
    srv = HTTPServer(("127.0.0.1", 0), _Capture)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

def test_push_posts_json_and_returns_true():
    srv = _serve()
    port = srv.server_address[1]
    ok = lamp_client.push({"sessions": [{"state": "working", "tool": "code"}]},
                          url=f"http://127.0.0.1:{port}/state")
    assert ok is True
    assert _Capture.received == {"sessions": [{"state": "working", "tool": "code"}]}
    srv.shutdown()

def test_push_unreachable_returns_false_no_raise():
    # 没人监听的端口；push 必须吞掉异常、返回 False
    ok = lamp_client.push({"sessions": []},
                          url="http://127.0.0.1:1/state", timeout=0.3)
    assert ok is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_lamp_client.py -v`
Expected: ImportError。

- [ ] **Step 3: 写 `vibelamp/lamp_client.py`**

```python
import json
import logging
import urllib.request
from . import config

log = logging.getLogger("vibelamp.lamp")


def push(payload, url=None, timeout=None):
    """POST payload 到灯。绝不抛异常——失败返回 False。"""
    url = url or config.LAMP_URL
    timeout = timeout or config.PUSH_TIMEOUT_SEC
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as e:
        log.debug("lamp push failed: %s", e)
        return False
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_lamp_client.py -v`
Expected: 2 个 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/lamp_client.py tests/test_lamp_client.py
git commit -m "feat(daemon): 灯客户端 push（容错不抛异常）"
```

---

## Task 5: HTTP 收事件 + 心跳线程 + 装配

server 是 IO 装配层，靠下一任务的手动端到端验证；此处只确保能起、能收、能转发。

**Files:**
- Create: `daemon/vibelamp/server.py`
- Create: `daemon/vibelamp/__main__.py`

- [ ] **Step 1: 写 `vibelamp/server.py`**

```python
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import config, lamp_client
from .model import SessionStore
from .normalize import transition

log = logging.getLogger("vibelamp.server")
store = SessionStore(config.SESSION_TTL_SEC)


def handle_event(event):
    t = transition(event)
    if t is None:
        return
    sid, state, tool = t
    store.update(sid, state, tool)
    lamp_client.push(store.to_wire())


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/event":
            self.send_response(404); self.end_headers(); return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            event = json.loads(body or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); return
        try:
            handle_event(event)
        except Exception as e:
            log.exception("handle_event failed: %s", e)   # 绝不让钩子失败
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


def _heartbeat_loop():
    while True:
        time.sleep(config.HEARTBEAT_SEC)
        try:
            store.sweep()
            lamp_client.push(store.to_wire())
        except Exception as e:
            log.debug("heartbeat error: %s", e)


def serve():
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    httpd = ThreadingHTTPServer((config.LISTEN_HOST, config.LISTEN_PORT), Handler)
    log.info("vibelamp daemon listening %s:%d -> %s",
             config.LISTEN_HOST, config.LISTEN_PORT, config.LAMP_URL)
    httpd.serve_forever()
```

- [ ] **Step 2: 写 `vibelamp/__main__.py`**

```python
import logging
from .server import serve


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    serve()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 起守护进程冒烟测试（指向一个临时假灯）**

Run（终端 A，假灯打印收到的推送）:
```bash
cd daemon && python -c "
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n=int(self.headers.get('Content-Length',0)); print('LAMP<-', self.rfile.read(n).decode())
        self.send_response(200); self.end_headers(); self.wfile.write(b'{}')
    def log_message(self,*a): pass
HTTPServer(('127.0.0.1',9999),H).serve_forever()
"
```
Run（终端 B）:
```bash
cd daemon && VIBELAMP_URL=http://127.0.0.1:9999/state python -m vibelamp
```
Expected: 终端 B 打印 `listening 127.0.0.1:8787`；终端 A 每 5s 收到一次 `LAMP<- {"sessions": []}`（心跳）。

- [ ] **Step 4: 提交**

```bash
cd daemon && git add vibelamp/server.py vibelamp/__main__.py
git commit -m "feat(daemon): HTTP 收事件 + 心跳线程 + 入口"
```

---

## Task 6: 端到端手动验证（curl 模拟钩子）

无新代码，纯验证守护进程 + 真灯（或假灯）整链路。

- [ ] **Step 1: 起守护进程指向真灯**

Run（终端 A，需计划 01 的灯在线）:
```bash
cd daemon && python -m vibelamp
```

- [ ] **Step 2: 模拟 Claude Code 钩子事件**

Run（终端 B）:
```bash
P=http://127.0.0.1:8787/event
curl -s -X POST $P -d '{"hook_event_name":"UserPromptSubmit","session_id":"s1"}'
curl -s -X POST $P -d '{"hook_event_name":"PreToolUse","session_id":"s1","tool_name":"Bash"}'
curl -s -X POST $P -d '{"hook_event_name":"Notification","session_id":"s1"}'
curl -s -X POST $P -d '{"hook_event_name":"Stop","session_id":"s1"}'
curl -s -X POST $P -d '{"hook_event_name":"SessionEnd","session_id":"s1"}'
```
Expected: 灯依次 **蓝呼吸 → 紫呼吸(命令) → 红慢闪 → 绿渐暗 → 空闲**。

- [ ] **Step 3: 验证多会话分段（需灯环 env）**

```bash
curl -s -X POST $P -d '{"hook_event_name":"PreToolUse","session_id":"a","tool_name":"Edit"}'
curl -s -X POST $P -d '{"hook_event_name":"Notification","session_id":"b"}'
```
Expected: 灯环一段蓝、一段红（needs_you 排在前）。

- [ ] **Step 4: 验证灯断线不崩守护进程**

断开灯电源，再发若干事件；守护进程应继续运行、日志 `lamp push failed`，不崩溃。重新上电灯后 ≤5s 心跳自愈到当前状态。

---

## Task 7: 钩子安装脚本（幂等合并，TDD）

**Files:**
- Create: `daemon/install.py`（含可测的纯函数 `merge_hooks`/`remove_hooks`）
- Create: `daemon/tests/test_install.py`

- [ ] **Step 1: 写失败测试**

`tests/test_install.py`:

```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "install", pathlib.Path(__file__).resolve().parent.parent / "install.py")
install = importlib.util.module_from_spec(spec); spec.loader.exec_module(install)

def test_merge_into_empty():
    out = install.merge_hooks({})
    assert "PreToolUse" in out["hooks"]
    assert "Stop" in out["hooks"]
    cmd = out["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "127.0.0.1:8787/event" in cmd

def test_merge_is_idempotent():
    once = install.merge_hooks({})
    twice = install.merge_hooks(once)
    assert once == twice                      # 重复跑不叠加

def test_merge_preserves_user_hooks():
    user = {"hooks": {"Stop": [{"matcher": "*", "hooks":
            [{"type": "command", "command": "echo mine"}]}]}}
    out = install.merge_hooks(user)
    cmds = [h["command"] for e in out["hooks"]["Stop"] for h in e["hooks"]]
    assert "echo mine" in cmds                # 用户的还在
    assert any("127.0.0.1:8787/event" in c for c in cmds)  # 我们的也加上了

def test_remove_only_ours():
    merged = install.merge_hooks({"hooks": {"Stop": [{"matcher": "*", "hooks":
             [{"type": "command", "command": "echo mine"}]}]}})
    cleaned = install.remove_hooks(merged)
    cmds = [h["command"] for e in cleaned["hooks"].get("Stop", []) for h in e["hooks"]]
    assert "echo mine" in cmds
    assert all("127.0.0.1:8787/event" not in c for c in cmds)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_install.py -v`
Expected: 失败（install.py 不存在或无 merge_hooks）。

- [ ] **Step 3: 写 `install.py` 的纯函数部分**

```python
#!/usr/bin/env python3
"""幂等安装/卸载 Vibe Lamp 的 Claude Code 钩子与 launchd 自启。"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK_CMD = ('curl -s --max-time 1 -X POST '
            'http://127.0.0.1:8787/event --data-binary @- || true')
HOOK_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
               "PostToolUseFailure", "Notification", "Stop", "SessionEnd"]

SETTINGS = Path.home() / ".claude" / "settings.json"
PLIST = Path.home() / "Library" / "LaunchAgents" / "com.vibelamp.daemon.plist"
LABEL = "com.vibelamp.daemon"


def _our_block():
    return {"matcher": "*", "hooks":
            [{"type": "command", "command": HOOK_CMD, "timeout": 2}]}


def merge_hooks(settings):
    settings = dict(settings or {})
    hooks = {k: list(v) for k, v in (settings.get("hooks") or {}).items()}
    for ev in HOOK_EVENTS:
        entries = list(hooks.get(ev) or [])
        already = any(
            any(h.get("command") == HOOK_CMD for h in (e.get("hooks") or []))
            for e in entries)
        if not already:
            entries.append(_our_block())
        hooks[ev] = entries
    settings["hooks"] = hooks
    return settings


def remove_hooks(settings):
    settings = dict(settings or {})
    hooks = {k: list(v) for k, v in (settings.get("hooks") or {}).items()}
    for ev in list(hooks.keys()):
        kept = [e for e in hooks[ev]
                if not any(h.get("command") == HOOK_CMD
                           for h in (e.get("hooks") or []))]
        if kept:
            hooks[ev] = kept
        else:
            del hooks[ev]
    settings["hooks"] = hooks
    return settings
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_install.py -v`
Expected: 4 个 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add install.py tests/test_install.py
git commit -m "feat(daemon): 钩子幂等合并/移除（纯函数+TDD）"
```

---

## Task 8: launchd 自启 + 安装/卸载 CLI

**Files:**
- Create: `daemon/com.vibelamp.daemon.plist.template`
- Modify: `daemon/install.py`（加文件 IO 与 launchd + CLI）

- [ ] **Step 1: 写 plist 模板**

`com.vibelamp.daemon.plist.template`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.vibelamp.daemon</string>
  <key>ProgramArguments</key>
  <array>
    <string>{PYTHON}</string>
    <string>-m</string>
    <string>vibelamp</string>
  </array>
  <key>WorkingDirectory</key><string>{DAEMON_DIR}</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONPATH</key><string>{DAEMON_DIR}</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{LOG_DIR}/vibelamp.out.log</string>
  <key>StandardErrorPath</key><string>{LOG_DIR}/vibelamp.err.log</string>
</dict>
</plist>
```

- [ ] **Step 2: 给 install.py 加文件 IO 与 launchd + CLI**

在 `install.py` 末尾追加：

```python
def _load_settings():
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text() or "{}")
    return {}


def _save_settings(settings):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False))


def _write_plist():
    daemon_dir = str(Path(__file__).resolve().parent)
    log_dir = str(Path.home() / "Library" / "Logs")
    tmpl = (Path(daemon_dir) / "com.vibelamp.daemon.plist.template").read_text()
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    PLIST.write_text(tmpl.format(
        PYTHON=sys.executable, DAEMON_DIR=daemon_dir, LOG_DIR=log_dir))


def _launchctl(*args):
    subprocess.run(["launchctl", *args], check=False)


def install():
    _save_settings(merge_hooks(_load_settings()))
    print(f"✅ 钩子已写入 {SETTINGS}")
    _write_plist()
    _launchctl("unload", str(PLIST))      # 先卸（忽略报错）
    _launchctl("load", "-w", str(PLIST))
    print(f"✅ launchd 已加载 {PLIST}（开机自启 + 崩溃重拉）")


def uninstall():
    _launchctl("unload", str(PLIST))
    if PLIST.exists():
        PLIST.unlink()
    _save_settings(remove_hooks(_load_settings()))
    print("✅ 已移除钩子与 launchd")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    else:
        print("用法: python install.py [install|uninstall]")
        sys.exit(1)
```

- [ ] **Step 3: 实跑安装**

Run: `cd daemon && python install.py install`
Expected: 打印钩子已写入、launchd 已加载。检查：
```bash
launchctl list | grep vibelamp        # 应有 com.vibelamp.daemon
cat ~/.claude/settings.json | python -m json.tool | grep -A2 8787   # 应见钩子
```

- [ ] **Step 4: 真实 Claude Code 端到端**

在任意目录起一个 Claude Code 会话，发个指令让它跑几个工具、问个权限、结束。
Expected: 灯实时反映——**指令开始蓝呼吸、跑命令变紫、要权限红慢闪、完成绿渐暗**。

- [ ] **Step 5: 验证卸载干净**

Run: `cd daemon && python install.py uninstall`
Expected: `launchctl list | grep vibelamp` 无输出；`~/.claude/settings.json` 里我们的钩子被移除、用户原有配置保留。

- [ ] **Step 6: 提交**

```bash
cd daemon && git add install.py com.vibelamp.daemon.plist.template
git commit -m "feat(daemon): launchd 自启 + install/uninstall CLI"
```

---

## 验收（整计划完成标准）

- `python -m pytest` 全绿（model / normalize / lamp_client / install 四组）。
- `python -m vibelamp` 能起，心跳每 5s 推空 sessions。
- curl 模拟钩子能驱动真灯全部状态；灯断电不崩守护进程，恢复后 ≤5s 自愈。
- `python install.py install` 后，真实 Claude Code 会话实时反映到灯；`uninstall` 移除干净且保留用户原有钩子。

## 后续计划

- **计划 03 — Codex 接入**：在 normalize 增加 Codex 事件映射；install.py 增加 `~/.codex/config.toml` 的钩子+notify 幂等写入；核实 Codex 的 session_id。
- **计划 04 — 网页配网（WiFiManager）+ BLE**。

## 自查记录

- **Spec 覆盖**：采集层（钩子 curl）、转译/聚合层（归一化+合并+优先级+心跳+超时兜底+容错不崩）、安装（幂等合并+launchd 自启）均有任务。BLE/Codex/配网属后续计划。
- **类型一致**：wire 的 state/tool 字符串与计划 01 固件 Task 7 的解析严格对齐（working/done/needs_you/error；none/code/command/search）；`REMOVE` 哨兵在 model 与 normalize 一致引用。
- **无占位**：每步给完整代码与命令；IO/launchd 层靠真实安装 + Claude Code 会话验证（已标注）。
- **已知取舍**：error 状态短暂、靠下一事件覆盖（设计文档已记）；session_id 取 Claude Code 钩子的 `session_id`，Codex 的待计划 03 核实。
