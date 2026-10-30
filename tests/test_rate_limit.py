from personal_agent_memory.server.auth import rate_limit


def test_windows_expire_without_extending_blocked_attempts(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(rate_limit.time, 'monotonic', lambda: now[0])
    limiter = rate_limit.RateLimiter(2, max_keys=2)
    assert limiter.allow('a') and limiter.allow('a')
    assert not limiter.allow('a')
    assert limiter.allow('b')
    assert not limiter.allow('c')
    now[0] = 59
    assert not limiter.allow('a')
    now[0] = 60
    assert limiter.allow('c')
    assert list(limiter.attempts) == ['c']
    assert limiter.allow('a')
