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
