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
