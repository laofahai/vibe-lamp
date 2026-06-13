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
