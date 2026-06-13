from vibelamp.normalize import (transition, classify_tool,
                                codex_transition, classify_codex_tool)
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


def test_classify_tool_uses_config_map(monkeypatch):
    from vibelamp import normalize
    monkeypatch.setattr(normalize, "_CLAUDE_MAP", {"FooTool": "command"})
    assert normalize.classify_tool("FooTool") == "command"
    assert normalize.classify_tool("Unknown") == "code"   # 缺省仍 code
