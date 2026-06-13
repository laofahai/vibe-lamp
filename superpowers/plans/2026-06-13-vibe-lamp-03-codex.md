# Vibe Lamp 实现计划 03 — Codex 接入

> **For agentic workers:** REQUIRED SUB-SKILL: 用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务执行。步骤用 `- [ ]` 复选框跟踪。
>
> 设计依据：`superpowers/specs/2026-06-13-vibe-lamp-design.md`。前置：计划 02 已产出 Python 守护进程，能接 Claude Code 钩子、合并多会话、推送 `vibelamp.local`、心跳、超时兜底、幂等装钩子 + launchd。**本计划是计划 02 的直接延续**：在同一个 `daemon/` 工程里给守护进程加上 Codex 会话支持，让 Claude Code 与 Codex 同开时灯环能分段显示两个 agent 的真实状态。

**Goal:** 让守护进程也认 Codex 会话——新增 Codex 事件归一化、用 agent 命名空间隔离两边的 session id（`claude:<id>` / `codex:<id>`）避免撞车、给 Codex 单开 `/event/codex` 端点、并幂等写入 Codex 配置（sidecar `hooks.json` + `config.toml` 一行指针 + notify）。

**Architecture:** 沿用计划 02 的链路与文件结构。Codex 钩子（一行 curl）把 stdin 的 JSON 事件 POST 到守护进程新端点 `127.0.0.1:8787/event/codex`；`server.py` 按端点路由到对应归一化器（`/event` → Claude，`/event/codex` → Codex），统一进 `(session_id, state, tool)` 元组，其中 `session_id` 已带 agent 前缀，再喂同一个 `SessionStore`、合并成同一份 wire `{"sessions":[...]}` 推灯。Codex 配置因 stdlib 只能读不能写 TOML（`tomllib` 无写能力），install.py 走「纯 JSON 写 `~/.codex/hooks.json` + 在 `config.toml` 末尾最小化追加一行 hooks 指针和一行 notify」的混合策略，全程幂等。

**Tech Stack:** 与计划 02 完全一致——Python 3.9+ **仅标准库**（http.server、urllib、threading、json、dataclasses、re）；pytest 做开发测试。不引入任何新依赖（`tomllib` 仅 Python 3.11+ 且只读，本计划**不用它写 TOML**，靠纯文本最小化追加搞定 config.toml）。

---

## 已确认的 Codex 钩子事实（2026-06-13 查官方文档 + 社区指南）

来源：`https://developers.openai.com/codex/hooks`、`/config-reference`、`/config-advanced`，及 `https://codex.danielvaughan.com/2026/04/15/...`。

**stdin JSON 字段名（与 Claude Code 同名，是巧合也是便利）：**
- 事件名字段：**`hook_event_name`**（"Current hook event name"）
- 会话 id 字段：**`session_id`**（"Current Codex session id. Subagent hooks use the parent session id."）
- 工具名字段：**`tool_name`**（"Canonical hook tool name, such as `Bash`, `apply_patch`, or an MCP name"）

**各事件 payload 字段：**
| 事件 | 关键字段 |
|---|---|
| SessionStart | `session_id` `hook_event_name` `cwd` `model` `source` `permission_mode` |
| UserPromptSubmit | + `turn_id` `prompt` |
| PreToolUse | + `turn_id` `tool_name` `tool_use_id` `tool_input` |
| PostToolUse | PreToolUse 全部 + **`tool_response`**（含 `output` 和 `exit_code`） |
| Stop | + `turn_id` `stop_hook_active` `last_assistant_message` |
| SubagentStart / SubagentStop | + `agent_id` `agent_type`（Stop 版再加 `agent_transcript_path`） |
| PermissionRequest | `tool_name` `tool_input` + 通用字段 + `permission_mode` |

**配置（`~/.codex/config.toml`）：**
- inline 写法 `[[hooks.PreToolUse]]` + `[[hooks.PreToolUse.hooks]]`（与 hooks.json 同 schema）。
- **sidecar 加载路径**：`~/.codex/hooks.json`（用户级）、`<repo>/.codex/hooks.json`（项目级，需信任）。
- notify：`notify = array<string>`，"Command invoked for notifications; receives a JSON payload from Codex."
- notify payload 字段是 **kebab-case**（与 hooks 的 snake_case 不同）：`type`（`agent-turn-complete` / `approval-requested`）、`thread-id`、`turn-id`、`cwd`、`input-messages`、`last-assistant-message`。

**两个仍存在不确定的点（本计划必须靠「先抓真实 payload/真实文件」兜底，不硬赌）：**
1. **`hooks.json` 顶层结构有冲突**：官方 `config-advanced` 页读出来是「事件名直接做顶层 key」（`{"PreToolUse":[...]}`）；社区详解指南读出来是「裹在 `hooks` key 下」（`{"hooks":{"PreToolUse":[...]}}`，与 Claude `settings.json` 同形）。**两份权威说法不一致**。本计划默认采用**裹 `hooks` key** 的写法（更细的第三方指南给了完整最小示例，且与 Claude 侧对称、合并逻辑可复用思路），但 `Task 5` 必须先用一次真实 `codex` 安装核对 `~/.codex/hooks.json` 实际被接受的结构，再锁定。merge 函数写成**容错读两种形状**。
2. **Codex 的 PostToolUse 没有独立的成功/失败事件**（Claude Code 侧官方提供了真实的 `PostToolUseFailure` 事件——工具调用失败时触发，与 `PostToolUse` 并列，计划 02 正是用它判出错；Codex 没有对应事件）。Codex 的失败只能从 `tool_response.exit_code != 0` 推断。具体 `exit_code` 在 `tool_response` 里的确切层级（顶层还是嵌套、键名是不是就叫 `exit_code`）**未 100% 确认**，`Task 5` 抓真实 PostToolUse payload 时一并核对，normalize 的 Codex 分支对它做多候选兜底取值。

---

## 文件结构（标注新建 / 改计划 02 的文件）

```
daemon/
├── vibelamp/
│   ├── config.py            # 【改 02】新增 CODEX_HOOKS_JSON / CODEX_CONFIG_TOML 路径常量
│   ├── normalize.py         # 【改 02】① Claude 端 transition 给 session_id 补 "claude:" 前缀
│   │                        #          ② 新增 codex_transition() + classify_codex_tool()
│   ├── model.py             # 【不改】SessionStore 对前缀化 session_id 无感
│   ├── server.py            # 【改 02】路由分流：/event→Claude，/event/codex→Codex
│   ├── lamp_client.py       # 【不改】
│   └── __main__.py          # 【不改】
├── tests/
│   ├── test_normalize.py    # 【改 02】Claude 端断言加 "claude:" 前缀；新增 Codex 用例
│   ├── test_server_routing.py   # 【新建】端点路由分流单测
│   └── test_install_codex.py    # 【新建】Codex 配置幂等写入单测
└── install.py               # 【改 02】install()/uninstall() 末尾接入 Codex 配置读写
```

**wire 协议**（与计划 01/02 完全一致，本计划不动）：`{"sessions":[{"state":"working","tool":"code"},{"state":"needs_you"}]}`。`state` ∈ working|done|needs_you|error（idle 用空数组）；`tool` ∈ none|code|command|search。**命名空间隔离只发生在 `session_id` 这个内部 key 上，wire 里不暴露 agent 字段**——灯只关心状态色，不关心是哪个 agent（设计文档：固件是哑终端，不懂 agent）。

---

## Task 1: 给 Claude 端 session_id 补 `claude:` 前缀（改 02，TDD）

命名空间隔离的第一半：先把已有的 Claude 端归一化输出从裸 `session_id` 改成 `claude:<id>`，避免与即将加入的 `codex:<id>` 撞车。这是对计划 02 `normalize.py` 的**最小修改**。

**Files:**
- Modify: `daemon/vibelamp/normalize.py`
- Modify: `daemon/tests/test_normalize.py`

- [ ] **Step 1: 改测试断言（先红）**

计划 02 的 `tests/test_normalize.py` 里所有断 Claude `transition()` 返回值的用例，session_id 都要带上 `claude:` 前缀。把下列 5 处用例**整体替换**为带前缀版本（其余 `classify_tool` 用例不动）：

```python
def test_user_prompt_submit_working():
    assert transition({"hook_event_name": "UserPromptSubmit", "session_id": "s1"}) \
        == ("claude:s1", "working", "none")

def test_pretooluse_classifies_tool():
    assert transition({"hook_event_name": "PreToolUse", "session_id": "s1",
                       "tool_name": "Bash"}) == ("claude:s1", "working", "command")

def test_notification_needs_you():
    assert transition({"hook_event_name": "Notification", "session_id": "s1"}) \
        == ("claude:s1", "needs_you", "none")

def test_stop_done():
    assert transition({"hook_event_name": "Stop", "session_id": "s1"}) \
        == ("claude:s1", "done", "none")

def test_failure_error():
    assert transition({"hook_event_name": "PostToolUseFailure", "session_id": "s1"}) \
        == ("claude:s1", "error", "none")

def test_session_end_removes():
    assert transition({"hook_event_name": "SessionEnd", "session_id": "s1"}) \
        == ("claude:s1", REMOVE, "none")

def test_missing_session_id_defaults():
    assert transition({"hook_event_name": "Stop"}) == ("claude:default", "done", "none")

def test_unknown_event_ignored():
    assert transition({"hook_event_name": "SubagentStop", "session_id": "s1"}) is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: 上述带前缀用例 FAIL（当前返回裸 `s1` / `default`）。

- [ ] **Step 3: 改 `normalize.py` 的 `transition()`**

把计划 02 `transition()` 里这一行：

```python
    sid = event.get("session_id") or "default"
```

改成：

```python
    sid = "claude:" + (event.get("session_id") or "default")
```

其余不动（各事件分支已经用 `sid`，自动带上前缀）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: 全 PASS。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/normalize.py tests/test_normalize.py
git commit -m "feat(daemon): Claude 端 session_id 加 claude: 命名空间前缀"
```

---

## Task 2: Codex 事件归一化 `codex_transition()`（新增，TDD）

命名空间隔离的第二半 + Codex 事件映射。新增 `codex_transition()` 和 `classify_codex_tool()`，输出 `codex:<id>` 前缀。Codex 工具名是 `Bash` / `apply_patch` / MCP 名等，与 Claude 工具集不同，单独分类。

**Codex 事件 → (state, tool) 映射表：**
| Codex 事件 | state | 说明 |
|---|---|---|
| `SessionStart` | idle | 会话开始（进 store 但不点亮，与 Claude 对称） |
| `UserPromptSubmit` | working / none | 开始干活 |
| `PreToolUse` | working / 按 `tool_name` 分色 | 干活中 |
| `PostToolUse` | working（成功）/ error（`tool_response.exit_code != 0`） | 出错检测 |
| `Stop` | done | 主回合结束 |
| `PermissionRequest` | needs_you | 要你批准（hooks 路；notify 的 `approval-requested` 是另一路，见 Task 4 说明） |
| `SubagentStart` / `SubagentStop` | None（忽略） | 不改主会话状态，与 Claude 对称 |
| 其它 | None | 忽略 |

**Files:**
- Modify: `daemon/vibelamp/normalize.py`
- Modify: `daemon/tests/test_normalize.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_normalize.py` 顶部 import 追加 `codex_transition, classify_codex_tool`：

```python
from vibelamp.normalize import (transition, classify_tool,
                                codex_transition, classify_codex_tool)
```

文件末尾追加用例：

```python
def test_classify_codex_tool():
    assert classify_codex_tool("apply_patch") == "code"
    assert classify_codex_tool("Bash") == "command"
    assert classify_codex_tool("shell") == "command"
    assert classify_codex_tool("read_file") == "search"
    assert classify_codex_tool("Grep") == "search"
    assert classify_codex_tool("update_plan") == "code"   # 默认归写码色
    assert classify_codex_tool(None) == "code"

def test_codex_user_prompt_submit_working():
    assert codex_transition({"hook_event_name": "UserPromptSubmit",
                             "session_id": "abc"}) == ("codex:abc", "working", "none")

def test_codex_pretooluse_classifies_tool():
    assert codex_transition({"hook_event_name": "PreToolUse", "session_id": "abc",
                             "tool_name": "Bash"}) == ("codex:abc", "working", "command")

def test_codex_posttooluse_ok_is_working():
    assert codex_transition({"hook_event_name": "PostToolUse", "session_id": "abc",
                             "tool_name": "apply_patch",
                             "tool_response": {"exit_code": 0}}) \
        == ("codex:abc", "working", "code")

def test_codex_posttooluse_nonzero_exit_is_error():
    assert codex_transition({"hook_event_name": "PostToolUse", "session_id": "abc",
                             "tool_name": "Bash",
                             "tool_response": {"exit_code": 2}}) \
        == ("codex:abc", "error", "none")

def test_codex_posttooluse_nested_exit_code_fallback():
    # exit_code 可能嵌在更深一层（字段层级未 100% 确认，做兜底）
    assert codex_transition({"hook_event_name": "PostToolUse", "session_id": "abc",
                             "tool_name": "Bash",
                             "tool_response": {"output": {"exit_code": 1}}}) \
        == ("codex:abc", "error", "none")

def test_codex_permission_request_needs_you():
    assert codex_transition({"hook_event_name": "PermissionRequest",
                             "session_id": "abc"}) == ("codex:abc", "needs_you", "none")

def test_codex_stop_done():
    assert codex_transition({"hook_event_name": "Stop", "session_id": "abc"}) \
        == ("codex:abc", "done", "none")

def test_codex_session_start_idle():
    assert codex_transition({"hook_event_name": "SessionStart", "session_id": "abc"}) \
        == ("codex:abc", "idle", "none")

def test_codex_missing_session_id_defaults():
    assert codex_transition({"hook_event_name": "Stop"}) == ("codex:default", "done", "none")

def test_codex_subagent_ignored():
    assert codex_transition({"hook_event_name": "SubagentStop",
                             "session_id": "abc"}) is None

def test_codex_alt_session_id_keys_fallback():
    # session_id 字段名未来若变体（thread_id/conversation_id），做兜底
    assert codex_transition({"hook_event_name": "Stop",
                             "thread_id": "t9"}) == ("codex:t9", "done", "none")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: ImportError（`codex_transition` / `classify_codex_tool` 不存在）。

- [ ] **Step 3: 在 `normalize.py` 追加 Codex 部分**

在 `normalize.py` 末尾追加（不动已有 Claude 部分）：

```python
# —— Codex 工具分类 ——
# Codex 工具名见官方："Bash", "apply_patch", "shell" 或 MCP 名
_CODEX_CODE = {"apply_patch", "update_plan", "edit_file", "write_file"}
_CODEX_COMMAND = {"Bash", "shell", "local_shell", "exec_command"}
_CODEX_SEARCH = {"read_file", "list_files", "Grep", "Glob", "search", "web_search"}


def classify_codex_tool(tool_name):
    if tool_name in _CODEX_CODE:
        return "code"
    if tool_name in _CODEX_COMMAND:
        return "command"
    if tool_name in _CODEX_SEARCH:
        return "search"
    return "code"   # 默认归写码色（与 Claude 端一致）


def _codex_session_id(event):
    # session_id 是官方确认字段；thread_id/conversation_id 作未来变体兜底
    raw = (event.get("session_id")
           or event.get("thread_id")
           or event.get("conversation_id")
           or "default")
    return "codex:" + raw


def _codex_exit_code(event):
    """从 tool_response 多候选层级取 exit_code；取不到返回 0（视为成功）。"""
    tr = event.get("tool_response")
    if not isinstance(tr, dict):
        return 0
    if "exit_code" in tr:
        return tr.get("exit_code") or 0
    out = tr.get("output")
    if isinstance(out, dict) and "exit_code" in out:
        return out.get("exit_code") or 0
    return 0


def codex_transition(event):
    """Codex 钩子 JSON → (session_id, state, tool)；返回 None 表示忽略。"""
    name = event.get("hook_event_name")
    sid = _codex_session_id(event)
    if name == "UserPromptSubmit":
        return (sid, "working", "none")
    if name == "PreToolUse":
        return (sid, "working", classify_codex_tool(event.get("tool_name")))
    if name == "PostToolUse":
        if _codex_exit_code(event) != 0:
            return (sid, "error", "none")
        return (sid, "working", classify_codex_tool(event.get("tool_name")))
    if name == "PermissionRequest":
        return (sid, "needs_you", "none")
    if name == "Stop":
        return (sid, "done", "none")
    if name == "SessionStart":
        return (sid, "idle", "none")
    return None
```

> 说明：Codex 没有 `SessionEnd` 钩子（官方事件清单里没有），死会话靠计划 02 `SessionStore` 的 `SESSION_TTL_SEC` 超时兜底清理——这正是计划 02 已建好的机制，无需 Codex 侧显式 REMOVE。`error` 状态短暂，下一次工具事件覆盖回 working（与设计文档/计划 02 一致）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_normalize.py -v`
Expected: 全 PASS（Claude 用例 + 新 Codex 用例）。

- [ ] **Step 5: 提交**

```bash
cd daemon && git add vibelamp/normalize.py tests/test_normalize.py
git commit -m "feat(daemon): Codex 事件归一化 + codex: 命名空间前缀 + exit_code 兜底"
```

---

## Task 3: server.py 端点路由分流（改 02，TDD）

计划 02 的 `server.py` 只认一个 `/event`（写死调 `transition`）。这里改成按 path 分流：`/event` → Claude，`/event/codex` → Codex。两个端点都进同一个 `store` 和同一个推灯逻辑。

**Files:**
- Modify: `daemon/vibelamp/server.py`
- Create: `daemon/tests/test_server_routing.py`

- [ ] **Step 1: 写失败测试**

`tests/test_server_routing.py`：

```python
import vibelamp.server as server
from vibelamp.model import REMOVE


def _fresh_store(monkeypatch):
    # 用全新的空 store，避免跨用例污染；并把推灯打桩成记录最后一次 payload
    from vibelamp.model import SessionStore
    from vibelamp import config
    store = SessionStore(config.SESSION_TTL_SEC)
    monkeypatch.setattr(server, "store", store)
    pushed = []
    monkeypatch.setattr(server, "_push_current", lambda: pushed.append(store.to_wire()))
    return store, pushed


def test_route_event_to_claude(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    server.handle_path_event("/event",
        {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Edit"})
    assert "claude:s1" in store._sessions
    assert pushed[-1] == {"sessions": [{"state": "working", "tool": "code"}]}


def test_route_event_codex_to_codex(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    server.handle_path_event("/event/codex",
        {"hook_event_name": "PreToolUse", "session_id": "abc", "tool_name": "Bash"})
    assert "codex:abc" in store._sessions
    assert pushed[-1] == {"sessions": [{"state": "working", "tool": "command"}]}


def test_two_agents_coexist_namespaced(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    server.handle_path_event("/event",
        {"hook_event_name": "PreToolUse", "session_id": "x", "tool_name": "Edit"})
    server.handle_path_event("/event/codex",
        {"hook_event_name": "PermissionRequest", "session_id": "x"})
    # 同名裸 id "x" 不撞车：claude:x 与 codex:x 并存
    assert set(store._sessions) == {"claude:x", "codex:x"}
    states = [s["state"] for s in store.to_wire()["sessions"]]
    assert states == ["needs_you", "working"]   # needs_you 优先在前


def test_unknown_path_returns_none(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    out = server.handle_path_event("/nope", {"hook_event_name": "Stop"})
    assert out is False        # 未知路径
    assert pushed == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_server_routing.py -v`
Expected: AttributeError（`handle_path_event` / `_push_current` 不存在）。

- [ ] **Step 3: 改 `server.py`**

把计划 02 `server.py` 里这个函数：

```python
def handle_event(event):
    t = transition(event)
    if t is None:
        return
    sid, state, tool = t
    store.update(sid, state, tool)
    lamp_client.push(store.to_wire())
```

替换成（新增 import + 路由分流 + 抽出 `_push_current`）：

```python
from .normalize import transition, codex_transition

# path → 归一化器
_ROUTES = {
    "/event": transition,
    "/event/codex": codex_transition,
}


def _push_current():
    lamp_client.push(store.to_wire())


def handle_path_event(path, event):
    """按端点路由到对应归一化器。未知路径返回 False。"""
    normalize_fn = _ROUTES.get(path)
    if normalize_fn is None:
        return False
    t = normalize_fn(event)
    if t is None:
        return True       # 路径有效但事件被忽略
    sid, state, tool = t
    store.update(sid, state, tool)
    _push_current()
    return True
```

并删除原文件顶部 `from .normalize import transition`（已并入上面那行）。`_heartbeat_loop` 里的 `lamp_client.push(store.to_wire())` 可保留原样，也可改调 `_push_current()`（等价）；推荐改成 `_push_current()` 收口。

- [ ] **Step 4: 改 `Handler.do_POST` 走路由**

把计划 02 `Handler.do_POST` 里这段：

```python
        if self.path != "/event":
            self.send_response(404); self.end_headers(); return
```

…以及随后调用 `handle_event(event)` 的那段，整体改为：先读 path、读 body、解析 JSON，再调 `handle_path_event`，未知路径回 404。完整 `do_POST`：

```python
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            event = json.loads(body or b"{}")
        except Exception:
            self.send_response(400); self.end_headers(); return
        try:
            ok = handle_path_event(self.path, event)
        except Exception as e:
            log.exception("handle_path_event failed: %s", e)   # 绝不让钩子失败
            ok = True
        if not ok:
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok":true}')
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_server_routing.py -v`
Expected: 4 个 PASS。

- [ ] **Step 6: 全量回归（确保没碰坏计划 02）**

Run: `cd daemon && python -m pytest -v`
Expected: model / normalize / lamp_client / install / server_routing 全绿。

- [ ] **Step 7: 提交**

```bash
cd daemon && git add vibelamp/server.py tests/test_server_routing.py
git commit -m "feat(daemon): server 按端点分流 /event 与 /event/codex"
```

---

## Task 4: config 增加 Codex 路径常量（改 02）

**Files:**
- Modify: `daemon/vibelamp/config.py`

- [ ] **Step 1: 在 `config.py` 末尾追加**

```python
from pathlib import Path

# —— Codex 配置文件路径 ——
CODEX_DIR = Path.home() / ".codex"
CODEX_HOOKS_JSON = CODEX_DIR / "hooks.json"     # sidecar 纯 JSON 钩子文件
CODEX_CONFIG_TOML = CODEX_DIR / "config.toml"   # 仅追加 hooks 指针注释 + notify 一行
```

> 注：`CODEX_DIR` 里 `import os` 在计划 02 已存在，这里只补 `from pathlib import Path`。若计划 02 的 config.py 顶部已 import Path，本步去掉重复行即可。

- [ ] **Step 2: 验证可导入**

Run: `cd daemon && python -c "from vibelamp import config as c; print(c.CODEX_HOOKS_JSON, c.CODEX_CONFIG_TOML)"`
Expected: 打印 `.../.codex/hooks.json .../.codex/config.toml`（家目录展开）。

- [ ] **Step 3: 提交**

```bash
cd daemon && git add vibelamp/config.py
git commit -m "feat(daemon): config 增加 Codex hooks.json/config.toml 路径常量"
```

---

## Task 5: 先抓真实 Codex payload + 真实 hooks.json 结构（验证锁定，无代码产出）

**这是本计划的关键防呆任务**，专门解决「文档对 hooks.json 顶层结构有冲突」「`exit_code` 层级 / `session_id` 字段名未 100% 确认」两个不确定项。**Task 6 的 install.py 与 Task 2 的 normalize 兜底，都以这一步抓到的真实数据为准。** 没跑通这一步前，不要把 merge/映射当成定论。

> 前置：本机已装 `codex` CLI 且能起一次真实会话。若本机没有 Codex，本任务只能跳过——届时 install.py 与 normalize 按文档默认值（裹 `hooks` key、`tool_response.exit_code`、`session_id`）走，并在自查记录里标注「未经真机核对」。

- [ ] **Step 1: 放一个临时 logging 钩子（手动）**

写一个把 stdin 原样 dump 到文件的脚本 `/tmp/codex_dump.sh`：

```bash
cat > /tmp/codex_dump.sh <<'EOF'
#!/bin/bash
cat >> /tmp/codex_hook_payloads.ndjson
echo >> /tmp/codex_hook_payloads.ndjson
echo '{"continue": true}'
EOF
chmod +x /tmp/codex_dump.sh
```

在 `~/.codex/hooks.json` 临时放（**先备份原文件**）——**两种顶层形状各试一次**，看 codex 接受哪个：

形状 A（裹 `hooks` key，本计划默认假设）：
```json
{ "hooks": {
  "SessionStart":     [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}],
  "UserPromptSubmit": [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}],
  "PreToolUse":       [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}],
  "PostToolUse":      [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}],
  "Stop":             [{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}],
  "PermissionRequest":[{"matcher": "*", "hooks": [{"type": "command", "command": "/tmp/codex_dump.sh"}]}]
}}
```

形状 B（事件名直接做顶层 key）：把上面最外层的 `{"hooks": {...}}` 去掉，只留 `{...}`。

- [ ] **Step 2: 跑一次真实 Codex 会话触发各事件**

Run: 起 `codex`，发一条会让它跑工具的指令（如「列出当前目录并改一个文件」），跑到要批准（触发 PermissionRequest）、完成（触发 Stop）。

- [ ] **Step 3: 核对 dump，锁定四件事**

Run: `cat /tmp/codex_hook_payloads.ndjson | python3 -m json.tool` 逐条看。**确认并记录**：
1. **哪种顶层形状（A 还是 B）被 codex 实际加载**（哪个形状下 dump 文件有内容）→ 决定 Task 6 merge 写哪种。
2. 事件名字段确实是 `hook_event_name`、值确实是 `PreToolUse`/`Stop`/... 大小写一致。
3. 会话 id 字段确实是 `session_id`（若不是，记下真实名——Task 2 的 `_codex_session_id` 已有 thread_id/conversation_id 兜底，必要时补真实名）。
4. PostToolUse 的 `tool_response` 里 `exit_code` 的确切层级与键名（顶层 / `output` 下 / 别的）→ 必要时回 Task 2 的 `_codex_exit_code` 补一层候选。

- [ ] **Step 4: 还原临时钩子**

Run: 删除 `/tmp/codex_dump.sh` 引用，恢复 `~/.codex/hooks.json` 备份（或清空），避免临时钩子残留影响 Task 6 的幂等测试。

- [ ] **Step 5: 把核对结论写进计划自查记录**

把 Step 3 的四项结论补到本文件「自查记录」段的「真机核对」条目下（形状 A/B、字段名、exit_code 层级）。**若任一项与文档默认不符，必须先回改 Task 2/Task 6 再继续。**

> 本任务无 commit（只抓数据 + 决策）；若据此回改了 Task 2/Task 6 的代码，跟随各自任务提交。

---

## Task 6: Codex 配置幂等写入（install.py，TDD）

stdlib 不能写 TOML（`tomllib` 只读），所以策略是：**hooks 全写进纯 JSON 的 `~/.codex/hooks.json`**（用可测纯函数 `merge_codex_hooks` / `remove_codex_hooks` 合并，结构以 Task 5 锁定的形状为准，默认形状 A 裹 `hooks` key），**config.toml 只做最小化文本追加**——一行指向 hooks 的注释提示 + 一行 `notify`（纯文本幂等追加 `ensure_codex_toml_lines`，不解析 TOML）。

> 为什么 config.toml 还要追加：sidecar `~/.codex/hooks.json` 官方说会自动加载（Task 5 已验证），所以 hooks 本身**不依赖** config.toml。config.toml 只用来加 `notify`（hooks 没有「turn-complete/approval」这种 Claude 的 Notification/Stop 对等语义之外的兜底通道，notify 是 Codex 给完成/批准的 legacy 通道，作为 hooks 的冗余）。若 Task 5 发现 hooks.json 不被自动加载，则改为在 config.toml 追加一行 `[[hooks...]]` 指针——此分支在 Step 3 的注释里给了备选文本。

**Codex 钩子命令**（与计划 02 Claude 钩子同形，只是 POST 到 `/event/codex`）：

```
curl -s --max-time 1 -X POST http://127.0.0.1:8787/event/codex --data-binary @- || true
```

**notify 程序**：notify 的 payload 是 kebab-case（`type`=`agent-turn-complete`/`approval-requested`），与 hooks 的 snake_case payload 不同。但守护进程的 Codex 端点已通过 hooks 的 `Stop`/`PermissionRequest` 覆盖了「完成/要批准」，**notify 在 v1 仅作冗余**：我们让 notify 也 POST 到 `/event/codex`，但 payload 字段名不同（kebab-case），`codex_transition` 认不出 `type` 字段会返回 None（被忽略，不报错）。因此 v1 的 notify 只是「装上备用通道、不依赖它生效」。**这是有意的简化**，写进自查记录。（真正消费 notify 的 kebab-case payload 留作后续计划，避免本计划膨胀。）

**Files:**
- Modify: `daemon/install.py`
- Create: `daemon/tests/test_install_codex.py`

- [ ] **Step 1: 写失败测试**

`tests/test_install_codex.py`：

```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "install", pathlib.Path(__file__).resolve().parent.parent / "install.py")
install = importlib.util.module_from_spec(spec); spec.loader.exec_module(install)

CODEX_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse",
                "PostToolUse", "Stop", "PermissionRequest"]


def _all_cmds(hooks_obj):
    """从 hooks.json 顶层对象（裹 hooks key 形状）收集所有 command 字符串。"""
    h = hooks_obj.get("hooks", {})
    return [hook["command"]
            for ev in h.values() for grp in ev for hook in grp["hooks"]]


def test_codex_merge_into_empty():
    out = install.merge_codex_hooks({})
    for ev in CODEX_EVENTS:
        assert ev in out["hooks"]
    cmds = _all_cmds(out)
    assert any("/event/codex" in c for c in cmds)


def test_codex_merge_is_idempotent():
    once = install.merge_codex_hooks({})
    twice = install.merge_codex_hooks(once)
    assert once == twice          # 重复跑不叠加


def test_codex_merge_preserves_user_hooks():
    user = {"hooks": {"Stop": [{"matcher": "*", "hooks":
            [{"type": "command", "command": "echo mine"}]}]}}
    out = install.merge_codex_hooks(user)
    cmds = _all_cmds(out)
    assert "echo mine" in cmds                      # 用户的还在
    assert any("/event/codex" in c for c in cmds)   # 我们的也加上


def test_codex_remove_only_ours():
    merged = install.merge_codex_hooks({"hooks": {"Stop": [{"matcher": "*", "hooks":
             [{"type": "command", "command": "echo mine"}]}]}})
    cleaned = install.remove_codex_hooks(merged)
    cmds = _all_cmds(cleaned)
    assert "echo mine" in cmds
    assert all("/event/codex" not in c for c in cmds)


def test_codex_merge_reads_unwrapped_shape():
    # 容错：用户文件是「事件名直接做顶层 key」（形状 B）也不丢
    user_b = {"Stop": [{"matcher": "*", "hooks":
              [{"type": "command", "command": "echo b"}]}]}
    out = install.merge_codex_hooks(user_b)
    assert "echo b" in _all_cmds(out)
    assert any("/event/codex" in c for c in _all_cmds(out))


def test_ensure_toml_lines_idempotent():
    base = "model = \"o1\"\n"
    once = install.ensure_codex_toml_lines(base)
    twice = install.ensure_codex_toml_lines(once)
    assert once == twice                            # 不重复追加
    assert "notify" in once
    assert "model = \"o1\"" in once                 # 原内容保留


def test_ensure_toml_lines_preserves_existing_notify():
    base = "notify = [\"my-notifier\"]\n"
    out = install.ensure_codex_toml_lines(base)
    # 已有用户 notify：不覆盖、不重复加我们的（避免抢占）
    assert out.count("notify") == 1
    assert "my-notifier" in out


def test_strip_toml_lines_removes_ours():
    base = "model = \"o1\"\n"
    added = install.ensure_codex_toml_lines(base)
    stripped = install.strip_codex_toml_lines(added)
    assert "VIBELAMP" not in stripped
    assert "model = \"o1\"" in stripped
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd daemon && python -m pytest tests/test_install_codex.py -v`
Expected: 失败（`merge_codex_hooks` 等不存在）。

- [ ] **Step 3: 在 `install.py` 追加 Codex 纯函数**

在 `install.py` 末尾（CLI 的 `if __name__` 块**之前**）追加：

```python
# ============ Codex 钩子（sidecar hooks.json + config.toml 最小追加） ============

CODEX_HOOK_CMD = ('curl -s --max-time 1 -X POST '
                  'http://127.0.0.1:8787/event/codex --data-binary @- || true')
CODEX_EVENTS = ["SessionStart", "UserPromptSubmit", "PreToolUse",
                "PostToolUse", "Stop", "PermissionRequest"]

CODEX_HOOKS_JSON = Path.home() / ".codex" / "hooks.json"
CODEX_CONFIG_TOML = Path.home() / ".codex" / "config.toml"

# config.toml 里我们追加的块，用 VIBELAMP 标记包裹，便于幂等检测与精确移除
_TOML_BEGIN = "# >>> VIBELAMP BEGIN (managed by vibelamp install.py) >>>"
_TOML_END = "# <<< VIBELAMP END <<<"
# notify 作为 hooks 的冗余通道（payload 为 kebab-case，v1 仅装上不强依赖）
_TOML_BODY = (
    'notify = ["curl", "-s", "--max-time", "1", "-X", "POST", '
    '"http://127.0.0.1:8787/event/codex", "--data-binary", "@-"]'
)


def _codex_block():
    return {"matcher": "*", "hooks":
            [{"type": "command", "command": CODEX_HOOK_CMD, "timeout": 2}]}


def _codex_event_map(hooks_obj):
    """从用户对象取出事件名→matcher组 的 map，容错两种顶层形状。
    形状 A：{"hooks": {"Stop": [...]}}  形状 B：{"Stop": [...]}
    统一返回内层 map 的浅拷贝。"""
    obj = dict(hooks_obj or {})
    if "hooks" in obj and isinstance(obj["hooks"], dict):
        return {k: list(v) for k, v in obj["hooks"].items()}
    # 形状 B：除保留键外，把顶层当事件 map（只认看起来像事件名的 key）
    return {k: list(v) for k, v in obj.items()
            if isinstance(v, list)}


def merge_codex_hooks(hooks_obj):
    """幂等：把 vibelamp 的 curl 钩子合进各事件；保留用户已有钩子。
    输出统一为形状 A：{"hooks": {event: [...]}}。"""
    events = _codex_event_map(hooks_obj)
    for ev in CODEX_EVENTS:
        entries = list(events.get(ev) or [])
        already = any(
            any(h.get("command") == CODEX_HOOK_CMD for h in (e.get("hooks") or []))
            for e in entries)
        if not already:
            entries.append(_codex_block())
        events[ev] = entries
    return {"hooks": events}


def remove_codex_hooks(hooks_obj):
    """只移除我们加的 curl 钩子，保留用户其它钩子。输出形状 A。"""
    events = _codex_event_map(hooks_obj)
    for ev in list(events.keys()):
        kept = [e for e in events[ev]
                if not any(h.get("command") == CODEX_HOOK_CMD
                           for h in (e.get("hooks") or []))]
        if kept:
            events[ev] = kept
        else:
            del events[ev]
    return {"hooks": events}


def ensure_codex_toml_lines(text):
    """幂等地在 config.toml 文本末尾追加 VIBELAMP 标记块（含 notify）。
    已存在我们的标记块 → 原样返回；用户已有自己的 notify → 不抢占（不加我们的 notify）。"""
    text = text or ""
    if _TOML_BEGIN in text:
        return text                       # 已装，幂等返回
    # 用户已有 notify（非我们的）→ 尊重之，不覆盖、不追加（避免双 notify 冲突）
    import re as _re
    has_user_notify = bool(_re.search(r'(?m)^\s*notify\s*=', text))
    block = "\n".join([_TOML_BEGIN, _TOML_BODY, _TOML_END]) + "\n"
    if has_user_notify:
        # 只放标记 + 说明，不放我们的 notify（hooks 已覆盖完成/批准语义）
        block = "\n".join([
            _TOML_BEGIN,
            "# 检测到用户已配置 notify，vibelamp 不覆盖；",
            "# Codex 状态已通过 ~/.codex/hooks.json 的钩子推送给守护进程。",
            _TOML_END]) + "\n"
    sep = "" if text.endswith("\n") or text == "" else "\n"
    return text + sep + "\n" + block


def strip_codex_toml_lines(text):
    """移除 VIBELAMP 标记块（含其间所有行），保留其余内容。"""
    text = text or ""
    if _TOML_BEGIN not in text or _TOML_END not in text:
        return text
    lines = text.splitlines(keepends=True)
    out, skipping = [], False
    for ln in lines:
        if ln.strip() == _TOML_BEGIN:
            skipping = True
            continue
        if ln.strip() == _TOML_END:
            skipping = False
            continue
        if not skipping:
            out.append(ln)
    return "".join(out)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd daemon && python -m pytest tests/test_install_codex.py -v`
Expected: 8 个 PASS。

- [ ] **Step 5: 把 Codex IO 接进 install()/uninstall()**

在 `install.py` 的 `install()` 函数末尾（计划 02 已有的 launchd 加载之后）追加：

```python
    _install_codex()
```

在 `uninstall()` 末尾追加：

```python
    _uninstall_codex()
```

并在 CLI 块之前追加这两个 IO 包装：

```python
def _read_text_or_empty(path):
    return path.read_text() if path.exists() else ""


def _load_codex_hooks():
    if CODEX_HOOKS_JSON.exists():
        try:
            return json.loads(CODEX_HOOKS_JSON.read_text() or "{}")
        except Exception:
            return {}
    return {}


def _install_codex():
    CODEX_HOOKS_JSON.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_codex_hooks(_load_codex_hooks())
    CODEX_HOOKS_JSON.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"✅ Codex 钩子已写入 {CODEX_HOOKS_JSON}")
    toml_text = ensure_codex_toml_lines(_read_text_or_empty(CODEX_CONFIG_TOML))
    CODEX_CONFIG_TOML.write_text(toml_text)
    print(f"✅ Codex config.toml 已追加 notify（{CODEX_CONFIG_TOML}）")


def _uninstall_codex():
    cleaned = remove_codex_hooks(_load_codex_hooks())
    if CODEX_HOOKS_JSON.exists():
        CODEX_HOOKS_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False))
    if CODEX_CONFIG_TOML.exists():
        CODEX_CONFIG_TOML.write_text(
            strip_codex_toml_lines(_read_text_or_empty(CODEX_CONFIG_TOML)))
    print("✅ 已移除 Codex 钩子与 config.toml 追加块")
```

- [ ] **Step 6: 全量回归（确保没碰坏计划 02 的 install 测试）**

Run: `cd daemon && python -m pytest -v`
Expected: 全绿（含计划 02 的 `test_install.py` + 新 `test_install_codex.py`）。

- [ ] **Step 7: 实跑安装并核对落盘（注意先备份 Task 5 验证后的真实文件）**

Run:
```bash
cd daemon && python install.py install
python -m json.tool ~/.codex/hooks.json | grep -c '/event/codex'   # 应 = 6（6 个事件各一条）
grep -c VIBELAMP ~/.codex/config.toml                              # 应 >= 2（BEGIN/END 各一）
```
Expected: hooks.json 有 6 条 `/event/codex` 钩子；config.toml 有 VIBELAMP 标记块。再跑一次 `python install.py install`，上述计数不变（幂等）。

- [ ] **Step 8: 提交**

```bash
cd daemon && git add install.py tests/test_install_codex.py
git commit -m "feat(daemon): Codex 配置幂等写入（hooks.json + config.toml 最小追加）"
```

---

## Task 7: 真实 Codex 会话端到端 + 双 agent 分段验证（无新代码）

纯集成验证：装好钩子后跑真实 Codex 会话，再 Claude + Codex 同开看灯环分段。需计划 01 的灯（最好是灯环 env）在线、守护进程在跑（计划 02 的 launchd 已自启）。

- [ ] **Step 1: 单 Codex 会话驱动灯**

Run: 起 `codex`，发指令让它跑工具、要一次批准、完成。
Expected: 灯依次 **蓝呼吸（开始）→ 紫呼吸（跑 Bash）/ 蓝（apply_patch）→ 红慢闪（要批准）→ 绿渐暗（完成）**。出错的命令（非零退出）应见 **红快闪一下** 再弹回干活色。

- [ ] **Step 2: curl 模拟双 agent 并存（不依赖真机 Codex 也能验路由）**

Run（守护进程在跑时）:
```bash
C=http://127.0.0.1:8787/event
X=http://127.0.0.1:8787/event/codex
curl -s -X POST $C -d '{"hook_event_name":"PreToolUse","session_id":"x","tool_name":"Edit"}'
curl -s -X POST $X -d '{"hook_event_name":"PermissionRequest","session_id":"x"}'
```
Expected: 同名裸 id `x` 不撞车——灯环 **一段蓝呼吸（claude:x 干活）+ 一段红慢闪（codex:x 要批准）**，红段排在前（needs_you 优先）。这直接证明命名空间隔离生效（若没隔离，第二条会覆盖第一条只剩一段）。

- [ ] **Step 3: 真实双 agent 同开**

Run: 一个终端开 Claude Code 跑任务，另一个终端开 Codex 跑任务。
Expected: 灯环两段各自实时反映两个 agent 的真实状态，互不干扰。

- [ ] **Step 4: 卸载干净（核对不误删用户配置）**

Run: `cd daemon && python install.py uninstall`
Expected: `~/.codex/hooks.json` 里我们的 `/event/codex` 钩子被移除、用户原有钩子保留；`~/.codex/config.toml` 的 VIBELAMP 标记块被精确移除、其余配置（model/notify 等）原样保留。

---

## 验收（整计划完成标准）

- `cd daemon && python -m pytest` 全绿——含计划 02 的 model/normalize/lamp_client/install 四组（normalize 已更新为带 `claude:` 前缀）+ 本计划新增 normalize Codex 用例、`test_server_routing.py`、`test_install_codex.py`。
- 命名空间隔离生效：`claude:x` 与 `codex:x` 在 store 中并存（Task 3 / Task 7 Step 2 双重验证）。
- `python install.py install` 幂等写入 `~/.codex/hooks.json`（6 事件各一条 `/event/codex` 钩子）+ `config.toml` 最小追加；重复跑不叠加；`uninstall` 精确移除且保留用户原有配置。
- 真实 Codex 会话能驱动灯全部状态（开始/工具分色/出错/要批准/完成）；Claude + Codex 同开灯环分段显示。
- **Task 5 的真机核对结论已回填自查记录**（hooks.json 形状、字段名、exit_code 层级）；任何与文档默认不符之处已回改代码。

## 后续计划

- **计划 04 — 网页配网（WiFiManager）+ BLE 兜底/配网**（计划 01/02 已列）。
- **Codex notify kebab-case payload 真正消费**（本计划仅把 notify 通道装上、未解析其 `type`=`agent-turn-complete`/`approval-requested`；若实践中发现 hooks 的 Stop/PermissionRequest 不够及时，再把 notify 的 kebab-case 字段接进一个 `/event/codex-notify` 端点专门归一化）。
- **更多 agent（Gemini CLI、Cursor 等）**：复用本计划的「新端点 + 新 `*_transition` + 新前缀 + install 加配置」模式，正交扩展。

## 自查记录

- **Spec 覆盖**：设计文档 §3.1 的 Codex 钩子（SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop + notify 的 turn-complete/approval-requested）、§11 范围「Claude Code + Codex 钩子接入」、§12「Codex 是否提供稳定 session 标识需核实」「PreToolUse/PostToolUse 默认不装需手动配置」——均落到任务：稳定 session id 靠 `session_id`（官方确认）+ 命名空间前缀，PreToolUse/PostToolUse 靠 install.py 主动写进 hooks.json 而非依赖默认。
- **延续计划 02**：复用同一 `daemon/` 工程、同一 `SessionStore`/`lamp_client`/wire 协议、同一 TDD 与中文 `feat(daemon): ...` commit 风格；对计划 02 的改动**全部标注了改哪个文件、改哪几行、改成什么**（normalize 一行加前缀、server 的 handle_event 重构为 handle_path_event + 路由表、do_POST 走路由、config 加常量、install 末尾接 Codex）。
- **命名空间隔离**：`claude:<id>` / `codex:<id>` 前缀在 normalize 两端各自加；`SessionStore` 对 key 内容无感（计划 02 已是纯 dict key），不需改 model；隔离效果有 `test_two_agents_coexist_namespaced` 与端到端 curl 双重证明。wire 不暴露 agent 字段（固件是哑终端，只认状态色）。
- **诚实处理不确定项**：
  - **hooks.json 顶层结构两份权威说法冲突**（官方 config-advanced = 事件名直接顶层 / 社区详解 = 裹 `hooks` key）→ 默认裹 `hooks` key，merge 函数 `_codex_event_map` **容错读两种形状**（有 `test_codex_merge_reads_unwrapped_shape` 守卫），并由 **Task 5 真机核对最终锁定**。
  - **PostToolUse 无独立失败事件** → 从 `tool_response.exit_code` 推断，`_codex_exit_code` 做**多候选层级兜底**（顶层 / `output` 下），层级由 Task 5 核对。
  - **session_id 字段名**（官方确认 `session_id`，但留 `thread_id`/`conversation_id` 兜底，有 `test_codex_alt_session_id_keys_fallback` 守卫）。
- **靠「先抓真实 payload」兜底的点**（Task 5 专设）：hooks.json 实际被接受的顶层形状、事件名/会话 id/工具名字段确切名与大小写、`exit_code` 在 `tool_response` 的确切层级——这四项在 install.py / normalize 锁定前必须真机核对；无 Codex 本机时按文档默认走并明确标注「未经真机核对」。
- **有意简化**：notify 通道 v1 仅装上作冗余（payload 是 kebab-case，`codex_transition` 认不出 `type` 字段会安全返回 None），不真正消费——留后续计划；`error` 状态短暂靠下一事件覆盖（沿用计划 02）。
- **无占位**：每个代码步骤给完整可运行代码与确切命令、期望输出；IO/真机相关步骤给了备份提示与核对命令。
