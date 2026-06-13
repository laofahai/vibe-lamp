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
