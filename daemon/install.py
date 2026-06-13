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


def _backup_once(path):
    """首次改写用户文件前留一份 .vibelamp-bak 备份（已存在则不覆盖，保留最早原貌）。"""
    if path.exists():
        bak = path.with_name(path.name + ".vibelamp-bak")
        if not bak.exists():
            bak.write_text(path.read_text())


def _save_settings(settings):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    _backup_once(SETTINGS)
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
    _install_codex()
    _ensure_default_config()


def uninstall():
    _launchctl("unload", str(PLIST))
    if PLIST.exists():
        PLIST.unlink()
    _save_settings(remove_hooks(_load_settings()))
    print("✅ 已移除钩子与 launchd")
    _uninstall_codex()


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
            "# 检测到用户已配置通知命令，vibelamp 不覆盖；",
            "# Codex 状态已通过 ~/.codex/hooks.json 的钩子推送给守护进程。",
            _TOML_END]) + "\n"
    # 放到文件最前面：TOML 根键（notify）必须在所有 [table] 之前，
    # 否则追加到末尾会被当成最后那个表的子键而失效。
    return block + text


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
    _backup_once(CODEX_HOOKS_JSON)
    merged = merge_codex_hooks(_load_codex_hooks())
    CODEX_HOOKS_JSON.write_text(json.dumps(merged, indent=2, ensure_ascii=False))
    print(f"✅ Codex 钩子已写入 {CODEX_HOOKS_JSON}")
    _backup_once(CODEX_CONFIG_TOML)
    toml_text = ensure_codex_toml_lines(_read_text_or_empty(CODEX_CONFIG_TOML))
    CODEX_CONFIG_TOML.write_text(toml_text)
    print(f"✅ Codex config.toml 已写入 notify（置顶为根键）（{CODEX_CONFIG_TOML}）")


def _uninstall_codex():
    cleaned = remove_codex_hooks(_load_codex_hooks())
    if CODEX_HOOKS_JSON.exists():
        CODEX_HOOKS_JSON.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False))
    if CODEX_CONFIG_TOML.exists():
        CODEX_CONFIG_TOML.write_text(
            strip_codex_toml_lines(_read_text_or_empty(CODEX_CONFIG_TOML)))
    print("✅ 已移除 Codex 钩子与 config.toml 追加块")


def _ensure_default_config():
    from vibelamp import config as cfg
    path = cfg.CONFIG_PATH
    if path.exists():
        return                       # 已有就不覆盖用户改动
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg._DEFAULTS, indent=2, ensure_ascii=False))
    print(f"✅ 已生成默认配置 {path}（可编辑工具分色/超时等）")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "install"
    if cmd == "install":
        install()
    elif cmd == "uninstall":
        uninstall()
    else:
        print("用法: python install.py [install|uninstall]")
        sys.exit(1)
