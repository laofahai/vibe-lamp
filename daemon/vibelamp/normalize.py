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
