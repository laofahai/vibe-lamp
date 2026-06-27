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


def test_route_event_generic(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    server.handle_path_event("/event/generic",
        {"agent": "opencode", "session_id": "abc", "state": "working", "tool": "search"})
    assert "opencode:abc" in store._sessions
    assert pushed[-1] == {"sessions": [{"state": "working", "tool": "search"}]}


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


def test_generic_agent_coexists_with_existing_agents(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    server.handle_path_event("/event",
        {"hook_event_name": "PreToolUse", "session_id": "x", "tool_name": "Edit"})
    server.handle_path_event("/event/generic",
        {"agent": "qwen", "session_id": "x", "event": "permission"})
    assert set(store._sessions) == {"claude:x", "qwen:x"}
    states = [s["state"] for s in store.to_wire()["sessions"]]
    assert states == ["needs_you", "working"]


def test_unknown_path_returns_none(monkeypatch):
    store, pushed = _fresh_store(monkeypatch)
    out = server.handle_path_event("/nope", {"hook_event_name": "Stop"})
    assert out is False        # 未知路径
    assert pushed == []
