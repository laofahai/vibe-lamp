import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "install", pathlib.Path(__file__).resolve().parent.parent / "install.py")
install = importlib.util.module_from_spec(spec); spec.loader.exec_module(install)

def test_merge_into_empty():
    out = install.merge_hooks({})
    assert "PreToolUse" in out["hooks"]
    assert "Stop" in out["hooks"]
    cmd = out["hooks"]["Stop"][0]["hooks"][0]["command"]
    assert "127.0.0.1:8787/event" in cmd

def test_merge_is_idempotent():
    once = install.merge_hooks({})
    twice = install.merge_hooks(once)
    assert once == twice                      # 重复跑不叠加

def test_merge_preserves_user_hooks():
    user = {"hooks": {"Stop": [{"matcher": "*", "hooks":
            [{"type": "command", "command": "echo mine"}]}]}}
    out = install.merge_hooks(user)
    cmds = [h["command"] for e in out["hooks"]["Stop"] for h in e["hooks"]]
    assert "echo mine" in cmds                # 用户的还在
    assert any("127.0.0.1:8787/event" in c for c in cmds)  # 我们的也加上了

def test_remove_only_ours():
    merged = install.merge_hooks({"hooks": {"Stop": [{"matcher": "*", "hooks":
             [{"type": "command", "command": "echo mine"}]}]}})
    cleaned = install.remove_hooks(merged)
    cmds = [h["command"] for e in cleaned["hooks"].get("Stop", []) for h in e["hooks"]]
    assert "echo mine" in cmds
    assert all("127.0.0.1:8787/event" not in c for c in cmds)
