from vibelamp.model import SessionStore, REMOVE

def test_empty_store_is_empty_sessions():
    s = SessionStore(ttl_sec=1800)
    assert s.to_wire() == {"sessions": []}

def test_single_session_in_wire():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "working", "code")
    assert s.to_wire() == {"sessions": [{"state": "working", "tool": "code"}]}

def test_idle_session_excluded():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "idle", "none")
    assert s.to_wire() == {"sessions": []}

def test_sessions_sorted_by_priority():
    s = SessionStore(ttl_sec=1800)
    s.update("a", "working", "code")
    s.update("b", "needs_you", "none")
    s.update("c", "done", "none")
    states = [x["state"] for x in s.to_wire()["sessions"]]
    assert states == ["needs_you", "working", "done"]  # needs_you 最优先

def test_remove_session():
    s = SessionStore(ttl_sec=1800)
    s.update("sid1", "working", "code")
    s.update("sid1", REMOVE, "none")
    assert s.to_wire() == {"sessions": []}

def test_sweep_expires_old_sessions():
    clock = [1000.0]
    s = SessionStore(ttl_sec=60, clock=lambda: clock[0])
    s.update("sid1", "working", "code")
    clock[0] = 1100.0   # 100s 后，超过 60s ttl
    s.sweep()
    assert s.to_wire() == {"sessions": []}


# ——— ESC/kill 卡蓝自愈：demote_stale_working ———————————————

def test_demote_stale_working_to_idle():
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "working", "code")
    clock[0] = 1000.0 + 200          # 200s 没新事件，超过 180s 阈值
    assert s.demote_stale_working(180) == 1
    assert s.to_wire() == {"sessions": []}   # 降级为 idle → 不再上灯（灯灭）

def test_demote_leaves_fresh_working():
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "working", "code")
    clock[0] = 1000.0 + 10           # 才 10s，远没超时（长构建静默期不误杀）
    assert s.demote_stale_working(180) == 0
    assert s.to_wire() == {"sessions": [{"state": "working", "tool": "code"}]}

def test_demote_ignores_non_working():
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "needs_you", "none")
    clock[0] = 1000.0 + 9999         # needs_you/done/error 是合法静止态，永不被降级
    assert s.demote_stale_working(180) == 0
    assert s.to_wire() == {"sessions": [{"state": "needs_you", "tool": "none"}]}


# ——— 调试面板快照：snapshot ————————————————————————————

def test_snapshot_shape():
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("claude:x", "working", "code")
    clock[0] = 1000.0 + 3
    assert s.snapshot() == [
        {"sid": "claude:x", "state": "working", "tool": "code", "age_sec": 3.0}]

def test_snapshot_includes_idle():
    s = SessionStore(ttl_sec=1800)
    s.update("claude:x", "idle", "none")    # idle 不上灯，但面板要看得见
    snap = s.snapshot()
    assert len(snap) == 1 and snap[0]["state"] == "idle"
