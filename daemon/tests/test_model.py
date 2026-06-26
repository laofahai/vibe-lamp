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


# ——— ESC/kill 卡灯自愈：demote_stale（两档超时）———————————————

def test_demote_idle_timeout_no_tool():
    """没工具在跑、静默超过短超时 → 降级 idle（灯灭）。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "working", "code", in_flight=False)
    clock[0] += 100                  # 100s > 90s 短超时
    assert s.demote_stale(90, 600) == 1
    assert s.to_wire() == {"sessions": []}

def test_demote_leaves_fresh():
    """刚有过事件 → 远没超时，不动（正常干活不误杀）。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "working", "code")
    clock[0] += 10
    assert s.demote_stale(90, 600) == 0
    assert s.to_wire() == {"sessions": [{"state": "working", "tool": "code"}]}

def test_demote_tool_in_flight_uses_long_timeout():
    """有工具在跑（长构建）→ 用长超时：过了短超时也不灭，超过长超时才灭。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "working", "command", in_flight=True)
    clock[0] += 100                  # 已过 90s 短超时，但工具在跑 → 不灭（长构建不误杀）
    assert s.demote_stale(90, 600) == 0
    assert s.to_wire() == {"sessions": [{"state": "working", "tool": "command"}]}
    clock[0] += 600                  # 累计 700s > 600s 长超时 → 灭
    assert s.demote_stale(90, 600) == 1
    assert s.to_wire() == {"sessions": []}

def test_demote_keeps_needs_you():
    """needs_you(红·该你了)是要持续提醒的「找你」态——绝不被 90s 掐断，
    一直亮到你处理或会话 TTL 清理。这是用户明确要的行为。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "needs_you", "none")
    clock[0] += 100                  # 远超短超时，但 needs_you 不该被降级
    assert s.demote_stale(90, 600) == 0
    assert s.to_wire() == {"sessions": [{"state": "needs_you", "tool": "none"}]}

def test_demote_keeps_error():
    """error(红·快闪)同属「找你」态，也不被自愈掐断。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "error", "none")
    clock[0] += 100
    assert s.demote_stale(90, 600) == 0
    assert s.to_wire() == {"sessions": [{"state": "error", "tool": "none"}]}

def test_demote_skips_idle():
    """idle 本就是灭灯态，跳过（返回 0）。"""
    clock = [1000.0]
    s = SessionStore(ttl_sec=1800, clock=lambda: clock[0])
    s.update("a", "idle", "none")
    clock[0] += 9999
    assert s.demote_stale(90, 600) == 0


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
