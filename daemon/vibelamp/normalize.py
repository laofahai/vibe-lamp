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
    sid = "claude:" + (event.get("session_id") or "default")
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
