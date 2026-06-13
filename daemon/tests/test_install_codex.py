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
